"""«Авто» → страховки: поліси (ОСЦПВ, КАСКО, Зелена карта…) з датами, ціною, PDF і/або посиланням на онлайн-перегляд.

The file is stored in Postgres (a policy PDF is ~100 KB–2 MB, so it is backed up with the database). It is opened
in the Telegram browser by a short-lived signed link: openLink can't send the Authorization header.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer

from app import crud, models
from app.api.housing import _actor_user_id
from app.config import settings
from app.core.deps import Actor, get_actor, require_family
from app.database import get_db
from app.services import vehicles as V

router = APIRouter(tags=["vehicles"])

DOC_KINDS = {"osago": ("🛡️", "Автоцивілка (ОСЦПВ)"), "kasko": ("💎", "КАСКО"), "green_card": ("🌍", "Зелена карта"),
             "other": ("📄", "Інший поліс")}
MAX_FILE = 10 * 1024 * 1024
FILE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp"}
SOON_DAYS = 30
LINK_TTL = timedelta(minutes=15)


class DocIn(BaseModel):
    vehicle_id: Optional[int] = None
    kind: Optional[str] = None
    company: Optional[str] = None
    number: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: Optional[float] = None
    url: Optional[str] = None
    note: Optional[str] = None
    log_id: Optional[int] = None  # an existing «Страховка» entry of the journal = the payment
    create_expense: bool = False  # …or record the payment: journal entry + expense in finances
    account: str = "Готівка"


def _date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise HTTPException(400, f"Невірна дата: {v}")


def doc_status(d, today: Optional[date] = None) -> dict:
    today = today or V.today_kyiv()
    if not d.end_date:
        return {"days_left": None, "status": "active"}
    left = (d.end_date - today).days
    return {"days_left": left, "status": "expired" if left < 0 else "soon" if left <= SOON_DAYS else "active"}


def doc_out(d: models.VehicleDocument, has_file: Optional[bool] = None) -> dict:
    icon, label = DOC_KINDS.get(d.kind, DOC_KINDS["other"])
    return {"id": d.id, "vehicle_id": d.vehicle_id, "kind": d.kind, "icon": icon, "label": label,
            "company": d.company or "", "number": d.number or "",
            "start_date": str(d.start_date) if d.start_date else None, "end_date": str(d.end_date) if d.end_date else None,
            "amount": d.amount, "url": d.url or "", "note": d.note or "", "log_id": d.log_id,
            "has_file": bool(d.file_name) if has_file is None else has_file, "file_name": d.file_name,
            **doc_status(d)}


def docs_brief(db: Session, family_id: int) -> dict[int, list[dict]]:
    """vehicle id → its current policies (the latest of each kind), for the overview / Home."""
    rows = (db.query(models.VehicleDocument).options(defer(models.VehicleDocument.file))
            .filter(models.VehicleDocument.family_id == family_id)
            .order_by(models.VehicleDocument.end_date.desc().nullslast(), models.VehicleDocument.id.desc()).all())
    out: dict[int, list[dict]] = {}
    seen: set = set()
    for d in rows:
        if (d.vehicle_id, d.kind) in seen:
            continue
        seen.add((d.vehicle_id, d.kind))
        out.setdefault(d.vehicle_id, []).append(doc_out(d))
    return out


def _doc(db: Session, fid: int, did: int) -> models.VehicleDocument:
    d = db.query(models.VehicleDocument).filter(models.VehicleDocument.id == did,
                                               models.VehicleDocument.family_id == fid).first()
    if not d:
        raise HTTPException(404, "Поліс не знайдено")
    return d


def _vehicle(db: Session, fid: int, vid: Optional[int]) -> models.Vehicle:
    v = db.query(models.Vehicle).filter(models.Vehicle.id == vid, models.Vehicle.family_id == fid).first()
    if not v:
        raise HTTPException(404, "Авто не знайдено")
    return v


def _apply(d: models.VehicleDocument, data: dict, db: Session, fid: int):
    if "kind" in data and data["kind"] not in DOC_KINDS:
        raise HTTPException(400, "Невірний тип поліса")
    if "vehicle_id" in data:
        _vehicle(db, fid, data["vehicle_id"])
    for k in ("start_date", "end_date"):
        if k in data:
            data[k] = _date(data[k])
    if data.get("url"):
        u = data["url"].strip()
        if not u.startswith(("https://", "http://")):
            raise HTTPException(400, "Посилання має починатися з https://")
        data["url"] = u[:1000]
    if data.get("amount") is not None and data["amount"] < 0:
        raise HTTPException(400, "Сума не може бути від'ємною")
    if data.get("log_id"):
        l = db.query(models.VehicleLog).filter(models.VehicleLog.id == data["log_id"],
                                               models.VehicleLog.family_id == fid).first()
        if not l:
            raise HTTPException(404, "Запис журналу не знайдено")
    for k, x in data.items():
        setattr(d, k, x.strip() if isinstance(x, str) else x)
    if d.start_date and not d.end_date:
        d.end_date = d.start_date.replace(year=d.start_date.year + 1) - timedelta(days=1) \
            if not (d.start_date.month == 2 and d.start_date.day == 29) else date(d.start_date.year + 1, 2, 28)
    if d.start_date and d.end_date and d.end_date < d.start_date:
        raise HTTPException(400, "Кінець дії раніше за початок")


def _payment(db: Session, d: models.VehicleDocument, fid: int, uid: Optional[int], account: str):
    """The policy's price as a journal entry «Страховка» + an expense in finances."""
    icon, label = DOC_KINDS.get(d.kind, DOC_KINDS["other"])
    title = " · ".join(x for x in (label, d.company) if x)
    when = d.start_date or V.today_kyiv()
    l = models.VehicleLog(family_id=fid, vehicle_id=d.vehicle_id, date=min(when, V.today_kyiv()), kind="insurance",
                          amount=d.amount, title=title, source="manual", user_id=uid, full_tank=False)
    if uid:
        tx = crud.create_transaction(db, fid, uid, V.category_for(db, fid, "insurance"), d.amount, crud.TYPE_EXPENSE,
                                     title, d.number or "", account, l.date)
        l.transaction_id = tx.id
    db.add(l)
    db.flush()
    d.log_id = l.id


