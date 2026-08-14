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
assert len(dlg.vars) == 46, f"editable fields in dialog: {len(dlg.vars)}"
# الحقول الجديدة (تأشيرة/تصريح، محرم، صحّة وطوارئ) موجودة وتُحفظ
for _k in ("visa_number", "permit_status", "mahram_name", "blood_type",
           "emergency_phone"):
    assert _k in dlg.vars, _k
dlg.vars["permit_status"].set("صدر")
dlg.vars["emergency_phone"].set("0501234567")
assert "status" in dlg.vars
dlg.vars["status"].set("قائمة انتظار")
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
assert r.permit_status == "صدر" and r.emergency_phone == "0501234567"
assert r.status == "قائمة انتظار"
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

print("\n=== تعديل جماعي وكشف المواصلات ===")
from hajj_app.gui import TransportDialog
app.clear_filters()
app.records = [
    PassportData(full_name_ar="حاج1", passport_number="B1", transport="باص 1"),
    PassportData(full_name_ar="حاج2", passport_number="B2", transport="باص 2"),
    PassportData(full_name_ar="حاج3", passport_number="B3"),
]
app.refresh()
# تعديل جماعي: يضبط الفندق والطيران لسجلين
n = app._apply_bulk([0, 2], {"hotel": "الصفوة", "airline": "الاتحاد"})
assert n == 2
assert app.records[0].hotel == "الصفوة" and app.records[0].airline == "الاتحاد"
assert app.records[2].hotel == "الصفوة"
assert app.records[1].hotel == "", "السجل غير المحدّد تغيّر خطأً"
print("  OK: التعديل الجماعي يطبّق الحقول على المحدّدين فقط")

# ---- المجموعات: تجميع جماعي + توزيع ----
app._apply_bulk([0, 1], {"group": "مجموعة أ"})
assert app.records[0].group == "مجموعة أ" and app.records[1].group == "مجموعة أ"
assert app.records[2].group == ""
from hajj_app.stats import distribution
gd = {b.label: b.count for b in distribution(app.records, "group")}
assert gd.get("مجموعة أ") == 2, gd
print("  OK: التجميع في مجموعة + التوزيع حسب المجموعة")

# ---- التراجع (Undo) ----
app._push_undo("لقطة")
before = [r.hotel for r in app.records]
app._apply_bulk([1], {"hotel": "كونراد"})
assert app.records[1].hotel == "كونراد"
app.undo()                                   # يستعيد اللقطة
assert [r.hotel for r in app.records] == before, "التراجع لم يستعد الحالة"
app._undo_stack.clear()
app.undo()                                   # لا شيء للتراجع — لا يتعطّل
print("  OK: التراجع يستعيد الحالة، والفارغ آمن")
# كشف المواصلات: يعرض المجموعات
td = TransportDialog(root, list(app.records))
tgroups = td._tree.get_children()
labels = [td._tree.item(g, "text") for g in tgroups]
assert any("باص 1" in t for t in labels) and any("بلا مواصلات" in t for t in labels), labels
td._var.set("باص 1"); td._rebuild()
assert len(td._current()) == 1
td.destroy()

# ---- لوحة التحكم (Dashboard) ----
from hajj_app.gui import DashboardDialog
dash = DashboardDialog(root, app)
dash.update()
_lbls = []
def _walk(w):
    for c in w.winfo_children():
        if c.__class__.__name__ == "Label":
            _lbls.append(c.cget("text"))
        _walk(c)
_walk(dash)
assert "الحجّاج" in _lbls and "تنبيهات الجودة" in _lbls, _lbls
assert any(str(len(app.records)) == t for t in _lbls), "عدد الحجّاج غير معروض"
dash.destroy()
print("  OK: لوحة التحكم تعرض المؤشّرات")

# ---- نطاق كشف التسكين: اختيار الفندق ونوع الغرفة ----
from hajj_app.gui import RoomingScopeDialog
from hajj_app.rooming import room_category
app.records = [
    PassportData(full_name_ar="أ", hotel="كونراد", room_type="رباعية 1"),
    PassportData(full_name_ar="ب", hotel="كونراد", room_type="ثنائية 1"),
    PassportData(full_name_ar="ج", hotel="الصفوة", room_type="رباعية 1"),
]
rsd = RoomingScopeDialog(root, app.records)
rsd.v_hotel.set("كونراد"); rsd.v_cat.set("رباعي"); rsd._ok()
assert rsd.result == ("كونراد", "رباعي"), rsd.result
_h, _c = rsd.result
_sel = [r for r in app.records if str(r.hotel or "").strip() == _h
        and room_category(r.room_type) == _c]
