# -*- coding: utf-8 -*-
"""اختبار الإنتاجية: محتوى QR، كشف المواصلات، وبطاقات الحجّاج."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from openpyxl import load_workbook
from hajj_app.cards import qr_payload
from hajj_app.transport import (
    TRANSPORT_COLUMNS, distinct_transports, executive_display,
    export_transport_excel, group_by_transport,
)
from hajj_app.pdf_io import export_badges_pdf, export_transport_pdf
from hajj_app.mrz import PassportData


def rec(**kw):
    return PassportData(**kw)


print("=== محتوى رمز QR للبطاقة ===")
r = rec(full_name_ar="عبدالله الشامسي", passport_number="a1234567",
        phone="0501112233", hotel="الصفوة", room_type="رباعية 2",
        family_number="101")
payload = qr_payload(r)
assert payload.startswith("الحاج: عبدالله الشامسي")
assert "الجواز: A1234567" in payload            # يُكبّر الأحرف
assert "الهاتف: 0501112233" in payload
assert "الإقامة: الصفوة - غرفة 2" in payload     # الرقم من نوع الغرفة
assert "العائلة: 101" in payload
# حاج بلا بيانات -> سطر الاسم فقط
assert qr_payload(rec()) == "الحاج: —"
print("  OK: أسطر مقروءة تُعرّف الحاج")

print("\n=== تجميع المواصلات ===")
recs = [
    rec(full_name_ar="أ", transport="باص 1", passport_number="P1", hotel="الصفوة"),
    rec(full_name_ar="ب", transport="باص 2", passport_number="P2"),
    rec(full_name_ar="ج", transport="باص 1", passport_number="P3"),
    rec(full_name_ar="د", transport="", passport_number="P4"),   # بلا مواصلات
]
assert distinct_transports(recs) == ["باص 1", "باص 2"]
groups, unassigned = group_by_transport(recs)
assert [name for name, _ in groups] == ["باص 1", "باص 2"]       # مرتّبة
assert len(groups[0][1]) == 2 and len(unassigned) == 1
print(f"  OK: باص 1 فيه 2، باص 2 فيه 1، وبلا مواصلات 1")

print("\n=== خدمة التنفيذي: جيمس فقط ===")
assert executive_display(rec(executive_service="جيمس")) == "جيمس"
assert executive_display(rec(executive_service="خدمة جيمس التنفيذية")) == "خدمة جيمس التنفيذية"
assert executive_display(rec(executive_service="أخرى")) == ""      # غير جيمس -> فارغ
assert executive_display(rec(executive_service="")) == ""
assert executive_display(rec()) == ""
print("  OK: تُعرض جيمس فقط، وتُترك القيم الأخرى فارغة")

print("\n=== تصدير المواصلات إكسل ===")
xlsx = _os.path.join(_OUTDIR, "transport.xlsx")
export_transport_excel(recs, xlsx)
wb = load_workbook(xlsx); ws = wb.active
assert ws.sheet_view.rightToLeft is True
assert [c.value for c in ws[2]] == list(TRANSPORT_COLUMNS)
assert "رقم الجواز" not in TRANSPORT_COLUMNS and "الغرفة" not in TRANSPORT_COLUMNS
assert list(TRANSPORT_COLUMNS) == [
    "م", "اسم الحاج", "الهاتف", "الفندق", "خدمة التنفيذي", "كرسي متحرك"]
serials = [row[0].value for row in ws.iter_rows(min_row=3) if isinstance(row[0].value, int)]
assert len(serials) == 4, serials     # كل الحجّاج مُدرجون (مع مجموعة بلا مواصلات)
print(f"  OK: إكسل RTL بأعمدة {list(TRANSPORT_COLUMNS)}، {len(serials)} حاجاً")

print("\n=== تصدير المواصلات PDF (كل باص في صفحة واحدة) ===")
pdf = _os.path.join(_OUTDIR, "transport.pdf")
export_transport_pdf(recs, pdf)
assert _os.path.getsize(pdf) > 3000
with open(pdf, "rb") as fh:
    assert fh.read(5) == b"%PDF-"
import fitz
d = fitz.open(pdf)
# مجموعتان (باص 1، باص 2) + بلا مواصلات = 3 صفحات، كل واحدة صفحة، وطولية
assert d.page_count == 3, d.page_count
page = d[0]
assert page.rect.height > page.rect.width, "الصفحة يجب أن تكون طولية"
d.close()
# باص كبير (60 راكباً بأسماء طويلة وفنادق) يبقى صفحة واحدة، كل حاج سطر واحد
big = [rec(full_name_ar=f"عبدالله محمد راشد الشامسي {i}", transport="باص 7",
           phone=f"05{i:08d}", hotel="فندق دار الصفوة المكية",
           wheelchair=("نعم" if i % 7 == 0 else ""))
       for i in range(60)]
big_pdf = _os.path.join(_OUTDIR, "transport_big.pdf")
export_transport_pdf(big, big_pdf)
d = fitz.open(big_pdf)
assert d.page_count == 1, f"باص 7 يجب أن يكون في صفحة واحدة، لا {d.page_count}"
d.close()
print(f"  OK: 3 صفحات طولية، وباص 7 (60 راكباً) في صفحة واحدة")

print("\n=== بطاقات الحجّاج (QR) PDF ===")
many = [rec(full_name_ar=f"حاج {i}", passport_number=f"A{i:04d}",
            phone=f"05000000{i:02d}", hotel="الصفوة", room_type="رباعية 2")
        for i in range(13)]       # أكثر من صفحة (10/صفحة)
badges = _os.path.join(_OUTDIR, "badges.pdf")
export_badges_pdf(many, badges, company="المصطفى للحج والعمرة")
assert _os.path.getsize(badges) > 4000
with open(badges, "rb") as fh:
    assert fh.read(5) == b"%PDF-"
# قائمة فارغة لا تتعطّل
export_badges_pdf([], _os.path.join(_OUTDIR, "badges_empty.pdf"))
print(f"  OK: بطاقات PDF ({_os.path.getsize(badges)} بايت)، والفارغة لا تتعطّل")

print("\n*** PRODUCTIVITY TESTS PASSED ***")
