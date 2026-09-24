# TronClass MCP Server

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for TronClass. It logs in with TronClass/CAS credentials, keeps an authenticated API session, and exposes course, homework, todo, grade, resource, calendar, submission, and peer-review tools to MCP clients such as Codex, Claude Desktop, and Hermes Agent.

> **Security note**: this repository does **not** include credentials. Pass `TRONCLASS_USERNAME` and `TRONCLASS_PASSWORD` through your MCP client environment or shell.

## Features

- CAS login flow for TronClass/FJU eLearn (`https://elearn2.fju.edu.tw` by default).
- Automatic session reuse and one retry after HTTP 401.
- 50+ typed MCP tools for common TronClass operations.
- `raw_api` escape hatch for authenticated calls to arbitrary `/api/*` endpoints.
- Built-in frontend-discovered endpoint catalog: 251 endpoint patterns across 110 groups.
- File upload and homework submission helpers.
- Peer-review / mutual-evaluation helpers.
- Unit tests for login/session behavior, catalog helpers, and MCP tool routing.

## Requirements

- Python 3.11+
- TronClass account credentials
- Python packages:
  - `mcp>=1,<2` (the server currently uses the MCP Python SDK v1 FastMCP API)
  - `requests`

## Quick start

```bash
git clone git@github.com:JasonWu55/tronclass-mcp.git
cd tronclass-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export TRONCLASS_USERNAME='YOUR_STUDENT_ID'
export TRONCLASS_PASSWORD='YOUR_PASSWORD'
python tronclass_mcp.py
```

The server speaks MCP over stdio, so it is normally launched by an MCP client instead of run directly in a terminal.

## Configuration

| Environment variable | Required | Default | Description |
|---|---:|---|---|
| `TRONCLASS_USERNAME` | Yes | — | TronClass/CAS username or student ID. |
| `TRONCLASS_PASSWORD` | Yes | — | TronClass/CAS password. |
| `TRONCLASS_BASE_URL` | No | `https://elearn2.fju.edu.tw` | TronClass base URL. |
| `TRONCLASS_TIMEOUT` | No | `30` | HTTP request timeout in seconds. |
| `TRONCLASS_VERIFY_TLS` | No | `true` | Set to `false`, `0`, `no`, or `off` to disable TLS verification. |
| `TRONCLASS_LOGIN_USER_AGENT` | No | mobile app UA | User-Agent for CAS login requests. |
| `TRONCLASS_API_USER_AGENT` | No | mobile/common UA | User-Agent for TronClass API requests. |

## MCP client setup

### Codex CLI

```bash
codex mcp add tronclass \
  --env TRONCLASS_USERNAME=YOUR_STUDENT_ID \
  --env TRONCLASS_PASSWORD=YOUR_PASSWORD \
  -- /absolute/path/to/tronclass-mcp/.venv/bin/python \
     /absolute/path/to/tronclass-mcp/tronclass_mcp.py
```

Check the registration:

```bash
codex mcp list
codex mcp get tronclass
```

Remove it:

```bash
codex mcp remove tronclass
```

### Claude Desktop / generic MCP JSON

```json
{
  "mcpServers": {
    "tronclass": {
      "command": "/absolute/path/to/tronclass-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/tronclass-mcp/tronclass_mcp.py"],
      "env": {
        "TRONCLASS_USERNAME": "YOUR_STUDENT_ID",
        "TRONCLASS_PASSWORD": "YOUR_PASSWORD"
      }
    }
  }
}
```

### Hermes Agent

Add a server entry to `~/.hermes/config.yaml`, then restart Hermes:

```yaml
mcp_servers:
  tronclass:
    command: "/absolute/path/to/tronclass-mcp/.venv/bin/python"
    args: ["/absolute/path/to/tronclass-mcp/tronclass_mcp.py"]
    env:
      TRONCLASS_USERNAME: "YOUR_STUDENT_ID"
      TRONCLASS_PASSWORD: "YOUR_PASSWORD"
    timeout: 120
```

Hermes registers tools with the prefix `mcp_tronclass_`, for example `mcp_tronclass_list_todos`.

## Available tools

### Server and discovery

