export type PrinterPreset = {
  printer_id: string;
  display_name: string;
  nozzle_mm: number;
  material: string;
  layer_height_mm: number;
};

export type FabricationSettings = {
  printer_id: string;
  source: "user" | "default";
  updated_at: string | null;
  printers: PrinterPreset[];
};

export function normalizeApiUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return "/api";
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}

export function readFabricationSettings(value: unknown): FabricationSettings {
  if (!value || typeof value !== "object") throw new Error("Invalid printer settings response.");
  const data = value as FabricationSettings;
  if (typeof data.printer_id !== "string" || !["user", "default"].includes(data.source)
    || !(data.updated_at === null || typeof data.updated_at === "string")
    || !Array.isArray(data.printers) || !data.printers.length
    || !data.printers.every((printer) => printer && typeof printer.printer_id === "string"
      && typeof printer.display_name === "string" && typeof printer.material === "string"
      && Number.isFinite(printer.nozzle_mm) && printer.nozzle_mm > 0
      && Number.isFinite(printer.layer_height_mm) && printer.layer_height_mm > 0)
    || !data.printers.some((printer) => printer.printer_id === data.printer_id)) {
    throw new Error("Invalid printer settings response.");
  }
  return data;
}
