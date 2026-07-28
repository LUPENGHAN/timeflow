"""Confirmation gate endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    ConfirmationResponse,
    EventResponse,
    WriteRequestCreateRequest,
    WriteRequestCreateResponse,
    WriteRequestResponse,
    WriteRequestUpdateRequest,
)
from timeapp.api.realtime import realtime_manager
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.models import Identity

router = APIRouter(prefix="/write-requests", tags=["write-requests"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.post("", response_model=WriteRequestCreateResponse)
async def create_write_request(
    request: WriteRequestCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> WriteRequestCreateResponse:
    """创建写请求。"""

    write_request, events = app.create_write_request(
        identity,
        request.source_command_id,
        request.candidate_payload,
    )
    await realtime_manager.broadcast_events(events)
    return WriteRequestCreateResponse(
        write_request=WriteRequestResponse.from_domain(write_request),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.patch("/{write_request_id}", response_model=ConfirmationResponse)
async def update_write_request(
    write_request_id: str,
    request: WriteRequestUpdateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> ConfirmationResponse:
    """更新写请求。"""

    try:
        result = app.update_write_request(
            write_request_id,
            identity,
            request.candidate_payload,
        )
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(result.events)

    return ConfirmationResponse(
        write_request=WriteRequestResponse.from_domain(result.write_request),
        events=[EventResponse.from_domain(event) for event in result.events],
    )


@router.get("/pending", response_model=list[WriteRequestResponse])
async def list_pending_write_requests(
    identity: IdentityDependency,
    app: AppDependency,
) -> list[WriteRequestResponse]:
    """列出当前用户待确认的写请求。"""

    return [
        WriteRequestResponse.from_domain(write_request)
        for write_request in app.list_pending_write_requests(identity)
    ]


@router.get("/{write_request_id}", response_model=WriteRequestResponse)
async def get_write_request(
    write_request_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> WriteRequestResponse:
    """按 ID 获取写请求。"""

    try:
        write_request = app.get_write_request(write_request_id, identity)
    except ApplicationError as error:
        raise http_error(error) from error

    return WriteRequestResponse.from_domain(write_request)


@router.post("/{write_request_id}/confirm", response_model=ConfirmationResponse)
async def confirm_write_request(
    write_request_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> ConfirmationResponse:
    """确认写请求并应用变更。"""

    try:
        result = app.confirm_write_request(write_request_id, identity)
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(result.events)

    return ConfirmationResponse(
        write_request=WriteRequestResponse.from_domain(result.write_request),
        events=[EventResponse.from_domain(event) for event in result.events],
    )


@router.post("/{write_request_id}/reject", response_model=ConfirmationResponse)
async def reject_write_request(
    write_request_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> ConfirmationResponse:
    """拒绝写请求。"""

    try:
        result = app.reject_write_request(write_request_id, identity)
    except ApplicationError as error:
        raise http_error(error) from error

    await realtime_manager.broadcast_events(result.events)

    return ConfirmationResponse(
        write_request=WriteRequestResponse.from_domain(result.write_request),
        events=[EventResponse.from_domain(event) for event in result.events],
    )
