import asyncio
import base64
import contextlib
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from blueprint_core.agents.workflows import (
    generate_project_with_workflow,
    get_workflow_debug_config,
    list_workflows,
    normalize_workflow_id,
)
from blueprint_core.agents.orchestrator import HardwarePipelineOrchestrator
from blueprint_core.database import update_generated_project_hardware_ir
from blueprint_core.images import build_image_provider, build_project_visual_spec, get_image_output_debug_config
from backend.job_store import JOB_STORE
from blueprint_core.llm import get_llm_runtime_debug_config
from blueprint_core.models import ComponentInstance, ConnectionNet
from blueprint_core.observability import (
    get_langfuse_debug_config,
    propagate_observation_attributes,
    serialize_for_langfuse,
    start_observation,
    update_observation,
)
from blueprint_core.pipeline import emit_agent_pipeline_event, observe_agent_pipeline
from blueprint_core.runtime import (
    AlphaGenerationUnavailableError,
    deployment_runtime_config,
    generation_unavailable_message,
)
from backend.storage import get_image_storage_config, upload_image_to_supabase_s3
from blueprint_core.utils import generate_mermaid_chart, generate_svg_schematic
from blueprint_core.validation import validate_circuit


logger = logging.getLogger(__name__)

BLUEPRINT_AGENT_ID = "blueprint"
SERVER_RECIPIENTS = {BLUEPRINT_AGENT_ID, "server", "hardware_pipeline", "hardware-compiler"}


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _payload_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class A2AAgentRegistration(BaseModel):
    agent_id: Optional[str] = Field(None, description="Stable agent identifier")
    name: Optional[str] = Field(None, description="Human-readable agent name")
    capabilities: List[str] = Field(default_factory=list, description="Capability labels this agent provides")
    transports: List[str] = Field(default_factory=list, description="Transports the agent can use")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional agent metadata")


class A2AMessage(BaseModel):
    job_id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex}")
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    type: str = Field("task", description="Message type such as task, event, result, error, or ping")
    action: str = Field("blueprint.generate_project", description="Action name or tool name")
    sender: str = Field("anonymous", description="Sending agent id")
    recipient: str = Field(BLUEPRINT_AGENT_ID, description="Recipient agent id")
    correlation_id: Optional[str] = Field(None, description="Optional id used to correlate request/result pairs")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Message-specific JSON payload")


class A2AEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    job_id: Optional[str] = None
    message_id: Optional[str] = None
    correlation_id: Optional[str] = None
    type: str = "event"
    action: str
    sender: str = BLUEPRINT_AGENT_ID
    recipient: str
    created_at: str = Field(default_factory=_utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)


