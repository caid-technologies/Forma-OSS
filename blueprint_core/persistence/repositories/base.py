from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ApplicationRepository(Protocol):
    """Persistence operations used by the application domain."""

    def count_component_templates(self) -> int: ...

    def list_component_templates(self) -> List[Any]: ...

    def get_component_template_by_part_number(self, part_number: str) -> Optional[Any]: ...

    def insert_component_template(self, record: Dict[str, Any]) -> None: ...

    def save_generated_project(
        self,
        record: Dict[str, Any],
        chat_record: Optional[Dict[str, Any]],
    ) -> None: ...

    def list_generated_projects(self, owner_user_id: Optional[str]) -> List[Any]: ...

    def list_generated_projects_page(
        self,
        owner_user_id: Optional[str],
        *,
        visibility: Optional[str],
        limit: int,
        offset: int,
        search: Optional[str] = None,
    ) -> tuple[List[Any], int]: ...

    def get_generated_project(self, project_id: str, include_deleted: bool = False) -> Optional[Any]: ...

    def insert_design_brief_version(self, record: Dict[str, Any]) -> Any: ...

    def list_design_brief_versions(self, project_id: str, owner_user_id: str) -> List[Any]: ...

    def get_design_brief_version(
        self,
        project_id: str,
        owner_user_id: str,
        brief_version: int,
    ) -> Optional[Any]: ...

    def get_latest_design_brief(self, project_id: str, owner_user_id: Optional[str]) -> Optional[Any]: ...

    def get_project_workflow(self, project_id: str, owner_user_id: Optional[str]) -> Optional[Any]: ...

    def list_project_workflow_transitions(self, project_id: str, owner_user_id: str) -> List[Any]: ...

    def get_project_workflow_transition_by_idempotency(
        self,
        project_id: str,
        owner_user_id: str,
        idempotency_key: str,
    ) -> Optional[Any]: ...

    def apply_project_workflow_transition(
        self,
        state_record: Dict[str, Any],
        transition_record: Dict[str, Any],
        expected_state: Optional[str],
        expected_revision: Optional[int],
    ) -> Optional[tuple[Any, Any]]: ...

    def get_project_build_by_idempotency(
        self,
        project_id: str,
        owner_user_id: str,
        idempotency_key: str,
    ) -> Optional[Any]: ...

    def get_latest_project_build(self, project_id: str, owner_user_id: str) -> Optional[Any]: ...

    def apply_project_build_initiation(
        self,
        state_record: Dict[str, Any],
        transition_record: Dict[str, Any],
        build_record: Dict[str, Any],
        expected_state: str,
        expected_revision: int,
    ) -> Optional[tuple[Any, Any, Any]]: ...

    def insert_worker_execution_plan(self, record: Dict[str, Any]) -> Any: ...

    def get_worker_execution_plan(self, plan_id: str, owner_user_id: str) -> Optional[Any]: ...

    def list_worker_execution_plans(self, limit: int = 200) -> List[Any]: ...

    def update_worker_execution_plan(
        self,
        plan_id: str,
        owner_user_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Any]: ...

    def get_latest_project_revision(self, project_id: str, owner_user_id: str) -> Optional[Any]: ...

    def list_latest_project_revisions(self, owner_user_id: str) -> List[Any]: ...

    def get_project_revision(
        self,
        project_id: str,
        owner_user_id: str,
        revision: int,
    ) -> Optional[Any]: ...

    def insert_project_revision(
        self,
        record: Dict[str, Any],
        expected_parent_revision: int,
    ) -> Optional[Any]: ...

    def get_project_revision_by_source_job(
        self,
        project_id: str,
        owner_user_id: str,
        source_job_id: str,
    ) -> Optional[Any]: ...

    def insert_initial_project_revision(self, record: Dict[str, Any]) -> Optional[Any]: ...

    def get_validation_report(self, report_id: str, owner_user_id: str) -> Optional[Any]: ...

    def get_validation_report_by_source_job(
        self,
        project_id: str,
        owner_user_id: str,
        source_job_id: str,
    ) -> Optional[Any]: ...

    def insert_project_validation_report(self, record: Dict[str, Any]) -> Optional[Any]: ...

    def list_due_project_purges(self, before: str, limit: int) -> List[Any]: ...

    def update_project_deletion_state(
        self,
        project_id: str,
        owner_user_id: Optional[str],
        allowed_statuses: List[str],
        updates: Dict[str, Any],
        expected_purge_started_at: Optional[str] = None,
    ) -> Optional[Any]: ...

    def hard_purge_project(self, project_id: str, owner_user_id: Optional[str]) -> bool: ...

    def update_generated_project_hardware_ir(
        self,
        project_id: str,
        hardware_ir: Dict[str, Any],
        chat_id: Optional[str],
        owner_user_id: Optional[str],
    ) -> bool: ...

    def update_generated_project_metadata(
        self,
        project_id: str,
        owner_user_id: str,
        updates: Dict[str, Any],
    ) -> bool: ...

    def delete_generated_project(self, project_id: str, owner_user_id: str) -> bool: ...

    def get_project_contribution_consent(self, project_id: str, user_id: str) -> Optional[Any]: ...

    def upsert_project_contribution_consent(self, record: Dict[str, Any]) -> Any: ...

    def withdraw_project_contribution_consent(self, project_id: str, user_id: str, withdrawn_at: str) -> Optional[Any]: ...

    def anonymize_project_contribution_consent(
        self,
        project_id: str,
        user_id: str,
        anonymized_project_id: str,
        anonymized_user_id: str,
        anonymized_at: str,
    ) -> bool: ...

    def upsert_project_contribution_snapshot(self, record: Dict[str, Any]) -> Any: ...

    def anonymize_project_contribution_snapshot(
        self,
        consent_record_id: str,
        anonymized_source_id: str,
        anonymized_consent_id: str,
        anonymized_at: str,
    ) -> bool: ...

    def purge_project_contribution_snapshots(self, consent_record_id: str, purged_at: str) -> int: ...

    def add_project_deletion_audit(self, record: Dict[str, Any]) -> Any: ...

    def get_latest_project_deletion_audit(self, project_id: str) -> Optional[Any]: ...

    def list_project_deletion_audits(self, limit: int) -> List[Any]: ...

    def upsert_project_chat(self, record: Dict[str, Any]) -> Any: ...

    def list_project_chats(self, owner_user_id: str) -> List[Any]: ...

    def get_project_chat(self, chat_id: str, owner_user_id: str) -> Optional[Any]: ...

    def delete_project_chat(self, chat_id: str, owner_user_id: str) -> bool: ...

    def save_alpha_signup(self, record: Dict[str, Any]) -> Any: ...

    def get_user_settings(self, owner_user_id: str) -> Optional[Any]: ...

    def upsert_user_settings(self, record: Dict[str, Any]) -> Any: ...

    def list_model_training_opt_out_user_ids(self) -> List[str]: ...
