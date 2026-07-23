# -*- coding: utf-8 -*-
"""اختبار الإحصاءات والملخّص المالي وكشف المتأخّرات."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.stats import (
    distribution, financial_summary, outstanding, remaining_amount,
)
from hajj_app.mrz import PassportData


def rec(**kw):
    return PassportData(**kw)


print("=== التوزيع حسب حقل ===")
recs = [
    rec(nationality_ar="الإمارات", sex="ذكر", hotel="الصفوة", room_type="رباعية 2"),
    rec(nationality_ar="الإمارات", sex="أنثى", hotel="الصفوة", room_type="رباعية 3"),
    rec(nationality_ar="مصر", sex="ذكر", hotel="كونراد", room_type="ثلاثية 1"),
    rec(nationality_ar="", sex="ذكر", hotel="", room_type=""),           # غير محدّد
]
nat = distribution(recs, "nationality_ar")
assert nat[0].label == "الإمارات" and nat[0].count == 2, nat
assert nat[0].percent == 50.0, nat[0].percent
labels = {b.label for b in nat}
assert "غير محدّد" in labels, labels
# نوع الغرفة يُجمع بالفئة (رباعية 2 و3 -> رباعي)
room = {b.label: b.count for b in distribution(recs, "room_type")}
assert room.get("رباعي") == 2, room
print(f"  OK: الجنسية {[(b.label, b.count) for b in nat]}؛ الغرف {room}")

print("\n=== الملخّص المالي ===")
recs = [
    rec(program_value="15,000", paid_amount="15,000"),   # مكتمل
    rec(program_value="20000", paid_amount="5000"),       # متبقٍّ 15000
    rec(program_value="10000", paid_amount=""),           # متبقٍّ 10000
    rec(program_value="", paid_amount="3000"),            # بلا قيمة برنامج -> لا متبقٍّ
]
fin = financial_summary(recs)
assert fin.count == 4
assert fin.total == 45000.0, fin.total          # 15+20+10 آلاف
assert fin.paid == 23000.0, fin.paid            # 15+5+3 آلاف
assert fin.remaining == 25000.0, fin.remaining  # 0+15+10 آلاف
assert fin.unpaid_count == 2, fin.unpaid_count
assert fin.collected_percent == round(23000 * 100 / 45000, 1)
rows = dict(fin.as_rows())
assert rows["المحصّل"] == "23,000" and rows["المتبقّي"] == "25,000", rows
print(f"  OK: إجمالي {fin.total:,.0f}، محصّل {fin.paid:,.0f}، متبقٍّ {fin.remaining:,.0f}, غير مكتمل {fin.unpaid_count}")

print("\n=== كشف المتأخّرات (مرتّب تنازلياً) ===")
owe = outstanding(recs)
amounts = [a for _r, a in owe]
assert amounts == [15000.0, 10000.0], amounts    # الأكبر أولاً، والمكتمل مستبعَد
assert remaining_amount(recs[1]) == 15000.0
assert remaining_amount(recs[0]) == 0.0
print(f"  OK: {len(owe)} متأخّراً، الأكبر {amounts[0]:,.0f}")

print("\n=== كشف فارغ لا يتعطّل ===")
empty = financial_summary([])
assert empty.count == 0 and empty.total == 0 and empty.collected_percent == 0.0
assert distribution([], "hotel") == [] and outstanding([]) == []
print("  OK: الكشف الفارغ آمن")

print("\n=== المبلغ كتابةً (إنجليزي) ===")
from hajj_app.fields import num_to_words_en
assert num_to_words_en(460000) == "four hundred sixty thousand", num_to_words_en(460000)
assert num_to_words_en(0) == "zero"
assert num_to_words_en(12000) == "twelve thousand", num_to_words_en(12000)
assert num_to_words_en(1001) == "one thousand one", num_to_words_en(1001)
assert num_to_words_en("") == ""
print(f"  OK: 460000 -> {num_to_words_en(460000)}")

print("\n=== سند قبض PDF (Receipt Voucher) ===")
from hajj_app.pdf_io import export_receipt_pdf, build_receipt_description
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
r = rec(full_name_ar="عبدالله الشامسي", passport_number="A1234567",
        nationality_ar="الإمارات", phone="0501112233", hotel="كونراد مكة",
        room_type="ثنائية", family_number="101",
        program_value="460000", paid_amount="460000")
# البيان الافتراضي يُبنى من بيانات الحاج
desc = build_receipt_description(r, season="1447", amount=460000)
assert "كونراد" in desc and "غير مستردة" in desc, desc
pdf = _os.path.join(_OUTDIR, "receipt.pdf")
export_receipt_pdf(r, pdf, season="1447", number="0119")
assert _os.path.getsize(pdf) > 3000
with open(pdf, "rb") as fh:
    assert fh.read(5) == b"%PDF-"
# تجاوز الحقول يدوياً (كما تفعل نافذة المعاينة)
export_receipt_pdf(r, _os.path.join(_OUTDIR, "receipt2.pdf"), number="0120",
                   date_str="May 1, 2026", amount=460000,
                   amount_words="four hundred sixty thousand",
                   description="وذلك عن: برنامج الحج", bank="Bank Transfer")
print(f"  OK: سند PDF ({_os.path.getsize(pdf)} بايت)")

print("\n=== تصدير الإحصاءات والملخّص المالي PDF ===")
from hajj_app.pdf_io import export_stats_pdf
statrecs = [
    rec(full_name_ar="أ", nationality_ar="الإمارات", sex="ذكر", hotel="الصفوة",
        airline="الاتحاد", room_type="رباعية 2", program_value="20000",
        paid_amount="20000", phone="0501"),
    rec(full_name_ar="ب", nationality_ar="مصر", sex="أنثى", hotel="كونراد",
        airline="الاتحاد", room_type="ثلاثية 1", program_value="18000",
        paid_amount="6000", phone="0502"),
    rec(full_name_ar="ج", nationality_ar="الإمارات", sex="ذكر", hotel="الصفوة",
        program_value="15000", paid_amount="", phone="0503"),
]
spdf = _os.path.join(_OUTDIR, "stats.pdf")
export_stats_pdf(statrecs, spdf, season="1447")
assert _os.path.getsize(spdf) > 3000
with open(spdf, "rb") as fh:
    assert fh.read(5) == b"%PDF-"
# كشف فارغ لا يتعطّل
export_stats_pdf([], _os.path.join(_OUTDIR, "stats_empty.pdf"))
print(f"  OK: PDF ({_os.path.getsize(spdf)} بايت)، والفارغ لا يتعطّل")

print("\n*** STATS TESTS PASSED ***")
