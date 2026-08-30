"""Post-generation project output: product images and canonical persistence."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from forma_core.database import init_db, save_generated_project, update_generated_project_hardware_ir
from forma_core.images import build_image_provider, build_project_visual_spec
from forma_core.persistence.images import get_image_storage_config, upload_image_to_supabase_s3


logger = logging.getLogger(__name__)


ImageProviderFactory = Callable[..., Any]
ImageStorageHandler = Callable[..., Dict[str, Any]]


def _safe_image_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): "<redacted>"
        if any(token in str(key).lower() for token in ("key", "token", "secret", "authorization"))
        else value
        for key, value in (config or {}).items()
    }


def _operation_summary(operations: list[Dict[str, Any]]) -> Dict[str, Any]:
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


def _set_operation(ir: Any, operation_id: str, **record: Any) -> None:
    metadata = dict(ir.assembly_metadata or {})
    operations = [
        item
        for item in metadata.get("operation_statuses", [])
        if isinstance(item, dict) and item.get("id") != operation_id
    ]
    operation = {"id": operation_id, **{key: value for key, value in record.items() if value is not None}}
    operations.append(operation)
    metadata["operation_statuses"] = operations
    metadata["operation_summary"] = _operation_summary(operations)
    ir.assembly_metadata = metadata


def store_project_image(
    ir: Any,
    *,
    image_data: str,
    metadata_prefix: str,
    object_prefix: str,
    fallback_content_type: str = "image/png",
    allow_remote_url: bool = False,
) -> Dict[str, Any]:
    metadata = ir.assembly_metadata or {}
    storage_config = get_image_storage_config()
    try:
        stored = upload_image_to_supabase_s3(
            image_data,
            prefix=object_prefix,
            project_id=metadata.get("project_id"),
            fallback_content_type=fallback_content_type,
            allow_remote_url=allow_remote_url,
        )
    except Exception as exc:
        logger.warning("Image persistence failed for %s: %s", metadata_prefix, exc)
        return {
            f"{metadata_prefix}_storage_error": str(exc)[:500],
            f"{metadata_prefix}_storage_bucket": storage_config.get("bucket"),
        }
    if not stored:
        return {
            f"{metadata_prefix}_storage_enabled": False,
            f"{metadata_prefix}_storage_bucket": storage_config.get("bucket"),
        }
    return {
        **stored.metadata(metadata_prefix),
        f"{metadata_prefix}_storage_enabled": True,
    }


def attach_hardware_reference_image(
    ir: Any,
    image_data: str,
    *,
    media_type: str | None = None,
    storage_handler: ImageStorageHandler = store_project_image,
) -> None:
    """Copy a user-supplied hardware reference onto assembly metadata for INFO/overview."""

    payload = str(image_data or "").strip()
    if not payload:
        return
    metadata = dict(ir.assembly_metadata or {})
    if metadata.get("reference_image_url") or metadata.get("reference_image_data"):
        return
    storage_metadata = storage_handler(
        ir,
        image_data=payload,
        metadata_prefix="reference_image",
        object_prefix="reference",
        fallback_content_type=media_type or "image/png",
        allow_remote_url=True,
    )
    reference_metadata = dict(storage_metadata)
    if not storage_metadata.get("reference_image_url"):
        reference_metadata["reference_image_data"] = payload
        if media_type:
            reference_metadata["reference_image_content_type"] = media_type
    ir.assembly_metadata = {
        **metadata,
        **reference_metadata,
        "input_mode": metadata.get("input_mode") or "prompt_image",
    }


def attach_product_image(
    prompt_text: str,
    ir: Any,
    *,
    generate_image: bool = False,
    provider_factory: ImageProviderFactory = build_image_provider,
    storage_handler: ImageStorageHandler = store_project_image,
) -> None:
    """Generate product visuals and attach UI-compatible metadata to a HardwareIR."""
    image_provider = provider_factory(force_enabled=generate_image)
    image_config = _safe_image_config(image_provider.get_debug_config())
    status = "pending" if generate_image else "not_requested"
    ir.assembly_metadata = {
        **(ir.assembly_metadata or {}),
        "image_output_requested": generate_image,
        "image_output_enabled": image_config.get("enabled", False),
        "image_output_provider": image_config.get("provider"),
        "image_output_model": image_config.get("model_name"),
        "image_output_configured": image_config.get("configured", False),
        "image_output_status": status,
        "image_output_reason": image_config.get("reason"),
        "image_output_debug": image_config,
        "product_visual_spec": build_project_visual_spec(prompt_text, ir),
    }
    _set_operation(
        ir,
        "image_generation",
        label="Image generation",
        status=status,
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
        error = image_config.get("reason") or "Image output was requested, but the provider is not configured."
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "image_output_status": "failed",
            "image_output_failed": True,
            "image_output_error": str(error)[:500],
            "image_output_error_type": "configuration",
            "product_image_error": str(error)[:500],
        }
        _set_operation(
            ir,
            "image_generation",
            label="Image generation",
            status="failed",
            requested=True,
            configured=False,
            error=str(error)[:500],
            error_type="configuration",
        )
        return

    try:
        generated_images = image_provider.generate_project_image_sequence(prompt_text, ir)
    except Exception as exc:
        logger.exception("Image generation failed: %s", exc)
        error = str(exc)[:500]
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "image_output_status": "failed",
            "image_output_failed": True,
            "image_output_error": error,
            "image_output_error_type": exc.__class__.__name__,
            "product_image_error": error,
        }
        _set_operation(
            ir,
            "image_generation",
            label="Image generation",
            status="failed",
            requested=True,
            error=error,
            error_type=exc.__class__.__name__,
        )
        return

    if not generated_images:
        error = "Image provider returned no images."
        ir.assembly_metadata = {
            **(ir.assembly_metadata or {}),
            "image_output_status": "failed",
            "image_output_failed": True,
            "image_output_error": error,
            "image_output_error_type": "empty_response",
            "product_image_error": error,
            "product_visual_sequence_count": 0,
        }
        _set_operation(ir, "image_generation", label="Image generation", status="failed", error=error)
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
    sequence: list[Dict[str, Any]] = []
    for index, image in enumerate(generated_images):
        view_id = image.view_id or f"view_{index + 1}"
        metadata_prefix = f"product_{view_id}_image"
        storage_metadata = storage_handler(
            ir,
            image_data=image.data_url,
            metadata_prefix=metadata_prefix,
            object_prefix=f"product-{view_id}",
            fallback_content_type=f"image/{image.output_format or 'png'}",
            allow_remote_url=True,
        )
        image_url = storage_metadata.get(f"{metadata_prefix}_url")
        image_content_type = (
            storage_metadata.get(f"{metadata_prefix}_content_type")
            or f"image/{image.output_format or 'png'}"
        )
        image_record = {
            "view_id": view_id,
            "label": image.label,
            "provider": image.provider,
            "model": image.model,
            "size": image.size,
            "output_format": image.output_format,
            "model_revision": image.model_revision,
            "inference_provider": image.inference_provider,
            "model_license": image.model_license,
            "prompt": image.prompt,
            "prompt_original_length": image.prompt_original_length,
            "prompt_final_length": image.prompt_final_length,
            "prompt_compacted": image.prompt_compacted,
            "prompt_compaction_strategy": image.prompt_compaction_strategy,
            "reference_view_id": image.reference_view_id,
            "url": image_url,
            "content_type": image_content_type,
            "s3_bucket": storage_metadata.get(f"{metadata_prefix}_s3_bucket"),
            "s3_key": storage_metadata.get(f"{metadata_prefix}_s3_key"),
            "storage_method": storage_metadata.get(f"{metadata_prefix}_storage_method"),
            "storage_error": storage_metadata.get(f"{metadata_prefix}_storage_error"),
        }
        if not image_url:
            image_record["data"] = image.data_url
            product_metadata[f"{metadata_prefix}_data"] = image.data_url
        sequence.append(image_record)
        product_metadata.update(storage_metadata)
        if index == 0:
            for field in (
                "provider", "model", "size", "output_format", "model_revision",
                "inference_provider", "model_license", "prompt", "prompt_original_length",
                "prompt_final_length", "prompt_compacted", "prompt_compaction_strategy",
            ):
                product_metadata[f"product_image_{field}"] = getattr(image, field)
            product_metadata.update({
                "product_image_url": image_url,
                "product_image_content_type": image_content_type,
                "product_image_s3_bucket": storage_metadata.get(f"{metadata_prefix}_s3_bucket"),
                "product_image_s3_key": storage_metadata.get(f"{metadata_prefix}_s3_key"),
                "product_image_storage_method": storage_metadata.get(f"{metadata_prefix}_storage_method"),
            })
            if not image_url:
                product_metadata["product_image_data"] = image.data_url

    product_metadata["product_visual_sequence"] = sequence
    ir.assembly_metadata = {**(ir.assembly_metadata or {}), **product_metadata}
    storage_errors = [item.get("storage_error") for item in sequence if item.get("storage_error")]
    _set_operation(
        ir,
        "image_generation",
        label="Image generation",
        status="succeeded",
        provider=image_config.get("provider"),
        model=image_config.get("model_name"),
        requested=True,
        enabled=True,
        configured=True,
        details={"generated_count": len(generated_images)},
    )
    _set_operation(
        ir,
        "image_storage",
        label="Image storage",
        status="failed" if storage_errors else "succeeded",
        requested=True,
        enabled=bool(get_image_storage_config().get("enabled")),
        configured=True,
        error=str(storage_errors[0])[:500] if storage_errors else None,
        details={
            "stored_count": len([item for item in sequence if item.get("url")]),
            "inline_count": len([item for item in sequence if item.get("data")]),
        },
    )


def attach_assembly_step(ir: Any, filepath: str | Path) -> Dict[str, Any]:
    """Attach a validated native STEP artifact to a generated project."""
    path = Path(filepath).expanduser().resolve()
    if path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("Assembly artifact must end in .step or .stp.")
    if not path.is_file():
        raise ValueError(f"Assembly artifact does not exist: {path}")

    data = path.read_bytes()
    upper = data.upper()
    if (
        not upper.lstrip().startswith(b"ISO-10303-21;")
        or b"HEADER;" not in upper
        or b"DATA;" not in upper
        or b"END-ISO-10303-21;" not in upper
    ):
        raise ValueError(f"Assembly artifact is not a valid STEP exchange file: {path}")

    artifact = {
        "path": str(path),
        "filename": path.name,
        "format": "step",
        "units": "mm",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    current = ir.cad_model if isinstance(ir.cad_model, dict) else {}
    ir.cad_model = {
        **current,
        "adapter": "forma-opencad",
        "source": "CLI assembly STEP artifact",
        **artifact,
    }
    return artifact


def persist_project_output(ir: Any, *, prompt_text: str = "", owner_user_id: Optional[str] = None) -> str:
    """Update the existing generated project, or save it when generation did not."""
    init_db()
    metadata = ir.assembly_metadata or {}
    project_id = metadata.get("project_id")
    if not project_id:
        raise ValueError("Project output cannot be persisted without assembly_metadata.project_id.")
    hardware_ir = ir.model_dump(mode="json")
    if update_generated_project_hardware_ir(project_id, hardware_ir, owner_user_id=owner_user_id):
        return project_id
    title = getattr(getattr(ir, "overview", None), "title", None) or prompt_text.strip() or "Untitled Forma Project"
    created_at = metadata.get("created_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    save_generated_project(
        project_id=project_id,
        title=title,
        prompt=prompt_text.strip(),
        hardware_ir=hardware_ir,
        created_at=created_at,
        chat_id=metadata.get("chat_id"),
        owner_user_id=owner_user_id,
        visibility="public",
    )
    return project_id


def primary_product_image_data(ir: Any) -> Optional[str]:
    metadata = ir.assembly_metadata or {}
    value = metadata.get("product_image_data")
    return value if isinstance(value, str) and value else None


__all__ = [
    "attach_hardware_reference_image",
    "attach_assembly_step",
    "attach_product_image",
    "persist_project_output",
    "primary_product_image_data",
    "store_project_image",
]
