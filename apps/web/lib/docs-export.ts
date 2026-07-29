export type DocsAssemblyStep = {
  step_num?: number | string | null;
  title?: string | null;
  description?: string | null;
  danger_flag?: boolean;
  danger_message?: string | null;
  affected_components?: unknown;
};

export type DocsValidationIssue = {
  severity?: string | null;
  category?: string | null;
  description?: string | null;
  troubleshooting?: string | null;
};

type ProjectDocsMarkdownInput = {
  title?: string | null;
  description?: string | null;
  assembly?: DocsAssemblyStep[] | null;
  issues?: DocsValidationIssue[] | null;
};

function cleanText(value: unknown) {
  if (typeof value === "string") return value.trim().replace(/\r\n?/g, "\n");
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
}

function singleLine(value: unknown) {
  return cleanText(value).replace(/\s+/g, " ");
}

function headingText(value: unknown, fallback: string) {
  return (singleLine(value) || fallback).replace(/([\\`*_[\]<>])/g, "\\$1");
}

function paragraphText(value: unknown) {
  return cleanText(value)
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.replace(/\s*\n\s*/g, " "))
    .filter(Boolean)
    .join("\n\n");
}

function inlineCode(value: unknown) {
  const text = singleLine(value);
  if (!text) return "";
  return text.includes("`") ? `\`\` ${text} \`\`` : `\`${text}\``;
}

function issueHeading(issue: DocsValidationIssue) {
  const severity = singleLine(issue.severity).toUpperCase();
  const category = singleLine(issue.category);
  return [severity, category].filter(Boolean).join(" · ") || "Audit note";
}

export function buildProjectDocsMarkdown({
  title,
  description,
  assembly = [],
  issues = [],
}: ProjectDocsMarkdownInput) {
  const lines = [`# ${headingText(title, "Untitled Hardware Project")}`, ""];
  const projectDescription = paragraphText(description);

  if (projectDescription) lines.push(projectDescription, "");

  lines.push("## Build Instructions", "");

  if (assembly?.length) {
    assembly.forEach((step, index) => {
      const stepNumber = singleLine(step.step_num) || String(index + 1);
      lines.push(`### ${stepNumber}. ${headingText(step.title, `Step ${stepNumber}`)}`, "");

      const stepDescription = paragraphText(step.description);
      if (stepDescription) lines.push(stepDescription, "");

      if (step.danger_flag) {
        const warning = paragraphText(step.danger_message) || "Pay close attention to safety constraints during this stage.";
        lines.push(`> **Warning:** ${warning.replace(/\n\n/g, "\n>\n> ")}`, "");
      }

      const components = Array.isArray(step.affected_components)
        ? step.affected_components.map(inlineCode).filter(Boolean)
        : [];
      if (components.length) lines.push(`**Components:** ${components.join(", ")}`, "");
    });
  } else {
    lines.push("_No build instructions are available._", "");
  }

  lines.push("## Safety Audit", "");

  if (issues?.length) {
    issues.forEach((issue) => {
      lines.push(`### ${headingText(issueHeading(issue), "Audit note")}`, "");

      const issueDescription = paragraphText(issue.description);
      if (issueDescription) lines.push(issueDescription, "");

      const troubleshooting = paragraphText(issue.troubleshooting);
      if (troubleshooting) lines.push(`**Suggested action:** ${troubleshooting}`, "");
    });
  } else {
    lines.push("_No safety issues were reported._", "");
  }

  return `${lines.join("\n").trimEnd()}\n`;
}

export function docsExportFilename(title?: string | null) {
  const basename = singleLine(title)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[’']/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "blueprint_project";

  return `${basename}_build_instructions.md`;
}
