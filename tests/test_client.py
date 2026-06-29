"""Tests for mytnb.client API client."""

# pylint: disable=duplicate-code, protected-access

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.client import MyTNBClient
from mytnb.client.config import DEFAULT_API_KEY
from mytnb.exceptions import APIError, AuthenticationError, MyTNBError, RateLimitError

# ── Fixtures ──────────────────────────────────────────────────────────────


def _creds(**overrides) -> Credentials:
    defaults = {
        "api_key": "test-api-key",
        "authorization_token": "test-auth-token",
        "secure_key": "test-secure-key",
        "user_info": UserInfo(user_name="test@example.com", user_id="uid-123"),
        "device_info": DeviceInfo(device_id="dev-456"),
    }
    defaults.update(overrides)
    return Credentials(**defaults)


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("POST", "https://example.com"),
    )


def _mock_tls_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock curl_cffi response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = json.dumps(data)
    return resp


# ── Header building ──────────────────────────────────────────────────────


class TestHeaders:
    def test_rest_headers_include_api_key(self):
        client = MyTNBClient(_creds())
        headers = client._rest_transport.headers()
        assert headers["x-api-key"] == "test-api-key"
        assert headers["Authorization"] == "test-auth-token"

    def test_rest_headers_include_view_info_when_device_present(self):
        client = MyTNBClient(_creds())
        headers = client._rest_transport.headers()
        assert "ViewInfo" in headers
        view = json.loads(headers["ViewInfo"])
        assert view["DeviceToken"] == "dev-456"

    def test_rest_headers_no_view_info_without_device(self):
        client = MyTNBClient(_creds(device_info=None))
        headers = client._rest_transport.headers()
        assert "ViewInfo" not in headers

    def test_rest_headers_include_channel_api_key(self):
        client = MyTNBClient(_creds(channel_api_key="channel-jwt"))
        headers = client._rest_transport.headers()
        assert headers["ApiKey"] == "channel-jwt"

    def test_bearer_headers_override_auth(self):
        client = MyTNBClient(_creds(bearer_token="my-bearer"))
        headers = client._rest_transport.bearer_headers()
        assert headers["Authorization"] == "Bearer my-bearer"

    def test_legacy_headers_include_user_info(self):
        client = MyTNBClient(_creds())
        headers = client._legacy_transport.headers()
        assert "UserInfo" in headers
        user = json.loads(headers["UserInfo"])
        assert user["UserName"] == "test@example.com"

    def test_legacy_headers_include_secure_key(self):
        client = MyTNBClient(_creds())
        headers = client._legacy_transport.headers()
        assert headers["SecureKey"] == "test-secure-key"


# ── Base user info ────────────────────────────────────────────────────────


class TestBaseUserInfo:
    def test_builds_usr_inf(self):
        client = MyTNBClient(_creds())
        info = client._legacy_transport.base_user_info()
        assert info["eid"] == "test@example.com"
        assert info["sspuid"] == "uid-123"
        assert info["did"] == "dev-456"
        assert info["lang"] == "EN"

    def test_raises_without_user_info(self):
        client = MyTNBClient(_creds(user_info=None))
        with pytest.raises(MyTNBError, match="user_info is required"):
            client._legacy_transport.base_user_info()

    def test_empty_device_id_without_device_info(self):
        client = MyTNBClient(_creds(device_info=None))
        info = client._legacy_transport.base_user_info()
        assert info["did"] == ""


# ── REST API ──────────────────────────────────────────────────────────────


class TestRestPost:
    @pytest.mark.asyncio
    async def test_successful_post(self):
        response_data = {
            "statusDetail": {"code": "7200"},
            "content": {"result": "ok"},
        }
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                result = await client._rest_transport.post("test/endpoint", body={"a": 1})
                assert result["content"]["result"] == "ok"

    @pytest.mark.asyncio
    async def test_auth_error_raises(self):
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response({}, status_code=401),
            ):
                with pytest.raises(AuthenticationError):
                    await client._rest_transport.post("test/endpoint")

    @pytest.mark.asyncio
    async def test_rate_limit_raises(self):
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response({}, status_code=429),
            ):
                with pytest.raises(RateLimitError):
                    await client._rest_transport.post("test/endpoint")

    @pytest.mark.asyncio
    async def test_api_error_raises(self):
        response_data = {
            "statusDetail": {
                "code": "5000",
                "description": "Internal error",
            },
        }
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                with pytest.raises(APIError, match="Internal error"):
                    await client._rest_transport.post("test/endpoint")


# ── Legacy API ────────────────────────────────────────────────────────────


