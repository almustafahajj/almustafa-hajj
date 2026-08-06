"""مساعد «اسأل بياناتك»: يجيب أسئلة عربية بسيطة من كشف الموسم — بلا إنترنت.

محرّك قواعد خفيف يتعرّف على نيّة السؤال (المتأخرون، المتبقّي، المحصّل،
عدد المعتمرين، الإشغال، أفضل/أضعف برنامج، صلاحية الجوازات...) ويحسب
الجواب من البرامج والمعتمرين مباشرةً. لا يعتمد على أي خدمة خارجية،
فيعمل داخل البرنامج المكتبي دون اتصال.

الدالة الرئيسية ``answer(question, trips, records)`` تعيد قاموساً موحّداً
تعرضه الواجهة: عنوان، وسطر إجابة كبير، وربّما جدول تفاصيل.
"""

from __future__ import annotations

import re

from . import umrah
from .fields import format_amount, parse_amount

_TASHKEEL = re.compile(r"[ؗ-ًؚ-ْٰـ]")


def _norm(s) -> str:
    """تطبيع عربي: حذف التشكيل، توحيد الألف/الياء/التاء المربوطة، وإزالة الترقيم."""
    s = _TASHKEEL.sub("", str(s or ""))
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"),
                 ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        s = s.replace(a, b)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def _has(q: str, *words) -> bool:
    return any(w in q for w in words)


def _val(r) -> float:
    return parse_amount(getattr(r, "program_value", "")) or 0.0


def _paid(r) -> float:
    return parse_amount(getattr(r, "paid_amount", "")) or 0.0


def _rem(r) -> float:
    return _val(r) - _paid(r)


def _name(r) -> str:
    return (getattr(r, "full_name_ar", "") or getattr(r, "passport_number", "")
            or "—")


def _aed(n: float) -> str:
    return f"{format_amount(n)} AED"


def _match_programs(q: str, trips: list) -> list:
    """البرامج التي وردت أسماؤها (أو كلمة منها) في السؤال — لتقييد النطاق."""
    qn = _norm(q)
    hits = []
    for t in trips:
        label = _norm(t.name or t.code)
        words = [w for w in label.split() if len(w) >= 3
                 and w not in _STOP]
        if label and label in qn:
            hits.append(t)
        elif any(w in qn for w in words):
            hits.append(t)
    return hits


_STOP = {"برنامج", "الباقه", "الباقة", "عمره", "عمرة", "موسم", "رحله"}


def _scope(q: str, trips: list, records: list):
    """يقيّد المعتمرين على البرامج المذكورة في السؤال إن وُجدت."""
    progs = _match_programs(q, trips)
    if not progs:
        return records, trips, ""
    codes = {t.code for t in progs}
    recs = [r for r in records if str(getattr(r, "trip", "") or "") in codes]
    label = "، ".join(t.name or t.code for t in progs)
    return recs, progs, label


def _prog_name_map(trips: list) -> dict:
    return {t.code: (t.name or t.code) for t in trips}


def _stat(title, headline, note="", headers=None, rows=None):
    return {"kind": "list" if rows else "stat", "title": title,
            "headline": headline, "note": note,
            "headers": headers, "rows": rows}


EXAMPLES = (
    "مين ما سدّد؟",
    "كم المتبقّي على رمضان؟",
    "كم معتمر هذا الموسم؟",
    "كم المبلغ المحصّل؟",
    "كم مقعد باقٍ؟",
    "أعلى برنامج تحصيلاً؟",
    "جوازات تنتهي قريباً؟",
)


def _help():
    return {"kind": "help", "title": "اسأل بياناتك",
            "headline": "اكتب سؤالك بالعربية عن معتمري الموسم وحساباتهم.",
            "note": "جرّب أحد الأمثلة:", "headers": None,
            "rows": None, "examples": list(EXAMPLES)}


