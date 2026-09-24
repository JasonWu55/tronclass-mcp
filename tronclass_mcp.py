from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import html
import io
import json
import logging
import os
import re
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urljoin

import requests

from tronclass_api_catalog import TRONCLASS_API_COUNT, TRONCLASS_API_GROUPS, TRONCLASS_METHOD_COUNT

logger = logging.getLogger("tronclass.mcp")

_MCP_SERVER_AVAILABLE = False
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ImageContent, TextContent

    _MCP_SERVER_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]


DEFAULT_BASE_URL = "https://elearn2.fju.edu.tw"
DEFAULT_LOGIN_USER_AGENT = "TronClass/2.14.5 (iPhone; iOS 26.2; Scale/3.00)"
DEFAULT_API_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) TronClass/common"
)
_SAFE_HEADER_KEYS = {"content-type", "x-session-id", "set-cookie", "location"}
_DEFAULT_GROUP_LIMIT = 100
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".py", ".java",
    ".c", ".h", ".cpp", ".js", ".ts", ".sql", ".r", ".m", ".ipynb", ".yaml", ".yml",
}
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


class TronClassError(RuntimeError):
    """Base exception for TronClass failures."""


class TronClassAuthError(TronClassError):
    """Raised when login or session refresh fails."""


@dataclass(slots=True)
class TronClassConfig:
    base_url: str = DEFAULT_BASE_URL
    username: Optional[str] = None
    password: Optional[str] = None
    request_timeout: int = 30
    verify_tls: bool = True
    login_user_agent: str = DEFAULT_LOGIN_USER_AGENT
    api_user_agent: str = DEFAULT_API_USER_AGENT

    @classmethod
    def from_env(cls) -> "TronClassConfig":
        return cls(
            base_url=os.getenv("TRONCLASS_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            username=os.getenv("TRONCLASS_USERNAME"),
            password=os.getenv("TRONCLASS_PASSWORD"),
            request_timeout=int(os.getenv("TRONCLASS_TIMEOUT", "30")),
            verify_tls=_env_bool("TRONCLASS_VERIFY_TLS", True),
            login_user_agent=os.getenv("TRONCLASS_LOGIN_USER_AGENT", DEFAULT_LOGIN_USER_AGENT),
            api_user_agent=os.getenv("TRONCLASS_API_USER_AGENT", DEFAULT_API_USER_AGENT),
        )

    def validate_credentials(self) -> None:
        if not self.username or not self.password:
            raise TronClassAuthError(
                "Missing TronClass credentials. Set TRONCLASS_USERNAME and TRONCLASS_PASSWORD."
            )


def load_dotenv(*paths: Path) -> None:
    """Load KEY=VALUE lines from .env files without overriding variables already set."""
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


class TronClassClient:
    """Thin stateful client for TronClass CAS + API session management."""

    def __init__(
        self,
        config: Optional[TronClassConfig] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.config = config or TronClassConfig.from_env()
        self.session = session or requests.Session()
        self._lock = threading.Lock()
        self._session_id: Optional[str] = None
        self._user_id: Optional[int] = None

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def user_id(self) -> Optional[int]:
        return self._user_id

    def auth_status(self) -> dict[str, Any]:
        self._ensure_logged_in()
        return {
            "base_url": self.config.base_url,
            "user_id": self._user_id,
            "has_session_id": bool(self._session_id),
            "cookie_names": sorted(self.session.cookies.keys()),
            "verify_tls": self.config.verify_tls,
        }

    def upload_file(
        self,
        file_path: str,
        *,
        name: Optional[str] = None,
        parent_type: Optional[str] = None,
        parent_id: int = 0,
        source: str = "",
    ) -> dict[str, Any]:
        """Upload a local file to TronClass resource storage and mark it uploaded."""
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise TronClassError(f"Upload file not found: {path}")
        return self.upload_bytes(
            path.read_bytes(),
            name or path.name,
            parent_type=parent_type,
            parent_id=parent_id,
            source=source,
        )

    def upload_bytes(
        self,
        content: bytes,
        name: str,
        *,
        parent_type: Optional[str] = None,
        parent_id: int = 0,
        source: str = "",
    ) -> dict[str, Any]:
        """Upload in-memory file content to TronClass resource storage and mark it uploaded."""
        upload_name = name
        create_body = {
            "name": upload_name,
            "size": len(content),
            "parent_type": parent_type,
            "parent_id": parent_id,
            "is_scorm": False,
            "is_wmpkg": False,
            "source": source,
            "is_marked_attachment": False,
            "embed_material_type": "",
        }
        created = self.request("POST", "/api/uploads", json_body=create_body)
        if not created.get("ok"):
            return {"ok": False, "stage": "create_upload", "result": created}
        upload = created.get("data") or {}
        upload_url = upload.get("upload_url") or upload.get("url")
        upload_id = upload.get("id")
        if not upload_url or not upload_id:
            return {"ok": False, "stage": "create_upload", "result": created, "error": "Missing upload_url or id"}
        response = requests.put(
            upload_url,
            files={"file": (upload_name, content, "application/octet-stream")},
            timeout=self.config.request_timeout,
            verify=self.config.verify_tls,
        )
        if not response.ok:
            return {
                "ok": False,
                "stage": "upload_binary",
                "status": response.status_code,
                "text": response.text[:1000],
                "upload": upload,
            }
        uploaded = self.request("PUT", f"/api/uploads/{upload_id}/uploaded")
        return {
            "ok": bool(uploaded.get("ok")),
            "stage": "complete",
            "upload": upload,
            "binary_status": response.status_code,
            "mark_uploaded": uploaded,
        }

    def submit_homework_uploads(
        self,
        activity_id: int,
        upload_ids: list[int],
        *,
        comment: str = "",
        draft: bool = False,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Submit already-uploaded resource IDs to a homework activity."""
        status = self.auth_status()
        submitter_id = user_id or status.get("user_id")
        if not submitter_id:
            raise TronClassError("Cannot submit homework because authenticated user_id is unknown.")
        current = self.request("GET", f"/api/course/activities/{activity_id}/students/{submitter_id}/submission")
        uploads = []
        for upload_id in upload_ids:
            uploads.append({"id": upload_id})
        body = {"comment": comment, "uploads": uploads, "is_draft": draft}
        result = self.request(
            "POST",
            f"/api/course/activities/{activity_id}/students/{submitter_id}/submission",
            json_body=body,
        )
        if not result.get("ok"):
            # Some TronClass deployments require PUT for resubmission. Return both attempts for diagnostics.
            put_result = self.request(
                "PUT",
                f"/api/course/activities/{activity_id}/students/{submitter_id}/submission",
                json_body=body,
            )
            result = {"ok": bool(put_result.get("ok")), "post_result": result, "put_result": put_result}
        verify = self.request("GET", f"/api/course/activities/{activity_id}/students/{submitter_id}/submission")
        return {"ok": bool(result.get("ok")), "submission": verify.get("data"), "result": result, "previous": current.get("data")}

    def list_peer_review_todos(self) -> dict[str, Any]:
        """Return todo items that look like peer-review work for the authenticated student."""
        result = self.request("GET", "/api/todos")
        todos = (result.get("data") or {}).get("todo_list") or []
        peer_review_todos = []
        for todo in todos:
            if todo.get("not_scored_num") or "互評" in str(todo.get("title") or ""):
                peer_review_todos.append(todo)
        return {"ok": result.get("ok"), "count": len(peer_review_todos), "items": peer_review_todos, "raw": result}

    def get_peer_submission(self, activity_id: int, submitter_id: int) -> dict[str, Any]:
        """Fetch a submitter's homework submission for peer-review inspection."""
        return self.request("GET", f"/api/course/activities/{activity_id}/students/{submitter_id}/submission")

    def submit_peer_review_score(
        self,
        activity_id: int,
        submitter_id: int,
        score: float,
        comment: str,
        *,
        inter_score_id: Optional[int] = None,
        upload_ids: Optional[list[int]] = None,
        rubric_score: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Submit/update a student peer-review score and plain-text comment.

        TronClass' web UI sends peer-review marks through the shared homework
        correction endpoint with student_id + reviewer_comment. The endpoint is
        also used by instructor marking, so callers must pass the intended
        submitter_id explicitly and verify the target submission afterward.
        """
        body: dict[str, Any] = {
            "student_id": submitter_id,
            "score": f"{float(score):.1f}",
            "reviewer_comment": comment,
            "uploads": upload_ids or [],
        }
        if rubric_score is not None:
            body["rubric_score"] = rubric_score
        if inter_score_id is not None:
            result = self.request("PUT", f"/api/inter-scores/{inter_score_id}", json_body=body)
        else:
            # Instructor-style fallback retained for older/manual workflows, but student
            # peer review normally requires the assigned inter_score_id endpoint above.
            result = self.request(
                "PUT",
                f"/api/course/activities/{activity_id}/submission/score",
                params={"fields": "id,score,instructor_comment,rubric_score,final_score", "need_submission_correct": "true"},
                json_body={**body, "rubric_score": rubric_score or []},
            )
        verify = self.get_peer_submission(activity_id, submitter_id)
        return {"ok": bool(result.get("ok")), "result": result, "submission": verify.get("data")}

    def download_upload(
        self,
        *,
        upload_id: Optional[int] = None,
        reference_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Download an uploaded file's bytes by upload ID or reference ID."""
        if (upload_id is None) == (reference_id is None):
            raise TronClassError("Pass exactly one of upload_id or reference_id.")
        if upload_id is not None:
            path = f"/api/uploads/{upload_id}/blob"
        else:
            path = f"/api/uploads/reference/{reference_id}/blob"

        self._ensure_logged_in()
        response = self._request_once("GET", path, allow_redirects=False)
        if response.status_code == 401:
            self._ensure_logged_in(force=True)
            response = self._request_once("GET", path, allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            # Blobs usually redirect to signed storage URLs; fetch those without the
            # TronClass session headers so the session ID is not sent to another host.
            location = urljoin(self.config.base_url + "/", response.headers.get("Location", ""))
            response = requests.get(
                location,
                timeout=self.config.request_timeout,
                verify=self.config.verify_tls,
            )
        if not response.ok:
            return {
                "ok": False,
                "status": response.status_code,
                "text": response.text[:1000],
            }
        content = response.content
        if len(content) > _MAX_DOWNLOAD_BYTES:
            raise TronClassError(
                f"File is {len(content)} bytes; the download limit is {_MAX_DOWNLOAD_BYTES} bytes."
            )
        return {
            "ok": True,
            "name": _filename_from_disposition(response.headers.get("Content-Disposition", "")),
            "content_type": response.headers.get("Content-Type", "application/octet-stream"),
            "content": content,
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        form_body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        retry_on_auth: bool = True,
    ) -> dict[str, Any]:
        if not path.startswith("/"):
            raise TronClassError("API path must start with '/'.")
        if not path.startswith("/api/") and path != "/api/cas-login":
            raise TronClassError("For safety, raw requests are limited to /api/* paths.")

        self._ensure_logged_in()
        response = self._request_once(
            method,
            path,
            params=params,
            json_body=json_body,
            form_body=form_body,
            headers=headers,
        )
        if response.status_code == 401 and retry_on_auth:
            logger.info("Session expired; refreshing TronClass login")
            self._ensure_logged_in(force=True)
            response = self._request_once(
                method,
                path,
                params=params,
                json_body=json_body,
                form_body=form_body,
                headers=headers,
            )
        return self._normalize_response(response)

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        form_body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        allow_redirects: bool = True,
    ) -> requests.Response:
        merged_headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "capacitor://localhost",
            "User-Agent": self.config.api_user_agent,
            "Accept-Language": "zh-Hant",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self._session_id:
            merged_headers["x-session-id"] = self._session_id
        if headers:
            merged_headers.update(headers)

        response = self.session.request(
            method.upper(),
            urljoin(self.config.base_url + "/", path.lstrip("/")),
            params=params,
            json=json_body,
            data=form_body,
            headers=merged_headers,
            timeout=self.config.request_timeout,
            verify=self.config.verify_tls,
            allow_redirects=allow_redirects,
        )
        rotated = response.headers.get("x-session-id") or response.headers.get("X-SESSION-ID")
        if rotated:
            self._session_id = rotated
        return response

    def _ensure_logged_in(self, force: bool = False) -> None:
        with self._lock:
            if self._session_id and not force:
                return
            self._login_locked()

    def _login_locked(self) -> None:
        self.config.validate_credentials()
        base = self.config.base_url
        login_headers = {
            "Accept": "*/*",
            "User-Agent": self.config.login_user_agent,
            "Accept-Language": "zh-Hant-TW;q=1, en-TW;q=0.9, zh-Hans-TW;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        tgt_response = self.session.post(
            f"{base}/cas/v1/tickets",
            headers=login_headers,
            data={"username": self.config.username, "password": self.config.password},
            allow_redirects=False,
            timeout=self.config.request_timeout,
            verify=self.config.verify_tls,
        )
        if tgt_response.status_code != 201:
            raise TronClassAuthError(
                f"Failed to obtain TGT: HTTP {tgt_response.status_code} {tgt_response.text[:200]}"
            )

        location = tgt_response.headers.get("Location") or tgt_response.headers.get("location")
        if not location:
            raise TronClassAuthError("CAS login succeeded but no TGT location was returned.")
        tgt_url = location.replace("http://", "https://", 1)

        st_response = self.session.post(
            tgt_url,
            headers=login_headers,
            data={"service": f"{base}/api/cas-login"},
            timeout=self.config.request_timeout,
            verify=self.config.verify_tls,
        )
        if st_response.status_code != 200:
            raise TronClassAuthError(
                f"Failed to obtain service ticket: HTTP {st_response.status_code} {st_response.text[:200]}"
            )
        service_ticket = st_response.text.strip()
        if not service_ticket.startswith("ST-"):
            raise TronClassAuthError("CAS returned an unexpected service ticket payload.")

        session_response = self.session.get(
            f"{base}/api/cas-login",
            params={"ticket": service_ticket},
            headers={
                "Origin": "capacitor://localhost",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": self.config.api_user_agent,
                "Accept-Language": "zh-TW,zh-Hant;q=0.9",
            },
            timeout=self.config.request_timeout,
            verify=self.config.verify_tls,
        )
        if session_response.status_code != 200:
            raise TronClassAuthError(
                f"Failed to exchange service ticket for app session: HTTP {session_response.status_code} {session_response.text[:200]}"
            )

        self._session_id = (
            session_response.headers.get("X-SESSION-ID")
            or session_response.headers.get("x-session-id")
        )
        if not self._session_id:
            raise TronClassAuthError("Login succeeded but no X-SESSION-ID was returned.")

        try:
            payload = session_response.json()
        except ValueError as exc:
            raise TronClassAuthError("Login succeeded but session payload was not JSON.") from exc
        self._user_id = payload.get("user_id")

    @staticmethod
    def _normalize_response(response: requests.Response) -> dict[str, Any]:
        content_type = response.headers.get("Content-Type", "")
        result: dict[str, Any] = {
            "status": response.status_code,
            "ok": response.ok,
            "content_type": content_type,
            "headers": {
                key: value
                for key, value in response.headers.items()
                if key.lower() in _SAFE_HEADER_KEYS
            },
        }
        if "application/json" in content_type:
            try:
                result["data"] = response.json()
            except ValueError:
                result["text"] = response.text
        else:
            result["text"] = response.text
        return result


def _flatten_catalog() -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for group, items in TRONCLASS_API_GROUPS.items():
        for item in items:
            flattened.append(
                {
                    "group": group,
                    "url": item.get("url"),
                    "methods": sorted(item.get("methods") or []),
                }
            )
    return flattened


def _catalog_search(
    *,
    search: Optional[str] = None,
    group: Optional[str] = None,
    method: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    items = _flatten_catalog()
    if group:
        items = [item for item in items if item["group"].lower() == group.lower()]
    if method:
        needle = method.upper()
        items = [item for item in items if needle in item["methods"]]
    if search:
        needle = search.lower()
        items = [
            item
            for item in items
            if needle in item["group"].lower() or needle in (item["url"] or "").lower()
        ]
    items.sort(key=lambda item: (item["group"], item["url"] or ""))
    return {
        "count": len(items[:limit]),
        "total_matches": len(items),
        "api_count": TRONCLASS_API_COUNT,
        "method_count": TRONCLASS_METHOD_COUNT,
        "items": items[:limit],
    }


def _catalog_group_summary() -> list[dict[str, Any]]:
    summary = []
    for group, items in TRONCLASS_API_GROUPS.items():
        methods = sorted({method for item in items for method in (item.get("methods") or [])})
        summary.append(
            {
                "group": group,
                "endpoint_count": len(items),
                "methods": methods,
                "sample_urls": [item.get("url") for item in items[:3]],
            }
        )
    summary.sort(key=lambda item: item["group"])
    return summary


def _compact_result(result: dict[str, Any], collection_key: Optional[str] = None) -> dict[str, Any]:
    compact = {
        "status": result.get("status"),
        "ok": result.get("ok"),
        "collection_key": collection_key,
    }
    data = result.get("data")
    if not isinstance(data, dict):
        if collection_key:
            compact["count"] = 0
        compact["result"] = result
        return compact

    if collection_key and isinstance(data.get(collection_key), list):
        compact["count"] = len(data[collection_key])
        compact["items"] = data[collection_key]
    elif collection_key and collection_key in data:
        compact["item"] = data[collection_key]
    else:
        for key, value in data.items():
            if isinstance(value, list):
                compact["collection_key"] = key
                compact["count"] = len(value)
                compact["items"] = value
                break
            if isinstance(value, dict):
                compact["collection_key"] = key
                compact["item"] = value
                break
        if "count" not in compact and "item" not in compact:
            compact["data"] = data
    return compact


def _filename_from_disposition(disposition: str) -> Optional[str]:
    match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", disposition, re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip().strip('"'))
    match = re.search(r'filename="?([^";]+)"?', disposition, re.IGNORECASE)
    return unquote(match.group(1)) if match else None


def _collect_uploads(data: Any, found: Optional[dict[Any, dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Walk a TronClass JSON payload and return every attached upload, de-duplicated."""
    if found is None:
        found = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("uploads", "attachments") and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and ("id" in item or "reference_id" in item):
                        found.setdefault(
                            (item.get("id"), item.get("reference_id")),
                            {
                                "upload_id": item.get("id"),
                                "reference_id": item.get("reference_id"),
                                "name": item.get("name"),
                                "size": item.get("size"),
                                "type": item.get("type"),
                                "activity_id": data.get("id") if "title" in data else None,
                                "activity_title": data.get("title"),
                            },
                        )
            else:
                _collect_uploads(value, found)
    elif isinstance(data, list):
        for item in data:
            _collect_uploads(item, found)
    return list(found.values())


def _xml_text(xml: bytes, paragraph_tag: str) -> str:
    """Pull visible text from an Office Open XML part, one line per paragraph."""
    text = re.sub(rf"</{paragraph_tag}>", "\n", xml.decode("utf-8", "replace"))
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _extract_text(name: str, content_type: str, content: bytes) -> Optional[str]:
    """Best-effort text extraction for common course material formats."""
    suffix = Path(name).suffix.lower()
    if suffix in _TEXT_EXTENSIONS or content_type.startswith("text/"):
        return content.decode("utf-8", "replace")
    if suffix == ".pdf" or content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages = [f"--- page {index} ---\n{page.extract_text() or ''}" for index, page in enumerate(reader.pages, 1)]
        return "\n\n".join(pages)
    if suffix in (".docx", ".pptx", ".xlsx"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if suffix == ".docx":
                return _xml_text(archive.read("word/document.xml"), "w:p")
            if suffix == ".pptx":
                slides = sorted(
                    (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                    key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()),
                )
                return "\n\n".join(
                    f"--- slide {index} ---\n{_xml_text(archive.read(slide), 'a:p')}"
                    for index, slide in enumerate(slides, 1)
                )
            if "xl/sharedStrings.xml" in names:
                return _xml_text(archive.read("xl/sharedStrings.xml"), "si")
    return None


def _json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def _item_path(base_path: str, item_id: int | str) -> str:
    return f"{base_path.rstrip('/')}/{item_id}"


def _tool_call(
    client: TronClassClient,
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    body: Optional[dict[str, Any]] = None,
    compact_key: Optional[str] = None,
) -> str:
    result = client.request(method, path, params=params, json_body=body)
    if compact_key is None:
        return _json(result)
    return _json(_compact_result(result, compact_key))


def create_mcp_server(client: Optional[TronClassClient] = None, **settings: Any) -> "FastMCP":
    if not _MCP_SERVER_AVAILABLE:
        raise ImportError(
            "MCP server requires the 'mcp' package. Install with: pip install -e ."
        )

    mcp = FastMCP(
        "tronclass",
        instructions=(
            "Authenticated TronClass MCP server for FJU. "
            "Use endpoint_catalog and endpoint_groups to explore discovered API families. "
            "Use raw_api for arbitrary /api calls. "
            "High-level tools cover todos, courses, activities, homework, exams, questionnaires, submissions, notes, grades, bulletins, resources, entries, and calendar workflows."
        ),
        **settings,
    )
    tron = client or TronClassClient()

    @mcp.tool()
    def server_info() -> str:
        """Return server metadata and configuration status."""
        config = tron.config
        return _json(
            {
                "server": "tronclass",
                "base_url": config.base_url,
                "credentials_configured": bool(config.username and config.password),
                "verify_tls": config.verify_tls,
                "api_count": TRONCLASS_API_COUNT,
                "method_count": TRONCLASS_METHOD_COUNT,
                "endpoint_groups": sorted(TRONCLASS_API_GROUPS.keys()),
            }
        )

    @mcp.tool()
    def auth_status() -> str:
        """Log in if needed and return the current authenticated session summary."""
        return _json(tron.auth_status())

    @mcp.tool()
    def endpoint_catalog(
        search: Optional[str] = None,
        group: Optional[str] = None,
        method: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """Browse the frontend-discovered TronClass API endpoint catalog."""
        return _json(_catalog_search(search=search, group=group, method=method, limit=limit))

    @mcp.tool()
    def endpoint_groups(limit: int = _DEFAULT_GROUP_LIMIT) -> str:
        """Summarize discovered endpoint groups with counts and supported methods."""
        groups = _catalog_group_summary()[:limit]
        return _json({"group_count": len(groups), "groups": groups})

    @mcp.tool()
    def raw_api(
        path: str,
        method: str = "GET",
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        form_body: Optional[dict[str, Any]] = None,
    ) -> str:
        """Call an arbitrary authenticated TronClass /api endpoint."""
        return _json(
            tron.request(method, path, params=params, json_body=json_body, form_body=form_body)
        )

    @mcp.tool()
    def list_todos() -> str:
        """Return the authenticated user's todo list."""
        return _tool_call(tron, "GET", "/api/todos", compact_key="todo_list")

    @mcp.tool()
    def list_my_courses() -> str:
        """Return the authenticated user's course list."""
        return _tool_call(tron, "GET", "/api/my-courses", compact_key="courses")

    @mcp.tool()
    def list_courses_page(page: int = 1, body: Optional[dict[str, Any]] = None) -> str:
        """Query the paginated /api/courses endpoint with an optional body payload."""
        payload = dict(body or {})
        payload.setdefault("page", page)
        return _tool_call(tron, "POST", "/api/courses", body=payload)

    @mcp.tool()
    def get_course(course_id: int) -> str:
        """Fetch a course by ID from /api/course/{id}."""
        return _tool_call(tron, "GET", _item_path("/api/course", course_id))

    @mcp.tool()
    def list_recently_visited_courses() -> str:
        """Return recently visited courses for the authenticated user."""
        return _tool_call(tron, "GET", "/api/user/recently-visited-courses", compact_key="visited_courses")

    @mcp.tool()
    def list_semesters() -> str:
        """Return semester metadata visible to the authenticated user."""
        return _tool_call(tron, "GET", "/api/my-semesters", compact_key="semesters")

    @mcp.tool()
    def list_calendar_events(params: Optional[dict[str, Any]] = None) -> str:
        """Return calendar events for the authenticated user."""
        return _tool_call(tron, "GET", "/api/calendar-events", params=params, compact_key="events")

    @mcp.tool()
    def create_calendar_event(body: dict[str, Any]) -> str:
        """Create a calendar event via /api/calendar-events."""
        return _tool_call(tron, "POST", "/api/calendar-events", body=body)

    @mcp.tool()
    def update_calendar_event(event_id: int, body: dict[str, Any]) -> str:
        """Update a calendar event by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/calendar-events", event_id), body=body)

    @mcp.tool()
    def delete_calendar_event(event_id: int) -> str:
        """Delete a calendar event by ID."""
        return _tool_call(tron, "DELETE", _item_path("/api/calendar-events", event_id))

    @mcp.tool()
    def list_calendar_timetables(params: Optional[dict[str, Any]] = None) -> str:
        """List calendar timetables."""
        return _tool_call(tron, "GET", "/api/calendar-timetables", params=params)

    @mcp.tool()
    def create_calendar_timetable(body: dict[str, Any]) -> str:
        """Create a calendar timetable."""
        return _tool_call(tron, "POST", "/api/calendar-timetables", body=body)

    @mcp.tool()
    def update_calendar_timetable(timetable_id: int, body: dict[str, Any]) -> str:
        """Update a calendar timetable by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/calendar-timetables", timetable_id), body=body)

    @mcp.tool()
    def list_course_activities(course_id: int, extra_params: Optional[dict[str, Any]] = None) -> str:
        """List activities for a course."""
        params = {"course_id": course_id, **(extra_params or {})}
        return _tool_call(tron, "GET", "/api/course/activities/", params=params)

    @mcp.tool()
    def get_activity(activity_id: int) -> str:
        """Fetch an activity by ID."""
        return _tool_call(tron, "GET", _item_path("/api/activities", activity_id))

    @mcp.tool()
    def create_activity(body: dict[str, Any]) -> str:
        """Create an activity."""
        return _tool_call(tron, "POST", "/api/activities/", body=body)

    @mcp.tool()
    def update_activity(activity_id: int, body: dict[str, Any]) -> str:
        """Update an activity by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/activities", activity_id), body=body)

    @mcp.tool()
    def delete_activity(activity_id: int) -> str:
        """Delete an activity by ID."""
        return _tool_call(tron, "DELETE", _item_path("/api/activities", activity_id))

    @mcp.tool()
    def check_activity_delete(activity_id: int) -> str:
        """Check whether an activity can be deleted."""
        return _tool_call(
            tron,
            "GET",
            "/api/activities/delete-check",
            params={"activity_id": activity_id},
        )

    @mcp.tool()
    def get_activity_dependencies(activity_id: int) -> str:
        """Inspect whether an activity has dependent records."""
        return _tool_call(
            tron,
            "GET",
            "/api/activities/have-dependents",
            params={"activity_id": activity_id},
        )

    @mcp.tool()
    def mark_activity_read(course_id: int, activity_ids: list[int], body: Optional[dict[str, Any]] = None) -> str:
        """Mark one or more course activities as read."""
        payload = {"course_id": course_id, "activity_ids": activity_ids}
        if body:
            payload.update(body)
        return _tool_call(tron, "POST", "/api/course/activities-read/", body=payload)

    @mcp.tool()
    def get_homework(homework_id: int) -> str:
        """Fetch homework details by ID."""
        return _tool_call(tron, "GET", _item_path("/api/homework", homework_id))

    @mcp.tool()
    def update_homework(homework_id: int, body: dict[str, Any]) -> str:
        """Update homework by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/homework", homework_id), body=body)

    @mcp.tool()
    def list_exams(params: Optional[dict[str, Any]] = None) -> str:
        """List exams."""
        return _tool_call(tron, "GET", "/api/exams/", params=params)

    @mcp.tool()
    def create_exam(body: dict[str, Any]) -> str:
        """Create an exam."""
        return _tool_call(tron, "POST", "/api/exams/", body=body)

    @mcp.tool()
    def delete_exam(exam_id: int) -> str:
        """Delete an exam by ID."""
        return _tool_call(tron, "DELETE", _item_path("/api/exams", exam_id))

    @mcp.tool()
    def batch_delete_exams(exam_ids: list[int]) -> str:
        """Delete multiple exams in one request."""
        return _tool_call(tron, "DELETE", "/api/exams/batch_delete", body={"exam_ids": exam_ids})

    @mcp.tool()
    def list_questionnaires(params: Optional[dict[str, Any]] = None) -> str:
        """List questionnaires."""
        return _tool_call(tron, "GET", "/api/questionnaires/", params=params)

    @mcp.tool()
    def list_submissions(params: Optional[dict[str, Any]] = None) -> str:
        """List submissions."""
        return _tool_call(tron, "GET", "/api/submissions/", params=params)

    @mcp.tool()
    def create_submission(body: dict[str, Any]) -> str:
        """Create a submission."""
        return _tool_call(tron, "POST", "/api/submissions/", body=body)

    @mcp.tool()
    def list_peer_review_todos() -> str:
        """List pending TronClass peer-review / mutual-evaluation todos for the authenticated student."""
        return _json(tron.list_peer_review_todos())

    @mcp.tool()
    def get_peer_submission(activity_id: int, submitter_id: int) -> str:
        """Fetch a peer submitter's homework submission, including upload/document metadata when visible."""
        return _json(tron.get_peer_submission(activity_id, submitter_id))

    @mcp.tool()
    def submit_peer_review_score(
        activity_id: int,
        submitter_id: int,
        score: float,
        comment: str,
        inter_score_id: Optional[int] = None,
        upload_ids: Optional[list[int]] = None,
        rubric_score: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Submit/update a plain-text student peer-review score and comment for a target submission."""
        return _json(
            tron.submit_peer_review_score(
                activity_id,
                submitter_id,
                score,
                comment,
                inter_score_id=inter_score_id,
                upload_ids=upload_ids,
                rubric_score=rubric_score,
            )
        )

    @mcp.tool()
    def upload_file(
        file_path: str,
        name: Optional[str] = None,
        parent_type: Optional[str] = None,
        parent_id: int = 0,
        source: str = "",
    ) -> str:
        """Upload a local file into TronClass storage. Returns the upload ID for later submission."""
        return _json(
            tron.upload_file(
                file_path,
                name=name,
                parent_type=parent_type,
                parent_id=parent_id,
                source=source,
            )
        )

    @mcp.tool()
    def upload_file_content(
        name: str,
        content_base64: str,
        parent_type: Optional[str] = None,
        parent_id: int = 0,
        source: str = "",
    ) -> str:
        """Upload base64-encoded file content into TronClass storage. Use this instead of upload_file when the server runs remotely. Returns the upload ID for later submission."""
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise TronClassError(f"content_base64 is not valid base64: {exc}") from exc
        return _json(
            tron.upload_bytes(
                content,
                name,
                parent_type=parent_type,
                parent_id=parent_id,
                source=source,
            )
        )

    @mcp.tool()
    def list_activity_files(activity_id: int) -> str:
        """List files attached to an activity (materials, homework instructions). Use download_file to fetch one."""
        result = tron.request("GET", _item_path("/api/activities", activity_id))
        if not result.get("ok"):
            return _json(result)
        files = _collect_uploads(result.get("data"))
        return _json({"ok": True, "activity_id": activity_id, "count": len(files), "files": files})

    @mcp.tool()
    def list_course_files(course_id: int) -> str:
        """List files attached to every activity in a course. Use download_file to fetch one."""
        attempts = [
            (f"/api/courses/{course_id}/activities", None),
            ("/api/course/activities/", {"course_id": course_id}),
        ]
        result: dict[str, Any] = {}
        for path, params in attempts:
            result = tron.request("GET", path, params=params)
            if result.get("ok"):
                files = _collect_uploads(result.get("data"))
                return _json(
                    {"ok": True, "course_id": course_id, "source": path, "count": len(files), "files": files}
                )
        return _json(result)

    @mcp.tool()
    def download_file(
        upload_id: Optional[int] = None,
        reference_id: Optional[int] = None,
        max_chars: int = 100_000,
        include_base64: bool = False,
        save_to_download_dir: bool = False,
    ):
        """Fetch a TronClass file by upload_id or reference_id (from list_activity_files / list_course_files).

        Text, PDF, DOCX, PPTX and XLSX files come back as extracted text (truncated to max_chars),
        images come back as images. Other formats return metadata only unless include_base64 is set.
        save_to_download_dir also writes the file into TRONCLASS_DOWNLOAD_DIR on the server machine.
        """
        downloaded = tron.download_upload(upload_id=upload_id, reference_id=reference_id)
        if not downloaded.get("ok"):
            return _json(downloaded)
        content: bytes = downloaded["content"]
        name = downloaded.get("name") or f"upload-{upload_id or reference_id}"
        content_type = downloaded["content_type"].split(";")[0].strip()
        info: dict[str, Any] = {
            "ok": True,
            "name": name,
            "content_type": content_type,
            "size": len(content),
        }

        if save_to_download_dir:
            download_dir = os.getenv("TRONCLASS_DOWNLOAD_DIR")
            if not download_dir:
                raise TronClassError("Set TRONCLASS_DOWNLOAD_DIR to enable saving downloads.")
            target_dir = Path(download_dir).expanduser().resolve()
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(name).name) or "download"
            target = target_dir / safe_name
            target.write_bytes(content)
            info["saved_to"] = str(target)

        suffix = Path(name).suffix.lower()
        image_type = _IMAGE_TYPES.get(suffix) or (content_type if content_type.startswith("image/") else None)
        if image_type:
            return [
                TextContent(type="text", text=_json(info)),
                ImageContent(type="image", data=base64.b64encode(content).decode(), mimeType=image_type),
            ]

        try:
            text = _extract_text(name, content_type, content)
        except Exception as exc:  # corrupt or unusual files should still return metadata
            info["extract_error"] = f"{type(exc).__name__}: {exc}"
            text = None
        if text is not None:
            info["chars"] = len(text)
            info["truncated"] = len(text) > max_chars
            info["text"] = text[:max_chars]
        else:
            info["note"] = "No text extraction for this format."
            if include_base64:
                info["content_base64"] = base64.b64encode(content).decode()
        return _json(info)

    @mcp.tool()
    def submit_homework_uploads(
        activity_id: int,
        upload_ids: list[int],
        comment: str = "",
        draft: bool = False,
        user_id: Optional[int] = None,
    ) -> str:
        """Submit uploaded file IDs to a homework activity for the authenticated student."""
        return _json(
            tron.submit_homework_uploads(
                activity_id,
                upload_ids,
                comment=comment,
                draft=draft,
                user_id=user_id,
            )
        )

    @mcp.tool()
    def list_notes(course_id: Optional[int] = None) -> str:
        """Return notes, optionally filtered by course ID."""
        params = {"course_id": course_id} if course_id is not None else None
        return _tool_call(tron, "GET", "/api/notes", params=params, compact_key="notes")

    @mcp.tool()
    def create_note(body: dict[str, Any]) -> str:
        """Create a note."""
        return _tool_call(tron, "POST", "/api/notes", body=body)

    @mcp.tool()
    def update_note(note_id: int, body: dict[str, Any]) -> str:
        """Update a note by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/notes", note_id), body=body)

    @mcp.tool()
    def delete_note(note_id: int) -> str:
        """Delete a note by ID."""
        return _tool_call(tron, "DELETE", _item_path("/api/notes", note_id))

    @mcp.tool()
    def list_grades(course_id: Optional[int] = None, org_id: Optional[int] = None) -> str:
        """Return grades, optionally filtered by course_id or org_id."""
        params: dict[str, Any] = {}
        if course_id is not None:
            params["course_id"] = course_id
        if org_id is not None:
            params["org_id"] = org_id
        return _tool_call(tron, "GET", "/api/grades", params=params or None)

    @mcp.tool()
    def list_org_bulletins(params: Optional[dict[str, Any]] = None) -> str:
        """List organization bulletins."""
        return _tool_call(tron, "GET", "/api/org-bulletin/bulletins", params=params)

    @mcp.tool()
    def create_org_bulletin(body: dict[str, Any]) -> str:
        """Create an organization bulletin."""
        return _tool_call(tron, "POST", "/api/org-bulletin/bulletins", body=body)

    @mcp.tool()
    def update_org_bulletin(bulletin_id: int, body: dict[str, Any]) -> str:
        """Update an organization bulletin by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/org-bulletin/bulletins", bulletin_id), body=body)

    @mcp.tool()
    def delete_org_bulletin(bulletin_id: int) -> str:
        """Delete an organization bulletin by ID."""
        return _tool_call(tron, "DELETE", _item_path("/api/org-bulletin/bulletins", bulletin_id))

    @mcp.tool()
    def list_org_bulletin_classifications() -> str:
        """List organization bulletin classifications."""
        return _tool_call(tron, "GET", "/api/org-bulletin/classifications")

    @mcp.tool()
    def list_resource_groups(course_id: Optional[int] = None, params: Optional[dict[str, Any]] = None) -> str:
        """List resource groups, optionally filtered by course ID."""
        merged = dict(params or {})
        if course_id is not None:
            merged["course_id"] = course_id
        return _tool_call(tron, "GET", "/api/resource-groups", params=merged or None)

    @mcp.tool()
    def get_resource_group(group_id: int) -> str:
        """Fetch a resource group by ID."""
        return _tool_call(tron, "GET", _item_path("/api/resource-groups", group_id))

    @mcp.tool()
    def create_resource_group(body: dict[str, Any]) -> str:
        """Create a resource group."""
        return _tool_call(tron, "POST", "/api/resource-groups/", body=body)

    @mcp.tool()
    def update_resource_group(group_id: int, body: dict[str, Any]) -> str:
        """Update a resource group by ID."""
        return _tool_call(tron, "PUT", _item_path("/api/resource-groups", group_id), body=body)

    @mcp.tool()
    def delete_resource_group(group_id: int) -> str:
        """Delete a resource group by ID."""
        return _tool_call(tron, "DELETE", _item_path("/api/resource-groups", group_id))

    @mcp.tool()
    def list_resource_group_folders(group_id: Optional[int] = None, params: Optional[dict[str, Any]] = None) -> str:
        """List resource group folders, optionally scoped by group ID."""
        merged = dict(params or {})
        if group_id is not None:
            merged["group_id"] = group_id
        return _tool_call(tron, "GET", "/api/resource-groups/folders", params=merged or None)

    @mcp.tool()
    def list_resource_group_resources(group_id: Optional[int] = None, params: Optional[dict[str, Any]] = None) -> str:
        """List resources inside resource groups, optionally scoped by group ID."""
        merged = dict(params or {})
        if group_id is not None:
            merged["group_id"] = group_id
        return _tool_call(tron, "GET", "/api/resource-groups/resources", params=merged or None)

    @mcp.tool()
    def list_entries(params: Optional[dict[str, Any]] = None) -> str:
        """List entry records."""
        return _tool_call(tron, "GET", "/api/entries", params=params)

    return mcp


def run_mcp_server(
    verbose: bool = False,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    token: Optional[str] = None,
) -> None:
    if not _MCP_SERVER_AVAILABLE:
        print(
            "Error: MCP server requires the 'mcp' package.\n"
            "Install with: pip install -e .",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        stream=sys.stderr,
    )
    if transport == "stdio":
        server = create_mcp_server()
        asyncio.run(server.run_stdio_async())
        return

    # Remote clients such as claude.ai reach the server through a public URL, and every tool
    # acts with the configured TronClass account, so the endpoint path carries a secret token.
    if not token:
        print(
            "Error: HTTP transport requires a secret token. Set TRONCLASS_MCP_TOKEN or pass --token.\n"
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
            file=sys.stderr,
        )
        sys.exit(1)
    from mcp.server.transport_security import TransportSecuritySettings

    server = create_mcp_server(
        host=host,
        port=port,
        streamable_http_path=f"/{token}/mcp",
        stateless_http=True,
        # The public hostname of a tunnel or reverse proxy is not known ahead of time;
        # the secret path is what guards the endpoint.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    print(f"TronClass MCP listening on http://{host}:{port}/<token>/mcp", file=sys.stderr)
    server.run(transport="streamable-http")


def main() -> None:
    load_dotenv(Path.cwd() / ".env", Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(description="Run the TronClass MCP server.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging to stderr.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.getenv("TRONCLASS_MCP_TRANSPORT", "stdio"),
        help="stdio for local clients, http (Streamable HTTP) for remote clients such as claude.ai.",
    )
    parser.add_argument("--host", default=os.getenv("TRONCLASS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("TRONCLASS_MCP_PORT", "8000")))
    parser.add_argument(
        "--token",
        default=os.getenv("TRONCLASS_MCP_TOKEN"),
        help="Secret path segment for the HTTP endpoint (prefer the TRONCLASS_MCP_TOKEN env var).",
    )
    args = parser.parse_args()
    run_mcp_server(
        verbose=args.verbose,
        transport=args.transport,
        host=args.host,
        port=args.port,
        token=args.token,
    )


if __name__ == "__main__":
    main()
