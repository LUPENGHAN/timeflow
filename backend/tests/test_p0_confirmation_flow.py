"""Tests for the MS1 voice-command confirmation flow."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from timeapp.api.dependencies import get_timeflow_app
from timeapp.application.service import TimeflowApplication
from timeapp.application.store import InMemoryStore
from timeapp.main import app


def test_voice_command_creates_and_confirms_todo_reminder() -> None:
    """Voice input must stop at confirmation before creating items/reminders."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        voice_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "到家后提醒我取快递"},
        )

        assert voice_response.status_code == 200
        voice_body = voice_response.json()
        write_request = voice_body["write_request"]
        assert write_request["status"] == "pending"
        assert write_request["candidate_payload"]["operation"] == "create_todo_with_reminder"

        items_before_confirmation = client.get("/api/v1/items")
        assert items_before_confirmation.status_code == 200
        assert items_before_confirmation.json() == []

        confirmation_response = client.post(
            f"/api/v1/write-requests/{write_request['id']}/confirm",
        )
        assert confirmation_response.status_code == 200
        confirmation_body = confirmation_response.json()
        assert confirmation_body["write_request"]["status"] == "applied"

        items_after_confirmation = client.get("/api/v1/items")
        assert items_after_confirmation.status_code == 200
        items = items_after_confirmation.json()
        assert len(items) == 1
        assert items[0]["type"] == "todo"
        assert items[0]["title"] == "取快递"
        assert items[0]["reminders"][0]["trigger_type"] == "enter_place"
    app.dependency_overrides.clear()


def test_voice_query_returns_matching_agenda_without_write_request() -> None:
    """Read-only voice queries should return agenda candidates without writes."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        starts_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        client.post(
            "/api/v1/items",
            json={
                "type": "calendar_event",
                "title": "项目会",
                "start_at": starts_at,
            },
        )
        item_id = client.post(
            "/api/v1/items",
            json={"type": "todo", "title": "买牛奶"},
        ).json()["item"]["id"]
        reminder_request = client.post(
            "/api/v1/reminders",
            json={
                "item_id": item_id,
                "trigger_type": "time",
                "trigger_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
                "priority": "normal",
            },
        )
        assert reminder_request.status_code == 200

        voice_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "我今天有什么安排？"},
        )

        assert voice_response.status_code == 200
        body = voice_response.json()
        assert body["write_request"] is None
        assert body["clarification"] is None
        assert [candidate["title"] for candidate in body["candidates"]] == [
            "项目会",
            "买牛奶",
        ]
        assert body["candidates"][1]["reminders"][0]["trigger_type"] == "time"

        pending_response = client.get("/api/v1/write-requests/pending")
        assert pending_response.status_code == 200
        assert pending_response.json() == []

    app.dependency_overrides.clear()


def test_voice_query_supports_tomorrow_and_week_ranges() -> None:
    """Voice agenda queries should understand tomorrow and this-week windows."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        tomorrow_at = (datetime.now(UTC) + timedelta(days=1)).replace(
            hour=9,
            minute=0,
            second=0,
            microsecond=0,
        )
        week_at = (datetime.now(UTC) + timedelta(days=4)).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )
        later_at = (datetime.now(UTC) + timedelta(days=9)).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )
        for title, start_at in [
            ("明天会议", tomorrow_at),
            ("本周体检", week_at),
            ("下周出差", later_at),
        ]:
            response = client.post(
                "/api/v1/items",
                json={
                    "type": "calendar_event",
                    "title": title,
                    "start_at": start_at.isoformat(),
                },
            )
            assert response.status_code == 200

        tomorrow_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "明天有什么安排？"},
        )
        assert tomorrow_response.status_code == 200
        assert [candidate["title"] for candidate in tomorrow_response.json()["candidates"]] == [
            "明天会议",
        ]

        week_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "本周有什么安排？"},
        )
        assert week_response.status_code == 200
        assert [candidate["title"] for candidate in week_response.json()["candidates"]] == [
            "明天会议",
            "本周体检",
        ]

    app.dependency_overrides.clear()