def answer(question: str, trips: list, records: list, *, season: str = "") -> dict:
    """يحلّل السؤال ويعيد جواباً موحّداً محسوباً من بيانات الموسم."""
    q = _norm(question)
    if not q:
        return _help()

    names = _prog_name_map(trips)
    scoped, sprogs, slabel = _scope(question, trips, records)
    tail = f" — {slabel}" if slabel else ""

    # 1) المتأخرون عن السداد (قائمة أسماء)
    if _has(q, "ما سدد", "لم يسدد", "ما دفع", "لم يدفع", "غير مسدد", "متاخر",
            "المتاخرين", "باقي علي", "ما خلص", "مدين", "الديون", "لم يكمل",
            "ناقص", "عليهم"):
        late = [r for r in scoped if _rem(r) > 0.5]
        late.sort(key=_rem, reverse=True)
        rows = [[_name(r), names.get(getattr(r, "trip", ""), "—"),
                 _aed(_rem(r))] for r in late]
        total = sum(_rem(r) for r in late)
        out = _stat(
            "المتأخرون عن السداد" + tail,
            f"{len(late)} معتمراً · المتبقّي {_aed(total)}" if late
            else "الحمد لله — لا متأخرات، الجميع سدّد بالكامل.",
            note=f"مرتّبون تنازلياً حسب المبلغ المتبقّي{tail}" if late else "",
            headers=["المعتمر", "البرنامج", "المتبقّي"] if late else None,
            rows=rows or None)
        if late:                       # قائمة قابلة للتنفيذ: تذكير واتساب
            out["action"] = "whatsapp_due"
            out["records"] = late
        return out

    # 2) المبلغ المتبقّي (رقم)
    if _has(q, "المتبقي", "كم باقي", "كم المتبقي", "الباقي", "المتبق",
            "لم يحصل", "المستحق") and not _has(q, "مقعد", "مقاعد"):
        total = sum(_rem(r) for r in scoped if _rem(r) > 0)
        cnt = sum(1 for r in scoped if _rem(r) > 0.5)
        return _stat("المبلغ المتبقّي" + tail, _aed(total),
                     note=f"على {cnt} معتمراً لم يكملوا السداد{tail}")

    # 3) المبلغ المحصّل (رقم)
    if _has(q, "المحصل", "حصلنا", "المدفوع", "الوارد", "كم دخل", "المقبوض",
            "الايراد المحصل"):
        total = sum(_paid(r) for r in scoped)
        val = sum(_val(r) for r in scoped)
        pct = (total / val * 100) if val else 0
        return _stat("المبلغ المحصّل" + tail, _aed(total),
                     note=f"{pct:.0f}٪ من إجمالي {_aed(val)}{tail}")

    # 4) إجمالي الإيراد / قيمة البرامج (رقم)
    if _has(q, "الايراد", "الاجمالي", "قيمه البرامج", "مجموع", "الدخل الكلي",
            "اجمالي البرامج", "كم الايراد"):
        val = sum(_val(r) for r in scoped)
        return _stat("إجمالي الإيراد المتوقّع" + tail, _aed(val),
                     note=f"قيمة برامج {len(scoped)} معتمراً{tail}")

    # 5) عدد المعتمرين (مع تصفية بالجنسية إن ذُكرت)
    if _has(q, "كم معتمر", "عدد المعتمرين", "كم حاج", "كم شخص", "كم راكب",
            "كم عدد", "كام معتمر"):
        nat = _match_nationality(q, scoped)
        if nat:
            n = sum(1 for r in scoped if _norm(
                getattr(r, "nationality_ar", "") or getattr(r, "nationality", "")
            ) == _norm(nat))
            return _stat(f"معتمرو جنسية {nat}" + tail, f"{n} معتمراً",
                         note=f"من أصل {len(scoped)} معتمراً{tail}")
        return _stat("عدد المعتمرين" + tail, f"{len(scoped)} معتمراً",
                     note=(f"في {len(sprogs)} برنامجاً" if not slabel else tail))

    # 6) عدد البرامج
    if _has(q, "كم برنامج", "عدد البرامج", "كم البرامج", "كام برنامج"):
        return _stat("عدد برامج الموسم", f"{len(trips)} برنامجاً",
                     note=f"موسم {season}" if season else "")

    # 7) الإشغال والمقاعد
    if _has(q, "اشغال", "مقعد", "مقاعد", "السعه", "باقي مقاعد",
            "المتاح", "شواغر", "كم باق"):
        used = free = cap = 0
        for t in (sprogs if slabel else trips):
            c = int(parse_amount(t.capacity) or 0)
            n = len(umrah.trip_pilgrims(records, t.code))
            cap += c
            used += n
            free += max(c - n, 0)
        pct = (used / cap * 100) if cap else 0
        return _stat("الإشغال والمقاعد" + tail,
                     f"{used} / {cap} مقعداً ({pct:.0f}٪)",
                     note=f"المتبقّي {free} مقعداً شاغراً{tail}")

    # 8) أعلى / أفضل برنامج تحصيلاً
    if _has(q, "افضل", "اعلي", "احسن", "اكثر") and _has(
            q, "تحصيل", "برنامج", "دفع", "سداد", "معتمر", "عدد"):
        best = _rank_programs(trips, records)
        if not best:
            return _stat("أفضل برنامج", "لا توجد برامج بعد.")
        top = best[0]
        return _stat("أعلى البرامج تحصيلاً",
                     f"{top['name']} · {top['pct']:.0f}٪",
                     note=f"{top['count']} معتمراً · حُصّل {_aed(top['paid'])} "
                          f"من {_aed(top['total'])}",
                     headers=["البرنامج", "التحصيل", "المعتمرون"],
                     rows=[[b["name"], f"{b['pct']:.0f}٪", str(b["count"])]
                           for b in best])

    # 9) أضعف / أقل برنامج تحصيلاً
    if _has(q, "اقل", "اضعف", "اسوا", "اخر") and _has(
            q, "تحصيل", "برنامج", "سداد"):
        best = _rank_programs(trips, records)
        if not best:
            return _stat("أضعف برنامج", "لا توجد برامج بعد.")
        low = best[-1]
        return _stat("أضعف البرامج تحصيلاً",
                     f"{low['name']} · {low['pct']:.0f}٪",
                     note=f"المتبقّي {_aed(low['total'] - low['paid'])}",
                     headers=["البرنامج", "التحصيل", "المتبقّي"],
                     rows=[[b["name"], f"{b['pct']:.0f}٪",
                            _aed(b["total"] - b["paid"])]
                           for b in reversed(best)])

    # 10) صلاحية الجوازات (منتهية أو تنتهي قبل ٦ أشهر من السفر)
    if _has(q, "جواز", "جوازات", "صلاحيه", "تنتهي", "منتهي", "منتهيه",
            "الانتهاء", "تجديد"):
        depart = {t.code: t.depart_date for t in trips}
        flagged = []
        for r in scoped:
            code = getattr(r, "trip", "")
            if umrah.passport_expired(r):
                status = "منتهٍ"
            elif umrah.passport_expiry_soon(r, depart.get(code, ""), 6):
                status = "أقل من ٦ أشهر"
            else:
                continue
            flagged.append([_name(r), names.get(code, "—"),
                            getattr(r, "expiry_date", "") or "—", status])
        return _stat(
            "جوازات تحتاج انتباهاً" + tail,
            f"{len(flagged)} جوازاً يحتاج المتابعة" if flagged
            else "كل الجوازات سارية وصالحة للسفر.",
            note="منتهية الصلاحية أو تنتهي قبل ٦ أشهر من السفر" if flagged else "",
            headers=["المعتمر", "البرنامج", "انتهاء الجواز", "الحالة"]
            if flagged else None,
            rows=flagged or None)

    # 11) توزيع الجنسيات
    if _has(q, "جنسيه", "الجنسيه", "جنسيات", "الجنسيات", "توزيع الجنسيات"):
        counts = {}
        for r in scoped:
            nat = (str(getattr(r, "nationality_ar", "") or "").strip()
                   or str(getattr(r, "nationality", "") or "").strip() or "غير محدّد")
            counts[nat] = counts.get(nat, 0) + 1
        ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        return _stat(
            "توزيع الجنسيات" + tail,
            f"{len(ordered)} جنسية · {len(scoped)} معتمراً",
            note="عدد المعتمرين حسب الجنسية" + tail,
            headers=["الجنسية", "العدد"] if ordered else None,
            rows=[[nat, str(n)] for nat, n in ordered] or None)

    # 12) بطاقة معتمرٍ بعينه (بالاسم) — إن ذُكر اسم يطابق أحد المعتمرين
    who = _match_pilgrim(question, scoped)
    if who is not None:
        code = getattr(who, "trip", "")
        rem = _rem(who)
        rows = [["البرنامج", names.get(code, "—")],
                ["قيمة البرنامج", _aed(_val(who))],
                ["المدفوع", _aed(_paid(who))],
                ["المتبقّي", _aed(rem)],
                ["الحالة", "سدّد بالكامل ✓" if rem <= 0.5 else "عليه متبقٍّ"],
                ["الجوال", str(getattr(who, "phone", "") or "—")]]
        out = _stat(
            "بطاقة المعتمر",
            f"{_name(who)} — " + ("سدّد بالكامل" if rem <= 0.5
                                  else f"متبقٍّ {_aed(rem)}"),
            note=names.get(code, ""),
            headers=["البند", "القيمة"], rows=rows)
        if rem > 0.5:
            out["action"] = "whatsapp_due"
            out["records"] = [who]
        return out

    return _help()


