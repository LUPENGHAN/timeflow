"""Mock ASR/parser components for the P0 skeleton."""

from __future__ import annotations

import re
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
            range_start, range_end = self._extract_query_range(normalized, now)
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.QUERY,
                entity=CommandEntity.CALENDAR_EVENT,
                title=normalized,
                time_range_start=range_start,
                time_range_end=range_end,
            )

        if "改到" in normalized or "改为" in normalized:
            start_at = self._extract_update_time(normalized, now)
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.UPDATE,
                entity=CommandEntity.CALENDAR_EVENT
                if "会议" in normalized or "日程" in normalized
                else CommandEntity.TODO,
                title="会议" if "会议" in normalized else normalized,
                start_at=start_at,
                end_at=start_at + timedelta(hours=1) if start_at else None,
                payload={
                    "operation": "update_item",
                    "reference_query": "会议" if "会议" in normalized else normalized,
                    "source_text": normalized,
                },
            )

        if self._looks_like_delete(normalized):
            reference_query = self._extract_delete_reference(normalized)
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.DELETE,
                entity=CommandEntity.CALENDAR_EVENT
                if "会议" in normalized or "日程" in normalized or "安排" in normalized
                else CommandEntity.TODO,
                title=reference_query,
                payload={
                    "operation": "delete_item",
                    "reference_query": reference_query,
                    "source_text": normalized,
                },
            )

        if self._looks_like_complete(normalized):
            reference_query = self._extract_complete_reference(normalized)
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.COMPLETE,
                entity=CommandEntity.TODO,
                title=reference_query,
                payload={
                    "operation": "complete_item",
                    "reference_query": reference_query,
                    "source_text": normalized,
                },
            )

        if "提醒" in normalized:
            title = self._extract_title_after_reminder(normalized)
            trigger_type = self._extract_place_trigger(normalized)
            trigger_at = self._extract_explicit_datetime(normalized, now)
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
                        "trigger_at": trigger_at.isoformat()
                        if trigger_type == ReminderTriggerType.TIME and trigger_at
                        else (
                            (now + timedelta(minutes=30)).isoformat()
                            if trigger_type == ReminderTriggerType.TIME
                            else None
                        ),
                    },
                    "source_text": normalized,
                },
            )

        if self._looks_like_calendar_event(normalized):
            start_at = self._extract_explicit_datetime(normalized, now)
            if start_at is None:
                start_at = now + timedelta(days=1)
            return Command(
                id=command_id,
                identity=identity,
                action=CommandAction.CREATE,
                entity=CommandEntity.CALENDAR_EVENT,
                title=normalized,
                start_at=start_at,
                end_at=start_at + timedelta(hours=1),
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

    def _extract_query_range(self, transcript: str, now: datetime) -> tuple[datetime, datetime]:
        if "明天" in transcript:
            start = self._start_of_day(now + timedelta(days=1))
            return start, start + timedelta(days=1)
        if "本周" in transcript or "这周" in transcript:
            start = self._start_of_day(now)
            return start, start + timedelta(days=7)
        start = self._start_of_day(now)
        return start, start + timedelta(days=1)

    def _start_of_day(self, value: datetime) -> datetime:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    def _looks_like_delete(self, transcript: str) -> bool:
        return transcript.startswith("取消") or transcript.startswith("删除")

    def _looks_like_complete(self, transcript: str) -> bool:
        return "买好了" in transcript or "完成了" in transcript or transcript.endswith("完成")

    def _looks_like_calendar_event(self, transcript: str) -> bool:
        return (
            "会议" in transcript
            or "日程" in transcript
            or "安排" in transcript
            or ("开" in transcript and "会" in transcript)
        )

    def _extract_delete_reference(self, transcript: str) -> str:
        reference = transcript.removeprefix("取消").removeprefix("删除").strip()
        reference = reference.replace("明天的", "").replace("明天", "").strip()
        return "会议" if "会议" in reference else reference

    def _extract_complete_reference(self, transcript: str) -> str:
        reference = transcript
        for marker in ["买好了", "完成了", "完成"]:
            reference = reference.replace(marker, "")
        return reference.removeprefix("把").strip()

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

    def _extract_update_time(self, transcript: str, now: datetime) -> datetime | None:
        return self._extract_explicit_datetime(transcript, now)

    def _extract_explicit_datetime(self, transcript: str, now: datetime) -> datetime | None:
        match = re.search(
            r"(?:(今天|明天|后天|大后天))?"
            r"(?:(凌晨|早上|上午|中午|下午|晚上))?"
            r"(?:(\d{1,2}|[零一二两三四五六七八九十]{1,3}))点"
            r"(?:(\d{1,2})分?|(?P<half>半))?",
            transcript,
        )
        if match is None:
            return None

        day_text, period_text, hour_text, minute_text = match.group(1), match.group(2), match.group(3), match.group(4)
        day_offset = {
            "今天": 0,
            "明天": 1,
            "后天": 2,
            "大后天": 3,
        }.get(day_text or "今天", 0)

        hour = self._parse_chinese_number(hour_text)
        if hour is None:
            return None

        minute = 0
        if minute_text is not None:
            minute = int(minute_text)
        elif match.group("half") is not None:
            minute = 30

        if period_text in {"下午", "晚上"} and hour < 12:
            hour += 12
        if period_text == "中午" and hour < 11:
            hour = 12 if hour == 0 else hour + 12
        if period_text == "凌晨" and hour == 12:
            hour = 0
        if period_text in {"早上", "上午"} and hour == 12:
            hour = 0
        if period_text is None and 1 <= hour <= 6:
            hour += 12

        result = self._start_of_day(now + timedelta(days=day_offset)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if day_text in {None, "今天"} and result <= now:
            result += timedelta(days=1)
        return result

    def _parse_chinese_number(self, value: str) -> int | None:
        if value.isdigit():
            return int(value)
        digit_map = {
            "零": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if value == "十":
            return 10
        if len(value) == 2 and value.startswith("十"):
            return 10 + digit_map.get(value[1], 0)
        if len(value) == 2 and value.endswith("十"):
            return digit_map.get(value[0], 0) * 10
        if len(value) == 3 and value[1] == "十":
            return digit_map.get(value[0], 0) * 10 + digit_map.get(value[2], 0)
        if len(value) == 2 and "十" in value:
            left, right = value.split("十", maxsplit=1)
            return digit_map.get(left, 1) * 10 + digit_map.get(right, 0)
        if len(value) == 1:
            return digit_map.get(value)
        return None
