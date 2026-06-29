"""myTNB API client."""

from __future__ import annotations

from typing import Any, Optional

import httpx
import tls_client

from mytnb.auth import Credentials
from mytnb.client.auth import login
from mytnb.client.config import AWS_API_BASE_URL, USER_AGENT, _check_http_status
from mytnb.client.legacy import _LegacyTransport
from mytnb.client.rest import _RestTransport
from mytnb.crypto import encrypt_request
from mytnb.exceptions import APIError
from mytnb.models import AccountUsage, BREligibility, CustomerAccount, SMRAccount


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
        self._rest: Optional[_RestTransport] = None
        self._legacy: Optional[_LegacyTransport] = None

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

    @property
    def _rest_transport(self) -> _RestTransport:
        if self._rest is None:
            self._rest = _RestTransport(self._client, self._credentials)
        return self._rest

    @property
    def _legacy_transport(self) -> _LegacyTransport:
        if self._legacy is None:
            self._legacy = _LegacyTransport(
                self._legacy_client,
                self._credentials,
                self._timeout,
                self._use_staging_key,
            )
        return self._legacy

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def __aenter__(self) -> "MyTNBClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    login = classmethod(login)

    # ── REST API endpoints ──────────────────────────────────────────

    async def get_bill_eligibility(
        self, contract_accounts: list[str], user_id: str
    ) -> list[BREligibility]:
        """Get bill rendering eligibility indicators for accounts."""
        body = {"caNos": contract_accounts, "userID": user_id}
        data = await self._rest_transport.post(
            "BillRendering/api/v1/BillRendering/BREligibilityIndicators",
            body=body,
        )
        content = data.get("content", [])
        return [BREligibility.model_validate(item) for item in content]

    async def get_draft_application_status(self) -> dict:
        """Get draft application status for MyHome."""
        data = await self._rest_transport.post(
            "myhome/myhome-svc/api/v1/GetDraftApplication/GetDraftApplicationStatus",
            use_bearer=True,
        )
        return data.get("content") or data

    async def get_eligibility_icons(self) -> dict:
        """Get more icon list (eligibility features)."""
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

        data = await self._rest_transport.post(
            "Eligibility/api/v1/Eligibility/GetMoreIconList",
            body=body,
        )
        return data.get("content") or data

    # ── Legacy API endpoints (auto-encrypted) ───────────────────────

    async def get_account_usage_smart(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> AccountUsage:
        """Get smart meter account usage data."""
        data = {
            "contractAccount": account_number,
            "isOwner": "true" if is_owner else "false",
            "metercode": "",
            "usrInf": self._legacy_transport.base_user_info(),
        }
        result = await self._legacy_transport.post("GetAccountUsageSmart", data)
        return AccountUsage.from_api_response(result.get("data", {}))

    async def get_smr_accounts(
        self,
        contract_accounts: list[str],
    ) -> list[SMRAccount]:
        """Get Smart Meter Reading account statuses."""
        data = {
            "contractAccounts": contract_accounts,
            "usrInf": self._legacy_transport.base_user_info(),
        }
        result = await self._legacy_transport.post("GetAccountsSMRIcon", data)
        accounts = result.get("data", [])
        return [SMRAccount.model_validate(acc) for acc in accounts]

    async def get_services(self) -> dict:
        """Get available services (V4)."""
        data = {"usrInf": self._legacy_transport.base_user_info()}
        return await self._legacy_transport.post("GetServicesV4", data)

    async def get_customer_accounts(self) -> list[CustomerAccount]:
        """Get all accounts linked to the current user.

        This is the auto-discovery endpoint — call this first to
        discover which accounts are available, then pass individual
        account numbers to get_account_usage_smart(), etc.

        Uses POST /v3/account/GetAccount via the AWS API gateway.
        The payload is encrypted (same encryption as legacy ASMX)
        but the response is plain JSON (no ``{"d":{...}}`` wrapper).
        """
        usr_inf = self._legacy_transport.base_user_info()
        usr_inf["IsWhiteList"] = False
        data = {
            "usrInf": usr_inf,
            "deviceInf": self._legacy_transport.base_device_info(),
            "featureInfo": [],
        }

        payload = encrypt_request(data, use_staging_key=self._use_staging_key)
        body = {"dt": payload.to_dict()}

        response = await self._client.post(
            f"{AWS_API_BASE_URL}/v3/account/GetAccount",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json,text/json,text/x-json,text/javascript,application/xml,text/xml",
                "User-Agent": USER_AGENT,
            },
            json=body,
        )

        _check_http_status(response.status_code, context="AWS account API")

        if response.status_code != 200:
            raise APIError(
                message=f"AWS account API request failed with status {response.status_code}",
                error_code=str(response.status_code),
            )

        data = response.json()
        accounts = data.get("data", [])
        return [CustomerAccount.model_validate(acc) for acc in accounts]

    async def get_energy_recommendations(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> dict:
        """Get energy budget recommendations."""
        data = {
            "contractAccount": account_number,
            "isOwner": "true" if is_owner else "false",
            "usrInf": self._legacy_transport.base_user_info(),
        }
        result = await self._legacy_transport.post("GetUserEBRecommendations", data)
        return result.get("data") or result

    async def get_account_due_amount(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> dict:
        """Get account due amount."""
        data = {
            "contractAccount": account_number,
            "isOwnedAccount": "true" if is_owner else "false",
            "usrInf": self._legacy_transport.base_user_info(),
        }
        result = await self._legacy_transport.post("GetAccountDueAmount", data)
        return result.get("data") or result

    async def get_bill_history(
        self,
        account_number: str,
        *,
        is_owner: bool = True,
    ) -> dict:
        """Get bill payment history."""
        data = {
            "contractAccount": account_number,
            "isOwnedAccount": "true" if is_owner else "false",
            "usrInf": self._legacy_transport.base_user_info(),
        }
        result = await self._legacy_transport.post("GetBillHistory", data)
        return result.get("data") or result

    async def get_current_usage(self, account_number: str) -> dict:
        """Get a simplified summary of current usage."""
        usage = await self.get_account_usage_smart(account_number)
        return {
            "current_usage_kwh": usage.current_usage_kwh,
            "current_cost_rm": usage.current_cost_rm,
            "projected_cost_rm": usage.projected_cost_rm,
            "date_range": usage.date_range,
        }
