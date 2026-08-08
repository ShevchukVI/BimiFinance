import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core import security
from app.core.deps import rate_limit_ip, require_internal_key
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=schemas.TokenResponse)
def token_for_mini_app(payload: schemas.InitDataRequest, request: Request, db: Session = Depends(get_db)):
    """Mint a JWT from validated Telegram initData (Mini App auth)."""
    rate_limit_ip(request, limit=10, window=60)
    parsed = security.validate_init_data(payload.init_data)
    try:
        user_json = json.loads(parsed["user"])
        tg_id = int(user_json["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid user data")

    user = crud.get_user_by_tg_id(db, tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    access_token = security.create_access_token(tg_id, user.id, user.family_id, user.role)
    return schemas.TokenResponse(access_token=access_token, user=schemas.UserOut.model_validate(user))


@router.get("/me", response_model=schemas.UserOut)
def get_me(tg_id: int, _: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    """Bot-only: resolve a Telegram user by tg_id."""
    user = crud.get_user_by_tg_id(db, tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
