"""Custom exceptions for the application."""
from fastapi import HTTPException, status


class AppException(Exception):
    """Base exception for application errors."""
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.detail = detail
        self.status_code = status_code
        super().__init__(self.detail)


class NotFoundException(AppException):
    """Resource not found exception."""
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail, status.HTTP_404_NOT_FOUND)


class UnauthorizedException(AppException):
    """Unauthorized access exception."""
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(detail, status.HTTP_401_UNAUTHORIZED)


class ForbiddenException(AppException):
    """Forbidden access exception."""
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(detail, status.HTTP_403_FORBIDDEN)


class BadRequestException(AppException):
    """Bad request exception."""
    def __init__(self, detail: str = "Bad request"):
        super().__init__(detail, status.HTTP_400_BAD_REQUEST)