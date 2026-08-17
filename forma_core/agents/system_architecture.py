"""System-tree construction and detail-scoped prompt context helpers."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from forma_core.workspaces.projects.models import (
    ComponentInstance,
    FunctionalRequirements,
    ProjectOverview,
    SystemArchitecture,
    SystemInterface,
    SystemNode,
)


_SYSTEM_NODE_FIELD_NAMES = {
    "system_id",
    "name",
    "domain",
    "purpose",
    "responsibilities",
    "constraints",
    "expected_component_roles",
    "interfaces",
    "connects_to",
    "detail_owner",
    "children",
}


def architecture_tree_is_usable(architecture: SystemArchitecture) -> bool:
    """Reject provider output that flattened recursive JSON fields into child IDs."""
    seen: set[str] = set()
    node_count = 0

    def visit(node: SystemNode) -> bool:
        nonlocal node_count
        node_count += 1
        system_id = node.system_id.strip().lower()
        if not system_id or system_id in _SYSTEM_NODE_FIELD_NAMES or system_id in seen:
            return False
        seen.add(system_id)
        if node_count > 64:
            return False
        return all(visit(child) for child in node.children)

    return visit(architecture.root)


def compact_component_catalog(catalog: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe selectable parts without spending prompt context on physical pins."""
    compact: list[dict[str, Any]] = []
    for item in catalog:
        pins = item.get("pins") or []
        interfaces = sorted(
            {
                str(pin.get("pin_type") or "").strip()
                for pin in pins
                if isinstance(pin, dict) and str(pin.get("pin_type") or "").strip()
            }
        )
        compact.append(
            {
                "part_number": item.get("part_number"),
                "name": item.get("name"),
                "category": item.get("category"),
                "description": item.get("description"),
                "price": item.get("price", 0.0),
                "sourcing_url": item.get("sourcing_url"),
                "use_cases": item.get("use_cases") or [],
                "pin_count": len(pins),
                "available_interfaces": interfaces,
            }
        )
    return compact


def hydrate_catalog_components(
    selected: Iterable[ComponentInstance],
    catalog: Iterable[dict[str, Any]],
) -> list[ComponentInstance]:
    """Restore canonical catalog metadata and pins after high-level part selection."""
    templates = {str(item.get("part_number")): item for item in catalog if item.get("part_number")}
    hydrated: list[ComponentInstance] = []
    for component in selected:
        template = templates.get(component.part_number)
        if not template:
            hydrated.append(component)
            continue
        hydrated.append(
            ComponentInstance(
                ref_des=component.ref_des,
                part_number=component.part_number,
                name=str(template.get("name") or component.name),
                category=str(template.get("category") or component.category),
                quantity=component.quantity,
                unit_price=float(template.get("price") or 0.0),
                sourcing_url=template.get("sourcing_url"),
                rationale=component.rationale,
                pins=template.get("pins") or [],
            )
        )
    return hydrated


def compact_component_context(components: Iterable[ComponentInstance]) -> list[dict[str, Any]]:
    """Return component identity and purpose while deliberately excluding pin definitions."""
    return [
        {
            "ref_des": component.ref_des,
            "part_number": component.part_number,
            "name": component.name,
            "category": component.category,
            "quantity": component.quantity,
            "rationale": component.rationale,
        }
        for component in components
    ]


def compact_net_context(nets: Iterable[Any]) -> list[dict[str, Any]]:
    """Keep system connectivity but hide individual pin IDs from non-wiring agents."""
    result: list[dict[str, Any]] = []
    for net in nets:
        refs: list[str] = []
        for pin in net.pins:
            if pin.ref_des not in refs:
                refs.append(pin.ref_des)
        result.append(
            {
                "net_id": net.net_id,
                "name": net.name,
                "net_type": net.net_type,
                "voltage": net.voltage,
                "component_refs": refs,
            }
        )
    return result


