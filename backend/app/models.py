from sqlalchemy import (BigInteger, LargeBinary, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import relationship
from app.database import Base


class Family(Base):
    __tablename__ = "families"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    invite_code = Column(String, unique=True, index=True, nullable=False)
    smart_auto = Column(Boolean, nullable=False, default=True)  # «Bimi розкладає сам» new bank operations it is sure about

    memberships = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan")
    users = relationship("User", secondary="family_members", back_populates="families", viewonly=True)
    categories = relationship("Category", back_populates="family")
    transactions = relationship("Transaction", back_populates="family")
    jars = relationship("Jar", back_populates="family")
    notes = relationship("Note", back_populates="family")


class FamilyMember(Base):
    __tablename__ = "family_members"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), primary_key=True)
    role = Column(String, nullable=False, default="member")

    user = relationship("User", back_populates="memberships", overlaps="families,memberships,user")
    family = relationship("Family", back_populates="memberships", overlaps="families,memberships,family")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)
    mono_token = Column(String, nullable=True)
    tab_prefs = Column(String, nullable=True)  # JSON {"auto": false, "housing": true} — personal bottom-bar tabs
    current_active_family_id = Column(Integer, ForeignKey("families.id"), nullable=True)

    memberships = relationship("FamilyMember", back_populates="user", cascade="all, delete-orphan")
    families = relationship("Family", secondary="family_members", back_populates="users", viewonly=True, overlaps="families,memberships")
    transactions = relationship("Transaction", back_populates="user")
    bank_accounts = relationship("BankAccount", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    icon = Column(String, nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, nullable=False)
    type = Column(String, nullable=False)
    family = relationship("Family", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    category_id = Column(Integer, ForeignKey("categories.id"))
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    note = Column(String, default="")
    account = Column(String, nullable=False)
    mono_id = Column(String, unique=True, nullable=True, index=True)
    date = Column(Date, nullable=False)
    currency = Column(String, default="UAH", nullable=False)  # UAH/USD/EUR...
    jar_id = Column(Integer, ForeignKey("jars.id"), nullable=True)  # deposit/withdrawal to/from jar
    obligation_id = Column(Integer, ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True)  # credit/subscription payment
    auto_category = Column(Boolean, nullable=False, default=False)  # 🤖 categorised by Bimi, not yet touched by a person
    mcc = Column(Integer, nullable=True)  # Monobank merchant category code (5541 АЗС, 4111 транспорт…) — a hint for categories
    family = relationship("Family", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    jar = relationship("Jar", back_populates="transactions")


class Jar(Base):
    __tablename__ = "jars"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    name = Column(String, nullable=False)
    # balance — зберігаємо фізично для зворотної сумісності, але НЕ використовуємо
    # для розрахунків. Баланс скарбнички тепер ДИНАМІЧНИЙ:
    #   SUM(amount) транзакцій з jar_id = this.id (поповнення +, зняття -).
    balance = Column(Float, default=0.0)
    goal = Column(Float, nullable=False)
    currency = Column(String, default="UAH", nullable=False)
    # Monobank «банка»: balance comes from the bank, history = transfers to/from it
    mono_jar_id = Column(String, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # whose Monobank
    bank_balance = Column(Float, nullable=True)
    synced_at = Column(DateTime, nullable=True)
    family = relationship("Family", back_populates="jars")
    transactions = relationship("Transaction", back_populates="jar")


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    content = Column(Text, nullable=False)
    family = relationship("Family", back_populates="notes")


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False, default="monobank")
    external_account_id = Column(String, nullable=False)
    name = Column(String, nullable=True)

    user = relationship("User", back_populates="bank_accounts")


# ============================================================================
# Housing («Житло»): profile, providers (utilities / rent / mortgage), meters,
# readings, bills (with lines), payments, notes, power outages, reminder log.
# Money convention: positive balance = debt (треба доплатити), negative = overpay.
# ============================================================================

class HousingProfile(Base):
    __tablename__ = "housing_profiles"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, unique=True)
    mode = Column(String, nullable=False, default="rent")  # rent | mortgage | own | off
    title = Column(String, default="")  # e.g. "Квартира"
    area_m2 = Column(Float, nullable=True)
    heating = Column(String, default="electric")  # electric | gas | central | other | none
    svitlobot_channel = Column(String, nullable=True)  # public t.me channel of a svitlobot
    readings_day = Column(Integer, default=1)  # day of month to submit meter readings
    reminders_enabled = Column(Boolean, default=True, nullable=False)


class UtilityProvider(Base):
    __tablename__ = "utility_providers"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    name = Column(String, nullable=False)  # "ONDO", "Нафтогаз", "Оренда"
    service = Column(String, nullable=False)  # electricity|gas|gas_delivery|water|heating|maintenance|waste|internet|rent|mortgage|other
    icon = Column(String, default="")
    billing = Column(String, nullable=False, default="metered")  # metered | fixed | manual
    fixed_amount = Column(Float, nullable=True)  # monthly charge for fixed billing (rent, maintenance, waste)
    due_day = Column(Integer, nullable=True)  # pay-by day of month
    account_number = Column(String, default="")  # особовий рахунок
    pay_url = Column(String, default="")
    start_date = Column(Date, nullable=True)  # ledger start for providers without bills
    opening_balance = Column(Float, default=0.0)  # debt at start_date (+ debt, - overpay)
    note = Column(String, default="")
    match_pattern = Column(String, default="")  # how payments look in the bank («Електроенергія|ONDO»)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)

    meters = relationship("UtilityMeter", back_populates="provider")
    bills = relationship("UtilityBill", back_populates="provider", cascade="all, delete-orphan")
    payments = relationship("UtilityPayment", back_populates="provider", cascade="all, delete-orphan")


class UtilityMeter(Base):
    __tablename__ = "utility_meters"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    name = Column(String, nullable=False)
    utility_type = Column(String, nullable=False)  # electricity, gas, water, heating
    unit = Column(String, nullable=False)  # кВт·год, м³
    tariff = Column(Float, default=0.0)  # current price per unit
    provider_id = Column(Integer, ForeignKey("utility_providers.id"), nullable=True)
    zone = Column(String, nullable=True)  # day | night | None (single-zone)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)

    family = relationship("Family")
    provider = relationship("UtilityProvider", back_populates="meters")
    readings = relationship("UtilityReading", back_populates="meter", cascade="all, delete-orphan")


class UtilityReading(Base):
    __tablename__ = "utility_readings"
    id = Column(Integer, primary_key=True)
    meter_id = Column(Integer, ForeignKey("utility_meters.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.0)  # legacy, unused
    note = Column(String, default="")
    source = Column(String, default="manual")  # manual | bill | import
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    meter = relationship("UtilityMeter", back_populates="readings")


class UtilityBill(Base):
    """One monthly bill (платіжка) of a provider. to_pay = opening - paid + accrued + adjustment."""
    __tablename__ = "utility_bills"
    __table_args__ = (UniqueConstraint("provider_id", "period", name="uq_bill_provider_period"),)
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("utility_providers.id"), nullable=False)
    period = Column(Date, nullable=False)  # first day of the billed month
    issued_on = Column(Date, nullable=True)
    opening_balance = Column(Float, default=0.0)  # борг на початок періоду
    paid = Column(Float, default=0.0)  # сплачено за період (за даними постачальника)
    accrued = Column(Float, default=0.0)  # нараховано
    adjustment = Column(Float, default=0.0)  # перерахунок / пеня / субсидія
    to_pay = Column(Float, default=0.0)  # до сплати на кінець періоду
    consumption = Column(Float, nullable=True)
    note = Column(String, default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    provider = relationship("UtilityProvider", back_populates="bills")
    lines = relationship("UtilityBillLine", back_populates="bill", cascade="all, delete-orphan",
                         order_by="UtilityBillLine.id")


class UtilityBillLine(Base):
    __tablename__ = "utility_bill_lines"
    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey("utility_bills.id"), nullable=False, index=True)
    meter_id = Column(Integer, ForeignKey("utility_meters.id"), nullable=True)
    label = Column(String, default="")
    prev_value = Column(Float, nullable=True)
    curr_value = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    tariff = Column(Float, nullable=True)
    amount = Column(Float, nullable=True)

    bill = relationship("UtilityBill", back_populates="lines")


class UtilityPayment(Base):
    __tablename__ = "utility_payments"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("utility_providers.id"), nullable=False)
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    note = Column(String, default="")
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)

    provider = relationship("UtilityProvider", back_populates="payments")
    user = relationship("User")


class HousingNote(Base):
    """Timeline note. kind='heating' with date..end_date marks a heating period (end_date NULL = still on)."""
    __tablename__ = "housing_notes"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    kind = Column(String, nullable=False, default="note")  # note | heating | away | repair
    text = Column(String, default="")
    provider_id = Column(Integer, ForeignKey("utility_providers.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class PowerOutage(Base):
    """Compact outage history (one row per outage) per svitlobot channel. Timestamps are naive UTC."""
    __tablename__ = "power_outages"
    __table_args__ = (UniqueConstraint("channel", "started_at", name="uq_outage_channel_start"),)
    id = Column(Integer, primary_key=True)
    channel = Column(String, nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)  # NULL = still without power
    off_post_id = Column(Integer, nullable=True)
    on_post_id = Column(Integer, nullable=True)


class PowerSyncState(Base):
    __tablename__ = "power_sync_state"
    channel = Column(String, primary_key=True)
    last_post_id = Column(Integer, default=0)
    synced_at = Column(DateTime, nullable=True)


class HousingReminderLog(Base):
    __tablename__ = "housing_reminder_log"
    __table_args__ = (UniqueConstraint("family_id", "key", name="uq_reminder_family_key"),)
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    key = Column(String, nullable=False)
    sent_on = Column(Date, nullable=False)


class Obligation(Base):
    """Regular payment the family owes: installment («оплата частинами»), loan or subscription.
    Payments are finance transactions linked via transactions.obligation_id."""
    __tablename__ = "obligations"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, default="installment")  # installment | loan | subscription
    name = Column(String, nullable=False)
    icon = Column(String, default="")
    amount = Column(Float, nullable=False)  # regular payment
    currency = Column(String, default="UAH", nullable=False)
    period = Column(String, default="month", nullable=False)  # month | year
    due_day = Column(Integer, nullable=True)
    first_due = Column(Date, nullable=True)  # first scheduled payment
    payments_total = Column(Integer, nullable=True)  # installments: 10, 12, 24…
    end_date = Column(Date, nullable=True)  # last payment (loans) / cancel date (subscriptions)
    total_amount = Column(Float, nullable=True)  # full price / principal (info)
    paid_before = Column(Integer, default=0)  # payments made outside Bimi (not linked)
    match_pattern = Column(String, default="")  # bank description to auto-link («Citrus|monomarket»)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)  # applied to linked pending txs
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # whose card pays it
    remind = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    note = Column(String, default="")


class Budget(Base):
    """Monthly spending limit for one expense category (UAH)."""
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("family_id", "category_id", name="uq_budget_family_category"),)
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)


