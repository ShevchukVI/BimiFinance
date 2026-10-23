"""Monobank «банки» as Bimi goals.

Monobank describes own-jar moves in the card statement as
  «Поповнення «На життя»»                  — money from the card into the jar
  «Часткове зняття банки «На життя»»       — money from the jar back to the card
Those are internal transfers: they must not count as spending/income. A top-up of
somebody else's jar (charity) has the same wording, so only titles of the family's own
synced jars are recognised.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.core import security

CURRENCY = {980: "UAH", 840: "USD", 978: "EUR"}
JAR_IN = re.compile(r"^(?:❓\s*)?Поповнення «(.+)»\s*$")
JAR_OUT = re.compile(r"^(?:❓\s*)?(?!Поповнення)[^«]*банк[иу]\s*«(.+)»\s*$", re.IGNORECASE)


def parse_jar_title(title: str) -> Optional[tuple[str, str]]:
    """('in'|'out', jar title) for a Monobank jar transfer description, else None."""
    t = (title or "").strip()
    m = JAR_IN.match(t)
    if m:
        return "in", m.group(1).strip()
    m = JAR_OUT.match(t)
    if m:
        return "out", m.group(1).strip()
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upsert_jars(db: Session, family_id: int, user_id: int, jars: list) -> int:
    """Create / update Bimi goals from Monobank client-info «jars». Returns count."""
    n = 0
    for j in jars:
        jid = str(j.get("id") or "")
        if not jid:
            continue
        row = db.query(models.Jar).filter(models.Jar.family_id == family_id, models.Jar.mono_jar_id == jid).first()
        goal = (j.get("goal") or 0) / 100.0
        if row is None:
            row = models.Jar(family_id=family_id, mono_jar_id=jid, user_id=user_id, name=j.get("title") or "Банка",
                             goal=goal, currency=CURRENCY.get(j.get("currencyCode"), "UAH"), balance=0.0)
            db.add(row)
        row.name = j.get("title") or row.name
        if goal > 0:
            row.goal = goal
        row.bank_balance = (j.get("balance") or 0) / 100.0
        row.synced_at = _now()
        n += 1
    db.flush()
    return n


def classify(db: Session, tx) -> Optional[int]:
    """Turn a Monobank own-jar transfer into a jar operation (excluded from stats). Returns jar id."""
    parsed = parse_jar_title(tx.title)
    if not parsed or tx.jar_id:
        return None
    direction, name = parsed
    q = db.query(models.Jar).filter(models.Jar.family_id == tx.family_id, models.Jar.mono_jar_id.isnot(None),
                                    models.Jar.name == name)
    jar = q.filter(models.Jar.user_id == tx.user_id).first() or q.first()
    if jar is None:
        return None
    if direction == "in" and tx.type == "Витрати":
        tx.type, tx.title = "Поповнення", f"У банку «{jar.name}»"
    elif direction == "out" and tx.type == "Поповнення":
        tx.type, tx.title = "Витрати", f"З банки «{jar.name}»"
    else:
        return None
    tx.jar_id, tx.category_id, tx.obligation_id = jar.id, None, None
    return jar.id


def reclassify(db: Session, family_id: int) -> int:
    """Existing (e.g. pending) transactions that are transfers to/from own jars."""
    n = 0
    for tx in db.query(models.Transaction).filter(models.Transaction.family_id == family_id,
                                                  models.Transaction.jar_id.is_(None),
                                                  models.Transaction.title.like("%«%»%")).all():
        if classify(db, tx):
            n += 1
    db.flush()
    return n


def sync_family(db: Session, family_id: int, fetch=None) -> dict:
    """Pull jars of every family member with a Monobank token, then reclassify transfers."""
    from app.services.banking.monobank import monobank
    fetch = fetch or (lambda token: asyncio.run(monobank.get_jars(token)))
    users = (db.query(models.User).join(models.FamilyMember)
             .filter(models.FamilyMember.family_id == family_id, models.User.mono_token.isnot(None)).all())
    synced = 0
    for u in users:
        try:
            jars = fetch(security.decrypt_secret(u.mono_token))
        except Exception:
            continue
        synced += upsert_jars(db, family_id, u.id, jars or [])
    moved = reclassify(db, family_id)
    db.commit()
    return {"family_id": family_id, "jars": synced, "reclassified": moved}
