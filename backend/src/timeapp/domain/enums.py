"""Stable enum values shared across capabilities and API boundaries."""

from enum import StrEnum


class CommandAction(StrEnum):
    """User intent verbs understood by the command layer."""

    CREATE = "create"
    QUERY = "query"
    UPDATE = "update"
    DELETE = "delete"
    COMPLETE = "complete"
    REMIND = "remind"
    SPLIT = "split"
    REPLAN = "replan"


class CommandEntity(StrEnum):
    """Stable target entities for commands."""

    CALENDAR_EVENT = "calendar_event"
    TODO = "todo"
    REMINDER = "reminder"
    RULE = "rule"


class WriteRequestStatus(StrEnum):
    """Confirmation gate states."""

    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    EXPIRED = "expired"


class VoiceCommandStatus(StrEnum):
    """ASR and parser lifecycle for a voice command."""

    RECEIVED = "received"
    TRANSCRIBED = "transcribed"
    PARSED = "parsed"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"


class ItemType(StrEnum):
    """Calendar and todo share a unified item table."""

    CALENDAR_EVENT = "calendar_event"
    TODO = "todo"


class ItemStatus(StrEnum):
    """P0 item states."""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


class ReminderTriggerType(StrEnum):
    """P0 reminder trigger types."""

    TIME = "time"
    ENTER_PLACE = "enter_place"
    LEAVE_PLACE = "leave_place"
    RETURN_TO_PLACE = "return_to_place"


class ReminderStatus(StrEnum):
    """Reminder lifecycle states required by the product baseline."""

    PENDING = "pending"
    ARMED = "armed"
    TRIGGERED = "triggered"
    DELIVERED = "delivered"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class ReminderPriority(StrEnum):
    """Priority affects delivery policy, not business identity."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class DeliveryChannel(StrEnum):
    """P0 only activates local notification delivery."""

    LOCAL_NOTIFICATION = "local_notification"


class NotificationRegistrationStatus(StrEnum):
    """Client local-notification registration state."""

    PENDING = "pending"
    REGISTERED = "registered"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class FallbackStatus(StrEnum):
    """Cloud fallback state; P0 records requests without real delivery."""

    NOT_REQUIRED = "not_required"
    REQUESTED = "requested"
    SENT = "sent"
    FAILED = "failed"


class DomainEventType(StrEnum):
    """Domain and realtime event names shared with WebSocket clients."""

    CONNECTION_READY = "connection.ready"
    COMMAND_STATUS_CHANGED = "command.status.changed"
    WRITE_REQUEST_CREATED = "write_request.created"
    WRITE_REQUEST_UPDATED = "write_request.updated"
    WRITE_REQUEST_APPLIED = "write_request.applied"
    WRITE_REQUEST_REJECTED = "write_request.rejected"
    ITEM_CREATED = "item.created"
    ITEM_UPDATED = "item.updated"
    REMINDER_ARMED = "reminder.armed"
    REMINDER_DUE = "reminder.due"
    REMINDER_DELIVERED = "reminder.delivered"
    REMINDER_DISMISSED = "reminder.dismissed"
    REMINDER_SNOOZED = "reminder.snoozed"
    REMINDER_CANCELLED = "reminder.cancelled"
    REMINDER_EXPIRED = "reminder.expired"
    REMINDER_FAILED = "reminder.failed"
    NOTIFICATION_REGISTRATION_FAILED = "notification.registration.failed"
    NOTIFICATION_FALLBACK_REQUESTED = "notification.fallback.requested"
    SYNC_RESPONSE = "sync.response"
