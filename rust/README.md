# Forma Rust Integration

This workspace is for low-level and streaming integrations that should not live
inside the Python API process.

Current crate:

- `blueprint-edge`: a small JSONL event emitter/listener process with an MCP
  stdio server for agent-facing source control.

The boundary between Rust and the rest of Forma is intentionally plain:
JSONL for streams and Content-Length-framed JSON-RPC for MCP. A Python worker,
A2A bridge, MCP client, or systemd service can spawn this binary and consume
events without linking Rust into the API process.

## Commands

```bash
cd rust
cargo run -p blueprint-edge -- emit --source-type manual --name demo --payload '{"ok":true}'
printf 'alpha\nbeta\n' | cargo run -p blueprint-edge -- stdin --name test-lines
cargo run -p blueprint-edge -- linux-snapshot
cargo run -p blueprint-edge -- mcp --config blueprint-edge/config/example.toml
cargo run -p blueprint-edge -- ollama-stream \
  --config blueprint-edge/config/example.toml \
  --model qwen3:0.6b \
  --prompt 'Describe a blue hardware prototype in one sentence.' \
  --agent-output planner=../.logs/agents/planner.jsonl \
  --agent-output critic=../.logs/agents/critic.jsonl
cargo run -p blueprint-edge -- llama-cpp-stream \
  --config blueprint-edge/config/example.toml \
  --model local-model \
  --prompt 'Stream a short note about a blue robot.' \
  --stream-id llama-cpp-blue-demo \
  --listen-tcp 127.0.0.1:9100
cargo run -p blueprint-edge -- spacebase-read \
  --config blueprint-edge/config/example.toml \
  --stream-id llama-cpp-blue-demo \
  --agent planner \
  --limit 5
../scripts/test-rust-stream-configs.py
../scripts/verify-contra-mcp.py
```

## MCP Tools

The MCP server currently exposes:

- `edge.config.get`: return loaded config and registered sources.
- `edge.sources.list`: list source registrations.
- `edge.emit`: create one edge event from tool arguments.
- `edge.linux.snapshot`: capture a best-effort Linux host snapshot.
- `edge.sources.poll`: poll configured pollable sources once.
- `edge.spacebase.agents.list`: list local stream agents.
- `edge.spacebase.stream.read`: read local Spacebase stream events.
- `edge.spacebase.event.write`: append one event to a local stream.

## Streaming LLM Fanout

`ollama-stream` listens to Ollama's streaming chat endpoint, converts every
provider chunk into a `llm.ollama.chat.chunk` event, and writes each event to
all configured agent outputs.

Agent outputs use `name=path`:

```bash
cargo run -p blueprint-edge -- ollama-stream \
  --prompt 'Say hello in five short chunks.' \
  --stdout false \
  --agent-output planner=../.logs/agents/planner.jsonl \
  --agent-output builder=../.logs/agents/builder.jsonl
```

Each agent receives JSONL with its own `metadata.agent_route.agent_name`, so
agents can tail separate files while seeing the same provider stream.

`llama-cpp-stream` reads OpenAI-compatible streaming chunks from a local
llama.cpp server at `/v1/chat/completions`, then writes the same stream into
local Spacebase-style files:

```text
.spacebase/
  streams/
    llama-cpp-blue-demo/
      manifest.json
      events.jsonl
      agents/
        planner.jsonl
        critic.jsonl
```

The default agent manifests in `blueprint-edge/config/example.toml` mark the
agents as `source = "contra-mcp"` with `model = "contra.com/mcp"`, so the local
stream contract points at Contra's MCP endpoint while provider listeners remain
local.

Contra MCP is OAuth-protected. `../scripts/verify-contra-mcp.py` fetches the
protected-resource metadata, records the unauthenticated challenge, and attempts
an authenticated initialize call when `CONTRA_MCP_TOKEN` is set.

Use `spacebase-read` to read the event log or one agent stream:

```bash
cargo run -p blueprint-edge -- spacebase-read \
  --config blueprint-edge/config/example.toml \
  --stream-id llama-cpp-blue-demo \
  --limit 20
```

For live in-memory delivery, add `--listen-tcp` and have agents connect before
or during generation:

```bash
nc 127.0.0.1 9100
```

Every chunk is first converted to an in-memory event, then immediately written
as JSONL to connected TCP listeners, and then to the configured file streams.
`--live-replay` controls how many recent in-memory frames a late listener gets.
For manual testing, add `--wait-for-live-listener` so the provider call waits
until your `nc` client is connected:

```bash
cargo run -p blueprint-edge -- ollama-stream \
  --config blueprint-edge/config/example.toml \
  --model qwen3:0.6b \
  --prompt 'Reply with exactly: blue stream ok' \
  --stdout false \
  --listen-tcp 127.0.0.1:9100 \
  --wait-for-live-listener
```

MCP messages use stdio framing:

```text
Content-Length: 47

{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

Configuration starts in `blueprint-edge/config/example.toml`. Add new source
blocks there first, then register them through typed config structs in
`blueprint-edge/src/lib.rs`.

## Event Shape

Each line is one JSON object:

```json
{
  "schema_version": 1,
  "event_id": "edge-...",
  "observed_at_unix_ms": 1760000000000,
  "kind": "source.event",
  "source": {
    "provider": "blueprint-edge",
    "source_type": "stdin",
    "name": "test-lines",
    "uri": null
  },
  "payload": {},
  "metadata": {}
}
```

## Intended Growth

- File, socket, serial, MQTT, or device listeners.
- Linux environment and process telemetry.
- Optional low-level integrations behind feature flags.
- A Python bridge that forwards JSONL events into Forma jobs/A2A.
- MCP resource subscriptions once sources become long-running streams.
