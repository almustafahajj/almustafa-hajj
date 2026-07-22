# -*- coding: utf-8 -*-
"""Smoke-test the GUI: build the window, load records, exercise refresh/edit/filter/sort."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tkinter import Tk
from hajj_app.gui import HajjApp, EditDialog
# --- isolate tests from the user's real data file ---
import hajj_app.gui as _g, hajj_app.storage as _st, pathlib as _pl
_TESTDB = _pl.Path(_OUTDIR) / "testdata" / "hajjaj.json"
_TESTDB.parent.mkdir(parents=True, exist_ok=True)
for _p in (_TESTDB, _TESTDB.with_suffix('.bak')):
    _p.unlink(missing_ok=True)
_g.default_data_path = lambda: _TESTDB
_st.default_data_path = lambda: _TESTDB
from hajj_app.mrz import PassportData

root = Tk()
root.withdraw()                      # build offscreen
app = HajjApp(root)
print("OK: window + toolbar + table built")

app.records = [
    PassportData(full_name_en="AYMAN ALSHEHABI", full_name_ar="أيمن الشهابي",
                 passport_number="A1234567", nationality_ar="السعودية",
                 sex="ذكر", birth_date="1985-01-01", hotel="فندق الصفوة",
                 program_value="15,000", paid_amount="5,000",
                 expiry_date="2030-12-01", phone="0559876543"),
    PassportData(full_name_en="FATIMA KHAN", passport_number="AB987654",
                 nationality_ar="باكستان", sex="أنثى", birth_date="1992-03-15",
                 warnings=["خانة التحقق لا تطابق: رقم الجواز"]),
]
app.refresh()
rows = app.tree.get_children()
print("rows in table:", len(rows))
assert len(rows) == 2, len(rows)

tags = app.tree.item(rows[1], "tags")
assert "warn" in tags, tags
print("OK: warning row highlighted ->", tags)

vals = app.tree.item(rows[0], "values")
assert "أيمن الشهابي" in vals, vals
print("OK: Arabic renders in table")

cols = [c.key for c in app.columns]
assert cols[-1] == "serial", cols[-3:]
assert cols[0] == "source_file", cols[:3]
assert vals[cols.index("serial")] == "1"
assert vals[cols.index("remaining_amount")] == "10,000", vals[cols.index("remaining_amount")]
print("OK: RTL column order + derived serial/remaining in table")
print("count label:", app.count_label.cget("text"))

# exercise the edit dialog end-to-end
saved = {}
dlg = EditDialog(root, app.records[1], on_save=lambda r: saved.update({"r": r}))
assert len(dlg.vars) == 29, f"editable fields in dialog: {len(dlg.vars)}"
dlg.vars["full_name_ar"].set("فاطمة خان")
dlg.vars["birth_date"].set("1992-03-15")
dlg.vars["arrival_time"].set("2:30 PM")          # must normalize on save
dlg.vars["program_value"].set("12000")
dlg.vars["paid_amount"].set("4500")
root.update()
live = dlg.remaining.cget("text")                 # live derived preview
print("live remaining label:", live)
assert "7,500" in live, live
dlg._save()
r = saved["r"]
assert r.full_name_ar == "فاطمة خان"
assert r.arrival_time == "14:30", r.arrival_time
assert r.program_value == "12,000", r.program_value
assert r.warnings == [], "manual edit should clear warnings"
print("OK: edit dialog normalizes time+money, live remaining, clears warnings")

print("\n=== الفلاتر ===")
for k in ("hotel", "room_type", "nationality_ar", "airline", "sex",
          "executive_service", "transport", "wheelchair", "notes"):
    assert k in app.filter_boxes, f"فلتر مفقود: {k}"
print("  OK: كل الفلاتر التسعة موجودة (بما فيها التنفيذي والمواصلات وكرسي متحرك وملاحظات)")

app.records = [
    PassportData(full_name_ar="حاج أول", hotel="كونراد", room_type="رباعية 1",
                 nationality_ar="الإمارات", sex="ذكر", passport_number="A1",
                 wheelchair="نعم", transport="باص A"),
    PassportData(full_name_ar="حاج ثاني", hotel="كونراد", room_type="ثلاثية 1",
                 nationality_ar="مصر", sex="ذكر", passport_number="A2",
                 transport="باص B"),
    PassportData(full_name_ar="حاجة ثالثة", hotel="هيلتون", room_type="رباعية 1",
                 nationality_ar="الإمارات", sex="أنثى", passport_number="A3"),
]
app.refresh()
assert set(app.filter_boxes["wheelchair"]["values"]) == {"الكل", "نعم"}
app.filter_vars["wheelchair"].set("نعم")
app.refresh()
assert [i for i in app.tree.get_children()] == ["0"], "فلتر كرسي متحرك خاطئ"
print("  OK: فلتر كرسي متحرك = نعم -> السجل 0 وحده")
app.clear_filters()
assert len(app.tree.get_children()) == 3
assert set(app.filter_boxes["hotel"]["values"]) == {"الكل", "كونراد", "هيلتون"}
print("  OK: قيم فلتر الفندق تُملأ من البيانات")

rt_values = list(app.filter_boxes["room_type"]["values"])
assert rt_values == ["الكل", "ثلاثي", "رباعي"], rt_values
print(f"  OK: فلتر الغرفة يعرض الفئة فقط ومرتّبة بالسعة -> {rt_values}")
app.filter_vars["room_type"].set("رباعي")
app.refresh()
assert set(app.tree.get_children()) == {"0", "2"}, app.tree.get_children()
print("  OK: 'رباعي' يشمل كل الرباعيات بلا نظر لرقمها")
app.clear_filters()

app.filter_vars["hotel"].set("كونراد")
app.refresh()
shown = app.tree.get_children()
assert len(shown) == 2, len(shown)
assert set(shown) == {"0", "1"}
assert "المعروض: 2 من 3" in app.count_label.cget("text")
print("  OK: فلتر الفندق -> 2 من 3، والصفوف تحمل الفهرس الأصلي")

serial_col = [c.key for c in app.columns].index("serial")
serials = [app.tree.item(i, "values")[serial_col] for i in shown]
assert serials == ["1", "2"], serials
print("  OK: المسلسل يعاد ترقيمه 1، 2 على المعروض")

app.filter_vars["nationality_ar"].set("الإمارات")
app.refresh()
assert len(app.tree.get_children()) == 1, "الفلترة المركّبة خاطئة"
assert app.tree.get_children()[0] == "0"
print("  OK: كونراد + الإمارات -> حاج واحد (السجل 0)")

assert app._visible_records()[0].passport_number == "A1"
print("  OK: _visible_records يعيد السجل الصحيح تحت الفلتر")

app.clear_filters()
app.filter_search.set("ثاني")
app.refresh()
assert len(app.tree.get_children()) == 1
assert app.tree.get_children()[0] == "1"
print("  OK: البحث الحر عن 'ثاني' -> السجل 1")

app.clear_filters()
assert len(app.tree.get_children()) == 3
assert "إجمالي الحجاج: 3" in app.count_label.cget("text")
print("  OK: مسح الفلاتر يعيد كل السجلات")

app.filter_vars["hotel"].set("كونراد")
title = app._filter_title()
assert "كونراد" in title and title.startswith("كشف الحجاج"), title
print(f"  OK: عنوان الطباعة يعكس الفلتر -> {title}")
app.clear_filters()

print("\n=== موسم السنة الهجرية ===")
from hajj_app.storage import load_settings
assert app.season_year.get() in _g.HIJRI_YEARS, app.season_year.get()
app.season_year.set("1448")
app._on_season_change()
assert load_settings().get("season_year") == "1448", "لم تُحفظ السنة"
title = app._report_title("كشف الحجاج")
assert "موسم 1448" in title, title
print(f"  OK: تُحفظ السنة وتظهر في العنوان -> {title}")

print("\n=== شعار الشركة في PDF ===")
from hajj_app.pdf_io import _logo_flowable
assert _logo_flowable() is not None, "لم يُحمّل الشعار للـ PDF"
print("  OK: شعار الشركة متاح لكشوفات الـ PDF")

print("\n=== الترتيب حسب (عرض فقط، قابل للإلغاء) ===")
app.clear_filters()
app.records = [
    PassportData(full_name_ar="محمد", family_number="103", passport_number="A1",
                 room_type="ثلاثية 2", program_value="10000", paid_amount="3000"),
    PassportData(full_name_ar="أحمد", family_number="101", passport_number="A2",
                 room_type="رباعية 1", program_value="10000", paid_amount="9000"),
    PassportData(full_name_ar="سالم", family_number="102", passport_number="A3",
                 room_type="مفرد 5", program_value="10000", paid_amount="1000"),
]
original = list(app.records)      # الترتيب الأصلي: محمد، أحمد، سالم
app.refresh()

name_c = [c.key for c in app.columns].index("full_name_ar")
def displayed():
    return [app.tree.item(i, "values")[name_c] for i in app.tree.get_children()]

app.sort_var.set("رقم العائلة")
app._apply_sort()
assert displayed() == ["أحمد", "سالم", "محمد"], displayed()
assert app.records == original, "الترتيب غيّر self.records (يجب أن يكون عرضاً فقط)"
print("  OK: العرض مرتّب حسب العائلة، وself.records لم يتغيّر")

app._toggle_sort_dir()
assert displayed() == ["محمد", "سالم", "أحمد"], displayed()
print("  OK: تنازلي")

app.sort_desc = False
app.sort_var.set("نوع الغرفة")
app._apply_sort()
assert displayed() == ["سالم", "محمد", "أحمد"], displayed()   # مفرد5، ثلاثي2، رباعي1
print("  OK: ترتيب الغرفة بالسعة -> مفرد، ثلاثي، رباعي")

app.sort_var.set(app._SORT_NONE)
app._apply_sort()
assert displayed() == ["محمد", "أحمد", "سالم"], displayed()
assert app.sort_field is None
print("  OK: «بدون ترتيب» أعاد الترتيب الأصلي")

app.sort_var.set("رقم العائلة"); app._apply_sort()
assert [r.family_number for r in app._ordered()] == ["101", "102", "103"]
assert [r.family_number for r in app._visible_records()] == ["101", "102", "103"]
print("  OK: التصدير/الطباعة يحترمان الترتيب عبر _ordered")
app.sort_var.set(app._SORT_NONE); app._apply_sort()

print("\n=== فحص جاهزية الكشف (QualityDialog) ===")
from hajj_app.gui import QualityDialog
app.clear_filters()
app.records = [
    PassportData(full_name_ar="مكرر أ", passport_number="DUP1", birth_date="1980-01-01"),
    PassportData(full_name_ar="مكرر ب", passport_number="DUP1", birth_date="1981-01-01"),
    PassportData(full_name_ar="", passport_number="", birth_date=""),   # نقص كامل
]
app.refresh()
picked = {}
qd = QualityDialog(root, lambda: app.records, lambda i: picked.update({"i": i}))
groups = qd._tree.get_children()
assert groups, "لا مجموعات مشكلات ظهرت"
leaf = qd._tree.get_children(groups[0])[0]      # أول مشكلة تحت أول مجموعة
qd._tree.selection_set(leaf)
qd._jump()
assert "i" in picked, "القفز إلى السجل لم يعمل"
qd.destroy()
# _focus_record يحدّد السجل في الجدول الرئيسي
app._focus_record(1)
assert app.tree.selection() == ("1",), app.tree.selection()
print("  OK: يعرض المشكلات مجمّعة، والقفز إلى السجل يعمل")

print("\n=== بوابة أمان «مسح الكل» ===")
# بلا جلسة: تُقبل كلمة «مسح» فقط، ويُرفض ما سواها (يمنع الضغط غير المقصود)
assert app.session is None
assert app._clear_credential_ok("مسح") is True
assert app._clear_credential_ok("مسح ") is True         # يتجاهل الفراغات
assert app._clear_credential_ok("نعم") is False
assert app._clear_credential_ok("") is False
assert app._clear_credential_ok("1234") is False
print("  OK: المسح محميّ — لا يتم إلا بكلمة التأكيد (أو كلمة مرور الحساب عند الدخول)")

app._require_records()
root.update()
root.destroy()
print("\n*** GUI SMOKE TEST PASSED ***")
