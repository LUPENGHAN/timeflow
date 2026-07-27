"""Skeleton place endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.schemas import PlaceCreateRequest, PlaceCreateResponse, PlaceResponse
from timeapp.application.service import TimeflowApplication
from timeapp.domain.models import Identity

router = APIRouter(prefix="/places", tags=["places"])
IdentityDependency = Annotated[Identity, Depends(get_identity)]
AppDependency = Annotated[TimeflowApplication, Depends(get_timeflow_app)]


@router.get("", response_model=list[PlaceResponse])
async def list_places(
    identity: IdentityDependency,
    app: AppDependency,
) -> list[PlaceResponse]:
    """Return configured places."""

    return [PlaceResponse.from_domain(place) for place in app.list_places(identity)]


@router.post("", response_model=PlaceCreateResponse)
async def create_place(
    request: PlaceCreateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> PlaceCreateResponse:
    """Create a lightweight place skeleton record."""

    place = app.create_place(
        identity=identity,
        label=request.label,
        place_type=request.place_type,
        radius_meters=request.radius_meters,
        description=request.description,
        latitude=request.latitude,
        longitude=request.longitude,
        accuracy_meters=request.accuracy_meters,
    )
    return PlaceCreateResponse(place=PlaceResponse.from_domain(place))
