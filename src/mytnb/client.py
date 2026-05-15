"""myTNB API client."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.crypto import encrypt_request
from mytnb.exceptions import APIError, AuthenticationError, MyTNBError
from mytnb.models import (
    AccountUsage,
    BREligibility,
    SMRAccount,
)

# Base URLs
LEGACY_BASE_URL = "https://mytnbapp.tnb.com.my/v7/mytnbws.asmx"
REST_BASE_URL = "https://api.mytnb.com.my"

# Default user agent
USER_AGENT = "myTNB/1425 CFNetwork/3860.500.112 Darwin/25.4.0"


class MyTNBClient:
    """Client for interacting with the myTNB API.

    This client supports two API backends:
    - Legacy ASMX API (mytnbapp.tnb.com.my) - uses encrypted payloads
    - REST API (api.mytnb.com.my) - uses JWT authentication

    For the REST API, you need an API key and authorization token.
    The legacy API payloads are automatically encrypted using the
    embedded RSA public key + AES-256-CBC.
    """

    def __init__(
        self,
        credentials: Credentials,
        timeout: float = 30.0,
        *,
        use_staging_key: bool = False,
    ):
        self._credentials = credentials
        self._timeout = timeout
        self._use_staging_key = use_staging_key
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def __aenter__(self) -> "MyTNBClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ──────────────────────────────────────────────────────────────────
    # REST API helpers
    # ──────────────────────────────────────────────────────────────────

    def _rest_headers(self) -> dict[str, str]:
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

    def _bearer_headers(self) -> dict[str, str]:
        """Build headers for Bearer-token authenticated endpoints."""
        headers = self._rest_headers()
        if self._credentials.bearer_token:
            headers["Authorization"] = f"Bearer {self._credentials.bearer_token}"
        return headers

    async def _rest_post(
        self,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
        use_bearer: bool = False,
    ) -> dict:
        """Make a POST request to the REST API."""
        url = f"{REST_BASE_URL}/{path.lstrip('/')}"
        headers = self._bearer_headers() if use_bearer else self._rest_headers()

        if params is None:
            params = {"environment": "Prod"}

        response = await self._client.post(
            url,
            headers=headers,
            json=body or {},
            params=params,
        )

        if response.status_code == 401:
            raise AuthenticationError("Authentication failed", error_code="401")
        if response.status_code == 429:
            from mytnb.exceptions import RateLimitError

            raise RateLimitError("Rate limited by API")

        response.raise_for_status()
        data = response.json()

        # Check for API-level errors
        status = data.get("statusDetail", {})
        if status.get("code") and status["code"] != "7200":
            raise APIError(
                message=status.get("description", "Unknown error"),
                error_code=status.get("code"),
            )

        return data

    async def _rest_get(
        self,
        path: str,
        params: Optional[dict] = None,
        use_bearer: bool = False,
    ) -> dict:
        """Make a GET request to the REST API."""
        url = f"{REST_BASE_URL}/{path.lstrip('/')}"
        headers = self._bearer_headers() if use_bearer else self._rest_headers()

        if params is None:
            params = {"environment": "Prod"}

        response = await self._client.get(url, headers=headers, params=params)

        if response.status_code == 401:
            raise AuthenticationError("Authentication failed", error_code="401")

        response.raise_for_status()
        return response.json()

    # ──────────────────────────────────────────────────────────────────
    # Legacy API helpers
    # ──────────────────────────────────────────────────────────────────

    def _legacy_headers(self) -> dict[str, str]:
        """Build headers for legacy ASMX API requests."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json,text/json,text/x-json,text/javascript,application/xml,text/xml",
            "Lang": "EN",
        }

        if self._credentials.user_info:
            headers["UserInfo"] = json.dumps(
                self._credentials.user_info.to_dict()
            )

        if self._credentials.secure_key:
            headers["SecureKey"] = self._credentials.secure_key

        return headers

    async def _legacy_post(self, endpoint: str, data: Any) -> dict:
        """Make a POST request to the legacy ASMX API.

        Automatically encrypts the data using AES-256-CBC + RSA-OAEP.

        Args:
            endpoint: The ASMX method name (e.g., "GetAccountUsageSmart")
            data: The plaintext request data (will be encrypted).
        """
        url = f"{LEGACY_BASE_URL}/{endpoint}"
        headers = self._legacy_headers()
        payload = encrypt_request(data, use_staging_key=self._use_staging_key)
        body = {"dt": payload.to_dict()}

        response = await self._client.post(url, headers=headers, json=body)

        if response.status_code == 401:
            raise AuthenticationError("Authentication failed", error_code="401")

        response.raise_for_status()
        data = response.json()

        # Check the 'd' wrapper for errors
        d = data.get("d", {})
        if d.get("isError") == "true":
            raise APIError(
                message=d.get("message", "Unknown error"),
                error_code=d.get("ErrorCode"),
                display_message=d.get("DisplayMessage"),
            )

        return d

    # ──────────────────────────────────────────────────────────────────
    # REST API endpoints
    # ──────────────────────────────────────────────────────────────────

    async def get_bill_eligibility(
        self, contract_accounts: list[str], user_id: str
    ) -> list[BREligibility]:
        """Get bill rendering eligibility indicators for accounts.

        Args:
            contract_accounts: List of contract account numbers.
            user_id: The user's UUID.

        Returns:
            List of BREligibility objects.
        """
        body = {"caNos": contract_accounts, "userID": user_id}
        data = await self._rest_post(
            "BillRendering/api/v1/BillRendering/BREligibilityIndicators",
            body=body,
        )
        content = data.get("content", [])
        return [BREligibility.model_validate(item) for item in content]

    async def get_draft_application_status(self) -> dict:
        """Get draft application status for MyHome.

        Returns:
            Raw response content.
        """
        data = await self._rest_post(
            "myhome/myhome-svc/api/v1/GetDraftApplication/GetDraftApplicationStatus",
            use_bearer=True,
        )
        return data.get("content") or data

    async def get_eligibility_icons(self) -> dict:
        """Get more icon list (eligibility features).

        Returns:
            Raw response content.
        """
        user_info = self._credentials.user_info
        device_info = self._credentials.device_info

        body = {}
        if user_info and device_info:
            body = {
                "usrInf": {
                    "userName": user_info.user_name,
                    "userID": user_info.user_id,
                    "sspuid": user_info.user_id,
                    "deviceID": device_info.device_id,
                    "language": user_info.language,
                    "sec_auth_k1": self._credentials.secure_key or "",
                    "sec_auth_k2": "",
                    "isWhiteList": False,
                },
                "deviceInf": device_info.to_dict(),
            }

        data = await self._rest_post(
            "Eligibility/api/v1/Eligibility/GetMoreIconList",
            body=body,
        )
        return data.get("content") or data

    # ──────────────────────────────────────────────────────────────────
    # Legacy API endpoints (auto-encrypted)
    # ──────────────────────────────────────────────────────────────────

    def _base_user_info(self) -> dict:
        """Build the usrInf object from credentials."""
        ui = self._credentials.user_info
        di = self._credentials.device_info
        if not ui:
            raise MyTNBError("user_info is required for legacy API calls")
        return {
            "sspuid": ui.user_id,
            "did": di.device_id if di else "",
            "ft": "",
            "lang": ui.language,
            "sec_auth_k1": self._credentials.secure_key or "",
            "sec_auth_k2": "",
            "ses_param1": "",
            "ses_param2": "",
        }

    async def get_account_usage_smart(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> AccountUsage:
        """Get smart meter account usage data.

        Args:
            account_number: The contract account number.
            is_owner: Whether the user owns the account.

        Returns:
            AccountUsage object with usage and billing data.
        """
        data = {
            "AccountNumber": account_number,
            "isOwner": is_owner,
            "MeterCode": "",
            "usrInf": self._base_user_info(),
        }
        result = await self._legacy_post("GetAccountUsageSmart", data)
        return AccountUsage.from_api_response(result.get("data", {}))

    async def get_smr_accounts(
        self,
        contract_accounts: list[str],
    ) -> list[SMRAccount]:
        """Get Smart Meter Reading account statuses.

        Args:
            contract_accounts: List of contract account numbers.

        Returns:
            List of SMRAccount objects.
        """
        data = {
            "contractAccounts": contract_accounts,
            "usrInf": self._base_user_info(),
        }
        result = await self._legacy_post("GetAccountsSMRIcon", data)
        accounts = result.get("data", [])
        return [SMRAccount.model_validate(acc) for acc in accounts]

    async def get_services(self) -> dict:
        """Get available services (V4).

        Returns:
            Raw service data dict.
        """
        data = {"usrInf": self._base_user_info()}
        return await self._legacy_post("GetServicesV4", data)

    async def get_energy_recommendations(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> dict:
        """Get energy budget recommendations.

        Args:
            account_number: The contract account number.
            is_owner: Whether the user owns the account.

        Returns:
            Raw recommendations data.
        """
        data = {
            "AccountNumber": account_number,
            "isOwner": is_owner,
            "usrInf": self._base_user_info(),
        }
        result = await self._legacy_post("GetUserEBRecommendations", data)
        return result.get("data") or result

    async def get_account_due_amount(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> dict:
        """Get account due amount.

        Args:
            account_number: The contract account number.
            is_owner: Whether the user owns the account.

        Returns:
            Raw due amount data.
        """
        data = {
            "AccountNumber": account_number,
            "IsOwnedAccount": is_owner,
            "usrInf": self._base_user_info(),
        }
        result = await self._legacy_post("GetAccountDueAmount", data)
        return result.get("data") or result

    async def get_bill_history(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> dict:
        """Get bill payment history.

        Args:
            account_number: The contract account number.
            is_owner: Whether the user owns the account.

        Returns:
            Raw bill history data.
        """
        data = {
            "accNum": account_number,
            "isOwnedAccount": is_owner,
            "usrInf": self._base_user_info(),
        }
        result = await self._legacy_post("GetBillHistory", data)
        return result.get("data") or result

    # ──────────────────────────────────────────────────────────────────
    # Convenience methods
    # ──────────────────────────────────────────────────────────────────

    async def get_current_usage(self, account_number: str) -> dict:
        """Get a simplified summary of current usage.

        Args:
            account_number: The contract account number.

        Returns:
            Dict with current_usage_kwh, current_cost_rm, projected_cost_rm.
        """
        usage = await self.get_account_usage_smart(account_number)
        return {
            "current_usage_kwh": usage.current_usage_kwh,
            "current_cost_rm": usage.current_cost_rm,
            "projected_cost_rm": usage.projected_cost_rm,
            "date_range": usage.date_range,
        }
