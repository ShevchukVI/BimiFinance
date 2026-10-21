"""Request schemas for the housing («Житло») API.

Dates are accepted as 'YYYY-MM-DD' strings (periods as 'YYYY-MM' or 'YYYY-MM-DD'):
pydantic 2.13.4 rejects every value for `Optional[date] = None` (see schemas.TransactionUpdate).
"""
from typing import List, Optional

from pydantic import BaseModel, Field

MODES = {"rent", "mortgage", "own", "off"}
HEATING = {"electric", "gas", "central", "other", "none"}
SERVICES = {"electricity", "gas", "gas_delivery", "water", "heating", "maintenance", "waste",
            "internet", "rent", "mortgage", "other"}
BILLING = {"metered", "fixed", "manual"}


class ProfileIn(BaseModel):
    mode: Optional[str] = None
    title: Optional[str] = None
    area_m2: Optional[float] = None
    heating: Optional[str] = None
    svitlobot_channel: Optional[str] = None
    readings_day: Optional[int] = Field(None, ge=1, le=28)
    reminders_enabled: Optional[bool] = None


class SetupIn(BaseModel):
    mode: str = "rent"
    templates: List[str] = []
    rent_amount: Optional[float] = None
    rent_day: Optional[int] = Field(None, ge=1, le=31)
    area_m2: Optional[float] = None
    heating: Optional[str] = None
    svitlobot_channel: Optional[str] = None


class ProviderIn(BaseModel):
    name: Optional[str] = None
    service: Optional[str] = None
    icon: Optional[str] = None
    billing: Optional[str] = None
    fixed_amount: Optional[float] = None
    due_day: Optional[int] = Field(None, ge=1, le=31)
    account_number: Optional[str] = None
    pay_url: Optional[str] = None
    start_date: Optional[str] = None
    opening_balance: Optional[float] = None
    note: Optional[str] = None
    match_pattern: Optional[str] = None  # bank description for auto-linking payments
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class MeterIn(BaseModel):
    name: Optional[str] = None
    utility_type: Optional[str] = None
    unit: Optional[str] = None
    tariff: Optional[float] = None
    provider_id: Optional[int] = None
    zone: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ReadingItem(BaseModel):
    meter_id: int
    value: float


class ReadingsIn(BaseModel):
    date: Optional[str] = None  # default: today (Kyiv)
    items: List[ReadingItem]
    note: str = ""
    allow_decrease: bool = False  # meter replaced / corrected


class BillLineIn(BaseModel):
    meter_id: Optional[int] = None
    label: str = ""
    prev_value: Optional[float] = None
    curr_value: Optional[float] = None
    volume: Optional[float] = None
    tariff: Optional[float] = None
    amount: Optional[float] = None


class BillIn(BaseModel):
    provider_id: int
    period: str
    issued_on: Optional[str] = None
    opening_balance: float = 0.0
    paid: float = 0.0
    accrued: float = 0.0
    adjustment: float = 0.0
    to_pay: Optional[float] = None  # default: computed
    consumption: Optional[float] = None
    note: str = ""
    lines: List[BillLineIn] = []
    save_readings: bool = True  # store billed meter values as readings (source='bill')


class PaymentIn(BaseModel):
    provider_id: int
    amount: float
    date: Optional[str] = None
    note: str = ""
    create_transaction: bool = False  # also write an expense into finances
    account: str = "Готівка"


class NoteIn(BaseModel):
    date: Optional[str] = None
    end_date: Optional[str] = None
    kind: str = "note"
    text: str = ""
    provider_id: Optional[int] = None


class HeatingIn(BaseModel):
    on: bool
    date: Optional[str] = None


class ReminderAck(BaseModel):
    items: List[dict]  # [{family_id, key}]
