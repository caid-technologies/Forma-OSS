---
name: forma-hardware
description: Compile, validate, inspect, or generate safe low-voltage maker-electronics projects with Forma. Use for Hardware IR, BOMs, wiring, schematics, mechanical notes, and build instructions in OpenClaw, NemoClaw, OpenCode, Claude Code, or Codex.
---

# Forma Hardware

Use the host agent to author the design and Forma to normalize Hardware IR, apply deterministic electrical checks, and render diagrams. Never replace a failed live generation with simulated output unless the user explicitly requests simulation.

## Connect

Prefer the native `forma.*` MCP tools when available. Otherwise run the bundled standard-library client:

```bash
python <skill-directory>/scripts/forma.py tools
```

It reads `FORMA_MCP_URL`, defaulting to `http://127.0.0.1:8000/mcp`, and optional `FORMA_AUTH_TOKEN`. Read [references/configuration.md](references/configuration.md) if the server is not connected.

## Author and compile

1. Keep the project within safe low-voltage educational or maker scope. Decline weapons, critical medical or life-support devices, mains AC, automotive control, and unsafe high-power battery requests.
2. Read [references/hardware-ir.md](references/hardware-ir.md), then author complete Hardware IR from the brief. Preserve stated power, dimensions, budget, environment, interfaces, and part preferences. Do not invent verified supplier availability or physical clearances.
3. Save the IR as `forma-project.json`.
4. Call `forma.compile_project` with `project_ir` and the correct `authoring_agent` (`openclaw`, `nemoclaw`, `opencode`, `claude`, or `codex`). With the bundled client:

```bash
python <skill-directory>/scripts/forma.py compile forma-project.json --authoring-agent openclaw --output compiled-project.json
python <skill-directory>/scripts/forma.py compile forma-project.json --authoring-agent nemoclaw --output compiled-project.json
python <skill-directory>/scripts/forma.py compile forma-project.json --authoring-agent opencode --output compiled-project.json
```

5. Fix practical agent-authored errors and compile again. Treat every `CRITICAL` finding as blocking.
6. Report artifact paths, power assumptions, major components, and remaining findings. Label the result as an AI-assisted prototype plan.

## Validate existing IR

Call `forma.validate_circuit`, or use:

```bash
python <skill-directory>/scripts/forma.py validate forma-project.json --output validation.json
```

## Optional server-side generation

Use `forma.generate_project` only when the user wants Forma's separately configured server-side LLM. Prefer host-authored IR plus `forma.compile_project` for normal OpenClaw, NemoClaw, and OpenCode work.

```bash
python <skill-directory>/scripts/forma.py generate "ESP32 plant monitor with an OLED" --output forma-project.json
```

## Output integrity

Keep compiled JSON intact. Do not expose credentials. Do not claim that diagrams, prices, availability, compatibility, or clearances were physically verified unless returned evidence establishes that.
