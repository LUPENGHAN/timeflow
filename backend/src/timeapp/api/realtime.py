"""WebSocket event sync endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from timeapp.api.dependencies import get_timeflow_app
from timeapp.api.schemas import EventResponse
from timeapp.application.service import TimeflowApplication
from timeapp.domain.enums import DomainEventType
from timeapp.domain.models import DomainEvent

router = APIRouter(tags=["realtime"])
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


class RealtimeConnectionManager:
    """Track active WebSocket clients and broadcast domain events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection."""

        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection if it is still registered."""

        self._connections.discard(websocket)

    async def broadcast_events(self, events: list[DomainEvent]) -> None:
        """Broadcast serialized domain events to every active WebSocket."""

        if not events or not self._connections:
            return

        messages = [
            EventResponse.from_domain(event).model_dump(mode="json") for event in events
        ]
        stale_connections: list[WebSocket] = []
        for websocket in list(self._connections):
            try:
                for message in messages:
                    await websocket.send_json(message)
            except RuntimeError:
                stale_connections.append(websocket)
            except WebSocketDisconnect:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(websocket)


realtime_manager = RealtimeConnectionManager()


@router.websocket("/ws")
async def websocket_events(
    websocket: WebSocket,
    app: AppDependency,
) -> None:
    """Provide connection.ready and cursor-based sync responses."""

    await realtime_manager.connect(websocket)
    await websocket.send_json(
        {
            "event_type": DomainEventType.CONNECTION_READY.value,
            "payload": {"message": "connected"},
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "sync.request":
                cursor = int(message.get("after", 0))
                events = app.list_events(cursor)
                await websocket.send_json(
                    {
                        "event_type": DomainEventType.SYNC_RESPONSE.value,
                        "payload": {
                            "next_cursor": cursor + len(events),
                            "events": [
                                EventResponse.from_domain(event).model_dump(mode="json")
                                for event in events
                            ],
                        },
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "event_type": "connection.heartbeat",
                        "payload": {"message": "ok"},
                    }
                )
    except WebSocketDisconnect:
        realtime_manager.disconnect(websocket)
