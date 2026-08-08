from datetime import date
from typing import Optional, List
from pydantic import BaseModel

class FamilyCreate(BaseModel):
    name: str
class FamilyOut(BaseModel):
    id: int
    name: str
    invite_code: str
    model_config = {"from_attributes": True}
class FamilyTokenUpdate(BaseModel):
    mono_token: str
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
    role: Optional[str] = None  # 'admin' | 'member' (дефолт: перший юзер сім'ї = admin)
class UserOut(BaseModel):
    id: int
    family_id: int
    tg_id: Optional[int]
    name: str
    has_mono_token: bool = False
    role: Optional[str] = None
    model_config = {"from_attributes": True}
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
    category_id: Optional[int] = None
    date: Optional[date] = None
class TransactionOut(BaseModel):
    id: int
    family_id: int
    user_id: int
    category_id: int
    amount: float
    type: str
    title: str
    note: str
    account: str
    mono_id: Optional[str]
    date: date
    model_config = {"from_attributes": True}
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
class NoteCreate(BaseModel):
    family_id: int
    content: str
class NoteOut(BaseModel):
    id: int
    family_id: int
    content: str
    model_config = {"from_attributes": True}

# --- Phase 1: Auth ---
class InitDataRequest(BaseModel):
    init_data: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut