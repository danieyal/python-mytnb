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


class GeoBlockedError(MyTNBError):
    """Raised when the request is blocked due to geographic restrictions.

    The myTNB API only allows connections from Malaysian IP addresses
    and blocks most VPNs.
    """

    def __init__(self):
        super().__init__(
            "Access denied — the myTNB API is restricted to Malaysian IP addresses "
            "and blocks VPN connections. Connect from a Malaysian network without a VPN.",
            error_code="403",
        )
