"""myTNB API client."""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any, Optional

import httpx
import tls_client

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.crypto import encrypt_request
from mytnb.exceptions import (
    APIError,
    AuthenticationError,
    GeoBlockedError,
    MyTNBError,
    RateLimitError,
)
from mytnb.models import (
    AccountUsage,
    BREligibility,
    SMRAccount,
)

# Base URLs
LEGACY_BASE_URL = "https://mytnbapp.tnb.com.my/v7/mytnbws.asmx"
REST_BASE_URL = "https://api.mytnb.com.my"
SITECORE_LOGIN_URL = "https://www.mytnb.com.my/api/sitecore/Account/Login"
SSO_HANDLER_URL = "https://myaccount.mytnb.com.my/SSO/SSOHandler"

# Default user agents
USER_AGENT = "RestSharp/110.2.0.0"
USER_AGENT_IOS = "myTNB/1425 CFNetwork/3860.500.112 Darwin/25.4.0"

# Default API key for token generation (embedded in the mobile app)
DEFAULT_API_KEY = "gpUS5pe4aO2yMbId7bFa13dGfYYnBWbjn3vqn0d7"

# Default security key for legacy ASMX requests (embedded in the mobile app)
DEFAULT_SECURE_KEY_K1 = "E6148656-205B-494C-BC95-CC241423E72F"


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
        self._tls_session: Optional[tls_client.Session] = None

    @property
    def credentials(self) -> Credentials:
        """The authenticated credentials for this client."""
        return self._credentials

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            )
        return self._http_client

    @property
    def _legacy_client(self) -> tls_client.Session:
        """Get or create a tls_client session for legacy ASMX requests.

        Uses an Android TLS fingerprint to bypass CloudFront WAF.
        """
        if self._tls_session is None:
            self._tls_session = tls_client.Session(
                client_identifier="okhttp4_android_13",
            )
        return self._tls_session

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def __aenter__(self) -> "MyTNBClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ──────────────────────────────────────────────────────────────────
    # Authentication
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    async def login(
        cls,
        email: str,
        password: str,
        *,
        device_id: str | None = None,
        timeout: float = 30.0,
        use_staging_key: bool = False,
    ) -> "MyTNBClient":
        """Authenticate with email and password, returning a ready-to-use client.

        Performs the full login flow:
        1. Authenticate via Sitecore web login (plaintext credentials)
        2. Submit SSO form to get user identity (userId)
        3. Generate an access token via the REST Identity API

        Args:
            email: myTNB account email.
            password: myTNB account password.
            device_id: Optional device UUID (generated if not provided).
            timeout: HTTP timeout in seconds.
            use_staging_key: Use the staging RSA key for encryption.

        Returns:
            An authenticated MyTNBClient instance.
        """
        if not device_id:
            device_id = str(uuid.uuid4()).upper()

        device_info = DeviceInfo(device_id=device_id)

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as http:
            # Step 1: Sitecore login (get SSO form with encrypted credentials)
            await http.get("https://www.mytnb.com.my/")

            login_resp = await http.post(
                SITECORE_LOGIN_URL,
                data={"Email": email, "Password": password},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://www.mytnb.com.my",
                    "Referer": "https://www.mytnb.com.my/",
                },
            )

            if login_resp.status_code == 403:
                raise GeoBlockedError()
            if login_resp.status_code != 200:
                raise AuthenticationError(
                    "Login failed",
                    error_code=str(login_resp.status_code),
                )

            # Extract SSO form fields from the HTML response
            sso_fields = dict(
                re.findall(
                    r'name="([^"]+)"\s+value="([^"]*)"',
                    login_resp.text,
                )
            )
            if "USERNAME" not in sso_fields:
                raise AuthenticationError(
                    "Invalid credentials or unexpected login response",
                    error_code="LOGIN_FAILED",
                )

            # Step 2: Submit SSO form to get JWT with userId
            sso_resp = await http.post(
                SSO_HANDLER_URL,
                data=sso_fields,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://www.mytnb.com.my",
                },
            )

            if sso_resp.status_code != 200:
                raise AuthenticationError(
                    "SSO authentication failed",
                    error_code=str(sso_resp.status_code),
                )

            # Extract userId from JWT in set-cookie headers
            user_id = None
            user_name = email
            display_name = ""
            for cookie_header in sso_resp.headers.get_list("set-cookie"):
                if "eyJhbGci" not in cookie_header:
                    continue
                jwt_match = re.search(r"=(eyJ[^;]+)", cookie_header)
                if not jwt_match:
                    continue
                parts = jwt_match.group(1).split(".")
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                jwt_data = json.loads(base64.b64decode(payload_b64))
                ui = json.loads(jwt_data["UserInfo"])
                user_id = ui["UserId"]
                user_name = ui.get("UserName", email)
                display_name = ui.get("DisplayName", "")
                break

            if not user_id:
                raise AuthenticationError(
                    "Failed to extract user identity from SSO response",
                    error_code="SSO_PARSE_FAILED",
                )

            # Step 3: Generate access token via REST API
            token_resp = await http.post(
                f"{REST_BASE_URL}/Identity/api/v1/Identity/GenerateAccessToken",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": DEFAULT_API_KEY,
                    "Accept": "application/json",
                },
                params={"environment": "Prod"},
                json={
                    "channel": "myTNB_API_Mobile",
                    "userId": user_id,
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data["content"]["accessToken"]

        secure_key = str(uuid.uuid4()).upper()

        credentials = Credentials(
            api_key=DEFAULT_API_KEY,
            authorization_token=access_token,
            secure_key=secure_key,
            user_info=UserInfo(
                user_name=user_name,
                user_id=user_id,
                display_name=display_name,
            ),
            device_info=device_info,
        )

        return cls(credentials, timeout=timeout, use_staging_key=use_staging_key)

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

        if response.status_code == 403:
            raise GeoBlockedError()
        if response.status_code == 401:
            raise AuthenticationError("Authentication failed", error_code="401")
        if response.status_code == 429:
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

        if response.status_code == 403:
            raise GeoBlockedError()
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
        Uses tls_client with an Android TLS fingerprint to bypass CloudFront WAF.

        Args:
            endpoint: The ASMX method name (e.g., "GetAccountUsageSmart")
            data: The plaintext request data (will be encrypted).
        """
        url = f"{LEGACY_BASE_URL}/{endpoint}"
        headers = self._legacy_headers()
        headers["User-Agent"] = USER_AGENT

        # ASMX requests do NOT include deviceInf (per decompiled app code)

        payload = encrypt_request(data, use_staging_key=self._use_staging_key)
        body = {"dt": payload.to_dict()}

        response = self._legacy_client.post(url, headers=headers, json=body)

        if response.status_code == 403:
            raise GeoBlockedError()
        if response.status_code == 401:
            raise AuthenticationError("Authentication failed", error_code="401")

        if response.status_code != 200:
            raise APIError(
                message=f"Legacy API request failed with status {response.status_code}",
                error_code=str(response.status_code),
            )

        data = response.json()

        # Check the 'd' wrapper for errors
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

    def _device_info(self) -> dict:
        """Build the deviceInf object for legacy ASMX requests."""
        di = self._credentials.device_info
        if not di:
            return {}
        return di.to_dict()

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
            "contractAccount": account_number,
            "isOwner": "true" if is_owner else "false",
            "metercode": "",
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
            "contractAccount": account_number,
            "isOwner": "true" if is_owner else "false",
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
            "contractAccount": account_number,
            "isOwnedAccount": "true" if is_owner else "false",
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
            "contractAccount": account_number,
            "isOwnedAccount": "true" if is_owner else "false",
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
