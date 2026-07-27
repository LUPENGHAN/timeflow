"""Reminder query and action endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    EventResponse,
    ReminderCreateRequest,
    ReminderCreateResponse,
    ReminderActionRequest,
    ReminderActionResponse,
    ReminderResponse,
)
from timeapp.application.service import ApplicationError, TimeflowApplication
from timeapp.domain.enums import ReminderPriority, ReminderTriggerType
from timeapp.domain.errors import ErrorCode
from timeapp.domain.models import Identity

router = APIRouter(prefix="/reminders", tags=["reminders"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.get("", response_model=list[ReminderResponse])
async def list_reminders(
    identity: IdentityDependency,
    app: AppDependency,
) -> list[ReminderResponse]:
    """Return reminders for the current user."""

    return [ReminderResponse.from_domain(reminder) for reminder in app.list_reminders(identity)]


@router.post("", response_model=ReminderCreateResponse)
async def create_reminder(
    request: ReminderCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> ReminderCreateResponse:
    """Create a reminder bound to an existing item."""

    try:
        trigger_type = ReminderTriggerType(request.trigger_type)
        priority = ReminderPriority(request.priority)
        reminder, events = app.create_reminder(
            identity=identity,
            item_id=request.item_id,
            trigger_type=trigger_type,
            trigger_at=request.trigger_at,
            place_id=request.place_id,
            priority=priority,
        )
    except ValueError as error:
        raise http_error(
            ApplicationError(
                code=ErrorCode.UNKNOWN_ACTION,
                message="Unsupported reminder trigger_type or priority.",
            )
        ) from error
    except ApplicationError as error:
        raise http_error(error) from error

    return ReminderCreateResponse(
        reminder=ReminderResponse.from_domain(reminder),
        events=[EventResponse.from_domain(event) for event in events],
    )


@router.post("/{reminder_id}/actions", response_model=ReminderActionResponse)
async def apply_reminder_action(
    reminder_id: str,
    request: ReminderActionRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> ReminderActionResponse:
    """Apply local notification/reminder action feedback."""

    try:
        reminder, events = app.apply_reminder_action(
            identity=identity,
            reminder_id=reminder_id,
            action=request.action,
            failed_reason=request.failed_reason,
            local_notification_id=request.local_notification_id,
            snooze_minutes=request.snooze_minutes,
            fallback_after_seconds=request.fallback_after_seconds,
        )
    except ApplicationError as error:
        raise http_error(error) from error

    return ReminderActionResponse(
        reminder=ReminderResponse.from_domain(reminder),
        events=[EventResponse.from_domain(event) for event in events],
    )
