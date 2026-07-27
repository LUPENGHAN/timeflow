"""Skeleton place endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from timeapp.api.dependencies import get_identity, get_timeflow_app
from timeapp.api.errors import http_error
from timeapp.api.schemas import (
    PlaceCreateRequest,
    PlaceCreateResponse,
    PlaceMutationResponse,
    PlaceResponse,
    PlaceUpdateRequest,
)
from timeapp.application.service import ApplicationError, TimeflowApplication
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


@router.patch("/{place_id}", response_model=PlaceMutationResponse)
async def update_place(
    place_id: str,
    request: PlaceUpdateRequest,
    identity: IdentityDependency,
    app: AppDependency,
) -> PlaceMutationResponse:
    """Update an existing place."""

    try:
        place = app.update_place(
            identity=identity,
            place_id=place_id,
            label=request.label,
            place_type=request.place_type,
            radius_meters=request.radius_meters,
            description=request.description,
            latitude=request.latitude,
            longitude=request.longitude,
            accuracy_meters=request.accuracy_meters,
        )
    except ApplicationError as error:
        raise http_error(error) from error

    return PlaceMutationResponse(place=PlaceResponse.from_domain(place))


@router.delete("/{place_id}", response_model=PlaceMutationResponse)
async def delete_place(
    place_id: str,
    identity: IdentityDependency,
    app: AppDependency,
) -> PlaceMutationResponse:
    """Delete an existing place."""

    try:
        place = app.delete_place(identity, place_id)
    except ApplicationError as error:
        raise http_error(error) from error

    return PlaceMutationResponse(place=PlaceResponse.from_domain(place))
