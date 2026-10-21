"""Parse a hand-kept housing spreadsheet (.xlsx) into a JSON seed for scripts/load_housing.py.

Everything specific to one home (sheet names, providers, tariffs, area, rent, svitlobot
channel) lives in a JSON config kept OUT of git — see scripts/housing_import.example.json.

Sheet layouts understood (`kind` in the config):
  journal      — rows: Дата | Категорія | Тип запису | Показник | Сума | Коментар
                 «Показник» → reading, «Оплата» → payment, other rows → notes
  zones_bill   — electricity bills in blocks «Рахунок за <місяць> <рік>» with «день/ніч» lines
                 (current, previous, volume, tariff), balance/payment/accrual/to-pay rows,
                 plus an own-vs-billed readings table in columns G:K
  gas_blocks   — blocks «<Місяць> <рік> | issued date» with Спожито/Нараховано/Борг/Сплачено/До сплати
  simple4      — blocks «Name | За <місяць> <рік>», row after «До сплати на…»: opening | accrued | paid | to pay
  simple3      — same, row after «Залишок на…»: opening | accrued | to pay

Usage (openpyxl is NOT a backend dependency — run in any python container):
  python import_finansy_xlsx.py book.xlsx config.json seed.json
The seed contains personal data — keep it out of git.
"""
import json
import re
import sys
from datetime import date, datetime

import openpyxl

MONTHS = ["січ", "лют", "берез", "квіт", "трав", "черв", "лип", "серп", "верес", "жовт", "листоп", "груд"]


def month_of(text):
    t = str(text).lower()
    y = re.search(r"(20\d\d)", t)
    for i, stem in enumerate(MONTHS):
        if stem in t and y:
            return date(int(y.group(1)), i + 1, 1)
    return None


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(v or ""))
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def rows(ws):
    for r in ws.iter_rows(values_only=True):
        yield list(r) + [None] * 16


def parse_journal(ws, cfg, out):
    cmap = cfg["categories"]  # {"Світло (День)": ["electricity", "el_day"], ...}
    for r in list(rows(ws))[1:]:
        d, cat, kind, val, amount, comment = as_date(r[0]), r[1], r[2], num(r[3]), num(r[4]), r[5] or ""
        if not d or cat not in cmap:
            continue
        prov, meter = cmap[cat]
        if kind == "Показник" and meter and val is not None:
            out["readings"].append({"meter": meter, "date": str(d), "value": val, "note": comment, "source": "import"})
        elif kind == "Оплата" and amount:
            out["payments"].append({"provider": prov, "date": str(d), "amount": round(abs(amount), 2), "note": comment})
        elif kind == "Платіжка" and val is not None:
            continue  # billed meter values are covered by bill lines
        else:
            out["notes"].append({"date": str(d), "kind": "note", "provider": prov,
                                 "text": f"{cat}: {kind or 'запис'} {amount if amount is not None else ''} {comment}".strip()})


def parse_zones_bill(ws, cfg, out):
    prov, zones = cfg["provider"], cfg["zones"]  # {"день": "el_day", "ніч": "el_night"}
    own = cfg.get("own_readings_cols")  # {"date": 6, "el_day": 7, "el_night": 8}
    cur, bills = None, []
    for r in rows(ws):
        a = str(r[0] or "")
        if own and as_date(r[own["date"]]):
            for meter, col in own.items():
                if meter != "date" and num(r[col]) is not None:
                    out["readings"].append({"meter": meter, "date": str(as_date(r[own["date"]])), "value": num(r[col]),
                                            "note": "", "source": "import"})
        if a.startswith("Рахунок за"):
            cur = {"provider": prov, "period": str(month_of(a)), "lines": [], "note": str(r[1] or "")}
            bills.append(cur)
            paid_on = as_date(r[1])
            if paid_on and num(r[2]):
                out["payments"].append({"provider": prov, "date": str(paid_on), "amount": num(r[2]),
                                        "note": f"Оплата рахунку {a[11:]}"})
            continue
        if cur is None:
            continue
        if a in zones and num(r[1]) is not None:
            vol, tariff = num(r[3]), num(r[4])
            cur["lines"].append({"meter": zones[a], "label": a, "prev_value": num(r[2]), "curr_value": num(r[1]),
                                 "volume": vol, "tariff": tariff,
                                 "amount": round(vol * tariff, 2) if vol is not None and tariff else None})
        elif a.startswith("Баланс попереднього"):
            cur["opening_balance"] = num(r[2])
        elif a.startswith("Оплата попереднього"):
            cur["paid"] = abs(num(r[2]) or 0)
        elif a.startswith("Поточні нарахування"):
            cur["accrued"] = num(r[2])
        elif a.startswith("Сума до сплати"):
            cur["to_pay"] = num(r[2])
    out["bills"] += [b for b in bills if b.get("to_pay") is not None]


