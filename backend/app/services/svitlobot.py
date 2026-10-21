"""Power outage history from a public svitlobot Telegram channel (t.me/s/<channel>).

The bot posts «🔴 17:24 Світло зникло … Воно було 6год 37хв» and
«🟢 21:13 Світло з'явилося … Його не було 3год 49хв». Each «з'явилося» post alone
is enough to restore one outage interval [end − duration, end], so the history is
robust to missed posts and to our own server being down during the outage.

Storage is compact: one `power_outages` row per outage (two timestamps).
No tokens needed — the public web preview of the channel is scraped (same approach
as Home Assistant's svitlobot sensor), with `?before=<id>` pagination for backfill.
"""
from __future__ import annotations

import html
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import models

KYIV = ZoneInfo("Europe/Kyiv")
CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{4,64}$")
MATCH_MINUTES = 6  # same outage if starts differ less than this
MAX_INFERRED_HOURS = 72  # an end inferred from «Воно було» across a silent channel gap is not trusted


@dataclass
class Event:
    post_id: int
    kind: str  # off | on
    at: datetime  # naive UTC
    duration_min: Optional[int] = None  # «on»: how long there was no power; «off»: how long it was on


def normalize_channel(value: Optional[str]) -> Optional[str]:
    """Accepts 'svitlobot_x', '@svitlobot_x', 't.me/svitlobot_x', 'https://t.me/s/svitlobot_x'."""
    if not value:
        return None
    v = value.strip()
    v = re.sub(r"^(https?://)?(www\.)?t\.me/(s/)?", "", v).lstrip("@").split("/")[0].split("?")[0]
    return v if CHANNEL_RE.match(v) else None


def parse_duration(text: str) -> Optional[int]:
    d = re.search(r"(\d+)\s*д(?:н|\b|[^а-яіїє])", text)
    h = re.search(r"(\d+)\s*год", text)
    m = re.search(r"(\d+)\s*хв", text)
    if not (d or h or m):
        return None
    return (int(d.group(1)) * 1440 if d else 0) + (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def _event_time(text: str, posted: datetime) -> datetime:
    """Kyiv wall-clock HH:MM from the post text (posts may lag), as naive UTC."""
    local = posted.astimezone(KYIV)
    m = re.search(r"(\d{1,2}):(\d{2})\s+Світло", text)
    at = local
    if m:
        cand = local.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if cand > local + timedelta(minutes=2):
            cand -= timedelta(days=1)
        at = cand
    return at.astimezone(timezone.utc).replace(tzinfo=None)


def parse_page(page: str) -> list[Event]:
    events: list[Event] = []
    for chunk in page.split('class="tgme_widget_message_wrap')[1:]:
        pid = re.search(r'data-post="[^"/]+/(\d+)"', chunk)
        body = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', chunk, re.S)
        ts = re.search(r'<time[^>]+datetime="([^"]+)"', chunk)
        if not (pid and body and ts):
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", body.group(1)))
        text = re.sub(r"\s+", " ", text)
        posted = datetime.fromisoformat(ts.group(1))
        if "Світло зникло" in text:
            # «Воно було 9год 34хв» = how long power was on → tells when the previous outage ended
            was = re.search(r"Воно було\s+([0-9дгодхвн ]+)", text)
            events.append(Event(int(pid.group(1)), "off", _event_time(text, posted),
                                parse_duration(was.group(1)) if was else None))
        elif re.search(r"Світло з.явилося", text):
            dur_part = re.search(r"Його не було\s+([0-9дгодхвн ]+)", text)
            events.append(Event(int(pid.group(1)), "on", _event_time(text, posted),
                                parse_duration(dur_part.group(1)) if dur_part else None))
    return events


def fetch_page(channel: str, before: Optional[int] = None, timeout: int = 10) -> str:
    url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BimiFinance housing)"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def apply_events(db: Session, channel: str, events: list[Event]) -> int:
    """Upsert outages from events (chronological). Returns number of changed rows."""
    changed = 0
    tol = timedelta(minutes=MATCH_MINUTES)
    q = db.query(models.PowerOutage).filter(models.PowerOutage.channel == channel)
    for ev in sorted(events, key=lambda e: e.post_id):
        if ev.kind == "off":
            if ev.duration_min is not None:
                # power had been on since `on_since` → any outage still open before that has ended then
                on_since = ev.at - timedelta(minutes=ev.duration_min)
                for stale in q.filter(models.PowerOutage.ended_at.is_(None),
                                      models.PowerOutage.started_at < on_since - tol).all():
                    gap_h = (on_since - stale.started_at).total_seconds() / 3600
                    stale.ended_at = on_since if gap_h <= MAX_INFERRED_HOURS else stale.started_at
                    changed += 1
            row = q.filter(models.PowerOutage.started_at.between(ev.at - tol, ev.at + tol)).first()
            if row is None:
                db.add(models.PowerOutage(channel=channel, started_at=ev.at, off_post_id=ev.post_id))
                changed += 1
            elif row.off_post_id is None:
                row.off_post_id = ev.post_id
            db.flush()
            continue
        # «on»: close the matching outage, or create it from the duration
        start = ev.at - timedelta(minutes=ev.duration_min) if ev.duration_min is not None else None
        row = None
        if start is not None:
            row = q.filter(models.PowerOutage.started_at.between(start - tol, start + tol)).first()
        if row is None:
            row = (q.filter(models.PowerOutage.ended_at.is_(None), models.PowerOutage.started_at <= ev.at)
                   .order_by(models.PowerOutage.started_at.desc()).first())
        if row is None and start is not None:
            row = models.PowerOutage(channel=channel, started_at=start)
            db.add(row)
        if row is not None and (row.ended_at != ev.at or row.on_post_id != ev.post_id):
            row.ended_at = ev.at
            row.on_post_id = ev.post_id
            changed += 1
        db.flush()
    changed += close_stale(db, channel)
    return changed


