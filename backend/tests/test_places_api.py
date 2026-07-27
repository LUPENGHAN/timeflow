"""Tests for place management endpoints."""

from fastapi.testclient import TestClient

from timeapp.api.dependencies import get_timeflow_app
from timeapp.application.service import TimeflowApplication
from timeapp.application.store import InMemoryStore
from timeapp.main import app


def test_place_update_and_delete_flow() -> None:
    """Places can be edited and deleted through HTTP."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/places",
            json={"label": "家", "place_type": "home", "radius_meters": 100},
        )
        assert created.status_code == 200
        place_id = created.json()["place"]["id"]

        updated = client.patch(
            f"/api/v1/places/{place_id}",
            json={"label": "新家", "radius_meters": 200, "description": "小区东门"},
        )
        assert updated.status_code == 200
        assert updated.json()["place"]["label"] == "新家"
        assert updated.json()["place"]["radius_meters"] == 200

        deleted = client.delete(f"/api/v1/places/{place_id}")
        assert deleted.status_code == 200
        assert deleted.json()["place"]["id"] == place_id

        places = client.get("/api/v1/places")
        assert places.status_code == 200
        assert places.json() == []

    app.dependency_overrides.clear()
