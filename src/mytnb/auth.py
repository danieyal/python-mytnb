"""Authentication handling for myTNB API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DeviceInfo:
    """Device information sent with API requests."""

    device_id: str
    app_version: str = "4.0.2"
    os_type: str = "2"  # 1=Android, 2=iOS
    os_version: str = "18.0"
    device_desc: str = "EN"
    version_code: str = "1425"

    def to_dict(self) -> dict:
        return {
            "deviceId": self.device_id,
            "appVersion": self.app_version,
            "osType": self.os_type,
            "osVersion": self.os_version,
            "deviceDesc": self.device_desc,
            "versionCode": self.version_code,
        }


@dataclass
class UserInfo:
    """User information for authenticated requests."""

    user_name: str
    user_id: str
    display_name: str = ""
    role_id: str = "16"
    language: str = "EN"

    def to_dict(self) -> dict:
        return {
            "RoleId": self.role_id,
            "UserId": self.user_id,
            "UserName": self.user_name,
            "Lang": self.language,
        }


@dataclass
class Credentials:
    """API credentials for myTNB."""

    # REST API (api.mytnb.com.my)
    api_key: str
    authorization_token: str
    # Optional bearer token for some endpoints
    bearer_token: Optional[str] = None
    # Channel API key (static JWT)
    channel_api_key: Optional[str] = None

    # Legacy API (mytnbapp.tnb.com.my)
    secure_key: Optional[str] = None

    # User context
    user_info: Optional[UserInfo] = None
    device_info: Optional[DeviceInfo] = None
