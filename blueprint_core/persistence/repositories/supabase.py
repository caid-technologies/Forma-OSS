from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional


def _record(row: Dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**row)


class SupabaseRepository:
    """Application repository implemented through Supabase PostgREST."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def count_component_templates(self) -> int:
        rows = self._client.table("component_templates").select("id").execute().data or []
        return len(rows)

    def list_component_templates(self) -> List[Any]:
        rows = self._client.table("component_templates").select("*").order("id").execute().data or []
        return [_record(row) for row in rows]

    def get_component_template_by_part_number(self, part_number: str) -> Optional[Any]:
        rows = (
            self._client.table("component_templates")
            .select("*")
            .eq("part_number", part_number)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _record(rows[0]) if rows else None

    def insert_component_template(self, record: Dict[str, Any]) -> None:
        self._client.table("component_templates").insert(record).execute()

    def save_generated_project(
        self,
        record: Dict[str, Any],
        chat_record: Optional[Dict[str, Any]],
    ) -> None:
        self._client.table("generated_projects").insert(record).execute()
        if chat_record:
            self.upsert_project_chat(chat_record)

    def list_generated_projects(self, owner_user_id: Optional[str]) -> List[Any]:
        query = self._client.table("generated_projects").select(
            "id,project_id,chat_id,title,prompt,created_at,owner_user_id,visibility,hardware_ir"
        )
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        rows = query.order("id", desc=True).execute().data or []
        return [_record(row) for row in rows]

    def get_generated_project(self, project_id: str) -> Optional[Any]:
        rows = (
            self._client.table("generated_projects")
            .select("*")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _record(rows[0]) if rows else None

    def update_generated_project_hardware_ir(
        self,
        project_id: str,
        hardware_ir: Dict[str, Any],
        chat_id: Optional[str],
        owner_user_id: Optional[str],
    ) -> bool:
        query = self._client.table("generated_projects").update(
            {"hardware_ir": hardware_ir, "chat_id": chat_id}
        ).eq("project_id", project_id)
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        return bool(query.execute().data)

    def update_generated_project_metadata(
        self,
        project_id: str,
        owner_user_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        response = (
            self._client.table("generated_projects")
            .update(updates)
            .eq("project_id", project_id)
            .eq("owner_user_id", owner_user_id)
            .execute()
        )
        return bool(response.data)

    def delete_generated_project(self, project_id: str, owner_user_id: str) -> bool:
        response = (
            self._client.table("generated_projects")
            .delete()
            .eq("project_id", project_id)
            .eq("owner_user_id", owner_user_id)
            .execute()
        )
        return bool(response.data)

    def upsert_project_chat(self, record: Dict[str, Any]) -> Any:
        rows = (
            self._client.table("project_chats")
            .select("*")
            .eq("chat_id", record["chat_id"])
            .eq("owner_user_id", record["owner_user_id"])
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            response = (
                self._client.table("project_chats")
                .update(
                    {
                        "title": record["title"],
                        "messages": record["messages"],
                        "updated_at": record["updated_at"],
                    }
                )
                .eq("chat_id", record["chat_id"])
                .eq("owner_user_id", record["owner_user_id"])
                .execute()
            )
        else:
            response = self._client.table("project_chats").insert(record).execute()
        response_rows = response.data or []
        return _record(response_rows[0]) if response_rows else _record(record)

    def list_project_chats(self, owner_user_id: str) -> List[Any]:
        rows = (
            self._client.table("project_chats")
            .select("*")
            .eq("owner_user_id", owner_user_id)
            .order("updated_at", desc=True)
            .execute()
            .data
            or []
        )
        return [_record(row) for row in rows]

    def get_project_chat(self, chat_id: str, owner_user_id: str) -> Optional[Any]:
        rows = (
            self._client.table("project_chats")
            .select("*")
            .eq("chat_id", chat_id)
            .eq("owner_user_id", owner_user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _record(rows[0]) if rows else None

    def delete_project_chat(self, chat_id: str, owner_user_id: str) -> bool:
        response = (
            self._client.table("project_chats")
            .delete()
            .eq("chat_id", chat_id)
            .eq("owner_user_id", owner_user_id)
            .execute()
        )
        if response.data:
            (
                self._client.table("generated_projects")
                .update({"chat_id": None})
                .eq("chat_id", chat_id)
                .eq("owner_user_id", owner_user_id)
                .execute()
            )
        return bool(response.data)

    def save_alpha_signup(self, record: Dict[str, Any]) -> Any:
        response = self._client.table("alpha_signups").insert(record).execute()
        rows = response.data or []
        return _record(rows[0]) if rows else _record(record)

    def get_user_settings(self, owner_user_id: str) -> Optional[Any]:
        rows = (
            self._client.table("user_settings")
            .select("*")
            .eq("owner_user_id", owner_user_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return _record(rows[0]) if rows else None

    def upsert_user_settings(self, record: Dict[str, Any]) -> Any:
        response = (
            self._client.table("user_settings")
            .upsert(record, on_conflict="owner_user_id")
            .execute()
        )
        rows = response.data or []
        return _record(rows[0]) if rows else _record(record)

    def list_model_training_opt_out_user_ids(self) -> List[str]:
        rows = (
            self._client.table("user_settings")
            .select("owner_user_id")
            .eq("model_training_opt_out", True)
            .execute()
            .data
            or []
        )
        return [str(row["owner_user_id"]) for row in rows]
