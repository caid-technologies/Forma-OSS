"""SQLAlchemy persistence model for durable jobs."""

from sqlalchemy import Boolean, Column, String, Text

from forma_core.persistence.models import Base


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
