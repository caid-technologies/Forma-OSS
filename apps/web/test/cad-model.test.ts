import assert from "node:assert/strict";
import { test } from "node:test";

import { projectCadModel, projectHasMechanicalPreview, resolveCadModel } from "../lib/cad-model.ts";

const mesh = {
  shapeId: "body",
  vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0],
  faces: [0, 1, 2],
};

test("project CAD models can be read from the canonical or mechanical payload", () => {
  assert.equal(projectCadModel({ cad_model: "body.step" }), "body.step");
  assert.deepEqual(projectCadModel({ mechanical: { cad_model: { shape_id: "body" } } }), { shape_id: "body" });
  assert.equal(projectCadModel({ assembly_metadata: { cad_model: "legacy.step" } }), "legacy.step");
});

test("mechanical placements provide a CAD-tab fallback when no native model is attached", () => {
  assert.equal(projectHasMechanicalPreview({ mechanical: { component_placements: [{ ref_des: "U1" }] } }), true);
  assert.equal(projectHasMechanicalPreview({ mechanical: { component_placements: [] } }), false);
  assert.equal(projectHasMechanicalPreview({ mechanical: null }), false);
});

test("renderable adapter meshes normalize into a viewport payload", () => {
  const resolved = resolveCadModel({ meshes: [mesh] });

  assert.equal(resolved?.kind, "meshes");
  assert.deepEqual(resolved?.kind === "meshes" ? resolved.meshes[0] : null, mesh);
});

test("shape and browser-loadable file sources resolve for OpenCAD", () => {
  const shape = resolveCadModel({ shape_id: "body", api_url: "https://cad.example.test/" });
  const nestedShape = resolveCadModel({ adapter: { shape_id: "nested-body", api_url: "https://cad.example.test" } });
  const file = resolveCadModel({ url: "https://assets.example.test/enclosure.STEP?signature=ok" });

  assert.deepEqual(shape, { kind: "shape", shapeId: "body", apiBaseUrl: "https://cad.example.test" });
  assert.deepEqual(nestedShape, { kind: "shape", shapeId: "nested-body", apiBaseUrl: "https://cad.example.test" });
  assert.deepEqual(file, {
    kind: "file",
    url: "https://assets.example.test/enclosure.STEP?signature=ok",
    filename: "enclosure.STEP",
    sourceKind: "http",
  });
});

test("unresolved local paths and raw S3 locations never become browser fetches", () => {
  const localPath = resolveCadModel({ path: "C:\\models\\body.step" });
  const s3Uri = resolveCadModel({ s3_uri: "s3://private-bucket/body.step" });
  const signedS3 = resolveCadModel({ s3_uri: "s3://private-bucket/body.step", signed_url: "https://signed.example.test/body.step?token=ok" });

  assert.equal(localPath?.kind, "unsupported");
  assert.equal(s3Uri?.kind, "unsupported");
  assert.equal(signedS3?.kind, "file");
});
