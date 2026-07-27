"""Skeleton repeat rule endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.schemas import (
    RepeatRuleCreateRequest,
    RepeatRuleCreateResponse,
    RepeatRuleResponse,
)
from timeapp.application.service import TimeflowApplication
from timeapp.domain.models import Identity

router = APIRouter(prefix="/repeat-rules", tags=["repeat-rules"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.get("", response_model=list[RepeatRuleResponse])
async def list_repeat_rules(
    identity: IdentityDependency,
    app: AppDependency,
) -> list[RepeatRuleResponse]:
    """Return repeat rules for the current user."""

    return [RepeatRuleResponse.from_domain(rule) for rule in app.list_repeat_rules(identity)]


@router.post("", response_model=RepeatRuleCreateResponse)
async def create_repeat_rule(
    request: RepeatRuleCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> RepeatRuleCreateResponse:
    """Create a repeat rule skeleton record."""

    repeat_rule = app.create_repeat_rule(
        identity=identity,
        pattern=request.pattern,
        weekdays=request.weekdays,
        time_of_day=request.time_of_day,
        series_status=request.series_status,
    )
    return RepeatRuleCreateResponse(
        repeat_rule=RepeatRuleResponse.from_domain(repeat_rule),
    )