assert len(_sel) == 1 and _sel[0].full_name_ar == "أ", _sel
# «الكل» يعيد (None, None)
rsd2 = RoomingScopeDialog(root, app.records); rsd2._ok()
assert rsd2.result == (None, None)
print("  OK: نطاق التسكين يفلتر بالفندق ونوع الغرفة")

# ---- تحسينات الواجهة: تلوين الصفوف + الحالة الفارغة + الرقائق + الإحصاء ----
app.records = []
app.refresh()
assert app._empty.winfo_manager() == "place", "الحالة الفارغة يجب أن تظهر"
app.records = [
    PassportData(full_name_ar="د", program_value="20000", paid_amount="5000"),
    PassportData(full_name_ar="هـ", program_value="20000", paid_amount="20000"),
]
app.refresh()
assert app._empty.winfo_manager() == "", "الحالة الفارغة يجب أن تختفي مع وجود سجلات"
_rtags = [app.tree.item(i, "tags")[0] for i in app.tree.get_children()]
assert "due" in _rtags and "paid" in _rtags, _rtags
assert "المحصّل" in app._fin_label.cget("text"), app._fin_label.cget("text")
# رقاقة فلتر نشطة عبر البحث الحر (لا يُعاد ضبطه في _populate_filters)
app.filter_search.set("د")
assert app._chips_row.winfo_manager() == "pack", "صفّ الرقائق يظهر مع فلتر نشط"
app.filter_search.set("")
assert app._chips_row.winfo_manager() == "", "الرقائق تختفي بلا فلاتر"
print("  OK: تلوين الصفوف، الحالة الفارغة، رقائق الفلاتر، الإحصاء الدائم")
print("  OK: كشف المواصلات يجمع بالباص ويصفّي بالاختيار")

print("\n=== لوحة الإحصاءات والمالية (StatsDialog) ===")
from hajj_app.gui import StatsDialog
app.clear_filters()
app.records = [
    PassportData(full_name_ar="أ", nationality_ar="الإمارات", hotel="الصفوة",
                 program_value="20000", paid_amount="20000"),
    PassportData(full_name_ar="ب", nationality_ar="الإمارات", hotel="كونراد",
                 program_value="20000", paid_amount="5000"),
    PassportData(full_name_ar="ج", nationality_ar="مصر", hotel="كونراد",
                 program_value="15000", paid_amount=""),
]
app.refresh()
sd = StatsDialog(root, list(app.records), season="1447")
# تبويب التوزيع يعرض الجنسية الأكثر أولاً
dist_rows = sd._dist.get_children()
assert dist_rows, "لا توزيع"
assert sd._dist.item(dist_rows[0], "text") == "الإمارات", sd._dist.item(dist_rows[0], "text")
# تبويب المتأخّرات يستبعد المكتمل (أ) ويرتّب تنازلياً (ب 15000 قبل ج 15000)
owe_rows = sd._owe.get_children()
assert len(owe_rows) == 2, owe_rows
assert "المتبقّي" in sd._owe_total.cget("text")
sd.destroy()
print("  OK: بطاقات مالية + توزيع + كشف المتأخّرات")

print("\n=== مؤثرات وحماية: حالة فارغة، toast، نسخ احتياطية ===")
from hajj_app.gui import RestoreDialog
import hajj_app.storage as _bk
# الحالة الفارغة تظهر بلا سجلات وتُخفى بوجودها
app.records = []
app.refresh()
assert app._empty.winfo_manager() == "place", "الحالة الفارغة لم تظهر"
app.records = [PassportData(full_name_ar="حاج", passport_number="Z1")]
app.refresh()
assert app._empty.winfo_manager() == "", "الحالة الفارغة لم تُخفَ"
# toast لا يتعطّل والنافذة مخفيّة
app.toast("اختبار", kind="success")
# نسخة احتياطية الآن ثم استعادة
app.records = [PassportData(full_name_ar="أ", passport_number="A1"),
               PassportData(full_name_ar="ب", passport_number="A2")]