def parse_gas_blocks(ws, cfg, out):
    prov, meter = cfg["provider"], cfg.get("meter")
    cur = None
    for r in rows(ws):
        a = str(r[0] or "")
        m = month_of(a)
        if m and as_date(r[1]):
            cur = {"provider": prov, "period": str(m), "issued_on": str(as_date(r[1])), "lines": [], "note": str(r[2] or "")}
            out["bills"].append(cur)
            continue
        if cur is None:
            continue
        v = num(r[1])
        if a.startswith("Спожито"):
            cur["consumption"] = v
        elif a.startswith("Нараховано"):
            cur["accrued"] = v
        elif a.startswith("Борг"):
            cur["opening_balance"] = v
        elif a.startswith("Сплачено"):
            cur["paid"] = v
        elif a.startswith("До сплати, грн"):
            cur["to_pay"] = v
        elif a.startswith("До сплати за"):
            cur["note"] = (cur["note"] + f"; {a} {v}").strip("; ")
        elif a.startswith("Показник на") and v is not None and meter:
            out["readings"].append({"meter": meter, "date": str(as_date(a)), "value": v, "note": "З платіжки", "source": "bill"})
        if meter and cur.get("consumption") and cur.get("accrued"):
            cur["lines"] = [{"meter": meter, "label": "Спожито", "volume": cur["consumption"],
                             "tariff": round(cur["accrued"] / cur["consumption"], 4), "amount": cur["accrued"]}]


def parse_simple(ws, cfg, out, three_cols):
    cur, header = None, False
    for r in rows(ws):
        a = str(r[0] or "")
        if month_of(r[1] or ""):
            cur = {"provider": cfg["provider"], "period": str(month_of(r[1])), "lines": [], "note": ""}
            out["bills"].append(cur)
            continue
        if cur is None:
            continue
        if a.startswith("До сплати на") or a.startswith("Залишок на"):
            header = True
            continue
        if header:
            header = False
            if three_cols:
                cur["opening_balance"], cur["accrued"], cur["to_pay"] = num(r[0]), num(r[1]), num(r[2])
                cur["paid"] = round((cur["opening_balance"] or 0) + (cur["accrued"] or 0) - (cur["to_pay"] or 0), 2)
            else:
                cur["opening_balance"], cur["accrued"], cur["paid"], cur["to_pay"] = num(r[0]), num(r[1]), num(r[2]), num(r[3])


def parse(path, config):
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {"readings": [], "bills": [], "payments": [], "notes": []}
    for sheet in config["sheets"]:
        ws = wb[sheet["name"]]
        kind = sheet["kind"]
        if kind == "journal":
            parse_journal(ws, sheet, out)
        elif kind == "zones_bill":
            parse_zones_bill(ws, sheet, out)
        elif kind == "gas_blocks":
            parse_gas_blocks(ws, sheet, out)
        elif kind in ("simple4", "simple3"):
            parse_simple(ws, sheet, out, three_cols=kind == "simple3")
        else:
            raise SystemExit(f"Unknown sheet kind: {kind}")
    meter_names = {mk: mv["name"] for pv in config["providers"].values() for mk, mv in pv.get("meters", {}).items()}
    for b in out["bills"]:
        for k in ("opening_balance", "paid", "accrued", "to_pay"):
            b[k] = round(b.get(k) or 0.0, 2)
        for ln in b["lines"]:
            ln["label"] = meter_names.get(ln.get("meter"), ln["label"])

    best = {}
    for x in out["readings"]:  # one reading per (meter, date), keep the max
        k = (x["meter"], x["date"])
        if k not in best or x["value"] > best[k]["value"]:
            best[k] = x
    seen, pays = set(), []
    for p in sorted(out["payments"], key=lambda p: p["date"]):
        k = (p["provider"], p["date"], round(p["amount"]))
        if k not in seen:
            seen.add(k)
            pays.append(p)
    return {"profile": config["profile"], "providers": config["providers"], "rent": config.get("rent"),
            "readings": sorted(best.values(), key=lambda x: (x["date"], x["meter"])),
            "bills": sorted(out["bills"], key=lambda b: (b["provider"], b["period"])),
            "payments": pays, "notes": out["notes"]}


if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as f:
        cfg = json.load(f)
    data = parse(sys.argv[1], cfg)
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"readings={len(data['readings'])} bills={len(data['bills'])} payments={len(data['payments'])} "
          f"notes={len(data['notes'])}")
