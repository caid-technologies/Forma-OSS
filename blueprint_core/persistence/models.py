from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class DBComponentTemplate(Base):
    __tablename__ = "component_templates"

    id = Column(Integer, primary_key=True, index=True)
    part_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, default=0.0)
    sourcing_url = Column(String, nullable=True)
    pins = Column(JSON, nullable=False)
    use_cases = Column(JSON, nullable=False)


class DBGeneratedProject(Base):
    __tablename__ = "generated_projects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, unique=True, index=True, nullable=False)
    chat_id = Column(String, index=True, nullable=True)
    owner_user_id = Column(String, index=True, nullable=True)
    visibility = Column(String, index=True, nullable=False, default="public")
    title = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    hardware_ir = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default="active")
    deleted_at = Column(String, nullable=True)
    deletion_requested_by = Column(String, nullable=True)
    purge_after = Column(String, index=True, nullable=True)
    purge_started_at = Column(String, nullable=True)
    purge_completed_at = Column(String, nullable=True)
    deletion_error = Column(Text, nullable=True)


class DBDesignBrief(Base):
    __tablename__ = "design_briefs"
    __table_args__ = (
        UniqueConstraint("project_id", "brief_version", name="uq_design_briefs_project_version"),
    )

    id = Column(String, primary_key=True)
    design_brief_id = Column(String, index=True, nullable=False)
    project_id = Column(String, index=True, nullable=False)
    conversation_id = Column(String, index=True, nullable=False)
    owner_user_id = Column(String, index=True, nullable=False)
    brief_version = Column(Integer, nullable=False)
    schema_version = Column(String, nullable=False)
    previous_version = Column(Integer, nullable=True)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(String, index=True, nullable=False)


class DBProjectWorkflow(Base):
    __tablename__ = "project_workflows"

    project_id = Column(String, primary_key=True)
    owner_user_id = Column(String, index=True, nullable=False)
    state = Column(String, index=True, nullable=False)
    revision = Column(Integer, nullable=False)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, index=True, nullable=False)


class DBProjectWorkflowTransition(Base):
    __tablename__ = "project_workflow_transitions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_project_workflow_transition_revision"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_project_workflow_transition_idempotency"),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, index=True, nullable=False)
    owner_user_id = Column(String, index=True, nullable=False)
    from_state = Column(String, nullable=True)
    to_state = Column(String, index=True, nullable=False)
    actor_type = Column(String, nullable=False)
    actor_id = Column(String, index=True, nullable=True)
    reason = Column(Text, nullable=False)
    idempotency_key = Column(String, nullable=True)
    revision = Column(Integer, nullable=False)
    created_at = Column(String, index=True, nullable=False)


class DBProjectContributionConsent(Base):
    __tablename__ = "project_contribution_consents"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_contribution_consent_project_user"),)

    id = Column(String, primary_key=True)
    project_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    workspace_id = Column(String, nullable=True)
    consent_version = Column(String, nullable=False)
    permitted_purposes = Column(JSON, nullable=False, default=list)
    granted_at = Column(String, nullable=False)
    withdrawn_at = Column(String, nullable=True)
    snapshot_created_at = Column(String, nullable=True)
    sanitized_at = Column(String, nullable=True)
    anonymized_at = Column(String, nullable=True)
    purged_at = Column(String, nullable=True)


class DBProjectContributionSnapshot(Base):
    __tablename__ = "project_contribution_snapshots"

    id = Column(String, primary_key=True)
    source_project_id = Column(String, index=True, nullable=False)
    consent_record_id = Column(String, unique=True, index=True, nullable=False)
    sanitization_version = Column(String, nullable=False)
    contribution_status = Column(String, index=True, nullable=False)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(String, nullable=False)
    sanitized_at = Column(String, nullable=True)
    anonymized_at = Column(String, nullable=True)
    purged_at = Column(String, nullable=True)


class DBProjectDeletionAudit(Base):
    __tablename__ = "project_deletion_audit"

    id = Column(String, primary_key=True)
    project_id = Column(String, index=True, nullable=False)
    acting_user_id = Column(String, index=True, nullable=True)
    action = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False)
    policy_version = Column(String, nullable=False)
    details_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(String, index=True, nullable=False)


class DBProjectChat(Base):
    __tablename__ = "project_chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True, nullable=False)
    owner_user_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    messages = Column(JSON, nullable=False, default=list)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class DBAlphaSignup(Base):
    __tablename__ = "alpha_signups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, index=True, nullable=False)
    organization = Column(String, nullable=True)
    additional_info = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="web")
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(String, nullable=False)


class DBUserIntegrationConfig(Base):
    __tablename__ = "user_integration_configs"

    owner_user_id = Column(String, primary_key=True)
    encrypted_config = Column(Text, nullable=False)
    encryption_key_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=True)
    updated_at = Column(String, nullable=False)


class DBWorkspaceIntegrationConfig(Base):
    __tablename__ = "workspace_integration_configs"

    config_key = Column(String, primary_key=True, default="default")
    encrypted_config = Column(Text, nullable=False)
    encryption_key_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=True)
    updated_at = Column(String, nullable=False)


class DBUserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(String, unique=True, index=True, nullable=False)
    model_training_opt_out = Column(Boolean, nullable=False, default=False)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
