"""Event sync endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from timeapp.api.dependencies import get_timeflow_app
from timeapp.api.schemas import EventListResponse, EventResponse, OutboxMessageResponse
from timeapp.application.service import TimeflowApplication

router = APIRouter(prefix="/events", tags=["events"])
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]
CursorQuery = Annotated[int, Query(ge=0)]


@router.get("", response_model=EventListResponse)
async def list_events(
    app: AppDependency,
    after: CursorQuery = 0,
) -> EventListResponse:
    """Return domain events after a client cursor."""

    events = app.list_events(after)
    return EventListResponse(
        next_cursor=after + len(events),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.get("/outbox", response_model=list[OutboxMessageResponse])
async def list_outbox_messages(app: AppDependency) -> list[OutboxMessageResponse]:
    """Return skeleton outbox messages derived from domain events."""

    return [
        OutboxMessageResponse.from_domain(message) for message in app.store.list_outbox_messages()
    ]
