"""The tools the realtime model may call, backed by ScheduleAgentService."""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from timeflow.business.calendar import (
    DeleteRecurringScheduleCommand,
    RecurringDeleteScope,
    ReminderStrength,
    ReminderType,
    ScheduleAgentService,
    ScheduleBusinessError,
    ScheduleKind,
    ScheduleMutationResult,
    ScheduleType,
)
from timeflow.intelligence.location import (
    LOCATION_SEARCH,
    PROVIDER_UNAVAILABLE_RESULT,
    ClientLocation,
    LocationCandidate,
    LocationConfigurationError,
    LocationConnectionError,
    LocationError,
    LocationInputError,
    LocationProtocolError,
    LocationSearchContext,
    LocationSearchService,
    convert_coordinate,
    location_search_definition,
)
from timeflow.intelligence.location.tools import _candidate_json, _query
from timeflow.intelligence.realtime.tool_mapping import (
    ToolInputError,
    map_create_schedule_command,
    map_delete_schedule_command,
    map_find_schedules_query,
    map_update_schedule_command,
    normalize_datetime_args,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Shanghai"

# Tool names from the conversation contract; names reach the client, so keep them.
SCHEDULE_CREATE = "schedule_create"
SCHEDULE_QUERY = "schedule_query"
SCHEDULE_UPDATE = "schedule_update"
SCHEDULE_DELETE = "schedule_delete"
REQUEST_USER_INPUT = "request_user_input"
END_CONVERSATION = "end_conversation"
# Re-exported for callers that only import this module: LOCATION_SEARCH == "location_search".

# Four question kinds registered; clients branch on this enum.
QUESTION_KINDS = ("missing_field", "ambiguous_target", "recurrence_scope", "confirmation")


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What a tool answered the model with, and what the client should be told."""

    output: str
    outcome: dict[str, Any] | None = None
    question: dict[str, Any] | None = None
    ends_conversation: bool = False


_DATETIME_SCHEMA = {"type": ["string", "null"], "format": "date-time"}
_NULLABLE_STRING_SCHEMA = {"type": ["string", "null"]}
_REMINDER_TYPE_SCHEMA = {
    "type": ["string", "null"],
    "enum": [
        ReminderType.AT_TIME.value,
        ReminderType.BEFORE_START.value,
        ReminderType.ARRIVE_LOCATION.value,
        ReminderType.RETURN_TO_RECORDED_LOCATION.value,
        None,
    ],
}
_REMINDER_STRENGTH_SCHEMA = {
    "type": ["string", "null"],
    "enum": [
        ReminderStrength.LOW.value,
        ReminderStrength.MEDIUM.value,
        ReminderStrength.HIGH.value,
        None,
    ],
}
_EDITABLE_PROPERTIES: dict[str, Any] = {
    "title": {"type": "string", "minLength": 1},
    "is_all_day": {"type": "boolean"},
    "start_time": _DATETIME_SCHEMA,
    "end_time": _DATETIME_SCHEMA,
    "timezone": {"type": "string", "minLength": 1},
    "recurrence_rule": _NULLABLE_STRING_SCHEMA,
    "location_name": _NULLABLE_STRING_SCHEMA,
    "location_provider_id": {
        "type": ["string", "null"],
        "description": (
            "location_search 某条候选的 provider_id，只能用上一次 location_search 结果里"
            "原样出现的值；不接受经纬度，坐标由服务端从该候选里取，不采信模型自己填的数字。"
        ),
    },
    "reminder_type": _REMINDER_TYPE_SCHEMA,
    "reminder_trigger_at": _DATETIME_SCHEMA,
    "reminder_offset_minutes": {"type": ["integer", "null"], "minimum": 0},
    "reminder_strength": _REMINDER_STRENGTH_SCHEMA,
}

TOOL_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": SCHEDULE_CREATE,
            "description": "创建时间或地点日程，所有必要信息确认后调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_type": {
                        "type": "string",
                        "enum": [ScheduleType.TIME.value, ScheduleType.LOCATION.value],
                    },
                    "schedule_kind": {
                        "type": "string",
                        "enum": [ScheduleKind.ONCE.value, ScheduleKind.RECURRING.value],
                    },
                    **_EDITABLE_PROPERTIES,
                },
                "required": ["schedule_type", "schedule_kind", "title"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SCHEDULE_QUERY,
            "description": "查询日程，用于列表、匹配、消歧、更新或删除前查找。",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": _NULLABLE_STRING_SCHEMA,
                    "title": _NULLABLE_STRING_SCHEMA,
                    "starts_at_or_after": _DATETIME_SCHEMA,
                    "starts_before": _DATETIME_SCHEMA,
                    "location_name": _NULLABLE_STRING_SCHEMA,
                    "include_deleted": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SCHEDULE_UPDATE,
            "description": "修改已确认的一条日程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string", "minLength": 1},
                    "expected_revision": {"type": "integer", "minimum": 0},
                    "changes": {
                        "type": "object",
                        "properties": _EDITABLE_PROPERTIES,
                        "minProperties": 1,
                        "additionalProperties": False,
                    },
                },
                "required": ["schedule_id", "expected_revision", "changes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SCHEDULE_DELETE,
            "description": "删除已确认的一条日程；周期日程需要指定 scope。",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "string", "minLength": 1},
                    "expected_revision": {"type": "integer", "minimum": 0},
                    "schedule_kind": {
                        "type": "string",
                        "enum": [ScheduleKind.ONCE.value, ScheduleKind.RECURRING.value],
                    },
                    "scope": {
                        "type": ["string", "null"],
                        "enum": [
                            RecurringDeleteScope.THIS_OCCURRENCE.value,
                            RecurringDeleteScope.THIS_AND_FUTURE.value,
                            RecurringDeleteScope.ENTIRE_SERIES.value,
                            None,
                        ],
                    },
                },
                "required": ["schedule_id", "expected_revision", "schedule_kind"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": REQUEST_USER_INPUT,
            "description": (
                "信息不足时向用户提问，而不是自己猜。"
                "缺少日期、时间、地点等必要信息，或者用户的说法匹配到多条日程时使用。"
                "调用之后要把 speech_text 原话说出来，让用户听到问题。一次只问一件事。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question_kind": {
                        "type": "string",
                        "enum": list(QUESTION_KINDS),
                        "description": (
                            "missing_field 缺必要信息；ambiguous_target 匹配到多条日程；"
                            "recurrence_scope 周期日程范围不明；confirmation 需要用户确认"
                        ),
                    },
                    "speech_text": {
                        "type": "string",
                        "description": "要问用户的话，一句口语，例如「这个会是哪天的？」",
                    },
                    "required_response": {
                        "type": "string",
                        "description": "希望用户补充的字段名，例如 start_time、location",
                    },
                    "candidates": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "匹配到多条时的候选日程，供客户端展示",
                    },
                },
                "required": ["question_kind", "speech_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": END_CONVERSATION,
            "description": (
                "用户明确表示想结束这次语音对话、退出免提模式、不想再继续时调用，"
                "例如说「结束对话」「先这样」「不用了」「退出语音模式」「停止监听」等。"
                "想说句告别的话可以说，说完再调用；调用之后客户端会自己挂断，不用再多说。"
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": location_search_definition().name,
            "description": location_search_definition().description,
            "parameters": location_search_definition().parameters,
        },
    },
)


class ToolBox:
    """Run tools the model is allowed to call, and refuse the rest."""

    def __init__(
        self,
        account_id: str,
        service: ScheduleAgentService,
        timezone: str = DEFAULT_TIMEZONE,
        now: Callable[[], datetime] | None = None,
        *,
        location_service: LocationSearchService | None = None,
        client_location: ClientLocation | None = None,
    ) -> None:
        """Store the account, the service, the client's zone, and the clock seam.

        client_location is whatever position the client reported at handshake -- see
        RealtimeAgent._session_for -- fixed for the life of the held session same as
        timezone. location_service being None means location_search degrades to
        provider_unavailable rather than being withheld from the schema: the model can
        always call it, it just may not always do anything.

        Preparing a LocationSearchContext from client_location is deferred to the first
        location_search call rather than done here, and retried on every call until it
        succeeds once: a transient failure (the provider being briefly unreachable) must
        not disable location_search for the rest of a session that can hold for minutes.
        """
        self._account_id = account_id
        self._service = service
        self._timezone = ZoneInfo(timezone)
        self._now = now or (lambda: datetime.now(self._timezone))
        self._location_service = location_service
        self._client_location = client_location
        self._location_context: LocationSearchContext | None = None
        # 只信这次会话里最近一次 location_search 真正返回过的候选：schedule_create/
        # update 只能引用 provider_id，不接受模型自己填的经纬度（issue #235 的可信坐标
        # 约束）。每次新的 location_search 整体替换，不跨多轮搜索累积。
        self._last_candidates: dict[str, LocationCandidate] = {}

    # The service is synchronous and reaches Postgres over a socket, so every call goes
    # to a worker thread: awaiting it inline would stall the loop streaming this turn's
    # audio. Each call opens its own session, so no session crosses a thread.

    def tools(self) -> list[dict[str, Any]]:
        """Return the tool schemas to register on the session."""
        return [dict(tool) for tool in TOOL_SCHEMAS]

    async def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Run a tool and report what each side of the conversation should get."""
        if name == REQUEST_USER_INPUT:
            return self._ask(arguments)
        if name == END_CONVERSATION:
            return ToolResult(
                output=json.dumps({"status": "ok"}, ensure_ascii=False), ends_conversation=True
            )
        if name == LOCATION_SEARCH:
            return await self._location_search(arguments)

        # Normalize datetime fields before mapping
        arguments = normalize_datetime_args(arguments, self._timezone)

        try:
            if name == SCHEDULE_CREATE:
                return await self._create(arguments)
            if name == SCHEDULE_QUERY:
                return await self._find(arguments)
            if name == SCHEDULE_UPDATE:
                return await self._update(arguments)
            if name == SCHEDULE_DELETE:
                return await self._delete(arguments)
        except ToolInputError as exc:
            return _refusal(str(exc))
        except ScheduleBusinessError as exc:
            return _business_error(exc)

        logger.warning("realtime model asked for a tool that is not offered", extra={"tool": name})
        return _refusal(f"工具 {name} 不可用。")

    async def _location_search(self, arguments: dict[str, Any]) -> ToolResult:
        """Search real places near the client, or report the search as unavailable.

        Unavailable covers "no location shared at handshake", "not configured", and a
        provider failure while preparing the search context -- the model gets the same
        stable status either way and never sees why. A prepare() failure is retried on
        the next call rather than remembered, so a provider outage this session opened
        during does not disable location_search for the rest of the call once the
        provider recovers.
        """
        if self._location_service is None or self._client_location is None:
            return ToolResult(output=PROVIDER_UNAVAILABLE_RESULT)
        if self._location_context is None:
            try:
                self._location_context = await self._location_service.prepare(self._client_location)
            except LocationError:
                return ToolResult(output=PROVIDER_UNAVAILABLE_RESULT)
        try:
            query = _query(arguments)
            candidates = await self._location_service.search(self._location_context, query)
        except LocationInputError:
            self._last_candidates = {}
            return ToolResult(
                output=json.dumps({"status": "invalid_input", "candidates": []}, ensure_ascii=False)
            )
        except (LocationConfigurationError, LocationConnectionError, LocationProtocolError):
            return ToolResult(output=PROVIDER_UNAVAILABLE_RESULT)
        # 整体替换，不是累加：上一轮搜索的候选一旦被新搜索覆盖就不再可引用，逼着模型
        # 用的 provider_id 始终对应最近一次搜索，不会拿到几轮之前已经过期的候选。
        self._last_candidates = {candidate.provider_id: candidate for candidate in candidates}
        return ToolResult(
            output=json.dumps(
                {"status": "ok", "candidates": [_candidate_json(c) for c in candidates]},
                ensure_ascii=False,
            )
        )

    async def _create(self, arguments: dict[str, Any]) -> ToolResult:
        self._resolve_location_provider_id(arguments)
        command = map_create_schedule_command(arguments, self._timezone)
        result = await asyncio.to_thread(
            partial(self._service.create_schedule, account_id=self._account_id, command=command)
        )
        return _mutation_result(result, "create_schedule", self._timezone)

    async def _find(self, arguments: dict[str, Any]) -> ToolResult:
        query = map_find_schedules_query(arguments)
        result = await asyncio.to_thread(
            partial(self._service.find_schedules, account_id=self._account_id, query=query)
        )
        schedules_with_local_time = [_for_model(s, self._timezone) for s in result.schedules]
        return ToolResult(
            output=json.dumps(
                {"count": len(result.schedules), "schedules": schedules_with_local_time},
                ensure_ascii=False,
            ),
            outcome={
                "operation": "list_schedules",
                "status": "applied",
                "schedules": [_snapshot_for_client(s) for s in result.schedules],
            },
        )

    async def _update(self, arguments: dict[str, Any]) -> ToolResult:
        changes = arguments.get("changes")
        if isinstance(changes, dict):
            self._resolve_location_provider_id(changes)
        command = map_update_schedule_command(arguments)
        result = await asyncio.to_thread(
            partial(self._service.update_schedule, account_id=self._account_id, command=command)
        )
        return _mutation_result(result, "update_schedule", self._timezone)

    def _resolve_location_provider_id(self, fields: dict[str, Any]) -> None:
        """Replace a trusted location_provider_id with server-known WGS84 coordinates.

        The model never supplies latitude/longitude directly -- dropped from the tool
        schema, and rejected here too if present anyway, since ScheduleUpdatePatch
        (the business-layer allowlist _reject_unknown checks against) still carries
        those keys and would otherwise wave a stray raw pair straight through. The
        model can only reference a provider_id from this session's most recent
        location_search results. Not found (stale, wrong turn, or invented) is a
        ToolInputError, not a silent no-op -- the model must search again rather than
        the schedule silently keeping its old coordinates.
        """
        if "latitude" in fields or "longitude" in fields:
            raise ToolInputError(
                "latitude/longitude 不是有效参数，改用 location_provider_id 引用"
                "location_search 的候选。"
            )
        if "location_provider_id" not in fields:
            return
        provider_id = fields.pop("location_provider_id")
        if provider_id is None:
            fields["latitude"] = None
            fields["longitude"] = None
            return
        candidate = self._last_candidates.get(provider_id)
        if candidate is None:
            raise ToolInputError(
                "location_provider_id 不是最近一次 location_search 返回的候选，"
                "请重新调用 location_search 再引用。"
            )
        coordinate = convert_coordinate(candidate.coordinate, "wgs84")
        fields["latitude"] = coordinate.latitude
        fields["longitude"] = coordinate.longitude

    async def _delete(self, arguments: dict[str, Any]) -> ToolResult:
        command = map_delete_schedule_command(arguments)
        if isinstance(command, DeleteRecurringScheduleCommand):
            result = await asyncio.to_thread(
                partial(
                    self._service.delete_recurring_schedule,
                    account_id=self._account_id,
                    command=command,
                )
            )
        else:
            result = await asyncio.to_thread(
                partial(
                    self._service.delete_once_schedule,
                    account_id=self._account_id,
                    command=command,
                )
            )
        return _mutation_result(result, "delete_schedule", self._timezone)

    def _ask(self, arguments: dict[str, Any]) -> ToolResult:
        """Turn a request to ask the user into a question, or refuse an unusable one."""
        kind = arguments.get("question_kind")
        speech_text = arguments.get("speech_text")
        if kind not in QUESTION_KINDS:
            logger.warning("realtime model asked with an unknown kind", extra={"kind": kind})
            return _refusal(f"question_kind 必须是 {'、'.join(QUESTION_KINDS)} 之一。")
        if not isinstance(speech_text, str) or not speech_text.strip():
            return _refusal("speech_text 不能为空，要写出问用户的原话。")

        candidates = _candidates(arguments.get("candidates"))
        if kind == "ambiguous_target" and not candidates:
            return _refusal("ambiguous_target 必须提供非空 candidates。先用 schedule_query 查询。")

        required = arguments.get("required_response")
        return ToolResult(
            output=json.dumps({"asked": True}, ensure_ascii=False),
            question={
                "question_kind": kind,
                "speech_text": speech_text.strip(),
                "required_response": required if isinstance(required, str) and required else None,
                "candidates": candidates,
            },
        )


def _refusal(reason: str) -> ToolResult:
    """Tell the model why it got nothing, and tell the client nothing at all."""
    return ToolResult(
        output=json.dumps({"status": "failed", "error": {"message": reason}}, ensure_ascii=False)
    )


def _business_error(error: ScheduleBusinessError) -> ToolResult:
    """Tell the model a write was refused; nothing was committed, so the client hears none.

    voice.command.result reports a committed transaction (protocol §5.5). A refusal has
    none to report, so only the model is told, and it says so out loud.
    """
    return ToolResult(
        output=json.dumps(
            {
                "status": "failed",
                "error": {
                    "code": error.code.value,
                    "field": error.field,
                    "message": error.message,
                    "schedule_id": error.schedule_id,
                },
            },
            ensure_ascii=False,
        )
    )


def _mutation_result(result: ScheduleMutationResult, operation: str, tz: ZoneInfo) -> ToolResult:
    """Convert a mutation result into model output and client outcome."""
    snapshot = result.schedules[0] if result.schedules else None
    return ToolResult(
        output=json.dumps(
            {"status": "applied", "schedule": _for_model_dict(snapshot, tz)}, ensure_ascii=False
        ),
        outcome={
            "operation": operation,
            "status": "applied",
            "schedule": _snapshot_for_client(snapshot) if snapshot else None,
        },
    )


def _for_model(schedule: Any, tz: ZoneInfo) -> dict[str, Any]:
    """Add a spoken-language local time beside the stored instant."""
    spoken = asdict(schedule)
    spoken["starts_at_local"] = _local_text(spoken.get("start_time"), tz)
    result = _json_value(spoken)
    assert isinstance(result, dict)
    return result


def _for_model_dict(schedule: Any, tz: ZoneInfo) -> dict[str, Any] | None:
    if schedule is None:
        return None
    return _for_model(schedule, tz)


def _snapshot_for_client(snapshot: Any) -> dict[str, Any]:
    """Convert ScheduleSnapshot to client dict, filtering out audit fields."""
    d = asdict(snapshot)
    return {
        k: _json_value(v)
        for k, v in d.items()
        if k not in {"account_id", "created_at", "updated_at", "deleted_at"}
    }


def _local_text(instant: datetime | None, tz: ZoneInfo) -> str:
    """Render a stored instant as local wall-clock text, empty for a schedule without one."""
    if instant is None:
        return ""
    return instant.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _candidates(value: Any) -> tuple[dict[str, Any], ...]:
    """Keep the choices that are actually objects, dropping anything else."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
