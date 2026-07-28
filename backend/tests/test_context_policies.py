"""Tests for reminder context policies."""

from datetime import UTC, datetime

from timeapp.context.policies import CloudFallbackPolicy
from timeapp.domain.enums import FallbackStatus, ReminderPriority, ReminderStatus
from timeapp.domain.models import Reminder, ReminderTriggerType


def test_cloud_fallback_policy_marks_requested_and_builds_payload() -> None:
    """Fallback policy should only mark local failures and emit a payload."""

    policy = CloudFallbackPolicy()
    reminder = Reminder(
        id="rem-1",
        user_id="user-1",
        item_id="item-1",
        trigger_type=ReminderTriggerType.TIME,
        priority=ReminderPriority.NORMAL,
        status=ReminderStatus.PENDING,
    )
    now = datetime.now(UTC)

    assert policy.should_request("registration_failed")
    payload = policy.request(reminder, now, 180, "permission_denied")

    assert reminder.fallback_status == FallbackStatus.REQUESTED
    assert reminder.fallback_after_seconds == 180
    assert reminder.fallback_requested_at == now
    assert payload == {
        "reminder_id": "rem-1",
        "fallback_after_seconds": 180,
        "failed_reason": "permission_denied",
    }


def test_cloud_fallback_policy_ignores_non_failure_actions() -> None:
    """Non failure reminder actions should not request fallback."""

    policy = CloudFallbackPolicy()
    assert not policy.should_request("delivered")
