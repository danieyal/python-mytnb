"""Tests for mytnb.models data models."""

from mytnb.models import (
    AccountUsage,
    BillingMonth,
    BREligibility,
    DailyUsage,
    Metric,
    MonthlyTariffBlock,
    SMRAccount,
    TariffBlock,
)

# ── Sample API response data ─────────────────────────────────────────────

USAGE_METRIC_DATA = {
    "Key": "CURRENTUSAGE",
    "Title": "Current Usage",
    "SubTitle": "as of 15 May",
    "Value": "234.5",
    "ValueUnit": "kWh",
    "ValueIndicator": "UP",
}

COST_METRIC_DATA = {
    "Key": "CURRENTCOST",
    "Title": "Current Cost",
    "SubTitle": "as of 15 May",
    "Value": "87.60",
    "ValueUnit": "RM",
}

TARIFF_BLOCK_DATA = {
    "BlockId": "1",
    "Amount": 21.80,
    "Usage": 100.0,
    "IsBlockAvailable": True,
    "BlockPricing": "0.218",
}

DAILY_USAGE_DATA = {
    "Date": "2026-05-14",
    "Year": "2026",
    "Month": "05",
    "Day": "14",
    "Consumption": "8.5",
    "Amount": "3.20",
    "IsEstimatedReading": False,
    "IsMissingReading": False,
    "IsCurrentBillCycle": True,
    "tariffBlocks": [],
}

BILLING_MONTH_DATA = {
    "BillingNo": "001",
    "Date": "2026-04-01",
    "Year": "2026",
    "Month": "04",
    "Day": "01",
    "AmountTotal": "156.30",
    "UsageTotal": "450.0",
    "Currency": "RM",
    "UsageUnit": "kWh",
    "IsEstimatedReading": False,
    "IsUnbilled": False,
    "tariffBlocks": [
        {
            "BlockId": "1",
            "Amount": 43.60,
            "Usage": 200.0,
            "IsBlockAvailable": True,
        },
    ],
    "BillingStartDate": "2026-03-01",
    "BillingEndDate": "2026-03-31",
}

FULL_API_RESPONSE = {
    "OtherUsageMetrics": {
        "Usage": [
            USAGE_METRIC_DATA,
            {
                "Key": "AVGUSAGE",
                "Title": "Avg Usage",
                "SubTitle": "daily",
                "Value": "15.6",
                "ValueUnit": "kWh",
            },
        ],
        "Cost": [
            COST_METRIC_DATA,
            {
                "Key": "PROJECTEDCOST",
                "Title": "Projected Cost",
                "SubTitle": "end of month",
                "Value": "180.00",
                "ValueUnit": "RM",
            },
        ],
        "CurrentCycleStartDate": "2026-05-01",
    },
    "ByMonth": {
        "Range": "6 months",
        "Months": [BILLING_MONTH_DATA],
    },
    "ByDay": [
        {
            "Range": "Week 1",
            "Days": [DAILY_USAGE_DATA],
        },
    ],
    "StartDate": "2026-05-01",
    "EndDate": "2026-05-15",
    "DateRange": "1 May - 15 May 2026",
}


# ── Tests ─────────────────────────────────────────────────────────────────


class TestTariffBlock:
    def test_parse(self):
        block = TariffBlock.model_validate(TARIFF_BLOCK_DATA)
        assert block.block_id == "1"
        assert block.amount == 21.80
        assert block.usage == 100.0
        assert block.is_block_available is True
        assert block.block_pricing == "0.218"

    def test_optional_fields(self):
        block = TariffBlock.model_validate(
            {"BlockId": "2", "Amount": 0, "Usage": 0, "IsBlockAvailable": False}
        )
        assert block.peak_usage is None
        assert block.start_date is None


