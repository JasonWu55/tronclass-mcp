import os
import asyncio
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import tronclass_mcp


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None, ok=None, content_type="application/json"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}
        if content_type and "Content-Type" not in self.headers:
            self.headers["Content-Type"] = content_type
        self.ok = status_code < 400 if ok is None else ok

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


class FakeSession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []
        self.cookies = {"session": "cookie-value"}

    def _next(self):
        if not self.responses:
            raise AssertionError("No more fake responses queued")
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._next()

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._next()

    def request(self, method, url, **kwargs):
        self.calls.append((method.upper(), url, kwargs))
        return self._next()


class StubClient:
    def __init__(self):
        self.config = tronclass_mcp.TronClassConfig(
            base_url="https://elearn2.fju.edu.tw",
            username="demo",
            password="demo",
            verify_tls=True,
        )
        self.calls = []

    def auth_status(self):
        return {"user_id": 512982, "has_session_id": True}

    def request(self, method, path, params=None, json_body=None, form_body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json_body": json_body,
                "form_body": form_body,
            }
        )
        return {
            "method": method,
            "path": path,
            "params": params,
            "json_body": json_body,
            "form_body": form_body,
            "ok": True,
        }

    def upload_file(self, file_path, *, name=None, parent_type=None, parent_id=0, source=""):
        self.calls.append(
            {
                "method": "UPLOAD_FILE",
                "file_path": file_path,
                "name": name,
                "parent_type": parent_type,
                "parent_id": parent_id,
                "source": source,
            }
        )
        return {"ok": True, "upload": {"id": 123, "name": name or Path(file_path).name}}

    def upload_bytes(self, content, name, *, parent_type=None, parent_id=0, source=""):
        self.calls.append(
            {
                "method": "UPLOAD_BYTES",
                "content": content,
                "name": name,
                "parent_type": parent_type,
                "parent_id": parent_id,
                "source": source,
            }
        )
        return {"ok": True, "upload": {"id": 124, "name": name}}

    def submit_homework_uploads(self, activity_id, upload_ids, *, comment="", draft=False, user_id=None):
        self.calls.append(
            {
                "method": "SUBMIT_HOMEWORK_UPLOADS",
                "activity_id": activity_id,
                "upload_ids": upload_ids,
                "comment": comment,
                "draft": draft,
                "user_id": user_id,
            }
        )
        return {"ok": True, "submission": {"id": 456, "activity_id": activity_id, "uploads": upload_ids}}

    def list_peer_review_todos(self):
        self.calls.append({"method": "LIST_PEER_REVIEW_TODOS"})
        return {"ok": True, "count": 1, "items": [{"id": 2862999, "not_scored_num": 15}]}

    def get_peer_submission(self, activity_id, submitter_id):
        self.calls.append({"method": "GET_PEER_SUBMISSION", "activity_id": activity_id, "submitter_id": submitter_id})
        return {"ok": True, "data": {"id": 21586320, "activity_id": activity_id, "submitter_id": submitter_id}}

    def submit_peer_review_score(
        self,
        activity_id,
        submitter_id,
        score,
        comment,
        *,
        inter_score_id=None,
        upload_ids=None,
        rubric_score=None,
    ):
        self.calls.append(
            {
                "method": "SUBMIT_PEER_REVIEW_SCORE",
                "activity_id": activity_id,
                "submitter_id": submitter_id,
                "score": score,
                "comment": comment,
                "inter_score_id": inter_score_id,
                "upload_ids": upload_ids,
                "rubric_score": rubric_score,
            }
        )
        return {"ok": True, "submission": {"id": 21586320, "activity_id": activity_id}, "result": {"path": f"/api/inter-scores/{inter_score_id}"}}


