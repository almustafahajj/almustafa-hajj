"""فحوص جودة الكشف قبل إصدار الكشوفات الرسمية.

تُحسب **عند الطلب** ولا تُخزَّن في بيانات الحاج:
- **تكرار رقم الجواز** (خطأ شائع عند دمج ملفات إكسل).
- **صلاحية الجواز**: منتهٍ، أو أقل من 6 أشهر من تاريخ السفر (شرط سعودي).
- **نقص بيانات حرجة**: الاسم، رقم الجواز، تاريخ الميلاد.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime

from .mrz import PassportData

MIN_PASSPORT_MONTHS = 6

# أنواع المشكلات (تُستعمل عناوينَ تجميع في التقرير)
KIND_DUPLICATE = "تكرار رقم الجواز"
KIND_PASSPORT = "صلاحية الجواز"
KIND_NAME = "تكرار الاسم"
KIND_PROGRAM = "تطابق البرنامج"
KIND_MISSING = "نقص بيانات حرجة"
KIND_ORDER = (KIND_PASSPORT, KIND_DUPLICATE, KIND_NAME, KIND_PROGRAM, KIND_MISSING)


# ------------------------------------------------ قائمة تحقّق الجاهزية
# بنود جاهزية الحاج للسفر (المفتاح، العنوان المعروض)
READINESS_ITEMS = (
    ("passport", "الجواز"),
    ("visa", "التأشيرة"),
    ("permit", "تصريح الحج"),
    ("vaccination", "التطعيم"),
    ("payment", "اكتمال الدفع"),
    ("contact", "الاسم والهاتف"),
)


def pilgrim_readiness(rec: PassportData, today: date | None = None) -> dict:
    """يعيد {المفتاح: مكتمل؟} لبنود جاهزية الحاج."""
    today = today or date.today()
    from .fields import compute_remaining, parse_amount
    pp = str(rec.passport_number or "").strip()
    exp = parse_date(rec.expiry_date)
    rem = parse_amount(compute_remaining(rec)) or 0.0
    name = str(rec.full_name_ar or rec.full_name_en or "").strip()
    return {
        "passport": bool(pp) and (exp is None or exp >= today),
        "visa": bool(str(rec.visa_number or "").strip()),
        "permit": bool(str(rec.permit_status or "").strip()),
        "vaccination": bool(str(rec.vaccination or "").strip()),
        "payment": rem <= 0,
        "contact": bool(name) and bool(str(rec.phone or "").strip()),
    }


def readiness_percent(rec: PassportData, today: date | None = None) -> int:
    """نسبة جاهزية الحاج (0–100)."""
    checks = pilgrim_readiness(rec, today)
    return round(100 * sum(1 for v in checks.values() if v) / len(checks))


def parse_date(text) -> date | None:
    """يحوّل نصاً إلى تاريخ من الصيغ الشائعة، أو None إن تعذّر."""
    t = str(text or "").strip()
    if not t:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def add_months(d: date, months: int) -> date:
    """يضيف أشهراً إلى تاريخ مع ضبط اليوم في نهاية الشهر القصير."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def travel_date(rec: PassportData) -> date | None:
    """تاريخ السفر المرجعي: المغادرة إن وُجدت، وإلا الوصول."""
    return parse_date(rec.departure_date) or parse_date(rec.arrival_date)


def program_travel_date(rec: PassportData,
                        program_dates: dict | None) -> date | None:
    """تاريخ سفر البرنامج المختار للحاج (من خريطة الاسم→التاريخ)، أو None."""
    if not program_dates:
        return None
    return program_dates.get(str(rec.program or "").strip())


def passport_issue(rec: PassportData, today: date,
                   program_dates: dict | None = None) -> str | None:
    """مشكلة صلاحية الجواز إن وُجدت، وإلا None.

    منتهٍ إذا كان تاريخ الانتهاء قبل اليوم، أو «أقل من 6 أشهر» إذا كان
    قبل مرور 6 أشهر من **تاريخ السفر**. تاريخ السفر يُؤخذ من سجل الحاج
    (المغادرة/الوصول) وإلا من **تاريخ سفر برنامج الحملة المختار للحاج**
    (``program_dates``)، ولا يُرجَع لتاريخ اليوم إلا عند غياب الاثنين معاً.
    """
    exp = parse_date(rec.expiry_date)
    if exp is None:
        return None                       # لا تاريخ — يُعالَج ضمن النواقص
    if exp < today:
        return "الجواز منتهٍ"
    ref = travel_date(rec) or program_travel_date(rec, program_dates) or today
    if exp < add_months(ref, MIN_PASSPORT_MONTHS):
        return f"صلاحيته أقل من {MIN_PASSPORT_MONTHS} أشهر من تاريخ السفر"
    return None


def duplicate_groups(records: list[PassportData]) -> dict[str, list[int]]:
    """يجمع فهارس السجلات التي تتشارك **رقم جواز** واحداً (غير الفارغ)."""
    seen: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        pp = str(rec.passport_number or "").strip().upper()
        if pp:
            seen.setdefault(pp, []).append(i)
    return {pp: idxs for pp, idxs in seen.items() if len(idxs) > 1}


def _norm_name(text) -> str:
    """يوحّد الاسم للمقارنة: يزيل الفراغات الزائدة ويوحّد الحالة."""
    return " ".join(str(text or "").split()).lower()


