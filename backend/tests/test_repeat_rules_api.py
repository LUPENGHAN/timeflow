"""Tests for repeat rule endpoints."""

from fastapi.testclient import TestClient

from timeapp.api.dependencies import get_timeflow_app
from timeapp.application.service import TimeflowApplication
from timeapp.application.store import InMemoryStore
from timeapp.main import app


def test_create_repeat_rule_normalizes_standard_patterns() -> None:
    """Daily and workday presets should store canonical weekday lists."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        daily = client.post(
            "/api/v1/repeat-rules",
            json={
                "pattern": "daily",
                "time_of_day": "08:30",
                "weekdays": [1, 2, 3],
            },
        )
        assert daily.status_code == 200
        assert daily.json()["repeat_rule"]["weekdays"] == []

        weekdays = client.post(
            "/api/v1/repeat-rules",
            json={
                "pattern": "weekdays",
                "time_of_day": "09:00",
                "weekdays": [6, 7],
            },
        )
        assert weekdays.status_code == 200
        assert weekdays.json()["repeat_rule"]["weekdays"] == [1, 2, 3, 4, 5]

    app.dependency_overrides.clear()


def test_create_custom_weekday_repeat_rule_sorts_and_deduplicates_weekdays() -> None:
    """Custom weekday rules should keep only one sorted weekday per selected day."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/repeat-rules",
            json={
                "pattern": "custom_weekdays",
                "time_of_day": "20:15",
                "weekdays": [5, 1, 5],
                "series_status": "paused",
            },
        )

        assert response.status_code == 200
        repeat_rule = response.json()["repeat_rule"]
        assert repeat_rule["pattern"] == "custom_weekdays"
        assert repeat_rule["weekdays"] == [1, 5]
        assert repeat_rule["time_of_day"] == "20:15"
        assert repeat_rule["series_status"] == "paused"

    app.dependency_overrides.clear()


def test_create_custom_weekday_repeat_rule_requires_weekdays() -> None:
    """The business rule rejects empty custom weekday selections."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/repeat-rules",
            json={"pattern": "custom_weekdays", "time_of_day": "08:00"},
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_required_field"

    app.dependency_overrides.clear()


def test_create_repeat_rule_schema_rejects_invalid_values() -> None:
    """Swagger-backed request validation should reject values outside the P0 set."""

    test_app = TimeflowApplication(InMemoryStore())
    app.dependency_overrides[get_timeflow_app] = lambda: test_app

    with TestClient(app) as client:
        invalid_pattern = client.post(
            "/api/v1/repeat-rules",
            json={"pattern": "workdays", "time_of_day": "09:00"},
        )
        assert invalid_pattern.status_code == 422

        invalid_time = client.post(
            "/api/v1/repeat-rules",
            json={"pattern": "daily", "time_of_day": "25:00"},
        )
        assert invalid_time.status_code == 422

        invalid_weekday = client.post(
            "/api/v1/repeat-rules",
            json={"pattern": "custom_weekdays", "time_of_day": "09:00", "weekdays": [8]},
        )
        assert invalid_weekday.status_code == 422

        invalid_status = client.post(
            "/api/v1/repeat-rules",
            json={"pattern": "daily", "time_of_day": "09:00", "series_status": "enabled"},
        )
        assert invalid_status.status_code == 422

    app.dependency_overrides.clear()
