# -*- coding: utf-8 -*-
"""البحث السريع الشامل في البورتال: المعتمرون/الحجّاج، البرامج والباقات، عروض
الأسعار والتسعيرات، والمستندات المؤرشفة — في النظام الحالي (حج أو عمرة).

المطابقة متسامحة مع الكتابة العربية (أ/ا، ة/ه، ى/ي) والحروف الكبيرة/الصغيرة.
"""
from __future__ import annotations

LIMIT = 30


def norm(text) -> str:
    from hajj_app.umrah import _norm_ar
    return _norm_ar(text)


def _hit(q: str, *values) -> bool:
    hay = " ".join(norm(v) for v in values if v)
    return all(part in hay for part in q.split())


def search(q: str, records, settings, mode: str, docs=None) -> list:
    """يعيد مجموعات: ``[{"title", "icon", "items": [{"kind", "ref", "title", "sub"}]}]``."""
    q = norm(q)
    if len(q) < 2:
        return []
    groups = []

    people = []
    for i, r in enumerate(records):
        if _hit(q, r.full_name_ar, r.full_name_en, r.passport_number, r.phone,
                r.reference_number, r.family_number, getattr(r, "pnr", ""),
                getattr(r, "visa_number", "")):
            grp = getattr(r, "trip" if mode == "umrah" else "program", "") or ""
            people.append({"kind": "record", "ref": i,
                           "title": r.full_name_ar or r.full_name_en or "—",
                           "sub": " · ".join(x for x in (r.passport_number, r.phone, grp,
                                                          r.reference_number) if x)})
    groups.append({"title": "المعتمرون" if mode == "umrah" else "الحجّاج",
                   "icon": "👤", "items": people})

    if mode == "umrah":
        from hajj_app import umrah
        trips = umrah.load_trips(settings)
        progs = [{"kind": "program", "ref": t.code,
                  "title": f"{t.code} — {t.name}" if t.name else t.code,
                  "sub": " · ".join(x for x in (t.package, t.airline, t.depart_date,
                                                 t.makkah_hotel) if x)}
                 for t in trips
                 if _hit(q, t.code, t.name, t.package, t.airline, t.flight_out,
                         t.flight_ret, t.flight_pnr, t.makkah_hotel, t.madinah_hotel,
                         getattr(t, "depart_city", ""))]
        groups.append({"title": "البرامج", "icon": "🗂", "items": progs})
        pk = [{"kind": "package", "ref": p, "title": p, "sub": "باقة برامج"}
              for p in umrah.load_packages(settings) if _hit(q, p)]
        groups.append({"title": "الباقات", "icon": "📦", "items": pk})
        quotes = []
        for code, lst in (settings.get("umrah_quotes") or {}).items():
            for x in lst if isinstance(lst, list) else []:
                if isinstance(x, dict) and x.get("number") and _hit(
                        q, x.get("number"), x.get("addressed_to"), x.get("title"),
                        x.get("date")):
                    quotes.append({"kind": "quote", "ref": (code, x["number"]),
                                   "title": f"{x['number']} — {x.get('addressed_to') or x.get('title') or 'عرض سعر'}",
                                   "sub": x.get("date", "")})
        groups.append({"title": "عروض الأسعار", "icon": "💼", "items": quotes})
        pr = [{"kind": "pricing", "ref": p.get("number"),
               "title": f"{p.get('number')} — {p.get('title') or 'تسعير'}",
               "sub": p.get("date", "")}
              for p in umrah.load_pricings(settings)
              if p.get("number") and _hit(q, p.get("number"), p.get("title"))]
        groups.append({"title": "التسعيرات", "icon": "🧮", "items": pr})

    arch = [{"kind": "archive", "ref": d.get("id"),
             "title": f"{d.get('number') or '—'} — {d.get('name') or d.get('title') or ''}",
             "sub": (d.get("ts") or "").replace("T", " ")[:16]}
            for d in reversed(docs or [])
            if d.get("id") and _hit(q, d.get("number"), d.get("name"), d.get("title"))]
    groups.append({"title": "المستندات المؤرشفة", "icon": "🗄", "items": arch})

    for g in groups:
        g["total"] = len(g["items"])
        g["items"] = g["items"][:LIMIT]
    return [g for g in groups if g["total"]]