class TestMetric:
    def test_parse_usage(self):
        m = Metric.model_validate(USAGE_METRIC_DATA)
        assert m.key == "CURRENTUSAGE"
        assert m.value == "234.5"
        assert m.value_unit == "kWh"

    def test_numeric_value_usage(self):
        m = Metric.model_validate(USAGE_METRIC_DATA)
        assert m.numeric_value == 234.5

    def test_parse_cost(self):
        m = Metric.model_validate(COST_METRIC_DATA)
        assert m.key == "CURRENTCOST"
        assert m.value == "87.60"

    def test_numeric_value_cost(self):
        m = Metric.model_validate(COST_METRIC_DATA)
        assert m.numeric_value == 87.60

    def test_numeric_value_fallback(self):
        m = Metric.model_validate({**COST_METRIC_DATA, "Value": "--"})
        assert m.numeric_value == 0.0


class TestDailyUsage:
    def test_parse(self):
        d = DailyUsage.model_validate(DAILY_USAGE_DATA)
        assert d.date == "2026-05-14"
        assert d.year == "2026"
        assert d.day == "14"
        assert d.is_current_bill_cycle is True

    def test_properties(self):
        d = DailyUsage.model_validate(DAILY_USAGE_DATA)
        assert d.consumption_kwh == 8.5
        assert d.amount_rm == 3.20


class TestBillingMonth:
    def test_parse(self):
        m = BillingMonth.model_validate(BILLING_MONTH_DATA)
        assert m.billing_no == "001"
        assert m.year == "2026"
        assert m.month == "04"
        assert len(m.tariff_blocks) == 1

    def test_properties(self):
        m = BillingMonth.model_validate(BILLING_MONTH_DATA)
        assert m.amount_rm == 156.30
        assert m.usage_kwh == 450.0

    def test_tariff_blocks_parsed(self):
        m = BillingMonth.model_validate(BILLING_MONTH_DATA)
        block = m.tariff_blocks[0]
        assert isinstance(block, MonthlyTariffBlock)
        assert block.amount == 43.60


class TestAccountUsage:
    def test_from_api_response(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert len(usage.usage_metrics) == 2
        assert len(usage.cost_metrics) == 2
        assert usage.date_range == "1 May - 15 May 2026"

    def test_current_usage_kwh(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert usage.current_usage_kwh == 234.5

    def test_current_cost_rm(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert usage.current_cost_rm == 87.60

    def test_projected_cost_rm(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert usage.projected_cost_rm == 180.00

    def test_by_month(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert usage.by_month is not None
        assert usage.by_month.range == "6 months"
        assert len(usage.by_month.months) == 1

    def test_by_day(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert len(usage.by_day) == 1
        assert len(usage.by_day[0].days) == 1

    def test_empty_response(self):
        usage = AccountUsage.from_api_response({})
        assert usage.current_usage_kwh is None
        assert usage.current_cost_rm is None
        assert usage.projected_cost_rm is None
        assert usage.by_month is None
        assert usage.by_day == []

    def test_missing_metrics_returns_none(self):
        data = {
            "OtherUsageMetrics": {"Usage": [], "Cost": []},
        }
        usage = AccountUsage.from_api_response(data)
        assert usage.current_usage_kwh is None
        assert usage.current_cost_rm is None


class TestSMRAccount:
    def test_parse(self):
        acc = SMRAccount.model_validate(
            {
                "ContractAccount": "220123456789",
                "SMREligibility": "ELIGIBLE",
                "IsTaggedSMR": "true",
            }
        )
        assert acc.contract_account == "220123456789"
        assert acc.is_smart_meter is True

    def test_not_smart_meter(self):
        acc = SMRAccount.model_validate(
            {
                "ContractAccount": "220000000000",
                "SMREligibility": "NOT_ELIGIBLE",
                "IsTaggedSMR": "false",
            }
        )
        assert acc.is_smart_meter is False


class TestBREligibility:
    def test_parse(self):
        e = BREligibility.model_validate(
            {
                "caNo": "220123456789",
                "isOwnerOverRule": True,
                "isOwnerAlreadyOptIn": True,
                "isTenantAlreadyOptIn": False,
            }
        )
        assert e.ca_no == "220123456789"
        assert e.is_owner_already_opt_in is True
        assert e.is_tenant_already_opt_in is False

    def test_defaults(self):
        e = BREligibility.model_validate({"caNo": "123"})
        assert e.is_owner_over_rule is False
        assert e.is_owner_already_opt_in is False
