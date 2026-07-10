# Fabricator

Fabricator is the workspace area for predicting how products can be fabricated from primitive inputs across chemistry, biotechnology, material science, and life science domains.

## MVP Direction

Fabricator can use Blueprint as its first MVP server. The initial implementation should expose Fabricator workflows through the existing Blueprint backend/runtime surfaces instead of starting a separate service.

LLM access should also go through Blueprint's provider interfaces. Fabricator should treat Blueprint as the boundary for model selection, prompt execution, streaming, logging, validation, and provider configuration so it can reuse the existing OpenAI, RunPod, Baseten, NVIDIA, simulation, and OpenAI-compatible paths.

## Human-Computer Interaction

Fabricator should feel like a question-driven fabrication copilot rather than a raw model endpoint. People should be able to describe available primitives, desired products, constraints, and equipment access in natural language, then receive structured fabrication options that can be inspected, compared, refined, and handed to Blueprint workflows.

The first interface can be conversational, with Blueprint providing the server, model routing, streaming responses, validation, logging, and MCP/tool access. Over time, the same interaction model can support forms, dashboards, route graphs, inventory views, device status panels, and protocol review queues.

Useful questions Fabricator can ask include:

- We have excess `{material}`. What product families, devices, components, reagents, biomaterials, or formulations could it support?
- Given `{primitive}` and `{target_product}`, what candidate fabrication routes exist, and what assumptions does each route make?
- Which instruments, lab devices, automation systems, CAD/CAM tools, LIMS, ELN, databases, or external services would this workflow need to interface with?
- What additional primitives, catalysts, organisms, substrates, consumables, process conditions, or quality checks are missing?
- Which route is most feasible under `{budget}`, `{timeline}`, `{safety_constraints}`, `{regulatory_context}`, and `{available_equipment}`?
- What measurements, assays, simulations, or validation checks should be requested before committing to a route?
- What parts of this plan require human review before execution because of safety, biosecurity, compliance, or irreversible physical actions?
- What should Blueprint MCP call next: inventory lookup, device capability discovery, literature search, schema validation, simulation, job creation, or status monitoring?

This is why Fabricator needs the Blueprint MCP server. MCP gives the conversational planner a controlled way to discover tools, inspect resources, call external systems, and coordinate fabrication workflows without hard-coding every device or provider inside Fabricator.

## Scope

- Map products to candidate primitives such as ingredients, organisms, materials, reagents, process units, and environmental conditions.
- Model fabrication routes including synthesis, formulation, growth, assembly, purification, finishing, and quality-control steps.
- Capture constraints such as yield, cost, safety, biocompatibility, manufacturability, sustainability, and regulatory boundaries.
- Provide room for predictors, domain schemas, examples, validation datasets, and evaluation reports.
- Integrate with Blueprint server routes and LLM orchestration before introducing Fabricator-specific infrastructure.

## Suggested Layout

This directory starts intentionally small. Likely next additions are:

- `main.py` for a runnable sample of Blueprint-backed Fabricator planning.
- `schemas/` for product, primitive, and process definitions.
- `predictors/` for route-planning and fabrication prediction models.
- `examples/` for domain-specific fabrication scenarios.
- `tests/` for fixtures and regression coverage.

## Sample Usage

Generate a local plan without calling a live model:

```bash
python -m fabricator plan
```

Run the same flow through Blueprint's configured LLM provider:

```bash
python -m fabricator plan --live --provider runpod --material "cellulose acetate offcuts"
```

Inspect tools through Blueprint's MCP handler:

```bash
python -m fabricator mcp-tools
```

Expose Fabricator as a Lattice domain-agent card for other agents:

```bash
python -m fabricator card
```

Generate a plan and write a JSON artifact:

```bash
python -m fabricator plan --material "cellulose acetate offcuts" --include-mcp-tools --output fabricator/results/sample-plan.json
```

Use a running Blueprint backend instead of the in-process handler:

```bash
python -m fabricator mcp-tools --mcp-url http://127.0.0.1:8000/mcp
```
