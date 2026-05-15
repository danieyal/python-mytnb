"""Custom exceptions for the myTNB API client."""

from __future__ import annotations


class MyTNBError(Exception):
    """Base exception for myTNB API errors."""

    def __init__(self, message: str, error_code: str | None = None):
        self.error_code = error_code
        super().__init__(message)


class AuthenticationError(MyTNBError):
    """Raised when authentication fails."""

    pass


class APIError(MyTNBError):
    """Raised when the API returns an error response."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        display_message: str | None = None,
    ):
        self.display_message = display_message
        super().__init__(message, error_code)


class RateLimitError(MyTNBError):
    """Raised when rate limited by the API."""

    pass
