"""Tests for mytnb.models data models."""

# pylint: disable=duplicate-code

from mytnb.models import (
    AccountUsage,
    BillingMonth,
    BREligibility,
    CustomerAccount,
    DailyUsage,
    Metric,
    MonthlyTariffBlock,
    SMRAccount,
    TariffBlock,
    TariffBlockLegendGroup,
    TariffBlockLegendItem,
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
    "TariffBlocksLegend": [
        {
            "BlockId": "BLK1",
            "RGB": {"R": 102, "G": 196, "B": 183},
            "BlockRange": "1 - 200 kWh",
            "BlockPrice": "RM 0.218 / kWh",
        },
        {
            "BlockId": "BLK2",
            "RGB": {"R": 158, "G": 214, "B": 182},
            "BlockRange": "201 - 300 kWh",
            "BlockPrice": "RM 0.334 / kWh",
        },
    ],
    "TariffBlocksLegendByMonthListRP4": [
        {
            "TariffBlocksLegend": [
                {
                    "BlockId": "EnergyCharge",
                    "BlockRange": "0",
                    "BlockPrice": "RM 0.2703",
                },
                {
                    "BlockId": "CustomerCharge",
                    "BlockRange": "0",
                    "BlockPrice": "RM 10.00",
                },
            ],
        },
    ],
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

    def test_tariff_blocks_legend(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert len(usage.tariff_blocks_legend) == 2
        assert usage.tariff_blocks_legend[0].block_id == "BLK1"
        assert usage.tariff_blocks_legend[0].block_range == "1 - 200 kWh"
        assert usage.tariff_blocks_legend[0].block_price == "RM 0.218 / kWh"

    def test_tariff_blocks_legend_rp4(self):
        usage = AccountUsage.from_api_response(FULL_API_RESPONSE)
        assert len(usage.tariff_blocks_legend_rp4) == 1
        assert len(usage.tariff_blocks_legend_rp4[0].items) == 2
        assert usage.tariff_blocks_legend_rp4[0].items[0].block_id == "EnergyCharge"
        assert usage.tariff_blocks_legend_rp4[0].items[0].block_price == "RM 0.2703"

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


class TestCustomerAccount:
    """Tests for the GetAccountsV4 / GetAccount response model."""

    SAMPLE = {
        "accNum": "220123456789",
        "userAccountID": "user-abc-123",
        "accDesc": "JALAN EXAMPLE 123",
        "icNum": "900101-01-1234",
        "amCurrentChg": 45.50,
        "isRegistered": "True",
        "isPaid": "False",
        "isOwned": "True",
        "isError": "false",
        "message": None,
        "accountTypeId": "1",
        "accountStAddress": "NO 123, JALAN EXAMPLE, 50000 KL",
        "ownerName": "AHMAD BIN ALI",
        "accountCategoryId": "2",
        "SmartMeterCode": "SMC001",
        "isTaggedSMR": "true",
        "IsHaveAccess": True,
        "IsApplyEBilling": True,
        "BudgetAmount": 150.00,
        "InstallationType": "Residential",
        "CreatedDate": "2024-01-15",
        "BusinessArea": "KL",
        "RateCategory": "Tariff A",
    }

    def test_parse_full(self):
        acc = CustomerAccount.model_validate(self.SAMPLE)
        assert acc.account_number == "220123456789"
        assert acc.user_account_id == "user-abc-123"
        assert acc.account_desc == "JALAN EXAMPLE 123"
        assert acc.ic_num == "900101-01-1234"
        assert acc.current_charges == "45.5"
        assert acc.is_registered == "True"
        assert acc.is_paid == "False"
        assert acc.is_owned == "True"
        assert acc.is_error == "false"
        assert acc.message == ""
        assert acc.account_type_id == "1"
        assert acc.account_st_address == "NO 123, JALAN EXAMPLE, 50000 KL"
        assert acc.owner_name == "AHMAD BIN ALI"
        assert acc.account_category_id == "2"
        assert acc.smart_meter_code == "SMC001"
        assert acc.is_tagged_smr == "true"
        assert acc.is_have_access is True
        assert acc.is_apply_ebilling is True
        assert acc.budget_amount == "150.0"
        assert acc.installation_type == "Residential"
        assert acc.created_date == "2024-01-15"
        assert acc.business_area == "KL"
        assert acc.rate_category == "Tariff A"

    def test_is_smart_meter_true(self):
        acc = CustomerAccount.model_validate(self.SAMPLE)
        assert acc.is_smart_meter is True

    def test_is_smart_meter_false(self):
        data = {**self.SAMPLE, "isTaggedSMR": "false"}
        acc = CustomerAccount.model_validate(data)
        assert acc.is_smart_meter is False

    def test_is_smart_meter_case_insensitive(self):
        data = {**self.SAMPLE, "isTaggedSMR": "True"}
        acc = CustomerAccount.model_validate(data)
        assert acc.is_smart_meter is True

    def test_boolean_helpers(self):
        acc = CustomerAccount.model_validate(self.SAMPLE)
        assert acc.is_registered_bool is True
        assert acc.is_owned_bool is True
        assert acc.is_paid_bool is False

    def test_coerces_numeric_fields(self):
        """Fields like amCurrentChg and BudgetAmount arrive as numbers."""
        data = {**self.SAMPLE, "amCurrentChg": 0.0, "BudgetAmount": 0}
        acc = CustomerAccount.model_validate(data)
        assert acc.current_charges == "0.0"
        assert acc.budget_amount == "0"

    def test_coerces_bool_fields(self):
        """isRegistered etc arrive as string 'True'/'False'."""
        data = {**self.SAMPLE, "isRegistered": "False", "isOwned": "False"}
        acc = CustomerAccount.model_validate(data)
        assert acc.is_registered == "False"
        assert acc.is_owned == "False"

    def test_accepts_useraccount_id_camelcase(self):
        """Should accept userAccountId (lowercase 'd') as well."""
        data = {**self.SAMPLE}
        del data["userAccountID"]
        data["userAccountId"] = "ua-camel"
        acc = CustomerAccount.model_validate(data)
        assert acc.user_account_id == "ua-camel"

    def test_accepts_smartmeter_code_camelcase(self):
        """Should accept smartMeterCode (lowercase 's') as well."""
        data = {**self.SAMPLE}
        del data["SmartMeterCode"]
        data["smartMeterCode"] = "SM002"
        acc = CustomerAccount.model_validate(data)
        assert acc.smart_meter_code == "SM002"

    def test_minimal_fields(self):
        acc = CustomerAccount.model_validate({"accNum": "220000000000"})
        assert acc.account_number == "220000000000"
        assert acc.user_account_id == ""
        assert acc.owner_name == ""
        assert acc.is_smart_meter is False

    def test_ignores_extra_fields(self):
        """Extra fields from the API (unitNo, building, etc.) are ignored."""
        data = {**self.SAMPLE, "unitNo": "21-7", "building": "RESIDENSI"}
        acc = CustomerAccount.model_validate(data)
        assert acc.account_number == "220123456789"  # still parses fine

    def test_null_fields_become_empty_strings(self):
        """API sends null for optional fields like icNum, message, etc."""
        data = {
            "accNum": "220123456789",
            "icNum": None,
            "message": None,
            "accDesc": None,
            "ownerName": None,
            "accountStAddress": None,
        }
        acc = CustomerAccount.model_validate(data)
        assert acc.ic_num == ""
        assert acc.message == ""
        assert acc.account_desc == ""
        assert acc.owner_name == ""
        assert acc.account_st_address == ""


class TestTariffBlockLegendItem:
    """Tests for TariffBlockLegendItem (residential tariff rate block)."""

    def test_parse(self):
        item = TariffBlockLegendItem.model_validate({
            "BlockId": "BLK1",
            "RGB": {"R": 102, "G": 196, "B": 183},
            "BlockRange": "1 - 200 kWh",
            "BlockPrice": "RM 0.218 / kWh",
        })
        assert item.block_id == "BLK1"
        assert item.block_range == "1 - 200 kWh"
        assert item.block_price == "RM 0.218 / kWh"

    def test_ignores_extra_fields(self):
        item = TariffBlockLegendItem.model_validate({
            "BlockId": "BLK1",
            "RGB": {"R": 0, "G": 0, "B": 0},
            "BlockRange": "",
            "BlockPrice": "",
            "Month": "Jan",
        })
        assert item.block_id == "BLK1"


class TestTariffBlockLegendGroup:
    """Tests for TariffBlockLegendGroup (RP4 monthly tariff breakdown)."""

    def test_parse(self):
        group = TariffBlockLegendGroup.model_validate({
            "TariffBlocksLegend": [
                {"BlockId": "EnergyCharge", "BlockRange": "0", "BlockPrice": "RM 0.2703"},
                {"BlockId": "CustomerCharge", "BlockRange": "0", "BlockPrice": "RM 10.00"},
            ],
        })
        assert len(group.items) == 2
        assert group.items[0].block_id == "EnergyCharge"
        assert group.items[1].block_price == "RM 10.00"

    def test_empty(self):
        group = TariffBlockLegendGroup.model_validate({"TariffBlocksLegend": []})
        assert group.items == []
