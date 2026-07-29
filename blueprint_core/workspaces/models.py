from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from blueprint_core.workspaces.chats.models import Chat
from blueprint_core.workspaces.projects.models import Project


class DesignThread(BaseModel):
    """A workspace chat and the durable projects generated from it."""

    chat: Chat
    projects: List[Project] = Field(default_factory=list)


class Workspace(BaseModel):
    """Aggregate root for one user's chats and projects."""

    owner_user_id: str
    chats: List[Chat] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)

    def design_threads(self) -> List[DesignThread]:
        """Group projects under chats without changing either resource's lifecycle."""

        projects_by_chat_id: dict[str, List[Project]] = {}
        for project in self.projects:
            if project.chat_id:
                projects_by_chat_id.setdefault(project.chat_id, []).append(project)
        return [
            DesignThread(chat=chat, projects=projects_by_chat_id.get(chat.chat_id, []))
            for chat in self.chats
        ]

    def standalone_projects(self) -> List[Project]:
        """Return projects not associated with a chat in this workspace."""

        chat_ids = {chat.chat_id for chat in self.chats}
        return [project for project in self.projects if not project.chat_id or project.chat_id not in chat_ids]