def test_voice_parser_reads_explicit_time_for_calendar_and_reminder() -> None:
    """Voice parsing should keep explicit Chinese time expressions."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        tomorrow_prefix = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        calendar_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "明天下午三点开项目会"},
        )
        assert calendar_response.status_code == 200
        calendar_body = calendar_response.json()
        assert calendar_body["write_request"]["candidate_payload"]["operation"] == "create_calendar_event"
        assert calendar_body["write_request"]["candidate_payload"]["item"]["start_at"].startswith(
            f"{tomorrow_prefix}T15:00:00"
        )

        reminder_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "明天上午九点提醒我交材料"},
        )
        assert reminder_response.status_code == 200
        reminder_body = reminder_response.json()
        assert reminder_body["write_request"]["candidate_payload"]["operation"] == "create_todo_with_reminder"
        assert reminder_body["write_request"]["candidate_payload"]["reminders"][0]["trigger_at"].startswith(
            f"{tomorrow_prefix}T09:00:00"
        )

    app.dependency_overrides.clear()


def test_voice_update_requires_candidate_selection_before_confirm() -> None:
    """Ambiguous voice updates should create a pending write request that needs selection."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/items",
            json={
                "type": "calendar_event",
                "title": "会议A",
                "start_at": (datetime.now(UTC) + timedelta(days=1, hours=1)).isoformat(),
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/items",
            json={
                "type": "calendar_event",
                "title": "会议B",
                "start_at": (datetime.now(UTC) + timedelta(days=1, hours=2)).isoformat(),
            },
        )
        assert second.status_code == 200

        voice_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "把明天的会议改到四点"},
        )

        assert voice_response.status_code == 200
        body = voice_response.json()
        assert body["clarification"] == "找到多个候选事项，请先选择要修改的对象。"
        assert body["write_request"]["status"] == "pending"
        write_request_id = body["write_request"]["id"]
        assert len(body["candidates"]) == 2

        blocked = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert blocked.status_code == 400
        assert blocked.json()["detail"]["code"] == "clarification_required"

        selected_candidate = body["candidates"][0]
        selected_operation = next(
            op
            for op in body["write_request"]["candidate_payload"]["operations"]
            if op["target_id"] == selected_candidate["id"]
        )
        narrowed_payload = {
            **body["write_request"]["candidate_payload"],
            "candidates": [selected_candidate],
            "operations": [selected_operation],
            "target_id": selected_candidate["id"],
        }
        update_response = client.patch(
            f"/api/v1/write-requests/{write_request_id}",
            json={"candidate_payload": narrowed_payload},
        )
        assert update_response.status_code == 200

        confirmed = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert confirmed.status_code == 200

        items = client.get("/api/v1/items").json()
        updated_item = next(item for item in items if item["id"] == selected_candidate["id"])
        assert updated_item["title"] == "会议"
        assert "T16:00:00" in updated_item["start_at"]

    app.dependency_overrides.clear()


def test_voice_delete_and_complete_create_confirmable_write_requests() -> None:
    """Voice delete and complete intents should still stop at confirmation."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        meeting = client.post(
            "/api/v1/items",
            json={"type": "calendar_event", "title": "会议"},
        )
        assert meeting.status_code == 200
        todo = client.post(
            "/api/v1/items",
            json={"type": "todo", "title": "买牛奶"},
        )
        assert todo.status_code == 200

        delete_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "取消明天的会议"},
        )
        assert delete_response.status_code == 200
        delete_body = delete_response.json()
        assert delete_body["write_request"]["candidate_payload"]["operation"] == "delete_item"
        assert client.get("/api/v1/items").json()[0]["status"] == "active"

        delete_confirmed = client.post(
            f"/api/v1/write-requests/{delete_body['write_request']['id']}/confirm",
        )
        assert delete_confirmed.status_code == 200
        visible_after_delete = client.get("/api/v1/items").json()
        assert [item["title"] for item in visible_after_delete] == ["买牛奶"]

        complete_response = client.post(
            "/api/v1/voice/commands",
            json={"transcript": "牛奶买好了"},
        )
        assert complete_response.status_code == 200
        complete_body = complete_response.json()
        assert complete_body["write_request"]["candidate_payload"]["operation"] == "complete_item"

        complete_confirmed = client.post(
            f"/api/v1/write-requests/{complete_body['write_request']['id']}/confirm",
        )
        assert complete_confirmed.status_code == 200
        items = client.get("/api/v1/items").json()
        assert items[0]["title"] == "买牛奶"
        assert items[0]["status"] == "completed"

    app.dependency_overrides.clear()


def test_events_endpoint_returns_cursor_sync_events() -> None:
    """HTTP sync should expose domain events with a cursor."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        response = client.post("/api/v1/voice/commands", json={"transcript": "记得买牛奶"})
        assert response.status_code == 200

        events_response = client.get("/api/v1/events")
        assert events_response.status_code == 200
        events_body = events_response.json()
        assert events_body["next_cursor"] == 2
        assert [event["event_type"] for event in events_body["events"]] == [
            "command.status.changed",
            "write_request.created",
        ]
    app.dependency_overrides.clear()


