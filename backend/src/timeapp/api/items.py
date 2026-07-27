"""Calendar and todo query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.schemas import ItemResponse
from timeapp.application.service import TimeflowApplication
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
