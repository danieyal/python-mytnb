"""Data models for myTNB API responses."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator


class TariffBlock(BaseModel):
    """A tariff block within a billing period."""

    block_id: str = Field(alias="BlockId")
    amount: float = Field(alias="Amount")
    usage: float = Field(alias="Usage")
    is_block_available: bool = Field(alias="IsBlockAvailable")
    block_pricing: Optional[str] = Field(default=None, alias="BlockPricing")
    peak_usage: Optional[str] = Field(default=None, alias="PeakUsage")
    off_peak_usage: Optional[str] = Field(default=None, alias="OffPeakUsage")
    start_date: Optional[str] = Field(default=None, alias="StartDate")
    end_date: Optional[str] = Field(default=None, alias="EndDate")

    model_config = {"populate_by_name": True}


class Metric(BaseModel):
    """A usage or cost metric returned by the myTNB API."""

    key: str = Field(alias="Key")
    title: str = Field(alias="Title")
    sub_title: str = Field(alias="SubTitle")
    value: str = Field(alias="Value")
    value_unit: str = Field(alias="ValueUnit")
    value_indicator: str = Field(default="", alias="ValueIndicator")

    model_config = {"populate_by_name": True}

    @property
    def numeric_value(self) -> float:
        try:
            return float(self.value)
        except (ValueError, TypeError):
            return 0.0


UsageMetric = Metric  # backward-compatible alias
CostMetric = Metric  # backward-compatible alias


class DailyUsage(BaseModel):
    """Daily electricity usage data."""

    date: str = Field(alias="Date")
    year: str = Field(alias="Year")
    month: str = Field(alias="Month")
    day: str = Field(alias="Day")
    consumption: str = Field(alias="Consumption")
    amount: str = Field(alias="Amount")
    is_estimated_reading: bool = Field(default=False, alias="IsEstimatedReading")
    is_missing_reading: bool = Field(default=False, alias="IsMissingReading")
    is_current_bill_cycle: bool = Field(default=False, alias="IsCurrentBillCycle")
    tariff_blocks: list[TariffBlock] = Field(default_factory=list, alias="tariffBlocks")

    model_config = {"populate_by_name": True}

    @property
    def consumption_kwh(self) -> float:
        return float(self.consumption)

    @property
    def amount_rm(self) -> float:
        return float(self.amount)


class DailyUsageWeek(BaseModel):
    """A week range of daily usage data."""

    range: str = Field(alias="Range")
    days: list[DailyUsage] = Field(default_factory=list, alias="Days")

    model_config = {"populate_by_name": True}


class RP4Usage(BaseModel):
    """RP4 tariff usage breakdown."""

    block_id: str = Field(alias="BlockId")
    amount: str = Field(alias="Amount")
    usage: str = Field(alias="Usage")
    is_block_available: bool = Field(default=False, alias="IsBlockAvailable")
    peak_usage: Optional[str] = Field(default=None, alias="PeakUsage")
    off_peak_usage: Optional[str] = Field(default=None, alias="OffPeakUsage")
    start_date: Optional[str] = Field(default=None, alias="StartDate")
    end_date: Optional[str] = Field(default=None, alias="EndDate")

    model_config = {"populate_by_name": True}


class MonthlyTariffBlock(BaseModel):
    """Tariff block for monthly billing."""

    block_id: str = Field(alias="BlockId")
    amount: float = Field(alias="Amount")
    usage: float = Field(alias="Usage")
    is_block_available: bool = Field(alias="IsBlockAvailable")
    block_pricing: Optional[str] = Field(default=None, alias="BlockPricing")
    rp4_usage: Optional[list[RP4Usage]] = Field(default=None, alias="RP4Usage")

    model_config = {"populate_by_name": True}


class BillingMonth(BaseModel):
    """Monthly billing data."""

    billing_no: Optional[str] = Field(default=None, alias="BillingNo")
    date: str = Field(alias="Date")
    year: str = Field(alias="Year")
    month: str = Field(alias="Month")
    day: str = Field(alias="Day")
    amount_total: str = Field(alias="AmountTotal")
    usage_total: str = Field(alias="UsageTotal")
    currency: str = Field(default="RM", alias="Currency")
    usage_unit: str = Field(default="kWh", alias="UsageUnit")
    is_estimated_reading: bool = Field(default=False, alias="IsEstimatedReading")
    is_unbilled: bool = Field(default=False, alias="IsUnbilled")
    tariff_blocks: list[MonthlyTariffBlock] = Field(
        default_factory=list, alias="tariffBlocks"
    )
    billing_start_date: Optional[str] = Field(default=None, alias="BillingStartDate")
    billing_end_date: Optional[str] = Field(default=None, alias="BillingEndDate")
    has_periodic_billing: bool = Field(default=False, alias="HasPeriodicBilling")

    model_config = {"populate_by_name": True}

    @property
    def amount_rm(self) -> float:
        return float(self.amount_total)

    @property
    def usage_kwh(self) -> float:
        return float(self.usage_total)


class ByMonthData(BaseModel):
    """Monthly billing history."""

    range: str = Field(alias="Range")
    months: list[BillingMonth] = Field(default_factory=list, alias="Months")

    model_config = {"populate_by_name": True}


class TariffBlockLegendItem(BaseModel):
    """A single tariff rate block in the legend (e.g. BLK1: RM 0.218/kWh)."""

    block_id: str = Field(alias="BlockId")
    block_range: str = Field(default="", alias="BlockRange")
    block_price: str = Field(default="", alias="BlockPrice")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class TariffBlockLegendGroup(BaseModel):
    """A monthly group of RP4 tariff legend items."""

    items: list[TariffBlockLegendItem] = Field(
        default_factory=list, alias="TariffBlocksLegend"
    )

    model_config = {"populate_by_name": True, "extra": "ignore"}


class AccountUsage(BaseModel):
    """Full account usage response from GetAccountUsageSmart."""

    usage_metrics: list[Metric] = Field(default_factory=list)
    cost_metrics: list[Metric] = Field(default_factory=list)
    current_cycle_start_date: Optional[str] = None
    by_month: Optional[ByMonthData] = None
    by_day: list[DailyUsageWeek] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    date_range: Optional[str] = None
    tariff_blocks_legend: list[TariffBlockLegendItem] = Field(default_factory=list)
    tariff_blocks_legend_rp4: list[TariffBlockLegendGroup] = Field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict) -> "AccountUsage":
        """Parse the API response data into an AccountUsage model."""
        other_usage = data.get("OtherUsageMetrics", {})
        usage_list = other_usage.get("Usage", [])
        cost_list = other_usage.get("Cost", [])

        usage_metrics = [Metric.model_validate(u) for u in usage_list]
        cost_metrics = [Metric.model_validate(c) for c in cost_list]

        by_month_raw = data.get("ByMonth")
        by_month = ByMonthData.model_validate(by_month_raw) if by_month_raw else None

        by_day_raw = data.get("ByDay", [])
        by_day = [DailyUsageWeek.model_validate(w) for w in by_day_raw]

        # Tariff block legends (residential)
        legend_raw = data.get("TariffBlocksLegend", [])
        tariff_blocks_legend = [
            TariffBlockLegendItem.model_validate(item) for item in legend_raw
        ]

        # Tariff block legends by month (RP4 commercial)
        rp4_raw = data.get("TariffBlocksLegendByMonthListRP4", [])
        tariff_blocks_legend_rp4 = [
            TariffBlockLegendGroup.model_validate(group) for group in rp4_raw
        ]

        return cls(
            usage_metrics=usage_metrics,
            cost_metrics=cost_metrics,
            current_cycle_start_date=other_usage.get("CurrentCycleStartDate"),
            by_month=by_month,
            by_day=by_day,
            start_date=data.get("StartDate"),
            end_date=data.get("EndDate"),
            date_range=data.get("DateRange"),
            tariff_blocks_legend=tariff_blocks_legend,
            tariff_blocks_legend_rp4=tariff_blocks_legend_rp4,
        )

    @property
    def current_usage_kwh(self) -> Optional[float]:
        for m in self.usage_metrics:
            if m.key == "CURRENTUSAGE":
                return m.numeric_value
        return None

    @property
    def current_cost_rm(self) -> Optional[float]:
        for m in self.cost_metrics:
            if m.key == "CURRENTCOST":
                return m.numeric_value
        return None

    @property
    def projected_cost_rm(self) -> Optional[float]:
        for m in self.cost_metrics:
            if m.key == "PROJECTEDCOST":
                return m.numeric_value
        return None


class SMRAccount(BaseModel):
    """Smart Meter Reading account status."""

    contract_account: str = Field(alias="ContractAccount")
    smr_eligibility: str = Field(alias="SMREligibility")
    is_tagged_smr: str = Field(alias="IsTaggedSMR")

    model_config = {"populate_by_name": True}

    @property
    def is_smart_meter(self) -> bool:
        return self.is_tagged_smr.lower() == "true"  # pylint: disable=no-member


class BREligibility(BaseModel):
    """Bill Rendering eligibility indicator."""

    ca_no: str = Field(alias="caNo")
    is_owner_over_rule: bool = Field(default=False, alias="isOwnerOverRule")
    is_owner_already_opt_in: bool = Field(default=False, alias="isOwnerAlreadyOptIn")
    is_tenant_already_opt_in: bool = Field(default=False, alias="isTenantAlreadyOptIn")

    model_config = {"populate_by_name": True}


class CustomerAccount(BaseModel):
    """A linked/customer account returned by the account auto-discovery endpoint.

    Uses GET /v3/account/GetAccount via the AWS API gateway.
    Returns all accounts linked to the current user without needing
    to know account numbers ahead of time.
    """

    account_number: str = Field(alias="accNum")
    user_account_id: str = Field(
        default="",
        validation_alias=AliasChoices("userAccountId", "userAccountID"),
    )
    account_desc: str = Field(default="", alias="accDesc")
    ic_num: str = Field(default="", alias="icNum")
    current_charges: str = Field(default="", alias="amCurrentChg")
    is_registered: str = Field(default="", alias="isRegistered")
    is_paid: str = Field(default="", alias="isPaid")
    is_owned: str = Field(default="", alias="isOwned")
    is_error: str = Field(default="", alias="isError")
    message: Optional[str] = Field(default=None, alias="message")
    account_type_id: str = Field(default="", alias="accountTypeId")
    account_st_address: str = Field(default="", alias="accountStAddress")
    owner_name: str = Field(default="", alias="ownerName")
    account_category_id: str = Field(default="", alias="accountCategoryId")
    smart_meter_code: str = Field(
        default="",
        validation_alias=AliasChoices("smartMeterCode", "SmartMeterCode"),
    )
    is_tagged_smr: str = Field(default="", alias="isTaggedSMR")
    is_have_access: bool = Field(default=False, alias="IsHaveAccess")
    is_apply_ebilling: bool = Field(default=False, alias="IsApplyEBilling")
    budget_amount: str = Field(default="", alias="BudgetAmount")
    installation_type: str = Field(default="", alias="InstallationType")
    created_date: str = Field(default="", alias="CreatedDate")
    business_area: str = Field(default="", alias="BusinessArea")
    rate_category: str = Field(default="", alias="RateCategory")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    # -- Coerce fields that can arrive as null, numbers, or string bools --

    @field_validator(
        "account_desc",
        "ic_num",
        "current_charges",
        "budget_amount",
        "account_type_id",
        "account_st_address",
        "owner_name",
        "account_category_id",
        "smart_meter_code",
        "installation_type",
        "created_date",
        "business_area",
        "rate_category",
        "message",
        "is_registered",
        "is_paid",
        "is_owned",
        "is_error",
        "is_tagged_smr",
        mode="before",
    )
    @classmethod
    def _coerce_to_str(cls, v: Any) -> str:
        """Normalise values that may arrive as null, int, float, or bool."""
        if v is None:
            return ""
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, (int, float)):
            return str(v)
        return str(v)

    # -- Helpers ----------------------------------------------------------

    @property
    def is_smart_meter(self) -> bool:
        """Whether this account has a smart meter."""
        # pylint: disable=no-member
        return self.is_tagged_smr.lower() == "true"

    @property
    def is_registered_bool(self) -> bool:
        """isRegistered as a boolean."""
        # pylint: disable=no-member
        return self.is_registered.lower() == "true"

    @property
    def is_owned_bool(self) -> bool:
        """isOwned as a boolean."""
        # pylint: disable=no-member
        return self.is_owned.lower() == "true"

    @property
    def is_paid_bool(self) -> bool:
        """isPaid as a boolean."""
        # pylint: disable=no-member
        return self.is_paid.lower() == "true"
