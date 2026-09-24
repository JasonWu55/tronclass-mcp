from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from tronclass_api_catalog import TRONCLASS_API_COUNT, TRONCLASS_API_GROUPS, TRONCLASS_METHOD_COUNT

logger = logging.getLogger("tronclass.mcp")

_MCP_SERVER_AVAILABLE = False
try:
    from mcp.server.fastmcp import FastMCP

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
        upload_name = name or path.name
        create_body = {
            "name": upload_name,
            "size": path.stat().st_size,
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
        with path.open("rb") as handle:
            response = requests.put(
                upload_url,
                files={"file": (upload_name, handle, "application/octet-stream")},
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


def create_mcp_server(client: Optional[TronClassClient] = None) -> "FastMCP":
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


def run_mcp_server(verbose: bool = False) -> None:
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
    server = create_mcp_server()
    asyncio.run(server.run_stdio_async())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TronClass MCP server over stdio.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging to stderr.")
    args = parser.parse_args()
    run_mcp_server(verbose=args.verbose)


if __name__ == "__main__":
    main()
