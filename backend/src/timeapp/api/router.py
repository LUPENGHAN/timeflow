"""Aggregate infrastructure and domain routers."""

from fastapi import APIRouter

from timeapp.api.agenda import router as agenda_router
from timeapp.api.events import router as events_router
from timeapp.api.health import router as health_router
from timeapp.api.items import router as items_router
from timeapp.api.permissions import router as permissions_router
from timeapp.api.realtime import router as realtime_router
from timeapp.api.reminders import router as reminders_router
from timeapp.api.repeat_rules import router as repeat_rules_router
from timeapp.api.voice import router as voice_router
from timeapp.api.write_requests import router as write_requests_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(agenda_router)
api_router.include_router(voice_router)
api_router.include_router(write_requests_router)
api_router.include_router(items_router)
api_router.include_router(permissions_router)
api_router.include_router(repeat_rules_router)
api_router.include_router(reminders_router)
api_router.include_router(events_router)
api_router.include_router(realtime_router)