def name_duplicate_groups(records: list[PassportData]) -> dict[str, list[int]]:
    """يجمع فهارس السجلات المتطابقة **بالاسم** (عربي أو إنجليزي).

    يُستبعَد ما كان تكراراً لرقم جواز واحد (يُغطّى في تكرار الجواز)، فيبقى
    الاسم المكرّر بجوازات مختلفة أو ناقصة — وهو ما يستحقّ المراجعة.
    """
    by_name: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        key = _norm_name(rec.full_name_ar) or _norm_name(rec.full_name_en)
        if key:
            by_name.setdefault(key, []).append(i)
    out: dict[str, list[int]] = {}
    for key, idxs in by_name.items():
        if len(idxs) < 2:
            continue
        pps = [str(records[i].passport_number or "").strip().upper() for i in idxs]
        if len(set(pps)) == 1 and pps[0]:      # كلهم نفس الجواز = تكرار جواز فقط
            continue
        out[key] = idxs
    return out


def missing_critical(rec: PassportData) -> list[str]:
    """الحقول الحرجة الناقصة (اسم/جواز/ميلاد)."""
    miss: list[str] = []
    if not (str(rec.full_name_ar or "").strip() or str(rec.full_name_en or "").strip()):
        miss.append("اسم الحاج")
    if not str(rec.passport_number or "").strip():
        miss.append("رقم الجواز")
    if not str(rec.birth_date or "").strip():
        miss.append("تاريخ الميلاد")
    return miss


@dataclass
class Issue:
    """مشكلة واحدة في سجل واحد."""
    index: int                # فهرس السجل في القائمة الأصلية
    name: str
    passport: str
    kind: str                 # أحد KIND_*
    detail: str


@dataclass
class QualityReport:
    """نتيجة فحص الجودة: قائمة المشكلات + إجماليات."""
    issues: list[Issue] = field(default_factory=list)
    total: int = 0

    @property
    def clean(self) -> bool:
        return not self.issues

    @property
    def flagged_indices(self) -> set[int]:
        return {iss.index for iss in self.issues}

    def by_kind(self) -> dict[str, list[Issue]]:
        groups: dict[str, list[Issue]] = {k: [] for k in KIND_ORDER}
        for iss in self.issues:
            groups.setdefault(iss.kind, []).append(iss)
        return {k: v for k, v in groups.items() if v}

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.by_kind().items()}


_ROOM_COST_KEY = {1: "cost_single", 2: "cost_double",
                  3: "cost_triple", 4: "cost_quad"}


def program_issue(rec: PassportData, programs: dict | None) -> str | None:
    """مشكلة تطابق البرنامج: برنامج غير معرّف، أو غرفة غير مسعّرة فيه."""
    if not programs:
        return None
    name = str(rec.program or "").strip()
    if not name:
        return None
    prog = programs.get(name)
    if prog is None:
        return "البرنامج المختار غير معرّف"
    rt = str(rec.room_type or "").strip()
    if not rt:
        return None
    from .fields import parse_amount
    from .rooming import room_capacity
    key = _ROOM_COST_KEY.get(room_capacity(rt))
    if key and not (parse_amount(getattr(prog, key, "")) or 0):
        return f"نوع الغرفة ({rt}) غير مسعّر في {name}"
    return None


def check_records(records: list[PassportData], today: date | None = None,
                  programs: dict | None = None) -> QualityReport:
    """يفحص الكشف كاملاً ويعيد تقريراً بكل المشكلات.

    ``programs`` خريطة {اسم البرنامج: البرنامج} تُستخدم لمرجع تاريخ السفر
    (قاعدة الـ6 أشهر) ولتدقيق تطابق البرنامج (تسعير الغرفة).
    """
    today = today or date.today()
    program_dates: dict = {}
    for pname, prog in (programs or {}).items():
        d = parse_date(getattr(prog, "travel_date", ""))
        if d:
            program_dates[pname] = d

    dups = duplicate_groups(records)
    dup_of = {i: pp for pp, idxs in dups.items() for i in idxs}
    name_dups = name_duplicate_groups(records)
    name_of = {i: key for key, idxs in name_dups.items() for i in idxs}

    issues: list[Issue] = []
    for i, rec in enumerate(records):
        name = rec.full_name_ar or rec.full_name_en or "—"
        pp = str(rec.passport_number or "").strip().upper()
        # الجواز أولاً (الأخطر)
        pi = passport_issue(rec, today, program_dates)
        if pi:
            issues.append(Issue(i, name, pp, KIND_PASSPORT, pi))
        if i in dup_of:
            issues.append(Issue(i, name, pp, KIND_DUPLICATE,
                                f"رقم الجواز مكرّر ({len(dups[dup_of[i]])} مرات)"))
        if i in name_of:
            issues.append(Issue(i, name, pp, KIND_NAME,
                                f"الاسم مكرّر ({len(name_dups[name_of[i]])} مرات)"))
        prg = program_issue(rec, programs)
        if prg:
            issues.append(Issue(i, name, pp, KIND_PROGRAM, prg))
        for label in missing_critical(rec):
            issues.append(Issue(i, name, pp, KIND_MISSING, label))
    return QualityReport(issues=issues, total=len(records))


def summary_text(report: QualityReport) -> str:
    """سطر ملخّص موجز للتقرير (للحالة أو رسالة سريعة)."""
    if report.clean:
        return "لا مشكلات — الكشف جاهز ✓"
    parts = [f"{k}: {n}" for k, n in report.counts().items()]
    return "  •  ".join(parts)
