"""Permission degradation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    EventResponse,
    ItemResponse,
    PermissionDegradeRequest,
    PermissionDegradeResponse,
)
from timeapp.api.realtime import realtime_manager
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.models import Identity

router = APIRouter(prefix="/permissions", tags=["permissions"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.post("/degrade", response_model=PermissionDegradeResponse)
async def degrade_permission(
    request: PermissionDegradeRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> PermissionDegradeResponse:
    """Apply a stable MVP permission degradation path."""

    try:
        item, events = app.degrade_permission(
            identity=identity,
            permission=request.permission,
            reason=request.reason,
            title=request.title,
            place_text=request.place_text,
        )
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(events)

    return PermissionDegradeResponse(
        item=ItemResponse.from_domain(item),
        events=[EventResponse.from_domain(event) for event in events],
    )