app.do_backup_now()
snaps = _bk.list_snapshots()
assert snaps, "لم تُنشأ لقطة"
recs, _note = _bk.load_records(snaps[0], None)
assert len(recs) == 2
# محاكاة الاستعادة (نتخطّى التأكيد)
app.records = [PassportData(full_name_ar="ج", passport_number="A3")]
import tkinter.messagebox as _mb
_orig_yes = _mb.askyesno
_mb.askyesno = lambda *a, **k: True
app._do_restore(recs, "لقطة")
_mb.askyesno = _orig_yes
assert [r.full_name_ar for r in app.records] == ["أ", "ب"], app.records
# RestoreDialog يعرض اللقطات
rd = RestoreDialog(root, None, lambda r, l: None)
assert rd._tree.get_children(), "لا لقطات في نافذة الاستعادة"
rd.destroy()
print("  OK: حالة فارغة تظهر/تُخفى، toast آمن، ونسخة احتياطية + استعادة")

print("\n=== بوابة أمان «مسح الكل» ===")
# بلا جلسة: تُقبل كلمة «مسح» فقط، ويُرفض ما سواها (يمنع الضغط غير المقصود)
assert app.session is None
assert app._clear_credential_ok("مسح") is True
assert app._clear_credential_ok("مسح ") is True         # يتجاهل الفراغات
assert app._clear_credential_ok("نعم") is False
assert app._clear_credential_ok("") is False
assert app._clear_credential_ok("1234") is False
print("  OK: المسح محميّ — لا يتم إلا بكلمة التأكيد (أو كلمة مرور الحساب عند الدخول)")

print("\n=== بدء موسم جديد (أرشفة ثم تفريغ + ضبط السنة) ===")
import tkinter as _tk
from hajj_app.mrz import PassportData as _PD


class _FakeNSD(_tk.Toplevel):
    def __init__(self, parent, current_year, pilgrim_count):
        super().__init__(parent)
        self.confirmed = True
        self.year = "1448"
        self.after(1, self.destroy)


_orig_nsd, _orig_pd = _g.NewSeasonDialog, _g.ProgramsDialog
_g.NewSeasonDialog = _FakeNSD
_g.ProgramsDialog = lambda root, appx: None
try:
    app.records = [_PD(full_name_ar=f"حاج {i}", passport_number=f"NS{i}")
                   for i in range(4)]
    app.season_year.set("1447")
    app.refresh()
    app.do_new_season()
    assert app.records == [], "الكشف لم يُفرَّغ"
    assert app.season_year.get() == "1448", app.season_year.get()
    assert _st.load_settings().get("season_year") == "1448"
    snaps = _st.list_snapshots()
    assert snaps, "لم تُنشأ لقطة أرشفة"
    archived, _n = _st.load_records(snaps[0], None)
    assert len(archived) == 4, "الأرشفة لم تحفظ حجّاج الموسم القديم"
    print("  OK: أُرشف 4 حجّاج، فُرّغ الكشف، وضُبطت السنة إلى 1448هـ")
finally:
    _g.NewSeasonDialog, _g.ProgramsDialog = _orig_nsd, _orig_pd

print("\n=== المجموعات والمرشدون ===")
from hajj_app.gui import GroupsDialog as _GD
app.records = [_PD(full_name_ar="أ", group="مجموعة 1"),
               _PD(full_name_ar="ب", group="مجموعة 1"),
               _PD(full_name_ar="ج", group="مجموعة 2")]
_gd = _GD(root, app)
assert set(_gd._vars.keys()) == {"مجموعة 1", "مجموعة 2"}
_gd._vars["مجموعة 1"][0].set("الشيخ خالد")
_gd._vars["مجموعة 1"][1].set("0501112233")
_gd._save()
_grp = _st.load_settings().get("groups", {})
assert _grp["مجموعة 1"]["guide"] == "الشيخ خالد", _grp
assert _grp["مجموعة 1"]["phone"] == "0501112233"
print("  OK: كشف المجموعتين، وحفظ مرشد وهاتف مجموعة 1")

