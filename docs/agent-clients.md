# OpenClaw, NemoClaw, and OpenCode

Forma supports these clients through two portable surfaces:

- A shared Agent Skill at `.agents/skills/forma-hardware/SKILL.md`.
- An MCP Streamable HTTP endpoint at `http://127.0.0.1:8000/mcp` (or `/api/mcp` when the deployment adds an `/api` prefix).

Start the backend in local authentication mode:

```bash
FORMA_AUTH_MODE=local uvicorn apps.api.main:app --port 8000
```

## OpenClaw

From this repository, OpenClaw discovers the project skill under `.agents/skills`. Register and probe Forma's MCP endpoint:

```bash
openclaw mcp set forma '{"url":"http://127.0.0.1:8000/mcp","transport":"streamable-http"}'
openclaw mcp doctor forma --probe
```

Start a new OpenClaw session after adding the skill. Ask it to use `forma-hardware`, or invoke the skill explicitly if desired.

## NemoClaw

NemoClaw runs OpenClaw inside an OpenShell sandbox. The sandbox cannot use the host's loopback address or read the host checkout directly, so expose Forma at a stable HTTPS URL and upload the skill into the sandbox.

Set `FORMA_MCP_API_KEY` to a random value of at least 32 characters on the Forma server. Put the same value in a temporary host environment variable, then let NemoClaw store it outside the sandbox and inject it into managed MCP requests:

```bash
export FORMA_MCP_TOKEN="your-random-token"
nemoclaw my-sandbox mcp add forma --url https://forma.example.com/api/mcp --env FORMA_MCP_TOKEN
unset FORMA_MCP_TOKEN
nemoclaw my-sandbox mcp status forma --json
```

Upload the portable skill into OpenClaw's sandbox workspace:

```bash
nemoclaw my-sandbox upload .agents/skills/forma-hardware /sandbox/.openclaw/workspace/skills/
```

Repeat the upload for each agent workspace. For a stable private RFC1918 endpoint, add `--trusted-private-host forma.internal.example` when registering it and use a certificate valid for that exact hostname. NemoClaw intentionally rejects `http://127.0.0.1`, `localhost`, and `host.docker.internal` MCP URLs.

## CAD skill dependency

The shared skill manages the OpenCAD dependency for CAD-capable workflows;
the base Forma SDK and MCP client do not install it. Run setup once after
installing the skill, before asking an agent to create or export CAD:

```bash
python .agents/skills/forma-hardware/scripts/cad.py setup
```

The adapter pins OpenCAD `0.2.3` with the `occt` extra, reuses a compatible
native installation, and verifies OCCT before a model runs. See the skill's
[CAD reference](../.agents/skills/forma-hardware/references/cad.md) for build
commands, exact recovery diagnostics, and `FORMA_OPENCAD_REQUIREMENT` source
overrides.

## OpenCode

OpenCode also discovers `.agents/skills/forma-hardware/SKILL.md`. Add Forma to `opencode.json`:

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

Verify it with:

```bash
opencode mcp list
```

## Protected deployments

The MCP route accepts either a Clerk administrator session or the dedicated `FORMA_MCP_API_KEY`. The API key must contain at least 32 characters. Pass the selected credential as an `Authorization: Bearer ...` header and keep it in an environment variable rather than committing it.

OpenCode header example:

```json
"headers": {
  "Authorization": "Bearer {env:FORMA_AUTH_TOKEN}"
}
```

OpenClaw can set the equivalent header with `openclaw mcp add --header` or in its saved server definition.

## Host-authored compilation

`forma.compile_project` is the preferred agent workflow. The calling agent authors Hardware IR, then Forma normalizes it, runs deterministic validation, and returns the compiled IR, validation summary, Mermaid wiring graph, and SVG schematic. This path does not invoke Forma's configured server-side LLM.

`forma.generate_project` remains available when server-side generation is explicitly wanted.

If MCP is not configured in the host, the skill's standard-library client can call the same endpoint:

```bash
python .agents/skills/forma-hardware/scripts/forma.py tools
python .agents/skills/forma-hardware/scripts/forma.py compile project.json --authoring-agent opencode --output compiled.json
```
