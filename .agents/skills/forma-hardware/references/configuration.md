# Forma connection

The bundled client uses only the Python standard library.

## Environment

- `FORMA_MCP_URL`: MCP endpoint; defaults to `http://127.0.0.1:8000/mcp`.
- `FORMA_AUTH_TOKEN`: optional bearer token for a protected deployment.
- `FORMA_TIMEOUT_SECONDS`: request timeout; defaults to 600 seconds.

Keep tokens in the environment, never in committed configuration or generated projects.

## Start Forma locally

From a Forma checkout, the one-command launcher installs missing backend and
frontend dependencies, enables local auth/SQLite defaults without selecting an
LLM, creates an encrypted local key under `.forma/`, and starts both services:

```bash
./scripts/development/dev.sh
```

The launcher honors explicit environment overrides. OpenCode (or another host
agent) supplies the model that authors Hardware IR; `forma.compile_project`
then performs deterministic validation, rendering, and persistence. The
launcher does not set `LLM_PROVIDER` or `LLM_MODEL`. To run only the backend
manually, set a server-only key:

```bash
FORMA_AUTH_MODE=local FORMA_DEV_MODE=true \
FORMA_USER_SECRETS_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
uvicorn apps.api.main:app --port 8000
```

The separate `forma.generate_project` path is server-side generation. Use it
only when the backend has an explicitly configured provider and model; it does
not inherit OpenCode's active model through MCP.

## OpenClaw

The project skill is discovered from `.agents/skills/forma-hardware/SKILL.md`. Register the Streamable HTTP server and verify it:

```bash
openclaw mcp set forma '{"url":"http://127.0.0.1:8000/mcp","transport":"streamable-http"}'
openclaw mcp doctor forma --probe
```

## NemoClaw

NemoClaw runs OpenClaw in a deny-by-default OpenShell sandbox. A host-loopback MCP URL is not reachable from that sandbox. Deploy Forma at a stable HTTPS URL, configure a random server-side `FORMA_MCP_API_KEY` of at least 32 characters, and register it as a managed MCP server:

```bash
export FORMA_MCP_TOKEN="your-random-token"
nemoclaw my-sandbox mcp add forma --url https://forma.example.com/api/mcp --env FORMA_MCP_TOKEN
unset FORMA_MCP_TOKEN
nemoclaw my-sandbox mcp status forma --json
```

The `--env` form keeps the raw bearer credential outside the sandbox. Upload this skill into the default OpenClaw workspace:

```bash
nemoclaw my-sandbox upload <skill-directory> /sandbox/.openclaw/workspace/skills/
```

Upload it separately for every agent workspace. NemoClaw rejects loopback and `host.docker.internal` MCP URLs. For a stable RFC1918 endpoint, register the exact TLS hostname with `--trusted-private-host <hostname>`.

## OpenCode

The project skill is discovered from the same `.agents/skills` directory. Add this to `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "forma": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "enabled": true,
      "oauth": false
    }
  }
}
```

Then run `opencode mcp list`. For a protected server, add `"Authorization": "Bearer {env:FORMA_AUTH_TOKEN}"` under `headers`.

## Troubleshooting

- Connection refused: run `./scripts/development/dev.sh` from a Forma checkout, or set `FORMA_MCP_URL` to a hosted `/api/mcp` endpoint.
- HTTP 401/403: supply either a Clerk admin bearer token or the dedicated `FORMA_MCP_API_KEY`.
- NemoClaw rejects the URL: use a stable HTTPS endpoint, not host loopback; declare an exact private hostname when needed.
- Method not found: update the Forma server and inspect `python scripts/forma.py tools`.
- Timeout: increase `FORMA_TIMEOUT_SECONDS` and inspect the configured provider if using server-side generation.
