# Architecture

Blueprint OSS turns prompts into structured hardware projects using a sequential, validation-aware agent pipeline. The system is intentionally scoped to low-voltage maker electronics and emphasizes traceable, typed outputs.

## System pipeline
1. **Prompt + optional image** enters the system.
2. **Safety guardrails** block high-risk domains early (weapons, medical, mains AC, etc.).
3. **Model resolution** determines whether live Gemini generation runs or a deterministic simulation fallback is used.
4. **Intent Parser Agent** produces a high-level `ProjectOverview`.
5. **Requirements Agent** extracts functional requirements and constraints.
6. **Component Selection Agent** chooses parts from the seed database.
7. **Wiring/Netlist Agent** generates connection nets and pin mappings.
8. **Validation rules** run on the netlist.
9. **Repair loop** re-invokes the wiring agent if critical issues are found.
10. **BOM step** computes total cost deterministically.
11. **Mechanical/Fabrication Agent** drafts enclosure notes and (optionally) placements.
12. **Assembly Instruction Agent** emits step-by-step build guidance.
13. **Post-processing** enriches missing mechanical placements for the 3D viewer.
14. **Hardware IR** is stored in the database and rendered in the UI.

## Orchestration and model runtime
- The backend runs an **ADK-style sequential workflow** implemented in `backend/agents/orchestrator.py`.
- **Gemini (google-genai)** is used for structured JSON output when `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is configured.
- Default model configuration targets **Gemini 3.5 Flash** (`GEMINI_MODEL=gemini-3.5-flash`) with a fallback to **Gemini 2.5 Flash** (`GEMINI_FALLBACK_MODEL=gemini-2.5-flash`).
- With `STRICT_GEMINI=true` (default), the backend fails fast when the requested model is unavailable.
- With `STRICT_GEMINI=false`, the backend may switch to the fallback model.
- If no API key is configured (or generation errors), the backend uses a deterministic simulation fallback backed by curated example projects.

## System diagram
```mermaid
flowchart TD
  A[Prompt + optional image] --> S[Safety guardrails]
  S --> M[Model resolution\n(live Gemini vs simulation)]
  M --> B[Intent Parser Agent]
  B --> C[Requirements Agent]
  C --> D[Component Selection Agent]
  D --> E[Wiring/Netlist Agent]
  E --> F[Rule-based Validation]
  F -->|critical issues| E
  F --> G[BOM + Mechanical/Fabrication Agent]
  G --> H[Assembly Instruction Agent]
  H --> P[Mechanical render enrichment]
  P --> I[Typed Hardware IR]
  I --> J[UI: React Flow + SVG + Mermaid + 3D mech]
  I --> K[(Project database)]
```

## Core subsystems
- **Frontend (Next.js + React Flow):** Visualizes the structured project, nets, BOM, and instructions.
- **Backend (FastAPI):** Hosts the orchestration layer, validation, and storage APIs.
- **Database (Postgres/SQLite):** Stores component templates and generated projects.
- **Utilities:** Render Mermaid and SVG schematics from the IR.

## Output artifacts
- **Hardware IR JSON** (typed source of truth)
- **React Flow schematic** (interactive wiring view)
- **SVG schematic** (static vector view)
- **Mermaid diagram** (lightweight topology graph)
- **BOM + assembly steps**
