from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import sessionmaker

from blueprint_core.persistence.models import (
    DBAlphaSignup,
    DBComponentTemplate,
    DBGeneratedProject,
    DBProjectChat,
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
            query = session.query(DBGeneratedProject)
            if owner_user_id:
                query = query.filter(DBGeneratedProject.owner_user_id == owner_user_id)
            return query.order_by(DBGeneratedProject.id.desc()).all()

    def get_generated_project(self, project_id: str) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBGeneratedProject).filter(
                DBGeneratedProject.project_id == project_id
            ).first()

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
            session.delete(project)
            return True

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
            return session.query(DBProjectChat).filter(
                DBProjectChat.owner_user_id == owner_user_id
            ).order_by(DBProjectChat.updated_at.desc()).all()

    def get_project_chat(self, chat_id: str, owner_user_id: str) -> Optional[Any]:
        with self._session() as session:
            return session.query(DBProjectChat).filter(
                DBProjectChat.chat_id == chat_id,
                DBProjectChat.owner_user_id == owner_user_id,
            ).first()

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
