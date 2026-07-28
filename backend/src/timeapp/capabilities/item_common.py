"""Item CRUD shared by the calendar and todo capabilities.

Both capabilities operate on the same underlying `items` table and the same
create/update/delete/complete rules regardless of `item_type`, so this logic
lives here once instead of being duplicated per capability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from timeapp.application.store import Store
from timeapp.domain.enums import DomainEventType, ItemStatus, ItemType
from timeapp.domain.errors import ApplicationError, ErrorCode
from timeapp.domain.models import DomainEvent, Identity, Item, utc_now


def item_payload(item: Item) -> dict[str, Any]:
    """序列化事项，用于事件载荷和候选预览。"""

    return {
        "id": item.id,
        "type": item.item_type.value,
        "title": item.title,
        "description": item.description,
        "start_at": item.start_at.isoformat() if item.start_at else None,
        "end_at": item.end_at.isoformat() if item.end_at else None,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "place_text": item.place_text,
        "place_type": item.place_type,
        "latitude": item.latitude,
        "longitude": item.longitude,
        "accuracy_meters": item.accuracy_meters,
        "radius_meters": item.radius_meters,
        "status": item.status.value,
        "version": item.version,
    }


def create_item(
    store: Store,
    identity: Identity,
    item_type: ItemType,
    title: str,
    description: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    due_at: datetime | None = None,
    place_text: str | None = None,
    place_type: str | None = None,
    latitude: str | None = None,
    longitude: str | None = None,
    accuracy_meters: int | None = None,
    radius_meters: int = 100,
) -> tuple[Item, list[DomainEvent]]:
    """创建事项。"""

    now = utc_now()
    item = Item(
        id=str(uuid4()),
        user_id=identity.user_id,
        item_type=item_type,
        title=title,
        description=description,
        status=ItemStatus.ACTIVE,
        start_at=start_at,
        end_at=end_at,
        due_at=due_at,
        place_text=place_text,
        place_type=place_type,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
        radius_meters=radius_meters,
        created_at=now,
        updated_at=now,
    )
    store.add_item(item)
    event = _event(
        store, DomainEventType.ITEM_CREATED, "item", item.id, {"item": item_payload(item)}
    )
    store.add_events([event])
    return item, [event]


def update_item_fields(
    store: Store,
    identity: Identity,
    item_id: str,
    changes: dict[str, Any],
) -> tuple[Item, list[DomainEvent]]:
    """按指定字段更新事项。"""

    item = store.get_item(item_id)
    if item is None or item.user_id != identity.user_id:
        raise ApplicationError(
            ErrorCode.ITEM_NOT_FOUND,
            f"Item {item_id} was not found.",
        )

    if "title" in changes:
        title = optional_str(changes.get("title"))
        if title is None:
            raise ApplicationError(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "Item title cannot be empty.",
            )
        item.title = title
    if "description" in changes:
        item.description = _nullable_str(changes.get("description"))
    if "start_at" in changes:
        item.start_at = _nullable_datetime(changes.get("start_at"))
    if "end_at" in changes:
        item.end_at = _nullable_datetime(changes.get("end_at"))
    if "due_at" in changes:
        item.due_at = _nullable_datetime(changes.get("due_at"))
    if "place_text" in changes:
        item.place_text = _nullable_str(changes.get("place_text"))
    if "place_type" in changes:
        item.place_type = _nullable_str(changes.get("place_type"))
    if "latitude" in changes:
        item.latitude = _nullable_str(changes.get("latitude"))
    if "longitude" in changes:
        item.longitude = _nullable_str(changes.get("longitude"))
    if "accuracy_meters" in changes:
        item.accuracy_meters = _nullable_int(changes.get("accuracy_meters"))
    if "radius_meters" in changes:
        radius_value = changes.get("radius_meters")
        if radius_value is not None:
            item.radius_meters = int(radius_value)
    if "status" in changes:
        status_value = changes.get("status")
        item.status = (
            status_value if isinstance(status_value, ItemStatus) else ItemStatus(str(status_value))
        )
    item.version += 1
    item.updated_at = utc_now()
    store.update_item(item)
    event = _event(
        store, DomainEventType.ITEM_UPDATED, "item", item.id, {"item": item_payload(item)}
    )
    store.add_events([event])
    return item, [event]


def update_item(
    store: Store,
    identity: Identity,
    item_id: str,
    title: str | None = None,
    description: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    due_at: datetime | None = None,
    place_text: str | None = None,
    place_type: str | None = None,
    latitude: str | None = None,
    longitude: str | None = None,
    accuracy_meters: int | None = None,
    radius_meters: int | None = None,
    status: ItemStatus | None = None,
) -> tuple[Item, list[DomainEvent]]:
    """更新事项。"""

    changes: dict[str, Any] = {}
    if title is not None:
        changes["title"] = title
    if description is not None:
        changes["description"] = description
    if start_at is not None:
        changes["start_at"] = start_at
    if end_at is not None:
        changes["end_at"] = end_at
    if due_at is not None:
        changes["due_at"] = due_at
    if place_text is not None:
        changes["place_text"] = place_text
    if place_type is not None:
        changes["place_type"] = place_type
    if latitude is not None:
        changes["latitude"] = latitude
    if longitude is not None:
        changes["longitude"] = longitude
    if accuracy_meters is not None:
        changes["accuracy_meters"] = accuracy_meters
    if radius_meters is not None:
        changes["radius_meters"] = radius_meters
    if status is not None:
        changes["status"] = status
    return update_item_fields(store, identity, item_id, changes)


def delete_item(
    store: Store,
    identity: Identity,
    item_id: str,
) -> tuple[Item, list[DomainEvent]]:
    """删除事项。"""

    return update_item(store, identity, item_id, status=ItemStatus.DELETED)


def complete_item(
    store: Store,
    identity: Identity,
    item_id: str,
) -> tuple[Item, list[DomainEvent]]:
    """将事项标记为已完成。"""

    return update_item(store, identity, item_id, status=ItemStatus.COMPLETED)


def degrade_permission(
    store: Store,
    identity: Identity,
    permission: str,
    reason: str,
    title: str,
    place_text: str | None = None,
) -> tuple[Item, list[DomainEvent]]:
    """处理权限降级。"""

    if permission != "location":
        raise ApplicationError(
            ErrorCode.PERMISSION_DENIED,
            f"{permission} permission is denied.",
        )
    item, item_events = create_item(
        store,
        identity=identity,
        item_type=ItemType.TODO,
        title=title,
        place_text=place_text,
    )
    degraded_event = _event(
        store,
        DomainEventType.PERMISSION_DEGRADED,
        "permission",
        permission,
        {
            "permission": permission,
            "reason": reason,
            "degraded_to": "todo_with_text_place",
            "item_id": item.id,
            "place_text": place_text,
        },
    )
    store.add_events([degraded_event])
    return item, [*item_events, degraded_event]


def _event(
    store: Store,
    event_type: DomainEventType,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> DomainEvent:
    """构造领域事件。"""
    return DomainEvent(
        id=str(uuid4()),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        version=len(store.events) + 1,
        occurred_at=utc_now(),
        payload=payload,
    )


def optional_datetime(value: Any) -> datetime | None:
    """解析可选的 ISO 日期时间字符串。"""

    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value)


def optional_str(value: Any) -> str | None:
    """解析可选字符串，空值直接返回 None。"""
    return value if isinstance(value, str) and value else None


def optional_int(value: Any) -> int | None:
    """解析可选整数，空值直接返回 None。"""
    if value is None:
        return None
    return int(value)


def _nullable_datetime(value: Any) -> datetime | None:
    """把可空输入统一转换为日期时间或 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return optional_datetime(value)


def _nullable_str(value: Any) -> str | None:
    """把可空输入统一转换为去空白后的字符串或 None。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _nullable_int(value: Any) -> int | None:
    """把可空输入统一转换为整数或 None。"""
    if value is None:
        return None
    return int(value)