class TestLegacyPost:
    @pytest.mark.asyncio
    async def test_successful_legacy_post(self):
        response_data = {
            "d": {
                "isError": "false",
                "ErrorCode": "7200",
                "data": {"result": "ok"},
            }
        }
        async with MyTNBClient(_creds()) as client:
            mock_session = MagicMock()
            mock_session.post.return_value = _mock_tls_response(response_data)
            client._tls_session = mock_session

            result = await client._legacy_transport.post(
                "TestEndpoint", {"key": "value"}
            )
            assert result["data"]["result"] == "ok"

            call_kwargs = mock_session.post.call_args
            body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert "dt" in body
            assert set(body["dt"].keys()) == {"ae", "ak", "av"}

    @pytest.mark.asyncio
    async def test_legacy_api_error(self):
        response_data = {
            "d": {
                "isError": "true",
                "message": "Account not found",
                "ErrorCode": "404",
                "DisplayMessage": "Account not found",
            }
        }
        async with MyTNBClient(_creds()) as client:
            mock_session = MagicMock()
            mock_session.post.return_value = _mock_tls_response(response_data)
            client._tls_session = mock_session

            with pytest.raises(APIError, match="Account not found"):
                await client._legacy_transport.post("TestEndpoint", {})

    @pytest.mark.asyncio
    async def test_legacy_auth_error(self):
        async with MyTNBClient(_creds()) as client:
            mock_session = MagicMock()
            mock_session.post.return_value = _mock_tls_response({}, status_code=401)
            client._tls_session = mock_session

            with pytest.raises(AuthenticationError):
                await client._legacy_transport.post("TestEndpoint", {})


# ── Endpoint methods ─────────────────────────────────────────────────────


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_get_bill_eligibility(self):
        response_data = {
            "statusDetail": {"code": "7200"},
            "content": [
                {
                    "caNo": "220123456789",
                    "isOwnerAlreadyOptIn": True,
                    "isTenantAlreadyOptIn": False,
                },
            ],
        }
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                result = await client.get_bill_eligibility(
                    ["220123456789"], "uid-123"
                )
                assert len(result) == 1
                assert result[0].ca_no == "220123456789"
                assert result[0].is_owner_already_opt_in is True

    @pytest.mark.asyncio
    async def test_get_account_usage_smart(self):
        response_data = {
            "d": {
                "isError": "false",
                "ErrorCode": "7200",
                "data": {
                    "OtherUsageMetrics": {
                        "Usage": [
                            {
                                "Key": "CURRENTUSAGE",
                                "Title": "Usage",
                                "SubTitle": "",
                                "Value": "100.0",
                                "ValueUnit": "kWh",
                            }
                        ],
                        "Cost": [
                            {
                                "Key": "CURRENTCOST",
                                "Title": "Cost",
                                "SubTitle": "",
                                "Value": "50.00",
                                "ValueUnit": "RM",
                            }
                        ],
                    },
                    "DateRange": "1-15 May",
                },
            }
        }
        async with MyTNBClient(_creds()) as client:
            mock_session = MagicMock()
            mock_session.post.return_value = _mock_tls_response(response_data)
            client._tls_session = mock_session

            usage = await client.get_account_usage_smart("220123456789")
            assert usage.current_usage_kwh == 100.0
            assert usage.current_cost_rm == 50.00

    @pytest.mark.asyncio
    async def test_get_smr_accounts(self):
        response_data = {
            "d": {
                "isError": "false",
                "ErrorCode": "7200",
                "data": [
                    {
                        "ContractAccount": "220123456789",
                        "SMREligibility": "ELIGIBLE",
                        "IsTaggedSMR": "true",
                    }
                ],
            }
        }
        async with MyTNBClient(_creds()) as client:
            mock_session = MagicMock()
            mock_session.post.return_value = _mock_tls_response(response_data)
            client._tls_session = mock_session

            accounts = await client.get_smr_accounts(["220123456789"])
            assert len(accounts) == 1
            assert accounts[0].is_smart_meter is True

    @pytest.mark.asyncio
    async def test_get_customer_accounts(self):
        response_data = {
            "data": [
                {
                    "accNum": "220123456789",
                    "userAccountID": "ua-001",
                    "accDesc": "JALAN EXAMPLE 123",
                    "icNum": "900101-01-1234",
                    "amCurrentChg": 45.50,
                    "isRegistered": "True",
                    "isPaid": "False",
                    "isOwned": "True",
                    "isError": "false",
                    "message": None,
                    "accountTypeId": "1",
                    "accountStAddress": "NO 123, JALAN EXAMPLE, KL",
                    "ownerName": "AHMAD BIN ALI",
                    "accountCategoryId": "2",
                    "SmartMeterCode": "SMC001",
                    "isTaggedSMR": "true",
                    "IsHaveAccess": True,
                    "IsApplyEBilling": True,
                    "BudgetAmount": 150.00,
                    "InstallationType": "Residential",
                    "CreatedDate": "2024-01-15",
                    "BusinessArea": "KL",
                    "RateCategory": "Tariff A",
                },
                {
                    "accNum": "220987654321",
                    "userAccountID": "ua-002",
                    "isOwned": "False",
                    "isTaggedSMR": "false",
                },
            ],
        }
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                result = await client.get_customer_accounts()
                assert len(result) == 2
                assert result[0].account_number == "220123456789"
                assert result[0].owner_name == "AHMAD BIN ALI"
                assert result[0].is_smart_meter is True
                assert result[0].is_owned_bool is True
                assert result[1].account_number == "220987654321"
                assert result[1].is_smart_meter is False
                assert result[1].is_owned_bool is False

    @pytest.mark.asyncio
    async def test_get_customer_accounts_empty(self):
        response_data = {"data": []}
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                result = await client.get_customer_accounts()
                assert result == []

    @pytest.mark.asyncio
    async def test_get_current_usage(self):
        response_data = {
            "d": {
                "isError": "false",
                "ErrorCode": "7200",
                "data": {
                    "OtherUsageMetrics": {
                        "Usage": [
                            {
                                "Key": "CURRENTUSAGE",
                                "Title": "Usage",
                                "SubTitle": "",
                                "Value": "200.0",
                                "ValueUnit": "kWh",
                            }
                        ],
                        "Cost": [
                            {
                                "Key": "CURRENTCOST",
                                "Title": "Cost",
                                "SubTitle": "",
                                "Value": "75.00",
                                "ValueUnit": "RM",
                            },
                            {
                                "Key": "PROJECTEDCOST",
                                "Title": "Projected",
                                "SubTitle": "",
                                "Value": "150.00",
                                "ValueUnit": "RM",
                            },
                        ],
                    },
                    "DateRange": "1-15 May",
                },
            }
        }
        async with MyTNBClient(_creds()) as client:
            mock_session = MagicMock()
            mock_session.post.return_value = _mock_tls_response(response_data)
            client._tls_session = mock_session

            result = await client.get_current_usage("220123456789")
            assert result["current_usage_kwh"] == 200.0
            assert result["current_cost_rm"] == 75.00
            assert result["projected_cost_rm"] == 150.00
            assert result["date_range"] == "1-15 May"


