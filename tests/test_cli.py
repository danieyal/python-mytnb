"""Tests for mytnb.cli module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from mytnb.cli import _build_credentials, _load_config, cli, main


class TestLoadConfig:
    def test_loads_from_explicit_path(self, tmp_path):
        cfg_file = tmp_path / "test.json"
        cfg_file.write_text(json.dumps({"api_key": "from-file"}))
        result = _load_config(str(cfg_file))
        assert result["api_key"] == "from-file"

    def test_loads_from_env_var(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "env.json"
        cfg_file.write_text(json.dumps({"api_key": "from-env"}))
        monkeypatch.setenv("MYTNB_CONFIG", str(cfg_file))
        result = _load_config()
        assert result["api_key"] == "from-env"

    def test_returns_empty_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("MYTNB_CONFIG", raising=False)
        result = _load_config()
        assert result == {}


class TestBuildCredentials:
    def test_minimal_config(self):
        creds = _build_credentials({"api_key": "k", "authorization_token": "t"})
        assert creds.api_key == "k"
        assert creds.authorization_token == "t"
        assert creds.user_info is None
        assert creds.device_info is None

    def test_full_config(self):
        cfg = {
            "api_key": "k",
            "authorization_token": "t",
            "secure_key": "sk",
            "bearer_token": "bt",
            "user": {
                "user_name": "user@test.com",
                "user_id": "uid",
                "language": "BM",
            },
            "device": {
                "device_id": "did",
                "app_version": "5.0",
                "os_type": "1",
            },
        }
        creds = _build_credentials(cfg)
        assert creds.secure_key == "sk"
        assert creds.user_info.user_name == "user@test.com"
        assert creds.user_info.language == "BM"
        assert creds.device_info.device_id == "did"
        assert creds.device_info.os_type == "1"

    def test_empty_config(self):
        creds = _build_credentials({})
        assert creds.api_key == ""
        assert creds.authorization_token == ""


class TestInitConfig:
    def test_creates_config_file(self, tmp_path):
        output = tmp_path / "mytnb.json"
        with patch("sys.argv", ["mytnb", "init-config", "-o", str(output)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        assert output.exists()
        cfg = json.loads(output.read_text())
        assert "api_key" in cfg
        assert "user" in cfg
        assert "device" in cfg

    def test_refuses_overwrite(self, tmp_path):
        output = tmp_path / "mytnb.json"
        output.write_text("{}")
        with patch("sys.argv", ["mytnb", "init-config", "-o", str(output)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0


class TestAccountsCommand:
    """Tests for the `mytnb accounts` auto-discovery command."""

    def test_json_output(self, tmp_path):
        """Test accounts --json produces valid JSON."""
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "api_key": "k",
            "authorization_token": "t",
            "secure_key": "sk",
            "user": {"user_name": "u@t.com", "user_id": "uid"},
            "device": {"device_id": "did"},
        }))

        from mytnb.models import CustomerAccount
        sample_acc = CustomerAccount.model_validate({"accNum": "220123456789"})
        mock_client = MagicMock()
        mock_client.get_customer_accounts = AsyncMock(return_value=[sample_acc])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("mytnb.cli._get_client", AsyncMock(return_value=mock_client)):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["-c", str(cfg_file), "accounts", "--json"],
            )
            assert result.exit_code == 0

    def test_no_accounts(self, tmp_path):
        """Test accounts shows empty message when no linked accounts."""
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "api_key": "k",
            "authorization_token": "t",
            "secure_key": "sk",
            "user": {"user_name": "u@t.com", "user_id": "uid"},
            "device": {"device_id": "did"},
        }))

        mock_client = MagicMock()
        mock_client.get_customer_accounts = AsyncMock(return_value=[])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("mytnb.cli._get_client", AsyncMock(return_value=mock_client)):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["-c", str(cfg_file), "accounts"],
            )
            assert result.exit_code == 0
            assert "No linked accounts" in result.output
