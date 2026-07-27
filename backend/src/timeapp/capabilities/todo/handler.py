"""Todo capability handler for confirmed write requests."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from timeapp.application.store import InMemoryStore
from timeapp.domain.enums import DomainEventType, ItemType
from timeapp.domain.models import DomainEvent, Item, WriteRequest, utc_now


class TodoCapability:
    """Create todo items after confirmation."""

    def apply(self, write_request: WriteRequest, store: InMemoryStore) -> list[DomainEvent]:
        """Create a todo item and emit an item-created event."""

        item_payload = write_request.candidate_payload["item"]
        item = Item(
            id=str(uuid4()),
            user_id=write_request.identity.user_id,
            item_type=ItemType.TODO,
            title=str(item_payload["title"]),
            description=self._optional_str(item_payload.get("description")),
            due_at=self._optional_datetime(item_payload.get("due_at")),
        )
        store.add_item(item)
        return [
            DomainEvent(
                id=str(uuid4()),
                event_type=DomainEventType.ITEM_CREATED,
                aggregate_type="item",
                aggregate_id=item.id,
                version=len(store.events) + 1,
                occurred_at=utc_now(),
                payload={"item": self._item_payload(item)},
            )
        ]

    def _optional_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value)

    def _optional_str(self, value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    def _item_payload(self, item: Item) -> dict[str, Any]:
        return {
            "id": item.id,
            "type": item.item_type.value,
            "title": item.title,
            "description": item.description,
            "start_at": item.start_at.isoformat() if item.start_at else None,
            "end_at": item.end_at.isoformat() if item.end_at else None,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "status": item.status.value,
        }
