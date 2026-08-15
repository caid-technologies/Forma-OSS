"""Generate a Forma project with Ollama and Firecrawl web research."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from blueprint_core.config import config


load_dotenv()

OLLAMA_MODEL = config.get("OLLAMA_MODEL", "qwen3:8b") or "qwen3:8b"
OLLAMA_BASE_URL = (
    config.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    or "http://127.0.0.1:11434/v1"
)
DATABASE_PATH = Path(__file__).resolve().with_name("forma-web-research.db")

# Configure the runtime before importing generation modules. The web-research
# workflow uses Firecrawl instead of component_templates and saves the completed
# project to a standalone SQLite database without seeding component templates.
config.update(
    {
        "BLUEPRINT_DEV_MODE": "true",
        "BLUEPRINT_DISABLE_GENERATION_FALLBACK": "true",
        "BLUEPRINT_STRICT_GENERATION": "true",
        "LLM_DISABLE_FALLBACK": "true",
        "LLM_PROVIDER": "openai-compatible",
        "LLM_ALLOWED_PROVIDERS": "openai-compatible",
        "LLM_BASE_URL": OLLAMA_BASE_URL,
        "LLM_MODEL": OLLAMA_MODEL,
        "OPENAI_COMPATIBLE_ALLOWED_MODELS": OLLAMA_MODEL,
        "LLM_ALLOW_NO_API_KEY": "true",
        "LLM_RESPONSE_FORMAT": "json_object",
        "OPENAI_FALLBACK_MODEL": "",
        "LLM_FALLBACK_MODEL": "",
        "LLM_TIMEOUT_SECONDS": "1200",
        "IMAGE_OUTPUT_ENABLED": "false",
        "EXTERNAL_SOURCE_PROVIDER": "firecrawl",
        "DATABASE_BACKEND": "sqlite",
        "SQLITE_DATABASE_URL": f"sqlite:///{DATABASE_PATH}",
    }
)
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


def validate_local_runtime() -> None:
    """Fail early when Ollama or Firecrawl prerequisites are missing."""
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
    """Generate a Forma project using Ollama and Firecrawl research."""
    validate_local_runtime()
    init_db()

    project_id = uuid4()
    hardware_ir = generate_project_with_workflow(
        "web_research",
        prompt,
        provider_name="openai-compatible",
        model_name=OLLAMA_MODEL,
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
    debug = get_workflow_debug_config(
        "web_research",
        provider_name="openai-compatible",
        model_name=OLLAMA_MODEL,
        external_source_provider="firecrawl",
    )
    print(f"Ollama model: {OLLAMA_MODEL}")
    print(f"Ollama endpoint: {OLLAMA_BASE_URL}")
    print(f"Firecrawl configured: {debug['external_sources']['enabled']}")
    print(f"SQLite metadata database: {DATABASE_PATH}")

    project = generate_project()
    print(project.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
