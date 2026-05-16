"""Command-line interface for myTNB API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.client import MyTNBClient
from mytnb.exceptions import MyTNBError


def _load_config(path: str | None = None) -> dict:
    """Load credentials from a JSON config file.

    Searches (in order):
      1. Explicit --config path
      2. MYTNB_CONFIG env var
      3. ./mytnb.json
      4. ~/.config/mytnb/config.json
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    if env := os.environ.get("MYTNB_CONFIG"):
        candidates.append(Path(env))
    candidates.append(Path("mytnb.json"))
    candidates.append(Path.home() / ".config" / "mytnb" / "config.json")

    for p in candidates:
        if p.is_file():
            with open(p) as f:
                return json.load(f)

    return {}


def _build_credentials(cfg: dict) -> Credentials:
    """Build Credentials from a config dict."""
    user_info = None
    if "user" in cfg:
        u = cfg["user"]
        user_info = UserInfo(
            user_name=u.get("user_name", ""),
            user_id=u.get("user_id", ""),
            language=u.get("language", "EN"),
        )

    device_info = None
    if "device" in cfg:
        d = cfg["device"]
        device_info = DeviceInfo(
            device_id=d.get("device_id", ""),
            app_version=d.get("app_version", "4.0.2"),
            os_type=d.get("os_type", "2"),
        )

    return Credentials(
        api_key=cfg.get("api_key", ""),
        authorization_token=cfg.get("authorization_token", ""),
        bearer_token=cfg.get("bearer_token"),
        channel_api_key=cfg.get("channel_api_key"),
        secure_key=cfg.get("secure_key"),
        user_info=user_info,
        device_info=device_info,
    )


def _print_json(data: object) -> None:
    """Pretty-print any object as JSON."""
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    elif hasattr(data, "__dict__") and not isinstance(data, dict):
        data = data.__dict__
    print(json.dumps(data, indent=2, default=str))


async def _run(args: argparse.Namespace) -> None:
    if args.command == "init-config":
        _init_config(args)
        return

    # Determine auth method: --email/--password or config file
    email = getattr(args, "email", None) or os.environ.get("MYTNB_EMAIL")
    password = getattr(args, "password", None) or os.environ.get("MYTNB_PASSWORD")

    if email and password:
        client = await MyTNBClient.login(email, password)
    else:
        cfg = _load_config(args.config)
        if not cfg:
            print(
                "Error: No credentials. Use --email/--password or create a config file "
                "(run: mytnb init-config)",
                file=sys.stderr,
            )
            sys.exit(1)
        creds = _build_credentials(cfg)
        staging = cfg.get("staging", False)
        client = MyTNBClient(creds, use_staging_key=staging)

    async with client:
        match args.command:
            case "usage":
                result = await client.get_account_usage_smart(args.account)
                _print_json(result)

            case "current-usage":
                result = await client.get_current_usage(args.account)
                _print_json(result)

            case "smr":
                accounts = [a.strip() for a in args.accounts.split(",")]
                result = await client.get_smr_accounts(accounts)
                _print_json([r.model_dump() for r in result])

            case "services":
                result = await client.get_services()
                _print_json(result)

            case "recommendations":
                result = await client.get_energy_recommendations(args.account)
                _print_json(result)

            case "due-amount":
                result = await client.get_account_due_amount(args.account)
                _print_json(result)

            case "bill-history":
                result = await client.get_bill_history(args.account)
                _print_json(result)

            case "bill-eligibility":
                accounts = [a.strip() for a in args.accounts.split(",")]
                result = await client.get_bill_eligibility(accounts, args.user_id)
                _print_json([r.model_dump() for r in result])

            case "eligibility-icons":
                result = await client.get_eligibility_icons()
                _print_json(result)

            case "login":
                info = {
                    "user_id": client._credentials.user_info.user_id,
                    "user_name": client._credentials.user_info.user_name,
                    "authenticated": True,
                }
                _print_json(info)

            case "init-config":
                _init_config(args)
                return


def _init_config(args: argparse.Namespace) -> None:
    """Generate a starter config file."""
    target = Path(args.output or "mytnb.json")
    if target.exists():
        print(f"Error: {target} already exists", file=sys.stderr)
        sys.exit(1)

    template = {
        "api_key": "",
        "authorization_token": "",
        "secure_key": "",
        "user": {
            "user_name": "",
            "user_id": "",
            "language": "EN",
        },
        "device": {
            "device_id": "",
            "app_version": "4.0.2",
            "os_type": "2",
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w") as f:
        json.dump(template, f, indent=2)
    print(f"Config written to {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mytnb",
        description="CLI for the myTNB API (Tenaga Nasional Berhad)",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to config JSON file (default: mytnb.json or ~/.config/mytnb/config.json)",
    )
    parser.add_argument(
        "-e", "--email",
        help="myTNB account email (or set MYTNB_EMAIL env var)",
    )
    parser.add_argument(
        "-p", "--password",
        help="myTNB account password (or set MYTNB_PASSWORD env var)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ── init-config ──────────────────────────────────────────────────
    p = sub.add_parser("init-config", help="Generate a starter config file")
    p.add_argument("-o", "--output", help="Output path (default: mytnb.json)")

    # ── usage ────────────────────────────────────────────────────────
    p = sub.add_parser("usage", help="Get smart meter usage data")
    p.add_argument("account", help="Contract account number")

    # ── current-usage ────────────────────────────────────────────────
    p = sub.add_parser("current-usage", help="Get simplified current usage summary")
    p.add_argument("account", help="Contract account number")

    # ── smr ──────────────────────────────────────────────────────────
    p = sub.add_parser("smr", help="Get SMR account statuses")
    p.add_argument("accounts", help="Comma-separated account numbers")

    # ── services ─────────────────────────────────────────────────────
    sub.add_parser("services", help="Get available services")

    # ── recommendations ──────────────────────────────────────────────
    p = sub.add_parser("recommendations", help="Get energy budget recommendations")
    p.add_argument("account", help="Contract account number")

    # ── due-amount ───────────────────────────────────────────────────
    p = sub.add_parser("due-amount", help="Get account due amount")
    p.add_argument("account", help="Contract account number")

    # ── bill-history ─────────────────────────────────────────────────
    p = sub.add_parser("bill-history", help="Get bill payment history")
    p.add_argument("account", help="Contract account number")

    # ── bill-eligibility ─────────────────────────────────────────────
    p = sub.add_parser("bill-eligibility", help="Get bill rendering eligibility")
    p.add_argument("accounts", help="Comma-separated account numbers")
    p.add_argument("user_id", help="User UUID")

    # ── eligibility-icons ────────────────────────────────────────────
    sub.add_parser("eligibility-icons", help="Get eligibility feature icons")

    # ── login ────────────────────────────────────────────────────────
    sub.add_parser("login", help="Test login and show user info")

    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except MyTNBError as exc:
        label = type(exc).__name__
        code = f" [{exc.error_code}]" if exc.error_code else ""
        print(f"Error ({label}{code}): {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
