---
name: forma-hardware
description: Authors, compiles, validates, and exports structured low-voltage maker-electronics projects with Forma, including Hardware IR, BOMs, wiring, mechanical layouts, build docs, and five-view PDFs. Use when a user asks Claude Code or Codex to design, compile, inspect, document, or electrically validate a safe 3.3V-12V hardware prototype with Forma.
---

# Forma Hardware

Use the current host agent—Claude Code or Codex—to author the design. Use Forma as the deterministic hardware compiler, validator, diagrammer, and exporter. Never substitute a simulated example for failed generation.

## Connect

Prefer native Forma MCP tools. Otherwise run the bundled client from this skill directory:

```bash
python <skill-directory>/scripts/forma.py tools
```

The client reads `FORMA_MCP_URL` and defaults to `http://127.0.0.1:8000/mcp`. For connection or authentication failures, read [references/configuration.md](references/configuration.md).

## Author and compile a project

1. Keep the project within safe low-voltage educational or maker scope. Decline weapons, critical medical or life-support devices, mains AC, automotive control, and unsafe high-power battery requests.
2. Read [references/hardware-ir.md](references/hardware-ir.md), then author complete Forma Hardware IR from the user's brief. Preserve stated power, size, budget, environment, interfaces, and component preferences. Do not copy a bundled example or claim unavailable supplier facts.
3. Save the IR as `forma-project.json`.
4. Compile it with the current host identity:

```bash
# Claude Code
python <skill-directory>/scripts/forma.py compile forma-project.json --authoring-agent claude --output compiled-project.json

# Codex
python <skill-directory>/scripts/forma.py compile forma-project.json --authoring-agent codex --output compiled-project.json
```

When the user requests a PDF, add `--pdf-output forma-project.pdf`. The PDF contains five landscape workspace captures: INFO, BOM, MECH, WIRE, and DOCS.

5. Inspect deterministic validation findings. Fix agent-authored components or nets and compile again when practical. Treat every `CRITICAL` issue as blocking.
6. Report the authoring agent, artifact paths, design summary, power assumptions, major components, and remaining validation issues. Label the result as an AI-assisted prototype plan.

When using native MCP, call `blueprint.compile_project` with `project_ir`, `authoring_agent` set to `claude` or `codex`, and optional `output_formats: ["pdf"]`.

## Validate or export existing IR

```bash
python <skill-directory>/scripts/forma.py validate forma-project.json --output validation.json
python <skill-directory>/scripts/forma.py export-pdf forma-project.json --pdf-output forma-project.pdf
```

Use export-only mode when the IR is already complete. It does not assert who authored the project.

## Optional server-side generation

Do not use `blueprint.generate_project` by default. Use it only when the user deliberately wants the separately configured Forma server LLM described in [references/configuration.md](references/configuration.md).

```bash
python <skill-directory>/scripts/forma.py generate "<brief>" --use-configured-provider --output forma-project.json
```

Simulation is never an automatic fallback. It requires explicit user acceptance and both `--provider simulation --allow-simulation`.

## Output integrity

Keep compiled JSON intact. Do not expose provider credentials or authorization headers. Do not claim that diagrams, prices, availability, compatibility, or mechanical clearances were physically verified unless returned evidence establishes that.