# ── Context manager ──────────────────────────────────────────────────────


class TestContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with MyTNBClient(_creds()) as client:
            assert client._http_client is None  # lazy init

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        client = MyTNBClient(_creds())
        await client.close()  # no client created yet, should be fine
        await client.close()  # double close is safe


# ── Login flow ────────────────────────────────────────────────────────────


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_returns_authenticated_client(self):
        sitecore_home = _mock_response({}, 200)
        sitecore_login = httpx.Response(
            status_code=200,
            text=(
                '<form action="https://myaccount.mytnb.com.my/SSO/SSOHandler" method="POST">'
                '<input type="hidden" name="USERNAME" value="user@example.com"/>'
                '<input type="hidden" name="USERPWD" value="enc=="/>'
                '<input type="hidden" name="ACTION_KEY" value="AUTH_USER"/>'
                '</form>'
            ),
            request=httpx.Request("POST", "https://www.mytnb.com.my/api/sitecore/Account/Login"),
        )

        user_info_json = json.dumps({
            "Channel": "myTNB_API_SSP",
            "UserId": "test-uid-123",
            "UserName": "user@example.com",
            "RoleIds": [16],
        })
        jwt_payload = base64.b64encode(json.dumps({
            "UserInfo": user_info_json,
        }).encode()).decode().rstrip("=")
        jwt_header = base64.b64encode(b'{"alg":"HS512","typ":"JWT"}').decode().rstrip("=")
        fake_jwt = f"{jwt_header}.{jwt_payload}.fakesig"

        sso_response = httpx.Response(
            status_code=200,
            text="<html>Signing In...</html>",
            headers=[("set-cookie", f"TOKEN={fake_jwt}; path=/")],
            request=httpx.Request("POST", "https://myaccount.mytnb.com.my/SSO/SSOHandler"),
        )

        token_response = _mock_response({
            "content": {"accessToken": "jwt-token-abc"},
            "statusDetail": {"code": "7200"},
        })

        mock_post = AsyncMock(side_effect=[
            sitecore_login,  # Sitecore login
            sso_response,    # SSO handler
            token_response,  # GenerateAccessToken
        ])
        mock_get = AsyncMock(return_value=sitecore_home)  # Home page
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mytnb.client.auth.httpx.AsyncClient", return_value=mock_client):
            client = await MyTNBClient.login("user@example.com", "pass123")

        assert client.credentials.user_info.user_id == "test-uid-123"
        assert client.credentials.user_info.user_name == "user@example.com"
        assert client.credentials.authorization_token == "jwt-token-abc"
        assert client.credentials.api_key == DEFAULT_API_KEY
        assert client.credentials.device_info is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_login_auth_failure_no_sso_form(self):
        """Login fails when Sitecore returns no SSO form (wrong credentials)."""
        sitecore_home = _mock_response({}, 200)
        sitecore_login = httpx.Response(
            status_code=200,
            text="<html>Invalid email or password</html>",
            request=httpx.Request("POST", "https://www.mytnb.com.my/api/sitecore/Account/Login"),
        )

        mock_post = AsyncMock(return_value=sitecore_login)
        mock_get = AsyncMock(return_value=sitecore_home)
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mytnb.client.auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AuthenticationError, match="Invalid credentials"):
                await MyTNBClient.login("bad@email.com", "wrong")
