"use client";

import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Viewport3D } from "opencad-viewport";

import { buildFormaOpenCadMeshes } from "../lib/opencad";

type OpenCadViewportProps = {
  components: any[];
  metadata: Record<string, any>;
  mechanical: Record<string, any>;
};

export default function OpenCadViewport({ components, metadata, mechanical }: OpenCadViewportProps) {
  const meshes = useMemo(
    () => buildFormaOpenCadMeshes(components, mechanical, metadata),
    [components, mechanical, metadata],
  );
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null);
  const selectedMesh = meshes.find((mesh) => mesh.shapeId === selectedShapeId) || null;

  return (
    <div className="flex h-full min-h-[420px] w-full flex-col overflow-hidden bg-[#0a0b0e]">
      <div className="flex min-h-12 items-center justify-between gap-3 border-b border-[#2a2c33] bg-[#141519] px-3 sm:px-4">
        <div className="min-w-0">
          <div className="truncate text-[10px] font-black uppercase tracking-[0.18em] text-white">
            CAID OpenCAD
          </div>
          <div className="truncate text-[10px] text-slate-500">
            Native viewport · {meshes.length} project {meshes.length === 1 ? "body" : "bodies"}
            {selectedMesh?.name ? ` · ${selectedMesh.name}` : ""}
          </div>
        </div>
        <a
          href="https://github.com/caid-technologies/OpenCAD"
          target="_blank"
          rel="noreferrer"
          className="flex shrink-0 items-center gap-2 border border-[#343741] bg-[#1b1d23] px-3 py-2 text-[9px] font-black uppercase tracking-[0.14em] text-slate-300 transition hover:border-cyan-400/50 hover:text-cyan-200"
        >
          OpenCAD source
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
      <div className="opencad-native-viewport min-h-0 flex-1 bg-[#f5f7fb]">
        <Viewport3D
          meshes={meshes}
          selectedShapeId={selectedShapeId}
          onSelectShape={setSelectedShapeId}
        />
      </div>
    </div>
  );
}
