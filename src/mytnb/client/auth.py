"""Authentication login flow for myTNB."""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from typing import TYPE_CHECKING

import httpx

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.client.config import (
    DEFAULT_API_KEY,
    REST_BASE_URL,
    SITECORE_LOGIN_URL,
    SSO_HANDLER_URL,
    USER_AGENT,
)
from mytnb.exceptions import AuthenticationError, GeoBlockedError

if TYPE_CHECKING:
    from mytnb.client.client import MyTNBClient

logger = logging.getLogger(__name__)


async def login(
    cls: type[MyTNBClient],
    email: str,
    password: str,
    *,
    device_id: str | None = None,
    timeout: float = 30.0,
    use_staging_key: bool = False,
) -> MyTNBClient:
    """Authenticate with email and password, returning a ready-to-use client.

    Performs the full login flow:
    1. Authenticate via Sitecore web login (plaintext credentials)
    2. Submit SSO form to get user identity (userId)
    3. Generate an access token via the REST Identity API
    """
    if not device_id:
        device_id = str(uuid.uuid4()).upper()

    device_info = DeviceInfo(device_id=device_id)

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as http:
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
        logger.info("Sitecore login response: %s", login_resp.status_code)

        if login_resp.status_code == 403:
            raise GeoBlockedError()
        if login_resp.status_code != 200:
            raise AuthenticationError(
                "Login failed",
                error_code=str(login_resp.status_code),
            )

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
