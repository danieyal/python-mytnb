"""Tests for mytnb.auth module."""

from mytnb.auth import Credentials, DeviceInfo, UserInfo


class TestDeviceInfo:
    def test_defaults(self):
        d = DeviceInfo(device_id="abc")
        assert d.app_version == "4.0.2"
        assert d.os_type == "2"

    def test_to_dict(self):
        d = DeviceInfo(device_id="abc")
        result = d.to_dict()
        assert result["deviceId"] == "abc"
        assert result["appVersion"] == "4.0.2"
        assert "device_id" not in result  # should use camelCase keys


class TestUserInfo:
    def test_defaults(self):
        u = UserInfo(user_name="user@example.com", user_id="uid-1")
        assert u.role_id == "16"
        assert u.language == "EN"

    def test_to_dict(self):
        u = UserInfo(user_name="user@example.com", user_id="uid-1")
        result = u.to_dict()
        assert result["UserName"] == "user@example.com"
        assert result["UserId"] == "uid-1"


class TestCredentials:
    def test_minimal(self):
        c = Credentials(api_key="key", authorization_token="token")
        assert c.api_key == "key"
        assert c.user_info is None
        assert c.device_info is None
        assert c.secure_key is None

    def test_full(self):
        c = Credentials(
            api_key="key",
            authorization_token="token",
            bearer_token="bearer",
            channel_api_key="channel",
            secure_key="secure",
            user_info=UserInfo(user_name="u", user_id="id"),
            device_info=DeviceInfo(device_id="d"),
        )
        assert c.bearer_token == "bearer"
        assert c.user_info.user_name == "u"
        assert c.device_info.device_id == "d"
