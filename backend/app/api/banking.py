"""Banking API — delegates to provider implementations. All endpoints require X-API-Key."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud
from app.core import security
from app.core.deps import require_internal_key
from app.database import get_db
from app.services.banking.monobank import monobank as monobank_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/banking", tags=["banking"])


class SyncResult(BaseModel):
    user_id: int
    tg_id: int
    accounts_synced: int
    webhook_ok: bool
    error: Optional[str] = None


@router.get("/accounts")
def get_all_accounts(_: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    accounts = crud.get_all_bank_accounts(db)
    return [{"user_id": a.user_id, "provider": a.provider, "external_account_id": a.external_account_id, "name": a.name} for a in accounts]


@router.post("/sync", response_model=List[SyncResult])
async def sync_all(webhook_url: str = "https://mono.vshevchuk.pp.ua/webhook",
                   _: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    tokens = crud.get_all_mono_tokens(db)
    if not tokens:
        return []

    results = []
    for user in tokens:
        try:
            plain = security.decrypt_secret(user.mono_token)
        except Exception as e:
            results.append(SyncResult(user_id=user.id, tg_id=user.tg_id, accounts_synced=0, webhook_ok=False, error=f"Decrypt failed"))
            continue

        synced = 0
        webhook_ok = False
        error = None

        try:
            webhook_ok = await monobank_provider.register_webhook(plain, webhook_url)
        except Exception as e:
            error = str(e)[:200]

        try:
            accounts = await monobank_provider.get_accounts(plain)
            if accounts:
                crud.clear_user_bank_accounts(db, user.id)
                for a in accounts:
                    crud.upsert_bank_account(db, user.id, "monobank", a.external_id, a.name)
                synced = len(accounts)
        except Exception as e:
            if not error:
                error = str(e)[:200]

        results.append(SyncResult(
            user_id=user.id, tg_id=user.tg_id, accounts_synced=synced, webhook_ok=webhook_ok, error=error,
        ))

    return results


@router.get("/balance/{tg_id}")
async def get_user_balance(tg_id: int, _: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    user = crud.get_user_by_tg_id(db, tg_id)
    if not user or not user.mono_token:
        return {"balance": 0.0, "has_token": False}
    try:
        plain = security.decrypt_secret(user.mono_token)
        balance = await monobank_provider.get_balance(plain)
        return {"balance": round(balance, 2), "has_token": True}
    except Exception:
        return {"balance": 0.0, "has_token": True, "error": "decrypt_failed"}
