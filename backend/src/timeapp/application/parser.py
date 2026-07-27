"""Mock ASR/parser components for the P0 skeleton."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from timeapp.domain.enums import CommandAction, CommandEntity, ReminderTriggerType
from timeapp.domain.models import Command, Identity


class MockCommandParser:
    """Parse a small set of common Mandarin MVP utterances into commands."""

    def parse(self, transcript: str, identity: Identity) -> Command:
        """Return a structured command candidate without writing business facts."""

        normalized = transcript.strip()
        command_id = str(uuid4())
        now = datetime.now(UTC)

        if self._looks_like_query(normalized):
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.QUERY,
                entity=CommandEntity.CALENDAR_EVENT,
                title=normalized,
                time_range_start=now,
                time_range_end=now + timedelta(days=1),
            )

        if "提醒" in normalized:
            title = self._extract_title_after_reminder(normalized)
            trigger_type = self._extract_place_trigger(normalized)
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.CREATE,
                entity=CommandEntity.TODO,
                title=title,
                payload={
                    "operation": "create_todo_with_reminder",
                    "reminder": {
                        "trigger_type": trigger_type.value,
                        "place_ref": "家" if "家" in normalized else None,
                        "trigger_at": (now + timedelta(minutes=30)).isoformat()
                        if trigger_type == ReminderTriggerType.TIME
                        else None,
                    },
                    "source_text": normalized,
                },
            )

        if "会议" in normalized or "日程" in normalized or "安排" in normalized:
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.CREATE,
                entity=CommandEntity.CALENDAR_EVENT,
                title=normalized,
                start_at=now + timedelta(days=1),
                end_at=now + timedelta(days=1, hours=1),
                payload={"operation": "create_calendar_event", "source_text": normalized},
            )

        title = normalized.removeprefix("记得").strip() or normalized
        return Command(
            id=command_id,
            identity=identity,
            action=CommandAction.CREATE,
            entity=CommandEntity.TODO,
            title=title,
            payload={"operation": "create_todo", "source_text": normalized},
        )

    def _looks_like_query(self, transcript: str) -> bool:
        return "什么安排" in transcript or transcript.startswith("查询")

    def _extract_title_after_reminder(self, transcript: str) -> str:
        if "提醒我" in transcript:
            return transcript.split("提醒我", maxsplit=1)[1].strip() or transcript
        return transcript

    def _extract_place_trigger(self, transcript: str) -> ReminderTriggerType:
        if "到家" in transcript or "进入" in transcript:
            return ReminderTriggerType.ENTER_PLACE
        if "离开" in transcript:
            return ReminderTriggerType.LEAVE_PLACE
        if "回到" in transcript:
            return ReminderTriggerType.RETURN_TO_PLACE
        return ReminderTriggerType.TIME
