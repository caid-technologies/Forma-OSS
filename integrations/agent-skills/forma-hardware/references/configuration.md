# Forma connection reference

The bundled client uses only the Python standard library.

## Environment

- `FORMA_MCP_URL`: Forma MCP endpoint. Defaults to `http://127.0.0.1:8000/mcp`. A bare server origin is normalized by appending `/mcp`.
- `FORMA_AUTH_TOKEN`: Optional bearer token for a protected deployment.
- `FORMA_TIMEOUT_SECONDS`: HTTP timeout. Defaults to `600` because hardware generation can take several minutes.

Keep secrets in the environment. Do not write tokens into skill files, shell history, generated projects, or chat responses.

## Start a local server

From a Forma OSS checkout, run either:

```bash
./scripts/development/dev.sh
```

or:

```bash
uvicorn apps.api.main:app --reload --port 8000
```

The server must have `BLUEPRINT_USER_SECRETS_KEY`. Normal Claude Code/Codex usage does not require a server LLM: the host agent authors Hardware IR and `blueprint.compile_project` performs deterministic compilation.

Server-side prompt generation is optional. Configure a live provider such as Anthropic or OpenAI before using `blueprint.generate_project`. A missing provider never authorizes simulation. Deterministic simulation is suitable only when the user explicitly accepts it and the request supplies `allow_simulation: true` (the client requires `--provider simulation --allow-simulation`).

## Common failures

- `Connection refused`: start Forma or correct `FORMA_MCP_URL`.
- `401` or `403`: obtain an authorized token and export `FORMA_AUTH_TOKEN`.
- JSON-RPC `Method not found`: the server is not a compatible Forma MCP endpoint or is outdated.
- Generation timeout: increase `FORMA_TIMEOUT_SECONDS` and check the selected model provider.
- Generation error: run the bundled `scripts/forma.py config` from the skill directory and report the credential-safe runtime details; never request that credentials be pasted into chat.

## Supported tool workflow

- `blueprint.compile_project`: compile host-agent-authored Hardware IR, validate it, and build diagrams or PDF captures.
- `blueprint.generate_project`: optional explicitly configured server-side LLM generation; never the default agent-skill path.
- `blueprint.validate_circuit`: validate components and connection nets.
- `blueprint.export_project_pdf`: render existing Hardware IR as an embedded `application/pdf` report.
- `blueprint.debug_config`: inspect credential-safe runtime configuration.
- `blueprint.a2a.get_job` and `blueprint.a2a.list_jobs`: inspect persisted job metadata.

Use the bundled `scripts/forma.py tools` to discover the live server's complete tool list instead of assuming optional tools exist.