def close_stale(db: Session, channel: str) -> int:
    """An open outage followed by a newer outage cannot still be open: the «з'явилося»
    post was missed. Without better info close it with zero length (never invent hours)."""
    rows = (db.query(models.PowerOutage).filter(models.PowerOutage.channel == channel)
            .order_by(models.PowerOutage.started_at).all())
    n = 0
    for cur, nxt in zip(rows, rows[1:]):
        if cur.ended_at is None:
            cur.ended_at = cur.started_at
            n += 1
    if n:
        db.flush()
    return n


def sync_channel(db: Session, channel: str, max_pages: int = 60, fetch=fetch_page) -> dict:
    """Fetch new posts (backfilling older pages on first run) and update outages."""
    state = db.get(models.PowerSyncState, channel)
    if state is None:
        state = models.PowerSyncState(channel=channel, last_post_id=0)
        db.add(state)
        db.flush()
    known = state.last_post_id or 0
    events: list[Event] = []
    seen_ids: set[int] = set()
    before = None
    pages = 0
    max_seen = known
    while pages < max_pages:
        page = fetch(channel, before)
        pages += 1
        ids = [int(x) for x in re.findall(r'data-post="[^"/]+/(\d+)"', page)]
        if not ids:
            break
        max_seen = max(max_seen, max(ids))
        for ev in parse_page(page):
            if ev.post_id > known and ev.post_id not in seen_ids:
                seen_ids.add(ev.post_id)
                events.append(ev)
        oldest = min(ids)
        if oldest <= known + 1 or oldest <= 1 or before == oldest:
            break
        before = oldest
        time.sleep(0.25)
    changed = apply_events(db, channel, events)
    newest = max_seen
    state.last_post_id = newest
    state.synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"channel": channel, "pages": pages, "events": len(events), "changed": changed, "last_post_id": newest}
