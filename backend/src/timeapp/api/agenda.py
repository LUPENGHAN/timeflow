"""Agenda projection endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.schemas import AgendaResponse, ItemResponse, ReminderResponse
from timeapp.application.service import TimeflowApplication
from timeapp.domain.models import Identity

router = APIRouter(prefix="/agenda", tags=["agenda"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.get("", response_model=AgendaResponse)
async def get_agenda(
    identity: IdentityDependency,
    app: AppDependency,
) -> AgendaResponse:
    """Return a single-panel agenda projection for the current user."""

    items = app.list_items(identity)
    reminders = [
        reminder
        for reminder in app.store.reminders.values()
        if reminder.user_id == identity.user_id
    ]
    return AgendaResponse(
        items=[
            ItemResponse.from_domain(item)
            for item in sorted(items, key=lambda current: current.created_at)
        ],
        reminders=[
            ReminderResponse.from_domain(reminder)
            for reminder in sorted(reminders, key=lambda current: current.created_at)
        ],
    )
