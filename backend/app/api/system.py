import gzip
import os
import subprocess
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import settings
from app.core import security
from app.core.deps import require_internal_key
from app.core.achievements import get_earned_achievements
from app.database import get_db

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/mono-tokens", response_model=list[schemas.SystemTokenOut])
def get_system_tokens(_: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    """Bot-only: decrypted Monobank tokens for webhook registration. NEVER public."""
    users = crud.get_all_mono_tokens(db)
    return [
        {"user_id": u.id, "tg_id": u.tg_id, "mono_token": security.decrypt_secret(u.mono_token)}
        for u in users
    ]


@router.get("/backup")
def system_backup(_: None = Depends(require_internal_key)):
    """Bot-only: full PostgreSQL dump (pg_dump), gzip-compressed, downloadable .sql.gz.

    Best practice for FastAPI/Docker: use the pg_dump CLI (postgresql-client is in the image)
    streamed in-memory — no temp files on disk, no extra pure-Python dump code to maintain.
    The dump is returned as gzip bytes with a Content-Disposition header.
    """
    db_host = os.getenv("POSTGRES_HOST", "postgres")
    db_port = os.getenv("POSTGRES_PORT", "5432")

    cmd = [
        "pg_dump",
        "--no-owner",
        "--clean",
        "-h", db_host,
        "-p", db_port,
        "-U", settings.POSTGRES_USER,
        "-d", settings.POSTGRES_DB,
    ]
    env = dict(os.environ, PGPASSWORD=settings.POSTGRES_PASSWORD)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300, env=env)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pg_dump failed to run: {e}")

    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace")[:500]
        raise HTTPException(status_code=500, detail=f"pg_dump failed: {stderr}")

    payload = proc.stdout
    if len(payload) < 1024:
        raise HTTPException(status_code=500, detail="pg_dump produced an empty/too-small dump")

    compressed = gzip.compress(payload)
    filename = f"bimi_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql.gz"
    return Response(
        content=compressed,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/achievements")
def get_achievements(tg_id: int, _: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    """Bot: повертає досягнення користувача на основі його статистики."""
    user = crud.get_user_by_tg_id(db, tg_id)
    if not user:
        return []
    family_id = user.current_active_family_id
    if not family_id:
        return []

    total_tx = db.query(crud.models.Transaction).filter(
        crud.models.Transaction.family_id == family_id,
        crud.models.Transaction.type == "Витрати"
    ).count()

    income_tx = db.query(crud.models.Transaction).filter(
        crud.models.Transaction.family_id == family_id,
        crud.models.Transaction.type == "Поповнення"
    ).all()

    total_saved = sum(t.amount for t in income_tx)
    current_streak = 0
    today = date.today()
    for i in range(30):
        d = today.replace(day=today.day - i) if today.day > i else today.replace(month=today.month - 1, day=28)
        count = db.query(crud.models.Transaction).filter(
            crud.models.Transaction.family_id == family_id,
            crud.models.Transaction.date == d.isoformat()
        ).count()
        if count > 0:
            current_streak += 1
        else:
            break

    earned = get_earned_achievements({
        "total_transactions": total_tx,
        "current_streak_days": current_streak,
        "total_saved": total_saved,
    })
    return [{"key": a.key, "name": a.name, "icon": a.icon, "description": a.description} for a in earned]
