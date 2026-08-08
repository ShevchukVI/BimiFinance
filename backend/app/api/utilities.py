"""Smart Utilities — foundation for meter tracking, readings, and payments.

V1: basic CRUD. V2: predictions, bill estimation, reminders.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from app import models
from app.core.deps import require_family, get_actor, Actor
from app.database import get_db

router = APIRouter(prefix="/utilities", tags=["utilities"])


class MeterCreate(BaseModel):
    name: str
    utility_type: str
    unit: str
    tariff: float = 0.0


class ReadingCreate(BaseModel):
    date: date
    value: float
    amount_paid: float = 0.0
    note: str = ""


@router.post("/families/{family_id}/meters")
def create_meter(family_id: int, payload: MeterCreate, _: None = Depends(require_family),
                 db: Session = Depends(get_db)):
    obj = models.UtilityMeter(family_id=family_id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "utility_type": obj.utility_type, "unit": obj.unit, "tariff": obj.tariff}


@router.get("/families/{family_id}/meters")
def get_meters(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    meters = db.query(models.UtilityMeter).filter(models.UtilityMeter.family_id == family_id).all()
    return [{"id": m.id, "name": m.name, "utility_type": m.utility_type, "unit": m.unit, "tariff": m.tariff} for m in meters]


@router.post("/families/{family_id}/meters/{meter_id}/readings")
def add_reading(family_id: int, meter_id: int, payload: ReadingCreate,
                _: None = Depends(require_family), db: Session = Depends(get_db)):
    meter = db.query(models.UtilityMeter).filter(models.UtilityMeter.id == meter_id,
                                                   models.UtilityMeter.family_id == family_id).first()
    if not meter:
        raise HTTPException(404, "Meter not found")
    obj = models.UtilityReading(meter_id=meter_id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "date": str(obj.date), "value": obj.value, "amount_paid": obj.amount_paid}


@router.get("/families/{family_id}/meters/{meter_id}/readings")
def get_readings(family_id: int, meter_id: int, _: None = Depends(require_family),
                 db: Session = Depends(get_db)):
    readings = (db.query(models.UtilityReading)
                .join(models.UtilityMeter)
                .filter(models.UtilityMeter.id == meter_id,
                        models.UtilityMeter.family_id == family_id)
                .order_by(models.UtilityReading.date.desc()).all())
    return [{"id": r.id, "date": str(r.date), "value": r.value, "amount_paid": r.amount_paid, "note": r.note}
            for r in readings]