print("\n=== المصروفات والمحاسبة ===")
from hajj_app.gui import ExpensesDialog as _ED
app.records = [_PD(paid_amount="10000"), _PD(paid_amount="5000")]
app._settings["expenses"] = []        # ابدأ من إعداد نظيف (الملف يبقى بين التشغيلات)
_ed = _ED(root, app)
_ed._supplier.set("فندق"); _ed._amount.set("4000"); _ed._add()
_ed._supplier.set("نقل"); _ed._amount.set("2000"); _ed._add()
assert _ed._expense_total() == 6000
assert "9,000" in _ed._totals.cget("text")            # 15000 محصّل - 6000 مصروف
assert len(_st.load_settings().get("expenses", [])) == 2
_ed.tree.selection_set("0"); _ed._delete()
assert _ed._expense_total() == 2000
print("  OK: مصروفان، الصافي 9,000، والحذف يخفّض الإجمالي")

print("\n=== جدول المناسك ===")
from hajj_app.gui import ItineraryDialog as _ID
_itin = _ID(root, app)
_itin._fill_template()
assert len(_itin._items) == 8
_saved_itin = _st.load_settings().get("itinerary", [])
assert len(_saved_itin) == 8 and "عرفة" in _saved_itin[1][2]
_itin._day.set("يوم"); _itin._activity.set("نشاط"); _itin._add()
assert len(_itin._items) == 9
print("  OK: قالب أيام الحجّ (8 بنود) يُحفظ، والإضافة تعمل")

app._require_records()
root.update()
root.destroy()

print("\n=== القفل التلقائي عند الخمول ===")
from hajj_app.auth import Session as _Sess
_r2 = Tk(); _r2.withdraw()
_app2 = HajjApp(_r2, session=_Sess("MHU", b"0" * 32, role="admin"))
assert _app2._idle_after is None                 # معطّل افتراضياً
_app2._settings["auto_lock_min"] = 15
_app2._setup_auto_lock()
assert _app2._idle_ms == 15 * 60000 and _app2._idle_after is not None
_app2._auto_lock()                               # يقفل ويطلب العودة للدخول
assert _app2._logout_requested is True
print("  OK: معطّل افتراضياً، يُجدوَل عند التفعيل، والقفل يطلب الدخول")

print("\n=== إشغال الغرف ===")
from hajj_app.gui import OccupancyDialog as _OD
_r3 = Tk(); _r3.withdraw()
_occ_recs = [
    _PD(hotel="الصفوة", room_type="ثنائي", room_number="101"),
    _PD(hotel="الصفوة", room_type="ثنائي", room_number="101"),
    _PD(hotel="الصفوة", room_type="ثنائي", room_number="101"),   # تجاوز
    _PD(hotel="الصفوة", room_type="رباعي", room_number="201"),
    _PD(hotel="الصفوة", room_type="رباعي", room_number="201"),   # شاغر 2
    _PD(hotel="كونراد", room_type="مفرد", room_number="5"),      # مكتملة
    _PD(hotel=""),                                                # بلا غرفة
]
_od = _OD(_r3, _occ_recs)
_s = _od._summary.cget("text")
assert "متجاوِزة: 1" in _s and "مكتملة: 1" in _s and "أسرّة شاغرة: 2" in _s
assert "بلا غرفة: 1" in _s
_r3.destroy()
print("  OK: تجاوز 1، مكتملة 1، أسرّة شاغرة 2، بلا غرفة 1")

print("\n=== الفلاتر المحفوظة ===")
from hajj_app.gui import FilterPresetsDialog as _FP
_r4 = Tk(); _r4.withdraw()
_app4 = HajjApp(_r4)
_app4._settings["filter_presets"] = {}     # ابدأ نظيفاً (الملف يبقى)
_app4.records = [_PD(hotel="الصفوة"), _PD(hotel="كونراد")]
_app4.refresh()
_app4.filter_search.set("الصفوة")
_fp = _FP(_r4, _app4); _fp._preset_name.set("حجّاج الصفوة"); _fp._save()
assert "حجّاج الصفوة" in _st.load_settings().get("filter_presets", {})
_app4.filter_search.set("")
_fp._reload(); _fp.listbox.selection_set(0); _fp._apply()
assert _app4.filter_search.get() == "الصفوة"
_r4.destroy()
print("  OK: حفظ الفلتر الحالي وتطبيقه لاحقاً")

print("\n=== الرسوم البيانية ===")
from hajj_app.gui import ChartsDialog as _CH
_r5 = Tk(); _r5.withdraw()
_ch = _CH(_r5, [
    _PD(program="الأول", hotel="الصفوة", nationality_ar="سعودي", status="نشط",
        program_value="5000", paid_amount="3000"),
    _PD(program="الأول", hotel="كونراد", nationality_ar="إماراتي", status="نشط",
        program_value="4000", paid_amount="4000"),
    _PD(program="الثاني", hotel="الصفوة", nationality_ar="سعودي", status="ملغى",
        program_value="6000", paid_amount="1000"),
])
_texts = [_ch.canvas.itemcget(i, "text") for i in _ch.canvas.find_all()
          if _ch.canvas.type(i) == "text"]
