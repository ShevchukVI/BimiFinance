import gzip
import os
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import settings
from app.core import security
from app.core.deps import require_internal_key
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
