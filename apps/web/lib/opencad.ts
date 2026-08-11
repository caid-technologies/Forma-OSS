import type { MeshPayload } from "opencad-viewport";

type Dimensions = { x_mm: number; y_mm: number; z_mm: number };
type VectorInput = Record<string, unknown> | null | undefined;

const BOX_FACES = [
  0, 3, 2, 0, 2, 1,
  4, 5, 6, 4, 6, 7,
  0, 1, 5, 0, 5, 4,
  1, 2, 6, 1, 6, 5,
  2, 3, 7, 2, 7, 6,
  3, 0, 4, 3, 4, 7,
];

const categorySizes: Record<string, [number, number, number]> = {
  microcontroller: [38, 28, 5],
  sensor: [20, 18, 8],
  actuator: [30, 24, 14],
  display: [32, 18, 4],
  power: [42, 24, 8],
  mechanical: [14, 14, 8],
  "3d print": [26, 20, 8],
  default: [22, 18, 6],
};

function finiteNumber(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function vectorValue(vector: VectorInput, axis: "x" | "y" | "z", fallback: number) {
  if (!vector) return fallback;
  return finiteNumber(vector[`${axis}_mm`] ?? vector[axis], fallback);
}

function vector3(vector: VectorInput, fallback: [number, number, number]): [number, number, number] {
  return [
    vectorValue(vector, "x", fallback[0]),
    vectorValue(vector, "y", fallback[1]),
    vectorValue(vector, "z", fallback[2]),
  ];
}

function dimensionsFrom(mechanical: Record<string, any>, metadata: Record<string, any>): Dimensions {
  const source = mechanical.render_dimensions
    || metadata.product_visual_spec?.external_dimensions_mm
    || metadata.render_dimensions
    || {};
  return {
    x_mm: Math.max(1, vectorValue(source, "x", 100)),
    y_mm: Math.max(1, vectorValue(source, "y", 60)),
    z_mm: Math.max(1, vectorValue(source, "z", 36)),
  };
}

function componentSize(component: Record<string, any> | undefined): [number, number, number] {
  const category = String(component?.category || "default").trim().toLowerCase();
  return categorySizes[category] || categorySizes.default;
}

function generatedPosition(index: number, count: number, dimensions: Dimensions): [number, number, number] {
  const columns = Math.ceil(Math.sqrt(Math.max(count, 1)));
  const rows = Math.ceil(count / columns);
  const column = index % columns;
  const row = Math.floor(index / columns);
  return [
    (column / Math.max(columns - 1, 1) - 0.5) * dimensions.x_mm * 0.62,
    (row / Math.max(rows - 1, 1) - 0.5) * dimensions.y_mm * 0.58,
    0,
  ];
}

function boxMesh(
  shapeId: string,
  name: string,
  center: [number, number, number],
  size: [number, number, number],
  scale: number,
): MeshPayload {
  const [cx, cy, cz] = center.map((value) => value * scale);
  const [hx, hy, hz] = size.map((value) => Math.max(1.5, Math.abs(value) * scale) / 2);
  return {
    shapeId,
    name,
    vertices: [
      cx - hx, cy - hy, cz - hz,
      cx + hx, cy - hy, cz - hz,
      cx + hx, cy + hy, cz - hz,
      cx - hx, cy + hy, cz - hz,
      cx - hx, cy - hy, cz + hz,
      cx + hx, cy - hy, cz + hz,
      cx + hx, cy + hy, cz + hz,
      cx - hx, cy + hy, cz + hz,
    ],
    faces: BOX_FACES,
  };
}

export function buildFormaOpenCadMeshes(
  components: Record<string, any>[],
  mechanical: Record<string, any>,
  metadata: Record<string, any>,
): MeshPayload[] {
  const dimensions = dimensionsFrom(mechanical, metadata);
  const scale = Math.min(1, 54 / Math.max(dimensions.x_mm, dimensions.y_mm, dimensions.z_mm));
  const placements = Array.isArray(mechanical.component_placements)
    ? mechanical.component_placements
    : Array.isArray(metadata.component_placements)
      ? metadata.component_placements
      : [];
  const componentByRef = new Map(
    components.map((component, index) => [String(component.ref_des || `C${index + 1}`), component]),
  );
  const placementByRef = new Map<string, Record<string, any>>();
  placements.forEach((placement: Record<string, any>, index: number) => {
    const ref = String(placement?.ref_des || placement?.ref || `placement-${index + 1}`);
    placementByRef.set(ref, placement);
  });
  const refs = Array.from(new Set([...componentByRef.keys(), ...placementByRef.keys()])).slice(0, 64);

  if (!refs.length) {
    return [boxMesh("forma-envelope", "Forma project envelope", [0, 0, 0], [dimensions.x_mm, dimensions.y_mm, dimensions.z_mm], scale)];
  }

  const rawPositions = refs.map((ref, index) => {
    const placement = placementByRef.get(ref);
    return placement
      ? vector3(placement.position_mm || placement.position, [0, 0, 0])
      : generatedPosition(index, refs.length, dimensions);
  });
  const positiveOrigin = rawPositions.length > 0 && rawPositions.every(([x, y, z]) =>
    x >= 0 && y >= 0 && z >= 0
    && x <= dimensions.x_mm && y <= dimensions.y_mm && z <= dimensions.z_mm
  );

  return refs.map((ref, index) => {
    const component = componentByRef.get(ref);
    const placement = placementByRef.get(ref);
    const rawPosition = rawPositions[index];
    const position: [number, number, number] = positiveOrigin
      ? [
          rawPosition[0] - dimensions.x_mm / 2,
          rawPosition[1] - dimensions.y_mm / 2,
          rawPosition[2] - dimensions.z_mm / 2,
        ]
      : rawPosition;
    const size = placement
      ? vector3(placement.size_mm || placement.size, componentSize(component))
      : componentSize(component);
    const name = String(placement?.label || component?.name || component?.part_number || ref);
    return boxMesh(`forma-${ref}-${index}`, name, position, size, scale);
  });
}
