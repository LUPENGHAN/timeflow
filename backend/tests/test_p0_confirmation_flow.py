"""Tests for the MS1 voice-command confirmation flow."""

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
