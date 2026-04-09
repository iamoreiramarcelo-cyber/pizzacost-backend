from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: list[Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []
        super().__init__(self.message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


def not_found(resource: str = "Resource", details: list[Any] | None = None) -> AppException:
    return AppException(
        code="NOT_FOUND",
        message=f"{resource} not found.",
        status=404,
        details=details,
    )


def unauthorized(message: str = "Authentication required.", details: list[Any] | None = None) -> AppException:
    return AppException(
        code="UNAUTHORIZED",
        message=message,
        status=401,
        details=details,
    )


def forbidden(message: str = "You do not have permission to perform this action.", details: list[Any] | None = None) -> AppException:
    return AppException(
        code="FORBIDDEN",
        message=message,
        status=403,
        details=details,
    )


def validation_error(message: str = "Validation failed.", details: list[Any] | None = None) -> AppException:
    return AppException(
        code="VALIDATION_ERROR",
        message=message,
        status=422,
        details=details,
    )


def subscription_limit(message: str = "You have reached your plan limit. Upgrade to continue.", details: list[Any] | None = None) -> AppException:
    return AppException(
        code="SUBSCRIPTION_LIMIT",
        message=message,
        status=403,
        details=details,
    )
