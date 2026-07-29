"use client";

import { useEffect, useMemo, useRef } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  Node as FlowNode,
  NodeProps,
  Position,
  useEdgesState,
  useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Battery,
  Box,
  Cpu,
  Database,
  Monitor,
  Printer,
  Sliders,
  Volume2,
  Wrench,
} from "lucide-react";

type SchematicCanvasProps = {
  project: any;
};

type SchematicPin = {
  pin_id: string;
  name?: string;
  pin_type?: string;
  voltage?: number | null;
  connected?: boolean;
  netTypes?: string[];
};

type SchematicNodeData = {
  component: any;
  leftPins: SchematicPin[];
  rightPins: SchematicPin[];
  tone: {
    label: string;
    border: string;
    text: string;
    soft: string;
  };
  roleLabel: string;
  connectionSide: "left" | "right" | "both";
  isController: boolean;
};

type PlacementPoint = {
  x: number;
  y: number;
};

type SchematicGraph = {
  nodes: FlowNode<SchematicNodeData>[];
  edges: Edge[];
};

type CachedNodePosition = { x: number; y: number };

const MAX_SCHEMATIC_POSITION_CACHES = 24;
const schematicPositionCache = new Map<string, Map<string, CachedNodePosition>>();

function schematicProjectKey(project: any) {
  const explicitId = project?.project_id || project?.id || project?.assembly_metadata?.project_id;
  if (explicitId) return String(explicitId);
  const componentKey = (project?.components || [])
    .map((component: any) => component?.ref_des || component?.id || component?.name || "")
    .filter(Boolean)
    .join("|");
  return componentKey || "active-schematic";
}

function restoreNodePositions(nodes: FlowNode<SchematicNodeData>[], projectKey: string) {
  const cachedPositions = schematicPositionCache.get(projectKey);
  if (!cachedPositions) return nodes;
  return nodes.map((node) => {
    const position = cachedPositions.get(node.id);
    return position ? { ...node, position } : node;
  });
}

function cacheNodePositions(projectKey: string, nodes: FlowNode<SchematicNodeData>[]) {
  schematicPositionCache.delete(projectKey);
  schematicPositionCache.set(
    projectKey,
    new Map(nodes.map((node) => [node.id, { x: node.position.x, y: node.position.y }]))
  );
  while (schematicPositionCache.size > MAX_SCHEMATIC_POSITION_CACHES) {
    const oldestKey = schematicPositionCache.keys().next().value;
    if (typeof oldestKey !== "string") break;
    schematicPositionCache.delete(oldestKey);
  }
}

const schematicTones: Record<string, { label: string; border: string; text: string; soft: string }> = {
  microcontroller: { label: "MCU", border: "#22d3ee", text: "#a5f3fc", soft: "#082f49" },
  sensor: { label: "SENSOR", border: "#60a5fa", text: "#bfdbfe", soft: "#10233f" },
  actuator: { label: "ACTUATOR", border: "#fb923c", text: "#fed7aa", soft: "#3a1b0c" },
  power: { label: "POWER", border: "#facc15", text: "#fef08a", soft: "#352a08" },
  passives: { label: "MODULE", border: "#a78bfa", text: "#ddd6fe", soft: "#24163f" },
  communication: { label: "MODULE", border: "#a78bfa", text: "#ddd6fe", soft: "#24163f" },
  display: { label: "DISPLAY", border: "#f472b6", text: "#fbcfe8", soft: "#3a1230" },
  default: { label: "PART", border: "#94a3b8", text: "#cbd5e1", soft: "#1e293b" },
};

const schematicNodeTypes = {
  schematicPart: SchematicPartNode,
};

function iconForCategory(category = "") {
  const cat = category.toLowerCase();
  if (cat === "microcontroller") return Cpu;
  if (cat === "sensor") return Database;
  if (cat === "power") return Battery;
  if (cat === "display") return Monitor;
  if (cat === "actuator") return Volume2;
  if (cat === "passives") return Sliders;
  if (cat === "mechanical") return Wrench;
  if (cat === "3d print") return Printer;
  return Box;
}

