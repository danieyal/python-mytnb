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
mytnb usage <account>                        # Usage & billing data
mytnb current-usage <account>                # Simplified current usage summary
mytnb due-amount <account>                   # Outstanding balance
mytnb bill-history <account>                 # Payment history
mytnb smr <account1>,<account2>              # Smart Meter Reading status
mytnb services                               # Available services
mytnb recommendations <account>              # Energy recommendations
```

Use a config file instead of flags (`--config <path>`, `mytnb.json`, or `~/.config/mytnb/config.json`):

```bash
mytnb init-config   # Generate a starter config file
```

## API Architecture

myTNB uses two API backends, both handled transparently by this library:

| Backend     | Domain                | Auth                                        | Used for                            |
| ----------- | --------------------- | ------------------------------------------- | ----------------------------------- |
| REST        | `api.mytnb.com.my`    | JWT + API key                               | Account listing, eligibility checks |
| Legacy ASMX | `mytnbapp.tnb.com.my` | Encrypted payloads (AES-256-CBC + RSA-OAEP) | Usage data, billing, services       |

Request encryption for the ASMX API is automatic — just pass plaintext parameters.

## Data Models

| Model           | Description                                          |
| --------------- | ---------------------------------------------------- |
| `AccountUsage`  | Full usage response: metrics, monthly and daily data |
| `UsageMetric`   | Current/average usage (kWh)                          |
| `CostMetric`    | Current/projected cost (RM)                          |
| `BillingMonth`  | Monthly billing record with tariff blocks            |
| `DailyUsage`    | Daily consumption and cost                           |
| `TariffBlock`   | Tariff pricing block details                         |
| `SMRAccount`    | Smart Meter Reading eligibility status               |
| `BREligibility` | Bill rendering opt-in status                         |

## Error Handling

```python
from mytnb.exceptions import MyTNBError, APIError, AuthenticationError

try:
    client = await MyTNBClient.login("user@example.com", "password")
    async with client:
        usage = await client.get_account_usage_smart("220123456789")
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
