from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from backend.a2a import build_generation_response
from backend.auth import UserApiKeyPrincipal, require_user_api_key, user_api_key_auth_configured
from backend.job_store import JOB_STORE
from blueprint_core.agents.workflows import get_workflow_debug_config
from blueprint_core.debug import api_error_detail, debug_mode_enabled, exception_debug_payload
from blueprint_core.database import get_database_config, get_generated_project, get_user_settings, update_generated_project_hardware_ir
from blueprint_core.llm import LLMProviderConfigError, LLMProviderOutputError
from blueprint_core.llm_providers import get_available_llm_runtime_options
from blueprint_core.models import GenerateProjectRequest
from blueprint_core.pipeline import observe_agent_pipeline
from blueprint_core.runtime import (
    ALPHA_GENERATION_UNAVAILABLE_MESSAGE,
    AlphaGenerationUnavailableError,
    deployment_runtime_config,
    generation_unavailable_detail,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["developer-api"])


def _deployment_runtime_config(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    return deployment_runtime_config(llm_config, signup_storage=get_database_config()["client"])


def _ensure_job_store_ready() -> None:
    JOB_STORE.init_db()


def _require_generation_input(request: GenerateProjectRequest) -> None:
    if (request.prompt or "").strip() or request.image_data:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Provide a prompt or reference image.",
    )


def _require_source_project_owner(project_id: Optional[str], owner_user_id: str) -> None:
    if not project_id:
        return
    source_project = get_generated_project(project_id)
    if not source_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source project not found.")
    source_owner_user_id = getattr(source_project, "owner_user_id", None)
    if source_owner_user_id != owner_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only use your own source projects.")


def _require_scope(principal: UserApiKeyPrincipal, scope: str) -> None:
    scopes = set(principal.scopes or [])
    if "*" in scopes or scope in scopes:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"API key requires scope: {scope}.")


def _api_key_sender(principal: UserApiKeyPrincipal) -> str:
    return f"api:{principal.key_id}"


def _job_provider_model(job: Dict[str, Any]) -> Dict[str, Optional[str]]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result_summary = job.get("result_summary") if isinstance(job.get("result_summary"), dict) else {}
    source_usage = job.get("source_usage") if isinstance(job.get("source_usage"), dict) else {}
    generation_usage = source_usage.get("generation") if isinstance(source_usage.get("generation"), dict) else {}
    return {
        "provider": (
            payload.get("provider")
            or result_summary.get("runtime_provider")
            or result_summary.get("llm_provider")
            or generation_usage.get("provider")
        ),
        "model": (
            payload.get("model")
            or result_summary.get("runtime_model")
            or result_summary.get("model_name")
            or generation_usage.get("model")
        ),
    }


def _job_belongs_to_principal(job: Dict[str, Any], principal: UserApiKeyPrincipal) -> bool:
    if job.get("sender") == _api_key_sender(principal):
        return True
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    return payload.get("owner_user_id") == principal.owner_user_id


