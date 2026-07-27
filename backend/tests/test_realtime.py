"""Tests for realtime WebSocket event broadcasting."""

import asyncio
from datetime import UTC, datetime

from timeapp.api.realtime import RealtimeConnectionManager
from timeapp.domain.enums import DomainEventType
from timeapp.domain.models import DomainEvent


class FakeWebSocket:
    """Minimal WebSocket test double."""

    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, object]) -> None:
        self.messages.append(message)


def test_realtime_manager_broadcasts_domain_events() -> None:
    """Connected clients receive serialized domain event messages."""

    async def run() -> None:
        manager = RealtimeConnectionManager()
        websocket = FakeWebSocket()
        await manager.connect(websocket)  # type: ignore[arg-type]
        await manager.broadcast_events(
            [
                DomainEvent(
                    id="event-1",
                    event_type=DomainEventType.ITEM_CREATED,
                    aggregate_type="item",
                    aggregate_id="item-1",
                    version=1,
                    occurred_at=datetime.now(UTC),
                    payload={"item": {"id": "item-1"}},
                )
            ]
        )

        assert websocket.accepted
        assert websocket.messages[0]["event_type"] == "item.created"
        assert websocket.messages[0]["event_id"] == "event-1"

    asyncio.run(run())
