from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from blueprint_core.persistence.models import (
    DBAlphaSignup,
    DBComponentTemplate,
    DBDesignBrief,
    DBGeneratedProject,
    DBProjectContributionConsent,
    DBProjectContributionSnapshot,
    DBProjectChat,
    DBProjectBuild,
    DBProjectDeletionAudit,
    DBProjectWorkflow,
    DBProjectWorkflowTransition,
    DBUserSettings,
)


class SqlAlchemyRepository:
    """Application repository shared by SQLAlchemy-backed database providers."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _session(self) -> Any:
        return self._session_factory()

    def count_component_templates(self) -> int:
        with self._session() as session:
            return session.query(DBComponentTemplate).count()

    def list_component_templates(self) -> List[Any]:
        with self._session() as session:
            return session.query(DBComponentTemplate).all()

    def get_component_template_by_part_number(self, part_number: str) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBComponentTemplate).filter(
                DBComponentTemplate.part_number == part_number
            ).first()

    def insert_component_template(self, record: Dict[str, Any]) -> None:
        with self._session() as session, session.begin():
            session.add(DBComponentTemplate(**record))

    def save_generated_project(
        self,
        record: Dict[str, Any],
        chat_record: Optional[Dict[str, Any]],
    ) -> None:
        with self._session() as session, session.begin():
            session.add(DBGeneratedProject(**record))
            if not chat_record:
                return
            chat = session.query(DBProjectChat).filter(
                DBProjectChat.chat_id == chat_record["chat_id"]
            ).first()
            if chat:
                if chat.owner_user_id == chat_record["owner_user_id"]:
                    chat.title = chat.title or chat_record["title"]
                    chat.updated_at = chat_record["updated_at"]
                return
            session.add(DBProjectChat(**chat_record))

    def list_generated_projects(self, owner_user_id: Optional[str]) -> List[Any]:
        with self._session() as session:
            query = session.query(DBGeneratedProject).filter(DBGeneratedProject.status == "active")
            if owner_user_id:
                query = query.filter(DBGeneratedProject.owner_user_id == owner_user_id)
            return query.order_by(DBGeneratedProject.id.desc()).all()

    def get_generated_project(self, project_id: str, include_deleted: bool = False) -> Optional[Any]:
        with self._session() as session:
            query = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.project_id == project_id
            )
            if not include_deleted:
                query = query.filter(DBGeneratedProject.status == "active")
            return query.first()

    def insert_design_brief_version(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            design_brief = DBDesignBrief(**record)
            session.add(design_brief)
            session.flush()
            session.refresh(design_brief)
            session.expunge(design_brief)
            return design_brief

    def list_design_brief_versions(self, project_id: str, owner_user_id: str) -> List[Any]:
        with self._session() as session:
            return (
                session.query(DBDesignBrief)
                .filter(
                    DBDesignBrief.project_id == project_id,
                    DBDesignBrief.owner_user_id == owner_user_id,
                )
                .order_by(DBDesignBrief.brief_version.asc())
                .all()
            )

    def get_design_brief_version(
        self,
        project_id: str,
        owner_user_id: str,
        brief_version: int,
    ) -> Optional[Any]:
        with self._session() as session:
            return (
                session.query(DBDesignBrief)
                .filter(
                    DBDesignBrief.project_id == project_id,
                    DBDesignBrief.owner_user_id == owner_user_id,
                    DBDesignBrief.brief_version == brief_version,
                )
                .first()
            )

    def get_latest_design_brief(self, project_id: str, owner_user_id: Optional[str]) -> Optional[Any]:
        with self._session() as session:
            query = session.query(DBDesignBrief).filter(DBDesignBrief.project_id == project_id)
            if owner_user_id:
                query = query.filter(DBDesignBrief.owner_user_id == owner_user_id)
            return query.order_by(DBDesignBrief.brief_version.desc()).first()

    def get_project_workflow(self, project_id: str, owner_user_id: Optional[str]) -> Optional[Any]:
        with self._session() as session:
            query = session.query(DBProjectWorkflow).filter(DBProjectWorkflow.project_id == project_id)
            if owner_user_id:
                query = query.filter(DBProjectWorkflow.owner_user_id == owner_user_id)
            return query.first()

    def list_project_workflow_transitions(self, project_id: str, owner_user_id: str) -> List[Any]:
        with self._session() as session:
            return (
                session.query(DBProjectWorkflowTransition)
                .filter(
                    DBProjectWorkflowTransition.project_id == project_id,
                    DBProjectWorkflowTransition.owner_user_id == owner_user_id,
                )
                .order_by(DBProjectWorkflowTransition.revision.asc())
                .all()
            )

    def get_project_workflow_transition_by_idempotency(
        self,
        project_id: str,
        owner_user_id: str,
        idempotency_key: str,
    ) -> Optional[Any]:
        with self._session() as session:
            return (
                session.query(DBProjectWorkflowTransition)
                .filter(
                    DBProjectWorkflowTransition.project_id == project_id,
                    DBProjectWorkflowTransition.owner_user_id == owner_user_id,
                    DBProjectWorkflowTransition.idempotency_key == idempotency_key,
                )
                .first()
            )

    def apply_project_workflow_transition(
        self,
        state_record: Dict[str, Any],
        transition_record: Dict[str, Any],
        expected_state: Optional[str],
        expected_revision: Optional[int],
    ) -> Optional[tuple[Any, Any]]:
        try:
            with self._session() as session, session.begin():
                workflow = session.query(DBProjectWorkflow).filter(
                    DBProjectWorkflow.project_id == state_record["project_id"]
                ).first()
                if expected_state is None:
                    if workflow is not None:
                        return None
                    workflow = DBProjectWorkflow(**state_record)
                    session.add(workflow)
                else:
                    if (
                        workflow is None
                        or workflow.owner_user_id != state_record["owner_user_id"]
                        or workflow.state != expected_state
                        or workflow.revision != expected_revision
                    ):
                        return None
                    workflow.state = state_record["state"]
                    workflow.revision = state_record["revision"]
                    workflow.updated_at = state_record["updated_at"]
                transition = DBProjectWorkflowTransition(**transition_record)
                session.add(transition)
                session.flush()
                session.refresh(workflow)
                session.refresh(transition)
                session.expunge(workflow)
                session.expunge(transition)
                return workflow, transition
        except IntegrityError:
            return None

    def get_project_build_by_idempotency(
        self,
        project_id: str,
        owner_user_id: str,
        idempotency_key: str,
    ) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBProjectBuild).filter(
                DBProjectBuild.project_id == project_id,
                DBProjectBuild.owner_user_id == owner_user_id,
                DBProjectBuild.idempotency_key == idempotency_key,
            ).first()

    def get_latest_project_build(self, project_id: str, owner_user_id: str) -> Optional[Any]:
        with self._session() as session:
            return (
                session.query(DBProjectBuild)
                .filter(
                    DBProjectBuild.project_id == project_id,
                    DBProjectBuild.owner_user_id == owner_user_id,
                )
                .order_by(DBProjectBuild.created_at.desc())
                .first()
            )

    def apply_project_build_initiation(
        self,
        state_record: Dict[str, Any],
        transition_record: Dict[str, Any],
        build_record: Dict[str, Any],
        expected_state: str,
        expected_revision: int,
    ) -> Optional[tuple[Any, Any, Any]]:
        try:
            with self._session() as session, session.begin():
                workflow = session.query(DBProjectWorkflow).filter(
                    DBProjectWorkflow.project_id == state_record["project_id"]
                ).first()
                if (
                    workflow is None
                    or workflow.owner_user_id != state_record["owner_user_id"]
                    or workflow.state != expected_state
                    or workflow.revision != expected_revision
                ):
                    return None
                workflow.state = state_record["state"]
                workflow.revision = state_record["revision"]
                workflow.updated_at = state_record["updated_at"]
                transition = DBProjectWorkflowTransition(**transition_record)
                build = DBProjectBuild(**build_record)
                session.add(transition)
                session.add(build)
                session.flush()
                session.refresh(workflow)
                session.refresh(transition)
                session.refresh(build)
                session.expunge(workflow)
                session.expunge(transition)
                session.expunge(build)
                return workflow, transition, build
        except IntegrityError:
            return None

    def list_due_project_purges(self, before: str, limit: int) -> List[Any]:
        with self._session() as session:
            return (
                session.query(DBGeneratedProject)
                .filter(
                    DBGeneratedProject.status.in_(("deletion_pending", "deletion_failed", "purging")),
                    DBGeneratedProject.purge_after.isnot(None),
                    DBGeneratedProject.purge_after <= before,
                )
                .order_by(DBGeneratedProject.purge_after.asc())
                .limit(limit)
                .all()
            )

    def update_project_deletion_state(
        self,
        project_id: str,
        owner_user_id: Optional[str],
        allowed_statuses: List[str],
        updates: Dict[str, Any],
        expected_purge_started_at: Optional[str] = None,
    ) -> Optional[Any]:
        with self._session() as session, session.begin():
            query = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.project_id == project_id,
                DBGeneratedProject.status.in_(allowed_statuses),
            )
            if owner_user_id:
                query = query.filter(DBGeneratedProject.owner_user_id == owner_user_id)
            if expected_purge_started_at is not None:
                query = query.filter(DBGeneratedProject.purge_started_at == expected_purge_started_at)
            project = query.first()
            if not project:
                return None
            for key, value in updates.items():
                setattr(project, key, value)
            session.flush()
            session.refresh(project)
            session.expunge(project)
            return project

    def hard_purge_project(self, project_id: str, owner_user_id: Optional[str]) -> bool:
        with self._session() as session, session.begin():
            query = session.query(DBGeneratedProject).filter(DBGeneratedProject.project_id == project_id)
            if owner_user_id:
                query = query.filter(DBGeneratedProject.owner_user_id == owner_user_id)
            project = query.first()
            if not project:
                return False
            chat_id = project.chat_id
            project_owner_user_id = project.owner_user_id
            session.query(DBProjectBuild).filter(DBProjectBuild.project_id == project_id).delete(
                synchronize_session=False
            )
            session.query(DBDesignBrief).filter(DBDesignBrief.project_id == project_id).delete(
                synchronize_session=False
            )
            session.query(DBProjectWorkflowTransition).filter(
                DBProjectWorkflowTransition.project_id == project_id
            ).delete(synchronize_session=False)
            session.query(DBProjectWorkflow).filter(DBProjectWorkflow.project_id == project_id).delete(
                synchronize_session=False
            )
            session.delete(project)
            session.flush()
            if chat_id and project_owner_user_id:
                remaining = session.query(DBGeneratedProject).filter(
                    DBGeneratedProject.chat_id == chat_id,
                    DBGeneratedProject.owner_user_id == project_owner_user_id,
                ).count()
                chat = session.query(DBProjectChat).filter(
                    DBProjectChat.chat_id == chat_id,
                    DBProjectChat.owner_user_id == project_owner_user_id,
                ).first()
                if chat and remaining == 0:
                    session.delete(chat)
                elif chat and isinstance(chat.messages, list):
                    chat.messages = [
                        message
                        for message in chat.messages
                        if not isinstance(message, dict) or str(message.get("projectId") or message.get("project_id") or "") != project_id
                    ]
            return True

    def update_generated_project_hardware_ir(
        self,
        project_id: str,
        hardware_ir: Dict[str, Any],
        chat_id: Optional[str],
        owner_user_id: Optional[str],
    ) -> bool:
        with self._session() as session, session.begin():
            query = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.project_id == project_id
            )
            if owner_user_id:
                query = query.filter(DBGeneratedProject.owner_user_id == owner_user_id)
            project = query.first()
            if not project:
                return False
            if project.status != "active":
                return False
            project.hardware_ir = hardware_ir
            project.chat_id = chat_id
            return True

    def update_generated_project_metadata(
        self,
        project_id: str,
        owner_user_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        with self._session() as session, session.begin():
            project = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.project_id == project_id,
                DBGeneratedProject.owner_user_id == owner_user_id,
                DBGeneratedProject.status == "active",
            ).first()
            if not project:
                return False
            for key, value in updates.items():
                setattr(project, key, value)
            return True

    def delete_generated_project(self, project_id: str, owner_user_id: str) -> bool:
        with self._session() as session, session.begin():
            project = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.project_id == project_id,
                DBGeneratedProject.owner_user_id == owner_user_id,
            ).first()
            if not project:
                return False
            session.query(DBProjectBuild).filter(DBProjectBuild.project_id == project_id).delete(
                synchronize_session=False
            )
            session.query(DBDesignBrief).filter(DBDesignBrief.project_id == project_id).delete(
                synchronize_session=False
            )
            session.query(DBProjectWorkflowTransition).filter(
                DBProjectWorkflowTransition.project_id == project_id
            ).delete(synchronize_session=False)
            session.query(DBProjectWorkflow).filter(DBProjectWorkflow.project_id == project_id).delete(
                synchronize_session=False
            )
            session.delete(project)
            return True

    def get_project_contribution_consent(self, project_id: str, user_id: str) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBProjectContributionConsent).filter(
                DBProjectContributionConsent.project_id == project_id,
                DBProjectContributionConsent.user_id == user_id,
            ).first()

    def upsert_project_contribution_consent(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            consent = session.query(DBProjectContributionConsent).filter(
                DBProjectContributionConsent.project_id == record["project_id"],
                DBProjectContributionConsent.user_id == record["user_id"],
            ).first()
            if consent:
                for key, value in record.items():
                    if key != "id":
                        setattr(consent, key, value)
            else:
                consent = DBProjectContributionConsent(**record)
                session.add(consent)
            session.flush()
            session.refresh(consent)
            session.expunge(consent)
            return consent

    def withdraw_project_contribution_consent(self, project_id: str, user_id: str, withdrawn_at: str) -> Optional[Any]:
        with self._session() as session, session.begin():
            consent = session.query(DBProjectContributionConsent).filter(
                DBProjectContributionConsent.project_id == project_id,
                DBProjectContributionConsent.user_id == user_id,
            ).first()
            if not consent:
                return None
            consent.withdrawn_at = withdrawn_at
            session.flush()
            session.refresh(consent)
            session.expunge(consent)
            return consent

    def anonymize_project_contribution_consent(
        self,
        project_id: str,
        user_id: str,
        anonymized_project_id: str,
        anonymized_user_id: str,
        anonymized_at: str,
    ) -> bool:
        with self._session() as session, session.begin():
            consent = session.query(DBProjectContributionConsent).filter(
                DBProjectContributionConsent.project_id == project_id,
                DBProjectContributionConsent.user_id == user_id,
            ).first()
            if not consent:
                return False
            consent.project_id = anonymized_project_id
            consent.user_id = anonymized_user_id
            consent.workspace_id = None
            consent.anonymized_at = anonymized_at
            return True

    def upsert_project_contribution_snapshot(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            snapshot = session.query(DBProjectContributionSnapshot).filter(
                DBProjectContributionSnapshot.consent_record_id == record["consent_record_id"]
            ).first()
            if snapshot:
                if snapshot.anonymized_at:
                    return snapshot
                for key, value in record.items():
                    if key != "id":
                        setattr(snapshot, key, value)
            else:
                snapshot = DBProjectContributionSnapshot(**record)
                session.add(snapshot)
            session.flush()
            session.refresh(snapshot)
            session.expunge(snapshot)
            return snapshot

    def anonymize_project_contribution_snapshot(
        self,
        consent_record_id: str,
        anonymized_source_id: str,
        anonymized_consent_id: str,
        anonymized_at: str,
    ) -> bool:
        with self._session() as session, session.begin():
            snapshot = session.query(DBProjectContributionSnapshot).filter(
                DBProjectContributionSnapshot.consent_record_id == consent_record_id,
                DBProjectContributionSnapshot.anonymized_at.is_(None),
            ).first()
            if not snapshot:
                return False
            snapshot.source_project_id = anonymized_source_id
            snapshot.consent_record_id = anonymized_consent_id
            snapshot.contribution_status = "anonymized"
            snapshot.anonymized_at = anonymized_at
            consent = session.query(DBProjectContributionConsent).filter(
                DBProjectContributionConsent.id == consent_record_id
            ).first()
            if consent:
                consent.anonymized_at = anonymized_at
            return True

    def purge_project_contribution_snapshots(self, consent_record_id: str, purged_at: str) -> int:
        with self._session() as session, session.begin():
            snapshots = session.query(DBProjectContributionSnapshot).filter(
                DBProjectContributionSnapshot.consent_record_id == consent_record_id,
                DBProjectContributionSnapshot.anonymized_at.is_(None),
            ).all()
            count = len(snapshots)
            for snapshot in snapshots:
                session.delete(snapshot)
            consent = session.query(DBProjectContributionConsent).filter(
                DBProjectContributionConsent.id == consent_record_id
            ).first()
            if consent:
                consent.purged_at = purged_at
            return count

    def add_project_deletion_audit(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            audit = DBProjectDeletionAudit(**record)
            session.add(audit)
            session.flush()
            session.refresh(audit)
            session.expunge(audit)
            return audit

    def get_latest_project_deletion_audit(self, project_id: str) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBProjectDeletionAudit).filter(
                DBProjectDeletionAudit.project_id == project_id
            ).order_by(DBProjectDeletionAudit.created_at.desc()).first()

    def list_project_deletion_audits(self, limit: int) -> List[Any]:
        with self._session() as session:
            return session.query(DBProjectDeletionAudit).order_by(
                DBProjectDeletionAudit.created_at.desc()
            ).limit(limit).all()

    def upsert_project_chat(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            chat = session.query(DBProjectChat).filter(
                DBProjectChat.chat_id == record["chat_id"],
                DBProjectChat.owner_user_id == record["owner_user_id"],
            ).first()
            if chat:
                chat.title = record["title"]
                chat.messages = record["messages"]
                chat.updated_at = record["updated_at"]
            else:
                chat = DBProjectChat(**record)
                session.add(chat)
            session.flush()
            session.refresh(chat)
            session.expunge(chat)
            return chat

    def list_project_chats(self, owner_user_id: str) -> List[Any]:
        with self._session() as session:
            chats = session.query(DBProjectChat).filter(
                DBProjectChat.owner_user_id == owner_user_id
            ).order_by(DBProjectChat.updated_at.desc()).all()
            projects = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.owner_user_id == owner_user_id,
                DBGeneratedProject.chat_id.isnot(None),
            ).all()
            by_chat: Dict[str, List[Any]] = {}
            for project in projects:
                by_chat.setdefault(str(project.chat_id), []).append(project)
            visible = []
            for chat in chats:
                linked = by_chat.get(chat.chat_id, [])
                if linked and not any(project.status == "active" for project in linked):
                    continue
                hidden_ids = {project.project_id for project in linked if project.status != "active"}
                if hidden_ids and isinstance(chat.messages, list):
                    chat.messages = [
                        message
                        for message in chat.messages
                        if not isinstance(message, dict)
                        or str(message.get("projectId") or message.get("project_id") or "") not in hidden_ids
                    ]
                visible.append(chat)
            return visible

    def get_project_chat(self, chat_id: str, owner_user_id: str) -> Optional[Any]:
        with self._session() as session:
            chat = session.query(DBProjectChat).filter(
                DBProjectChat.chat_id == chat_id,
                DBProjectChat.owner_user_id == owner_user_id,
            ).first()
            if not chat:
                return None
            linked = session.query(DBGeneratedProject).filter(
                DBGeneratedProject.chat_id == chat_id,
                DBGeneratedProject.owner_user_id == owner_user_id,
            ).all()
            if linked and not any(project.status == "active" for project in linked):
                return None
            hidden_ids = {project.project_id for project in linked if project.status != "active"}
            if hidden_ids and isinstance(chat.messages, list):
                chat.messages = [
                    message
                    for message in chat.messages
                    if not isinstance(message, dict)
                    or str(message.get("projectId") or message.get("project_id") or "") not in hidden_ids
                ]
            return chat

    def delete_project_chat(self, chat_id: str, owner_user_id: str) -> bool:
        with self._session() as session, session.begin():
            chat = session.query(DBProjectChat).filter(
                DBProjectChat.chat_id == chat_id,
                DBProjectChat.owner_user_id == owner_user_id,
            ).first()
            if not chat:
                return False
            session.delete(chat)
            session.query(DBGeneratedProject).filter(
                DBGeneratedProject.chat_id == chat_id,
                DBGeneratedProject.owner_user_id == owner_user_id,
            ).update({"chat_id": None})
            return True

    def save_alpha_signup(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            signup = DBAlphaSignup(**record)
            session.add(signup)
            session.flush()
            session.refresh(signup)
            session.expunge(signup)
            return signup

    def get_user_settings(self, owner_user_id: str) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBUserSettings).filter(
                DBUserSettings.owner_user_id == owner_user_id
            ).first()

    def upsert_user_settings(self, record: Dict[str, Any]) -> Any:
        with self._session() as session, session.begin():
            settings = session.query(DBUserSettings).filter(
                DBUserSettings.owner_user_id == record["owner_user_id"]
            ).first()
            if settings:
                settings.model_training_opt_out = record["model_training_opt_out"]
                settings.updated_at = record["updated_at"]
            else:
                settings = DBUserSettings(**record)
                session.add(settings)
            session.flush()
            session.refresh(settings)
            session.expunge(settings)
            return settings

    def list_model_training_opt_out_user_ids(self) -> List[str]:
        with self._session() as session:
            rows = session.query(DBUserSettings.owner_user_id).filter(
                DBUserSettings.model_training_opt_out.is_(True)
            ).all()
            return [str(row[0]) for row in rows]