class A2AHub:
    """In-memory event broker for lightweight agent-to-agent handoffs."""

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue[A2AEvent]] = {}
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._history: Dict[str, List[A2AEvent]] = {}
        self._lock = asyncio.Lock()

    async def register(self, agent_id: str, registration: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with self._lock:
            if agent_id not in self._queues:
                self._queues[agent_id] = asyncio.Queue()
            current = self._agents.get(agent_id, {})
            self._agents[agent_id] = {
                **current,
                **(registration or {}),
                "agent_id": agent_id,
                "last_seen_at": _utc_now(),
            }
            self._history.setdefault(agent_id, [])
            return self._agents[agent_id]

    async def publish(self, event: A2AEvent) -> A2AEvent:
        await self.register(event.recipient)
        queue = self._queues[event.recipient]
        await queue.put(event)
        history = self._history.setdefault(event.recipient, [])
        history.append(event)
        del history[:-100]
        return event

    async def poll(self, agent_id: str, timeout: float = 25.0, limit: int = 10) -> List[A2AEvent]:
        await self.register(agent_id)
        queue = self._queues[agent_id]
        events: List[A2AEvent] = []

        if limit <= 0:
            return events

        if queue.empty() and timeout > 0:
            try:
                events.append(await asyncio.wait_for(queue.get(), timeout=timeout))
            except asyncio.TimeoutError:
                return events

        while len(events) < limit:
            try:
                events.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        return events

    def snapshot(self) -> Dict[str, Any]:
        return {
            "agents": list(self._agents.values()),
            "queued_events": {agent_id: queue.qsize() for agent_id, queue in self._queues.items()},
        }


A2A_HUB = A2AHub()


def _lattice_registry():
    from blueprint_core.lattice import LatticeRegistry
    from blueprint_core.lattice_agents import default_namespace_agent_cards
    from fabricator import fabricator_lattice_card

    return LatticeRegistry([*default_namespace_agent_cards(), fabricator_lattice_card()])


def get_a2a_capabilities() -> Dict[str, Any]:
    try:
        llm_runtime = get_llm_runtime_debug_config()
    except Exception as exc:
        llm_runtime = {"error": str(exc)}

    return {
        "agent_id": BLUEPRINT_AGENT_ID,
        "name": "Blueprint OSS Hardware Compiler",
        "transports": {
            "rest": {
                "capabilities": "/api/a2a/capabilities",
                "register": "/api/a2a/agents/{agent_id}",
                "send_message": "/api/a2a/messages",
                "listen": "/api/a2a/agents/{agent_id}/events",
            },
            "websocket": {"listen": "/api/a2a/socket/{agent_id}"},
            "tcp_jsonl": {
                "enabled_env": "A2A_SOCKET_ENABLED=true",
                "host_env": "A2A_SOCKET_HOST",
                "port_env": "A2A_SOCKET_PORT",
            },
            "mcp": {
                "endpoint": "/api/mcp",
                "alias": "/api/a2a/mcp",
                "tools": [
                    "blueprint.generate_project",
                    "blueprint.debug_config",
                    "blueprint.validate_circuit",
                    "blueprint.a2a.send_message",
                    "blueprint.a2a.poll_events",
                    "blueprint.a2a.get_job",
                    "blueprint.a2a.list_jobs",
                    "blueprint.lattice.list_agents",
                    "blueprint.lattice.get_agent_card",
                ],
            },
        },
        "job_metadata": JOB_STORE.get_config(),
        "llm_runtime": llm_runtime,
        "image_output": get_image_output_debug_config(),
        "image_storage": get_image_storage_config(),
        "observability": get_langfuse_debug_config(),
        "workflows": list_workflows(),
        "actions": [
            "blueprint.generate_project",
            "blueprint.debug_config",
            "blueprint.validate_circuit",
            "blueprint.a2a.capabilities",
            "blueprint.a2a.get_job",
            "blueprint.a2a.list_jobs",
            "blueprint.lattice.list_agents",
            "blueprint.lattice.get_agent_card",
            "a2a.ping",
        ],
        "lattice": _lattice_registry().manifest(),
        "hub": A2A_HUB.snapshot(),
    }


def _decode_image_data(image_data: Optional[str]) -> Tuple[Optional[bytes], Optional[str]]:
    if not image_data:
        return None, None

    base64_data = image_data.strip()
    image_mime_type = None
    if "," in image_data:
        header, base64_data = image_data.split(",", 1)
        if "data:" in header and ";base64" in header:
            image_mime_type = header.split(";")[0].replace("data:", "")
        base64_data = base64_data.strip()

    return base64.b64decode(base64_data), image_mime_type or "image/png"


def _attach_stored_image_metadata(
    ir: Any,
    *,
    image_data: str,
    metadata_prefix: str,
    object_prefix: str,
    fallback_content_type: str = "image/png",
    allow_remote_url: bool = False,
) -> Dict[str, Any]:
    metadata = ir.assembly_metadata or {}
    project_id = metadata.get("project_id")
    try:
        stored = upload_image_to_supabase_s3(
            image_data,
            prefix=object_prefix,
            project_id=project_id,
            fallback_content_type=fallback_content_type,
            allow_remote_url=allow_remote_url,
        )
    except Exception as exc:
        logger.warning("Image upload to Supabase Storage failed for %s: %s", metadata_prefix, exc)
        return {
            f"{metadata_prefix}_storage_error": str(exc)[:500],
            f"{metadata_prefix}_storage_bucket": get_image_storage_config().get("bucket"),
        }

    if not stored:
        return {
            f"{metadata_prefix}_storage_enabled": False,
            f"{metadata_prefix}_storage_bucket": get_image_storage_config().get("bucket"),
        }
    return {
        **stored.metadata(metadata_prefix),
        f"{metadata_prefix}_storage_enabled": True,
    }


def _operation_summary(operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"succeeded": 0, "failed": 0, "pending": 0, "not_requested": 0}
    for operation in operations:
        status = str(operation.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "total": len(operations),
        "failed": counts.get("failed", 0),
        "succeeded": counts.get("succeeded", 0),
        "pending": counts.get("pending", 0),
        "not_requested": counts.get("not_requested", 0),
        "ok": counts.get("failed", 0) == 0,
    }


def _set_operation_status(
    ir: Any,
    operation_id: str,
    *,
    label: str,
    status: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    requested: Optional[bool] = None,
    enabled: Optional[bool] = None,
    configured: Optional[bool] = None,
    reason: Optional[str] = None,
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    metadata = dict(ir.assembly_metadata or {})
    operations = [
        item for item in metadata.get("operation_statuses", [])
        if isinstance(item, dict) and item.get("id") != operation_id
    ]
    record: Dict[str, Any] = {
        "id": operation_id,
        "label": label,
        "status": status,
    }
    optional_values = {
        "provider": provider,
        "model": model,
        "requested": requested,
        "enabled": enabled,
        "configured": configured,
        "reason": reason,
        "error": error,
        "error_type": error_type,
        "details": details,
    }
    for key, value in optional_values.items():
        if value is not None:
            record[key] = value

    operations.append(record)
    metadata["operation_statuses"] = operations
    metadata["operation_summary"] = _operation_summary(operations)
    ir.assembly_metadata = metadata


def _attach_product_image(prompt_text: str, ir: Any, generate_image: bool = False) -> None:
    image_provider = build_image_provider(force_enabled=generate_image)
    image_config = image_provider.get_debug_config()
    visual_spec = build_project_visual_spec(prompt_text, ir)
    image_status = "pending" if generate_image else "not_requested"
    metadata = {
        **(ir.assembly_metadata or {}),
        "image_output_requested": generate_image,
        "image_output_enabled": image_config.get("enabled", False),
        "image_output_provider": image_config.get("provider"),
        "image_output_model": image_config.get("model_name"),
        "image_output_configured": image_config.get("configured", False),
        "image_output_status": image_status,
        "image_output_reason": image_config.get("reason"),
        "product_visual_spec": visual_spec,
    }
    ir.assembly_metadata = metadata
    _set_operation_status(
        ir,
        "image_generation",
        label="Image generation",
        status=image_status,
        provider=image_config.get("provider"),
        model=image_config.get("model_name"),
        requested=generate_image,
        enabled=image_config.get("enabled", False),
        configured=image_config.get("configured", False),
        reason=image_config.get("reason"),
    )

    if not generate_image:
        return

    if not image_config.get("configured", False):
        error_message = image_config.get("reason") or "Image output was requested, but the image provider is not configured."
        logger.warning(
            "Image generation operation failed before request: provider=%s model=%s reason=%s",
            image_config.get("provider"),
            image_config.get("model_name"),
            error_message,
        )
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "image_output_status": "failed",
            "image_output_failed": True,
            "image_output_error": str(error_message)[:500],
            "image_output_error_type": "configuration",
            "product_image_error": str(error_message)[:500],
        }
        _set_operation_status(
            ir,
            "image_generation",
            label="Image generation",
            status="failed",
            provider=image_config.get("provider"),
            model=image_config.get("model_name"),
            requested=True,
            enabled=image_config.get("enabled", False),
            configured=False,
            reason=image_config.get("reason"),
            error=str(error_message)[:500],
            error_type="configuration",
        )
        return

    try:
        generated_images = image_provider.generate_project_image_sequence(prompt_text, ir)
    except Exception as exc:
        logger.warning(
            "Image generation operation failed: provider=%s model=%s error_type=%s error=%s",
            image_config.get("provider"),
            image_config.get("model_name"),
            exc.__class__.__name__,
            exc,
        )
        error_message = str(exc)[:500]
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "image_output_status": "failed",
            "image_output_failed": True,
            "image_output_error": error_message,
            "image_output_error_type": exc.__class__.__name__,
            "product_image_error": error_message,
        }
        _set_operation_status(
            ir,
            "image_generation",
            label="Image generation",
            status="failed",
            provider=image_config.get("provider"),
            model=image_config.get("model_name"),
            requested=True,
            enabled=image_config.get("enabled", False),
            configured=image_config.get("configured", False),
            error=error_message,
            error_type=exc.__class__.__name__,
        )
        return

    if not generated_images:
        error_message = "Image output was requested, but the image provider returned no images."
        logger.warning(
            "Image generation operation failed: provider=%s model=%s error_type=empty_response error=%s",
            image_config.get("provider"),
            image_config.get("model_name"),
            error_message,
        )
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "image_output_status": "failed",
            "image_output_failed": True,
            "image_output_error": error_message,
            "image_output_error_type": "empty_response",
            "product_image_error": error_message,
            "product_visual_sequence_count": 0,
        }
        _set_operation_status(
            ir,
            "image_generation",
            label="Image generation",
            status="failed",
            provider=image_config.get("provider"),
            model=image_config.get("model_name"),
            requested=True,
            enabled=image_config.get("enabled", False),
            configured=image_config.get("configured", False),
            error=error_message,
            error_type="empty_response",
        )
        return

    product_metadata: Dict[str, Any] = {
        "image_output_status": "succeeded",
        "image_output_failed": False,
        "image_output_error": None,
        "image_output_error_type": None,
        "image_output_generated_count": len(generated_images),
        "product_image_error": None,
        "product_visual_sequence_count": len(generated_images),
    }
    product_visual_sequence: List[Dict[str, Any]] = []

    for index, generated_image in enumerate(generated_images):
        view_id = generated_image.view_id or f"view_{index + 1}"
        metadata_prefix = f"product_{view_id}_image"
        object_prefix = f"product-{view_id}"
        storage_metadata = _attach_stored_image_metadata(
            ir,
            image_data=generated_image.data_url,
            metadata_prefix=metadata_prefix,
            object_prefix=object_prefix,
            fallback_content_type=f"image/{generated_image.output_format or 'png'}",
            allow_remote_url=True,
        )
        image_url = storage_metadata.get(f"{metadata_prefix}_url")
        image_record: Dict[str, Any] = {
            "view_id": view_id,
            "label": generated_image.label,
            "provider": generated_image.provider,
            "model": generated_image.model,
            "size": generated_image.size,
            "output_format": generated_image.output_format,
            "prompt": generated_image.prompt,
            "prompt_original_length": generated_image.prompt_original_length,
            "prompt_final_length": generated_image.prompt_final_length,
            "prompt_compacted": generated_image.prompt_compacted,
            "prompt_compaction_strategy": generated_image.prompt_compaction_strategy,
            "reference_view_id": generated_image.reference_view_id,
            "url": image_url,
            "content_type": storage_metadata.get(f"{metadata_prefix}_content_type"),
            "s3_bucket": storage_metadata.get(f"{metadata_prefix}_s3_bucket"),
            "s3_key": storage_metadata.get(f"{metadata_prefix}_s3_key"),
            "storage_method": storage_metadata.get(f"{metadata_prefix}_storage_method"),
            "storage_error": storage_metadata.get(f"{metadata_prefix}_storage_error"),
        }
        if not image_url:
            image_record["data"] = generated_image.data_url
            product_metadata[f"{metadata_prefix}_data"] = generated_image.data_url

        product_visual_sequence.append(image_record)
        product_metadata.update(storage_metadata)

        if index == 0:
            product_metadata.update(
                {
                    "product_image_provider": generated_image.provider,
                    "product_image_model": generated_image.model,
                    "product_image_size": generated_image.size,
                    "product_image_output_format": generated_image.output_format,
                    "product_image_prompt": generated_image.prompt,
                    "product_image_prompt_original_length": generated_image.prompt_original_length,
                    "product_image_prompt_final_length": generated_image.prompt_final_length,
                    "product_image_prompt_compacted": generated_image.prompt_compacted,
                    "product_image_prompt_compaction_strategy": generated_image.prompt_compaction_strategy,
                    "product_image_url": image_url,
                    "product_image_content_type": storage_metadata.get(f"{metadata_prefix}_content_type"),
                    "product_image_s3_bucket": storage_metadata.get(f"{metadata_prefix}_s3_bucket"),
                    "product_image_s3_key": storage_metadata.get(f"{metadata_prefix}_s3_key"),
                    "product_image_storage_method": storage_metadata.get(f"{metadata_prefix}_storage_method"),
                }
            )
            if not image_url:
                product_metadata["product_image_data"] = generated_image.data_url

    product_metadata["product_visual_sequence"] = product_visual_sequence

    ir.assembly_metadata = {
        **(ir.assembly_metadata or {}),
        **product_metadata,
    }
    storage_errors = [
        record.get("storage_error")
        for record in product_visual_sequence
        if isinstance(record, dict) and record.get("storage_error")
    ]
    _set_operation_status(
        ir,
        "image_generation",
        label="Image generation",
        status="succeeded",
        provider=image_config.get("provider"),
        model=image_config.get("model_name"),
        requested=True,
        enabled=image_config.get("enabled", False),
        configured=image_config.get("configured", False),
        details={"generated_count": len(generated_images)},
    )
    _set_operation_status(
        ir,
        "image_storage",
        label="Image storage",
        status="failed" if storage_errors else "succeeded",
        requested=True,
        enabled=True,
        configured=True,
        error=str(storage_errors[0])[:500] if storage_errors else None,
        error_type="storage_upload" if storage_errors else None,
        details={"stored_count": len([record for record in product_visual_sequence if isinstance(record, dict) and record.get("url")])},
    )


