# -*- coding: utf-8 -*-
"""إشعارات البورتال: ما يحتاج انتباهاً الآن (امتلاء، غرف، مغادرة قريبة، جوازات،
سداد متأخّر). تُحسب من البيانات مباشرة — لا شيء يُخزَّن.

كل إشعار: ``{"level": danger|warn|info, "icon", "text", "kind", "ref", "date"}``
و``kind/ref`` يحوّلهما الخادم إلى رابط الصفحة المناسبة.
"""
from __future__ import annotations

from datetime import date, timedelta

_LEVELS = {"danger": 0, "warn": 1, "info": 2}
SOON_DAYS = 14          # «مغادرة قريبة»
PAY_DAYS = 30           # متابعة السداد قبل المغادرة بشهر


def _d(text):
    from hajj_app.quality import parse_date
    try:
        return parse_date(text)
    except Exception:                              # noqa: BLE001
        return None


def _int(text) -> int:
    try:
        return int(float(str(text or "").strip() or 0))
    except ValueError:
        return 0


def _passport_bad(rec, dep, today) -> bool:
    """منتهٍ، أو ينتهي قبل ٦ أشهر من السفر (شرط دخول السعودية)."""
    from hajj_app.umrah import _add_months
    exp = _d(getattr(rec, "expiry_date", ""))
    if not exp:
        return False
    return exp < today or bool(dep and exp < _add_months(dep, 6))


def _owing(recs) -> tuple[int, float]:
    from hajj_app.stats import remaining_amount
    vals = [remaining_amount(r) for r in recs]
    owe = [v for v in vals if v > 0.005]
    return len(owe), sum(owe)


def _a(level, icon, text, kind, ref="", when=None) -> dict:
    return {"level": level, "icon": icon, "text": text, "kind": kind, "ref": ref,
            "date": when.isoformat() if when else ""}


def _common(out, label, ref, recs, dep, today, kind):
    """مغادرة قريبة + جوازات + سداد — مشتركة بين برامج الحج والعمرة."""
    if dep is None:
        return
    days = (dep - today).days
    if 0 <= days <= SOON_DAYS:
        when = "اليوم" if days == 0 else "غداً" if days == 1 else f"بعد {days} يوماً"
        out.append(_a("info", "✈️", f"مغادرة «{label}» {when} ({dep.isoformat()}) — "
                      f"{len(recs)} شخصاً", kind, ref, dep))
    bad = sum(1 for r in recs if _passport_bad(r, dep, today))
    if bad:
        out.append(_a("warn", "🛂", f"{bad} جوازاً في «{label}» منتهٍ أو ينتهي قبل ٦ "
                      "أشهر من السفر", "quality", "", dep))
    if days <= PAY_DAYS:
        n, total = _owing(recs)
        if n:
            from hajj_app.fields import format_amount
            out.append(_a("warn" if days > 7 else "danger", "💰",
                          f"{n} لم يُكملوا السداد في «{label}» (المتبقّي "
                          f"{format_amount(total)}) — المغادرة {dep.isoformat()}",
                          "finance", "", dep))


def umrah_alerts(records, settings, today: date | None = None) -> list:
    from hajj_app import umrah
    today = today or date.today()
    trips = umrah.load_trips(settings)
    pools = umrah.room_pools(trips)
    out: list = []
    for t in trips:
        dep = _d(t.depart_date)
        ret = _d(t.return_date)
        if (ret or dep) and (ret or dep) < today:          # برنامج انتهى
            continue
        recs = [r for r in umrah.trip_pilgrims(records, t.code)
                if str(getattr(r, "status", "") or "").strip() != "ملغى"]
        label = f"{t.code} — {t.name}" if t.name else t.code
        cap, n = _int(t.capacity), len(recs)
        if cap and n > cap:
            out.append(_a("danger", "🪑", f"تجاوز السعة في «{label}»: {n} من {cap} مقعداً",
                          "program", t.code, dep))
        elif cap and n == cap:
            out.append(_a("info", "✅", f"اكتملت مقاعد «{label}» ({cap})",
                          "program", t.code, dep))
        if pools[t.code][0].code == t.code:                 # الغرف مرّة لكل مجموعة
            shared = [p.code for p in pools[t.code][1:]]
            tag = f"«{label}»" + (f" ومن يشاركه ({'، '.join(shared)})" if shared else "")
            for city, avail, _used, left in umrah.trip_rooms_left(
                    t, records, pool=pools[t.code]):
                if left < 0:
                    out.append(_a("danger", "🛏", f"زيادة {-left} غرفة في فندق {city} — {tag}",
                                  "program", t.code, dep))
                elif left <= 2 and avail >= 5:
                    out.append(_a("warn", "🛏", f"تبقّت {left} غرفة فقط في فندق {city} — {tag}",
                                  "program", t.code, dep))
        _common(out, label, t.code, recs, dep, today, "program")
    return _sorted(out)


def hajj_alerts(records, settings, today: date | None = None) -> list:
    from hajj_app import programs as hp
    today = today or date.today()
    out: list = []
    # برامج الحج بأسمائها الثابتة (البرنامج الأول/الثاني/الثالث) بالترتيب
    for name, p in zip(hp.PROGRAM_NAMES, hp.load_programs(settings)):
        dep = _d(p.travel_date)
        if dep and dep < today:
            continue
        recs = [r for r in records if str(getattr(r, "program", "") or "") == name]
        if recs:
            _common(out, name, name, recs, dep, today, "travel")
    return _sorted(out)


def _sorted(out: list) -> list:
    return sorted(out, key=lambda a: (_LEVELS.get(a["level"], 9), a["date"] or "9999"))
