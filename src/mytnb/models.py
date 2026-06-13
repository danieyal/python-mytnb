"""Data models for myTNB API responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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


class UsageMetric(BaseModel):
    """A usage metric (current usage, average usage)."""

    key: str = Field(alias="Key")
    title: str = Field(alias="Title")
    sub_title: str = Field(alias="SubTitle")
    value: str = Field(alias="Value")
    value_unit: str = Field(alias="ValueUnit")
    value_indicator: str = Field(default="", alias="ValueIndicator")

    model_config = {"populate_by_name": True}

    @property
    def numeric_value(self) -> float:
        return float(self.value)


class CostMetric(BaseModel):
    """A cost metric (current cost, projected cost)."""

    key: str = Field(alias="Key")
    title: str = Field(alias="Title")
    sub_title: str = Field(alias="SubTitle")
    value: str = Field(alias="Value")
    value_unit: str = Field(alias="ValueUnit")
    value_indicator: str = Field(default="", alias="ValueIndicator")

    model_config = {"populate_by_name": True}

    @property
    def numeric_value(self) -> float:
        return float(self.value)


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


class AccountUsage(BaseModel):
    """Full account usage response from GetAccountUsageSmart."""

    usage_metrics: list[UsageMetric] = Field(default_factory=list)
    cost_metrics: list[CostMetric] = Field(default_factory=list)
    current_cycle_start_date: Optional[str] = None
    by_month: Optional[ByMonthData] = None
    by_day: list[DailyUsageWeek] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    date_range: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict) -> "AccountUsage":
        """Parse the API response data into an AccountUsage model."""
        other_usage = data.get("OtherUsageMetrics", {})
        usage_list = other_usage.get("Usage", [])
        cost_list = other_usage.get("Cost", [])

        usage_metrics = [UsageMetric.model_validate(u) for u in usage_list]
        cost_metrics = [CostMetric.model_validate(c) for c in cost_list]

        by_month_raw = data.get("ByMonth")
        by_month = ByMonthData.model_validate(by_month_raw) if by_month_raw else None

        by_day_raw = data.get("ByDay", [])
        by_day = [DailyUsageWeek.model_validate(w) for w in by_day_raw]

        return cls(
            usage_metrics=usage_metrics,
            cost_metrics=cost_metrics,
            current_cycle_start_date=other_usage.get("CurrentCycleStartDate"),
            by_month=by_month,
            by_day=by_day,
            start_date=data.get("StartDate"),
            end_date=data.get("EndDate"),
            date_range=data.get("DateRange"),
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
