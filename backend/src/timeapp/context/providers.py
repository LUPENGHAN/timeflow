"""Context provider interfaces and P0 lightweight implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class TimeContext:
    """Current time and timezone used by reminders and queries."""

    now: datetime
    timezone: str


@dataclass(frozen=True, slots=True)
class PlaceContext:
    """A user-confirmed or temporary place input."""

    place_id: str
    label: str
    latitude: float | None = None
    longitude: float | None = None
    accuracy_meters: float | None = None
    radius_meters: float = 100


class TimeContextProvider:
    """Active P0 provider for current time and user timezone."""

    def current(self, timezone: str = "UTC") -> TimeContext:
        """获取当前时间上下文。"""

        return TimeContext(now=datetime.now(UTC), timezone=timezone)


class PlaceContextProvider:
    """Active P0 provider for fixed or temporary places.

    This skeleton does not request device permissions or track continuous
    location. Clients pass confirmed place data into commands.
    """

    def from_label(self, label: str) -> PlaceContext:
        """根据标签构造地点上下文。"""

        return PlaceContext(place_id=label, label=label)


class WeatherContextProvider:
    """Skeleton provider; not active in P0."""


class NoiseContextProvider:
    """Skeleton provider; not active in P0."""


class DeviceStateContextProvider:
    """Skeleton provider; not active in P0."""


class UserPreferenceContextProvider:
    """Skeleton provider; not active in P0."""
