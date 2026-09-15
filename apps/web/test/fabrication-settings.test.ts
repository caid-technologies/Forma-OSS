import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeApiUrl, readFabricationSettings } from "../lib/fabrication-settings.ts";

for (const [input, expected] of [["", "/api"], [" /api/// ", "/api"],
  ["https://api.example.test/", "https://api.example.test/api"],
  ["https://api.example.test/api///", "https://api.example.test/api"],
  ["https://api.example.test/v2/", "https://api.example.test/v2/api"]]) {
  test(`API base normalization: ${input}`, () => assert.equal(normalizeApiUrl(input), expected));
}
const valid = { printer_id: "bambu_a1_04", source: "user", updated_at: "today", printers: [
  { printer_id: "bambu_a1_04", display_name: "Bambu A1", material: "PLA", nozzle_mm: 0.4, layer_height_mm: 0.2 },
] };
test("a persisted preference is preserved exactly", () => assert.deepEqual(readFabricationSettings(valid), valid));
test("unrecognized or incomplete responses cannot claim a successful save", () => {
  for (const value of [null, {}, { ...valid, source: "environment" }, { ...valid, printer_id: "unknown" },
    { ...valid, printers: [] }, { ...valid, printers: [{ ...valid.printers[0], nozzle_mm: NaN }] }]) {
    assert.throws(() => readFabricationSettings(value), /Invalid printer settings/);
  }
});
test("an account without saved settings can select and save the default", () => {
  const data = readFabricationSettings({ ...valid, source: "default", updated_at: null });
  assert.equal(data.source, "default");
  assert.equal(data.updated_at, null);
});
