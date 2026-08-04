---
name: forma-hardware
description: Generates and validates structured low-voltage maker-electronics projects with Forma, including Hardware IR, BOMs, wiring nets, diagrams, assembly steps, and optional concept images. Use when a user asks to design, compile, inspect, or electrically validate a safe 3.3V-5V hardware prototype with Forma.
---

# Forma Hardware

Use Forma as the hardware compiler. Do not invent a successful generation or validation result when Forma is unavailable.

## Connect

Use the bundled dependency-free client. Resolve `<skill-directory>` to the directory containing this `SKILL.md`; do not assume the current working directory is the skill directory. The client reads `FORMA_MCP_URL` and defaults to `http://127.0.0.1:8000/mcp`.

```bash
python <skill-directory>/scripts/forma.py tools
```

If the server requires authentication, have the user set `FORMA_AUTH_TOKEN`; never place the token in a command or output. Read [references/configuration.md](references/configuration.md) when connection, authentication, or server startup fails.

## Generate a project

1. Confirm the request is a low-voltage educational or maker project. Decline requests involving weapons, critical medical or life-support devices, mains AC, automotive control, or unsafe high-power batteries.
2. Ask a follow-up question only when a missing constraint would materially change the design. Otherwise preserve the user's stated power, size, budget, environment, interfaces, and component preferences in the prompt.
3. Run:

```bash
python <skill-directory>/scripts/forma.py generate "<complete hardware brief>" --output forma-project.json
```

Use `--workflow web_research` only when the user needs sourced component research and the Forma server has Firecrawl configured. Add `--generate-image` only when the user explicitly wants a concept image. Add `--image-file <path>` when a reference image is part of the request.

4. Inspect the returned `project_ir`, especially `overview`, `requirements`, `components`, `nets`, `validation`, `bom`, `assembly_steps`, and `assembly_metadata`.
5. Report the artifact path, the design summary, unresolved warnings, and whether electrical validation passed. Clearly label the output as a prototype plan, not fabrication-ready engineering approval.

## Validate an existing project

Run validation after changing components or nets and before presenting the result as complete:

```bash
python <skill-directory>/scripts/forma.py validate forma-project.json --output validation.json
```

Treat every `CRITICAL` issue as blocking. Report warnings rather than silently discarding them. If the input is not a Forma response or Hardware IR object, explain the schema problem and ask for components and nets.

## Inspect server state and jobs

Use these only when they help answer the user's request:

```bash
python <skill-directory>/scripts/forma.py config
python <skill-directory>/scripts/forma.py job <job-id>
python <skill-directory>/scripts/forma.py jobs --status succeeded --limit 10
```

Do not expose provider credentials, authorization headers, or unredacted debug secrets. Prefer the returned structured JSON over parsing the human-readable text content.

## Output contract

Keep Forma output intact when saving JSON. In the user-facing response include:

- Project title and goal
- Power assumptions and major components
- Validation status and remaining issues
- Saved artifact paths
- Any unavailable optional outputs, such as product imagery or web research

Do not claim that generated diagrams, BOM availability, pricing, or component compatibility have been physically verified unless the returned data explicitly establishes it.
