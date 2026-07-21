# Forma TUI

`blueprint-tui` is a Rust terminal chatbot for Forma Lattice agents.

Each namespace agent runs independently. When the user sends text or a file, the TUI broadcasts the input to every agent worker and renders their responses as they arrive.

The right rail includes the **Forma Architect**, a master coordination agent. It streams visible working notes while the request is routed, waits for the namespace agents to finish, then streams a final synthesized output.

## Run

```bash
cargo run --manifest-path blueprint-tui/Cargo.toml
```

Skip the name prompt:

```bash
cargo run --manifest-path blueprint-tui/Cargo.toml -- --name Isayah
```

Submit a file at startup:

```bash
cargo run --manifest-path blueprint-tui/Cargo.toml -- --name Isayah --file README.md
```

Discover live Lattice cards from a running Forma backend and let the agents use Forma MCP context:

```bash
cargo run --manifest-path blueprint-tui/Cargo.toml -- --name Isayah --mcp-url http://127.0.0.1:8000/api/mcp
```

When `--mcp-url` is set, each agent can discover Forma MCP tools and fetch its own Lattice card before responding. Agents keep a short in-session memory of prior user turns and their own replies.

By default, the TUI stores local jobs, agent responses, and persistent agent memory in `./blueprint_tui.db`.
Use `BLUEPRINT_TUI_DB_PATH`, `--sqlite-path path/to/file.db`, or `--no-sqlite` to change that behavior.

Stream the Forma Architect and every namespace agent through OpenAI:

```bash
cargo run --manifest-path blueprint-tui/Cargo.toml -- --name Isayah --openai
```

The TUI loads `OPENAI_API_KEY` from the repo `.env` automatically, or from the process environment if already set.
It also uses `OPENAI_MODEL` from `.env` unless `--openai-model` is provided. If that model is unavailable, it retries with `OPENAI_FALLBACK_MODEL` or `gpt-4o-mini`.

Choose a model or OpenAI-compatible base URL:

```bash
cargo run --manifest-path blueprint-tui/Cargo.toml -- --name Isayah --openai --openai-model gpt-4o-mini --openai-base-url https://api.openai.com/v1
```

## Keys And Commands

- Type a short name first, or type a prompt and the TUI will use your OS username automatically.
- Type normal text and press Enter to broadcast it.
- Press Tab or Shift-Tab to switch the chat pane between all agents and individual agents.
- Press F2 or Ctrl-F to switch the scroll port between chat, Forma Architect, and agents.
- Press Up/Down, PageUp/PageDown, Home, or End to scroll the active port.
- Type `/scroll chat`, `/scroll architect`, or `/scroll agents` to switch the scroll port directly.
- Type `/agent all`, `/agent next`, `/agent prev`, or `/agent product.bom` to switch the chat pane directly.
- Type `/file path/to/file` to broadcast a file preview.
- Type `/agents` to list loaded agents.
- Type `/forget` to clear all in-session and SQLite-backed agent memory.
- Type `/clear` to clear the transcript.
- Type `/quit` or press Ctrl-Q to exit.
