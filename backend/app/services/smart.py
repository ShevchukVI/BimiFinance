"""«Bimi пропонує»: категорія для нерозібраної операції — з історії сім'ї, MCC-коду Monobank і відомих мереж.

Сигнали, від сильнішого:
1. Історія: операції з тією ж назвою продавця («Київське метро», «AZS 4») і схожою сумою, які сім'я вже розклала.
   Сума важлива: на «AZS 4» до ~150 ₴ — кава, від ~300 ₴ — пальне.
2. MCC (тип продавця від Monobank): 5541 АЗС, 4111 транспорт, 5411 продукти…
3. Відомі мережі за назвою: Сільпо, АТБ, Glovo, Steam…

Впевненість: «sure» — історія майже одностайна (≥ 90 %) і достатня; «likely» — є здогадка. Нічого не
застосовується саме — етап 1 лише пропонує; підтверджує людина (по одній або групою).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.services.vehicles import merchant_key

SYSTEM = ("Очікує", "Балансування")
SURE_SHARE, SURE_MIN, LIKELY_SHARE = 0.9, 3, 0.6
AUTO_MIN = 3  # categorised automatically only after 3+ consistent examples
FEE_MAX = 0.05  # a transfer between family members may cost the sender up to 5 % (Monobank credit funds: 4 %)

# MCC → words of a category name (the first family category containing one of them wins)
MCC_HINTS: list[tuple[range | tuple, tuple[str, ...], str]] = [
    ((5541, 5542, 5983, 5172), ("палив", "пальне", "бензин"), "АЗС"),
    ((4111, 4112, 4121, 4131), ("транспорт", "проїзд", "таксі"), "транспорт"),
    ((5411, 5422, 5441, 5451, 5462, 5499), ("продукт",), "продукти"),
    ((5812, 5813, 5814), ("кафе", "ресторан", "дрібниц", "їжа"), "кафе"),
    ((5912, 8011, 8021, 8043, 8062, 8099), ("здоров", "аптек", "медиц"), "аптека / лікар"),
    ((5651, 5691, 5699, 5661, 5621, 5611), ("одяг",), "одяг"),
    ((5995,), ("улюбл", "тварин", "кіт", "пес"), "зоотовари"),
    ((7542,), ("авто",), "мийка"),
    ((7538, 5533, 5532), ("ремонт авто", "авто"), "автосервіс"),
    ((4814, 4899), ("зв'яз", "інтернет", "мобіл"), "зв'язок"),
    ((7832, 7922, 7991, 7994, 7996), ("розваг",), "розваги"),
    ((5815, 5816, 5817, 5818), ("підписк", "розваг"), "цифрові послуги"),
    ((7230, 7298), ("догляд", "краса"), "салон краси"),
    ((5732, 5734, 5045), ("технік",), "техніка"),
    ((8220, 8299), ("освіт", "курс"), "освіта"),
]
CHAINS: list[tuple[str, tuple[str, ...], str]] = [
    (r"сільпо|silpo|атб|atb|novus|новус|фора|fora|велмарт|velmart|varus|варус|ашан|auchan|metro cash|"
     r"червоний маркет|коло\b|наш край|рукавичка|produkt|продукт|kishen|кишеня|neptun|нептун|tavria|таврія", ("продукт",), "супермаркет"),
    (r"glovo|bolt food|uber eats|mcdonald|макдональдс|kfc|puzata|пузата|domino|сушия|starbucks|aroma kava|lviv croissant",
     ("кафе", "дрібниц", "їжа", "ресторан"), "їжа / кафе"),
    (r"steam|playstation|xbox|nintendo|epic games", ("розваг", "ігр"), "ігри"),
    (r"netflix|spotify|youtube|apple\.com|icloud|google one|megogo|sweet\.tv|chatgpt|openai", ("підписк",), "підписка"),
    (r"uklon|uber|bolt\b|київ цифровий|kyiv digital|метро|metro\b|укрзалізниц|ukrzaliznyc|київпастранс", ("транспорт",), "транспорт"),
    (r"wog|okko|окко|socar|upg|klo\b|брсм|brsm|shell|авіас|avias|motto|amic", ("палив",), "АЗС"),
    (r"аптека|apteka|podorozhnyk|подорожник|анц|ліки24|liki24|d\.s\.|бажаємо здоров", ("здоров", "аптек"), "аптека"),
    (r"rozetka|розетка|comfy|фокстрот|foxtrot|eldorado|allo|алло|citrus|цитрус", ("технік",), "техніка"),
    (r"epicentr|епіцентр|нова лінія|jysk|ikea|leroy", ("дім",), "товари для дому"),
    (r"zoomagazin|зоо|masterzoo|zoo", ("улюбл", "тварин"), "зоотовари"),
    (r"kyivstar|київстар|vodafone|lifecell|воля|volia|triolan|тріолан|vega", ("інтернет", "зв'яз"), "зв'язок"),
    (r"нова пошта|nova poshta|укрпошта|ukrposhta|meest", ("документ", "пошт"), "пошта"),
]


def _cat_by_words(cats: list, words: tuple[str, ...]) -> Optional[models.Category]:
    for w in words:
        c = next((c for c in cats if w in c.name.lower()), None)
        if c:
            return c
    return None


def _times(n: int) -> str:
    return "раз" if n % 10 == 1 and n % 100 != 11 else "рази" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "разів"


def _ctype(tx_type: str) -> str:
    return "expense" if tx_type == "Витрати" else "income"


class Brain:
    """What the family taught Bimi: merchant → [(amount, category, type)] from every categorised operation."""

    def __init__(self, db: Session, family_id: int):
        self.db, self.family_id = db, family_id
        self.cats = db.query(models.Category).filter(models.Category.family_id == family_id).all()
        self.by_id = {c.id: c for c in self.cats}
        usable = {c.id for c in self.cats if not any(s in c.name for s in SYSTEM)}
        self.hist: dict[str, list[tuple[float, int, str, bool]]] = defaultdict(list)
        rows = (db.query(models.Transaction.title, models.Transaction.amount, models.Transaction.category_id,
                         models.Transaction.type, models.Transaction.refund)
                .filter(models.Transaction.family_id == family_id, models.Transaction.category_id.in_(usable),
                        models.Transaction.jar_id.is_(None)).all())
        refunds: Counter = Counter()
        for title, amount, cat, typ, refund in rows:
            if refund:
                refunds[cat] += 1
            k = merchant_key(title)
            if k:
                self.hist[k].append((amount or 0, cat, typ, bool(refund)))
        # ↩️ categories the family files refunds under, most used first (friends pay back for social events…)
        self.refund_order = [c for c, _ in refunds.most_common()]
        self.rejects = {(r.merchant, r.category_id) for r in db.query(models.SmartReject).filter(
            models.SmartReject.family_id == family_id)}

    def _pickable(self, tx_type: str) -> list:
        t = _ctype(tx_type)
        return [c for c in self.cats if c.type == t and not any(s in c.name for s in SYSTEM)]

    def _closest_leg(self, tx):
        if tx.jar_id is not None or tx.type not in ("Витрати", "Поповнення") or not tx.date:
            return None
        T = models.Transaction
        # the sender may pay a fee on top (Monobank: 4 % when sending credit funds: −728 ↔ +700)
        lo, hi = (tx.amount / (1 + FEE_MAX), tx.amount) if tx.type == "Витрати" else (tx.amount, tx.amount * (1 + FEE_MAX))
        cands = (self.db.query(T).filter(T.family_id == self.family_id, T.id != tx.id, T.user_id != tx.user_id,
                                         T.amount >= lo - 0.005, T.amount <= hi + 0.005, T.jar_id.is_(None),
                                         T.type == ("Поповнення" if tx.type == "Витрати" else "Витрати"),
                                         T.date >= tx.date - timedelta(days=1), T.date <= tx.date + timedelta(days=1)).all())
        return min(cands, key=lambda t: (abs(t.amount - tx.amount), abs((t.date - tx.date).days), abs(t.id - tx.id)), default=None)

    def transfer_pair(self, tx):
        """The other leg of money sent between family members: same amount, opposite direction, another
        member, within a day (−500 «Сонце 💖» at Вадим ↔ +500 «Від: Вадим Шевчук» at Аня). Closest in
        time and mutual, so a 400 ₴ bowling the day before does not steal the pair of a 400 ₴ «На каву»."""
        pair = self._closest_leg(tx)
        if pair is None:
            return None
        back = self._closest_leg(pair)
        return pair if back is not None and back.id == tx.id else None

    def suggest(self, tx) -> Optional[dict]:
        """→ {category_id, confidence: sure|likely, reason, source: family|history|mcc|chain} or None."""
        transfer = next((c for c in self.cats if "Переказ" in c.name), None)
        pair = self.transfer_pair(tx) if transfer else None
        incoming, outgoing = (tx, pair) if tx.type == "Поповнення" else (pair, tx)
        # the incoming leg must be a card transfer («Від: …»), else a friend's +200 and a 200 ₴ shop the same day would pair
        if pair is not None and re.match(r"^(❓\s*)?Від:", incoming.title or ""):
            sender = (outgoing.user.name if outgoing.user else "") or "?"
            receiver = (incoming.user.name if incoming.user else "") or "?"
            certain = sender.lower() in (incoming.title or "").lower()  # «Від: Вадим Шевчук» from Вадим
            return {"category_id": transfer.id, "confidence": "sure" if certain else "likely", "source": "family",
                    "pair_id": pair.id, "auto": certain,
                    "reason": f"переказ між вами ({sender} → {receiver})"
                              + (f", комісія {outgoing.amount - incoming.amount:g} ₴" if outgoing.amount > incoming.amount else "")}
        key = merchant_key(tx.title)
        a = tx.amount or 0
        ct = _ctype(tx.type)
        # an incoming transfer from a person who usually pays back (↩️) learns the refund category too
        hist = [(x, (c, r)) for x, c, typ, r in self.hist.get(key, [])
                if typ == tx.type and c in self.by_id and (key, c) not in self.rejects
                and (self.by_id[c].type == ct or (r and ct == "income") or "Переказ" in self.by_id[c].name)]
        if hist:
            near = [c for x, c in hist if abs(x - a) <= max(0.25 * a, 15)]
            pool = near or [c for _, c in hist]
            (cat, refund), n = Counter(pool).most_common(1)[0]
            share = n / len(pool)
            if share >= LIKELY_SHARE:
                sure = share >= SURE_SHARE and (n >= SURE_MIN or (n >= 2 and share == 1))
                seen = sum(1 for _, c in hist if c == (cat, refund))
                return {"category_id": cat, "refund": refund, "confidence": "sure" if sure else "likely", "source": "history", "seen": seen,
                        "auto": sure and n >= AUTO_MIN,
                        "reason": "так розкладено минулого разу" if seen == 1 else f"так розкладали {seen} {_times(seen)}"}
        pick = self._pickable(tx.type)
        mcc = getattr(tx, "mcc", None)
        if mcc and tx.type == "Витрати":
            for codes, words, label in MCC_HINTS:
                if mcc in codes:
                    c = _cat_by_words(pick, words)
                    if c and (key, c.id) not in self.rejects:
                        return {"category_id": c.id, "confidence": "likely", "source": "mcc", "reason": f"тип продавця: {label}"}
        if tx.type == "Витрати":
            text = (tx.title or "").lower()
            for rx, words, label in CHAINS:
                if re.search(rx, text):
                    c = _cat_by_words(pick, words)
                    if c and (key, c.id) not in self.rejects:
                        return {"category_id": c.id, "confidence": "likely", "source": "chain", "reason": label}
        return None


def pending_query(db: Session, family_id: int):
    return (db.query(models.Transaction).join(models.Category, models.Transaction.category_id == models.Category.id)
            .filter(models.Transaction.family_id == family_id, models.Category.name.like("%Очікує%")))


def suggestions(db: Session, family_id: int, limit: int = 500) -> dict:
    """Pending operations with a suggestion: per operation and grouped (merchant + category) for one-tap accept."""
    brain = Brain(db, family_id)
    txs = (pending_query(db, family_id).order_by(models.Transaction.date.desc(), models.Transaction.id.desc())
           .limit(limit).all())
    by_tx: dict[int, dict] = {}
    groups: dict[tuple, dict] = {}
    for tx in txs:
        s = brain.suggest(tx)
        if not s:
            continue
        by_tx[tx.id] = s
        k = (merchant_key(tx.title), s["category_id"], s["confidence"])
        g = groups.setdefault(k, {"title": re.split(r"\s*[|(]", (tx.title or "").replace("❓ ", ""))[0].strip(),
                                  "category_id": s["category_id"], "refund": bool(s.get("refund")),
                                  "confidence": s["confidence"], "source": s["source"],
                                  "reason": s["reason"], "count": 0, "min": None, "max": None, "total": 0.0,
                                  "transaction_ids": [], "type": tx.type})
        if s.get("seen", 0) > g.get("seen", 0):
            g["seen"], g["reason"] = s["seen"], s["reason"]
        g["count"] += 1
        g["total"] = round(g["total"] + (tx.amount or 0), 2)
        g["min"] = tx.amount if g["min"] is None else min(g["min"], tx.amount)
        g["max"] = tx.amount if g["max"] is None else max(g["max"], tx.amount)
        g["transaction_ids"].append(tx.id)
    order = sorted(groups.values(), key=lambda g: (g["confidence"] != "sure", -g["count"], -g["total"]))
    return {"pending": pending_query(db, family_id).count(), "suggested": len(by_tx),
            "sure": sum(1 for s in by_tx.values() if s["confidence"] == "sure"),
            "by_tx": {str(k): v for k, v in by_tx.items()}, "groups": order, "refund_order": brain.refund_order}


def reject(db: Session, family_id: int, title: str, category_id: int) -> None:
    key = merchant_key(title)
    if key and not db.query(models.SmartReject).filter_by(family_id=family_id, merchant=key, category_id=category_id).first():
        db.add(models.SmartReject(family_id=family_id, merchant=key, category_id=category_id))


def unreject(db: Session, family_id: int, title: str, category_id: int) -> None:
    db.query(models.SmartReject).filter_by(family_id=family_id, merchant=merchant_key(title),
                                           category_id=category_id).delete()


def auto_categorize(db: Session, tx) -> bool:
    """A new bank operation still waiting in «Очікує»: categorised right away when the family's history is
    unanimous (3+ times, ≥ 90 %) and the family keeps «Bimi розкладає сам» on. Marked 🤖. Never raises."""
    try:
        fam = db.get(models.Family, tx.family_id)
        if fam is None or not fam.smart_auto or tx.jar_id or tx.obligation_id:
            return False
        cat = db.get(models.Category, tx.category_id) if tx.category_id else None
        if cat is None or "Очікує" not in cat.name:
            return False
        s = Brain(db, tx.family_id).suggest(tx)
        if not s or not s.get("auto"):
            return False
        from app.crud import _clean_pending_title
        tx.category_id, tx.title, tx.auto_category = s["category_id"], _clean_pending_title(tx.title), True
        tx.refund = bool(s.get("refund"))
        pair = db.get(models.Transaction, s["pair_id"]) if s.get("pair_id") else None
        pcat = db.get(models.Category, pair.category_id) if pair is not None and pair.category_id else None
        if pcat is not None and "Очікує" in pcat.name:
            pair.category_id, pair.title, pair.auto_category = s["category_id"], _clean_pending_title(pair.title), True
        db.commit()
        db.refresh(tx)
        return True
    except Exception:
        db.rollback()
        return False
