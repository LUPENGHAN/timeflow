"""Calendar capability handler: create, update, delete and query calendar events."""

from __future__ import annotations

from uuid import uuid4

from timeapp.application.store import Store
from timeapp.capabilities import item_common
from timeapp.domain.enums import DomainEventType, ItemType
from timeapp.domain.models import DomainEvent, Identity, Item, WriteRequest, utc_now


class CalendarCapability:
    """Own calendar_event items after the confirmation gate has approved them."""

    def apply(
        self,
        write_request: WriteRequest,
        store: Store,
    ) -> list[DomainEvent]:
        """应用处理逻辑。"""

        item_payload = write_request.candidate_payload["item"]
        item = Item(
            id=str(uuid4()),
            user_id=write_request.identity.user_id,
            item_type=ItemType.CALENDAR_EVENT,
            title=str(item_payload["title"]),
            description=item_common.optional_str(item_payload.get("description")),
            start_at=item_common.optional_datetime(item_payload.get("start_at")),
            end_at=item_common.optional_datetime(item_payload.get("end_at")),
            place_text=item_common.optional_str(item_payload.get("place_text")),
            place_type=item_common.optional_str(item_payload.get("place_type")),
            latitude=item_common.optional_str(item_payload.get("latitude")),
            longitude=item_common.optional_str(item_payload.get("longitude")),
            accuracy_meters=item_common.optional_int(item_payload.get("accuracy_meters")),
            radius_meters=item_common.optional_int(item_payload.get("radius_meters")) or 100,
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
                payload={"item": item_common.item_payload(item)},
            )
        ]

    def update(
        self,
        store: Store,
        identity: Identity,
        item_id: str,
        changes: dict[str, object],
    ) -> tuple[Item, list[DomainEvent]]:
        """更新既有对象。"""

        return item_common.update_item_fields(store, identity, item_id, changes)

    def delete(
        self,
        store: Store,
        identity: Identity,
        item_id: str,
    ) -> tuple[Item, list[DomainEvent]]:
        """删除既有对象。"""

        return item_common.delete_item(store, identity, item_id)
