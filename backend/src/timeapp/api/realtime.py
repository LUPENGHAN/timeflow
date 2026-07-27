"""WebSocket event sync endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from timeapp.api.dependencies import get_timeflow_app
from timeapp.api.schemas import EventResponse
from timeapp.application.service import TimeflowApplication
from timeapp.domain.enums import DomainEventType

router = APIRouter(tags=["realtime"])
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.websocket("/ws")
async def websocket_events(
    websocket: WebSocket,
    app: AppDependency,
) -> None:
    """Provide connection.ready and cursor-based sync responses."""

    await websocket.accept()
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
        return
