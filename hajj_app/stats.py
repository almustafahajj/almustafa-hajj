"""إحصاءات الكشف والملخّص المالي — تُحسب عند الطلب ولا تُخزَّن.

- توزيع الحجّاج حسب الجنسية/الجنس/الفندق/الطيران/نوع الغرفة.
- ملخّص مالي: إجمالي قيمة البرامج، المحصّل، والمتبقّي، وعدد غير المكتمل.
- كشف المتأخّرات: من عليه مبلغ متبقٍّ، مرتّباً تنازلياً.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fields import compute_remaining, format_amount, parse_amount
from .mrz import PassportData
from .rooming import room_category


def _amount(value) -> float:
    return parse_amount(str(value or "")) or 0.0


def remaining_amount(rec: PassportData) -> float:
    """المتبقّي على الحاج (قيمة البرنامج − المدفوع)، أو 0 إن لا قيمة برنامج."""
    return _amount(compute_remaining(rec))


# حقول التوزيع المتاحة في اللوحة (المفتاح، العنوان، دالة القيمة)
def _sex(rec):
    return str(rec.sex or "").strip()


def _room(rec):
    return room_category(str(rec.room_type or ""))


GROUPINGS: tuple[tuple[str, str], ...] = (
    ("nationality_ar", "الجنسية"),
    ("sex", "الجنس"),
    ("hotel", "الفندق"),
    ("airline", "الطيران"),
    ("room_type", "نوع الغرفة"),
    ("program", "برنامج الحملة"),
)


def _group_value(rec: PassportData, key: str) -> str:
    if key == "room_type":
        return _room(rec)
    return str(getattr(rec, key, "") or "").strip()


@dataclass
class Bucket:
    """خانة توزيع: القيمة وعددها ونسبتها المئوية."""
    label: str
    count: int
    percent: float


def distribution(records: list[PassportData], key: str) -> list[Bucket]:
    """توزيع الحجّاج حسب حقل، مرتّباً تنازلياً بالعدد. الفارغ يُدرَج «غير محدّد»."""
    counts: dict[str, int] = {}
    for rec in records:
        value = _group_value(rec, key) or "غير محدّد"
        counts[value] = counts.get(value, 0) + 1
    total = len(records) or 1
    buckets = [Bucket(v, c, round(c * 100 / total, 1)) for v, c in counts.items()]
    buckets.sort(key=lambda b: (-b.count, b.label))
    return buckets


@dataclass
class Financials:
    """ملخّص مالي للكشف."""
    count: int = 0
    total: float = 0.0        # إجمالي قيمة البرامج
    paid: float = 0.0         # إجمالي المحصّل
    remaining: float = 0.0    # إجمالي المتبقّي
    unpaid_count: int = 0     # عدد من عليهم متبقٍّ

    @property
    def collected_percent(self) -> float:
        return round(self.paid * 100 / self.total, 1) if self.total else 0.0

    def as_rows(self) -> list[tuple[str, str]]:
        """أزواج (العنوان، القيمة المنسّقة) للعرض."""
        return [
            ("عدد الحجّاج", f"{self.count:,}"),
            ("إجمالي قيمة البرامج", format_amount(self.total) or "0"),
            ("المحصّل", format_amount(self.paid) or "0"),
            ("المتبقّي", format_amount(self.remaining) or "0"),
            ("نسبة التحصيل", f"{self.collected_percent}%"),
            ("عدد غير المكتمل", f"{self.unpaid_count:,}"),
        ]


def financial_summary(records: list[PassportData]) -> Financials:
    """يجمع الأرقام المالية للكشف كاملاً."""
    fin = Financials(count=len(records))
    for rec in records:
        fin.total += _amount(rec.program_value)
        fin.paid += _amount(rec.paid_amount)
        rem = remaining_amount(rec)
        fin.remaining += rem
        if rem > 0.005:
            fin.unpaid_count += 1
    return fin


def outstanding(records: list[PassportData]) -> list[tuple[PassportData, float]]:
    """من عليهم متبقٍّ (> صفر)، مرتّبين تنازلياً بالمبلغ."""
    items = [(r, remaining_amount(r)) for r in records]
    items = [(r, a) for r, a in items if a > 0.005]
    items.sort(key=lambda t: -t[1])
    return items


def financials_by_program(records: list[PassportData]
                          ) -> list[tuple[str, Financials]]:
    """ملخّص مالي لكل برنامج حملة، مرتّباً بالاسم، ثم «بلا برنامج» أخيراً."""
    groups: dict[str, list[PassportData]] = {}
    for rec in records:
        key = str(rec.program or "").strip() or "بلا برنامج"
        groups.setdefault(key, []).append(rec)

    def sort_key(name: str):
        return (name == "بلا برنامج", name)

    return [(name, financial_summary(groups[name]))
            for name in sorted(groups, key=sort_key)]
