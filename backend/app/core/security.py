"""Security primitives: Fernet encryption, JWT, Telegram initData validation, API key checks."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.config import settings

_JWT_ALGO = "HS256"


# ---------- API Key (bot <-> backend, internal) ----------
def verify_api_key(candidate: str) -> bool:
    return bool(candidate) and secrets.compare_digest(candidate, settings.BOT_API_KEY)


# ---------- Fernet: bank tokens at rest ----------
_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FERNET_KEY.encode())
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise HTTPException(status_code=500, detail="Failed to decrypt stored secret (key rotated?)")


def encrypt_legacy_tokens():
    """One-time idempotent migration: encrypt plaintext mono tokens already in the DB."""
    from sqlalchemy import text

    from app.database import engine

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, mono_token FROM users WHERE mono_token IS NOT NULL AND mono_token != ''"
        )).fetchall()
        for row_id, value in rows:
            if value and not value.startswith("gAAAA"):
                conn.execute(
                    text("UPDATE users SET mono_token = :enc WHERE id = :uid"),
                    {"enc": encrypt_secret(value), "uid": row_id},
                )


# ---------- JWT (Mini App sessions) ----------
def create_access_token(tg_id: int, user_id: int, family_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(tg_id),
        "uid": user_id,
        "fid": family_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_JWT_ALGO)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[_JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# ---------- Telegram Mini App initData validation ----------
def validate_init_data(init_data: str) -> dict:
    """Server-side validation of Telegram WebApp initData. Returns parsed pairs or raises 401."""
    from urllib.parse import parse_qsl

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.get("hash")
    auth_date = parsed.get("auth_date")
    if not received_hash or not auth_date:
        raise HTTPException(status_code=401, detail="Missing initData hash or auth_date")
    try:
        if int(time.time()) - int(auth_date) > settings.INIT_DATA_MAX_AGE:
            raise HTTPException(status_code=401, detail="initData is expired")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid auth_date")

    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()) if k != "hash")
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData signature")
    return parsed
