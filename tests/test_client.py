"""Tests for mytnb.client API client."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.client import MyTNBClient
from mytnb.exceptions import APIError, AuthenticationError, MyTNBError


# ── Fixtures ──────────────────────────────────────────────────────────────


def _creds(**overrides) -> Credentials:
    defaults = dict(
        api_key="test-api-key",
        authorization_token="test-auth-token",
        secure_key="test-secure-key",
        user_info=UserInfo(user_name="test@example.com", user_id="uid-123"),
        device_info=DeviceInfo(device_id="dev-456"),
    )
    defaults.update(overrides)
    return Credentials(**defaults)


def _mock_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("POST", "https://example.com"),
    )


# ── Header building ──────────────────────────────────────────────────────


class TestHeaders:
    def test_rest_headers_include_api_key(self):
        client = MyTNBClient(_creds())
        headers = client._rest_headers()
        assert headers["x-api-key"] == "test-api-key"
        assert headers["Authorization"] == "test-auth-token"

    def test_rest_headers_include_view_info_when_device_present(self):
        client = MyTNBClient(_creds())
        headers = client._rest_headers()
        assert "ViewInfo" in headers
        view = json.loads(headers["ViewInfo"])
        assert view["DeviceToken"] == "dev-456"

    def test_rest_headers_no_view_info_without_device(self):
        client = MyTNBClient(_creds(device_info=None))
        headers = client._rest_headers()
        assert "ViewInfo" not in headers

    def test_rest_headers_include_channel_api_key(self):
        client = MyTNBClient(_creds(channel_api_key="channel-jwt"))
        headers = client._rest_headers()
        assert headers["ApiKey"] == "channel-jwt"

    def test_bearer_headers_override_auth(self):
        client = MyTNBClient(_creds(bearer_token="my-bearer"))
        headers = client._bearer_headers()
        assert headers["Authorization"] == "Bearer my-bearer"

    def test_legacy_headers_include_user_info(self):
        client = MyTNBClient(_creds())
        headers = client._legacy_headers()
        assert "UserInfo" in headers
        user = json.loads(headers["UserInfo"])
        assert user["UserName"] == "test@example.com"

    def test_legacy_headers_include_secure_key(self):
        client = MyTNBClient(_creds())
        headers = client._legacy_headers()
        assert headers["SecureKey"] == "test-secure-key"


# ── Base user info ────────────────────────────────────────────────────────


class TestBaseUserInfo:
    def test_builds_usr_inf(self):
        client = MyTNBClient(_creds())
        info = client._base_user_info()
        assert info["sspuid"] == "uid-123"
        assert info["did"] == "dev-456"
        assert info["lang"] == "EN"

    def test_raises_without_user_info(self):
        client = MyTNBClient(_creds(user_info=None))
        with pytest.raises(MyTNBError, match="user_info is required"):
            client._base_user_info()

    def test_empty_device_id_without_device_info(self):
        client = MyTNBClient(_creds(device_info=None))
        info = client._base_user_info()
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
                result = await client._rest_post("test/endpoint", body={"a": 1})
                assert result["content"]["result"] == "ok"

    @pytest.mark.asyncio
    async def test_auth_error_raises(self):
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response({}, status_code=401),
            ):
                with pytest.raises(AuthenticationError):
                    await client._rest_post("test/endpoint")

    @pytest.mark.asyncio
    async def test_rate_limit_raises(self):
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response({}, status_code=429),
            ):
                from mytnb.exceptions import RateLimitError
                with pytest.raises(RateLimitError):
                    await client._rest_post("test/endpoint")

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
                    await client._rest_post("test/endpoint")


# ── Legacy API ────────────────────────────────────────────────────────────


class TestLegacyPost:
    @pytest.mark.asyncio
    async def test_successful_legacy_post(self):
        response_data = {
            "d": {
                "isError": "false",
                "data": {"result": "ok"},
            }
        }
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ) as mock_post:
                result = await client._legacy_post(
                    "TestEndpoint", {"key": "value"}
                )
                assert result["data"]["result"] == "ok"

                # Verify the body was encrypted (has dt with ae/ak/av)
                call_kwargs = mock_post.call_args
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
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                with pytest.raises(APIError, match="Account not found"):
                    await client._legacy_post("TestEndpoint", {})

    @pytest.mark.asyncio
    async def test_legacy_auth_error(self):
        async with MyTNBClient(_creds()) as client:
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response({}, status_code=401),
            ):
                with pytest.raises(AuthenticationError):
                    await client._legacy_post("TestEndpoint", {})


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
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                usage = await client.get_account_usage_smart("220123456789")
                assert usage.current_usage_kwh == 100.0
                assert usage.current_cost_rm == 50.00

    @pytest.mark.asyncio
    async def test_get_smr_accounts(self):
        response_data = {
            "d": {
                "isError": "false",
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
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
                accounts = await client.get_smr_accounts(["220123456789"])
                assert len(accounts) == 1
                assert accounts[0].is_smart_meter is True

    @pytest.mark.asyncio
    async def test_get_current_usage(self):
        response_data = {
            "d": {
                "isError": "false",
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
            with patch.object(
                client._client, "post", new_callable=AsyncMock,
                return_value=_mock_response(response_data),
            ):
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
        # After exit, client should be available (close is safe on None)

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        client = MyTNBClient(_creds())
        await client.close()  # no client created yet, should be fine
        await client.close()  # double close is safe
