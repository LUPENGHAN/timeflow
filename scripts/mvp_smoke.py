"""Executable P0 MVP smoke validation for Timeflow.

Run from the repository root:
    backend/.venv/bin/python scripts/mvp_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from timeapp.api.dependencies import get_timeflow_app  # noqa: E402
from timeapp.main import app  # noqa: E402


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


def post_json(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    expect(response.status_code == 200, f"POST {path} returned 200")
    return response.json()


def main() -> None:
    get_timeflow_app.cache_clear()

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        expect(
            health.status_code == 200 and health.json()["status"] == "ok",
            "health check",
        )

        agenda = client.get("/api/v1/agenda")
        expect(
            agenda.status_code == 200 and agenda.json()["items"] == [], "empty agenda"
        )

        todo = post_json(
            client,
            "/api/v1/items",
            {"type": "todo", "title": "买牛奶", "description": "manual todo"},
        )["item"]
        calendar = post_json(
            client,
            "/api/v1/items",
            {
                "type": "calendar_event",
                "title": "明天会议",
                "description": "manual calendar",
            },
        )["item"]
        expect(
            todo["version"] == 1 and calendar["version"] == 1,
            "manual create has LWW fields",
        )

        rejected_voice = post_json(
            client,
            "/api/v1/voice/commands",
            {"transcript": "记得买咖啡"},
        )
        item_count_before_reject = len(client.get("/api/v1/items").json())
        reject = client.post(
            f"/api/v1/write-requests/{rejected_voice['write_request']['id']}/reject"
        )
        expect(reject.status_code == 200, "write request cancel returned 200")
        expect(
            len(client.get("/api/v1/items").json()) == item_count_before_reject,
            "cancelled write request did not write item",
        )

        calendar_voice = post_json(
            client,
            "/api/v1/voice/commands",
            {"transcript": "明天安排会议"},
        )
        confirm_calendar = client.post(
            f"/api/v1/write-requests/{calendar_voice['write_request']['id']}/confirm"
        )
        expect(confirm_calendar.status_code == 200, "voice calendar confirm")

        reminder_voice = post_json(
            client,
            "/api/v1/voice/commands",
            {"transcript": "到家后提醒我取快递"},
        )
        expect(
            reminder_voice["write_request"]["candidate_payload"]["operation"]
            == "create_todo_with_reminder",
            "voice reminder parsed to write request",
        )
        confirm_reminder = client.post(
            f"/api/v1/write-requests/{reminder_voice['write_request']['id']}/confirm"
        )
        expect(confirm_reminder.status_code == 200, "voice reminder confirm")
        reminders = client.get("/api/v1/reminders").json()
        expect(
            any(reminder["trigger_type"] == "enter_place" for reminder in reminders),
            "place reminder created",
        )

        failed = post_json(
            client,
            f"/api/v1/reminders/{reminders[0]['id']}/actions",
            {"action": "failed", "failed_reason": "local notification failed"},
        )
        expect(
            failed["reminder"]["fallback_status"] == "requested",
            "local failed generated fallback requested",
        )

        update_voice = post_json(
            client,
            "/api/v1/voice/commands",
            {"transcript": "把明天会议改到四点"},
        )
        expect(
            update_voice["write_request"] is not None or update_voice["candidates"],
            "reference resolver returned write request or candidates",
        )
        if update_voice["write_request"] is not None:
            update_confirm = client.post(
                f"/api/v1/write-requests/{update_voice['write_request']['id']}/confirm"
            )
            expect(update_confirm.status_code == 200, "voice update confirm")

        modify_wr = post_json(
            client,
            "/api/v1/write-requests",
            {
                "source_command_id": "smoke-modify",
                "candidate_payload": {
                    "operation": "update_item",
                    "target_id": todo["id"],
                    "item": {"title": todo["title"], "type": todo["type"]},
                },
            },
        )["write_request"]
        edited_title = "买牛奶 - edited"
        patch = client.patch(
            f"/api/v1/write-requests/{modify_wr['id']}",
            json={
                "candidate_payload": {
                    **modify_wr["candidate_payload"],
                    "item": {"title": edited_title, "type": todo["type"]},
                    "operations": [
                        {
                            "changes": {"title": edited_title},
                            "op": "update_item",
                            "target_id": todo["id"],
                        }
                    ],
                }
            },
        )
        expect(patch.status_code == 200, "write request edit returned 200")
        expect(
            patch.json()["write_request"]["payload_hash"] != modify_wr["payload_hash"],
            "write request edit refreshed payload hash",
        )
        expect(
            client.post(f"/api/v1/write-requests/{modify_wr['id']}/confirm").status_code
            == 200,
            "manual modify through edited write request",
        )
        modified_todo = next(
            item
            for item in client.get("/api/v1/items").json()
            if item["id"] == todo["id"]
        )
        expect(
            modified_todo["title"] == edited_title, "edited write request changed item"
        )

        complete_wr = post_json(
            client,
            "/api/v1/write-requests",
            {
                "source_command_id": "smoke-complete",
                "candidate_payload": {
                    "operation": "complete_item",
                    "target_id": todo["id"],
                    "item": {"title": todo["title"], "type": todo["type"]},
                },
            },
        )["write_request"]
        expect(
            client.post(
                f"/api/v1/write-requests/{complete_wr['id']}/confirm"
            ).status_code
            == 200,
            "manual complete through write request",
        )
        completed_todo = next(
            item
            for item in client.get("/api/v1/items").json()
            if item["id"] == todo["id"]
        )
        expect(completed_todo["status"] == "completed", "completed item status synced")

        delete_wr = post_json(
            client,
            "/api/v1/write-requests",
            {
                "source_command_id": "smoke-delete",
                "candidate_payload": {
                    "operation": "delete_item",
                    "target_id": calendar["id"],
                    "item": {"title": calendar["title"], "type": calendar["type"]},
                },
            },
        )["write_request"]
        expect(
            client.post(f"/api/v1/write-requests/{delete_wr['id']}/confirm").status_code
            == 200,
            "manual delete through write request",
        )
        visible_after_delete = client.get("/api/v1/items").json()
        expect(
            all(item["id"] != calendar["id"] for item in visible_after_delete),
            "deleted item removed from visible list",
        )
        expect(
            any(
                event["event_type"] == "item.updated"
                and event["aggregate_id"] == calendar["id"]
                and event["payload"]["item"]["status"] == "deleted"
                for event in client.get("/api/v1/events").json()["events"]
            ),
            "deleted item emitted status event",
        )

        multi_wr = post_json(
            client,
            "/api/v1/write-requests",
            {
                "source_command_id": "smoke-multi-reminder",
                "candidate_payload": {
                    "operation": "create_todo_with_reminder",
                    "item": {"title": "多提醒事项", "type": "todo"},
                    "reminders": [
                        {
                            "trigger_type": "time",
                            "trigger_at": "2026-07-28T09:00:00+00:00",
                        },
                        {"trigger_type": "leave_place", "place_ref": "公司"},
                    ],
                },
            },
        )["write_request"]
        expect(
            client.post(f"/api/v1/write-requests/{multi_wr['id']}/confirm").status_code
            == 200,
            "multi reminder write request confirm",
        )
        multi_item = next(
            item
            for item in client.get("/api/v1/items").json()
            if item["title"] == "多提醒事项"
        )
        expect(
            len(multi_item["reminders"]) == 2, "same item displays multiple reminders"
        )

        for place_type in ("home", "work", "custom", "temporary_parking"):
            place = post_json(
                client,
                "/api/v1/places",
                {
                    "label": place_type,
                    "place_type": place_type,
                    "radius_meters": 100,
                    "accuracy_meters": 25,
                },
            )["place"]
            expect(place["place_type"] == place_type, f"saved {place_type} place")

        for pattern, weekdays in (
            ("daily", []),
            ("weekdays", [1, 2, 3, 4, 5]),
            ("custom_weekdays", [2, 4]),
        ):
            repeat = post_json(
                client,
                "/api/v1/repeat-rules",
                {"pattern": pattern, "weekdays": weekdays, "time_of_day": "09:00"},
            )["repeat_rule"]
            expect(repeat["pattern"] == pattern, f"saved repeat {pattern}")

        degraded = post_json(
            client,
            "/api/v1/permissions/degrade",
            {
                "permission": "location",
                "reason": "denied",
                "title": "取快递",
                "place_text": "家",
            },
        )
        expect(
            degraded["item"]["place_text"] == "家",
            "location denied degraded to text place",
        )

        with client.websocket_connect("/api/v1/ws") as websocket:
            ready = websocket.receive_json()
            expect(
                ready["event_type"] == "connection.ready", "websocket connection ready"
            )
            post_json(client, "/api/v1/items", {"type": "todo", "title": "WS 同步事项"})
            websocket.send_json({"type": "sync.request", "after": 0})
            sync = websocket.receive_json()
            expect(sync["event_type"] == "sync.response", "websocket sync response")
            ws_cursor = sync["payload"]["next_cursor"]
            expect(ws_cursor > 0, "websocket returned cursor")

        post_json(client, "/api/v1/items", {"type": "todo", "title": "断线后补拉"})
        backfill = client.get(f"/api/v1/events?after={ws_cursor}").json()
        expect(
            backfill["next_cursor"] > ws_cursor, "HTTP cursor backfilled after WS close"
        )
        expect(
            len(client.get("/api/v1/events/outbox").json()) > 0,
            "outbox projected events",
        )

    print("MVP smoke passed")


if __name__ == "__main__":
    main()
