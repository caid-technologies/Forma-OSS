from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, Integer, JSON, String, Text
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


class DBProjectChat(Base):
    __tablename__ = "project_chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True, nullable=False)
    owner_user_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    messages = Column(JSON, nullable=False, default=list)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class DBA2AJob(Base):
    __tablename__ = "a2a_jobs"

    job_id = Column(String, primary_key=True)
    message_id = Column(String, nullable=False)
    correlation_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    sender = Column(String, nullable=False, index=True)
    recipient = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    server_owned = Column(Boolean, nullable=False, default=False)
    created_at = Column(String, nullable=False, index=True)
    updated_at = Column(String, nullable=False)
    started_at = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)
    payload_json = Column(Text, nullable=True)
    result_summary_json = Column(Text, nullable=True)
    source_usage_json = Column(Text, nullable=True)
    progress_events_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    error_debug_json = Column(Text, nullable=True)


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