def _persist_updated_project_ir(ir: Any) -> None:
    metadata = ir.assembly_metadata or {}
    project_id = metadata.get("project_id")
    if not project_id:
        return

    try:
        update_generated_project_hardware_ir(project_id, ir.model_dump())
    except Exception as exc:
        logger.warning("Failed to persist updated project metadata for %s: %s", project_id, exc)


def build_generation_response(
    prompt: str,
    image_data: Optional[str] = None,
    generate_image: bool = False,
    workflow: str = "default",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    external_source_provider: Optional[str] = None,
    chat_id: Optional[str] = None,
    source_project_id: Optional[str] = None,
    frontend_job_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    prompt_text = (prompt or "").strip()
    workflow_id = normalize_workflow_id(workflow)
    has_prompt = bool(prompt_text)
    if not has_prompt and not image_data:
        raise ValueError("Provide a prompt or reference image.")
    if not has_prompt:
        prompt_text = "Infer a buildable hardware project from the uploaded reference image."

    try:
        image_bytes, image_mime_type = _decode_image_data(image_data)
    except Exception as exc:
        if not has_prompt:
            raise ValueError("Reference image could not be decoded.") from exc
        image_bytes, image_mime_type = None, None

    llm_config = get_workflow_debug_config(
        workflow_id,
        provider_name=provider,
        model_name=model,
        external_source_provider=external_source_provider,
    )
    if deployment_runtime_config(llm_config)["alpha_generation_gate_active"]:
        raise AlphaGenerationUnavailableError(generation_unavailable_message(llm_config))

    trace_metadata = {
        "workflow": workflow_id,
        "chat_id": chat_id,
        "source_project_id": source_project_id,
        "owner_user_id": owner_user_id,
        "requested_provider": provider,
        "requested_model": model,
        "runtime_provider": (llm_config.get("runtime") or {}).get("runtime_provider"),
        "runtime_model": (llm_config.get("runtime") or {}).get("runtime_model"),
        "has_reference_image": bool(image_data),
        "image_mime_type": image_mime_type,
        "generate_image": generate_image,
        "frontend_job_id": frontend_job_id,
        "external_source_provider": external_source_provider,
    }
    with start_observation(
        name="blueprint.generate_project",
        as_type="span",
        input={
            "prompt": prompt_text,
            "workflow": workflow_id,
            "provider": provider,
            "model": model,
            "external_source_provider": external_source_provider,
            "has_reference_image": bool(image_data),
            "generate_image": generate_image,
        },
        metadata=trace_metadata,
    ) as root_observation:
        with propagate_observation_attributes(
            trace_name="blueprint.generate_project",
            metadata=trace_metadata,
            tags=["blueprint", f"workflow:{workflow_id}"],
        ):
            ir = generate_project_with_workflow(
                workflow_id,
                prompt_text,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                provider_name=provider,
                model_name=model,
                external_source_provider=external_source_provider,
                generation_metadata={
                    "chat_id": chat_id,
                    "source_project_id": source_project_id,
                    "frontend_job_id": frontend_job_id,
                    "owner_user_id": owner_user_id,
                    "external_source_provider": external_source_provider,
                },
            )
            ir.assembly_metadata = {
                **(ir.assembly_metadata or {}),
                "chat_id": chat_id or (ir.assembly_metadata or {}).get("chat_id"),
                "source_project_id": source_project_id or (ir.assembly_metadata or {}).get("source_project_id"),
                "frontend_job_id": frontend_job_id or (ir.assembly_metadata or {}).get("frontend_job_id"),
                "workflow": workflow_id,
                "external_source_provider": external_source_provider or (ir.assembly_metadata or {}).get("external_source_provider"),
            }

            if image_data:
                metadata = ir.assembly_metadata or {}
                storage_metadata = _attach_stored_image_metadata(
                    ir,
                    image_data=image_data,
                    metadata_prefix="reference_image",
                    object_prefix="reference",
                    fallback_content_type=image_mime_type or "image/png",
                )
                reference_metadata: Dict[str, Any] = {
                    **storage_metadata,
                    "image_features": metadata.get("image_features") or ir.constraints[:12],
                    "input_mode": "prompt_image",
                }
                if not storage_metadata.get("reference_image_url"):
                    reference_metadata["reference_image_data"] = image_data
                ir.assembly_metadata = {
                    **metadata,
                    **reference_metadata,
                }

            if generate_image:
                emit_agent_pipeline_event(workflow_id, "image_generation", "started")
            _attach_product_image(prompt_text, ir, generate_image=generate_image)
            if generate_image:
                image_status = (ir.assembly_metadata or {}).get("image_output_status")
                emit_agent_pipeline_event(
                    workflow_id,
                    "image_generation",
                    "failed" if image_status == "failed" else "completed",
                    details={"image_output_status": image_status},
                )
            _persist_updated_project_ir(ir)

            response = {
                "project_id": (ir.assembly_metadata or {}).get("project_id"),
                "chat_id": (ir.assembly_metadata or {}).get("chat_id"),
                "project_ir": ir.model_dump(),
                "mermaid_code": generate_mermaid_chart(ir),
                "svg_schematic": generate_svg_schematic(ir),
            }
            update_observation(
                root_observation,
                output={
                    "project_id": (ir.assembly_metadata or {}).get("project_id"),
                    "chat_id": (ir.assembly_metadata or {}).get("chat_id"),
                    "title": ir.overview.title if ir.overview else None,
                    "is_valid": ir.is_valid,
                    "component_count": len(ir.components),
                    "net_count": len(ir.nets),
                    "workflow": workflow_id,
                },
                metadata={
                    **trace_metadata,
                    "project_id": (ir.assembly_metadata or {}).get("project_id"),
                    "chat_id": (ir.assembly_metadata or {}).get("chat_id"),
                    "llm_provider": (ir.assembly_metadata or {}).get("llm_provider"),
                    "model_name": (ir.assembly_metadata or {}).get("model_name"),
                    "runtime_provider": (ir.assembly_metadata or {}).get("runtime_provider"),
                    "runtime_model": (ir.assembly_metadata or {}).get("runtime_model"),
                    "response_summary": serialize_for_langfuse(
                        {
                            "has_mermaid": bool(response["mermaid_code"]),
                            "has_svg_schematic": bool(response["svg_schematic"]),
                        }
                    ),
                },
            )
            return response


async def call_blueprint_action(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = action.removeprefix("blueprint.")

    if normalized == "generate_project":
        return await asyncio.to_thread(
            build_generation_response,
            payload.get("prompt", ""),
            payload.get("image_data"),
            _payload_bool(payload.get("generate_image"), default=False),
            payload.get("workflow", "default"),
            payload.get("provider"),
            payload.get("model"),
            payload.get("external_source_provider"),
            payload.get("chat_id"),
            payload.get("source_project_id"),
            payload.get("client_job_id") or payload.get("frontend_job_id"),
            payload.get("owner_user_id"),
        )

    if normalized == "debug_config":
        orchestrator = HardwarePipelineOrchestrator(
            provider_name=payload.get("provider"),
            model_name=payload.get("model"),
        )
        return {
            **orchestrator.get_debug_config(),
            "image_output": get_image_output_debug_config(),
            "image_storage": get_image_storage_config(),
            "observability": get_langfuse_debug_config(),
            "workflows": list_workflows(),
        }

    if normalized == "validate_circuit":
        components = [ComponentInstance.model_validate(component) for component in payload.get("components", [])]
        nets = [ConnectionNet.model_validate(net) for net in payload.get("nets", [])]
        issues = validate_circuit(components, nets)
        return {
            "is_valid": not any(issue.severity.upper() == "CRITICAL" for issue in issues),
            "issues": [issue.model_dump() for issue in issues],
        }

    if normalized in {"a2a.capabilities", "capabilities"}:
        return get_a2a_capabilities()

    if action == "a2a.ping" or normalized == "ping":
        return {"pong": True, "server_time": _utc_now()}

    raise ValueError(f"Unsupported Blueprint A2A action: {action}")


def _is_server_message(message: A2AMessage) -> bool:
    return message.recipient in SERVER_RECIPIENTS or message.action.startswith("blueprint.")


async def submit_a2a_message(message: A2AMessage) -> A2AEvent:
    await A2A_HUB.register(message.sender)
    server_owned = _is_server_message(message)
    job = JOB_STORE.create_job(
        job_id=message.job_id,
        message_id=message.message_id,
        correlation_id=message.correlation_id,
        action=message.action,
        sender=message.sender,
        recipient=message.recipient,
        payload=message.payload,
        server_owned=server_owned,
        status="queued" if server_owned else "accepted",
    )

    ack = A2AEvent(
        job_id=message.job_id,
        message_id=message.message_id,
        correlation_id=message.correlation_id,
        type="ack",
        action=message.action,
        sender=BLUEPRINT_AGENT_ID,
        recipient=message.sender,
        payload={"accepted": True, "server_owned": server_owned, "job_id": message.job_id, "job": job},
    )
    await A2A_HUB.publish(ack)

    if server_owned:
        asyncio.create_task(_process_server_message(message))
    else:
        JOB_STORE.mark_routed(message.job_id)
        await A2A_HUB.publish(
            A2AEvent(
                job_id=message.job_id,
                message_id=message.message_id,
                correlation_id=message.correlation_id,
                type=message.type,
                action=message.action,
                sender=message.sender,
                recipient=message.recipient,
                payload=message.payload,
            )
        )

    return ack


async def _process_server_message(message: A2AMessage) -> None:
    JOB_STORE.mark_running(message.job_id)
    try:
        with observe_agent_pipeline(lambda event: JOB_STORE.append_progress_event(message.job_id, event.as_dict())):
            result = await call_blueprint_action(message.action, message.payload)
        JOB_STORE.mark_succeeded(message.job_id, result)
        event = A2AEvent(
            job_id=message.job_id,
            message_id=message.message_id,
            correlation_id=message.correlation_id,
            type="result",
            action=message.action,
            sender=BLUEPRINT_AGENT_ID,
            recipient=message.sender,
            payload=result,
        )
    except Exception as exc:
        JOB_STORE.mark_failed(message.job_id, str(exc))
        event = A2AEvent(
            job_id=message.job_id,
            message_id=message.message_id,
            correlation_id=message.correlation_id,
            type="error",
            action=message.action,
            sender=BLUEPRINT_AGENT_ID,
            recipient=message.sender,
            payload={"error": str(exc)},
        )

    await A2A_HUB.publish(event)


async def handle_a2a_websocket(websocket: WebSocket, agent_id: str) -> None:
    await websocket.accept()
    await A2A_HUB.register(agent_id, {"transports": ["websocket"]})

    sender_task = asyncio.create_task(_websocket_sender(websocket, agent_id))
    try:
        await A2A_HUB.publish(
            A2AEvent(
                type="ready",
                action="a2a.connected",
                sender=BLUEPRINT_AGENT_ID,
                recipient=agent_id,
                payload=get_a2a_capabilities(),
            )
        )
        while True:
            raw_message = await websocket.receive_json()
            if isinstance(raw_message, dict) and raw_message.get("jsonrpc") == "2.0":
                await websocket.send_json(await handle_mcp_json_rpc(raw_message))
                continue

            raw_message = {**raw_message, "sender": raw_message.get("sender") or agent_id}
            await submit_a2a_message(A2AMessage.model_validate(raw_message))
    except WebSocketDisconnect:
        logger.info("A2A websocket disconnected: %s", agent_id)
    finally:
        sender_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender_task


async def _websocket_sender(websocket: WebSocket, agent_id: str) -> None:
    while True:
        events = await A2A_HUB.poll(agent_id, timeout=30.0, limit=10)
        for event in events:
            await websocket.send_json(event.model_dump())


_tcp_server: Optional[asyncio.AbstractServer] = None


async def start_a2a_tcp_server() -> Optional[asyncio.AbstractServer]:
    global _tcp_server
    if _tcp_server is not None or not _env_bool("A2A_SOCKET_ENABLED", default=False):
        return _tcp_server

    host = os.getenv("A2A_SOCKET_HOST", "127.0.0.1")
    port = int(os.getenv("A2A_SOCKET_PORT", "8766"))
    _tcp_server = await asyncio.start_server(_handle_tcp_client, host, port)
    logger.info("A2A TCP JSONL socket listening on %s:%s", host, port)
    return _tcp_server


async def stop_a2a_tcp_server() -> None:
    global _tcp_server
    if _tcp_server is None:
        return
    _tcp_server.close()
    await _tcp_server.wait_closed()
    _tcp_server = None


async def _handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    agent_id = f"tcp_{uuid.uuid4().hex[:12]}"
    await A2A_HUB.register(agent_id, {"transports": ["tcp_jsonl"], "metadata": {"peer": str(peer)}})
    sender_task = asyncio.create_task(_tcp_sender(writer, agent_id))

    await A2A_HUB.publish(
        A2AEvent(
            type="ready",
            action="a2a.connected",
            sender=BLUEPRINT_AGENT_ID,
            recipient=agent_id,
            payload={**get_a2a_capabilities(), "connection_agent_id": agent_id},
        )
    )

    try:
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            try:
                raw_message = json.loads(line.decode("utf-8"))
                raw_message = {**raw_message, "sender": raw_message.get("sender") or agent_id}
                await submit_a2a_message(A2AMessage.model_validate(raw_message))
            except Exception as exc:
                writer.write(json.dumps({"type": "error", "error": str(exc)}).encode("utf-8") + b"\n")
                await writer.drain()
    finally:
        sender_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender_task
        writer.close()
        await writer.wait_closed()


async def _tcp_sender(writer: asyncio.StreamWriter, agent_id: str) -> None:
    while not writer.is_closing():
        events = await A2A_HUB.poll(agent_id, timeout=30.0, limit=10)
        for event in events:
            writer.write(json.dumps(event.model_dump()).encode("utf-8") + b"\n")
            await writer.drain()


def _jsonrpc_result(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _mcp_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(result)}],
        "structuredContent": result,
    }


