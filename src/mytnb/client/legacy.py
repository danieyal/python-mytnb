"""Legacy ASMX API transport (mytnbapp.tnb.com.my) with encryption."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from curl_cffi import requests as curl_requests

from mytnb.auth import Credentials
from mytnb.client.config import (
    DEFAULT_SECURE_KEY_K1,
    LEGACY_BASE_URL,
    USER_AGENT,
    _check_http_status,
)
from mytnb.client.retry import RETRYABLE_STATUS_CODES, with_retry
from mytnb.crypto import encrypt_request
from mytnb.exceptions import (
    APIError,
    MyTNBError,
)

logger = logging.getLogger(__name__)


class _LegacyTransport:
    """Internal helper for legacy ASMX API encrypted requests."""

    def __init__(
        self,
        session: curl_requests.Session,
        credentials: Credentials,
        timeout: float,
        use_staging_key: bool,
    ):
        self._session = session
        self._credentials = credentials
        self._timeout = timeout
        self._use_staging_key = use_staging_key

    def headers(self) -> dict[str, str]:
        """Build headers for legacy ASMX API requests."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json,text/json,text/x-json,text/javascript,application/xml,text/xml",
            "Lang": "EN",
        }

        if self._credentials.user_info:
            headers["UserInfo"] = json.dumps(self._credentials.user_info.to_dict())

        if self._credentials.secure_key:
            headers["SecureKey"] = self._credentials.secure_key

        return headers

    def base_user_info(self) -> dict:
        """Build the usrInf object from credentials for legacy ASMX requests."""
        ui = self._credentials.user_info
        di = self._credentials.device_info
        if not ui:
            raise MyTNBError("user_info is required for legacy API calls")
        return {
            "eid": ui.user_name,
            "sspuid": ui.user_id,
            "did": di.device_id if di else "",
            "ft": "",
            "lang": ui.language,
            "sec_auth_k1": DEFAULT_SECURE_KEY_K1,
            "sec_auth_k2": "",
            "ses_param1": "",
            "ses_param2": "",
        }

    def base_device_info(self) -> dict:
        """Build the deviceInf object from credentials for legacy ASMX requests."""
        di = self._credentials.device_info
        if not di:
            return {}
        return di.to_dict()

    async def post(self, endpoint: str, data: Any) -> dict:
        """Make a POST request to the legacy ASMX API.

        Automatically encrypts the data using AES-256-CBC + RSA-OAEP.
        Uses curl_cffi with a TLS fingerprint to bypass CloudFront WAF.
        """
        url = f"{LEGACY_BASE_URL}/{endpoint}"
        req_headers = self.headers()
        req_headers["User-Agent"] = USER_AGENT

        payload = encrypt_request(data, use_staging_key=self._use_staging_key)
        body = {"dt": payload.to_dict()}

        async def _send() -> Any:
            response = await asyncio.to_thread(
                self._session.post,
                url,
                headers=req_headers,
                json=body,
                timeout=int(self._timeout),
            )
            logger.debug("Legacy POST %s → %s", endpoint, response.status_code)

            _check_http_status(response.status_code, context="legacy API")

            if response.status_code != 200:
                raise APIError(
                    message=f"Legacy API request failed with status {response.status_code}",
                    error_code=str(response.status_code),
                    retryable=response.status_code in RETRYABLE_STATUS_CODES,
                )
            return response

        response = await with_retry(_send, logger=logger)

        data = response.json()

        d = data.get("d", {})
        error_code = d.get("ErrorCode")
        if error_code and error_code not in ("7200", "7204"):
            display_msg = d.get("DisplayMessage") or d.get("displayMessage")
            msg = display_msg or d.get("Message") or d.get("message") or "Unknown error"
            raise APIError(
                message=msg,
                error_code=error_code,
                display_message=display_msg,
            )

        return d
