"""Voice command intake endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    EventResponse,
    VoiceCommandCreateRequest,
    VoiceCommandCreateResponse,
    VoiceCommandResponse,
    WriteRequestResponse,
)
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.models import Identity

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

    return VoiceCommandCreateResponse(
        voice_command=VoiceCommandResponse.from_domain(result.voice_command),
        write_request=WriteRequestResponse.from_domain(result.write_request)
        if result.write_request
        else None,
        events=[EventResponse.from_domain(event) for event in result.events],
        clarification=result.clarification,
    )