def _office_zip(parts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, xml in parts.items():
            archive.writestr(name, xml)
    return buffer.getvalue()


class FileStubClient(StubClient):
    def __init__(self, activity=None, download=None):
        super().__init__()
        self.activity = activity
        self.download = download

    def request(self, method, path, params=None, json_body=None, form_body=None):
        self.calls.append({"method": method, "path": path, "params": params})
        return {"ok": True, "status": 200, "data": self.activity}

    def download_upload(self, *, upload_id=None, reference_id=None):
        self.calls.append({"method": "DOWNLOAD", "upload_id": upload_id, "reference_id": reference_id})
        return self.download


def _run_tool(server, name, args=None):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(server._tool_manager.call_tool(name, args or {}))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
    return json.loads(result) if isinstance(result, str) else result


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TRONCLASS_USERNAME", raising=False)
    monkeypatch.delenv("TRONCLASS_PASSWORD", raising=False)
    monkeypatch.delenv("TRONCLASS_BASE_URL", raising=False)
    monkeypatch.delenv("TRONCLASS_VERIFY_TLS", raising=False)


class TestCatalogHelpers:
    def test_catalog_search_filters(self):
        result = tronclass_mcp._catalog_search(group="notes", method="GET", limit=20)
        assert result["total_matches"] >= 1
        assert all(item["group"] == "notes" for item in result["items"])
        assert all("GET" in item["methods"] for item in result["items"])

    def test_catalog_search_by_text(self):
        result = tronclass_mcp._catalog_search(search="my-courses", limit=5)
        assert result["total_matches"] >= 1
        assert any("my-courses" in item["url"] for item in result["items"])

    def test_catalog_group_summary_contains_major_families(self):
        summary = tronclass_mcp._catalog_group_summary()
        groups = {item["group"] for item in summary}
        assert {"activities", "course", "calendar-events", "resource-groups", "submissions"}.issubset(groups)

    def test_compact_result_extracts_primary_payload(self):
        payload = {"status": 200, "ok": True, "data": {"notes": [{"id": 1}], "other": []}}
        compact = tronclass_mcp._compact_result(payload, "notes")
        assert compact["count"] == 1
        assert compact["items"] == [{"id": 1}]
        assert compact["collection_key"] == "notes"


class TestClientLogin:
    def test_login_flow_uses_cas_api(self):
        session = FakeSession(
            responses=[
                FakeResponse(status_code=201, headers={"Location": "http://elearn2.fju.edu.tw/cas/v1/tickets/TGT-demo", "Content-Type": "text/html"}),
                FakeResponse(status_code=200, text="ST-demo", content_type="text/plain"),
                FakeResponse(status_code=200, json_data={"user_id": 512982}, headers={"X-SESSION-ID": "V2-1-demo"}),
            ]
        )
        client = tronclass_mcp.TronClassClient(
            tronclass_mcp.TronClassConfig(username="user", password="pass"),
            session=session,
        )

        status = client.auth_status()

        assert status["user_id"] == 512982
        assert client.session_id == "V2-1-demo"
        assert session.calls[0][1].endswith("/cas/v1/tickets")
        assert session.calls[1][1] == "https://elearn2.fju.edu.tw/cas/v1/tickets/TGT-demo"
        assert session.calls[2][1].endswith("/api/cas-login")

    def test_request_retries_once_after_401(self):
        session = FakeSession(
            responses=[
                FakeResponse(status_code=201, headers={"Location": "http://elearn2.fju.edu.tw/cas/v1/tickets/TGT-one", "Content-Type": "text/html"}),
                FakeResponse(status_code=200, text="ST-one", content_type="text/plain"),
                FakeResponse(status_code=200, json_data={"user_id": 1}, headers={"X-SESSION-ID": "SID-one"}),
                FakeResponse(status_code=401, json_data={"message": "expired"}),
                FakeResponse(status_code=201, headers={"Location": "http://elearn2.fju.edu.tw/cas/v1/tickets/TGT-two", "Content-Type": "text/html"}),
                FakeResponse(status_code=200, text="ST-two", content_type="text/plain"),
                FakeResponse(status_code=200, json_data={"user_id": 1}, headers={"X-SESSION-ID": "SID-two"}),
                FakeResponse(status_code=200, json_data={"todo_list": []}),
            ]
        )
        client = tronclass_mcp.TronClassClient(
            tronclass_mcp.TronClassConfig(username="user", password="pass"),
            session=session,
        )

        result = client.request("GET", "/api/todos")

        assert result["status"] == 200
        assert client.session_id == "SID-two"
        request_calls = [call for call in session.calls if call[0] == "GET" and call[1].endswith("/api/todos")]
        assert len(request_calls) == 2

    def test_request_rejects_non_api_paths(self):
        client = tronclass_mcp.TronClassClient(
            tronclass_mcp.TronClassConfig(username="user", password="pass"),
            session=FakeSession(),
        )
        with pytest.raises(tronclass_mcp.TronClassError):
            client.request("GET", "/dashboard")


@pytest.mark.skipif(not tronclass_mcp._MCP_SERVER_AVAILABLE, reason="mcp package not installed")
class TestFileHelpers:
    def test_collect_uploads_walks_nested_activities(self):
        data = {
            "activities": [
                {"id": 1, "title": "Week 1", "uploads": [{"id": 10, "reference_id": 100, "name": "a.pdf", "size": 3}]},
                {"id": 2, "title": "Week 2", "uploads": [], "sub": {"uploads": [{"id": 11, "name": "b.pptx"}]}},
            ]
        }
        files = tronclass_mcp._collect_uploads(data)
        assert [f["upload_id"] for f in files] == [10, 11]
        assert files[0]["reference_id"] == 100
        assert files[0]["activity_title"] == "Week 1"

    def test_extract_text_docx_and_pptx(self):
        docx = _office_zip({"word/document.xml": "<w:document><w:p><w:t>Hello &amp; hi</w:t></w:p><w:p><w:t>Line 2</w:t></w:p></w:document>"})
        pptx = _office_zip(
            {
                "ppt/slides/slide2.xml": "<p:sld><a:p><a:t>Second</a:t></a:p></p:sld>",
                "ppt/slides/slide10.xml": "<p:sld><a:p><a:t>Tenth</a:t></a:p></p:sld>",
                "ppt/slides/slide1.xml": "<p:sld><a:p><a:t>First</a:t></a:p></p:sld>",
            }
        )
        assert tronclass_mcp._extract_text("n.docx", "", docx) == "Hello & hi\nLine 2"
        slides = tronclass_mcp._extract_text("s.pptx", "", pptx)
        assert slides.index("First") < slides.index("Second") < slides.index("Tenth")
        assert tronclass_mcp._extract_text("x.bin", "application/octet-stream", b"\x00") is None

    def test_filename_from_disposition(self):
        assert tronclass_mcp._filename_from_disposition("attachment; filename*=UTF-8''%E8%AC%9B%E7%BE%A9.pdf") == "講義.pdf"
        assert tronclass_mcp._filename_from_disposition('attachment; filename="notes.txt"') == "notes.txt"
        assert tronclass_mcp._filename_from_disposition("") is None


class TestMcpServer:
    def test_tools_registered(self):
        server = tronclass_mcp.create_mcp_server(client=StubClient())
        tool_names = {tool.name for tool in server._tool_manager.list_tools()}
        assert {
            "server_info",
            "auth_status",
            "endpoint_catalog",
            "endpoint_groups",
            "raw_api",
            "list_todos",
            "list_my_courses",
            "list_courses_page",
            "get_course",
            "list_recently_visited_courses",
            "list_semesters",
            "list_calendar_events",
            "create_calendar_event",
            "update_calendar_event",
            "delete_calendar_event",
            "list_calendar_timetables",
            "create_calendar_timetable",
            "update_calendar_timetable",
            "list_course_activities",
            "get_activity",
            "create_activity",
            "update_activity",
            "delete_activity",
            "check_activity_delete",
            "get_activity_dependencies",
            "mark_activity_read",
            "get_homework",
            "update_homework",
            "list_exams",
            "create_exam",
            "delete_exam",
            "batch_delete_exams",
            "list_questionnaires",
            "list_submissions",
            "create_submission",
            "list_peer_review_todos",
            "get_peer_submission",
            "submit_peer_review_score",
            "list_notes",
            "create_note",
            "update_note",
            "delete_note",
            "list_grades",
            "list_org_bulletins",
            "create_org_bulletin",
            "update_org_bulletin",
            "delete_org_bulletin",
            "list_org_bulletin_classifications",
            "list_resource_groups",
            "get_resource_group",
            "create_resource_group",
            "update_resource_group",
            "delete_resource_group",
            "list_resource_group_folders",
            "list_resource_group_resources",
            "list_entries",
        }.issubset(tool_names)

    def test_endpoint_catalog_tool(self):
        server = tronclass_mcp.create_mcp_server(client=StubClient())
        result = _run_tool(server, "endpoint_catalog", {"group": "notes", "method": "GET", "limit": 10})
        assert result["total_matches"] >= 1
        assert all(item["group"] == "notes" for item in result["items"])

    def test_endpoint_groups_tool(self):
        server = tronclass_mcp.create_mcp_server(client=StubClient())
        result = _run_tool(server, "endpoint_groups")
        assert result["group_count"] >= 5
        assert any(group["group"] == "resource-groups" for group in result["groups"])

    def test_raw_api_tool_delegates_to_client(self):
        server = tronclass_mcp.create_mcp_server(client=StubClient())
        result = _run_tool(
            server,
            "raw_api",
            {
                "path": "/api/todos",
                "method": "GET",
                "params": {"page": 1},
            },
        )
        assert result["path"] == "/api/todos"
        assert result["params"] == {"page": 1}

    def test_list_course_activities_uses_expected_endpoint(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "list_course_activities", {"course_id": 101})
        assert result["path"] == "/api/course/activities/"
        assert result["params"] == {"course_id": 101}
        assert client.calls[-1]["method"] == "GET"

    def test_create_note_posts_body(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "create_note", {"body": {"title": "A"}})
        assert result["path"] == "/api/notes"
        assert result["method"] == "POST"
        assert result["json_body"] == {"title": "A"}

    def test_update_resource_group_targets_item_endpoint(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "update_resource_group", {"group_id": 7, "body": {"name": "Docs"}})
        assert result["path"] == "/api/resource-groups/7"
        assert result["method"] == "PUT"
        assert result["json_body"] == {"name": "Docs"}

    def test_batch_delete_exams_sends_json_body(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "batch_delete_exams", {"exam_ids": [1, 2, 3]})
        assert result["path"] == "/api/exams/batch_delete"
        assert result["method"] == "DELETE"
        assert result["json_body"] == {"exam_ids": [1, 2, 3]}

    def test_list_resource_group_resources_passes_group_id(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "list_resource_group_resources", {"group_id": 9})
        assert result["path"] == "/api/resource-groups/resources"
        assert result["params"] == {"group_id": 9}

    def test_upload_file_tool_delegates_to_client(self, tmp_path):
        upload = tmp_path / "answer.pdf"
        upload.write_bytes(b"pdf")
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)

        result = _run_tool(
            server,
            "upload_file",
            {"file_path": str(upload), "name": "HW.pdf", "parent_type": "homework", "parent_id": 2975679},
        )

        assert result["upload"]["id"] == 123
        assert client.calls[-1] == {
            "method": "UPLOAD_FILE",
            "file_path": str(upload),
            "name": "HW.pdf",
            "parent_type": "homework",
            "parent_id": 2975679,
            "source": "",
        }

    def test_upload_file_content_tool_decodes_base64(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)

        result = _run_tool(
            server,
            "upload_file_content",
            {"name": "HW.pdf", "content_base64": "cGRm", "parent_type": "homework", "parent_id": 7},
        )

        assert result["upload"]["id"] == 124
        assert client.calls[-1] == {
            "method": "UPLOAD_BYTES",
            "content": b"pdf",
            "name": "HW.pdf",
            "parent_type": "homework",
            "parent_id": 7,
            "source": "",
        }

    def test_submit_homework_uploads_tool_delegates_to_client(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)

        result = _run_tool(
            server,
            "submit_homework_uploads",
            {"activity_id": 2975679, "upload_ids": [35331102], "comment": "done"},
        )

        assert result["submission"]["id"] == 456
        assert client.calls[-1] == {
            "method": "SUBMIT_HOMEWORK_UPLOADS",
            "activity_id": 2975679,
            "upload_ids": [35331102],
            "comment": "done",
            "draft": False,
            "user_id": None,
        }

    def test_peer_review_tools_delegate_to_client(self):
        client = StubClient()
        server = tronclass_mcp.create_mcp_server(client=client)

        todos = _run_tool(server, "list_peer_review_todos")
        submission = _run_tool(server, "get_peer_submission", {"activity_id": 2862999, "submitter_id": 314117})
        result = _run_tool(
            server,
            "submit_peer_review_score",
            {
                "activity_id": 2862999,
                "submitter_id": 314117,
                "score": 82.0,
                "comment": "優點是主題清楚，待改進是截圖可以再完整一點。",
                "inter_score_id": 5108154,
            },
        )

        assert todos["count"] == 1
        assert submission["data"]["submitter_id"] == 314117
        assert result["ok"] is True
        assert client.calls[-1] == {
            "method": "SUBMIT_PEER_REVIEW_SCORE",
            "activity_id": 2862999,
            "submitter_id": 314117,
            "score": 82.0,
            "comment": "優點是主題清楚，待改進是截圖可以再完整一點。",
            "inter_score_id": 5108154,
            "upload_ids": None,
            "rubric_score": None,
        }


