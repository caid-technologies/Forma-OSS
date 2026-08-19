export type ProjectCostMetrics = {
  electricalParts: number;
  mechanicalParts: number;
  totalParts: number;
  electricalCost: number;
  mechanicalCost: number;
  totalCost: number;
};

function nonNegativeNumber(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

export function resolveProjectComponentInstances(project: any): any[] {
  const components = Array.isArray(project?.components) ? project.components : [];
  const definitions = new Map(
    (Array.isArray(project?.part_definitions) ? project.part_definitions : [])
      .filter((definition: any) => definition?.part_definition_id)
      .map((definition: any) => [definition.part_definition_id, definition])
  );

  return components.map((component: any) => {
    const definition = definitions.get(component?.part_definition_id) as any;
    if (!definition) return component;
    return {
      ...definition,
      ...component,
      pins: Array.isArray(definition.pins) ? definition.pins : (component.pins || []),
      quantity: component.quantity || 1,
    };
  });
}

export function calculateProjectCostMetrics(project: any): ProjectCostMetrics {
  let electricalParts = 0;
  let mechanicalParts = 0;
  let electricalCost = 0;
  let mechanicalCost = 0;

  const components = Array.isArray(project?.bom) && project.bom.length
    ? project.bom
    : (Array.isArray(project?.components) ? project.components : []);
  components.forEach((component: any) => {
    const category = String(component?.category || "").trim().toLowerCase();
    const quantity = nonNegativeNumber(component?.quantity) || 1;
    const componentCost = nonNegativeNumber(component?.extended_price)
      || nonNegativeNumber(component?.unit_price) * quantity;
    if (["mechanical", "3d print"].includes(category)) {
      mechanicalParts += quantity;
      mechanicalCost += componentCost;
    } else {
      electricalParts += quantity;
      electricalCost += componentCost;
    }
  });

  const fabricationCost = nonNegativeNumber(project?.mechanical?.fabrication_cost_estimate_usd);
  const cadSources = Array.isArray(project?.mechanical?.cad_sources) ? project.mechanical.cad_sources : [];
  const pricedFabricationParts = cadSources.filter(
    (source: any) => nonNegativeNumber(source?.estimated_unit_price_usd) > 0
  ).length;
  const fabricationParts = fabricationCost > 0 ? Math.max(1, pricedFabricationParts) : 0;

  mechanicalParts += fabricationParts;
  mechanicalCost += fabricationCost;

  return {
    electricalParts,
    mechanicalParts,
    totalParts: electricalParts + mechanicalParts,
    electricalCost: Number(electricalCost.toFixed(2)),
    mechanicalCost: Number(mechanicalCost.toFixed(2)),
    totalCost: Number((electricalCost + mechanicalCost).toFixed(2)),
  };
}