def _mcp_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "blueprint.generate_project",
            "description": "Generate a Blueprint Hardware IR package, Mermaid diagram, and SVG schematic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "workflow": {
                        "type": "string",
                        "enum": ["default", "web_research"],
                        "default": "default",
                    },
                    "image_data": {"type": "string", "description": "Optional data URL or base64 image"},
                    "generate_image": {"type": "boolean", "default": False},
                    "external_source_provider": {
                        "type": "string",
                        "enum": ["firecrawl"],
                        "description": "Optional provider for web_research workflow.",
                    },
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "blueprint.debug_config",
            "description": "Return configured LLM provider and model resolution details.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "blueprint.validate_circuit",
            "description": "Validate a list of components and nets against Blueprint electrical rules.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "components": {"type": "array", "items": {"type": "object"}},
                    "nets": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["components", "nets"],
            },
        },
        {
            "name": "blueprint.a2a.send_message",
            "description": "Send an A2A message through the Blueprint in-memory broker.",
            "inputSchema": {"type": "object", "properties": A2AMessage.model_json_schema()["properties"]},
        },
        {
            "name": "blueprint.a2a.poll_events",
            "description": "Long-poll queued A2A events for an agent id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "timeout": {"type": "number", "default": 25},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["agent_id"],
            },
        },
        {
            "name": "blueprint.a2a.get_job",
            "description": "Fetch persisted metadata for one A2A job.",
            "inputSchema": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        },
        {
            "name": "blueprint.a2a.list_jobs",
            "description": "List persisted A2A job metadata.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
        {
            "name": "blueprint.lattice.list_agents",
            "description": "List Lattice domain-agent cards registered with Blueprint.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Optional namespace filter, such as product.mech."},
                    "domain": {"type": "string", "description": "Optional domain text filter."},
                    "capability": {"type": "string", "description": "Optional capability id or label filter."},
                    "tool": {"type": "string", "description": "Optional needed-tool text filter."},
                },
            },
        },
        {
            "name": "blueprint.lattice.get_agent_card",
            "description": "Fetch one Lattice domain-agent card by agent id.",
            "inputSchema": {
                "type": "object",
                "properties": {"agent_id": {"type": "string", "default": "fabricator"}},
                "required": ["agent_id"],
            },
        },
    ]