| Tool | Description |
|---|---|
| `server_info` | Return server metadata and configuration status. |
| `auth_status` | Log in if needed and return the authenticated session summary. |
| `endpoint_catalog` | Browse the frontend-discovered TronClass API endpoint catalog. |
| `endpoint_groups` | Summarize endpoint groups with counts and methods. |
| `raw_api` | Call an arbitrary authenticated TronClass `/api` endpoint. |

### Course, activity, homework, and submissions

| Tool | Description |
|---|---|
| `list_todos` | Return the authenticated user's todo list. |
| `list_my_courses` | Return the authenticated user's course list. |
| `list_courses_page` | Query the paginated `/api/courses` endpoint. |
| `get_course` | Fetch a course by ID. |
| `list_recently_visited_courses` | Return recently visited courses. |
| `list_semesters` | Return semester metadata. |
| `list_course_activities` | List activities for a course. |
| `get_activity` / `create_activity` / `update_activity` / `delete_activity` | Manage activities. |
| `check_activity_delete` | Check whether an activity can be deleted. |
| `get_activity_dependencies` | Inspect whether an activity has dependent records. |
| `mark_activity_read` | Mark one or more course activities as read. |
| `get_homework` / `update_homework` | Fetch or update homework details. |
| `list_submissions` / `create_submission` | List or create submissions. |
| `upload_file` | Upload a local file into TronClass storage. |
| `submit_homework_uploads` | Submit uploaded file IDs to a homework activity. |

### Peer review / mutual evaluation

| Tool | Description |
|---|---|
| `list_peer_review_todos` | List pending peer-review / mutual-evaluation todos. |
| `get_peer_submission` | Fetch a peer submitter's submission metadata. |
| `submit_peer_review_score` | Submit or update a plain-text peer-review score and comment. |

### Calendar, exams, notes, resources, grades, bulletins

| Tool family | Tools |
|---|---|
| Calendar events | `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event` |
| Calendar timetables | `list_calendar_timetables`, `create_calendar_timetable`, `update_calendar_timetable` |
| Exams | `list_exams`, `create_exam`, `delete_exam`, `batch_delete_exams` |
| Questionnaires | `list_questionnaires` |
| Notes | `list_notes`, `create_note`, `update_note`, `delete_note` |
| Grades | `list_grades` |
| Organization bulletins | `list_org_bulletins`, `create_org_bulletin`, `update_org_bulletin`, `delete_org_bulletin`, `list_org_bulletin_classifications` |
| Resource groups | `list_resource_groups`, `get_resource_group`, `create_resource_group`, `update_resource_group`, `delete_resource_group`, `list_resource_group_folders`, `list_resource_group_resources` |
| Entries | `list_entries` |

## Examples

Call a raw endpoint through an MCP client:

```json
{
  "path": "/api/todos",
  "method": "GET"
}
```

List course activities:

```json
{
  "course_id": 123456,
  "extra_params": {
    "module_ids": "",
    "activity_type": ""
  }
}
```

Upload then submit homework:

1. Call `upload_file` with the local file path.
2. Read the returned upload ID from `upload.id`.
3. Call `submit_homework_uploads` with `activity_id` and `upload_ids`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

The tests use fake sessions and do not contact TronClass.

## Documentation

- [`docs/tronclass-mcp-connection-guide.md`](docs/tronclass-mcp-connection-guide.md) — connection examples for MCP clients.
- [`docs/tronclass-api-complete.md`](docs/tronclass-api-complete.md) — generated endpoint notes and frontend-discovered API catalog summary.

## Troubleshooting

### Missing credentials

Set `TRONCLASS_USERNAME` and `TRONCLASS_PASSWORD` in your MCP client configuration or shell.

### MCP client cannot start the server

Verify that:

- The configured Python path exists.
- `pip install -e .` completed successfully.
- The configured `tronclass_mcp.py` path is absolute and correct.
- Credentials are present in the MCP client environment.

### Login succeeds but API calls fail

The server retries once on HTTP 401. If failures continue, confirm that the account can log in through the TronClass web/mobile interface and that `TRONCLASS_BASE_URL` is correct.

### Some endpoints return 403, 404, or 500

The catalog includes frontend-discovered endpoints. Some are role-specific, require exact UI payloads, or are unavailable to student accounts. Use `endpoint_catalog` and `raw_api` to inspect and test the exact request shape.
