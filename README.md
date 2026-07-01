[![PyPI version](https://badge.fury.io/py/python-mytnb.svg)](https://badge.fury.io/py/python-mytnb)
[![CI](https://github.com/danieyal/python-mytnb/actions/workflows/ci.yml/badge.svg)](https://github.com/danieyal/python-mytnb/actions/workflows/ci.yml)

# python-mytnb

A Python library to interface with the myTNB (Tenaga Nasional Berhad) API for electricity account management and usage monitoring in Malaysia.

## Installation

```bash
uv add python-mytnb
```

Or with pip:

```bash
pip install python-mytnb
```

## Quick Start

```python
import asyncio
from mytnb import MyTNBClient

async def main():
    client = await MyTNBClient.login("user@example.com", "your-password")

    async with client:
        # Auto-discover linked accounts
        accounts = await client.get_customer_accounts()
        for acc in accounts:
            print(f"{acc.account_number} — {acc.owner_name} (SMR: {acc.is_smart_meter})")

        # Get smart meter usage & billing history
        usage = await client.get_account_usage_smart("220123456789")

        # Monthly billing breakdown
        for month in usage.by_month.months:
            print(f"{month.month} {month.year}: {month.usage_total} kWh — RM {month.amount_total}")

        # Bill history & due amount
        history = await client.get_bill_history("220123456789")
        due = await client.get_account_due_amount("220123456789")

asyncio.run(main())
```

## CLI

The `mytnb` command-line tool requires the optional `cli` extra (it pulls in
`click` and `rich`, which the library itself does not need). If you installed
without it, `mytnb` (or `python -m mytnb`) will fail to start:

```bash
pip install "python-mytnb[cli]"
```

Pass credentials directly:

```bash
mytnb --email user@example.com --password yourpass usage 220123456789
```

Or via environment variables:

```bash
export MYTNB_EMAIL=user@example.com
export MYTNB_PASSWORD=yourpass
mytnb usage 220123456789
```

All commands:

```
mytnb login                                  # Test login, show user info
mytnb accounts                               # List all linked accounts (auto-discovery)
mytnb accounts --json                        # Account list as JSON
mytnb usage <account>                        # Monthly usage & billing summary
mytnb usage --daily <account>                # Daily usage breakdown
mytnb usage --json <account>                 # Full usage data as JSON
mytnb current-usage <account>                # Simplified current usage summary
mytnb due-amount <account>                   # Outstanding balance
mytnb bill-history <account>                 # Payment history
```

Global options: `--debug` for full tracebacks, `--version`.

Use a config file instead of flags (`--config <path>`, `mytnb.json`, or `~/.config/mytnb/config.json`):

```bash
mytnb init-config   # Generate a starter config file
```

## API Architecture

myTNB uses two API backends, both handled transparently by this library:

| Backend     | Domain                      | Auth                                        | Used for                            |
| ----------- | --------------------------- | ------------------------------------------- | ----------------------------------- |
| REST        | `api.mytnb.com.my`          | JWT + API key                               | Bill eligibility, eligibility icons |
| AWS Gateway | `api.mytnb.com.my/core/api` | Encrypted payloads (AES-256-CBC + RSA-OAEP) | Account listing (auto-discovery)    |
| Legacy ASMX | `mytnbapp.tnb.com.my`       | Encrypted payloads (AES-256-CBC + RSA-OAEP) | Usage data, billing, services       |

Request encryption for the ASMX API is automatic — just pass plaintext parameters.

## Data Models

| Model             | Description                                          |
| ----------------- | ---------------------------------------------------- |
| `CustomerAccount` | Linked account: number, owner, address, SMR status   |
| `AccountUsage`    | Full usage response: metrics, monthly and daily data |
| `UsageMetric`     | Current/average usage (kWh)                          |
| `CostMetric`      | Current/projected cost (RM)                          |
| `BillingMonth`    | Monthly billing record with tariff blocks            |
| `DailyUsage`      | Daily consumption and cost                           |
| `TariffBlock`     | Tariff pricing block details                         |
| `SMRAccount`      | Smart Meter Reading eligibility status               |
| `BREligibility`   | Bill rendering opt-in status                         |

## Geographic Restrictions

The myTNB API only accepts connections from **Malaysian IP addresses** and blocks most VPN services. If you get a `GeoBlockedError` (HTTP 403), make sure you are connecting from a Malaysian network without a VPN.

## Error Handling

```python
from mytnb.exceptions import MyTNBError, APIError, AuthenticationError, GeoBlockedError

try:
    client = await MyTNBClient.login("user@example.com", "password")
    async with client:
        usage = await client.get_account_usage_smart("220123456789")
except GeoBlockedError:
    print("Blocked — connect from a Malaysian IP without VPN")
except AuthenticationError:
    print("Invalid email or password")
except APIError as e:
    print(f"API error {e.error_code}: {e.display_message}")
except MyTNBError as e:
    print(f"Error: {e}")
```

## Development

```bash
uv sync --extra dev
uv run pytest
uv run pylint src/mytnb/
```

## License

MIT
