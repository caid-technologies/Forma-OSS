"use client";

import React, { useState, useEffect, useRef } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Sparkles,
  Wrench,
  Cpu,
  ShieldCheck,
  AlertTriangle,
  CheckCircle,
  ShoppingBag,
  History,
  Box,
  RefreshCw,
  Eye,
  Download,
  Database,
  ArrowRight,
  Send,
  Battery,
  Monitor,
  Printer,
  Sliders,
  Info,
  Layers,
  Volume2,
  Paperclip,
  X
} from "lucide-react";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [projectIR, setProjectIR] = useState<any>(null);
  const [mermaidCode, setMermaidCode] = useState<string>("");
  const [svgSchematic, setSvgSchematic] = useState<string>("");
  const [projectHistory, setProjectHistory] = useState<any[]>([]);
  const [catalogComponents, setCatalogComponents] = useState<any[]>([]);
  const [serverStatus, setServerStatus] = useState<"connected" | "disconnected">("disconnected");
  
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const fileInputRefSidebar = useRef<HTMLInputElement>(null);
  const fileInputRefCenter = useRef<HTMLInputElement>(null);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      setSelectedImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const removeSelectedImage = () => {
    setSelectedImage(null);
    if (fileInputRefSidebar.current) fileInputRefSidebar.current.value = "";
    if (fileInputRefCenter.current) fileInputRefCenter.current.value = "";
  };

  // React Flow states
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Active state for mechanical view controls
  const [mechElectricalActive, setMechElectricalActive] = useState(true);
  const [mechToggles, setMechToggles] = useState({
    structural: true,
    enclosure: true,
    mechanism: true,
    misc: false,
    print: true,
  });

  // API Backend URL (Assumes running on Port 8000)
  const API_URL = "http://localhost:8000";

  // Fetch initial catalog and server status on mount
  useEffect(() => {
    checkServerStatus();
    fetchCatalog();
    fetchProjectHistory();
  }, []);

  const checkServerStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/`);
      if (res.ok) {
        setServerStatus("connected");
      } else {
        setServerStatus("disconnected");
      }
    } catch {
      setServerStatus("disconnected");
    }
  };

  const fetchCatalog = async () => {
    try {
      const res = await fetch(`${API_URL}/api/components`);
      if (res.ok) {
        const data = await res.json();
        setCatalogComponents(data);
      }
    } catch (e) {
      console.error("Error fetching catalog", e);
    }
  };

  const fetchProjectHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/api/projects`);
      if (res.ok) {
        const data = await res.json();
        setProjectHistory(data);
      }
    } catch (e) {
      console.error("Error fetching project history", e);
    }
  };

  // Convert Structured Hardware IR to React Flow Nodes & Edges
  const buildReactFlowGraph = (ir: any) => {
    if (!ir || !ir.components) return;

    const newNodes: Node[] = [];
    const newEdges: Edge[] = [];

    // Filter only electrical parts for schematic nodes to keep view clean (like a real CAD board)
    const electricalParts = ir.components.filter((c: any) => 
      !["mechanical", "3d print"].includes(c.category.toLowerCase())
    );

    const mcus = electricalParts.filter((c: any) => c.category.toLowerCase() === "microcontroller");
    const inputs = electricalParts.filter((c: any) => c.category.toLowerCase() === "sensor" || c.category.toLowerCase() === "power");
    const outputs = electricalParts.filter((c: any) => ["actuator", "display", "passives"].includes(c.category.toLowerCase()));

    // Layout margins
    const MCU_X = 400;
    const INPUT_X = 50;
    const OUTPUT_X = 750;

    // Generate Nodes
    electricalParts.forEach((comp: any) => {
      let x = 400;
      let y = 100;

      // Assign position column
      if (comp.category.toLowerCase() === "microcontroller") {
        x = MCU_X;
        const mcuIdx = mcus.findIndex((c: any) => c.ref_des === comp.ref_des);
        y = mcuIdx * 280 + 100;
      } else if (comp.category.toLowerCase() === "sensor" || comp.category.toLowerCase() === "power") {
        x = INPUT_X;
        const inputIdx = inputs.findIndex((c: any) => c.ref_des === comp.ref_des);
        y = inputIdx * 160 + 50;
      } else {
        x = OUTPUT_X;
        const outputIdx = outputs.findIndex((c: any) => c.ref_des === comp.ref_des);
        y = outputIdx * 160 + 50;
      }

      // Design gorgeous dark CAD chip node
      const themeColors = {
        microcontroller: { bg: "bg-slate-900", border: "border-cyan-500/80 shadow-cyan-950/40", text: "text-cyan-400", badge: "bg-cyan-950/60 text-cyan-400 border-cyan-500/30" },
        sensor: { bg: "bg-slate-900", border: "border-emerald-500/80 shadow-emerald-950/40", text: "text-emerald-400", badge: "bg-emerald-950/60 text-emerald-400 border-emerald-500/30" },
        actuator: { bg: "bg-slate-900", border: "border-purple-500/80 shadow-purple-950/40", text: "text-purple-400", badge: "bg-purple-950/60 text-purple-400 border-purple-500/30" },
        display: { bg: "bg-slate-900", border: "border-pink-500/80 shadow-pink-950/40", text: "text-pink-400", badge: "bg-pink-950/60 text-pink-400 border-pink-500/30" },
        power: { bg: "bg-slate-900", border: "border-amber-500/80 shadow-amber-950/40", text: "text-amber-400", badge: "bg-amber-950/60 text-amber-400 border-amber-500/30" },
        default: { bg: "bg-slate-900", border: "border-slate-500/80 shadow-slate-950/40", text: "text-slate-400", badge: "bg-slate-950/60 text-slate-400 border-slate-500/30" },
      };

      const style = themeColors[comp.category.toLowerCase() as keyof typeof themeColors] || themeColors.default;

      newNodes.push({
        id: comp.ref_des,
        position: { x, y },
        draggable: true,
        data: {
          label: (
            <div className={`p-4 rounded-xl border-2 ${style.border} ${style.bg} ${style.text} w-64 text-left shadow-2xl transition-all duration-300 hover:border-white`}>
              <div className="flex justify-between items-center mb-2">
                <span className={`text-[8px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full border ${style.badge}`}>
                  {comp.category}
                </span>
                <span className="font-extrabold text-xs font-mono bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-white">{comp.ref_des}</span>
              </div>
              <h4 className="font-black text-xs text-white truncate mb-1">{comp.name}</h4>
              <p className="text-[9px] text-slate-400 font-mono tracking-tight mb-2">{comp.part_number}</p>
              
              <div className="border-t border-slate-800/80 pt-2 mt-2">
                <div className="text-[8px] uppercase tracking-widest font-extrabold text-slate-500 mb-1">Pinout Config</div>
                <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[8px] font-mono">
                  {comp.pins.slice(0, 8).map((p: any) => (
                    <div key={p.pin_id} className="flex justify-between border-b border-slate-800/30 py-0.5">
                      <span className="font-bold text-slate-300 truncate max-w-[50px]">{p.pin_id}</span>
                      <span className="text-slate-500 truncate max-w-[50px]">{p.name}</span>
                    </div>
                  ))}
                  {comp.pins.length > 8 && (
                    <div className="col-span-2 text-center text-[7px] text-slate-500 mt-1">
                      + {comp.pins.length - 8} more pins
                    </div>
                  )}
                </div>
              </div>
            </div>
          ),
        },
        style: { background: "transparent", border: "none", width: 256 },
      });
    });

    // Generate Edges from connection nets
    const netColors = {
      ground: "#000000",       // Black
      power: "#ef4444",        // Red
      i2c: "#06b6d4",          // Cyan
      spi: "#a855f7",          // Purple
      digital: "#3b82f6",      // Blue
      analog: "#f59e0b",       // Amber
      pwm: "#10b981",          // Emerald
      default: "#64748b"       // Slate
    };

    ir.nets.forEach((net: any) => {
      const netType = net.net_type.toLowerCase();
      const color = netColors[netType as keyof typeof netColors] || netColors.default;
      const isPowerGround = ["power", "ground"].includes(netType);

      if (net.pins.length >= 2) {
        // Sequentially connect pins in the net to represent schematic flow
        for (let i = 0; i < net.pins.length - 1; i++) {
          const srcPin = net.pins[i];
          const destPin = net.pins[i + 1];

          // Make sure both pins are actually represented as electrical nodes
          const hasSrc = electricalParts.some((c: any) => c.ref_des === srcPin.ref_des);
          const hasDest = electricalParts.some((c: any) => c.ref_des === destPin.ref_des);

          if (hasSrc && hasDest) {
            newEdges.push({
              id: `edge_${net.net_id}_${srcPin.ref_des}_to_${destPin.ref_des}`,
              source: srcPin.ref_des,
              target: destPin.ref_des,
              animated: !isPowerGround, // Animate signal paths
              label: `${net.name} (${srcPin.pin_id}➔${destPin.pin_id})`,
              labelStyle: { fill: "#94a3b8", fontWeight: 700, fontSize: 8, fontFamily: "monospace" },
              style: {
                stroke: color,
                strokeWidth: isPowerGround ? 2.5 : 1.5,
                strokeDasharray: netType === "ground" ? "5,5" : "none",
              },
              markerEnd: {
                type: MarkerType.ArrowClosed,
                width: 10,
                height: 10,
                color,
              },
            });
          }
        }
      }
    });

    setNodes(newNodes);
    setEdges(newEdges);
  };

  // Triggers API prompt generation
  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setIsLoading(true);
    checkServerStatus();

    try {
      const res = await fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ 
          prompt,
          image_data: selectedImage || null
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setProjectIR(data.project_ir);
        setMermaidCode(data.mermaid_code);
        setSvgSchematic(data.svg_schematic);
        buildReactFlowGraph(data.project_ir);
        fetchProjectHistory();
        setSelectedImage(null); // Clear image after successful generation
        setActiveTab("overview"); // Jump to overview to admire project specifications!
      } else {
        alert("Error from compilation server. Running with simulated fallback...");
      }
    } catch (e) {
      console.warn("Connection to FastAPI failed. Running high-fidelity local simulation fallback...");
      const mockRes = await runMockCompilation(prompt);
      setProjectIR(mockRes.project_ir);
      setMermaidCode(mockRes.mermaid_code);
      setSvgSchematic(mockRes.svg_schematic);
      buildReactFlowGraph(mockRes.project_ir);
      setSelectedImage(null); // Clear image
      setActiveTab("overview");
    } finally {
      setIsLoading(false);
    }
  };

  // Loads prebuilt example templates directly into visualizer
  const loadExample = async (filename: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`/examples/${filename}`);
      if (res.ok) {
        const ir = await res.json();
        setProjectIR(ir);
        buildReactFlowGraph(ir);
        setSvgSchematic(generateMockSvg(ir));
        setActiveTab("overview");
      }
    } catch (e) {
      console.error("Error loading example", e);
    } finally {
      setIsLoading(false);
    }
  };

  const generateMockSvg = (ir: any): string => {
    const components = ir.components || [];
    const mcu = components.find((component: any) => component.category?.toLowerCase() === "microcontroller") || components[0];
    const inputs = components.filter((component: any) => ["sensor", "power"].includes(component.category?.toLowerCase())).slice(0, 2);
    const outputs = components.filter((component: any) => ["actuator", "display", "passives"].includes(component.category?.toLowerCase())).slice(0, 3);
    const inputA = inputs[0]?.name || "Input Module";
    const inputB = inputs[1]?.name || "Power Rail";
    const outputA = outputs[0]?.name || "Output Module";
    const outputB = outputs[1]?.name || "Display / Actuator";
    const outputC = outputs[2]?.name || "Status Output";

    return `<svg viewBox="0 0 800 380" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#0b0d19" stroke="#1e293b" stroke-width="2"/>
      <g stroke="#1e293b" stroke-width="1">
        <line x1="0" y1="40" x2="800" y2="40" stroke-dasharray="5 5" />
        <line x1="0" y1="120" x2="800" y2="120" stroke-dasharray="5 5" />
        <line x1="0" y1="200" x2="800" y2="200" stroke-dasharray="5 5" />
        <line x1="0" y1="280" x2="800" y2="280" stroke-dasharray="5 5" />
        <line x1="160" y1="0" x2="160" y2="380" stroke-dasharray="5 5" />
        <line x1="400" y1="0" x2="400" y2="380" stroke-dasharray="5 5" />
        <line x1="640" y1="0" x2="640" y2="380" stroke-dasharray="5 5" />
      </g>
      <text x="30" y="30" font-family="monospace" font-size="12" font-weight="bold" fill="#00d2ff">CAD ELECTRICAL WIRE-GRID SCHEMATIC</text>
      
      <!-- MCU node -->
      <rect x="300" y="100" width="200" height="180" rx="8" fill="#0e1324" stroke="#00d2ff" stroke-width="2" filter="drop-shadow(0 0 8px rgba(0,210,255,0.2))"/>
      <text x="400" y="130" font-family="monospace" font-size="12" font-weight="bold" fill="#ffffff" text-anchor="middle">MAIN CONTROLLER</text>
      <text x="400" y="150" font-family="monospace" font-size="10" fill="#00d2ff" text-anchor="middle">${mcu?.part_number || "Controller"}</text>
      
      <!-- Inputs left -->
      <rect x="50" y="80" width="130" height="80" rx="6" fill="#0e1324" stroke="#10b981" stroke-width="1.5" />
      <text x="115" y="115" font-family="monospace" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle">INPUT</text>
      <text x="115" y="135" font-family="monospace" font-size="9" fill="#10b981" text-anchor="middle">${inputA.slice(0, 18)}</text>
      <path d="M 180 120 L 300 150" fill="none" stroke="#10b981" stroke-width="1.5" />

      <rect x="50" y="200" width="130" height="80" rx="6" fill="#0e1324" stroke="#f59e0b" stroke-width="1.5" />
      <text x="115" y="235" font-family="monospace" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle">POWER</text>
      <text x="115" y="255" font-family="monospace" font-size="9" fill="#f59e0b" text-anchor="middle">${inputB.slice(0, 18)}</text>
      <path d="M 180 240 L 300 240" fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="5 5" />

      <!-- Outputs right -->
      <rect x="620" y="70" width="130" height="80" rx="6" fill="#0e1324" stroke="#d946ef" stroke-width="1.5" />
      <text x="685" y="105" font-family="monospace" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle">OUTPUT</text>
      <text x="685" y="125" font-family="monospace" font-size="9" fill="#d946ef" text-anchor="middle">${outputA.slice(0, 18)}</text>
      <path d="M 500 160 L 620 110" fill="none" stroke="#d946ef" stroke-width="1.5" />

      <rect x="620" y="180" width="130" height="80" rx="6" fill="#0e1324" stroke="#a855f7" stroke-width="1.5" />
      <text x="685" y="215" font-family="monospace" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle">MODULE</text>
      <text x="685" y="235" font-family="monospace" font-size="9" fill="#a855f7" text-anchor="middle">${outputB.slice(0, 18)}</text>
      <path d="M 500 220 L 620 220" fill="none" stroke="#a855f7" stroke-width="1.5" />

      <rect x="620" y="290" width="130" height="60" rx="6" fill="#0e1324" stroke="#94a3b8" stroke-width="1.5" />
      <text x="685" y="325" font-family="monospace" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle">${outputC.slice(0, 18)}</text>
      <path d="M 750 220 L 750 320 L 685 320" fill="none" stroke="#a855f7" stroke-width="1" />
    </svg>`;
  };

  // Generates offline high fidelity fallback structures
  const runMockCompilation = async (userPrompt: string): Promise<any> => {
    const promptLower = userPrompt.toLowerCase();
    let file = "biometric_deadbolt.json";
    
    if (promptLower.includes("water") || promptLower.includes("plant") || promptLower.includes("soil") || promptLower.includes("garden")) {
      file = "plant_watering.json";
    } else if (promptLower.includes("thermostat") || promptLower.includes("temperature") || promptLower.includes("weather")) {
      file = "smart_thermostat.json";
    } else {
      file = "biometric_deadbolt.json";
    }

    const res = await fetch(`/examples/${file}`);
    const ir = await res.json();
    return {
      project_ir: ir,
      mermaid_code: `graph LR;\n  SEN1[Sensor] -->|Signal| U1[${ir.components[0].part_number}];\n  U1 -->|Command| ACT1[Actuator];`,
      svg_schematic: generateMockSvg(ir)
    };
  };

  // Helper to load old project
  const loadOldProject = async (projId: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/projects/${projId}`);
      if (res.ok) {
        const data = await res.json();
        setProjectIR(data.project_ir);
        setMermaidCode(data.mermaid_code);
        setSvgSchematic(data.svg_schematic);
        buildReactFlowGraph(data.project_ir);
        setActiveTab("overview");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  const downloadJSONIR = () => {
    if (!projectIR) return;
    const jsonStr = JSON.stringify(projectIR, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${projectIR.overview.title.toLowerCase().replace(/\s+/g, "_")}_blueprint.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Calculate numbers dynamically for the summary table.
  const getOverviewMetrics = () => {
    if (!projectIR || !projectIR.components) return { electricalParts: 0, mechanicalParts: 0, totalParts: 0, electricalCost: 0, mechanicalCost: 0, totalCost: 0 };
    
    let elParts = 0;
    let mechParts = 0;
    let elCost = 0;
    let mechCost = 0;

    projectIR.components.forEach((c: any) => {
      const cat = c.category?.toLowerCase() || "";
      if (["mechanical", "3d print"].includes(cat)) {
        mechParts += c.quantity || 1;
        mechCost += (c.unit_price || 0) * (c.quantity || 1);
      } else {
        elParts += c.quantity || 1;
        elCost += (c.unit_price || 0) * (c.quantity || 1);
      }
    });

    return {
      electricalParts: elParts,
      mechanicalParts: mechParts,
      totalParts: elParts + mechParts,
      electricalCost: parseFloat(elCost.toFixed(2)),
      mechanicalCost: parseFloat(mechCost.toFixed(2)),
      totalCost: parseFloat((elCost + mechCost).toFixed(2))
    };
  };

  const metrics = getOverviewMetrics();

  // Helper to resolve custom category colored icons for the parts list sidebar.
  const getSidebarPartIcon = (category: string) => {
    const cat = category.toLowerCase();
    if (cat === "microcontroller") {
      return { icon: <Cpu className="w-4.5 h-4.5" />, color: "text-cyan-400 bg-cyan-950/60 border-cyan-500/20" };
    } else if (cat === "sensor") {
      return { icon: <Database className="w-4.5 h-4.5" />, color: "text-purple-400 bg-purple-950/60 border-purple-500/20" };
    } else if (cat === "power") {
      return { icon: <Battery className="w-4.5 h-4.5" />, color: "text-yellow-400 bg-yellow-950/60 border-yellow-500/20" };
    } else if (cat === "display") {
      return { icon: <Monitor className="w-4.5 h-4.5" />, color: "text-pink-400 bg-pink-950/60 border-pink-500/20" };
    } else if (cat === "actuator") {
      // Small speaker or headphone output
      return { icon: <Volume2 className="w-4.5 h-4.5" />, color: "text-orange-400 bg-orange-950/60 border-orange-500/20" };
    } else if (cat === "passives") {
      return { icon: <Sliders className="w-4.5 h-4.5" />, color: "text-purple-400 bg-purple-950/60 border-purple-500/20" };
    } else if (cat === "mechanical") {
      return { icon: <Wrench className="w-4.5 h-4.5" />, color: "text-red-400 bg-red-950/60 border-red-500/20" };
    } else {
      return { icon: <Printer className="w-4.5 h-4.5" />, color: "text-blue-400 bg-blue-950/60 border-blue-500/20" };
    }
  };

  const samplePrompts = [
    "ESP32 greenhouse monitor with OLED screen and battery power",
    "Arduino LED wearable with button controls and 3D printed clip",
    "Low-voltage relay controller for a small DC pump"
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#070913] text-slate-100 font-mono antialiased overflow-hidden">
      
      {/* 🚀 HEADER SECTION */}
      <header className="sticky top-0 z-40 bg-[#0b0d19]/95 backdrop-blur-md border-b border-slate-800/80 px-6 py-3.5 flex justify-between items-center shadow-lg shadow-black/10">
        <div className="flex items-center space-x-3.5">
          <div className="p-2 bg-blue-600 rounded-xl text-white shadow-lg shadow-blue-500/20 ring-1 ring-blue-400/30">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-md font-black tracking-widest text-white uppercase flex items-center space-x-1.5">
              <span>BLUEPRINT</span>
              <span className="text-[9px] bg-blue-500/15 border border-blue-500/30 text-blue-400 px-1.5 py-0.5 rounded font-bold font-mono tracking-normal normal-case">open-source</span>
            </h1>
            <p className="text-[8px] uppercase tracking-widest font-extrabold text-slate-500">AI Hardware Compiler & CAD Terminal</p>
          </div>
        </div>

        {/* Preset Instant Loaders */}
        <div className="flex items-center space-x-4">
          <div className="hidden md:flex items-center space-x-1 bg-slate-900/60 p-1 rounded-xl border border-slate-800">
            <span className="text-[8px] font-black text-slate-500 uppercase px-2">Presets:</span>
            <button
              onClick={() => loadExample("plant_watering.json")}
              className="text-[10px] font-extrabold px-2.5 py-1.5 rounded-lg hover:bg-[#1a2035] text-slate-300 hover:text-white transition-all font-mono"
            >
              🌱 Watering
            </button>
            <button
              onClick={() => loadExample("smart_thermostat.json")}
              className="text-[10px] font-extrabold px-2.5 py-1.5 rounded-lg hover:bg-[#1a2035] text-slate-300 hover:text-white transition-all font-mono"
            >
              🌡️ Thermostat
            </button>
            <button
              onClick={() => loadExample("biometric_deadbolt.json")}
              className="text-[10px] font-extrabold px-2.5 py-1.5 rounded-lg hover:bg-[#1a2035] text-slate-300 hover:text-white transition-all font-mono"
            >
              🔒 Deadbolt
            </button>
          </div>

          {/* Connection Status Badge */}
          <div className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-full border text-[9px] font-black uppercase tracking-wider font-mono ${
            serverStatus === "connected" 
              ? "bg-emerald-950/40 text-emerald-400 border-emerald-500/20" 
              : "bg-amber-950/40 text-amber-400 border-amber-500/20"
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${serverStatus === "connected" ? "bg-emerald-400 animate-pulse" : "bg-amber-400 tech-pulse"}`} />
            <span>{serverStatus === "connected" ? "Core Connected" : "Local Simulation"}</span>
          </div>
        </div>
      </header>

      {/* WORKSPACE AREA */}
      <main className="flex-1 flex flex-col xl:flex-row p-4 gap-4 h-[calc(100vh-68px)] overflow-hidden">
        
        {/* LEFT COMPILER PANEL (350px) */}
        <section className={`${!projectIR ? "hidden" : "flex"} w-full xl:w-[340px] flex-col space-y-4 h-full overflow-y-auto pr-1 flex-shrink-0`}>
          {projectIR ? (
            <>
              <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl p-4 shadow-xl space-y-4">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
                  <Info className="w-4 h-4 text-blue-400" />
                  <span>About Project</span>
                </div>
                <div className="space-y-3">
                  <h2 className="text-sm font-black tracking-wider text-white uppercase">{projectIR.overview?.title}</h2>
                  <p className="text-[10px] leading-relaxed text-slate-400">{projectIR.overview?.description}</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(projectIR.constraints || []).slice(0, 8).map((tag: string) => (
                    <span key={tag} className="text-[7px] font-black uppercase tracking-wider px-2 py-1 rounded border border-slate-800 bg-slate-950 text-slate-400">
                      {tag.split(":")[0]}
                    </span>
                  ))}
                </div>
                <div className="border border-slate-800 rounded-xl overflow-hidden">
                  <div className="grid grid-cols-3 bg-slate-950 text-[8px] text-slate-500 uppercase font-black">
                    <span className="p-2">Category</span>
                    <span className="p-2 text-center">Parts</span>
                    <span className="p-2 text-right">Cost</span>
                  </div>
                  <div className="grid grid-cols-3 text-[10px] border-t border-slate-800">
                    <span className="p-2 text-slate-300">Electrical</span>
                    <span className="p-2 text-center text-slate-300">{metrics.electricalParts}</span>
                    <span className="p-2 text-right text-emerald-400">${metrics.electricalCost.toFixed(2)}</span>
                  </div>
                  <div className="grid grid-cols-3 text-[10px] border-t border-slate-800">
                    <span className="p-2 text-slate-300">Mechanical</span>
                    <span className="p-2 text-center text-slate-300">{metrics.mechanicalParts}</span>
                    <span className="p-2 text-right text-emerald-400">${metrics.mechanicalCost.toFixed(2)}</span>
                  </div>
                  <div className="grid grid-cols-3 text-[10px] border-t border-slate-800 bg-slate-950/50 font-black">
                    <span className="p-2 text-white">Total</span>
                    <span className="p-2 text-center text-white">{metrics.totalParts}</span>
                    <span className="p-2 text-right text-emerald-400">${metrics.totalCost.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <>
          
          {/* Main prompt compiling form */}
          <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl p-4 shadow-xl space-y-4">
            <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-blue-400" />
              <span>COMPILE DESIGN</span>
            </h3>
            <form onSubmit={handleGenerate} className="space-y-3">
              <div className="relative">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Describe a safe low-voltage electronics idea, such as an ESP32 sensor dashboard, Arduino motor controller, battery-powered LED wearable, or simple 3D-printable enclosure..."
                  className="w-full h-28 p-3 pb-9 text-[11px] bg-[#070913] border border-slate-800 rounded-xl focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all placeholder:text-slate-600 text-slate-200 leading-normal"
                />
                <div className="absolute bottom-2 left-2 flex items-center gap-1.5">
                  <input
                    type="file"
                    ref={fileInputRefSidebar}
                    accept="image/*"
                    onChange={handleImageChange}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRefSidebar.current?.click()}
                    className={`p-1 rounded hover:bg-slate-800 transition-all ${
                      selectedImage ? "text-blue-400" : "text-slate-500"
                    }`}
                    title="Attach reference sketch/image (multimodal)"
                  >
                    <Paperclip className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {selectedImage && (
                <div className="relative w-16 h-16 rounded-lg border border-slate-800 bg-slate-950 overflow-hidden flex items-center justify-center group">
                  <img src={selectedImage} alt="Reference sketch" className="object-cover w-full h-full" />
                  <button
                    type="button"
                    onClick={removeSelectedImage}
                    className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity"
                  >
                    <X className="w-4 h-4 text-red-400" />
                  </button>
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading || !prompt.trim()}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-xl shadow-lg shadow-blue-500/10 flex items-center justify-center space-x-2 transition-all disabled:opacity-50 text-xs tracking-wider"
              >
                {isLoading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Orchestrating Agents...</span>
                  </>
                ) : (
                  <>
                    <span>COMPILE HARDWARE</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Seed inventory templates catalog */}
          <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl p-4 shadow-xl flex-1 flex flex-col min-h-[180px] overflow-hidden">
            <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center space-x-2 mb-3">
              <Database className="w-4 h-4 text-emerald-400" />
              <span>PARTS SEED DATABASE</span>
            </h3>
            <div className="flex-1 overflow-y-auto space-y-2 pr-1 text-[10px]">
              {catalogComponents.length > 0 ? (
                catalogComponents.map((c: any) => (
                  <div key={c.id || c.part_number} className="p-2.5 bg-[#070913] border border-slate-800/50 rounded-xl hover:border-slate-700 transition-all">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-extrabold text-slate-200 truncate max-w-[140px]">{c.name}</span>
                      <span className="text-[8px] font-mono bg-slate-900 text-slate-400 px-1.5 py-0.5 rounded font-bold border border-slate-800">{c.part_number}</span>
                    </div>
                    <p className="text-slate-500 text-[9px] line-clamp-1 mb-1">{c.description}</p>
                    <div className="flex justify-between items-center text-[8px] font-semibold text-slate-500 mt-1.5">
                      <span className="bg-slate-900 border border-slate-800 text-slate-400 px-1.5 py-0.5 rounded">{c.category.toUpperCase()}</span>
                      <span className="text-emerald-400 font-mono">${c.price.toFixed(2)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-slate-600">Loading catalog...</div>
              )}
            </div>
          </div>

          {/* Project compile history */}
          {projectHistory.length > 0 && (
            <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl p-4 shadow-xl max-h-[160px] flex flex-col overflow-hidden">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center space-x-2 mb-2">
                <History className="w-4 h-4 text-slate-500" />
                <span>COMPILED HISTORY</span>
              </h3>
              <div className="flex-1 overflow-y-auto space-y-1.5">
                {projectHistory.map((p: any) => (
                  <button
                    key={p.project_id}
                    onClick={() => loadOldProject(p.project_id)}
                    className="w-full p-2 text-left bg-[#070913] hover:bg-slate-900/40 border border-slate-800/50 rounded-lg flex justify-between items-center transition-all text-[10px]"
                  >
                    <div className="truncate max-w-[190px]">
                      <div className="font-bold text-slate-300 truncate">{p.title}</div>
                      <div className="text-[8px] text-slate-500 truncate">{p.prompt}</div>
                    </div>
                    <span className="text-[8px] text-blue-400 font-bold font-mono">{p.project_id}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
            </>
          )}
        </section>

        {/* CENTER MAIN DESIGN CANVAS */}
        <section className="flex-1 bg-[#0b0d19] border border-slate-800/80 rounded-3xl shadow-2xl overflow-hidden flex flex-col h-full">
          
          {/* Navigation Workspace Tabs */}
          {projectIR && (
          <div className="bg-[#0f1123]/60 px-5 py-3 border-b border-slate-800/80 flex flex-wrap justify-between items-center gap-3">
            <div className="flex space-x-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800/60">
              <button
                onClick={() => setActiveTab("overview")}
                className={`text-[10px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg flex items-center space-x-1.5 transition-all ${
                  activeTab === "overview" ? "bg-blue-600 text-white shadow-md shadow-blue-500/10" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Overview</span>
              </button>
              <button
                onClick={() => setActiveTab("schematic")}
                className={`text-[10px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg flex items-center space-x-1.5 transition-all ${
                  activeTab === "schematic" ? "bg-blue-600 text-white shadow-md shadow-blue-500/10" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Cpu className="w-3.5 h-3.5" />
                <span>Schematic</span>
              </button>
              <button
                onClick={() => setActiveTab("svg")}
                className={`text-[10px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg flex items-center space-x-1.5 transition-all ${
                  activeTab === "svg" ? "bg-blue-600 text-white shadow-md shadow-blue-500/10" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Eye className="w-3.5 h-3.5" />
                <span>Vector view</span>
              </button>
              <button
                onClick={() => setActiveTab("bom")}
                className={`text-[10px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg flex items-center space-x-1.5 transition-all ${
                  activeTab === "bom" ? "bg-blue-600 text-white shadow-md shadow-blue-500/10" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <ShoppingBag className="w-3.5 h-3.5" />
                <span>BOM & SOURCING</span>
              </button>
              <button
                onClick={() => setActiveTab("assembly")}
                className={`text-[10px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg flex items-center space-x-1.5 transition-all ${
                  activeTab === "assembly" ? "bg-blue-600 text-white shadow-md shadow-blue-500/10" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Wrench className="w-3.5 h-3.5" />
                <span>Instructions</span>
              </button>
              <button
                onClick={() => setActiveTab("mechanical")}
                className={`text-[10px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg flex items-center space-x-1.5 transition-all ${
                  activeTab === "mechanical" ? "bg-blue-600 text-white shadow-md shadow-blue-500/10" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Box className="w-3.5 h-3.5" />
                <span>Mechanical</span>
              </button>
            </div>

            {/* Export and Actions */}
            {projectIR && (
              <button
                onClick={downloadJSONIR}
                className="bg-slate-950 hover:bg-slate-900 border border-slate-800 text-white font-black px-4 py-2 rounded-xl text-[10px] tracking-wider uppercase flex items-center space-x-1.5 transition-all"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export Package</span>
              </button>
            )}
          </div>
          )}

          {/* Main Visualizer Window */}
          <div className="flex-1 relative overflow-hidden bg-[#070913]">
            {projectIR ? (
              <>
                {/* 1. Project overview hero */}
                {activeTab === "overview" && (
                  <div className="w-full h-full p-8 overflow-y-auto space-y-8">
                    
                    {/* Floating premium rendering at the top of landing */}
                    <div className="w-full bg-[#0b0d19] border border-slate-800/80 rounded-2xl overflow-hidden p-6 relative shadow-lg">
                      <div className="absolute top-4 right-4 bg-slate-950 px-2 py-1 rounded text-[8px] font-mono border border-slate-800 font-bold text-slate-500 uppercase tracking-widest flex items-center space-x-1">
                        <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-ping mr-1" />
                        <span>Interactive CAD Mockup Render</span>
                      </div>
                      
                      <div className="h-52 flex items-center justify-center relative overflow-hidden">
                        <div className="absolute inset-0 opacity-30" style={{
                          backgroundImage: "linear-gradient(#1e293b 1px, transparent 1px), linear-gradient(90deg, #1e293b 1px, transparent 1px)",
                          backgroundSize: "32px 32px",
                          transform: "perspective(500px) rotateX(58deg) translateY(35px)"
                        }} />
                        <div className="w-80 h-36 bg-[#0e1324]/90 border border-slate-700 rounded-2xl relative shadow-2xl flex flex-col p-4 rotate-[-4deg]">
                          <div className="flex justify-between items-center">
                            <div className="text-[8px] text-cyan-400 font-black tracking-widest uppercase">{projectIR.overview.category} Project Package</div>
                            <div className="flex gap-1.5">
                              <span className="w-2 h-2 rounded-full bg-slate-600" />
                              <span className="w-2 h-2 rounded-full bg-slate-600" />
                              <span className="w-2 h-2 rounded-full bg-slate-600" />
                            </div>
                          </div>
                          <div className="flex-1 mt-3 grid grid-cols-3 gap-2">
                            <div className="rounded-lg border border-cyan-500/30 bg-cyan-950/20 flex items-center justify-center">
                              <Cpu className="w-7 h-7 text-cyan-400" />
                            </div>
                            <div className="rounded-lg border border-purple-500/30 bg-purple-950/20 flex items-center justify-center">
                              <Database className="w-7 h-7 text-purple-400" />
                            </div>
                            <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 flex items-center justify-center">
                              <Battery className="w-7 h-7 text-amber-400" />
                            </div>
                          </div>
                          <div className="mt-3 flex items-center justify-between text-[7px] text-slate-500 uppercase tracking-widest">
                            <span>Typed IR</span>
                            <span>{projectIR.components.length} Parts</span>
                            <span>{projectIR.nets.length} Nets</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Metadata header and constraint tags */}
                    <div className="space-y-4">
                      <div className="space-y-1">
                        <h2 className="text-xl font-black text-white uppercase tracking-wider font-mono">{projectIR.overview.title}</h2>
                        <div className="flex flex-wrap gap-2 pt-2">
                          {/* Extract tags from IR constraints */}
                          {projectIR.constraints && projectIR.constraints.map((tag: string, i: number) => {
                            const cleanTag = tag.split(":")[0].replace(/\s+/g, " ").toUpperCase();
                            return (
                              <span key={i} className="text-[8px] font-black uppercase font-mono bg-slate-900 border border-slate-800 text-slate-400 px-2.5 py-1 rounded">
                                {cleanTag}
                              </span>
                            );
                          })}
                          <span className="text-[8px] font-black uppercase font-mono bg-slate-900 border border-slate-800 text-slate-400 px-2.5 py-1 rounded">BUILDABLE PACKAGE</span>
                          <span className="text-[8px] font-black uppercase font-mono bg-slate-900 border border-slate-800 text-slate-400 px-2.5 py-1 rounded">VALIDATED IR</span>
                          <span className="text-[8px] font-black uppercase font-mono bg-slate-900 border border-slate-800 text-slate-400 px-2.5 py-1 rounded">LOW VOLTAGE</span>
                        </div>
                      </div>

                      {/* Technical description */}
                      <div className="space-y-2">
                        <div className="text-[9px] uppercase tracking-widest font-extrabold text-slate-500">Technical Description</div>
                        <p className="text-[11px] leading-relaxed text-slate-300 font-mono">{projectIR.overview.description}</p>
                      </div>

                      {/* Cost/part count summary table */}
                      <div className="space-y-2 pt-4">
                        <div className="text-[9px] uppercase tracking-widest font-extrabold text-slate-500">Project Sourcing Breakdown</div>
                        <div className="bg-[#0b0d19] border border-slate-800/80 rounded-xl overflow-hidden max-w-lg">
                          <table className="w-full text-left text-[10px] border-collapse">
                            <thead>
                              <tr className="bg-slate-900/60 border-b border-slate-800/80 text-slate-500 font-bold font-mono">
                                <th className="py-2.5 px-4 uppercase">Category</th>
                                <th className="py-2.5 px-4 uppercase text-center">Parts</th>
                                <th className="py-2.5 px-4 uppercase text-right">Cost</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/50 font-mono">
                              <tr className="hover:bg-slate-900/10">
                                <td className="py-2.5 px-4 text-slate-300">Electrical</td>
                                <td className="py-2.5 px-4 text-center text-slate-300">{metrics.electricalParts}</td>
                                <td className="py-2.5 px-4 text-right text-emerald-400">${metrics.electricalCost.toFixed(2)}</td>
                              </tr>
                              <tr className="hover:bg-slate-900/10">
                                <td className="py-2.5 px-4 text-slate-300">Mechanical</td>
                                <td className="py-2.5 px-4 text-center text-slate-300">{metrics.mechanicalParts}</td>
                                <td className="py-2.5 px-4 text-right text-emerald-400">${metrics.mechanicalCost.toFixed(2)}</td>
                              </tr>
                              <tr className="bg-slate-900/30 border-t border-slate-800/80 font-bold font-mono">
                                <td className="py-3 px-4 text-white">Total</td>
                                <td className="py-3 px-4 text-center text-white">{metrics.totalParts}</td>
                                <td className="py-3 px-4 text-right text-emerald-400">${metrics.totalCost.toFixed(2)}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>

                    </div>
                  </div>
                )}

                {/* 2. SCHEMATIC CANVAS TAB (React Flow) */}
                {activeTab === "schematic" && (
                  <div className="w-full h-full relative">
                    <ReactFlow
                      nodes={nodes}
                      edges={edges}
                      onNodesChange={onNodesChange}
                      onEdgesChange={onEdgesChange}
                      fitView
                      fitViewOptions={{ padding: 0.15 }}
                      className="bg-[#070913]"
                    >
                      <Background color="#1e293b" gap={20} size={1} />
                      <Controls className="!bg-slate-950 !border !border-slate-800 !shadow-2xl !p-1 !text-white" />
                      <MiniMap className="!bg-slate-950 !border !border-slate-800 !shadow-2xl !rounded-xl" nodeStrokeColor="#1e293b" nodeColor="#070913" maskColor="rgba(0,0,0,0.6)" />
                    </ReactFlow>
                  </div>
                )}

                {/* 3. SVG SCHEMATIC VIEW TAB */}
                {activeTab === "svg" && (
                  <div className="w-full h-full p-6 overflow-auto bg-[#070913] flex items-center justify-center">
                    <div className="bg-[#0b0d19] border border-slate-800/80 p-8 rounded-3xl shadow-2xl max-w-4xl w-full" dangerouslySetInnerHTML={{ __html: svgSchematic }} />
                  </div>
                )}

                {/* 4. BOM table */}
                {activeTab === "bom" && (
                  <div className="w-full h-full p-8 overflow-y-auto space-y-6">
                    <div className="flex justify-between items-center border-b border-slate-800 pb-4">
                      <div>
                        <h2 className="text-md font-black text-white uppercase tracking-wider">Project Bill of Materials</h2>
                        <p className="text-[10px] text-slate-500 mt-1">Sourcing inventory templates compiled by BOM Agent.</p>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-black text-emerald-400 font-mono">${metrics.totalCost.toFixed(2)}</div>
                        <div className="text-[8px] uppercase font-bold text-slate-500 tracking-wider">Total Project Cost</div>
                      </div>
                    </div>

                    <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl overflow-hidden shadow-2xl">
                      <table className="w-full text-left border-collapse text-[10px] font-mono">
                        <thead>
                          <tr className="bg-slate-950 text-slate-500 font-bold border-b border-slate-800">
                            <th className="py-4 px-5">PART</th>
                            <th className="py-4 px-5 text-center">QTY</th>
                            <th className="py-4 px-5">UNIT</th>
                            <th className="py-4 px-5">SOURCE</th>
                            <th className="py-4 px-5 text-right">SUBTOTAL</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/40">
                          {projectIR.components.map((c: any) => {
                            const isMechanical = ["mechanical", "3d print"].includes(c.category.toLowerCase());
                            return (
                              <tr key={c.ref_des} className="hover:bg-slate-900/10 transition-colors">
                                <td className="py-4 px-5 max-w-md">
                                  <div className="flex items-start space-x-3">
                                    <div className={`p-2 rounded-lg border flex-shrink-0 ${
                                      isMechanical ? "bg-red-950/40 text-red-400 border-red-500/20" : "bg-blue-950/40 text-blue-400 border-blue-500/20"
                                    }`}>
                                      {isMechanical ? <Wrench className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}
                                    </div>
                                    <div>
                                      <div className="flex items-center space-x-2">
                                        <span className="font-extrabold text-white text-xs">{c.name}</span>
                                        <span className="text-[8px] font-bold bg-slate-950 border border-slate-800 text-slate-400 px-1.5 py-0.5 rounded">
                                          {c.ref_des}
                                        </span>
                                      </div>
                                      <div className="text-[9px] text-slate-500 mt-0.5">{c.part_number}</div>
                                      <div className="text-[9px] text-slate-400 mt-1.5 leading-normal max-w-[280px] line-clamp-2">{c.rationale}</div>
                                    </div>
                                  </div>
                                </td>
                                <td className="py-4 px-5 text-center font-bold text-slate-300">{c.quantity}</td>
                                <td className="py-4 px-5 text-slate-300">~${c.unit_price.toFixed(2)}</td>
                                <td className="py-4 px-5">
                                  <div className="flex flex-col gap-1">
                                    <span className={`text-[9px] border px-2 py-0.5 rounded text-center max-w-[120px] ${
                                      isMechanical
                                        ? "bg-blue-950/40 text-blue-400 border-blue-500/20"
                                        : "bg-emerald-950/30 text-emerald-400 border-emerald-500/20"
                                    }`}>
                                      {isMechanical ? "Fabricate" : "Seed Library"}
                                    </span>
                                    {c.sourcing_url && (
                                      <span className="text-[8px] text-slate-500">datasheet/source available</span>
                                    )}
                                  </div>
                                </td>
                                <td className="py-4 px-5 text-right font-bold text-emerald-400">~${(c.unit_price * c.quantity).toFixed(2)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* 5. ASSEMBLY GUIDE TAB */}
                {activeTab === "assembly" && (
                  <div className="w-full h-full p-8 overflow-y-auto space-y-6">
                    <div>
                      <h2 className="text-md font-black text-white uppercase tracking-wider">Chronological Build Instructions</h2>
                      <p className="text-[10px] text-slate-500 mt-1">Order guidelines prepared sequentially from your circuit connections graph.</p>
                    </div>

                    <div className="space-y-4">
                      {projectIR.assembly.map((step: any) => (
                        <div key={step.step_num} className="bg-[#0b0d19] border border-slate-800/80 p-5 rounded-2xl shadow-xl flex gap-4">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-950 text-blue-400 border border-blue-500/30 flex items-center justify-center font-extrabold text-xs">
                            {step.step_num}
                          </div>
                          <div className="space-y-2 flex-1 font-mono text-[10px]">
                            <h4 className="font-extrabold text-slate-200 text-xs">{step.title}</h4>
                            <p className="text-slate-400 leading-relaxed">{step.description}</p>
                            
                            {/* Danger notification */}
                            {step.danger_flag && (
                              <div className="p-3 bg-red-950/30 border border-red-500/20 text-red-400 rounded-xl font-bold flex items-start space-x-2">
                                <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                                <span>{step.danger_message || "Pay close attention to safety constraints during this stage!"}</span>
                              </div>
                            )}

                            {/* Affected Components Badge */}
                            {step.affected_components && step.affected_components.length > 0 && (
                              <div className="flex items-center space-x-1.5 pt-1.5">
                                <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Target Parts:</span>
                                {step.affected_components.map((part: string) => (
                                  <span key={part} className="bg-slate-950 text-slate-400 font-mono text-[8px] font-bold px-2 py-0.5 rounded border border-slate-800">
                                    {part}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 6. Mechanical wireframe view */}
                {activeTab === "mechanical" && (
                  <div className="w-full h-full flex overflow-hidden">
                    {/* Left internal CAD controls panel */}
                    <div className="w-56 border-r border-slate-850 bg-[#0a0c18] p-5 flex flex-col space-y-5">
                      <div>
                        <h4 className="text-[9px] font-black uppercase text-slate-500 tracking-wider">3D CAD CONTROLS</h4>
                        <div className="mt-2 text-[10px] font-bold text-slate-300">Workspace Layer Options</div>
                      </div>
                      
                      {/* Interactive layer toggles */}
                      <div className="space-y-2.5 text-[9px] font-bold">
                        <button 
                          onClick={() => setMechElectricalActive(!mechElectricalActive)}
                          className={`w-full text-left py-1.5 px-3 rounded border flex justify-between items-center transition-all ${
                            mechElectricalActive ? "bg-cyan-950/30 text-cyan-400 border-cyan-500/20" : "bg-slate-950 text-slate-600 border-slate-900"
                          }`}
                        >
                          <span>❖ ELECTRICAL</span>
                          <span className="text-[8px]">{mechElectricalActive ? "ON" : "OFF"}</span>
                        </button>
                        
                        <div className="border-t border-slate-800/80 pt-3">
                          <span className="text-[8px] text-slate-500 tracking-widest uppercase">MECHANICAL</span>
                          <div className="mt-2 space-y-1.5">
                            {Object.entries(mechToggles).map(([key, val]) => (
                              <button
                                key={key}
                                onClick={() => setMechToggles({...mechToggles, [key]: !val})}
                                className={`w-full text-left py-1.5 px-3 rounded border flex justify-between items-center transition-all ${
                                  val ? "bg-slate-900 text-white border-slate-800" : "bg-slate-950 text-slate-600 border-slate-900"
                                }`}
                              >
                                <span className="uppercase">☼ {key}</span>
                                <span className="text-[7px]">{val ? "ACTIVE" : "HIDE"}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Translucent wireframe viewport with lines & labels calling out internal mounts */}
                    <div className="flex-1 bg-slate-950/30 p-6 flex flex-col items-center justify-center relative overflow-hidden">
                      <div className="absolute top-4 left-4 bg-slate-950 border border-slate-800 px-2.5 py-1.5 rounded-lg text-[8px] text-slate-400 font-bold uppercase tracking-wider flex items-center space-x-1.5">
                        <span className="w-2 h-2 rounded bg-cyan-400" />
                        <span>TRANS-AXIAL TRANSPARENT CHASSIS ASSEMBLY</span>
                      </div>

                      <div className="absolute inset-0 opacity-30" style={{
                        backgroundImage: "linear-gradient(#1e293b 1px, transparent 1px), linear-gradient(90deg, #1e293b 1px, transparent 1px)",
                        backgroundSize: "46px 46px",
                        transform: "perspective(650px) rotateX(62deg) translateY(120px)"
                      }} />
                      <div className="relative w-96 h-56 mt-4 flex items-center justify-center">
                        <div className="absolute w-80 h-36 border border-cyan-500/30 bg-cyan-950/5 rounded-lg flex flex-col justify-between p-2 transform rotate-12 skew-x-3 shadow-2xl relative">
                          <span className="absolute w-2 h-2 bg-pink-500 rounded-full left-10 top-10" />
                          <span className="absolute w-2 h-2 bg-cyan-500 rounded-full right-16 bottom-12" />
                          <span className="absolute w-2 h-2 bg-yellow-500 rounded-full left-1/2 top-6" />
                          <div className="absolute left-[-42px] top-1/2 transform -translate-y-1/2 text-[9px] font-bold text-cyan-400 font-mono">Y</div>
                          <div className="absolute bottom-[-22px] left-1/2 transform -translate-x-1/2 text-[9px] font-bold text-cyan-400 font-mono">X</div>
                          <div className="absolute right-[-42px] top-1/2 transform -translate-y-1/2 text-[9px] font-bold text-cyan-400 font-mono">Z</div>
                        </div>

                        <div className="absolute top-[-30px] left-8 border-l border-b border-dashed border-slate-500 pl-2 pb-1 text-[8px] text-slate-400 font-bold uppercase">
                          Display / Sensor Mount
                        </div>
                        <div className="absolute top-[-5px] right-4 border-r border-b border-dashed border-slate-500 pr-2 pb-1 text-[8px] text-slate-400 font-bold uppercase">
                          Main Controller Mount
                        </div>
                        <div className="absolute bottom-[0px] left-[-20px] border-l border-t border-dashed border-slate-500 pl-2 pt-1 text-[8px] text-slate-400 font-bold uppercase">
                          Battery / Cable Routing
                        </div>
                        <div className="absolute bottom-[-15px] right-8 border-r border-t border-dashed border-slate-500 pr-2 pt-1 text-[8px] text-slate-400 font-bold uppercase">
                          Enclosure Fasteners
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              </>
            ) : (
              <div className="w-full h-full bg-[#070913] text-slate-500 p-8 font-mono overflow-y-auto">
                <div className="h-full min-h-[520px] border border-slate-800/80 rounded-3xl bg-[#0b0d19] relative overflow-hidden flex items-center justify-center">
                  <div className="absolute inset-0 opacity-20" style={{
                    backgroundImage: "linear-gradient(#1e293b 1px, transparent 1px), linear-gradient(90deg, #1e293b 1px, transparent 1px)",
                    backgroundSize: "36px 36px"
                  }} />
                  <div className="relative max-w-3xl mx-auto text-center space-y-8 p-8">
                    <div className="mx-auto w-20 h-20 rounded-2xl border border-blue-500/30 bg-blue-950/20 flex items-center justify-center shadow-2xl shadow-blue-950/30">
                      <Cpu className="w-9 h-9 text-blue-400" />
                    </div>
                    <div className="space-y-3">
                      <p className="text-[10px] uppercase tracking-[0.35em] text-blue-400 font-black">Prompt-to-Verifiable Hardware</p>
                      <h2 className="text-2xl md:text-3xl font-black text-white uppercase tracking-wider">Describe a low-voltage build idea</h2>
                      <p className="text-xs text-slate-400 leading-relaxed max-w-xl mx-auto">
                        Blueprint compiles your idea into requirements, components, wiring nets, pin mappings, fabrication notes,
                        assembly steps, and a typed JSON Hardware IR with validation checks.
                      </p>
                    </div>
                    <form onSubmit={handleGenerate} className="max-w-2xl mx-auto w-full">
                      <div className="bg-[#070913] border border-slate-800 rounded-2xl p-2 flex flex-col gap-2 shadow-2xl">
                        <div className="flex items-end gap-2">
                          <textarea
                            value={prompt}
                            onChange={(event) => setPrompt(event.target.value)}
                            placeholder="Ask Blueprint to architect an ESP32 greenhouse monitor..."
                            className="min-h-[76px] flex-1 resize-none bg-transparent p-3 text-xs text-slate-200 placeholder:text-slate-600 outline-none leading-relaxed"
                          />
                          <div className="flex items-center gap-2 pb-1.5 pr-1.5">
                            <input
                              type="file"
                              ref={fileInputRefCenter}
                              accept="image/*"
                              onChange={handleImageChange}
                              className="hidden"
                            />
                            <button
                              type="button"
                              onClick={() => fileInputRefCenter.current?.click()}
                              className={`p-2.5 rounded-xl hover:bg-slate-800 border border-slate-800 transition-all ${
                                selectedImage ? "text-blue-400 border-blue-500/30" : "text-slate-500"
                              }`}
                              title="Attach reference sketch/image (multimodal)"
                            >
                              <Paperclip className="w-4 h-4" />
                            </button>
                            <button
                              type="submit"
                              disabled={isLoading || !prompt.trim()}
                              className="h-11 w-11 rounded-xl bg-blue-600 text-white flex items-center justify-center disabled:opacity-40 hover:bg-blue-500 transition-all"
                              aria-label="Generate hardware design"
                            >
                              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                            </button>
                          </div>
                        </div>

                        {selectedImage && (
                          <div className="px-3 pb-2 flex items-center">
                            <div className="relative w-20 h-20 rounded-xl border border-slate-800 bg-slate-950 overflow-hidden flex items-center justify-center group shadow-md">
                              <img src={selectedImage} alt="Reference sketch" className="object-cover w-full h-full" />
                              <button
                                type="button"
                                onClick={removeSelectedImage}
                                className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity"
                                title="Remove image"
                              >
                                <X className="w-5 h-5 text-red-400" />
                              </button>
                            </div>
                            <div className="ml-3 text-left">
                              <span className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider">multimodal input loaded</span>
                              <span className="text-[9px] text-slate-500">Google Nano Banana will extract visual context.</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </form>
                    <div className="grid md:grid-cols-3 gap-3 text-left">
                      {[
                        "ESP32 greenhouse monitor with OLED screen",
                        "Arduino LED wearable with rechargeable battery",
                        "Low-voltage relay controller in printed enclosure"
                      ].map((example) => (
                        <button
                          key={example}
                          onClick={() => setPrompt(example)}
                          className="p-4 rounded-2xl border border-slate-800 bg-slate-950/50 hover:border-blue-500/40 hover:text-slate-200 transition-all text-[10px] leading-relaxed"
                        >
                          <span className="block text-blue-400 font-black uppercase tracking-widest mb-2">Example Prompt</span>
                          {example}
                        </button>
                      ))}
                    </div>
                    <div className="flex flex-wrap justify-center gap-2 text-[8px] uppercase tracking-widest font-black">
                      <span className="px-2.5 py-1 rounded border border-slate-800 bg-slate-950">Arduino / ESP32</span>
                      <span className="px-2.5 py-1 rounded border border-slate-800 bg-slate-950">Sensors</span>
                      <span className="px-2.5 py-1 rounded border border-slate-800 bg-slate-950">Displays</span>
                      <span className="px-2.5 py-1 rounded border border-slate-800 bg-slate-950">Simple Motors</span>
                      <span className="px-2.5 py-1 rounded border border-red-900/60 bg-red-950/20 text-red-300">Blocks unsafe domains</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Right sidebar: parts list and safety audit */}
        {projectIR && (
          <section className="w-full xl:w-[320px] flex flex-col space-y-4 h-full overflow-y-auto flex-shrink-0">
            
            {/* Parts list side panel */}
            <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl p-4 shadow-xl flex-1 flex flex-col overflow-hidden max-h-[60%]">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center space-x-2 border-b border-slate-800 pb-3 mb-2.5">
                <Box className="w-4 h-4 text-cyan-400" />
                <span>PARTS LIST ({projectIR.components.length})</span>
              </h3>
              <div className="flex-1 overflow-y-auto space-y-1.5 pr-1 text-[9px] font-mono">
                {projectIR.components.map((c: any, index: number) => {
                  const deco = getSidebarPartIcon(c.category);
                  return (
                    <div key={index} className="p-2 bg-[#070913] border border-slate-800/55 rounded-lg flex items-center space-x-2.5 hover:border-slate-700 transition-all">
                      <div className={`p-1.5 rounded-md border ${deco.color} flex-shrink-0`}>
                        {deco.icon}
                      </div>
                      <div className="truncate flex-1">
                        <div className="font-extrabold text-slate-200 truncate">{c.name}</div>
                        <div className="text-[8px] text-slate-500 truncate mt-0.5">{c.part_number}</div>
                      </div>
                      <span className="text-[8px] bg-slate-900 border border-slate-800 text-slate-400 px-1 rounded font-bold font-mono">
                        {c.ref_des}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* SAFETY AUDITOR SUMMARY PANEL */}
            <div className="bg-[#0b0d19] border border-slate-800/80 rounded-2xl p-4 shadow-xl flex-1 flex flex-col overflow-hidden max-h-[40%]">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center space-x-2 border-b border-slate-800 pb-3 mb-2.5">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                <span>SAFETY AUDIT REPORT</span>
              </h3>

              {/* Status banner */}
              {projectIR.is_valid ? (
                <div className="p-2.5 bg-emerald-950/40 border border-emerald-500/20 text-emerald-400 rounded-xl flex items-center space-x-2 mb-3 shadow">
                  <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                  <div className="text-[8px] font-bold uppercase tracking-wider font-mono">
                    Circuit Approved (Safe to Power)
                  </div>
                </div>
              ) : (
                <div className="p-2.5 bg-red-950/40 border border-red-500/20 text-red-400 rounded-xl flex items-center space-x-2 mb-3 shadow">
                  <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <div className="text-[8px] font-bold uppercase tracking-wider font-mono">
                    Safety Violations Detected
                  </div>
                </div>
              )}

              {/* Issue list */}
              <div className="flex-1 overflow-y-auto space-y-2 pr-1 text-[9px] font-mono">
                {(() => {
                  const allIssues = [
                    ...(projectIR.validation?.critical || []),
                    ...(projectIR.validation?.warning || []),
                    ...(projectIR.validation?.info || []),
                    ...(projectIR.validation_issues || [])
                  ];
                  
                  if (allIssues.length > 0) {
                    return allIssues.map((issue: any, index: number) => {
                      const isCritical = issue.severity === "CRITICAL" || issue.severity === "ERROR";
                      const isWarning = issue.severity === "WARNING";
                      
                      let cardBg = "bg-blue-950/30 border-blue-500/10 text-slate-300";
                      let badgeBg = "bg-blue-950 text-blue-400 border border-blue-500/25";
                      if (isCritical) {
                        cardBg = "bg-red-950/30 border-red-500/10 text-slate-300";
                        badgeBg = "bg-red-950 text-red-400 border border-red-500/25";
                      } else if (isWarning) {
                        cardBg = "bg-amber-950/30 border-amber-500/10 text-slate-300";
                        badgeBg = "bg-amber-950 text-amber-400 border border-amber-500/25";
                      }

                      return (
                        <div key={index} className={`p-2.5 rounded-lg border shadow ${cardBg}`}>
                          <div className="flex justify-between items-center mb-1">
                            <span className={`text-[7px] font-extrabold px-1.5 py-0.5 rounded ${badgeBg}`}>
                              {issue.severity}
                            </span>
                            <span className="font-extrabold text-[8px] text-slate-500 tracking-wider font-mono">{issue.category}</span>
                          </div>
                          <p className="font-bold text-[9px] leading-normal text-slate-200 mt-1">{issue.description}</p>
                        </div>
                      );
                    });
                  } else {
                    return (
              <div className="text-center py-6 text-slate-600 flex flex-col justify-center items-center space-y-2.5">
                        <ShieldCheck className="w-7 h-7 stroke-[1.5] text-slate-700" />
                        <span className="text-[8px] uppercase tracking-wider font-bold">All electrical nets validated safely.</span>
                      </div>
                    );
                  }
                })()}
              </div>
            </div>

          </section>
        )}
      </main>
    </div>
  );
}
