"""ms1 architecture baseline tables

Revision ID: 20260727_0002
Revises: 20260721_0001
Create Date: 2026-07-27

Creates the core audit/sync tables plus unified item, reminder and P0 place
tables described by the architecture baseline.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0002"
down_revision: str | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create MS1 architecture baseline tables."""

    op.create_table(
        "voice_commands",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("parsed_command", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_voice_commands_user_id", "voice_commands", ["user_id"])
    op.create_index("ix_voice_commands_status", "voice_commands", ["status"])

    op.create_table(
        "write_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("source_command_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_write_requests_idempotency_key"),
    )
    op.create_index("ix_write_requests_user_id", "write_requests", ["user_id"])
    op.create_index("ix_write_requests_status", "write_requests", ["status"])
    op.create_index("ix_write_requests_payload_hash", "write_requests", ["payload_hash"])
    op.create_index(
        "ix_write_requests_source_command_id",
        "write_requests",
        ["source_command_id"],
    )

    op.create_table(
        "domain_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])
    op.create_index("ix_domain_events_aggregate_type", "domain_events", ["aggregate_type"])
    op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"])
    op.create_index("ix_domain_events_occurred_at", "domain_events", ["occurred_at"])

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_messages_event_id", "outbox_messages", ["event_id"])
    op.create_index("ix_outbox_messages_channel", "outbox_messages", ["channel"])
    op.create_index("ix_outbox_messages_status", "outbox_messages", ["status"])

    op.create_table(
        "sync_cursors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("last_event_id", sa.String(length=36), nullable=True),
        sa.Column("last_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sync_cursors_user_id", "sync_cursors", ["user_id"])
    op.create_index("ix_sync_cursors_device_id", "sync_cursors", ["device_id"])

    op.create_table(
        "items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("place_text", sa.String(length=256), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_items_user_id", "items", ["user_id"])
    op.create_index("ix_items_item_type", "items", ["item_type"])
    op.create_index("ix_items_status", "items", ["status"])
    op.create_index("ix_items_start_at", "items", ["start_at"])
    op.create_index("ix_items_due_at", "items", ["due_at"])

    op.create_table(
        "places",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("place_type", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.String(length=64), nullable=True),
        sa.Column("longitude", sa.String(length=64), nullable=True),
        sa.Column("accuracy_meters", sa.Integer(), nullable=True),
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_places_user_id", "places", ["user_id"])
    op.create_index("ix_places_place_type", "places", ["place_type"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=36), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("trigger_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("place_id", sa.String(length=36), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("delivery_channel", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("snooze_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_notification_id", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_item_id", "reminders", ["item_id"])
    op.create_index("ix_reminders_trigger_type", "reminders", ["trigger_type"])
    op.create_index("ix_reminders_trigger_at", "reminders", ["trigger_at"])
    op.create_index("ix_reminders_place_id", "reminders", ["place_id"])
    op.create_index("ix_reminders_status", "reminders", ["status"])

    op.create_table(
        "reminder_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("rule_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reminder_rules_user_id", "reminder_rules", ["user_id"])
    op.create_index("ix_reminder_rules_item_id", "reminder_rules", ["item_id"])
    op.create_index("ix_reminder_rules_status", "reminder_rules", ["status"])

    op.create_table(
        "user_reminder_preferences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("preference_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_reminder_preferences_user_id"),
    )

    op.create_table(
        "reminder_rule_conditions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("condition_type", sa.String(length=64), nullable=False),
        sa.Column("condition_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_reminder_rule_conditions_rule_id",
        "reminder_rule_conditions",
        ["rule_id"],
    )
    op.create_index(
        "ix_reminder_rule_conditions_condition_type",
        "reminder_rule_conditions",
        ["condition_type"],
    )

    op.create_table(
        "reminder_occurrences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("reminder_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_reminder_occurrences_reminder_id",
        "reminder_occurrences",
        ["reminder_id"],
    )
    op.create_index("ix_reminder_occurrences_rule_id", "reminder_occurrences", ["rule_id"])
    op.create_index(
        "ix_reminder_occurrences_occurred_at",
        "reminder_occurrences",
        ["occurred_at"],
    )
    op.create_index("ix_reminder_occurrences_status", "reminder_occurrences", ["status"])


def downgrade() -> None:
    """Drop MS1 architecture baseline tables."""

    op.drop_index("ix_reminder_occurrences_status", table_name="reminder_occurrences")
    op.drop_index("ix_reminder_occurrences_occurred_at", table_name="reminder_occurrences")
    op.drop_index("ix_reminder_occurrences_rule_id", table_name="reminder_occurrences")
    op.drop_index("ix_reminder_occurrences_reminder_id", table_name="reminder_occurrences")
    op.drop_table("reminder_occurrences")

    op.drop_index(
        "ix_reminder_rule_conditions_condition_type",
        table_name="reminder_rule_conditions",
    )
    op.drop_index("ix_reminder_rule_conditions_rule_id", table_name="reminder_rule_conditions")
    op.drop_table("reminder_rule_conditions")

    op.drop_table("user_reminder_preferences")

    op.drop_index("ix_reminder_rules_status", table_name="reminder_rules")
    op.drop_index("ix_reminder_rules_item_id", table_name="reminder_rules")
    op.drop_index("ix_reminder_rules_user_id", table_name="reminder_rules")
    op.drop_table("reminder_rules")

    op.drop_index("ix_reminders_status", table_name="reminders")
    op.drop_index("ix_reminders_place_id", table_name="reminders")
    op.drop_index("ix_reminders_trigger_at", table_name="reminders")
    op.drop_index("ix_reminders_trigger_type", table_name="reminders")
    op.drop_index("ix_reminders_item_id", table_name="reminders")
    op.drop_index("ix_reminders_user_id", table_name="reminders")
    op.drop_table("reminders")

    op.drop_index("ix_places_place_type", table_name="places")
    op.drop_index("ix_places_user_id", table_name="places")
    op.drop_table("places")

    op.drop_index("ix_items_due_at", table_name="items")
    op.drop_index("ix_items_start_at", table_name="items")
    op.drop_index("ix_items_status", table_name="items")
    op.drop_index("ix_items_item_type", table_name="items")
    op.drop_index("ix_items_user_id", table_name="items")
    op.drop_table("items")

    op.drop_index("ix_sync_cursors_device_id", table_name="sync_cursors")
    op.drop_index("ix_sync_cursors_user_id", table_name="sync_cursors")
    op.drop_table("sync_cursors")

    op.drop_index("ix_outbox_messages_status", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_channel", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_event_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")

    op.drop_index("ix_domain_events_occurred_at", table_name="domain_events")
    op.drop_index("ix_domain_events_aggregate_id", table_name="domain_events")
    op.drop_index("ix_domain_events_aggregate_type", table_name="domain_events")
    op.drop_index("ix_domain_events_event_type", table_name="domain_events")
    op.drop_table("domain_events")

    op.drop_index("ix_write_requests_source_command_id", table_name="write_requests")
    op.drop_index("ix_write_requests_payload_hash", table_name="write_requests")
    op.drop_index("ix_write_requests_status", table_name="write_requests")
    op.drop_index("ix_write_requests_user_id", table_name="write_requests")
    op.drop_table("write_requests")

    op.drop_index("ix_voice_commands_status", table_name="voice_commands")
    op.drop_index("ix_voice_commands_user_id", table_name="voice_commands")
    op.drop_table("voice_commands")