# ============================================================================
# Auto («Авто»): family vehicles and their journal (fuel fills, service, washes…).
# A journal entry may point to the finance transaction that paid it (one-to-one).
# ============================================================================

class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    name = Column(String, nullable=False)  # "Skoda Octavia Tour"
    icon = Column(String, default="🚗")
    plate = Column(String, default="")
    fuel = Column(String, nullable=False, default="petrol")  # petrol | diesel | lpg | electric
    fuel2 = Column(String, nullable=True)  # second fuel of a bi-fuel car (ГБО: petrol + lpg)
    tank_l = Column(Float, nullable=True)
    tank2_l = Column(Float, nullable=True)
    start_odometer = Column(Integer, nullable=True)
    match_pattern = Column(String, default="")  # bank descriptions of stations / washes («AZS|OKKO|DEWASH»)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # first driver (kept for older clients)
    driver_ids = Column(String, nullable=True)  # "1,2" — who drives it; picks the car for auto-linking
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)
    note = Column(String, default="")


class VehicleLog(Base):
    __tablename__ = "vehicle_logs"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    kind = Column(String, nullable=False, default="fuel")  # fuel | service | repair | tires | wash | parking | insurance | fine | other | odometer
    odometer = Column(Integer, nullable=True)
    fuel = Column(String, nullable=True)
    liters = Column(Float, nullable=True)  # kWh for electric
    price = Column(Float, nullable=True)  # per liter
    full_tank = Column(Boolean, default=False, nullable=False)
    place = Column(String, nullable=True)  # station / service: «WOG», «Пролюкс» — learned per bank merchant
    amount = Column(Float, default=0.0)  # mirrors the linked transaction
    title = Column(String, default="")
    note = Column(String, default="")
    source = Column(String, default="manual")  # manual | transaction | import
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class SmartReject(Base):
    """«Ні» to a suggestion: this merchant is not this category (Bimi stops offering it)."""
    __tablename__ = "smart_rejects"
    __table_args__ = (UniqueConstraint("family_id", "merchant", "category_id", name="uq_smart_reject"),)
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    merchant = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)


class VehicleDocument(Base):
    """Insurance policy (ОСЦПВ, КАСКО, Зелена карта…) of a car: dates, price, the PDF and/or an online link."""
    __tablename__ = "vehicle_documents"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False, default="osago")  # osago | kasko | green_card | other
    company = Column(String, default="")
    number = Column(String, default="")
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    amount = Column(Float, nullable=True)
    url = Column(String, default="")  # online policy view (insurer / МТСБУ)
    file = Column(LargeBinary, nullable=True)  # PDF / photo, ≤ 10 MB
    file_name = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    log_id = Column(Integer, ForeignKey("vehicle_logs.id", ondelete="SET NULL"), nullable=True)  # the payment
    note = Column(String, default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=True)


class VehicleIgnoredTx(Base):
    """«Не авто» — a suggested operation the family dismissed (coffee at a station, a borrowed car)."""
    __tablename__ = "vehicle_ignored_tx"
    __table_args__ = (UniqueConstraint("family_id", "transaction_id", name="uq_vehicle_ignored_tx"),)
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