def _match_nationality(question: str, records: list):
    """جنسية وردت في السؤال وتطابق جنسية أحد المعتمرين — أو None."""
    qn = _norm(question)
    seen = {}
    for r in records:
        nat = (str(getattr(r, "nationality_ar", "") or "").strip()
               or str(getattr(r, "nationality", "") or "").strip())
        if nat:
            seen.setdefault(_norm(nat), nat)
    for norm_nat, original in seen.items():
        if norm_nat and re.search(r"(?:^| )" + re.escape(norm_nat) + r"(?:$| )", qn):
            return original
    return None


def _match_pilgrim(question: str, records: list):
    """أقرب معتمرٍ اسمه (أو جزء منه) وارد في السؤال — أو None."""
    qn = _norm(question)
    best, best_score = None, 0
    for r in records:
        toks = [t for t in _norm(getattr(r, "full_name_ar", "")).split()
                if len(t) >= 3]
        score = sum(1 for t in toks
                    if re.search(r"(?:^| )" + re.escape(t) + r"(?:$| )", qn))
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 1 else None


def due_reminder(rec, program_name: str = "",
                 company_ar: str = "المصطفى للحج والعمرة") -> str:
    """رسالة تذكير سداد عربية مهذّبة لمعتمرٍ متأخّر (لواتساب)."""
    prog = f"«{program_name}»" if program_name else "برنامج العمرة"
    return (f"السلام عليكم ورحمة الله، {_name(rec)} 🌙\n\n"
            f"نذكّركم بلطف بأنّ المبلغ المتبقّي على {prog} هو {_aed(_rem(rec))}.\n"
            f"يسعدنا إكماله لتأكيد حجزكم وضمان مقعدكم بإذن الله.\n\n"
            f"مع خالص التقدير،\n{company_ar}")


def due_wa_link(rec, program_name: str = "",
                company_ar: str = "المصطفى للحج والعمرة",
                cc: str = "971"):
    """رابط واتساب مع رسالة التذكير، أو None إن كان رقم الهاتف غير صالح."""
    from .whatsapp import wa_link
    return wa_link(getattr(rec, "phone", ""),
                   due_reminder(rec, program_name, company_ar), cc)


def _rank_programs(trips: list, records: list) -> list:
    """البرامج مرتّبة تنازلياً حسب نسبة التحصيل (يتجاهل ما بلا قيمة)."""
    out = []
    for t in trips:
        pil = umrah.trip_pilgrims(records, t.code)
        total = sum(_val(r) for r in pil)
        paid = sum(_paid(r) for r in pil)
        if total <= 0:
            continue
        out.append({"name": t.name or t.code, "count": len(pil),
                    "total": total, "paid": paid, "pct": paid / total * 100})
    out.sort(key=lambda d: d["pct"], reverse=True)
    return out
