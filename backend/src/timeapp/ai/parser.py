"""Command parsers for transcript-based voice commands."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from timeapp.domain.enums import CommandAction, CommandEntity, ReminderPriority, ReminderTriggerType
from timeapp.domain.models import Command, Identity

logger = logging.getLogger(__name__)


class LLMCommandParser:
    """Parse free-form transcripts through an OpenAI-compatible chat API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        fallback: MockCommandParser | None = None,
    ) -> None:
        """初始化实例。"""
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback = fallback or MockCommandParser()

    def parse(self, transcript: str, identity: Identity) -> Command:
        """解析输入并返回结构化结果。"""

        try:
            payload = self._request_command(transcript)
            return self._to_command(payload, transcript, identity)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            logger.warning("LLM command parsing failed; using local parser: %s", error)
            return self.fallback.parse(transcript, identity)

    def _request_command(self, transcript: str) -> dict[str, Any]:
        """向模型请求命令。"""
        now = datetime.now(UTC)
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": self._system_prompt(now),
                    },
                    {"role": "user", "content": transcript},
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("LLM response content must be a string.")
        parsed = json.loads(self._strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise TypeError("LLM response must be a JSON object.")
        return parsed

    def _to_command(
        self,
        payload: dict[str, Any],
        transcript: str,
        identity: Identity,
    ) -> Command:
        """将载荷转换为命令。"""
        action = CommandAction(str(payload["action"]))
        entity = CommandEntity(str(payload["entity"]))
        operation = str(payload.get("operation") or "")
        if action != CommandAction.QUERY and operation not in {
            "create_calendar_event",
            "create_todo",
            "create_todo_with_reminder",
            "update_item",
            "delete_item",
            "complete_item",
            "cancel_complete_item",
        }:
            raise ValueError(f"Unsupported operation {operation}.")

        command_payload: dict[str, Any] = {
            "operation": operation,
            "reference_query": payload.get("reference_query"),
            "source_text": transcript,
        }
        reminder = payload.get("reminder")
        if isinstance(reminder, dict):
            trigger_type = self._parse_reminder_trigger_type(reminder.get("trigger_type"))
            command_payload["reminder"] = {
                "trigger_type": trigger_type.value,
                "trigger_at": reminder.get("trigger_at"),
                "place_ref": reminder.get("place_ref"),
                "priority": self._parse_reminder_priority(reminder.get("priority")),
            }

        start_at = self._optional_datetime(payload.get("start_at"))
        end_at = self._optional_datetime(payload.get("end_at"))
        if operation == "create_calendar_event" and start_at is not None and end_at is None:
            end_at = start_at + timedelta(hours=1)

        return Command(
            id=str(uuid4()),
            identity=identity,
            action=action,
            entity=entity,
            title=self._optional_text(payload.get("title")),
            description=self._optional_text(payload.get("description")),
            start_at=start_at,
            end_at=end_at,
            due_at=self._optional_datetime(payload.get("due_at")),
            time_range_start=self._optional_datetime(payload.get("time_range_start")),
            time_range_end=self._optional_datetime(payload.get("time_range_end")),
            payload=command_payload,
        )

    def _system_prompt(self, now: datetime) -> str:
        """生成系统提示词。"""
        return f"""You convert Mandarin time-management requests into one JSON object.
Current UTC time: {now.isoformat()}.
Supported actions: create, query, update, delete, complete.
Supported entities: calendar_event, todo.
Supported operations: create_calendar_event, create_todo, create_todo_with_reminder,
update_item, delete_item, complete_item, cancel_complete_item.
Return these keys: action, entity, operation, title, description, reference_query,
start_at, end_at, due_at, time_range_start, time_range_end, reminder.
All datetime values must be ISO 8601 with a timezone. Use null when absent.
For read-only queries set operation to null and provide the requested time range.
For update/delete/complete, reference_query must contain the existing item's identifying text.
For a reminder request, use create_todo_with_reminder and reminder with trigger_type
(time, enter_place, leave_place, return_to_place), trigger_at, place_ref, and priority.
Never execute actions and never add unsupported operations. Return JSON only."""

    def _parse_reminder_trigger_type(self, value: Any) -> ReminderTriggerType:
        """校验 LLM 返回的触发类型，非法值兜底成 time。"""
        if value is None:
            return ReminderTriggerType.TIME
        try:
            return ReminderTriggerType(str(value))
        except ValueError:
            logger.warning("LLM returned invalid reminder trigger_type %r; default time", value)
            return ReminderTriggerType.TIME

    def _parse_reminder_priority(self, value: Any) -> str:
        """校验 LLM 返回的优先级，非法值兜底成 normal。"""
        candidate = str(value) if value is not None else ReminderPriority.NORMAL.value
        if candidate not in {priority.value for priority in ReminderPriority}:
            logger.warning("LLM returned invalid reminder priority %r; defaulting to normal", value)
            return ReminderPriority.NORMAL.value
        return candidate

    def _strip_code_fence(self, value: str) -> str:
        """去除代码块围栏。"""
        normalized = value.strip()
        if normalized.startswith("```"):
            normalized = normalized.removeprefix("```json").removeprefix("```")
            normalized = normalized.removesuffix("```").strip()
        return normalized

    def _optional_datetime(self, value: Any) -> datetime | None:
        """解析可选日期时间。"""
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _optional_text(self, value: Any) -> str | None:
        """解析可选文本。"""
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None


class MockCommandParser:
    """Parse a small set of common Mandarin MVP utterances into commands."""

    def parse(self, transcript: str, identity: Identity) -> Command:
        """解析输入并返回结构化结果。"""

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
        """判断是否像查询语句。"""
        return "什么安排" in transcript or transcript.startswith("查询")

    def _extract_query_range(self, transcript: str, now: datetime) -> tuple[datetime, datetime]:
        """提取查询时间范围。"""
        if "明天" in transcript:
            start = self._start_of_day(now + timedelta(days=1))
            return start, start + timedelta(days=1)
        if "本周" in transcript or "这周" in transcript:
            start = self._start_of_day(now)
            return start, start + timedelta(days=7)
        start = self._start_of_day(now)
        return start, start + timedelta(days=1)

    def _start_of_day(self, value: datetime) -> datetime:
        """取当天零点。"""
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    def _looks_like_delete(self, transcript: str) -> bool:
        """判断是否像删除语句。"""
        return transcript.startswith("取消") or transcript.startswith("删除")

    def _looks_like_complete(self, transcript: str) -> bool:
        """判断是否像完成语句。"""
        return "买好了" in transcript or "完成了" in transcript or transcript.endswith("完成")

    def _looks_like_calendar_event(self, transcript: str) -> bool:
        """判断是否像日程事件。"""
        return (
            "会议" in transcript
            or "日程" in transcript
            or "安排" in transcript
            or ("开" in transcript and "会" in transcript)
        )

    def _extract_delete_reference(self, transcript: str) -> str:
        """提取删除引用。"""
        reference = transcript.removeprefix("取消").removeprefix("删除").strip()
        reference = reference.replace("明天的", "").replace("明天", "").strip()
        return "会议" if "会议" in reference else reference

    def _extract_complete_reference(self, transcript: str) -> str:
        """提取完成引用。"""
        reference = transcript
        for marker in ["买好了", "完成了", "完成"]:
            reference = reference.replace(marker, "")
        return reference.removeprefix("把").strip()

    def _extract_title_after_reminder(self, transcript: str) -> str:
        """提取 reminder 后的标题。"""
        if "提醒我" in transcript:
            return transcript.split("提醒我", maxsplit=1)[1].strip() or transcript
        return transcript

    def _extract_place_trigger(self, transcript: str) -> ReminderTriggerType:
        """提取地点触发器。"""
        if "到家" in transcript or "进入" in transcript:
            return ReminderTriggerType.ENTER_PLACE
        if "离开" in transcript:
            return ReminderTriggerType.LEAVE_PLACE
        if "回到" in transcript:
            return ReminderTriggerType.RETURN_TO_PLACE
        return ReminderTriggerType.TIME

    def _extract_update_time(self, transcript: str, now: datetime) -> datetime | None:
        """提取更新时间。"""
        return self._extract_explicit_datetime(transcript, now)

    def _extract_explicit_datetime(self, transcript: str, now: datetime) -> datetime | None:
        """提取显式日期时间。"""
        match = re.search(
            r"(?:(今天|明天|后天|大后天))?"
            r"(?:(凌晨|早上|上午|中午|下午|晚上))?"
            r"(?:(\d{1,2}|[零一二两三四五六七八九十]{1,3}))点"
            r"(?:(\d{1,2})分?|(?P<half>半))?",
            transcript,
        )
        if match is None:
            return None

        day_text, period_text, hour_text, minute_text = (
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
        )
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
        """解析中文数字。"""
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