assert any("المالية" in t for t in _texts) and any("البرنامج" in t for t in _texts)
assert len(_ch.canvas.find_all()) > 20
_r5.destroy()
print("  OK: رسوم التوزيعات والمالية تُرسَم على Canvas")

print("\n=== حول/اختصارات/لوحة الأوامر (Ctrl+K) ===")
import hajj_app as _ha
from hajj_app.gui import AboutDialog as _AB, ShortcutsDialog as _SH, CommandPalette as _CP
assert _ha.__version__ == "2.0.0"
_r6 = Tk(); _r6.withdraw()
_ab = _AB(_r6); _ab.destroy()
_sh = _SH(_r6); _sh.destroy()
_hit = []
_cp = _CP(_r6, [("أمر", lambda: _hit.append("cmd"))],
          [_PD(full_name_ar="أحمد", passport_number="A1"),
           _PD(full_name_ar="سالم", passport_number="B2")],
          lambda i: _hit.append(("pil", i)))
assert _cp.listbox.size() == 3                     # أمر + حاجّان
_cp._q.set("سالم")
_rows = [_cp.listbox.get(i) for i in range(_cp.listbox.size())]
assert any("سالم" in x for x in _rows) and not any("أحمد" in x for x in _rows)
_cp.listbox.selection_set(0); _cp._run()
assert ("pil", 1) in _hit
_r6.destroy()
print("  OK: النسخة 2.0.0، النوافذ تفتح، ولوحة الأوامر تصفّي وتقفز")

print("\n=== تلوين الحالة + سمات اللون ===")
from hajj_app.gui import ACCENTS as _ACC, apply_accent as _apac
_r7 = Tk(); _r7.withdraw()
_app7 = HajjApp(_r7)
assert _app7._row_tag({"status": "ملغى"}, 1) == "cancelled"
assert _app7._row_tag({"status": "قائمة انتظار"}, 1) == "waitlist"
assert _app7._row_tag({"status": "", "warnings": ["x"]}, 1) == "warn"
assert {"برونزي", "أخضر زمرّدي", "أزرق ملكي"} <= set(_ACC)
_app7._accent = "برونزي"; _app7.cycle_accent()        # بلا جلسة يطبّق فوراً
assert _st.load_settings()["ui"]["accent"] == "أخضر زمرّدي"
# إعادة للبرونزي حتى لا يؤثّر على بقية الاختبارات
_app7._ui["accent"] = "برونزي"; _app7._settings["ui"] = _app7._ui
_st.save_settings(_app7._settings); _apac("برونزي")
_r7.destroy()
print("  OK: صفوف ملغى/انتظار ملوّنة، وتبديل لون البرنامج يُحفظ")

print("\n=== شاشة الترحيب ===")
from hajj_app.gui import WelcomeDialog as _WEL
from hajj_app.auth import Session as _S2
_r8 = Tk(); _r8.withdraw()
_app8 = HajjApp(_r8, session=_S2("MHU", b"0" * 32, role="admin"))
_app8.records = [_PD(full_name_ar="أحمد", passport_number="A1",
                     program_value="5000", paid_amount="2000")]
_app8.season_year.set("1447")
_wel = _WEL(_r8, _app8)
assert len(_wel.winfo_children()) > 0
_wel._hide.set(True); _wel._toggle_hide()
assert _st.load_settings()["ui"]["show_welcome"] is False
_wel.destroy(); _r8.destroy()
print("  OK: شاشة الترحيب تبني المؤشّرات، و«لا تُظهر» تُحفظ")

print("\n=== التحقق من التحديثات ===")
import hajj_app.gui as _gg
_r9 = Tk(); _r9.withdraw()
_app9 = HajjApp(_r9)
_msgs = []
_gg.messagebox.showinfo = lambda t, m, **k: _msgs.append(("info", t, m))
_gg.messagebox.showwarning = lambda t, m, **k: _msgs.append(("warn", t, m))
_app9._settings["update_url"] = ""
_app9.do_check_updates()                              # بلا رابط -> يدوي
assert "2.0.0" in _msgs[-1][2]
import urllib.request as _ur


