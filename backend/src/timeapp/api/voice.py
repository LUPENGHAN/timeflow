"""Voice command intake endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from timeapp.ai.asr import AsrClient, AsrError
from timeapp.api.dependencies import get_asr_client, get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.realtime import realtime_manager
from timeapp.api.schemas import (
    EventResponse,
    ItemResponse,
    VoiceCommandCreateRequest,
    VoiceCommandCreateResponse,
    VoiceCommandResponse,
    WriteRequestResponse,
)
from timeapp.application.service import (
    ApplicationError,
    TimeflowApplication,
    VoiceCommandResult,
)
from timeapp.core.config import get_settings
from timeapp.domain.models import Identity, Reminder

router = APIRouter(prefix="/voice", tags=["voice-command"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]
AsrDependency = Annotated[AsrClient | None, Depends(get_asr_client)]
AudioUpload = Annotated[UploadFile, File()]


@router.post("/commands", response_model=VoiceCommandCreateResponse)
async def create_voice_command(
    request: VoiceCommandCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> VoiceCommandCreateResponse:
    """创建语音命令。"""

    try:
        result = app.submit_voice_command(request.transcript, identity)
    except ApplicationError as error:
        raise http_error(error) from error

    return await _voice_command_response(result, app, identity)


@router.post("/commands/audio", response_model=VoiceCommandCreateResponse)
async def create_audio_voice_command(
    identity: IdentityDependency,
    app: AppDependency,
    asr: AsrDependency,
    audio: AudioUpload,
) -> VoiceCommandCreateResponse:
    """创建audio 语音 命令。"""

    if asr is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "asr_not_configured", "message": "ASR API is not configured."},
        )

    content = await audio.read()
    settings = get_settings()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_audio", "message": "Audio file is empty."},
        )
    if len(content) > settings.asr_max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "audio_too_large", "message": "Audio file exceeds the upload limit."},
        )

    try:
        transcript = await run_in_threadpool(
            asr.transcribe,
            audio.filename or "recording",
            audio.content_type or "application/octet-stream",
            content,
        )
        result = app.submit_voice_command(transcript, identity)
    except AsrError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "asr_failed", "message": str(error)},
        ) from error
    except ApplicationError as error:
        raise http_error(error) from error

    return await _voice_command_response(result, app, identity)


async def _voice_command_response(
    result: VoiceCommandResult,
    app: TimeflowApplication,
    identity: Identity,
) -> VoiceCommandCreateResponse:
    """处理实例相关逻辑。"""

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
