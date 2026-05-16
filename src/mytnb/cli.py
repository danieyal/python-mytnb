"""Command-line interface for myTNB API."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

from mytnb.auth import Credentials, DeviceInfo, UserInfo
from mytnb.client import MyTNBClient
from mytnb.exceptions import MyTNBError

console = Console()
err_console = Console(stderr=True)


# ─── Exception handling ──────────────────────────────────────────────────────


def _handle_exception(debug: bool, exc: BaseException) -> None:
    """Handle exceptions with nice output."""
    if isinstance(exc, click.ClickException):
        raise
    if isinstance(exc, click.exceptions.Exit):
        sys.exit(exc.code)
    if isinstance(exc, click.exceptions.Abort):
        sys.exit(0)

    if isinstance(exc, MyTNBError):
        code = f" [{exc.error_code}]" if exc.error_code else ""
        err_console.print(f"[bold red]Error[/] ({type(exc).__name__}{code}): {exc}")
    else:
        err_console.print(f"[bold red]Error[/]: {exc}")

    if debug:
        err_console.print_exception()
    else:
        err_console.print("[dim]Run with --debug to see the full traceback[/]")
    sys.exit(1)


class CatchAllGroup(click.Group):
    """Click Group that catches all exceptions and prints them nicely."""

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except Exception as exc:
            _handle_exception(ctx.params.get("debug", False), exc)

    def main(self, *args, **kwargs):
        try:
            return super().main(*args, **kwargs)
        except KeyboardInterrupt:
            err_console.print("\n[yellow]Aborted![/]")
            sys.exit(1)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _load_config(path: str | None = None) -> dict:
    """Load credentials from a JSON config file."""
    candidates = []
    if path:
        candidates.append(Path(path))
    if env := os.environ.get("MYTNB_CONFIG"):
        candidates.append(Path(env))
    candidates.append(Path("mytnb.json"))
    candidates.append(Path.home() / ".config" / "mytnb" / "config.json")

    for p in candidates:
        if p.is_file():
            with open(p, encoding="utf-8") as f:
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


def _to_json(data: object) -> str:
    """Serialize any object to JSON string."""
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    elif hasattr(data, "__dict__") and not isinstance(data, dict):
        data = data.__dict__
    return json.dumps(data, indent=2, default=str)


def _print_json(data: object) -> None:
    """Pretty-print any object as highlighted JSON."""
    console.print(JSON(_to_json(data)))


def _run_async(coro):
    """Run an async coroutine."""
    return asyncio.run(coro)


async def _get_client(ctx: click.Context) -> MyTNBClient:
    """Build and return a MyTNBClient from CLI context."""
    email = ctx.obj.get("email")
    password = ctx.obj.get("password")
    config_path = ctx.obj.get("config")

    if email and password:
        with console.status("[bold green]Logging in..."):
            return await MyTNBClient.login(email, password)

    cfg = _load_config(config_path)
    if not cfg:
        raise click.UsageError(
            "No credentials. Use --email/--password, set MYTNB_EMAIL/MYTNB_PASSWORD "
            "env vars, or create a config file (run: mytnb init-config)"
        )
    creds = _build_credentials(cfg)
    staging = cfg.get("staging", False)
    return MyTNBClient(creds, use_staging_key=staging)


# ─── CLI definition ─────────────────────────────────────────────────────────


@click.group(cls=CatchAllGroup)
@click.option("-c", "--config", help="Path to config JSON file.")
@click.option("-e", "--email", envvar="MYTNB_EMAIL", help="myTNB account email.")
@click.option("-p", "--password", envvar="MYTNB_PASSWORD", help="myTNB account password.")
@click.option("--debug", is_flag=True, help="Show full traceback on errors.")
@click.version_option(package_name="python-mytnb")
@click.pass_context
def cli(ctx, config, email, password, debug):
    """CLI for the myTNB API (Tenaga Nasional Berhad)."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["email"] = email
    ctx.obj["password"] = password
    ctx.obj["debug"] = debug


@cli.command()
@click.pass_context
def login(ctx):
    """Test login and show user info."""

    async def _login():
        client = await _get_client(ctx)
        async with client:
            ui = client._credentials.user_info
            table = Table(title="Login Successful", show_header=False)
            table.add_column("Field", style="bold cyan")
            table.add_column("Value")
            table.add_row("User ID", ui.user_id)
            table.add_row("Email", ui.user_name)
            table.add_row("Display Name", getattr(ui, "display_name", "") or "")
            console.print(table)

    _run_async(_login())


