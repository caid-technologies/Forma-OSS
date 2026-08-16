import assert from "node:assert/strict";
import { test } from "node:test";

import {
  calculateProjectCostMetrics,
  resolveProjectComponentInstances,
} from "../lib/project-cost-metrics.ts";

const project = {
  part_definitions: [{
    part_definition_id: "PART_N20",
    part_number: "N20-6V",
    name: "N20 gear motor",
    category: "Actuator",
    pins: [{ pin_id: "+", name: "Positive", pin_type: "Power" }],
    unit_price: 3.25,
  }],
  components: ["M1", "M2", "M3", "M4"].map((ref_des) => ({
    ref_des,
    part_definition_id: "PART_N20",
    rationale: "Wheel drive",
  })),
  bom: [{
    line_id: "BOM_PART_N20",
    part_definition_id: "PART_N20",
    instance_refs: ["M1", "M2", "M3", "M4"],
    quantity: 4,
    name: "N20 gear motor",
    category: "Actuator",
    unit_price: 3.25,
    extended_price: 13,
  }],
};

test("normalized component instances resolve shared display and pin data", () => {
  const components = resolveProjectComponentInstances(project);

  assert.equal(components.length, 4);
  assert.equal(components[0].name, "N20 gear motor");
  assert.equal(components[0].pins[0].pin_id, "+");
  assert.equal(components[0].quantity, 1);
});

test("cost metrics use aggregated BOM rows without double counting instances", () => {
  const metrics = calculateProjectCostMetrics(project);

  assert.equal(metrics.electricalParts, 4);
  assert.equal(metrics.electricalCost, 13);
});
