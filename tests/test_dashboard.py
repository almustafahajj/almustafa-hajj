# -*- coding: utf-8 -*-
"""اختبار مولّد لوحة الموسم (HTML): صحّة الحساب وسلامة الصفحة المُنتَجة."""
import sys, io
import os as _os
import pathlib as _pl
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app import dashboard_html as D, umrah
from hajj_app.umrah import UmrahTrip
from hajj_app.mrz import PassportData

t1 = UmrahTrip(code="U-101", name="رجب · الذهبية", depart_date="2026-01-12",
               return_date="2026-01-18", makkah_hotel="كونراد مكة",
               madinah_hotel="دار الإيمان", capacity="45")
t2 = UmrahTrip(code="U-102", name="شعبان · الفاخرة", depart_date="2026-02-03",
               return_date="2026-02-09", makkah_hotel="فيرمونت",
               madinah_hotel="أنوار المدينة", capacity="32")


def rec(code, val, paid):
    return PassportData(full_name_ar="معتمر", passport_number="P", trip=code,
                        program_value=str(val), paid_amount=str(paid))


records = [rec("U-101", 15000, 15000), rec("U-101", 15000, 9000),
          rec("U-101", 15000, 15000),           # 45000 total, 39000 paid -> 86.7%
          rec("U-102", 18000, 9000), rec("U-102", 18000, 18000)]  # 36000/27000 -> 75%

print("=== الحساب لكل برنامج + الإجماليات ===")
rows, totals = D.season_dashboard_stats([t1, t2], records)
assert rows[0]["count"] == 3 and rows[0]["capacity"] == 45
assert abs(rows[0]["total"] - 45000) < 1 and abs(rows[0]["paid"] - 39000) < 1
assert round(rows[0]["col_pct"]) == 87, rows[0]["col_pct"]
assert round(rows[1]["col_pct"]) == 75, rows[1]["col_pct"]
assert totals["programs"] == 2 and totals["pilgrims"] == 5 and totals["capacity"] == 77
assert abs(totals["total"] - 81000) < 1 and abs(totals["remaining"] - 15000) < 1
assert round(totals["col_pct"], 1) == 81.5, totals["col_pct"]
print(f"  OK: تحصيل {rows[0]['col_pct']:.0f}٪/{rows[1]['col_pct']:.0f}٪، "
      f"الإجمالي {totals['col_pct']:.1f}٪")

print("\n=== شارات الحالة حسب نسبة التحصيل ===")
assert D._status(96) == ("ok", "مكتمل")
assert D._status(80)[0] == "mid"
assert D._status(60) == ("low", "متابعة")
assert D._status(40)[0] == "low"
print("  OK: مكتمل/جيد/متابعة/متأخّر")

print("\n=== توليد صفحة HTML سليمة ومستقلّة ===")
out = _pl.Path(_OUTDIR) / "season.html"
p = D.export_season_dashboard_html([t1, t2], records, out,
                                   season="١٤٤٧ هـ", company={"name_ar": "المصطفى للحج والعمرة"})
htmltxt = p.read_text(encoding="utf-8")
assert htmltxt.startswith("<!doctype html>")
assert 'dir="rtl"' in htmltxt and 'lang="ar"' in htmltxt
assert "المصطفى للحج والعمرة" in htmltxt
assert "رجب · الذهبية" in htmltxt and "كونراد مكة" in htmltxt
assert "لوحة موسم العمرة" in htmltxt
# القيم الحقيقية ظاهرة
assert "81,000" in htmltxt or "81000" in htmltxt
# لا وسوم قالب غير مُستبدَلة تسرّبت للمخرجات
assert "{totals" not in htmltxt and "{_e(" not in htmltxt and "{r[" not in htmltxt
assert htmltxt.count("</html>") == 1
print(f"  OK: {p.name} ({p.stat().st_size} بايت) — RTL، مستقلّة، بالأرقام الحقيقية")

print("\n=== تقرير الموسم PDF (بنفس حسابات اللوحة) ===")
from hajj_app import pdf_io
pdf = _pl.Path(_OUTDIR) / "season_report.pdf"
pp = pdf_io.export_season_report_pdf([t1, t2], records, pdf, season="١٤٤٧هـ",
                                     company={"name_ar": "المصطفى للحج والعمرة"})
assert pp.is_file() and pp.stat().st_size > 2000, pp.stat().st_size
head = pp.read_bytes()[:5]
assert head == b"%PDF-", head
# لا ينكسر بلا برامج
pe = pdf_io.export_season_report_pdf([], [], _pl.Path(_OUTDIR) / "season_report_empty.pdf",
                                     season="١٤٤٧هـ")
assert pe.read_bytes()[:5] == b"%PDF-"
print(f"  OK: {pp.name} ({pp.stat().st_size} بايت) + الحالة الفارغة")

print("\n=== الحالة الفارغة (لا برامج) لا تنكسر ===")
empty = D.export_season_dashboard_html([], [], _pl.Path(_OUTDIR) / "season_empty.html",
                                       season="١٤٤٧ هـ")
et = empty.read_text(encoding="utf-8")
assert "لا توجد برامج" in et and et.startswith("<!doctype html>")
print("  OK: رسالة فارغة أنيقة")

print("\n*** DASHBOARD TESTS PASSED ***")