class _FR:
    def read(self): return b"2.1.0\n"
    def __enter__(self): return self
    def __exit__(self, *a): return False


_ur.urlopen = lambda url, timeout=5: _FR()
_app9._settings["update_url"] = "http://x/v.txt"
_app9.do_check_updates()
assert _msgs[-1][1] == "تحديث متوفّر" and "2.1.0" in _msgs[-1][2]
_r9.destroy()
print("  OK: يُعلم بالإصدار الحالي، ويكتشف الأحدث عبر الرابط")

print("\n=== معالج أول تشغيل ===")
from hajj_app.gui import OnboardingWizard as _OW
import hajj_app.gui as _gw
_gw.ProgramsDialog = lambda root, appx: None          # لا نفتح البرامج فعلياً
_r10 = Tk(); _r10.withdraw()
_app10 = HajjApp(_r10, session=_S2("MHU", b"0" * 32, role="admin"))
_w = _OW(_r10, _app10)
assert _w._step == 0 and _w.STEPS == 4
_w._next(); _w._v["name_ar"].set("حملة النور"); _w._v["trn"].set("100200300")
_w._next(); _w._season.set("1448")
_w._next(); assert _w._step == 3
_w._open_programs.set(True); _w._finish()
_co = _app10._company_info()
assert _co["name_ar"] == "حملة النور" and _co["trn"] == "100200300"
assert _app10.season_year.get() == "1448"
assert _st.load_settings()["ui"]["onboarded"] is True
# تخطّي يعلّم onboarded
_app10._ui["onboarded"] = False; _st.save_settings(_app10._settings)
_OW(_r10, _app10)._skip()
assert _st.load_settings()["ui"]["onboarded"] is True
_r10.destroy()
print("  OK: خطوات المعالج تحفظ الشركة والموسم وتعلّم onboarded (وكذلك التخطّي)")

print("\n=== الوضع المفتوح (بلا رقم سري) ===")
root_open = Tk()
root_open.withdraw()
app_open = HajjApp(root_open, session=None, open_mode=True)
assert app_open._open_mode is True
# ملف بيانات منفصل حتى لا يُمسّ الكشف المشفّر
assert app_open.data_path.name == "hajjaj-open.json", app_open.data_path
assert app_open.data_path.parent == _TESTDB.parent
root_open.update()
root_open.destroy()
print("  OK: الوضع المفتوح يستعمل ملفاً منفصلاً دون المساس بالمشفّر")

print("\n=== الصلاحيات: مدير/محرّر/مطّلع ===")
from hajj_app.auth import Session


def _menu_labels(a):
    out = []
    for m in a._menus:
        end = m.index("end")
        for i in range(0, (end + 1) if end is not None else 0):
            try:
                out.append(m.entrycget(i, "label"))
            except Exception:
                pass
    return out


expect = {
    "admin":  dict(edit=True,  imp=True,  accounts=True),
    "editor": dict(edit=True,  imp=True,  accounts=False),
    "viewer": dict(edit=False, imp=False, accounts=False),
}
for role, exp in expect.items():
    r = Tk(); r.withdraw()
    a = HajjApp(r, session=Session(f"u_{role}", b"0" * 32, role=role))
    labels = _menu_labels(a)
    has = lambda s: any(s in x for x in labels)
    assert a._can_edit() is exp["edit"], role
    assert has("إضافة حاج") is exp["edit"], role
    assert has("حذف المحدد") is exp["edit"], role
    assert has("استيراد من إكسل") is exp["imp"], role
    assert has("إدارة الحسابات") is exp["accounts"], role
    # التصدير والتقارير متاحة للجميع (بما فيهم المطّلع)
    assert has("تصدير إكسل") and has("سجلّ التدقيق"), role
    if role == "viewer":                      # محاولات التعديل تُمنع بلا استثناء
        a.records = list(app.records)
        a.add_manual(); a.edit_selected(); a.delete_selected(); a.clear_all()
        assert len(a.records) == len(app.records), "المطّلع عدّل البيانات!"
    r.update(); r.destroy()
    print(f"  OK: {role} — تعديل={exp['edit']} استيراد={exp['imp']} حسابات={exp['accounts']}")

print("\n*** GUI SMOKE TEST PASSED ***")
