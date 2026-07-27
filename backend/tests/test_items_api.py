"""Tests for direct item management endpoints."""

from fastapi.testclient import TestClient

from timeapp.api.dependencies import get_timeflow_app
from timeapp.application.service import TimeflowApplication
from timeapp.application.store import InMemoryStore
from timeapp.main import app


def test_item_update_complete_cancel_and_delete_flow() -> None:
    """Items can be edited, completed, reactivated and deleted through HTTP."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/items",
            json={"type": "todo", "title": "买牛奶"},
        )
        assert created.status_code == 200
        item_id = created.json()["item"]["id"]

        updated = client.patch(
            f"/api/v1/items/{item_id}",
            json={"title": "买低脂牛奶", "place_text": "超市"},
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["title"] == "买低脂牛奶"
        assert updated.json()["item"]["place_text"] == "超市"

        completed = client.post(f"/api/v1/items/{item_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["item"]["status"] == "completed"

        reactivated = client.post(f"/api/v1/items/{item_id}/cancel-complete")
        assert reactivated.status_code == 200
        assert reactivated.json()["item"]["status"] == "active"

        deleted = client.delete(f"/api/v1/items/{item_id}")
        assert deleted.status_code == 200
        assert deleted.json()["item"]["status"] == "deleted"

        visible_items = client.get("/api/v1/items")
        assert visible_items.status_code == 200
        assert visible_items.json() == []

    app.dependency_overrides.clear()
