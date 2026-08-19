"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  X,
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
  allPins: SchematicPin[];
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

const schematicAccent = {
  cyan: "rgb(var(--forma-cyan-rgb))",
  green: "rgb(var(--forma-green-rgb))",
  yellow: "rgb(var(--forma-yellow-rgb))",
  red: "rgb(var(--forma-red-rgb))",
  violet: "rgb(var(--forma-violet-rgb))",
  muted: "var(--forma-text-muted)",
} as const;

const schematicTones: Record<string, { label: string; border: string; text: string; soft: string }> = {
  microcontroller: { label: "MCU", border: schematicAccent.cyan, text: schematicAccent.cyan, soft: "rgb(var(--forma-cyan-rgb) / 0.1)" },
  sensor: { label: "SENSOR", border: schematicAccent.green, text: schematicAccent.green, soft: "rgb(var(--forma-green-rgb) / 0.1)" },
  actuator: { label: "ACTUATOR", border: schematicAccent.yellow, text: schematicAccent.yellow, soft: "rgb(var(--forma-yellow-rgb) / 0.1)" },
  power: { label: "POWER", border: schematicAccent.yellow, text: schematicAccent.yellow, soft: "rgb(var(--forma-yellow-rgb) / 0.1)" },
  passives: { label: "MODULE", border: schematicAccent.violet, text: schematicAccent.violet, soft: "rgb(var(--forma-violet-rgb) / 0.1)" },
  communication: { label: "MODULE", border: schematicAccent.violet, text: schematicAccent.violet, soft: "rgb(var(--forma-violet-rgb) / 0.1)" },
  display: { label: "DISPLAY", border: schematicAccent.violet, text: schematicAccent.violet, soft: "rgb(var(--forma-violet-rgb) / 0.1)" },
  default: { label: "PART", border: "var(--forma-border)", text: schematicAccent.muted, soft: "var(--forma-surface-muted)" },
};

const schematicNetStyles: Record<string, { color: string; dash?: string; width: number }> = {
  ground: { color: schematicAccent.muted, width: 1.8 },
  power: { color: schematicAccent.red, width: 2.2 },
  i2c: { color: schematicAccent.cyan, width: 2 },
  spi: { color: schematicAccent.green, width: 2 },
  uart: { color: schematicAccent.violet, width: 2 },
  digital: { color: schematicAccent.violet, width: 2 },
  analog: { color: schematicAccent.yellow, width: 2 },
  pwm: { color: schematicAccent.yellow, width: 2 },
  default: { color: schematicAccent.cyan, width: 2 },
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
  return <SchematicPartCard data={data} />;
}

