export type MechanicalMotionType = "revolute" | "prismatic" | "compliant";
export type MechanicalAxis = "X" | "Y" | "Z";

export type MechanicalMotionInput = {
  motion_id?: string;
  id?: string;
  label?: string;
  type?: string;
  target_ref?: string;
  target_ref_des?: string;
  parent_ref?: string;
  parent_ref_des?: string;
  axis?: string;
  pivot_mm?: number[] | { x_mm?: number; y_mm?: number; z_mm?: number; x?: number; y?: number; z?: number };
  min_deg?: number;
  max_deg?: number;
  min_mm?: number;
  max_mm?: number;
  notes?: string;
};

export type NormalizedMechanicalMotion = {
  id: string;
  label: string;
  type: MechanicalMotionType;
  targetRef: string;
  parentRef?: string;
  axis: MechanicalAxis;
  pivotMm: [number, number, number];
  min: number;
  max: number;
  unit: "deg" | "mm";
  notes?: string;
};

function finiteNumber(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeAxis(value: unknown): MechanicalAxis | null {
  const axis = String(value || "").trim().toUpperCase();
  return axis === "X" || axis === "Y" || axis === "Z" ? axis : null;
}

function normalizePivot(value: MechanicalMotionInput["pivot_mm"]): [number, number, number] {
  if (Array.isArray(value)) {
    return [
      finiteNumber(value[0], 0),
      finiteNumber(value[1], 0),
      finiteNumber(value[2], 0),
    ];
  }
  if (value && typeof value === "object") {
    return [
      finiteNumber(value.x_mm ?? value.x, 0),
      finiteNumber(value.y_mm ?? value.y, 0),
      finiteNumber(value.z_mm ?? value.z, 0),
    ];
  }
  return [0, 0, 0];
}

export function clampMotionProgress(progress: number) {
  if (!Number.isFinite(progress)) return 0;
  return Math.min(1, Math.max(0, progress));
}

export function motionValueAtProgress(motion: NormalizedMechanicalMotion, progress: number) {
  const t = clampMotionProgress(progress);
  return motion.min + (motion.max - motion.min) * t;
}

export function motionRangeLabel(motion: NormalizedMechanicalMotion) {
  const format = (value: number) => Number.isInteger(value) ? String(value) : value.toFixed(1);
  return `${format(motion.min)} → ${format(motion.max)} ${motion.unit}`;
}

export function normalizeMechanicalMotions(
  inputs: MechanicalMotionInput[],
  validTargetRefs?: ReadonlySet<string>,
): NormalizedMechanicalMotion[] {
  if (!Array.isArray(inputs)) return [];

  return inputs.flatMap((input, index) => {
    if (!input || typeof input !== "object") return [];

    const type = String(input.type || "").trim().toLowerCase() as MechanicalMotionType;
    if (type !== "revolute" && type !== "prismatic" && type !== "compliant") return [];

    const targetRef = String(input.target_ref || input.target_ref_des || "").trim();
    const axis = normalizeAxis(input.axis);
    if (!targetRef || !axis || (validTargetRefs && !validTargetRefs.has(targetRef))) return [];

    const unit = type === "prismatic" ? "mm" : "deg";
    const defaultMax = type === "prismatic" ? 10 : type === "compliant" ? 30 : 90;
    const min = finiteNumber(unit === "mm" ? input.min_mm : input.min_deg, 0);
    const max = finiteNumber(unit === "mm" ? input.max_mm : input.max_deg, defaultMax);
    const parentRef = String(input.parent_ref || input.parent_ref_des || "").trim() || undefined;
    const id = String(input.motion_id || input.id || `${targetRef}-${type}-${index + 1}`).trim();
    const label = String(input.label || `${targetRef} ${type}`).trim();

    return [{
      id,
      label,
      type,
      targetRef,
      parentRef,
      axis,
      pivotMm: normalizePivot(input.pivot_mm),
      min,
      max,
      unit,
      notes: typeof input.notes === "string" && input.notes.trim() ? input.notes.trim() : undefined,
    }];
  });
}