class TestFileTools:
    def test_list_activity_files(self):
        client = FileStubClient(activity={"id": 5, "title": "HW", "uploads": [{"id": 7, "reference_id": 70, "name": "spec.pdf"}]})
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "list_activity_files", {"activity_id": 5})
        assert client.calls[-1]["path"] == "/api/activities/5"
        assert result["count"] == 1
        assert result["files"][0]["upload_id"] == 7

    def test_download_file_returns_text(self):
        client = FileStubClient(download={"ok": True, "name": "notes.txt", "content_type": "text/plain; charset=utf-8", "content": "abcdef".encode()})
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "download_file", {"reference_id": 70, "max_chars": 4})
        assert client.calls[-1] == {"method": "DOWNLOAD", "upload_id": None, "reference_id": 70}
        assert result["text"] == "abcd"
        assert result["truncated"] is True
        assert result["size"] == 6

    def test_download_file_returns_image_content(self):
        client = FileStubClient(download={"ok": True, "name": "fig.png", "content_type": "image/png", "content": b"\x89PNG"})
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "download_file", {"upload_id": 7})
        assert result[1].type == "image"
        assert result[1].mimeType == "image/png"

    def test_download_file_saves_only_inside_download_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRONCLASS_DOWNLOAD_DIR", str(tmp_path))
        client = FileStubClient(download={"ok": True, "name": "../../evil.txt", "content_type": "text/plain", "content": b"hi"})
        server = tronclass_mcp.create_mcp_server(client=client)
        result = _run_tool(server, "download_file", {"upload_id": 7, "save_to_download_dir": True})
        assert Path(result["saved_to"]) == tmp_path / "evil.txt"
        assert (tmp_path / "evil.txt").read_bytes() == b"hi"

    def test_client_download_follows_redirect_without_session_header(self):
        blob = FakeResponse(status_code=302, headers={"Location": "https://storage.example/signed?sig=1"}, content_type="text/html")
        session = FakeSession(responses=[blob])
        client = tronclass_mcp.TronClassClient(tronclass_mcp.TronClassConfig(username="u", password="p"), session=session)
        client._session_id = "SID"
        storage = FakeResponse(status_code=200, headers={"Content-Disposition": 'attachment; filename="a.pdf"'}, content_type="application/pdf")
        storage.content = b"%PDF"

        with patch.object(tronclass_mcp.requests, "get", return_value=storage) as get:
            result = client.download_upload(upload_id=9)

        assert session.calls[0][1].endswith("/api/uploads/9/blob")
        assert session.calls[0][2]["allow_redirects"] is False
        get.assert_called_once()
        assert get.call_args[0][0] == "https://storage.example/signed?sig=1"
        assert "headers" not in get.call_args[1]
        assert result == {"ok": True, "name": "a.pdf", "content_type": "application/pdf", "content": b"%PDF"}


class TestMain:
    def test_run_mcp_server_without_mcp_exits(self):
        with patch.object(tronclass_mcp, "_MCP_SERVER_AVAILABLE", False):
            with pytest.raises(SystemExit):
                tronclass_mcp.run_mcp_server()

    def test_http_transport_requires_token(self):
        with patch.object(tronclass_mcp, "create_mcp_server") as create:
            with pytest.raises(SystemExit):
                tronclass_mcp.run_mcp_server(transport="http", token=None)
        create.assert_not_called()

    def test_load_dotenv_does_not_override_existing(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# comment\nTRONCLASS_USERNAME='student'\nexport TRONCLASS_MCP_PORT=9000\nTRONCLASS_PASSWORD=from_file\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("TRONCLASS_USERNAME", raising=False)
        monkeypatch.delenv("TRONCLASS_MCP_PORT", raising=False)
        monkeypatch.setenv("TRONCLASS_PASSWORD", "from_shell")

        tronclass_mcp.load_dotenv(env_file, tmp_path / "missing.env")

        assert os.environ["TRONCLASS_USERNAME"] == "student"
        assert os.environ["TRONCLASS_MCP_PORT"] == "9000"
        assert os.environ["TRONCLASS_PASSWORD"] == "from_shell"
