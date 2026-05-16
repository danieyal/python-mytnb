# python-mytnb

A Python library to interface with the myTNB (Tenaga Nasional Berhad) API for electricity usage monitoring in Malaysia.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
import asyncio
from mytnb import MyTNBClient

async def main():
    # Login with email and password
    client = await MyTNBClient.login("user@example.com", "your-password")

    async with client:
        # Smart meter usage (auto-encrypted)
        usage = await client.get_account_usage_smart("220123456789")
        print(f"Current usage: {usage.current_usage_kwh} kWh")
        print(f"Current cost: RM {usage.current_cost_rm}")
        print(f"Projected cost: RM {usage.projected_cost_rm}")

        # Monthly billing history
        if usage.by_month:
            for month in usage.by_month.months:
                print(f"  {month.month} {month.year}: {month.usage_kwh} kWh = RM {month.amount_rm}")

        # Bill payment history
        history = await client.get_bill_history("220123456789")

        # Due amount
        due = await client.get_account_due_amount("220123456789")

asyncio.run(main())
```

## CLI

The easiest way is to pass your myTNB credentials directly:

```bash
python -m mytnb --email user@example.com --password yourpass usage 220123456789
python -m mytnb -e user@example.com -p yourpass current-usage 220123456789
```

Or set environment variables:

```bash
export MYTNB_EMAIL=user@example.com
export MYTNB_PASSWORD=yourpass
python -m mytnb usage 220123456789
```

All commands:

```bash
python -m mytnb login                              # Test login, show user info
python -m mytnb usage 220123456789                  # Smart meter usage data
python -m mytnb current-usage 220123456789           # Simplified usage summary
python -m mytnb due-amount 220123456789              # Account due amount
python -m mytnb bill-history 220123456789            # Bill payment history
python -m mytnb smr 220123456789,220987654321        # SMR account statuses
python -m mytnb services                             # Available services
python -m mytnb recommendations 220123456789         # Energy recommendations
```

Alternatively, use a config file (`--config <path>`, `mytnb.json`, or `~/.config/mytnb/config.json`):

```bash
python -m mytnb init-config   # Generate a starter config file
```

## API Architecture

The myTNB app uses two API backends:

### REST API (`api.mytnb.com.my`)

Modern REST endpoints authenticated with JWT tokens and an API key. Used for:

- Bill rendering eligibility
- Eligibility/feature icons
- MyHome draft applications

### Legacy ASMX API (`mytnbapp.tnb.com.my`)

ASP.NET web service with encrypted request payloads (AES-256-CBC + RSA-OAEP).
Encryption is handled automatically — just pass plaintext parameters.

Used for:

- Smart meter usage data (`GetAccountUsageSmart`)
- SMR account status (`GetAccountsSMRIcon`)
- Available services (`GetServicesV4`)
- Energy recommendations (`GetUserEBRecommendations`)
- Account due amount (`GetAccountDueAmount`)
- Bill history (`GetBillHistory`)

## Data Models

| Model           | Description                                                          |
| --------------- | -------------------------------------------------------------------- |
| `AccountUsage`  | Full smart meter usage response with metrics, monthly and daily data |
| `UsageMetric`   | Current/average usage in kWh                                         |
| `CostMetric`    | Current/projected cost in RM                                         |
| `BillingMonth`  | Monthly billing record with tariff blocks                            |
| `DailyUsage`    | Daily consumption and cost data                                      |
| `TariffBlock`   | Tariff pricing block details                                         |
| `SMRAccount`    | Smart Meter Reading eligibility status                               |
| `BREligibility` | Bill rendering opt-in status                                         |

## Authentication

The REST API uses:

- `x-api-key` — API gateway key
- `Authorization` — JWT token (with user claims)
- `ApiKey` header — Channel authentication JWT
- `Bearer` token — For some endpoints

The legacy API requires a `SecureKey` header and user info. Request payloads
are automatically encrypted using the embedded RSA public key.

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

## License

MIT
