"""Generate a Forma project with Vertex AI and Firecrawl web research."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from blueprint_core.config import config


load_dotenv()



VERTEX_MODEL = config.get("VERTEX_AI_MODEL", "gemini-3.5-flash") or "gemini-3.5-flash"
VERTEX_PROJECT = config.first(
    (
        "VERTEX_AI_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_PROJECT_ID",
        "GCLOUD_PROJECT",
    ),
)
VERTEX_LOCATION = config.first(
    ("VERTEX_AI_LOCATION", "GOOGLE_CLOUD_LOCATION"),
    "global",
) or "global"
DATABASE_PATH = Path(__file__).resolve().with_name("forma-web-research.db")

# Configure the runtime before importing generation modules. Vertex AI uses
# Google Cloud Application Default Credentials; Firecrawl supplies current
# component and datasheet research to the web-research workflow.
config.update(
    {
        "BLUEPRINT_DEV_MODE": "true",
        "BLUEPRINT_DISABLE_GENERATION_FALLBACK": "true",
        "BLUEPRINT_STRICT_GENERATION": "true",
        "STRICT_LLM": "true",
        "LLM_DISABLE_FALLBACK": "true",
        "LLM_PROVIDER": "vertex",
        "LLM_ALLOWED_PROVIDERS": "vertex",
        "LLM_MODEL": VERTEX_MODEL,
        "VERTEX_AI_MODEL": VERTEX_MODEL,
        "VERTEX_AI_ALLOWED_MODELS": VERTEX_MODEL,
        "LLM_FALLBACK_MODEL": "",
        "LLM_TIMEOUT_SECONDS": "1200",
        "IMAGE_OUTPUT_ENABLED": "false",
        "EXTERNAL_SOURCE_PROVIDER": "firecrawl",
        "DATABASE_BACKEND": "sqlite",
        "SQLITE_DATABASE_URL": f"sqlite:///{DATABASE_PATH}",
    }
)
config.set_default("VERTEX_AI_LOCATION", VERTEX_LOCATION)
config.set_default("FIRECRAWL_SEARCH_LIMIT", "3")
config.set_default("FIRECRAWL_MCP_TIMEOUT_SECONDS", "90")

from blueprint_core.agents.workflows import (  # noqa: E402
    generate_project_with_workflow,
    get_workflow_debug_config,
)
from blueprint_core.database import init_db  # noqa: E402
from blueprint_core.workspaces.projects.objects import (  # noqa: E402
    FormaProjectObject,
    attach_project_object_metadata,
    build_project_object,
)


PROMPT = (
    "Design a compact desktop environmental monitor using an ESP32, a real "
    "temperature and humidity sensor, an OLED display, and USB-C power. Research "
    "real components, datasheets, sourcing references, wiring requirements, and "
    "a practical 3D-printable enclosure."
)


def validate_runtime() -> None:
    """Fail early when Vertex AI or Firecrawl prerequisites are missing."""
    if not VERTEX_PROJECT:
        raise RuntimeError(
            "Set GOOGLE_CLOUD_PROJECT or VERTEX_AI_PROJECT before running this example."
        )

    try:
        __import__("google.genai")
    except ImportError as exc:
        raise RuntimeError(
            "Vertex AI support requires google-genai. Install it with "
            "`pip install -e '.[vertex]'`."
        ) from exc

    firecrawl_api_key = config.optional("FIRECRAWL_API_KEY")
    firecrawl_command = config.optional("FIRECRAWL_MCP_COMMAND")

    if not firecrawl_api_key and not firecrawl_command:
        raise RuntimeError(
            "Set FIRECRAWL_API_KEY or FIRECRAWL_MCP_COMMAND before running this example."
        )

    if firecrawl_api_key and not firecrawl_command and shutil.which("npx") is None:
        raise RuntimeError(
            "Firecrawl defaults to 'npx -y firecrawl-mcp', but npx is not installed."
        )


def generate_project(prompt: str = PROMPT) -> FormaProjectObject:
    """Generate a Forma project object using Vertex AI and Firecrawl research."""
    validate_runtime()
    init_db()

    project_id = uuid4()
    hardware_ir = generate_project_with_workflow(
        "web_research",
        prompt,
        provider_name="vertex",
        model_name=VERTEX_MODEL,
        external_source_provider="firecrawl",
        generation_metadata={
            "project_id": str(project_id),
            "project_prompt": prompt,
        },
    )

    hardware_ir = attach_project_object_metadata(hardware_ir)
    return build_project_object(hardware_ir)


def main() -> None:
    """Validate configuration, generate the project, and print its JSON."""
    validate_runtime()
    debug = get_workflow_debug_config(
        "web_research",
        provider_name="vertex",
        model_name=VERTEX_MODEL,
        external_source_provider="firecrawl",
    )
    print(f"Vertex AI project: {VERTEX_PROJECT}")
    print(f"Vertex AI location: {VERTEX_LOCATION}")
    print(f"Vertex AI model: {VERTEX_MODEL}")
    print(f"Firecrawl configured: {debug['external_sources']['enabled']}")
    print(f"SQLite metadata database: {DATABASE_PATH}")

    project = generate_project()
    print(project.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
