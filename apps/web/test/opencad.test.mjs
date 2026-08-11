import assert from "node:assert/strict";
import { test } from "node:test";

import { buildFormaOpenCadMeshes } from "../lib/opencad.ts";

test("Forma placements become native OpenCAD box meshes", () => {
  const meshes = buildFormaOpenCadMeshes(
    [{ ref_des: "U1", name: "Controller", category: "microcontroller" }],
    {
      render_dimensions: { x_mm: 100, y_mm: 60, z_mm: 30 },
      component_placements: [
        { ref_des: "U1", position_mm: { x_mm: 50, y_mm: 30, z_mm: 15 }, size_mm: { x_mm: 40, y_mm: 20, z_mm: 6 } },
      ],
    },
    {},
  );

  assert.equal(meshes.length, 1);
  assert.equal(meshes[0].name, "Controller");
  assert.equal(meshes[0].vertices.length, 24);
  assert.equal(meshes[0].faces.length, 36);
  assert.deepEqual(meshes[0].vertices.slice(0, 3), [-10.8, -5.4, -1.62]);
});

test("Forma projects without parts still show an OpenCAD envelope", () => {
  const meshes = buildFormaOpenCadMeshes([], {}, {});
  assert.equal(meshes.length, 1);
  assert.equal(meshes[0].shapeId, "forma-envelope");
});