def find_system_node(architecture: SystemArchitecture, system_id: str) -> Optional[SystemNode]:
    target = system_id.strip().lower()

    def visit(node: SystemNode) -> Optional[SystemNode]:
        normalized_id = node.system_id.lower()
        if normalized_id == target or normalized_id.endswith(f".{target}"):
            return node
        for child in node.children:
            found = visit(child)
            if found:
                return found
        return None

    exact_or_suffix = visit(architecture.root)
    if exact_or_suffix:
        return exact_or_suffix

    def visit_domain(node: SystemNode) -> Optional[SystemNode]:
        if node.domain.strip().lower() == target and node.children:
            return node
        for child in node.children:
            found = visit_domain(child)
            if found:
                return found
        return None

    return visit_domain(architecture.root)


def system_context(architecture: SystemArchitecture, system_id: Optional[str] = None) -> dict[str, Any]:
    """Project only the requested architecture branch into an agent prompt."""
    node = find_system_node(architecture, system_id) if system_id else architecture.root
    if node is None:
        node = architecture.root
    return {"summary": architecture.summary, "system": node.model_dump()}


def build_default_system_architecture(
    overview: ProjectOverview,
    requirements: FunctionalRequirements,
    components: Iterable[ComponentInstance] = (),
) -> SystemArchitecture:
    """Produce a useful tree for simulations, legacy projects, and provider fallbacks."""
    components = list(components)
    categories = {component.category.strip().lower() for component in components}
    requirement_text = " ".join(requirements.requirements).lower()
    has_controller = not components or any("microcontroller" in category or "sbc" in category for category in categories)
    has_sensing = any("sensor" in category for category in categories) or any(
        word in requirement_text for word in ("sense", "measure", "detect", "monitor")
    )
    has_output = any("actuator" in category or "display" in category for category in categories) or any(
        word in requirement_text for word in ("display", "control", "move", "alert", "audio")
    )

    electrical_children = [
        SystemNode(
            system_id="electrical.power",
            name="Power System",
            domain="electrical",
            purpose="Safely converts and distributes energy at the voltages every other system requires.",
            responsibilities=["Accept the selected power source", "Regulate and protect power rails", "Provide a common reference"],
            constraints=[requirements.power_needs, f"Primary logic voltage: {requirements.operating_voltage} V"],
            expected_component_roles=["power source", "regulator or protection", "connectors"],
            interfaces=[SystemInterface(name="Power rails", connects_to="electrical.control", purpose="Supplies regulated energy and ground")],
            detail_owner="power/electrical agent",
        )
    ]
    if has_controller:
        electrical_children.append(
            SystemNode(
                system_id="electrical.control",
                name="Control and Compute System",
                domain="electrical",
                purpose="Coordinates sensing, decisions, communication, and outputs without exposing pin assignments at architecture level.",
                responsibilities=["Run control logic", "Coordinate peripheral interfaces", "Expose programming and diagnostics"],
                expected_component_roles=["controller", "programming interface"],
                interfaces=[SystemInterface(name="Logical control", connects_to="firmware.control", purpose="Provides hardware resources to firmware")],
                detail_owner="control electronics agent",
            )
        )
    if has_sensing:
        electrical_children.append(
            SystemNode(
                system_id="electrical.sensing",
                name="Sensing and Input System",
                domain="electrical",
                purpose="Converts user or environmental conditions into information the controller can use.",
                responsibilities=["Acquire required inputs", "Condition or digitize signals", "Report reliable measurements"],
                expected_component_roles=["sensors", "input controls", "signal conditioning"],
                interfaces=[SystemInterface(name="Sensor data", connects_to="electrical.control", purpose="Carries measurements and input state")],
                detail_owner="sensing agent",
            )
        )
    if has_output:
        electrical_children.append(
            SystemNode(
                system_id="electrical.outputs",
                name="Output and Actuation System",
                domain="electrical",
                purpose="Turns controller decisions into visible, audible, or physical results.",
                responsibilities=["Drive required outputs", "Isolate higher-current loads", "Provide user feedback"],
                expected_component_roles=["display or indicators", "actuators", "drivers"],
                interfaces=[SystemInterface(name="Commands and feedback", connects_to="electrical.control", purpose="Receives commands and reports state")],
                detail_owner="output/actuation agent",
            )
        )

    mechanical = SystemNode(
        system_id="mechanical",
        name="Mechanical Systems",
        domain="mechanical",
        purpose="Turns the electronics into a durable, manufacturable object with safe access and correct physical relationships.",
        responsibilities=["Protect the product", "Locate parts", "Support fabrication and service"],
        detail_owner="mechanical architect",
        children=[
            SystemNode(
                system_id="mechanical.enclosure",
                name="Enclosure and Protection System",
                domain="mechanical",
                purpose="Protects users and components while providing the external form and required openings.",
                responsibilities=["Define the outer shell", "Provide access and ventilation", "Meet environmental constraints"],
                constraints=requirements.physical_constraints,
                expected_component_roles=["shell", "covers", "seals or vents"],
                interfaces=[SystemInterface(name="Physical envelope", connects_to="electrical", purpose="Contains and protects electrical systems")],
                detail_owner="enclosure agent",
            ),
            SystemNode(
                system_id="mechanical.mounting",
                name="Mounting and Structure System",
                domain="mechanical",
                purpose="Keeps boards, batteries, sensors, and actuators aligned under handling and operating loads.",
                responsibilities=["Retain components", "Maintain clearances", "Provide fasteners and assembly order"],
                expected_component_roles=["mounts", "standoffs", "fasteners"],
                interfaces=[SystemInterface(name="Mounting features", connects_to="electrical", purpose="Locates each electrical subsystem")],
                detail_owner="mechanical integration agent",
            ),
        ],
    )

    children = [
        SystemNode(
            system_id="electrical",
            name="Electrical Systems",
            domain="electrical",
            purpose="Provides power, information flow, control, and physical outputs for the product.",
            responsibilities=["Power distribution", "Signal flow", "Control and I/O"],
            detail_owner="electrical architect",
            children=electrical_children,
        ),
        mechanical,
    ]
    if has_controller:
        children.append(
            SystemNode(
                system_id="firmware",
                name="Firmware Systems",
                domain="firmware",
                purpose="Implements product behavior while depending on abstract hardware interfaces instead of raw pin details.",
                responsibilities=["Initialize hardware", "Run control behavior", "Handle faults and user interaction"],
                detail_owner="firmware architect",
                children=[
                    SystemNode(
                        system_id="firmware.control",
                        name="Control Logic",
                        domain="firmware",
                        purpose="Coordinates product states, inputs, outputs, and safe failure behavior.",
                        responsibilities=["State management", "Input processing", "Output commands", "Fault handling"],
                        expected_component_roles=["hardware abstraction layer", "application state machine"],
                        detail_owner="firmware agent",
                    )
                ],
            )
        )

    return SystemArchitecture(
        summary=f"{overview.title} is divided into discipline-level systems so each specialist receives only the context it owns.",
        root=SystemNode(
            system_id="product",
            name=overview.title,
            domain="product",
            purpose=overview.description,
            responsibilities=requirements.requirements,
            constraints=requirements.physical_constraints,
            detail_owner="system architect",
            children=children,
        ),
    )


def ensure_system_architecture(ir: Any) -> Any:
    if not getattr(ir, "system_architecture", None) and getattr(ir, "overview", None) and getattr(ir, "requirements", None):
        ir.system_architecture = build_default_system_architecture(ir.overview, ir.requirements, ir.components)
    return ir


__all__ = [
    "build_default_system_architecture",
    "compact_component_catalog",
    "compact_component_context",
    "compact_net_context",
    "ensure_system_architecture",
    "find_system_node",
    "hydrate_catalog_components",
    "system_context",
]
