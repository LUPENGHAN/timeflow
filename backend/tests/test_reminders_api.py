"""Tests for reminder creation and action endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from timeapp.api.dependencies import get_timeflow_app
from timeapp.application.service import TimeflowApplication
from timeapp.application.store import InMemoryStore
from timeapp.main import app


def test_create_time_reminder_and_mark_delivered() -> None:
    """A reminder can be created for an item and then updated by client action."""

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

        reminder_response = client.post(
            "/api/v1/reminders",
            json={
                "item_id": item_id,
                "trigger_type": "time",
                "trigger_at": trigger_at,
                "priority": "normal",
            },
        )
        assert reminder_response.status_code == 200
        reminder = reminder_response.json()["reminder"]
        assert reminder["item_id"] == item_id
        assert reminder["trigger_type"] == "time"
        assert reminder["status"] == "pending"

        delivered = client.post(
            f"/api/v1/reminders/{reminder['id']}/actions",
            json={"action": "delivered"},
        )
        assert delivered.status_code == 200
        assert delivered.json()["reminder"]["status"] == "delivered"

    app.dependency_overrides.clear()
