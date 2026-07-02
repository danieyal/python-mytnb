"""REST API transport (api.mytnb.com.my)."""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from mytnb.auth import Credentials
from mytnb.client.config import REST_BASE_URL, _check_http_status
from mytnb.client.retry import RETRYABLE_STATUS_CODES, with_retry
from mytnb.exceptions import APIError

logger = logging.getLogger(__name__)


class _RestTransport:
    """Internal helper for REST API HTTP requests."""

    def __init__(self, client: httpx.AsyncClient, credentials: Credentials):
        self._client = client
        self._credentials = credentials

    def headers(self) -> dict[str, str]:
        """Build headers for REST API requests."""
        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "*/*",
            "x-api-key": self._credentials.api_key,
            "Authorization": self._credentials.authorization_token,
        }

        if self._credentials.device_info:
            view_info = {
                "DeviceToken": self._credentials.device_info.device_id,
                "AppVersion": self._credentials.device_info.app_version,
                "RoleId": self._credentials.user_info.role_id
                if self._credentials.user_info
                else "16",
                "Lang": "EN",
                "FontSize": "L",
                "OSType": self._credentials.device_info.os_type,
            }
            headers["ViewInfo"] = json.dumps(view_info)

        if self._credentials.channel_api_key:
            headers["ApiKey"] = self._credentials.channel_api_key

        return headers

    def bearer_headers(self) -> dict[str, str]:
        """Build headers for Bearer-token authenticated endpoints."""
        headers = self.headers()
        if self._credentials.bearer_token:
            headers["Authorization"] = f"Bearer {self._credentials.bearer_token}"
        return headers

    async def post(
        self,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
        use_bearer: bool = False,
    ) -> dict:
        """Make a POST request to the REST API."""
        url = f"{REST_BASE_URL}/{path.lstrip('/')}"
        req_headers = self.bearer_headers() if use_bearer else self.headers()

        if params is None:
            params = {"environment": "Prod"}

        async def _send() -> httpx.Response:
            response = await self._client.post(
                url,
                headers=req_headers,
                json=body or {},
                params=params,
            )
            logger.debug("REST POST %s → %s", path, response.status_code)

            _check_http_status(response.status_code)
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise APIError(
                    message=f"REST API request failed with status {response.status_code}",
                    error_code=str(response.status_code),
                    retryable=True,
                )
            response.raise_for_status()
            return response

        response = await with_retry(_send, logger=logger)
        data = response.json()

        status = data.get("statusDetail", {})
        if status.get("code") and status["code"] != "7200":
            logger.error(
                "REST API error code=%s desc=%s",
                status.get("code"),
                status.get("description"),
            )
            raise APIError(
                message=status.get("description", "Unknown error"),
                error_code=status.get("code"),
            )

        return data

    async def get(
        self,
        path: str,
        params: Optional[dict] = None,
        use_bearer: bool = False,
    ) -> dict:
        """Make a GET request to the REST API."""
        url = f"{REST_BASE_URL}/{path.lstrip('/')}"
        req_headers = self.bearer_headers() if use_bearer else self.headers()

        if params is None:
            params = {"environment": "Prod"}

        async def _send() -> httpx.Response:
            response = await self._client.get(url, headers=req_headers, params=params)
            logger.debug("REST GET %s → %s", path, response.status_code)

            _check_http_status(response.status_code)
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise APIError(
                    message=f"REST API request failed with status {response.status_code}",
                    error_code=str(response.status_code),
                    retryable=True,
                )
            response.raise_for_status()
            return response

        response = await with_retry(_send, logger=logger)
        return response.json()
