"""In-memory store for the MS1 executable skeleton.

The database schema is initialized separately through Alembic. This store keeps
the API runnable before repository implementations are introduced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from timeapp.domain.enums import WriteRequestStatus
from timeapp.domain.models import DomainEvent, Item, Reminder, VoiceCommand, WriteRequest


@dataclass(slots=True)
class InMemoryStore:
    """Small explicit storage boundary used by tests and local skeleton routes."""

    voice_commands: dict[str, VoiceCommand] = field(default_factory=dict)
    write_requests: dict[str, WriteRequest] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    reminders: dict[str, Reminder] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock)

    def add_voice_command(self, voice_command: VoiceCommand) -> None:
        """Persist a voice command audit record."""

        with self._lock:
            self.voice_commands[voice_command.id] = voice_command

    def add_write_request(self, write_request: WriteRequest) -> None:
        """Persist a pending write request."""

        with self._lock:
            self.write_requests[write_request.id] = write_request

    def get_write_request(self, write_request_id: str) -> WriteRequest | None:
        """Load a write request by id."""

        with self._lock:
            return self.write_requests.get(write_request_id)

    def list_pending_write_requests(self, user_id: str) -> list[WriteRequest]:
        """Return pending write requests for a user."""

        with self._lock:
            return [
                request
                for request in self.write_requests.values()
                if request.identity.user_id == user_id
                and request.status == WriteRequestStatus.PENDING
            ]

    def add_item(self, item: Item) -> None:
        """Persist a calendar or todo item."""

        with self._lock:
            self.items[item.id] = item

    def add_reminder(self, reminder: Reminder) -> None:
        """Persist a reminder."""

        with self._lock:
            self.reminders[reminder.id] = reminder

    def add_events(self, events: list[DomainEvent]) -> None:
        """Append domain events in order."""

        with self._lock:
            self.events.extend(events)

    def list_items(self, user_id: str) -> list[Item]:
        """Return all visible items for a user."""

        with self._lock:
            return [item for item in self.items.values() if item.user_id == user_id]

    def list_events_after(self, cursor: int = 0) -> list[DomainEvent]:
        """Return events after a one-based cursor."""

        with self._lock:
            return self.events[cursor:]