function SchematicPartCard({ data, viewMode = false }: { data: SchematicNodeData; viewMode?: boolean }) {
  const { component, leftPins, rightPins, tone, roleLabel, connectionSide, isController } = data;
  const Icon = iconForCategory(component.category);
  const expandedPins = viewMode && data.allPins.length ? data.allPins : undefined;
  const expandedPinColumns = expandedPins
    ? isController
      ? splitControllerPins(expandedPins, expandedPins.length)
      : connectionSide === "left"
        ? { leftPins: [], rightPins: expandedPins }
        : { leftPins: expandedPins, rightPins: [] }
    : undefined;
  const visibleLeftPins = expandedPinColumns?.leftPins || leftPins;
  const visibleRightPins = expandedPinColumns?.rightPins || rightPins;
  const modulePins = connectionSide === "left" ? visibleRightPins : visibleLeftPins;
  const modulePinSide = connectionSide === "left" ? "right" : "left";
  const visiblePinCount = visibleLeftPins.length + visibleRightPins.length;
  const partNumber = component.part_number || component.ref_des;
  const subtitle = component.category || component.part_type || roleLabel || tone.label;

  return (
    <div
      className={`schematic-node schematic-card ${isController ? "schematic-controller-card" : ""} ${viewMode ? "schematic-view-card" : ""}`}
      style={{
        ["--schematic-accent" as string]: tone.border,
        ["--schematic-soft" as string]: tone.soft,
        ["--schematic-text" as string]: tone.text,
      }}
    >
      <div className={`flex items-start ${viewMode ? "gap-4" : "gap-3"}`}>
        <div
          className={`flex shrink-0 items-center justify-center rounded-md border border-[var(--schematic-accent)] bg-[var(--schematic-soft)] text-[var(--schematic-text)] ${viewMode ? "h-14 w-14" : "h-9 w-9"}`}
        >
          <Icon className={viewMode ? "h-6 w-6" : "h-4 w-4"} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className={`${viewMode ? "text-[11px]" : "text-[9px]"} font-medium uppercase leading-none tracking-[0.14em] text-[var(--schematic-text)]`}>
              {roleLabel || tone.label}
            </div>
            <div className="h-px flex-1 bg-[var(--schematic-accent)] opacity-35" />
          </div>
          <div className={`${viewMode ? "mt-2 break-words text-xl" : "mt-1 truncate text-[13px]"} font-semibold leading-tight tracking-tight text-[var(--forma-text-strong)]`}>
            {component.name || component.ref_des}
          </div>
          <div className={`mt-1 flex items-center gap-2 font-medium uppercase tracking-[0.08em] text-[var(--forma-text-muted)] ${viewMode ? "text-[10px]" : "text-[8px]"}`}>
            <span className="truncate">{partNumber}</span>
            <span className="h-1 w-1 shrink-0 rounded-full bg-[var(--forma-text-muted)]" />
            <span className="shrink-0">{component.ref_des}</span>
          </div>
        </div>
      </div>

      {!isController && (
        <div className={`${viewMode ? "mt-5 pt-3 text-[11px]" : "mt-3 pt-2 text-[9px]"} flex items-center justify-between gap-2 border-t border-[var(--forma-border)] font-medium uppercase tracking-[0.12em] text-[var(--forma-text-muted)]`}>
          <span className="truncate">{subtitle}</span>
          <span className="shrink-0 text-[var(--schematic-text)]">{visiblePinCount || 0} pins</span>
        </div>
      )}

      <div
        className={
          isController
            ? `${viewMode ? "mt-5 grid-cols-[minmax(0,1fr)_96px_minmax(0,1fr)] gap-3" : "mt-3 grid-cols-[1fr_72px_1fr] gap-2"} grid`
            : viewMode
              ? "mt-5"
              : "mt-3"
        }
      >
        {isController && (
          <PinColumn
            componentRef={component.ref_des}
            pins={visibleLeftPins}
            side="left"
            tone={tone}
            viewMode={viewMode}
          />
        )}
        {isController && (
          <div className={`flex flex-col items-center justify-center rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-2 text-center ${viewMode ? "min-h-[230px]" : "min-h-[156px]"}`}>
            <Cpu className={`mb-2 text-[rgb(var(--forma-cyan-rgb))] ${viewMode ? "h-10 w-10" : "h-7 w-7"}`} />
            <div className={`${viewMode ? "text-xs" : "text-[8px]"} font-semibold uppercase tracking-[0.12em] text-[var(--forma-text-strong)]`}>{component.ref_des}</div>
            <div className={`mt-1 font-medium leading-tight text-[var(--forma-text-muted)] ${viewMode ? "text-[9px]" : "text-[7px]"}`}>Controller</div>
          </div>
        )}
        {isController ? (
          <PinColumn
            componentRef={component.ref_des}
            pins={visibleRightPins}
            side="right"
            tone={tone}
            viewMode={viewMode}
          />
        ) : (
          <PinColumn
            componentRef={component.ref_des}
            pins={modulePins}
            side={modulePinSide}
            tone={tone}
            emptyLabel="No linked pins"
            viewMode={viewMode}
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
  viewMode = false,
}: {
  componentRef: string;
  pins: SchematicPin[];
  side: "left" | "right";
  tone: SchematicNodeData["tone"];
  emptyLabel?: string;
  viewMode?: boolean;
}) {
  if (!pins.length) {
    return (
      <div className={`rounded-md border border-dashed border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 font-medium uppercase tracking-[0.12em] text-[var(--forma-text-muted)] ${viewMode ? "py-4 text-[11px]" : "py-2 text-[9px]"}`}>
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
            {!viewMode && (
              <>
                <Handle
                  type="target"
                  id={schematicHandleId(componentRef, pin.pin_id)}
                  position={handlePosition}
                  className="schematic-pin-handle"
                  style={{
                    ...handleStyle,
                    ["--handle-border" as string]: tone.border,
                    ["--handle-color" as string]: pin.connected ? tone.border : "var(--forma-surface)",
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
                    ["--handle-color" as string]: pin.connected ? tone.border : "var(--forma-surface)",
                  }}
                />
              </>
            )}
            <span className={`block truncate font-medium uppercase leading-none text-[var(--forma-text-strong)] ${viewMode ? "text-[11px]" : "text-[8px]"}`}>{pin.pin_id}</span>
            {pin.name && (
              <span className={`mt-0.5 block truncate font-medium uppercase leading-none text-[var(--forma-text-muted)] ${viewMode ? "text-[8px]" : "text-[6px]"}`}>
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

function splitControllerPins(pins: SchematicPin[], maxPins = 28) {
  const sorted = sortSchematicPins(pins);
  const connected = sorted.filter((pin) => pin.connected);
  const rest = sorted.filter((pin) => !pin.connected);
  const ordered = [...connected, ...rest].slice(0, maxPins);
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
      ariaLabel: `View ${component.name || component.ref_des}`,
      data: {
        component,
        allPins,
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

  const netStyles = schematicNetStyles;

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
    { label: "VCC", color: schematicAccent.red, dash: "none" },
    { label: "GND", color: schematicAccent.muted, dash: "none" },
    { label: "I2C", color: schematicAccent.cyan, dash: "none" },
    { label: "DATA", color: schematicAccent.violet, dash: "none" },
    { label: "PWM", color: schematicAccent.yellow, dash: "none" },
  ];

  return (
    <div className="schematic-legend pointer-events-none absolute left-4 top-4 z-10 max-w-[calc(100%-2rem)] rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] px-3 py-2 shadow-[var(--forma-card-shadow)] backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <div className="mr-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">Wires</div>
        {wireRows.map((wire) => (
          <div
            key={wire.label}
            className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.08em]"
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

function ComponentViewOverlay({ data, onClose }: { data: SchematicNodeData; onClose: () => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const title = data.component.name || data.component.ref_des || "Component";

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    closeButtonRef.current?.focus();

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    };

    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [onClose]);

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-[rgb(var(--forma-scrim-rgb)/0.85)] p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="schematic-view-mode-title"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={`flex max-h-full w-full flex-col overflow-hidden rounded-xl border border-[var(--forma-border)] bg-[var(--forma-surface)] shadow-[var(--forma-card-shadow)] ${data.isController ? "max-w-[640px]" : "max-w-[480px]"}`}
      >
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-[var(--forma-border)] bg-[var(--forma-surface)] px-4 py-3">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">View mode</div>
            <h2 id="schematic-view-mode-title" className="mt-1 truncate text-sm font-semibold tracking-tight text-[var(--forma-text-strong)]">
              {title}
            </h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-[var(--forma-border)] text-[var(--forma-text-body)] hover:bg-[var(--forma-surface-muted)] hover:text-[var(--forma-text-strong)] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--forma-cyan-rgb)/0.45)]"
            aria-label="Close component view"
            title="Close component view (Escape)"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto p-4 sm:p-6">
          <SchematicPartCard data={data} viewMode />
        </div>
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
  const [viewedNodeId, setViewedNodeId] = useState<string | null>(null);
  const appliedProjectRef = useRef(project);
  const nodesProjectKeyRef = useRef(projectKey);
  const viewedNode = viewedNodeId ? nodes.find((node) => node.id === viewedNodeId) : undefined;
  const closeViewMode = useCallback(() => setViewedNodeId(null), []);

  useEffect(() => {
    cacheNodePositions(nodesProjectKeyRef.current, nodes);
  }, [nodes]);

  useEffect(() => {
    if (appliedProjectRef.current === project) return;
    appliedProjectRef.current = project;
    nodesProjectKeyRef.current = projectKey;
    setViewedNodeId(null);
    setNodes(restoreNodePositions(graph.nodes, projectKey));
    setEdges(graph.edges);
  }, [graph, project, projectKey, setEdges, setNodes]);

  return (
    <div className="relative flex h-full min-h-[620px] flex-col overflow-hidden bg-[var(--forma-page)]">
      <div className="schematic-header flex min-h-[60px] flex-wrap items-center gap-3 border-b border-[var(--forma-border)] bg-[var(--forma-surface)] px-4 py-3">
        <div className="mr-2 text-sm font-semibold tracking-tight text-[var(--forma-text-strong)]">Wiring diagram</div>
        <div className="inline-flex h-10 items-center gap-2 rounded-md border border-[var(--forma-border)] bg-[var(--forma-surface-muted)] px-3 text-xs font-medium text-[var(--forma-text-strong)]">
          <Cpu className="h-4 w-4 text-[var(--forma-text-muted)]" />
          <span>{primaryControllerLabel(project)}</span>
        </div>
        <div className="ml-auto text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--forma-text-muted)]">
          Click a component to view
        </div>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={schematicNodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => setViewedNodeId(node.id)}
        fitView
        fitViewOptions={{ padding: 0.16 }}
        minZoom={0.28}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        className="schematic-flow flex-1 bg-[var(--forma-page)]"
      >
        <Background color="var(--forma-text-muted)" gap={28} size={1.1} />
        <Controls
          position="bottom-right"
          className="!rounded-md !border !border-[var(--forma-border)] !bg-[var(--forma-surface)] !text-[var(--forma-text)]"
        />
        <SchematicLegend />
      </ReactFlow>
      {viewedNode && <ComponentViewOverlay data={viewedNode.data} onClose={closeViewMode} />}
    </div>
  );
}
