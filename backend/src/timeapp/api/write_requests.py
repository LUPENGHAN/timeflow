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
    """Create a pending write request from a candidate payload."""

    write_request, events = app.create_write_request(
        identity,
        request.source_command_id,
        request.candidate_payload,
    )
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
    """Edit a pending write request without applying it."""

    try:
        result = app.update_write_request(
            write_request_id,
            identity,
            request.candidate_payload,
        )
    except ApplicationError as error:
        raise http_error(error) from error

    return ConfirmationResponse(
        write_request=WriteRequestResponse.from_domain(result.write_request),
        events=[EventResponse.from_domain(event) for event in result.events],
    )


@router.get("/pending", response_model=list[WriteRequestResponse])
async def list_pending_write_requests(
    identity: IdentityDependency,
    app: AppDependency,
) -> list[WriteRequestResponse]:
    """Return pending write requests for the current user."""

    return [
        WriteRequestResponse.from_domain(write_request)
        for write_request in app.list_pending_write_requests(identity)
    ]


@router.post("/{write_request_id}/confirm", response_model=ConfirmationResponse)
async def confirm_write_request(
    write_request_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> ConfirmationResponse:
    """Confirm and apply a write request through active capability handlers."""

    try:
        result = app.confirm_write_request(write_request_id, identity)
    except ApplicationError as error:
        raise http_error(error) from error

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
    """Reject a pending write request."""

    try:
        result = app.reject_write_request(write_request_id, identity)
    except ApplicationError as error:
        raise http_error(error) from error

    return ConfirmationResponse(
        write_request=WriteRequestResponse.from_domain(result.write_request),
        events=[EventResponse.from_domain(event) for event in result.events],
    )