@router.get("/families/{family_id}/vehicles/{vehicle_id}/documents")
def list_docs(family_id: int, vehicle_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    _vehicle(db, family_id, vehicle_id)
    rows = (db.query(models.VehicleDocument).options(defer(models.VehicleDocument.file))
            .filter(models.VehicleDocument.family_id == family_id, models.VehicleDocument.vehicle_id == vehicle_id)
            .order_by(models.VehicleDocument.end_date.desc().nullslast(), models.VehicleDocument.id.desc()).all())
    return [doc_out(d) for d in rows]


@router.post("/families/{family_id}/vehicle-documents")
def create_doc(family_id: int, payload: DocIn, actor: Actor = Depends(get_actor), _: None = Depends(require_family),
               db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    create_expense, account = data.pop("create_expense", False), data.pop("account", "Готівка")
    v = _vehicle(db, family_id, data.get("vehicle_id"))
    uid = _actor_user_id(db, actor, family_id)
    d = models.VehicleDocument(family_id=family_id, vehicle_id=v.id, kind="osago", user_id=uid,
                               created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    _apply(d, data, db, family_id)
    db.add(d)
    db.flush()
    if create_expense and (d.amount or 0) > 0 and not d.log_id:
        _payment(db, d, family_id, uid, account)
    db.commit()
    return doc_out(d)


@router.put("/families/{family_id}/vehicle-documents/{doc_id}")
def update_doc(family_id: int, doc_id: int, payload: DocIn, actor: Actor = Depends(get_actor),
               _: None = Depends(require_family), db: Session = Depends(get_db)):
    d = _doc(db, family_id, doc_id)
    data = payload.model_dump(exclude_unset=True)
    create_expense, account = data.pop("create_expense", False), data.pop("account", "Готівка")
    _apply(d, data, db, family_id)
    if create_expense and (d.amount or 0) > 0 and not d.log_id:
        _payment(db, d, family_id, _actor_user_id(db, actor, family_id), account)
    db.commit()
    return doc_out(d)


@router.delete("/families/{family_id}/vehicle-documents/{doc_id}")
def delete_doc(family_id: int, doc_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """The payment (journal entry and expense) stays — it was real money."""
    db.delete(_doc(db, family_id, doc_id))
    db.commit()
    return {"deleted": True}


@router.put("/families/{family_id}/vehicle-documents/{doc_id}/file")
async def upload_file(family_id: int, doc_id: int, request: Request, name: str = "поліс.pdf",
                      _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Raw body = the file (Content-Type: application/pdf or an image) — no multipart needed."""
    d = _doc(db, family_id, doc_id)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in FILE_TYPES:
        raise HTTPException(415, "Підтримуються PDF і фото (JPG, PNG, HEIC)")
    if int(request.headers.get("content-length") or 0) > MAX_FILE:
        raise HTTPException(413, "Файл більший за 10 МБ")
    body = await request.body()
    if not body:
        raise HTTPException(400, "Порожній файл")
    if len(body) > MAX_FILE:
        raise HTTPException(413, "Файл більший за 10 МБ")
    if ctype == "application/pdf" and not body.startswith(b"%PDF"):
        raise HTTPException(415, "Це не схоже на PDF")
    d.file, d.file_type, d.file_name = body, ctype, (name or "поліс").strip()[:120]
    db.commit()
    return doc_out(d, has_file=True)


@router.delete("/families/{family_id}/vehicle-documents/{doc_id}/file")
def delete_file(family_id: int, doc_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    d = _doc(db, family_id, doc_id)
    d.file = d.file_type = d.file_name = None
    db.commit()
    return doc_out(d, has_file=False)


@router.get("/families/{family_id}/vehicle-documents/{doc_id}/file-link")
def file_link(family_id: int, doc_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """A link the Telegram browser can open without our Authorization header (valid 15 minutes, this file only)."""
    d = (db.query(models.VehicleDocument).options(defer(models.VehicleDocument.file))
         .filter(models.VehicleDocument.id == doc_id, models.VehicleDocument.family_id == family_id).first())
    if not d or not d.file_name:
        raise HTTPException(404, "Файл не завантажено")
    token = jwt.encode({"doc": d.id, "fam": family_id, "typ": "vdoc",
                        "exp": datetime.now(timezone.utc) + LINK_TTL}, settings.JWT_SECRET, algorithm="HS256")
    return {"path": f"/vehicle-documents/{d.id}/file?t={token}"}


@router.get("/vehicle-documents/{doc_id}/file")
def get_file(doc_id: int, t: str, db: Session = Depends(get_db)):
    try:
        p = jwt.decode(t, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(403, "Посилання застаріло — відкрийте файл з Bimi ще раз")
    if p.get("typ") != "vdoc" or p.get("doc") != doc_id:
        raise HTTPException(403, "Невірне посилання")
    d = _doc(db, p["fam"], doc_id)
    if not d.file:
        raise HTTPException(404, "Файл не завантажено")
    return Response(d.file, media_type=d.file_type or "application/octet-stream",
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(d.file_name or 'polis')}",
                             "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
