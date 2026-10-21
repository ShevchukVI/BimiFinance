"""Load a housing JSON seed (see scripts/import_finansy_xlsx.py) into one family.

Run inside the backend container:
  python -m scripts.load_housing /tmp/housing_seed.json --family-id 3 [--replace]

Without --replace it refuses to touch a family that already has housing providers.
--replace deletes ONLY that family's housing data (providers, meters, readings, bills,
payments, housing notes, profile) — finance transactions are never touched.
"""
import argparse
import json
import sys
from datetime import date

from app import models
from app.core.migrations import run_migrations
from app.database import SessionLocal


def _d(v):
    return date.fromisoformat(v) if v else None


def wipe(db, fid):
    pids = [p.id for p in db.query(models.UtilityProvider).filter(models.UtilityProvider.family_id == fid)]
    mids = [m.id for m in db.query(models.UtilityMeter).filter(models.UtilityMeter.family_id == fid)]
    bids = [b.id for b in db.query(models.UtilityBill).filter(models.UtilityBill.family_id == fid)]
    if bids:
        db.query(models.UtilityBillLine).filter(models.UtilityBillLine.bill_id.in_(bids)).delete(synchronize_session=False)
    db.query(models.UtilityBill).filter(models.UtilityBill.family_id == fid).delete(synchronize_session=False)
    db.query(models.UtilityPayment).filter(models.UtilityPayment.family_id == fid).delete(synchronize_session=False)
    if mids:
        db.query(models.UtilityReading).filter(models.UtilityReading.meter_id.in_(mids)).delete(synchronize_session=False)
    db.query(models.HousingNote).filter(models.HousingNote.family_id == fid).delete(synchronize_session=False)
    db.query(models.UtilityMeter).filter(models.UtilityMeter.family_id == fid).delete(synchronize_session=False)
    if pids:
        db.query(models.UtilityProvider).filter(models.UtilityProvider.id.in_(pids)).delete(synchronize_session=False)
    db.query(models.HousingProfile).filter(models.HousingProfile.family_id == fid).delete(synchronize_session=False)
    db.flush()


def load(db, fid, data):
    p = data["profile"]
    db.add(models.HousingProfile(family_id=fid, **p))
    prov_ids, meter_ids = {}, {}
    rent = data.get("rent")
    order = 0
    if rent:
        r = models.UtilityProvider(family_id=fid, service="rent", billing="fixed", icon="🏠", sort_order=order,
                                   name=rent["name"], fixed_amount=rent["fixed_amount"], due_day=rent["due_day"],
                                   start_date=_d(rent.get("start_date")), note=rent.get("note", ""))
        db.add(r)
        order += 1
    for key, pv in data["providers"].items():
        meters = pv.get("meters", {})
        fields = {k: v for k, v in pv.items() if k not in ("meters", "start_date")}
        obj = models.UtilityProvider(family_id=fid, sort_order=order, start_date=_d(pv.get("start_date")), **fields)
        db.add(obj)
        db.flush()
        prov_ids[key] = obj.id
        for i, (mkey, mv) in enumerate(meters.items()):
            m = models.UtilityMeter(family_id=fid, provider_id=obj.id, sort_order=order * 10 + i, **mv)
            db.add(m)
            db.flush()
            meter_ids[mkey] = m.id
        order += 1
    for x in data["readings"]:
        db.add(models.UtilityReading(meter_id=meter_ids[x["meter"]], date=_d(x["date"]), value=x["value"],
                                     note=x.get("note", ""), source=x.get("source", "import")))
    for b in data["bills"]:
        bill = models.UtilityBill(family_id=fid, provider_id=prov_ids[b["provider"]], period=_d(b["period"]),
                                  issued_on=_d(b.get("issued_on")), opening_balance=b["opening_balance"],
                                  paid=b["paid"], accrued=b["accrued"], adjustment=b.get("adjustment", 0.0),
                                  to_pay=b["to_pay"], consumption=b.get("consumption"), note=b.get("note", ""))
        bill.lines = [models.UtilityBillLine(meter_id=meter_ids.get(ln.get("meter")), label=ln.get("label", ""),
                                             prev_value=ln.get("prev_value"), curr_value=ln.get("curr_value"),
                                             volume=ln.get("volume"), tariff=ln.get("tariff"), amount=ln.get("amount"))
                      for ln in b.get("lines", [])]
        db.add(bill)
    for x in data["payments"]:
        db.add(models.UtilityPayment(family_id=fid, provider_id=prov_ids[x["provider"]], date=_d(x["date"]),
                                     amount=x["amount"], note=x.get("note", "")))
    for n in data.get("notes", []):
        db.add(models.HousingNote(family_id=fid, date=_d(n["date"]), kind=n.get("kind", "note"), text=n["text"],
                                  provider_id=prov_ids.get(n.get("provider"))))
    db.flush()
    return {"providers": len(prov_ids) + (1 if rent else 0), "meters": len(meter_ids),
            "readings": len(data["readings"]), "bills": len(data["bills"]), "payments": len(data["payments"]),
            "notes": len(data.get("notes", []))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("seed")
    ap.add_argument("--family-id", type=int, required=True)
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    run_migrations()
    data = json.load(open(a.seed, encoding="utf-8"))
    db = SessionLocal()
    try:
        if not db.get(models.Family, a.family_id):
            sys.exit(f"Family {a.family_id} not found")
        has = db.query(models.UtilityProvider).filter(models.UtilityProvider.family_id == a.family_id).count()
        if has and not a.replace:
            sys.exit(f"Family {a.family_id} already has {has} housing providers — use --replace")
        if has:
            wipe(db, a.family_id)
        print(load(db, a.family_id, data))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