@cli.command()
@click.argument("account")
@click.option("--json", "as_json", is_flag=True, help="Output full JSON instead of table.")
@click.pass_context
def usage(ctx, account, as_json):
    """Get smart meter usage & billing data."""

    async def _usage():
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching usage data..."):
                result = await client.get_account_usage_smart(account)

            if as_json:
                _print_json(result)
                return

            # Show a summary table
            table = Table(title=f"Usage — {account}")
            table.add_column("Month", style="cyan")
            table.add_column("Usage (kWh)", justify="right")
            table.add_column("Amount (RM)", justify="right", style="green")

            if result.by_month:
                for m in result.by_month.months:
                    table.add_row(
                        f"{m.month} {m.year}",
                        m.usage_total or "--",
                        m.amount_total or "--",
                    )

            console.print(table)

            # Current usage metrics
            if result.usage_metrics or result.cost_metrics:
                console.print()
                for metric in result.usage_metrics:
                    if metric.value and metric.value != "--":
                        console.print(f"  [cyan]{metric.title}:[/] {metric.value} {metric.value_unit}")
                for metric in result.cost_metrics:
                    if metric.value and metric.value != "--":
                        console.print(f"  [green]{metric.title}:[/] {metric.value_unit} {metric.value}")

    _run_async(_usage())


@cli.command("current-usage")
@click.argument("account")
@click.pass_context
def current_usage(ctx, account):
    """Get simplified current usage summary."""

    async def _current():
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching..."):
                result = await client.get_current_usage(account)
            _print_json(result)

    _run_async(_current())


@cli.command("due-amount")
@click.argument("account")
@click.option("--json", "as_json", is_flag=True, help="Output full JSON.")
@click.pass_context
def due_amount(ctx, account, as_json):
    """Get account outstanding balance."""

    async def _due():
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching..."):
                result = await client.get_account_due_amount(account)

            if as_json:
                _print_json(result)
                return

            data = result.get("AccountAmountDue", result) if isinstance(result, dict) else result
            if isinstance(data, dict):
                amount = data.get("amountDue", "--")
                due_date = data.get("billDueDate", "--")
                console.print(Panel(
                    f"[bold green]RM {amount}[/]\nDue by [cyan]{due_date}[/]",
                    title=f"Due Amount — {account}",
                ))
            else:
                _print_json(result)

    _run_async(_due())


@cli.command("bill-history")
@click.argument("account")
@click.option("--json", "as_json", is_flag=True, help="Output full JSON.")
@click.pass_context
def bill_history(ctx, account, as_json):
    """Get bill payment history."""

    async def _history():
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching..."):
                result = await client.get_bill_history(account)

            if as_json:
                _print_json(result)
                return

            if isinstance(result, list):
                table = Table(title=f"Bill History — {account}")
                table.add_column("Date", style="cyan")
                table.add_column("Bill No")
                table.add_column("Amount (RM)", justify="right", style="green")
                for bill in result:
                    table.add_row(
                        bill.get("DtBill", "--"),
                        bill.get("BillingNo", "--"),
                        bill.get("AmPayable", "--"),
                    )
                console.print(table)
            else:
                _print_json(result)

    _run_async(_history())


@cli.command()
@click.argument("accounts")
@click.pass_context
def smr(ctx, accounts):
    """Get Smart Meter Reading account statuses.

    ACCOUNTS is a comma-separated list of contract account numbers.
    """

    async def _smr():
        accs = [a.strip() for a in accounts.split(",")]
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching..."):
                result = await client.get_smr_accounts(accs)
            _print_json([r.model_dump() for r in result])

    _run_async(_smr())


@cli.command()
@click.pass_context
def services(ctx):
    """Get available services."""

    async def _services():
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching..."):
                result = await client.get_services()
            _print_json(result)

    _run_async(_services())


@cli.command()
@click.argument("account")
@click.pass_context
def recommendations(ctx, account):
    """Get energy budget recommendations."""

    async def _recs():
        client = await _get_client(ctx)
        async with client:
            with console.status("[bold green]Fetching..."):
                result = await client.get_energy_recommendations(account)
            _print_json(result)

    _run_async(_recs())


@cli.command("init-config")
@click.option("-o", "--output", default="mytnb.json", help="Output path.")
def init_config(output):
    """Generate a starter config file."""
    target = Path(output)
    if target.exists():
        raise click.ClickException(f"{target} already exists")

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
    with open(target, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
    console.print(f"[green]Config written to[/] {target}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
