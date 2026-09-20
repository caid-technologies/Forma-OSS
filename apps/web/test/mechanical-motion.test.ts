import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampMotionProgress,
  motionRangeLabel,
  motionValueAtProgress,
  normalizeMechanicalMotions,
} from "../lib/mechanical-motion.ts";

test("normalizes revolute and prismatic motion definitions", () => {
  const motions = normalizeMechanicalMotions([
    {
      motion_id: "lid",
      type: "revolute",
      target_ref: "LID",
      axis: "z",
      pivot_mm: [-40, 10, 0],
      min_deg: 0,
      max_deg: 105,
    },
    {
      type: "prismatic",
      target_ref_des: "BUTTON",
      parent_ref_des: "CASE",
      axis: "Y",
      pivot_mm: { x_mm: 1, y_mm: 2, z_mm: 3 },
      min_mm: 0,
      max_mm: 1.5,
    },
  ], new Set(["LID", "BUTTON", "CASE"]));

  assert.equal(motions.length, 2);
  assert.deepEqual(motions[0], {
    id: "lid",
    label: "LID revolute",
    type: "revolute",
    targetRef: "LID",
    parentRef: undefined,
    axis: "Z",
    pivotMm: [-40, 10, 0],
    min: 0,
    max: 105,
    unit: "deg",
    notes: undefined,
  });
  assert.equal(motions[1].parentRef, "CASE");
  assert.deepEqual(motions[1].pivotMm, [1, 2, 3]);
  assert.equal(motionRangeLabel(motions[1]), "0 → 1.5 mm");
});

test("motion progress clamps and interpolates signed ranges", () => {
  const [motion] = normalizeMechanicalMotions([
    { type: "prismatic", target_ref: "SLIDE", axis: "X", min_mm: -4, max_mm: 6 },
  ]);

  assert.equal(clampMotionProgress(-1), 0);
  assert.equal(clampMotionProgress(2), 1);
  assert.equal(motionValueAtProgress(motion, 0), -4);
  assert.equal(motionValueAtProgress(motion, 0.5), 1);
  assert.equal(motionValueAtProgress(motion, 1), 6);
});

test("invalid motion definitions and missing targets are ignored", () => {
  const motions = normalizeMechanicalMotions([
    { type: "spin", target_ref: "A", axis: "Z" },
    { type: "revolute", target_ref: "", axis: "Z" },
    { type: "revolute", target_ref: "MISSING", axis: "Z" },
    { type: "revolute", target_ref: "A", axis: "Q" },
  ], new Set(["A"]));

  assert.deepEqual(motions, []);
});
