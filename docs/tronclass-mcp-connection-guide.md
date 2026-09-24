# TronClass MCP Connection Guide

This guide explains how to connect the TronClass MCP server to Codex, Claude Desktop, Hermes Agent, or any MCP client that supports stdio servers.

## 1. Server location

Clone the repository and install dependencies:

```bash
git clone git@github.com:JasonWu55/tronclass-mcp.git
cd tronclass-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Use absolute paths in MCP client configuration:

- Python runtime: `/absolute/path/to/tronclass-mcp/.venv/bin/python`
- Server script: `/absolute/path/to/tronclass-mcp/tronclass_mcp.py`

## 2. Environment variables

Required:

- `TRONCLASS_USERNAME`
- `TRONCLASS_PASSWORD`

Optional:

- `TRONCLASS_BASE_URL` (default: `https://elearn2.fju.edu.tw`)
- `TRONCLASS_TIMEOUT` (default: `30`)
- `TRONCLASS_VERIFY_TLS` (default: `true`)
- `TRONCLASS_LOGIN_USER_AGENT`
- `TRONCLASS_API_USER_AGENT`

## 3. Start the server manually

```bash
source /absolute/path/to/tronclass-mcp/.venv/bin/activate
export TRONCLASS_USERNAME='YOUR_STUDENT_ID'
export TRONCLASS_PASSWORD='YOUR_PASSWORD'
python /absolute/path/to/tronclass-mcp/tronclass_mcp.py
```

The server uses stdio, so it waits for MCP JSON-RPC messages on stdin.

## 4. Codex integration

```bash
codex mcp add tronclass \
  --env TRONCLASS_USERNAME=YOUR_STUDENT_ID \
  --env TRONCLASS_PASSWORD=YOUR_PASSWORD \
  -- /absolute/path/to/tronclass-mcp/.venv/bin/python \
     /absolute/path/to/tronclass-mcp/tronclass_mcp.py
```

Check it with:

```bash
codex mcp list
codex mcp get tronclass
```

Remove it with:

```bash
codex mcp remove tronclass
```

Codex stores MCP server configuration in `~/.codex/config.toml`.

## 5. Claude Desktop or generic MCP JSON

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

## 6. Hermes Agent config

Add this to `~/.hermes/config.yaml` and restart Hermes:

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

## 7. Main tools

Examples:

- `auth_status`
- `endpoint_catalog`
- `endpoint_groups`
- `raw_api`
- `list_todos`
- `list_my_courses`
- `list_course_activities`
- `get_homework`
- `upload_file`
- `submit_homework_uploads`
- `list_peer_review_todos`
- `get_peer_submission`
- `submit_peer_review_score`
- `list_exams`
- `list_questionnaires`
- `list_submissions`
- `list_notes`
- `list_grades`
- `list_org_bulletins`
- `list_resource_groups`
- `list_calendar_events`

## 8. Troubleshooting

### Missing credentials

Set `TRONCLASS_USERNAME` and `TRONCLASS_PASSWORD` in the MCP client environment.

### Login succeeds but API calls fail

Check whether the session expired and retry. The client automatically refreshes once on HTTP 401.

### MCP client cannot start the server

Verify:

- Python path exists.
- `mcp` and `requests` are installed in the venv.
- `tronclass_mcp.py` exists.
- Credentials are present in environment or client config.

### Some endpoints return 404 or 403

This is expected for role-specific or UI-specific endpoints. Use `endpoint_catalog` to discover candidates, then test them with `raw_api` using the exact parameters/body expected by the frontend.
