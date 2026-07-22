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
KIND_MISSING = "نقص بيانات حرجة"
KIND_ORDER = (KIND_PASSPORT, KIND_DUPLICATE, KIND_MISSING)


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


def passport_issue(rec: PassportData, today: date) -> str | None:
    """مشكلة صلاحية الجواز إن وُجدت، وإلا None.

    منتهٍ إذا كان تاريخ الانتهاء قبل اليوم، أو «أقل من 6 أشهر» إذا كان
    قبل مرور 6 أشهر من تاريخ السفر (أو من اليوم إن غاب تاريخ السفر).
    """
    exp = parse_date(rec.expiry_date)
    if exp is None:
        return None                       # لا تاريخ — يُعالَج ضمن النواقص
    if exp < today:
        return "الجواز منتهٍ"
    ref = travel_date(rec) or today
    if exp < add_months(ref, MIN_PASSPORT_MONTHS):
        return f"صلاحيته أقل من {MIN_PASSPORT_MONTHS} أشهر من السفر"
    return None


def duplicate_groups(records: list[PassportData]) -> dict[str, list[int]]:
    """يجمع فهارس السجلات التي تتشارك **رقم جواز** واحداً (غير الفارغ)."""
    seen: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        pp = str(rec.passport_number or "").strip().upper()
        if pp:
            seen.setdefault(pp, []).append(i)
    return {pp: idxs for pp, idxs in seen.items() if len(idxs) > 1}


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


def check_records(records: list[PassportData], today: date | None = None) -> QualityReport:
    """يفحص الكشف كاملاً ويعيد تقريراً بكل المشكلات."""
    today = today or date.today()
    dups = duplicate_groups(records)
    dup_of = {i: pp for pp, idxs in dups.items() for i in idxs}

    issues: list[Issue] = []
    for i, rec in enumerate(records):
        name = rec.full_name_ar or rec.full_name_en or "—"
        pp = str(rec.passport_number or "").strip().upper()
        # الجواز أولاً (الأخطر)
        pi = passport_issue(rec, today)
        if pi:
            issues.append(Issue(i, name, pp, KIND_PASSPORT, pi))
        if i in dup_of:
            issues.append(Issue(i, name, pp, KIND_DUPLICATE,
                                f"رقم الجواز مكرّر ({len(dups[dup_of[i]])} مرات)"))
        for label in missing_critical(rec):
            issues.append(Issue(i, name, pp, KIND_MISSING, label))
    return QualityReport(issues=issues, total=len(records))


def summary_text(report: QualityReport) -> str:
    """سطر ملخّص موجز للتقرير (للحالة أو رسالة سريعة)."""
    if report.clean:
        return "لا مشكلات — الكشف جاهز ✓"
    parts = [f"{k}: {n}" for k, n in report.counts().items()]
    return "  •  ".join(parts)
