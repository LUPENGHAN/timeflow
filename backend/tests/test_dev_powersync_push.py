"""Tests for the development-only PowerSync upload adapter."""

from pathlib import Path

from timeflow.data.database import Base, build_engine, build_session_factory
from timeflow.infrastructure.sync.dev_push import (
    DevPowerSyncPushService,
    DevSyncOperation,
    DevSyncPushRequest,
)


def _service(tmp_path: Path) -> DevPowerSyncPushService:
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'powersync.db'}")
    Base.metadata.create_all(engine)
    return DevPowerSyncPushService(build_session_factory(engine))


def _create(operation_id: str = "op_create") -> DevSyncOperation:
    return DevSyncOperation(
        operation_id=operation_id,
        entity="schedules",
        entity_id="schedule_dev_1",
        operation="create",
        payload={
            "source_mode": "manual",
            "schedule_type": "time",
            "status": "scheduled",
            "title": "PowerSync 验证",
            "start_time": "2026-08-04T07:00:00+00:00",
            "timezone": "UTC",
            "geofence_radius_meters": 100,
            "geofence_armed": 0,
            "time_remind_offset_minutes": 15,
            "time_triggered_at": None,
            "geo_triggered_at": None,
            "created_at": "2026-08-04T06:00:00+00:00",
            "updated_at": "2026-08-04T06:00:00+00:00",
        },
    )


def test_dev_push_applies_create_patch_and_soft_delete(tmp_path: Path) -> None:
    service = _service(tmp_path)

    created = service.push(DevSyncPushRequest(operations=[_create()]))
    assert created.results[0].status == "applied"

    updated = service.push(
        DevSyncPushRequest(
            operations=[
                DevSyncOperation(
                    operation_id="op_update",
                    entity="schedules",
                    entity_id="schedule_dev_1",
                    operation="update",
                    payload={"title": "PowerSync 验证（已修改）"},
                )
            ]
        )
    )
    assert updated.results[0].status == "applied"

    deleted = service.push(
        DevSyncPushRequest(
            operations=[
                DevSyncOperation(
                    operation_id="op_delete",
                    entity="schedules",
                    entity_id="schedule_dev_1",
                    operation="delete",
                )
            ]
        )
    )
    assert deleted.results[0].status == "applied"


def test_dev_push_rejects_duplicate_create_without_claiming_idempotency(tmp_path: Path) -> None:
    service = _service(tmp_path)

    service.push(DevSyncPushRequest(operations=[_create()]))
    result = service.push(DevSyncPushRequest(operations=[_create("op_retry")]))

    assert result.results[0].status == "conflict"
