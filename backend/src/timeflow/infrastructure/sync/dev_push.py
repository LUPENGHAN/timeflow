"""Development-only PowerSync upload endpoint.

This adapter intentionally omits authentication, idempotency, and conflict
resolution. Those concerns belong to the production sync boundary owned by the
account/sync workstream. Keeping this endpoint small makes it useful for
verifying PowerSync's local SQLite and upload callback without pretending to be
safe for a shared environment.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from timeflow.data.models import Schedule

DEV_USER_ID = "default_user"
Operation = Literal["create", "update", "delete"]

_MUTABLE_COLUMNS = frozenset(
    {
        "source_mode",
        "schedule_type",
        "status",
        "title",
        "notes",
        "start_time",
        "end_time",
        "timezone",
        "location_name",
        "location_address",
        "latitude",
        "longitude",
        "geofence_radius_meters",
        "geofence_armed",
        "time_remind_offset_minutes",
        "time_triggered_at",
        "geo_triggered_at",
        "system_schedule_ref_id",
        "system_alarm_ref_id",
        "created_at",
        "updated_at",
    }
)


class DevSyncOperation(BaseModel):
    """One PowerSync CRUD entry translated to the upload API contract."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1)
    entity: Literal["schedules"]
    entity_id: str = Field(min_length=1)
    operation: Operation
    payload: dict[str, Any] = Field(default_factory=dict)
    base_version: int | None = None


class DevSyncPushRequest(BaseModel):
    """Development upload request; production auth is deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    operations: list[DevSyncOperation] = Field(min_length=1, max_length=100)


class DevSyncOperationResult(BaseModel):
    """Per-operation result returned to the PowerSync connector."""

    operation_id: str
    status: Literal["applied", "not_found", "conflict", "rejected"]
    entity_id: str
    message: str | None = None


class DevSyncPushResponse(BaseModel):
    """Development upload response."""

    results: list[DevSyncOperationResult]


class DevPowerSyncPushService:
    """Apply a small, fixed-user batch for local PowerSync verification."""

    def __init__(self, session_factory: sessionmaker[Session], user_id: str = DEV_USER_ID) -> None:
        self._session_factory = session_factory
        self._user_id = user_id

    def push(self, request: DevSyncPushRequest) -> DevSyncPushResponse:
        results: list[DevSyncOperationResult] = []
        with self._session_factory() as session:
            for operation in request.operations:
                results.append(self._apply(session, operation))
            session.commit()
        return DevSyncPushResponse(results=results)

    def _apply(self, session: Session, operation: DevSyncOperation) -> DevSyncOperationResult:
        model = session.get(Schedule, operation.entity_id)
        if operation.operation == "create":
            if model is not None:
                return DevSyncOperationResult(
                    operation_id=operation.operation_id,
                    status="conflict",
                    entity_id=operation.entity_id,
                    message="schedule id already exists in development sync mode",
                )
            session.add(self._new_model(operation))
            return DevSyncOperationResult(
                operation_id=operation.operation_id,
                status="applied",
                entity_id=operation.entity_id,
            )

        if model is None or model.user_id != self._user_id:
            return DevSyncOperationResult(
                operation_id=operation.operation_id,
                status="not_found",
                entity_id=operation.entity_id,
                message="schedule not found",
            )

        if operation.operation == "delete":
            model.status = "deleted"
            model.updated_at = self._now()
        else:
            self._apply_patch(model, operation.payload)
        return DevSyncOperationResult(
            operation_id=operation.operation_id,
            status="applied",
            entity_id=operation.entity_id,
        )

    def _new_model(self, operation: DevSyncOperation) -> Schedule:
        payload = dict(operation.payload)
        payload.pop("id", None)
        payload.pop("user_id", None)
        payload.setdefault("source_mode", "manual")
        payload.setdefault("schedule_type", "time")
        payload.setdefault("status", "scheduled")
        payload.setdefault("title", "")
        payload.setdefault("geofence_radius_meters", 100)
        payload.setdefault("geofence_armed", 0)
        payload.setdefault("time_remind_offset_minutes", 0)
        payload.setdefault("created_at", self._now())
        payload.setdefault("updated_at", self._now())
        for key in _MUTABLE_COLUMNS:
            payload.setdefault(key, None)
        payload["geofence_armed"] = int(bool(payload["geofence_armed"]))
        payload["id"] = operation.entity_id
        payload["user_id"] = self._user_id
        return Schedule(**{key: payload[key] for key in _MUTABLE_COLUMNS | {"id", "user_id"}})

    @staticmethod
    def _apply_patch(model: Schedule, payload: Mapping[str, Any]) -> None:
        for key, value in payload.items():
            if key in _MUTABLE_COLUMNS:
                setattr(model, key, value)
        if "geofence_armed" in payload:
            model.geofence_armed = int(bool(payload["geofence_armed"]))
        model.updated_at = DevPowerSyncPushService._now()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


__all__ = [
    "DEV_USER_ID",
    "DevPowerSyncPushService",
    "DevSyncOperation",
    "DevSyncOperationResult",
    "DevSyncPushRequest",
    "DevSyncPushResponse",
]
