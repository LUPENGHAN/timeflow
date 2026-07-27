"""Exception mapping for application errors."""

from fastapi import HTTPException, status

from timeapp.application.service import ApplicationError
from timeapp.domain.errors import ErrorCode


def http_error(error: ApplicationError) -> HTTPException:
    """Convert application errors into HTTP errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    if error.code == ErrorCode.WRITE_REQUEST_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    if error.code == ErrorCode.ITEM_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    if error.code == ErrorCode.REMINDER_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    if error.code == ErrorCode.PLACE_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    if error.code == ErrorCode.WRITE_REQUEST_NOT_PENDING:
        status_code = status.HTTP_409_CONFLICT
    if error.code == ErrorCode.WRITE_REQUEST_EXPIRED:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.message},
    )