def _public_job_payload(job: Dict[str, Any], *, include_progress: bool = False) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    result_summary = job.get("result_summary") if isinstance(job.get("result_summary"), dict) else {}
    provider_model = _job_provider_model(job)
    public_payload: Dict[str, Any] = {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "action": job.get("action"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "workflow": payload.get("workflow"),
        "provider": provider_model["provider"],
        "model": provider_model["model"],
        "api_key_id": payload.get("api_key_id"),
        "owner_user_id": payload.get("owner_user_id"),
        "project_id": result_summary.get("project_id"),
        "chat_id": result_summary.get("chat_id") or payload.get("chat_id"),
        "source_project_id": result_summary.get("source_project_id") or payload.get("source_project_id"),
        "title": result_summary.get("title"),
        "error": job.get("error"),
        "result_summary": result_summary,
        "source_usage": job.get("source_usage") or {},
        "progress_event_count": len(job.get("progress_events") or []),
    }
    if include_progress:
        public_payload["progress_events"] = job.get("progress_events") or []
    return public_payload


def _generation_error_detail(exc: Exception, *, job_id: str, request: GenerateProjectRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(exc, ValueError):
        return api_error_detail(
            code="generation_request_invalid",
            message=str(exc),
            exc=exc,
            job_id=job_id,
            provider=request.provider,
            model=request.model,
            context=payload,
        )
    if isinstance(exc, LLMProviderConfigError):
        return api_error_detail(
            code="llm_config_invalid",
            message=str(exc),
            exc=exc,
            job_id=job_id,
            provider=request.provider,
            model=request.model,
            context=payload,
        )
    if isinstance(exc, LLMProviderOutputError):
        return api_error_detail(
            code="llm_output_invalid",
            message=str(exc),
            exc=exc,
            job_id=job_id,
            provider=request.provider,
            model=request.model,
            context=payload,
        )
    if isinstance(exc, AlphaGenerationUnavailableError):
        code = "alpha_generation_unavailable" if str(exc) == ALPHA_GENERATION_UNAVAILABLE_MESSAGE else "llm_generation_unavailable"
        return api_error_detail(
            code=code,
            message=str(exc),
            exc=exc,
            job_id=job_id,
            provider=request.provider,
            model=request.model,
            context=payload,
        )
    return api_error_detail(
        code="generation_failed",
        message=f"Generation failed: {str(exc)}",
        exc=exc,
        job_id=job_id,
        provider=request.provider,
        model=request.model,
        context=payload,
    )


def _generation_http_status(exc: Exception) -> int:
    if isinstance(exc, ValueError):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, LLMProviderConfigError):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, LLMProviderOutputError):
        return status.HTTP_502_BAD_GATEWAY
    if isinstance(exc, AlphaGenerationUnavailableError):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _validate_generation_request(request: GenerateProjectRequest, owner_user_id: str) -> None:
    try:
        llm_config = get_workflow_debug_config(
            request.workflow,
            provider_name=request.provider,
            model_name=request.model,
            external_source_provider=request.external_source_provider,
        )
    except LLMProviderConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=api_error_detail(
                code="llm_config_invalid",
                message=str(exc),
                exc=exc,
                provider=request.provider,
                model=request.model,
                context={
                    "workflow": request.workflow,
                    "generate_image": request.generate_image,
                    "external_source_provider": request.external_source_provider,
                },
            ),
        ) from exc

    deployment_config = _deployment_runtime_config(llm_config)
    if deployment_config["alpha_generation_gate_active"]:
        detail = generation_unavailable_detail(llm_config)
        logger.warning(
            "Developer API generation unavailable for provider=%s model=%s: %s",
            detail.get("provider"),
            detail.get("model"),
            detail.get("reason") or detail.get("message"),
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    _require_generation_input(request)
    _require_source_project_owner(request.source_project_id, owner_user_id)


def _create_generation_job(request: GenerateProjectRequest, principal: UserApiKeyPrincipal) -> Dict[str, Any]:
    _ensure_job_store_ready()
    owner_user_id = principal.owner_user_id
    user_settings = get_user_settings(owner_user_id)
    model_training_opt_out = bool(getattr(user_settings, "model_training_opt_out", False))
    _validate_generation_request(request, owner_user_id)

    job_id = request.client_job_id or f"job_api_{uuid4().hex}"
    payload = {
        "prompt": request.prompt,
        "workflow": request.workflow,
        "image_data": request.image_data,
        "generate_image": request.generate_image,
        "provider": request.provider,
        "model": request.model,
        "chat_id": request.chat_id,
        "source_project_id": request.source_project_id,
        "client_job_id": request.client_job_id,
        "owner_user_id": owner_user_id,
        "api_key_id": principal.key_id,
        "model_training_opt_out": model_training_opt_out,
        "external_source_provider": request.external_source_provider,
    }
    job = JOB_STORE.create_job(
        job_id=job_id,
        message_id=f"msg_{uuid4().hex}",
        correlation_id=None,
        action="blueprint.generate_project",
        sender=_api_key_sender(principal),
        recipient="blueprint",
        payload=payload,
        server_owned=True,
        status="queued",
    )
    return {"job_id": job_id, "payload": payload, "model_training_opt_out": model_training_opt_out, "job": job}


def _run_generation_job(
    *,
    request: GenerateProjectRequest,
    job_id: str,
    owner_user_id: str,
    model_training_opt_out: bool,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    JOB_STORE.mark_running(job_id)
    try:
        with observe_agent_pipeline(lambda event: JOB_STORE.append_progress_event(job_id, event.as_dict())):
            response = build_generation_response(
                request.prompt,
                request.image_data,
                generate_image=request.generate_image,
                workflow=request.workflow,
                provider=request.provider,
                model=request.model,
                external_source_provider=request.external_source_provider,
                chat_id=request.chat_id,
                source_project_id=request.source_project_id,
                frontend_job_id=job_id,
                owner_user_id=owner_user_id,
                model_training_opt_out=model_training_opt_out,
            )
        JOB_STORE.mark_succeeded(job_id, response)
        metadata = (response.get("project_ir", {}).get("assembly_metadata") or {})
        project_id = metadata.get("project_id")
        if project_id and isinstance(response.get("project_ir"), dict):
            try:
                update_generated_project_hardware_ir(project_id, response["project_ir"])
            except Exception:
                logger.warning(
                    "Failed to persist developer API generation metadata for project_id=%s",
                    project_id,
                    exc_info=debug_mode_enabled(),
                )
        return {
            **response,
            "project_id": project_id,
            "chat_id": metadata.get("chat_id"),
            "job_id": job_id,
            "job": JOB_STORE.get_job(job_id),
        }
    except Exception as exc:
        error_debug = exception_debug_payload(exc, context=payload) if debug_mode_enabled() else None
        JOB_STORE.mark_failed(job_id, str(exc), error_debug)
        if not isinstance(exc, (ValueError, LLMProviderConfigError, LLMProviderOutputError, AlphaGenerationUnavailableError)):
            logger.exception(
                "Developer API generation failed for job_id=%s provider=%s model=%s",
                job_id,
                request.provider,
                request.model,
            )
        raise


def _run_generation_job_background(
    request: GenerateProjectRequest,
    job_id: str,
    owner_user_id: str,
    model_training_opt_out: bool,
    payload: Dict[str, Any],
) -> None:
    try:
        _run_generation_job(
            request=request,
            job_id=job_id,
            owner_user_id=owner_user_id,
            model_training_opt_out=model_training_opt_out,
            payload=payload,
        )
    except Exception:
        logger.info("Developer API async generation ended with failed job_id=%s", job_id, exc_info=debug_mode_enabled())


@router.get("/health")
def developer_api_health() -> Dict[str, Any]:
    return {
        "status": "online",
        "service": "Blueprint Developer API",
        "auth": {
            "api_keys_configured": user_api_key_auth_configured(),
            "headers": ["Authorization: Bearer <api_key>", "X-API-Key: <api_key>"],
        },
        "endpoints": {
            "me": "/api/v1/me",
            "llms": "/api/v1/llms",
            "models": "/api/v1/models",
            "generate": "/api/v1/generate",
            "create_job": "POST /api/v1/jobs",
            "jobs": "/api/v1/jobs",
            "job": "/api/v1/jobs/{job_id}",
        },
    }


@router.get("/me")
def developer_api_me(principal: UserApiKeyPrincipal = Depends(require_user_api_key)) -> Dict[str, str]:
    return {
        "key_id": principal.key_id,
        "owner_user_id": principal.owner_user_id,
    }


@router.get("/llms")
def developer_api_llms(principal: UserApiKeyPrincipal = Depends(require_user_api_key)) -> Dict[str, Any]:
    """List provider/model choices available for API generation."""
    _require_scope(principal, "generate:project")
    return get_available_llm_runtime_options()


@router.get("/models")
def developer_api_models(principal: UserApiKeyPrincipal = Depends(require_user_api_key)) -> Dict[str, Any]:
    """Alias for /v1/llms."""
    return developer_api_llms(principal)


@router.get("/jobs")
def developer_api_jobs(
    job_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    scope: str = Query("key", pattern="^(key|owner)$"),
    include_progress: bool = False,
    principal: UserApiKeyPrincipal = Depends(require_user_api_key),
) -> Dict[str, Any]:
    """List generation jobs visible to the supplied API key."""
    _require_scope(principal, "read:job")
    _ensure_job_store_ready()
    if scope == "owner":
        jobs = JOB_STORE.list_jobs(owner_user_id=principal.owner_user_id, status=job_status, limit=limit)
    else:
        jobs = JOB_STORE.list_jobs(sender=_api_key_sender(principal), status=job_status, limit=limit)
    return {
        "owner_user_id": principal.owner_user_id,
        "key_id": principal.key_id,
        "scope": scope,
        "count": len(jobs),
        "jobs": [_public_job_payload(job, include_progress=include_progress) for job in jobs],
    }


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def developer_api_create_job(
    request: GenerateProjectRequest,
    background_tasks: BackgroundTasks,
    principal: UserApiKeyPrincipal = Depends(require_user_api_key),
) -> Dict[str, Any]:
    """Create an async generation job and return immediately for polling."""
    _require_scope(principal, "generate:project")
    created = _create_generation_job(request, principal)
    background_tasks.add_task(
        _run_generation_job_background,
        request,
        created["job_id"],
        principal.owner_user_id,
        created["model_training_opt_out"],
        created["payload"],
    )
    job = JOB_STORE.get_job(created["job_id"]) or created["job"]
    return {
        "job_id": created["job_id"],
        "status": job.get("status", "queued"),
        "poll_url": f"/api/v1/jobs/{created['job_id']}",
        "job": _public_job_payload(job, include_progress=False),
    }


@router.get("/jobs/{job_id}")
def developer_api_job(
    job_id: str,
    include_progress: bool = True,
    principal: UserApiKeyPrincipal = Depends(require_user_api_key),
) -> Dict[str, Any]:
    """Fetch one generation job visible to the supplied API key."""
    _require_scope(principal, "read:job")
    _ensure_job_store_ready()
    job = JOB_STORE.get_job(job_id)
    if not job or not _job_belongs_to_principal(job, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return _public_job_payload(job, include_progress=include_progress)


@router.post("/generate", response_model=Dict[str, Any])
def developer_generate_project_endpoint(
    request: GenerateProjectRequest,
    principal: UserApiKeyPrincipal = Depends(require_user_api_key),
):
    """Generate a Blueprint hardware project with an API key instead of a Clerk session."""
    _require_scope(principal, "generate:project")
    created = _create_generation_job(request, principal)

    try:
        return _run_generation_job(
            request=request,
            job_id=created["job_id"],
            owner_user_id=principal.owner_user_id,
            model_training_opt_out=created["model_training_opt_out"],
            payload=created["payload"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=_generation_http_status(exc),
            detail=_generation_error_detail(exc, job_id=created["job_id"], request=request, payload=created["payload"]),
        ) from exc
