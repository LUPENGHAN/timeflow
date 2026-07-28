"""Calendar and todo query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    EventResponse,
    ItemCreateRequest,
    ItemCreateResponse,
    ItemMutationResponse,
    ItemResponse,
    ItemUpdateRequest,
)
from timeapp.api.realtime import realtime_manager
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.enums import ItemStatus, ItemType
from timeapp.domain.errors import ErrorCode
from timeapp.domain.models import Identity, Reminder

router = APIRouter(prefix="/items", tags=["items"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.get("", response_model=list[ItemResponse])
async def list_items(
    identity: IdentityDependency,
    app: AppDependency,
) -> list[ItemResponse]:
    """列出用户事项。"""

    items = app.list_items(identity)
    reminders_by_item: dict[str, list[Reminder]] = {}
    for reminder in app.list_reminders(identity):
        reminders_by_item.setdefault(reminder.item_id, []).append(reminder)

    return [
        ItemResponse.from_domain(item, reminders_by_item.get(item.id, []))
        for item in sorted(items, key=lambda current: current.created_at)
    ]


@router.post("", response_model=ItemCreateResponse)
async def create_item(
    request: ItemCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> ItemCreateResponse:
    """创建事项。"""

    try:
        item_type = ItemType(request.type)
    except ValueError as error:
        raise http_error(
            ApplicationError(
                code=ErrorCode.UNKNOWN_ENTITY,
                message=f"Unsupported item type {request.type}.",
            )
        ) from error

    item, events = app.create_item(
        identity=identity,
        item_type=item_type,
        title=request.title,
        description=request.description,
        start_at=request.start_at,
        end_at=request.end_at,
        due_at=request.due_at,
        place_text=request.place_text,
        place_type=request.place_type,
        latitude=request.latitude,
        longitude=request.longitude,
        accuracy_meters=request.accuracy_meters,
        radius_meters=request.radius_meters,
    )
    await realtime_manager.broadcast_events(events)
    return ItemCreateResponse(
        item=ItemResponse.from_domain(item, []),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.patch("/{item_id}", response_model=ItemMutationResponse)
async def update_item(
    item_id: str,
    request: ItemUpdateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> ItemMutationResponse:
    """更新事项。"""

    try:
        item, events = app.update_item_fields(
            identity=identity,
            item_id=item_id,
            changes=request.model_dump(exclude_unset=True),
        )
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(events)

    reminders = [reminder for reminder in app.list_reminders(identity) if reminder.item_id == item.id]
    return ItemMutationResponse(
        item=ItemResponse.from_domain(item, reminders),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.post("/{item_id}/complete", response_model=ItemMutationResponse)
async def complete_item(
    item_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> ItemMutationResponse:
    """将事项标记为已完成。"""

    try:
        item, events = app.complete_item(identity, item_id)
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(events)

    reminders = [reminder for reminder in app.list_reminders(identity) if reminder.item_id == item.id]
    return ItemMutationResponse(
        item=ItemResponse.from_domain(item, reminders),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.post("/{item_id}/cancel-complete", response_model=ItemMutationResponse)
async def cancel_complete_item(
    item_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> ItemMutationResponse:
    """处理实例相关逻辑。"""

    try:
        item, events = app.update_item(identity, item_id, status=ItemStatus.ACTIVE)
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(events)

    reminders = [reminder for reminder in app.list_reminders(identity) if reminder.item_id == item.id]
    return ItemMutationResponse(
        item=ItemResponse.from_domain(item, reminders),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.delete("/{item_id}", response_model=ItemMutationResponse)
async def delete_item(
    item_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> ItemMutationResponse:
    """删除事项。"""

    try:
        item, events = app.delete_item(identity, item_id)
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(events)

    return ItemMutationResponse(
        item=ItemResponse.from_domain(item, []),
        events=[EventResponse.from_domain(event) for event in events],
    )
