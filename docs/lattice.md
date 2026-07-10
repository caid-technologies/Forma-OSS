# Lattice

Lattice is Blueprint's typed contract layer for composable domain agents.

Each meaningful project namespace can be represented as its own Lattice agent:

- `product.overview`
- `product.electrical`
- `product.bom`
- `product.mech`
- `product.firmware`
- `product.visuals`
- `product.validation`
- `product.assembly`
- `project.docs`
- `project.history`
- `project.meta`

`fabricator` follows the same pattern as a specialist namespace-style agent. It keeps the CLI/package name `fabricator`, but its Lattice card declares ownership of `product.fabricator`.

## Contract Shape

Every Lattice agent card describes:

- the namespace it owns
- the capability it exposes
- its input and output schema contract
- the tools it may need
- the handoff actions it can request
- safety and human-review boundaries

Blueprint remains the runtime boundary for provider selection, MCP/tool calls, logging, validation, persistence, and cross-namespace orchestration.
