from datetime import date
from typing import Optional, List
from pydantic import BaseModel, computed_field, model_validator

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
    model_config = {"from_attributes": True}

    @computed_field
    @property
    def family_id(self) -> Optional[int]:
        """Backward compat — frontend uses family_id."""
        return self.current_active_family_id
class FamilyMembershipOut(BaseModel):
    family_id: int
    name: str
    role: str
    is_active: bool = False
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
class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    type: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[int] = None
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
class JarCreate(BaseModel):
    family_id: int
    name: str
    goal: float
class JarOut(BaseModel):
    id: int
    family_id: int
    name: str
    balance: float
    goal: float
    model_config = {"from_attributes": True}
class JarTopUp(BaseModel):
    amount: float
class CategoryStat(BaseModel):
    name: str
    amount: float
class FamilyStatsOut(BaseModel):
    income: float
    expense: float
    balance: float
    top_categories: List[CategoryStat]
    pending_count: int = 0
    # Баланси джерел коштів (наразі лише готівка; банк дає реальний баланс через API)
    balances: dict = {}
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