function SchematicPartNode({ data }: NodeProps<SchematicNodeData>) {
  const { component, leftPins, rightPins, tone, roleLabel, connectionSide, isController } = data;
  const Icon = iconForCategory(component.category);
  const visibleLeftPins = leftPins.length ? leftPins : [];
  const visibleRightPins = rightPins.length ? rightPins : [];
  const modulePins = connectionSide === "left" ? visibleRightPins : visibleLeftPins;
  const modulePinSide = connectionSide === "left" ? "right" : "left";
  const visiblePinCount = visibleLeftPins.length + visibleRightPins.length;
  const partNumber = component.part_number || component.ref_des;
  const subtitle = component.category || component.part_type || roleLabel || tone.label;

  return (
    <div
      className={`schematic-node schematic-card ${isController ? "schematic-controller-card" : ""}`}
      style={{
        ["--schematic-accent" as string]: tone.border,
        ["--schematic-soft" as string]: tone.soft,
        ["--schematic-text" as string]: tone.text,
      }}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center border border-[var(--schematic-accent)] bg-[var(--schematic-soft)] text-[var(--schematic-text)]">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="text-[9px] font-black uppercase leading-none tracking-[0.16em] text-[var(--schematic-text)]">
              {roleLabel || tone.label}
            </div>
            <div className="h-px flex-1" style={{ backgroundColor: tone.border, opacity: 0.35 }} />
          </div>
          <div className="mt-1 truncate text-[13px] font-black leading-tight text-white">
            {component.name || component.ref_des}
          </div>
          <div className="mt-1 flex items-center gap-2 text-[8px] font-bold uppercase tracking-[0.08em] text-slate-500">
            <span className="truncate">{partNumber}</span>
            <span className="h-1 w-1 shrink-0 bg-slate-700" />
            <span className="shrink-0">{component.ref_des}</span>
          </div>
        </div>
      </div>

      {!isController && (
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#2b3038] pt-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
          <span className="truncate">{subtitle}</span>
          <span className="shrink-0 text-[var(--schematic-text)]">{visiblePinCount || 0} pins</span>
        </div>
      )}

      <div className={isController ? "mt-3 grid grid-cols-[1fr_72px_1fr] gap-2" : "mt-3"}>
        {isController && (
          <PinColumn componentRef={component.ref_des} pins={visibleLeftPins} side="left" tone={tone} />
        )}
        {isController && (
          <div className="flex min-h-[156px] flex-col items-center justify-center border border-[#334155] bg-[#0f1720] px-2 text-center">
            <Cpu className="mb-2 h-7 w-7 text-cyan-200" />
            <div className="text-[8px] font-black uppercase tracking-[0.12em] text-white">{component.ref_des}</div>
            <div className="mt-1 text-[7px] font-bold leading-tight text-slate-500">Controller</div>
          </div>
        )}
        {isController ? (
          <PinColumn componentRef={component.ref_des} pins={visibleRightPins} side="right" tone={tone} />
        ) : (
          <PinColumn
            componentRef={component.ref_des}
            pins={modulePins}
            side={modulePinSide}
            tone={tone}
            emptyLabel="No linked pins"
          />
        )}
      </div>
    </div>
  );
}

