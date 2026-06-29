# Agents

Blueprint uses an **ADK-style** sequential multi-agent workflow (implemented in `backend/agents/orchestrator.py`). Each agent consumes the prior agent’s output and writes structured data into the Hardware IR.

## Pipeline overview
0. Safety guardrails → 0.5 Optional Firecrawl MCP design research → 1. Intent Parser → 2. Requirements → 3. Component Selection → 4. Wiring/Netlist (+ repair loop) → 5. BOM → 6. Mechanical/Fabrication → 7. Assembly Instructions → 8. Mechanical render enrichment

## Agent responsibilities

### Safety Guardrail (pre-check)
**Input:** Prompt
**Output:** Either a normal pipeline run, or a safety-blocked Hardware IR
**Goal:** Block high-risk categories early (weapons, medical, mains AC, automotive control, high-power battery packs).

### Intent Parser Agent
**Input:** Prompt (+ optional image)  
**Output:** `ProjectOverview`  
**Goal:** Convert intent into a concise, high-level project summary.

### Design Research Agent (optional Firecrawl MCP pre-step)
**Input:** Prompt  
**Output:** Research context in `assembly_metadata.design_research` and prompt context for downstream agents  
**Goal:** Find reference designs, common module/BOM patterns, and CAD/enclosure hints.

This step is enabled with `DESIGN_RESEARCH_ENABLED=true`. It uses Firecrawl MCP search results as evidence, not as trusted electrical schema. Component selection is still instructed to instantiate only part numbers that exactly match the local component template database.

### Requirements Agent
**Input:** Prompt + `ProjectOverview`  
**Output:** `FunctionalRequirements`  
**Goal:** Extract functional requirements, power needs, constraints, and missing info.

### Component Selection Agent
**Input:** Requirements + seed component database + optional design research context  
**Output:** `ComponentInstance[]`  
**Goal:** Choose compatible parts and instantiate the BOM with pinouts.

### Wiring/Netlist Agent
**Input:** Components + requirements  
**Output:** `ConnectionNet[]` + `PinMappingEntry[]`  
**Goal:** Wire pins into power, ground, and signal nets.

If validation produces CRITICAL issues, the orchestrator runs a one-step **auto-correction** prompt and re-validates.

### BOM Agent
**Input:** Component list  
**Output:** Updated `ProjectOverview.estimated_cost`  
**Goal:** Calculate total cost from unit prices and quantities (deterministic step).

### Mechanical/Fabrication Agent
**Input:** Overview + components  
**Output:** `MechanicalNotes`  
**Goal:** Suggest enclosure type, mounting, and fabrication details.

The agent may also emit `render_dimensions`, `component_placements`, and `spatial_relationships` for the 3D viewer.

### Assembly Instruction Agent
**Input:** Overview + components + nets + mechanical notes  
**Output:** `AssemblyStep[]`  
**Goal:** Produce step-by-step build instructions with safety flags.

## State transitions
```mermaid
flowchart LR
  A[Prompt] --> R[Optional Design Research]
  R --> B[ProjectOverview]
  B --> C[FunctionalRequirements]
  C --> D[ComponentInstance[]]
  D --> E[ConnectionNet[] + PinMappingEntry[]]
  E --> F[Validation + repair loop]
  F --> G[MechanicalNotes]
  G --> H[AssemblyStep[]]
  H --> I[Hardware IR]
```

## Notes
- Agents run **sequentially** for determinism and traceability.
- Validation can trigger a **repair loop** that re-invokes the wiring agent.
- If a live LLM provider isn’t configured (or generation fails), the backend uses a deterministic **simulation fallback** backed by the example projects.
- The pipeline is designed to swap models or add agents without rewriting the core IR schema.
- External agents can call or listen to Blueprint through the A2A layer documented in `docs/a2a.md`.

## Chat revisions
Existing projects use a separate **Project Revision Agent**. It consumes the current Hardware IR, the user's chat message, optional Firecrawl research context, and the trusted component catalog, then returns a complete revised Hardware IR. The backend reruns validation, increments `assembly_metadata.revision`, appends `project_version_history`, stores chat messages in `assembly_metadata.chat_history`, and persists the updated project row.