async def handle_mcp_json_rpc(payload: Any) -> Any:
    if isinstance(payload, list):
        return [await _handle_mcp_request(item) for item in payload]
    return await _handle_mcp_request(payload)


async def _handle_mcp_request(request: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(request, dict):
        return _jsonrpc_error(None, -32600, "Invalid JSON-RPC request.")

    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    try:
        if method == "initialize":
            requested_version = params.get("protocolVersion") or os.getenv("MCP_PROTOCOL_VERSION", "2024-11-05")
            return _jsonrpc_result(
                request_id,
                {
                    "protocolVersion": requested_version,
                    "serverInfo": {"name": "blueprint-oss", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            )

        if method in {"notifications/initialized", "ping"}:
            return _jsonrpc_result(request_id, {})

        if method == "tools/list":
            return _jsonrpc_result(request_id, {"tools": _mcp_tools()})

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            result = await _call_mcp_tool(tool_name, arguments)
            return _jsonrpc_result(request_id, _mcp_tool_result(result))

        return _jsonrpc_error(request_id, -32601, f"Unknown MCP method: {method}")
    except Exception as exc:
        return _jsonrpc_error(request_id, -32000, str(exc))


async def _call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "blueprint.a2a.send_message":
        ack = await submit_a2a_message(A2AMessage.model_validate(arguments))
        return ack.model_dump()

    if tool_name == "blueprint.a2a.poll_events":
        events = await A2A_HUB.poll(
            arguments["agent_id"],
            timeout=float(arguments.get("timeout", 25)),
            limit=int(arguments.get("limit", 10)),
        )
        return {"events": [event.model_dump() for event in events]}

    if tool_name == "blueprint.a2a.get_job":
        job = JOB_STORE.get_job(arguments["job_id"])
        if not job:
            raise ValueError("A2A job not found.")
        return job

    if tool_name == "blueprint.a2a.list_jobs":
        return {
            "jobs": JOB_STORE.list_jobs(
                sender=arguments.get("sender"),
                status=arguments.get("status"),
                limit=int(arguments.get("limit", 50)),
            )
        }

    if tool_name == "blueprint.lattice.list_agents":
        registry = _lattice_registry()
        agents = registry.find(
            namespace=arguments.get("namespace"),
            domain=arguments.get("domain"),
            capability=arguments.get("capability"),
            tool=arguments.get("tool"),
        )
        return {
            "name": "Lattice",
            "agents": [agent.model_dump(mode="json") for agent in agents],
        }

    if tool_name == "blueprint.lattice.get_agent_card":
        registry = _lattice_registry()
        return {"agent": registry.get(arguments.get("agent_id", "fabricator")).model_dump(mode="json")}

    return await call_blueprint_action(tool_name, arguments)
