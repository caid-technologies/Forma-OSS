# Agent-To-Agent (A2A)

Forma exposes the same hardware generation capability through several agent-friendly transports.

## Transports
- **REST:** `GET /api/a2a/capabilities`, `PUT /api/a2a/agents/{agent_id}`, `POST /api/a2a/messages`, long-poll `GET /api/a2a/agents/{agent_id}/events`, and job metadata lookup under `GET /api/a2a/jobs`
- **WebSocket:** `/api/a2a/socket/{agent_id}`
- **TCP JSONL socket:** optional newline-delimited JSON socket enabled with `A2A_SOCKET_ENABLED=true`
- **MCP-style JSON-RPC:** `POST /api/mcp` or `POST /api/a2a/mcp`

Job metadata is stored in the primary application database selected by `DATABASE_BACKEND`. Local jobs live in the same SQLite file selected by `SQLITE_DATABASE_URL`; hosted jobs live in the same Supabase database as projects and chats. On upgrade, rows from the retired `blueprint_jobs.db` file are imported without overwriting jobs already present in the primary database. The legacy file is retained. The store keeps compact metadata only: payloads have image data redacted, results are summarized instead of storing full generated IR blobs, and `source_usage` records whether a generation job used the Catalog/data warehouse, Web Research/Firecrawl, past-job context, or a combination.

## Message Shape
```json
{
  "type": "task",
  "job_id": "job-build-001",
  "action": "blueprint.generate_project",
  "sender": "agent_alpha",
  "recipient": "blueprint",
  "correlation_id": "build-001",
  "payload": {
    "prompt": "ESP32 soil moisture monitor with OLED",
    "workflow": "default",
    "data_sources": ["past_jobs"],
    "past_jobs_limit": 3,
    "generate_image": false
  }
}
```

Server-owned actions queue an `ack` event followed by a `result` or `error` event for the sender. Messages addressed to another agent are brokered into that agent's queue. Every submitted message is persisted with a `job_id` and lifecycle status.

`data_sources: ["past_jobs"]` adds lightweight, owner-scoped retrieval over completed generation jobs. Forma ranks recent stored project outputs by lexical overlap with the new prompt and supplies a compact context window to the generator. Retrieval and generation run asynchronously; no embeddings or external retrieval infrastructure are used.

## REST Listen Flow
1. Register an agent:
```bash
curl -X PUT http://localhost:8000/api/a2a/agents/agent_alpha \
  -H 'Content-Type: application/json' \
  -d '{"name":"Agent Alpha","capabilities":["hardware_planning"],"transports":["rest"]}'
```

2. Send a task:
```bash
curl -X POST http://localhost:8000/api/a2a/messages \
  -H 'Content-Type: application/json' \
  -d '{"sender":"agent_alpha","recipient":"blueprint","action":"blueprint.generate_project","payload":{"prompt":"ESP32 soil moisture monitor with OLED","generate_image":false}}'
```

Set `payload.generate_image` to `true` only for jobs that should call the configured image model. If the image model fails, the hardware job can still succeed; persisted job metadata includes `result_summary.operation_statuses`, `image_output_status=failed`, `image_output_error`, and `image_output_error_type`.

3. Long-poll for queued events:
```bash
curl 'http://localhost:8000/api/a2a/agents/agent_alpha/events?timeout=30&limit=10'
```

4. Fetch persisted job metadata:
```bash
curl http://localhost:8000/api/a2a/jobs/job-build-001
curl 'http://localhost:8000/api/a2a/jobs?sender=agent_alpha&status=succeeded'
```

## WebSocket
Connect to `/api/a2a/socket/{agent_id}` and send the same JSON message shape. The socket receives queued A2A events as JSON objects. It also accepts MCP JSON-RPC envelopes.

## TCP JSONL
Set:
```env
A2A_SOCKET_ENABLED=true
A2A_SOCKET_HOST=127.0.0.1
A2A_SOCKET_PORT=8766
```

Each line sent to the socket is an `A2AMessage` JSON object. Each line returned by the socket is an `A2AEvent` JSON object.

## MCP Tools
`POST /api/mcp` supports:
- `initialize`
- `tools/list`
- `tools/call`

Available tools:
- `blueprint.generate_project`
- `blueprint.debug_config`
- `blueprint.validate_circuit`
- `blueprint.export_project_pdf`
- `blueprint.a2a.send_message`
- `blueprint.a2a.poll_events`
- `blueprint.a2a.get_job`
- `blueprint.a2a.list_jobs`
- `blueprint.lattice.list_agents`
- `blueprint.lattice.get_agent_card`

`blueprint.generate_project` accepts `output_formats: ["pdf"]` to add a printable project report. The PDF is returned as an MCP embedded binary resource with MIME type `application/pdf`; existing generation responses are unchanged when `output_formats` is omitted.

To export existing Hardware IR without generating a new project, call `blueprint.export_project_pdf`:

```json
{
  "jsonrpc": "2.0",
  "id": "pdf-1",
  "method": "tools/call",
  "params": {
    "name": "blueprint.export_project_pdf",
    "arguments": {
      "project_ir": {
        "overview": {"title": "Plant Monitor", "description": "A low-voltage sensor project"},
        "components": [],
        "nets": []
      }
    }
  }
}
```
