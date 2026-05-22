from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import KnowledgeBase
from providers.graph_store import (
    fetch_graph_view,
    get_graph_store_provider_name,
    list_graph_relation_types,
)


class GraphDataService:
    @staticmethod
    async def list_relation_types(kb_id: str, file_id: str | None = None) -> dict:
        relation_types = await asyncio.to_thread(list_graph_relation_types, kb_id, file_id)
        return {
            "provider": get_graph_store_provider_name(),
            "kb_id": kb_id,
            "file_id": file_id,
            "items": relation_types,
        }

    @staticmethod
    async def get_view(
        db: AsyncSession,
        kb_id: str,
        file_id: str | None = None,
        entity_query: str | None = None,
        relation_type: str | None = None,
    ) -> dict:
        kb = (
            await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
        ).scalar_one_or_none()
        if not kb:
            raise ValueError("Knowledge base not found")

        data = await asyncio.to_thread(
            fetch_graph_view,
            kb_id,
            file_id,
            entity_query,
            relation_type,
        )
        data["provider"] = get_graph_store_provider_name()
        data["kb"] = {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
        }
        data["filters"] = {
            "kb_id": kb_id,
            "file_id": file_id,
            "entity_query": entity_query or "",
            "relation_type": relation_type or "",
        }
        return data
