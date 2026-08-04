# Claude Code and Codex Agent Skill

Forma ships one portable [`forma-hardware`](../integrations/agent-skills/forma-hardware/SKILL.md) Agent Skill for Claude Code and Codex. It teaches either agent how to generate and validate safe, low-voltage hardware projects through a running Forma MCP endpoint.

## Install

Install for both agents at user scope:

```bash
python scripts/operations/install-forma-skill.py
```

This copies the skill to:

- Claude Code: `~/.claude/skills/forma-hardware`
- Codex: `~/.agents/skills/forma-hardware`

Install into a repository instead:

```bash
python scripts/operations/install-forma-skill.py --scope project --project-dir /path/to/project
```

Use `--agent claude` or `--agent codex` to install only one target. Re-run with `--force` to update an existing copy. The installer never writes credentials or agent settings.

## Connect to Forma

Start the Forma backend, then configure the endpoint if it is not the local default:

```bash
export FORMA_MCP_URL=http://127.0.0.1:8000/mcp
```

For a protected deployment, export an access token without placing it in a prompt or checked-in file:

```bash
export FORMA_AUTH_TOKEN=your_access_token
```

`FORMA_TIMEOUT_SECONDS` defaults to `600`. Increase it when the selected provider has a long cold start.

The skill includes a standard-library Python client, so the agent does not need a separate MCP client package. Verify the connection directly:

```bash
python integrations/agent-skills/forma-hardware/scripts/forma.py tools
```

Optionally register Forma as a native Claude Code MCP server so its tools are available outside the skill too:

```bash
claude mcp add --scope user --transport http forma http://127.0.0.1:8000/mcp
claude mcp list
```

Use the full hosted `/api/mcp` URL instead when Forma is deployed behind that route. A protected endpoint also needs an authorization header configured through the agent host. The skill's client remains the portable fallback for both Claude Code and Codex.

## Use

In Claude Code, ask for a Forma hardware design naturally or invoke `/forma-hardware`. In Codex, ask naturally or invoke `$forma-hardware`.

Example requests:

- `Use Forma to design a 5V ESP32 soil monitor and save the Hardware IR.`
- `Validate the components and nets in forma-project.json.`
- `Generate a low-voltage weather station with sourced component research.`

The skill preserves Forma's safety boundary. Its output is a prototype plan and does not replace electrical review, compliance testing, or physical verification.

## Package layout

The canonical, product-neutral skill lives under `integrations/agent-skills/forma-hardware`. Both installations receive the same `SKILL.md`, client script, and connection reference. Codex also reads the optional `agents/openai.yaml` UI metadata; Claude safely ignores that product-specific file.

Agent Skills are an open folder format based on `SKILL.md`. See the [Agent Skills specification](https://agentskills.io/specification), [Claude Agent Skills documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview), and [Codex skill documentation](https://developers.openai.com/codex/skills) for host-specific behavior.