function PinColumn({
  componentRef,
  pins,
  side,
  tone,
  emptyLabel,
}: {
  componentRef: string;
  pins: SchematicPin[];
  side: "left" | "right";
  tone: SchematicNodeData["tone"];
  emptyLabel?: string;
}) {
  if (!pins.length) {
    return (
      <div className="border border-dashed border-[#333844] bg-[#101116] px-3 py-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-600">
        {emptyLabel || "No pins"}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {pins.map((pin) => {
        const handlePosition = side === "left" ? Position.Left : Position.Right;
        const handleStyle = side === "left" ? { left: -8, top: "50%" } : { right: -8, top: "50%" };
        return (
          <div
            key={`${side}-${pin.pin_id}`}
            className={`schematic-pin-row ${side === "left" ? "pl-2 text-left" : "pr-2 text-right"} ${pin.connected ? "schematic-pin-connected" : ""}`}
            title={`${pin.pin_id}${pin.name ? ` - ${pin.name}` : ""}${pin.voltage !== undefined && pin.voltage !== null ? ` / ${pin.voltage}V` : ""}`}
          >
            <Handle
              type="target"
              id={schematicHandleId(componentRef, pin.pin_id)}
              position={handlePosition}
              className="schematic-pin-handle"
              style={{
                ...handleStyle,
                ["--handle-border" as string]: tone.border,
                ["--handle-color" as string]: pin.connected ? tone.border : "#111216",
              }}
            />
            <Handle
              type="source"
              id={schematicHandleId(componentRef, pin.pin_id)}
              position={handlePosition}
              className="schematic-pin-handle"
              style={{
                ...handleStyle,
                ["--handle-border" as string]: tone.border,
                ["--handle-color" as string]: pin.connected ? tone.border : "#111216",
              }}
            />
            <span className="block truncate text-[8px] font-black uppercase leading-none text-white">{pin.pin_id}</span>
            {pin.name && (
              <span className="mt-0.5 block truncate text-[6px] font-bold uppercase leading-none text-slate-500">
                {pin.name}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function schematicToneForCategory(category = "") {
  return schematicTones[category.toLowerCase()] || schematicTones.default;
}

function pinKey(pin: SchematicPin) {
  return pin.pin_id;
}

function schematicHandleId(refDes: string, pinId: string) {
  return `${refDes}.${pinId}`;
}

function normalizeSchematicCategory(category = "") {
  const normalized = category.toLowerCase();
  if (normalized.includes("micro") || normalized.includes("controller") || normalized === "mcu") return "microcontroller";
  if (normalized.includes("sensor")) return "sensor";
  if (normalized.includes("display") || normalized.includes("screen") || normalized.includes("oled")) return "display";
  if (normalized.includes("actuator") || normalized.includes("motor") || normalized.includes("servo") || normalized.includes("relay")) return "actuator";
  if (normalized.includes("power") || normalized.includes("battery") || normalized.includes("regulator")) return "power";
  if (normalized.includes("comm") || normalized.includes("radio") || normalized.includes("wifi") || normalized.includes("ble")) return "communication";
  if (normalized.includes("passive") || normalized.includes("module") || normalized.includes("io")) return "passives";
  return normalized || "default";
}

function isControllerComponent(component: any) {
  const category = normalizeSchematicCategory(component?.category || "");
  const text = `${component?.name || ""} ${component?.part_number || ""} ${component?.ref_des || ""}`.toLowerCase();
  return (
    category === "microcontroller" ||
    /^u1$/i.test(component?.ref_des || "") ||
    /\b(esp32|arduino|pico|stm32|devkit|teensy|mcu|microcontroller)\b/.test(text)
  );
}

function schematicRoleLabel(component: any) {
  const category = normalizeSchematicCategory(component?.category || "");
  if (isControllerComponent(component)) return "ESP32 DevKit v1";
  if (category === "display") return "Display";
  if (category === "sensor") return "Sensor module";
  if (category === "actuator") return "Actuator / driver";
  if (category === "power") return "Power module";
  if (category === "communication") return "Comms";
  if (category === "passives") return "Module";
  return "Peripheral";
}

function primaryControllerLabel(project: any) {
  const parts = Array.isArray(project?.components) ? project.components : [];
  const controller = parts.find((component: any) => isControllerComponent(component));
  return controller?.part_number || controller?.name || controller?.ref_des || "Controller";
}

function pinSortScore(pin: SchematicPin) {
  const id = pin.pin_id.toLowerCase();
  const type = pin.pin_type?.toLowerCase() || "";
  if (/(vcc|vin|vbat|3v3|5v|12v|\+|pos)/.test(id) || type === "power") return `00-${id}`;
  if (/(gnd|ground|-|neg)/.test(id) || type === "ground") return `01-${id}`;
  if (/(sda|scl|i2c)/.test(id) || type === "i2c") return `02-${id}`;
  if (/(tx|rx|uart)/.test(id)) return `03-${id}`;
  if (/(sck|miso|mosi|cs|spi)/.test(id) || type === "spi") return `04-${id}`;
  if (/(pwm|sig|in|out|gpio|d\d+|a\d+)/.test(id)) return `05-${id}`;
  return `09-${id}`;
}

function sortSchematicPins(pins: SchematicPin[]) {
  return [...pins].sort(
    (a, b) =>
      pinSortScore(a).localeCompare(pinSortScore(b), undefined, { numeric: true }) ||
      pinKey(a).localeCompare(pinKey(b), undefined, { numeric: true })
  );
}

function splitControllerPins(pins: SchematicPin[]) {
  const sorted = sortSchematicPins(pins);
  const connected = sorted.filter((pin) => pin.connected);
  const rest = sorted.filter((pin) => !pin.connected);
  const ordered = [...connected, ...rest].slice(0, 28);
  const leftPins: SchematicPin[] = [];
  const rightPins: SchematicPin[] = [];
  ordered.forEach((pin, index) => {
    const id = pin.pin_id.toLowerCase();
    if (/(vcc|vin|3v3|5v|gnd|en|rst|reset|gpio0|d0|a0|sda|scl)/.test(id)) {
      leftPins.push(pin);
    } else if (/(tx|rx|mosi|miso|sck|cs|pwm|gpio|d\d+)/.test(id)) {
      rightPins.push(pin);
    } else if (leftPins.length <= rightPins.length) {
      leftPins.push(pin);
    } else {
      rightPins.push(pin);
    }
    if (Math.abs(leftPins.length - rightPins.length) > 4 && index > 6) {
      const source = leftPins.length > rightPins.length ? leftPins : rightPins;
      const target = leftPins.length > rightPins.length ? rightPins : leftPins;
      const moved = source.pop();
      if (moved) target.push(moved);
    }
  });
  return { leftPins, rightPins };
}

function schematicSideForComponent(component: any, counts: { left: number; right: number }) {
  const category = normalizeSchematicCategory(component?.category || "");
  if (["display", "sensor", "power"].includes(category)) return "left";
  if (["actuator", "communication", "passives"].includes(category)) return "right";
  return counts.left <= counts.right ? "left" : "right";
}

function schematicGridPosition(side: "left" | "right", index: number, rowsPerColumn: number): PlacementPoint {
  const row = index % rowsPerColumn;
  const column = Math.floor(index / rowsPerColumn);
  const rowGap = 126;
  const columnGap = 266;
  const top = 96;
  const innerLeftX = 320;
  const innerRightX = 910;
  return {
    x: side === "left" ? innerLeftX - column * columnGap : innerRightX + column * columnGap,
    y: top + row * rowGap,
  };
}

function normalizePlacement(value: any): PlacementPoint | null {
  if (!value || typeof value.x !== "number" || typeof value.y !== "number") return null;
  return { x: value.x, y: value.y };
}

function buildSchematicGraph(project: any): SchematicGraph {
  const newNodes: FlowNode<SchematicNodeData>[] = [];
  const newEdges: Edge[] = [];
  if (!project?.components) return { nodes: newNodes, edges: newEdges };

  const electricalParts = project.components.filter(
    (component: any) => !["mechanical", "3d print"].includes(component.category?.toLowerCase())
  );
  const electricalRefs = new Set(electricalParts.map((component: any) => component.ref_des));
  const componentByRef = new Map<string, any>(
    electricalParts.map((component: any) => [component.ref_des, component])
  );
  const pinMapByRef = new Map<string, Map<string, SchematicPin>>();
  const netTypesByPin = new Map<string, Set<string>>();

  electricalParts.forEach((component: any) => {
    const pinMap = new Map<string, SchematicPin>();
    (component.pins || []).forEach((pin: any) => {
      if (!pin?.pin_id) return;
      pinMap.set(pin.pin_id, {
        pin_id: pin.pin_id,
        name: pin.name,
        pin_type: pin.pin_type,
        voltage: pin.voltage,
      });
    });
    pinMapByRef.set(component.ref_des, pinMap);
  });

  (project.nets || []).forEach((net: any) => {
    (net.pins || []).forEach((pinRef: any) => {
      if (!electricalRefs.has(pinRef.ref_des)) return;
      const key = schematicHandleId(pinRef.ref_des, pinRef.pin_id);
      if (!netTypesByPin.has(key)) netTypesByPin.set(key, new Set());
      netTypesByPin.get(key)?.add(net.net_type || "default");
      const pinMap = pinMapByRef.get(pinRef.ref_des);
      if (!pinMap) return;
      const existing = pinMap.get(pinRef.pin_id);
      if (existing) {
        pinMap.set(pinRef.pin_id, {
          ...existing,
          connected: true,
          netTypes: Array.from(netTypesByPin.get(key) || []),
          pin_type: existing.pin_type || net.net_type,
          voltage: existing.voltage ?? net.voltage,
        });
        return;
      }
      pinMap.set(pinRef.pin_id, {
        pin_id: pinRef.pin_id,
        name: pinRef.pin_id,
        pin_type: net.net_type,
        voltage: net.voltage,
        connected: true,
        netTypes: Array.from(netTypesByPin.get(key) || []),
      });
    });
  });

  const schematicMeta = project.assembly_metadata?.schematic || {};
  const explicitPlacements = schematicMeta.placements || {};
  const controller =
    electricalParts.find((component: any) => isControllerComponent(component)) ||
    electricalParts.find((component: any) => String(component.ref_des || "").toUpperCase() === "U1") ||
    electricalParts[0];
  const sideCounts = { left: 0, right: 0 };
  const leftParts: any[] = [];
  const rightParts: any[] = [];

  electricalParts
    .filter((component: any) => component.ref_des !== controller?.ref_des)
    .forEach((component: any) => {
      const side = schematicSideForComponent(component, sideCounts);
      if (side === "left") {
        leftParts.push(component);
        sideCounts.left += 1;
      } else {
        rightParts.push(component);
        sideCounts.right += 1;
      }
    });

  const positionedParts = [
    ...leftParts.map((component, index) => ({ component, side: "left" as const, index })),
    ...(controller ? [{ component: controller, side: "both" as const, index: 0 }] : []),
    ...rightParts.map((component, index) => ({ component, side: "right" as const, index })),
  ];
  const sideRows = Math.min(6, Math.max(3, Math.ceil(Math.max(leftParts.length, rightParts.length, 1) / 2)));
  const controllerY = 118 + Math.max(0, sideRows - 4) * 42;

  positionedParts.forEach(({ component, side, index }) => {
    const category = normalizeSchematicCategory(component.category || "default");
    const placement = normalizePlacement(explicitPlacements[component.ref_des]);
    const isController = component.ref_des === controller?.ref_des;
    const allPins = sortSchematicPins(Array.from(pinMapByRef.get(component.ref_des)?.values() || []));
    const connectedPins = allPins.filter((pin) => pin.connected);
    const visiblePins = connectedPins.length ? connectedPins : allPins.slice(0, isController ? 18 : 4);
    const splitPins = isController
      ? splitControllerPins(visiblePins)
      : side === "left"
        ? { leftPins: [], rightPins: visiblePins }
        : { leftPins: visiblePins, rightPins: [] };
    const position =
      placement ||
      (isController
        ? { x: 596, y: controllerY }
        : schematicGridPosition(side === "left" ? "left" : "right", index, sideRows));

    newNodes.push({
      id: component.ref_des,
      type: "schematicPart",
      position,
      draggable: true,
      data: {
        component,
        leftPins: splitPins.leftPins,
        rightPins: splitPins.rightPins,
        tone: schematicToneForCategory(category),
        roleLabel: schematicRoleLabel(component),
        connectionSide: side,
        isController,
      },
      style: { background: "transparent", border: "none", width: isController ? 300 : 240 },
    });
  });

  const netStyles: Record<string, { color: string; dash?: string; width: number }> = {
    ground: { color: "#64748b", width: 1.8 },
    power: { color: "#ef4444", width: 2.2 },
    i2c: { color: "#0ea5e9", width: 2 },
    spi: { color: "#22c55e", width: 2 },
    uart: { color: "#ec4899", width: 2 },
    digital: { color: "#8b5cf6", width: 2 },
    analog: { color: "#eab308", width: 2 },
    pwm: { color: "#f97316", width: 2 },
    default: { color: "#14b8a6", width: 2 },
  };

  const pinTypeForRef = (pinRef: any) =>
    pinMapByRef.get(pinRef.ref_des)?.get(pinRef.pin_id)?.pin_type?.toLowerCase() || "";

  const chooseSourcePin = (net: any, usablePins: any[]) => {
    const netType = net.net_type?.toLowerCase() || "default";
    if (netType === "power" || netType === "ground") {
      return (
        usablePins.find(
          (pinRef: any) => componentByRef.get(pinRef.ref_des)?.category?.toLowerCase() === "power"
        ) ||
        usablePins.find((pinRef: any) => pinTypeForRef(pinRef) === netType) ||
        usablePins[0]
      );
    }
    return (
      usablePins.find(
        (pinRef: any) => componentByRef.get(pinRef.ref_des)?.category?.toLowerCase() === "microcontroller"
      ) || usablePins[0]
    );
  };

  const edgeLabel = (net: any, sourcePin: any, targetPin: any) => {
    const voltage = typeof net.voltage === "number" ? `${net.voltage}V` : net.net_type || "net";
    return `${net.name || net.net_id} / ${voltage} / ${sourcePin.pin_id}->${targetPin.pin_id}`;
  };

  (project.nets || []).forEach((net: any) => {
    const netType = net.net_type?.toLowerCase() || "default";
    const style = netStyles[netType] || netStyles.default;
    const usablePins = (net.pins || []).filter((pinRef: any) => electricalRefs.has(pinRef.ref_des));

    if (usablePins.length < 2) return;

    const sourcePin = chooseSourcePin(net, usablePins);
    usablePins
      .filter((targetPin: any) => targetPin !== sourcePin)
      .forEach((targetPin: any, index: number) => {
        const id = `edge_${net.net_id}_${sourcePin.ref_des}_${sourcePin.pin_id}_to_${targetPin.ref_des}_${targetPin.pin_id}_${index}`;

        newEdges.push({
          id,
          source: sourcePin.ref_des,
          sourceHandle: schematicHandleId(sourcePin.ref_des, sourcePin.pin_id),
          target: targetPin.ref_des,
          targetHandle: schematicHandleId(targetPin.ref_des, targetPin.pin_id),
          type: "smoothstep",
          animated: false,
          label: undefined,
          data: { label: edgeLabel(net, sourcePin, targetPin), net },
          style: {
            stroke: style.color,
            strokeWidth: style.width,
            opacity: 0.82,
            strokeDasharray: style.dash || "none",
          },
        });
      });
  });

  return { nodes: newNodes, edges: newEdges };
}

function SchematicLegend() {
  const wireRows = [
    { label: "VCC", color: "#ef4444", dash: "none" },
    { label: "GND", color: "#64748b", dash: "none" },
    { label: "I2C", color: "#0ea5e9", dash: "none" },
    { label: "DATA", color: "#8b5cf6", dash: "none" },
    { label: "PWM", color: "#f97316", dash: "none" },
  ];

  return (
    <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-[calc(100%-2rem)] border border-[#30343d] bg-[#15161b]/90 px-3 py-2 shadow-[0_16px_36px_rgba(0,0,0,0.28)] backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <div className="mr-1 text-[9px] font-black uppercase tracking-[0.18em] text-slate-500">Wires</div>
        {wireRows.map((wire) => (
          <div
            key={wire.label}
            className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-[0.08em]"
            style={{ color: wire.color }}
          >
            <svg width="24" height="8" viewBox="0 0 40 8" aria-hidden="true">
              <line
                x1="0"
                y1="4"
                x2="40"
                y2="4"
                stroke={wire.color}
                strokeWidth="3"
                strokeDasharray={wire.dash}
              />
            </svg>
            <span>{wire.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SchematicCanvas({ project }: SchematicCanvasProps) {
  const graph = useMemo(() => buildSchematicGraph(project), [project]);
  const projectKey = schematicProjectKey(project);
  const [nodes, setNodes, onNodesChange] = useNodesState<SchematicNodeData>(
    restoreNodePositions(graph.nodes, projectKey)
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);
  const appliedProjectRef = useRef(project);
  const nodesProjectKeyRef = useRef(projectKey);

  useEffect(() => {
    cacheNodePositions(nodesProjectKeyRef.current, nodes);
  }, [nodes]);

  useEffect(() => {
    if (appliedProjectRef.current === project) return;
    appliedProjectRef.current = project;
    nodesProjectKeyRef.current = projectKey;
    setNodes(restoreNodePositions(graph.nodes, projectKey));
    setEdges(graph.edges);
  }, [graph, project, projectKey, setEdges, setNodes]);

  return (
    <div className="flex h-full min-h-[620px] flex-col bg-[#111216]">
      <div className="flex min-h-[60px] flex-wrap items-center gap-3 border-b border-[#2a2c33] bg-[#17181d] px-4 py-3">
        <div className="mr-2 text-sm font-black text-white">Wiring diagram</div>
        <div className="inline-flex h-10 items-center gap-2 border border-[#3a3d46] bg-[#101116] px-3 text-xs font-black text-white">
          <Cpu className="h-4 w-4 text-slate-400" />
          <span>{primaryControllerLabel(project)}</span>
        </div>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={schematicNodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.16 }}
        minZoom={0.28}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        className="schematic-flow flex-1 bg-[#0f1014]"
      >
        <Background color="#262b33" gap={28} size={1.1} />
        <Controls
          position="bottom-right"
          className="!border !border-[#2f333c] !bg-[#15161b] !text-white"
        />
        <SchematicLegend />
      </ReactFlow>
    </div>
  );
}
