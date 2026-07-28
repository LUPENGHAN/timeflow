"""Stable error codes used at API and application boundaries."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Errors that clients can safely branch on."""

    UNKNOWN_ACTION = "unknown_action"
    UNKNOWN_ENTITY = "unknown_entity"
    PERMISSION_DENIED = "permission_denied"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_FIELD_VALUE = "invalid_field_value"
    WRITE_REQUEST_NOT_FOUND = "write_request_not_found"
    WRITE_REQUEST_NOT_PENDING = "write_request_not_pending"
    WRITE_REQUEST_EXPIRED = "write_request_expired"
    ITEM_NOT_FOUND = "item_not_found"
    REMINDER_NOT_FOUND = "reminder_not_found"
    CAPABILITY_NOT_ACTIVE = "capability_not_active"
    CLARIFICATION_REQUIRED = "clarification_required"
    SNOOZE_LIMIT_REACHED = "snooze_limit_reached"


class ApplicationError(RuntimeError):
    """Application-layer error with a stable client-facing code.

    Raised by capability handlers as well as the application service, so it
    lives in `domain` (core) where both layers can depend on it without a
    circular import.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        """初始化实例。"""
        super().__init__(message)
        self.code = code
        self.message = message
