"""Calendar and todo query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import EventResponse, ItemCreateRequest, ItemCreateResponse, ItemResponse
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.enums import ItemType
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
    """Return current user's calendar and todo items."""

    items = app.list_items(identity)
    reminders_by_item: dict[str, list[Reminder]] = {}
    for reminder in app.store.reminders.values():
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
    """Create a manual calendar or todo item."""

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
    )
    return ItemCreateResponse(
        item=ItemResponse.from_domain(item, []),
        events=[EventResponse.from_domain(event) for event in events],
    )
