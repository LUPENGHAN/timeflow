"""Voice command intake endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    EventResponse,
    ItemResponse,
    VoiceCommandCreateRequest,
    VoiceCommandCreateResponse,
    VoiceCommandResponse,
    WriteRequestResponse,
)
from timeapp.api.realtime import realtime_manager
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.models import Identity, Reminder

router = APIRouter(prefix="/voice", tags=["voice-command"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.post("/commands", response_model=VoiceCommandCreateResponse)
async def create_voice_command(
    request: VoiceCommandCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> VoiceCommandCreateResponse:
    """Create a mock voice command and pending write request when applicable."""

    try:
        result = app.submit_voice_command(request.transcript, identity)
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(result.events)
    reminders_by_item: dict[str, list[Reminder]] = {}
    for reminder in app.list_reminders(identity):
        reminders_by_item.setdefault(reminder.item_id, []).append(reminder)

    return VoiceCommandCreateResponse(
        voice_command=VoiceCommandResponse.from_domain(result.voice_command),
        write_request=WriteRequestResponse.from_domain(result.write_request)
        if result.write_request
        else None,
        events=[EventResponse.from_domain(event) for event in result.events],
        clarification=result.clarification,
        candidates=[
            ItemResponse.from_domain(item, reminders_by_item.get(item.id, []))
            for item in result.candidates
        ],
    )