def test_write_request_detail_and_expiration_gate() -> None:
    """Expired pending writes can be inspected but cannot be confirmed."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        response = client.post("/api/v1/voice/commands", json={"transcript": "记得买牛奶"})
        assert response.status_code == 200
        write_request_id = response.json()["write_request"]["id"]

        detail_response = client.get(f"/api/v1/write-requests/{write_request_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["status"] == "pending"

        write_request = test_app.store.write_requests[write_request_id]
        write_request.expires_at = datetime.now(UTC) - timedelta(minutes=1)

        confirm_response = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert confirm_response.status_code == 409
        assert confirm_response.json()["detail"]["code"] == "write_request_expired"

        pending_response = client.get("/api/v1/write-requests/pending")
        assert pending_response.status_code == 200
        assert pending_response.json() == []

    app.dependency_overrides.clear()


def test_write_request_can_restore_completed_item() -> None:
    """Cancel-complete operations go through the confirmation gate."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        created = client.post("/api/v1/items", json={"type": "todo", "title": "买咖啡"})
        assert created.status_code == 200
        item_id = created.json()["item"]["id"]
        completed = client.post(f"/api/v1/items/{item_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["item"]["status"] == "completed"

        request = client.post(
            "/api/v1/write-requests",
            json={
                "source_command_id": f"manual-{item_id}-cancel-complete",
                "candidate_payload": {
                    "operation": "cancel_complete_item",
                    "target_id": item_id,
                    "item": {"title": "买咖啡", "type": "todo"},
                },
            },
        )
        assert request.status_code == 200
        write_request_id = request.json()["write_request"]["id"]

        confirmed = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert confirmed.status_code == 200

        items = client.get("/api/v1/items").json()
        assert items[0]["status"] == "active"

    app.dependency_overrides.clear()


def test_write_request_can_update_item_fields_and_clear_nullable_values() -> None:
    """Manual edits go through confirmation and can clear nullable item fields."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/items",
            json={
                "type": "todo",
                "title": "买牛奶",
                "description": "低脂",
                "place_text": "超市",
            },
        )
        assert created.status_code == 200
        item_id = created.json()["item"]["id"]

        request = client.post(
            "/api/v1/write-requests",
            json={
                "source_command_id": f"manual-{item_id}-update",
                "candidate_payload": {
                    "operation": "update_item",
                    "target_id": item_id,
                    "item": {"title": "买燕麦奶", "type": "todo"},
                    "operations": [
                        {
                            "op": "update_item",
                            "target_id": item_id,
                            "changes": {
                                "title": "买燕麦奶",
                                "description": None,
                                "place_text": None,
                            },
                        }
                    ],
                },
            },
        )
        assert request.status_code == 200
        write_request_id = request.json()["write_request"]["id"]

        confirmed = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert confirmed.status_code == 200

        items = client.get("/api/v1/items").json()
        assert items[0]["title"] == "买燕麦奶"
        assert items[0]["description"] is None
        assert items[0]["place_text"] is None

    app.dependency_overrides.clear()


def test_write_request_can_create_time_reminder_for_existing_item() -> None:
    """Reminder creation for an existing item also stops at confirmation."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/items",
            json={"type": "todo", "title": "交材料"},
        )
        assert created.status_code == 200
        item_id = created.json()["item"]["id"]
        trigger_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

        request = client.post(
            "/api/v1/write-requests",
            json={
                "source_command_id": f"manual-{item_id}-reminder",
                "candidate_payload": {
                    "operation": "create_reminder",
                    "target_id": item_id,
                    "item": {"title": "交材料", "type": "todo"},
                    "reminders": [
                        {
                            "trigger_type": "time",
                            "trigger_at": trigger_at,
                            "priority": "normal",
                        }
                    ],
                },
            },
        )
        assert request.status_code == 200
        write_request_id = request.json()["write_request"]["id"]

        before_confirmation = client.get("/api/v1/items").json()
        assert before_confirmation[0]["reminders"] == []

        confirmed = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert confirmed.status_code == 200

        items = client.get("/api/v1/items").json()
        assert items[0]["reminders"][0]["trigger_type"] == "time"
        assert items[0]["reminders"][0]["status"] == "pending"

        events = client.get("/api/v1/events").json()["events"]
        event_types = [event["event_type"] for event in events]
        assert event_types == [
            "item.created",
            "write_request.created",
            "write_request.updated",
            "write_request.applied",
        ]

    app.dependency_overrides.clear()


def test_write_request_can_create_place_reminder_for_existing_item() -> None:
    """Place reminder creation reads its trigger location off the target item."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/items",
            json={"type": "todo", "title": "取快递"},
        )
        assert created.status_code == 200
        item_id = created.json()["item"]["id"]

        placed = client.patch(
            f"/api/v1/items/{item_id}",
            json={"place_text": "家", "place_type": "home"},
        )
        assert placed.status_code == 200

        request = client.post(
            "/api/v1/write-requests",
            json={
                "source_command_id": f"manual-{item_id}-place-reminder",
                "candidate_payload": {
                    "operation": "create_reminder",
                    "target_id": item_id,
                    "item": {"title": "取快递", "type": "todo"},
                    "reminders": [
                        {
                            "trigger_type": "enter_place",
                            "priority": "normal",
                        }
                    ],
                },
            },
        )
        assert request.status_code == 200
        write_request_id = request.json()["write_request"]["id"]

        confirmed = client.post(f"/api/v1/write-requests/{write_request_id}/confirm")
        assert confirmed.status_code == 200

        items = client.get("/api/v1/items").json()
        reminder = items[0]["reminders"][0]
        assert reminder["trigger_type"] == "enter_place"
        assert reminder["status"] == "armed"

    app.dependency_overrides.clear()
