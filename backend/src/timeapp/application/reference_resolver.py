"""Reference resolution for commands that point at existing items."""

from timeapp.application.store import Store
from timeapp.domain.enums import CommandEntity, ItemStatus, ItemType
from timeapp.domain.models import Command, Item


class ReferenceResolver:
    """Resolve recent item candidates without applying business writes."""

    def resolve_item_candidates(self, command: Command, store: Store) -> list[Item]:
        """解析事项 候选项。"""

        query = str(command.payload.get("reference_query") or command.title or "").strip()
        candidates = [
            item
            for item in store.list_items(command.identity.user_id)
            if item.status != ItemStatus.DELETED
            and self._entity_matches(command.entity, item)
            and self._query_matches(query, item)
        ]
        return sorted(candidates, key=lambda item: item.updated_at, reverse=True)[:3]

    def _entity_matches(self, entity: CommandEntity, item: Item) -> bool:
        """处理ReferenceResolver相关逻辑。"""
        if entity == CommandEntity.CALENDAR_EVENT:
            return item.item_type == ItemType.CALENDAR_EVENT
        if entity == CommandEntity.TODO:
            return item.item_type == ItemType.TODO
        return False

    def _query_matches(self, query: str, item: Item) -> bool:
        """处理ReferenceResolver相关逻辑。"""
        if not query:
            return True
        normalized = query.lower()
        return normalized in item.title.lower() or normalized in (item.description or "").lower()
