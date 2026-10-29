import json
from datetime import date, datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, computed_field, field_validator, model_validator

class FamilyCreate(BaseModel):
    name: str
class FamilyOut(BaseModel):
    id: int
    name: str
    invite_code: str
    model_config = {"from_attributes": True}
class UserTokenUpdate(BaseModel):
    mono_token: str
class SystemTokenOut(BaseModel):
    user_id: int
    tg_id: int
    mono_token: str
class UserCreate(BaseModel):
    family_id: int
    name: str
    tg_id: Optional[int] = None
    mono_token: Optional[str] = None
    role: Optional[str] = None
class UserOut(BaseModel):
    id: int
    tg_id: Optional[int]
    name: str
    has_mono_token: bool = False
    current_active_family_id: Optional[int] = None
    role: Optional[str] = None
    tab_prefs: dict[str, bool] = {}
    model_config = {"from_attributes": True}

    @field_validator("tab_prefs", mode="before")
    @classmethod
    def _tab_prefs(cls, v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                v = {}
        return {k: bool(x) for k, x in (v or {}).items()} if isinstance(v, dict) else {}

    @computed_field
    @property
    def family_id(self) -> Optional[int]:
        """Backward compat — frontend uses family_id."""
        return self.current_active_family_id
class TabPrefsUpdate(BaseModel):
    tab: Literal["housing", "auto"]
    show: Optional[bool] = None  # None → back to the default (shown when the family uses it)


class FamilyMembershipOut(BaseModel):
    family_id: int
    name: str
    role: str
    is_active: bool = False
class FamilyMemberOut(BaseModel):
    user_id: int
    name: str
    role: str
class MemberRoleUpdate(BaseModel):
    role: str
class JoinFamilyRequest(BaseModel):
    invite_code: str
class SetActiveFamilyRequest(BaseModel):
    family_id: int
class CategoryCreate(BaseModel):
    family_id: int
    icon: str
    name: str
    color: str
    type: str
class CategoryOut(BaseModel):
    id: int
    family_id: int
    icon: str
    name: str
    color: str
    type: str
    model_config = {"from_attributes": True}
class TransactionCreate(BaseModel):
    family_id: int
    user_id: int
    category_id: int
    amount: float
    type: str
    title: str
    note: str = ""
    account: str
    mono_id: Optional[str] = None
    date: date
    currency: str = "UAH"
    jar_id: Optional[int] = None  # поповнення/зняття до/з скарбнички
    mcc: Optional[int] = None  # Monobank MCC
    refund: bool = False  # ↩️ повернення витрати: дохід у категорії витрат, зменшує витрати й конверт
class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    type: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[int] = None
    currency: Optional[str] = None
    refund: Optional[bool] = None
    # NOTE: pydantic 2.13.4 баг — 'Optional[date] = None' завжди падає з
    # 'none_required' для будь-якого введення. Тому приймаємо str і парсимо
    # у crud-шарі (див. crud._coerce_date).
    date: Optional[str] = None
class TransferCreate(BaseModel):
    """Переказ між джерелами коштів (Cash ↔ Bank). Не дохід/витрата."""
    family_id: int
    user_id: Optional[int] = None
    amount: float
    from_account: str
    to_account: str
    mono_id: Optional[str] = None  # для дедуплікації банківських вебхуків
    currency: str = "UAH"
class TransactionOut(BaseModel):
    id: int
    family_id: int
    user_id: int
    category_id: Optional[int]  # NULL у переказів (тип 'Переказ')
    amount: float
    type: str
    title: str
    note: str
    account: str
    mono_id: Optional[str]
    date: date
    currency: str = "UAH"
    jar_id: Optional[int] = None
    obligation_id: Optional[int] = None  # кредит / розстрочка / підписка
    mcc: Optional[int] = None
    auto_category: bool = False  # 🤖 Bimi розклав сам
    refund: bool = False  # ↩️ повернення витрати
    user_name: Optional[str] = None  # ім'я автора (атрибуція в Mini App)
    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _attach_user_name(cls, data):
        """Дістаємо ім'я автора з ORM-об'єкта/словника до валідації."""
        if isinstance(data, dict):
            if "user_name" not in data and data.get("user") is not None:
                data = dict(data)
                data["user_name"] = getattr(data["user"], "name", None)
            return data
        # ORM-об'єкт: робимо плоский dict, щоб не мутувати SQLAlchemy-інстанс
        if hasattr(data, "__table__"):
            d = {c.name: getattr(data, c.name) for c in data.__table__.columns}
            d["user_name"] = data.user.name if data.user else None
            return d
        return data


class BankAccountOut(BaseModel):
    """Банківський рахунок з балансом (для Mini App Home)."""
    name: str
    balance: float  # own funds (bank balance minus the credit limit; negative = credit in use)
    currency: str = "UAH"
    kind: str = ""
    last4: str = ""
    credit_limit: float = 0.0
    available: Optional[float] = None  # what can be spent now, credit included


class BankUserBalancesOut(BaseModel):
    """Користувач сім'ї з підключеними банківськими рахунками."""
    user_id: int
    user_name: str
    provider: str
    accounts: List[BankAccountOut]
class JarCreate(BaseModel):
    family_id: int
    name: str
    goal: float
    currency: str = "UAH"
class JarOut(BaseModel):
    id: int
    family_id: int
    name: str
    balance: float
    goal: float
    currency: str = "UAH"
    mono_jar_id: Optional[str] = None  # linked Monobank «банка»
    user_id: Optional[int] = None
    synced_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
class JarTopUp(BaseModel):
    amount: float
class CategoryStat(BaseModel):
    name: str
    amount: float
class CashUserBalanceOut(BaseModel):
    user_id: int
    user_name: str
    balance: float
    currency: str = "UAH"


class CashByCurrencyOut(BaseModel):
    currency: str
    balance: float


class FamilyStatsOut(BaseModel):
    income: float
    expense: float
    balance: float
    top_categories: List[CategoryStat]
    pending_count: int = 0
    # Баланси джерел коштів (наразі лише готівка; банк дає реальний баланс через API)
    balances: dict = {}
    # Готівка, згрупована по користувачах (для відображення per-person)
    cash_by_user: List[CashUserBalanceOut] = []
    # Дохід/витрати по валютах (місяць): {"UAH": {"income": .., "expense": ..}, "USD": {...}}
    by_currency: dict = {}
    # Готівка по валютах (увесь час): [{"currency": "UAH", "balance": ..}, ...]
    cash_by_currency: List[CashByCurrencyOut] = []
    # «<payer> винне»: {"payer": "Прего", "owed": 3455.0} (− = their money left with us); None if not set up
    work: Optional[dict] = None
class NoteCreate(BaseModel):
    family_id: int
    content: str
class NoteOut(BaseModel):
    id: int
    family_id: int
    content: str
    model_config = {"from_attributes": True}

class InitDataRequest(BaseModel):
    init_data: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
