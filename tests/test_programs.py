# -*- coding: utf-8 -*-
"""اختبار برامج الحملة الثلاثة: النموذج، الحفظ/التحميل، والنافذة."""
import sys, io
import os as _os
import pathlib as _pl
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.programs import (
    default_programs, load_programs, programs_to_dicts,
    PROGRAM_KEYS, PROGRAM_NAMES, TRANSPORT_OPTIONS,
)

print("=== النموذج والقيم الافتراضية ===")
progs = default_programs()
assert len(progs) == 3 and len(PROGRAM_NAMES) == 3
assert progs[0].svc_jeems == "40000" and progs[0].svc_business_ticket == "7000"
assert progs[0].svc_wheelchair == "1000" and progs[0].svc_wheelchair_escort == "5000"
assert progs[0].svc_hady == "1000" and progs[0].transport == "باص"
assert TRANSPORT_OPTIONS == ("باص", "جيمس")
for k in ("travel_date", "departure_airport", "return_date", "arrival_airport",
          "carrier", "hotel", "cost_single", "cost_double", "cost_triple",
          "cost_quad", "transport"):
    assert k in PROGRAM_KEYS, k
print(f"  OK: 3 برامج، {len(PROGRAM_KEYS)} حقلاً، أسعار الخدمات الافتراضية")

print("\n=== الحفظ والتحميل (roundtrip) ===")
progs[0].hotel = "كونراد مكة"
progs[0].cost_double = "12,000"
progs[0].transport = "جيمس"
back = load_programs({"programs": programs_to_dicts(progs)})
assert back[0].hotel == "كونراد مكة" and back[0].cost_double == "12,000"
assert back[0].transport == "جيمس" and back[1].svc_hady == "1000"
# ملف ناقص/تالف لا يتعطّل ويُكمَّل بالافتراضي
assert load_programs({"programs": [{"hotel": "x"}]})[0].hotel == "x"
assert load_programs({})[0].svc_wheelchair_escort == "5000"
assert load_programs({"programs": "bad"})[0].transport == "باص"
print("  OK: roundtrip + إكمال الناقص")

print("\n=== احتساب التكلفة من البرنامج ===")
from hajj_app.programs import Program, program_cost, program_by_name, AUTOFILL_MAP
p = Program(cost_single="20000", cost_double="15000", cost_triple="12000",
            cost_quad="10000")
total, br = program_cost(p, room_type="ثنائية", wheelchair="نعم", hady="نعم",
                         executive_service="جيمس", travel_class="رجال أعمال")
assert total == 15000 + 1000 + 1000 + 40000 + 7000, (total, br)
labels = [lbl for lbl, _a in br]
assert "غرفة ثنائية" in labels and "جيمس" in labels and "تذكرة رجال أعمال" in labels
# كرسي متحرك مع مرافق (سعر مختلف)
t2, _ = program_cost(p, room_type="رباعية", wheelchair="مع مرافق")
assert t2 == 10000 + 5000, t2
# غرفة فارغة لا تُحسب رغم أن السعة الافتراضية 4
assert program_cost(p, room_type="")[0] == 0
assert program_cost(p, room_type="مفردة")[0] == 20000
# program_by_name + خريطة التعبئة
progs2 = default_programs()
assert program_by_name(progs2, PROGRAM_NAMES[2]) is progs2[2]
assert program_by_name(progs2, "س") is None
assert dict(AUTOFILL_MAP)["carrier"] == "airline"
print(f"  OK: تكلفة {total:,.0f} من الغرفة والخدمات")

print("\n=== النافذة: تبديل البرنامج والحفظ (معزول) ===")
# عزل الإعدادات وقاعدة البيانات عن ملفات المستخدم الحقيقية
import hajj_app.storage as _st
_SET = _pl.Path(_OUTDIR) / "prog_settings.json"
_SET.unlink(missing_ok=True)
_st.settings_path = lambda: _SET
import hajj_app.gui as _g
_TESTDB = _pl.Path(_OUTDIR) / "testdata_prog" / "hajjaj.json"
_TESTDB.parent.mkdir(parents=True, exist_ok=True)
for _p in (_TESTDB, _TESTDB.with_suffix(".bak")):
    _p.unlink(missing_ok=True)
_g.default_data_path = lambda: _TESTDB

from tkinter import Tk
from hajj_app.gui import HajjApp, ProgramsDialog
root = Tk(); root.withdraw()
app = HajjApp(root)
d = ProgramsDialog(root, app); d.update()
d._vars["hotel"].set("كونراد مكة")
d._vars["cost_double"].set("12000")
d._vars["transport"].set("جيمس")
d._sel.set("1"); d._switch()                    # ينقل ويحفظ البرنامج الأول
d._vars["hotel"].set("فندق الصفوة")
d._save()
loaded = app._load_programs()
assert loaded[0].hotel == "كونراد مكة", loaded[0].hotel
assert loaded[0].cost_double == "12,000", loaded[0].cost_double   # طُبِّع بالفواصل
assert loaded[0].transport == "جيمس"
assert loaded[1].hotel == "فندق الصفوة"
assert loaded[0].svc_jeems == "40,000"          # طُبِّعت أسعار الخدمات بالفواصل
assert _SET.is_file()                           # حُفظ على القرص المعزول
print("  OK: تبديل + حفظ + إعادة تحميل معزول")

print("\n=== نافذة التعديل: تطبيق البرنامج (تعبئة + احتساب) ===")
import tkinter.messagebox as _mb
_mb.showinfo = lambda *a, **k: None              # لا تعليق على النوافذ
from hajj_app.gui import EditDialog
from hajj_app.mrz import PassportData
rec = PassportData(full_name_ar="حاج", room_type="ثنائية")
dlg = EditDialog(root, rec, on_save=lambda r: None)
dlg.vars["program"].set(PROGRAM_NAMES[0])         # البرنامج الأول (كونراد + جيمس)
dlg._apply_program()
assert dlg.vars["hotel"].get() == "كونراد مكة", dlg.vars["hotel"].get()
assert dlg.vars["transport"].get() == "جيمس", dlg.vars["transport"].get()
# ثنائية 12,000 + جيمس 40,000 (المواصلات جيمس) = 52,000
assert dlg.vars["program_value"].get() == "52,000", dlg.vars["program_value"].get()
dlg.destroy()
print("  OK: عُبّئ الفندق/المواصلات وحُسبت القيمة")

print("\n=== تطبيق البرنامج على دفعة (تعديل جماعي) ===")
# البرنامج الأول محفوظ: كونراد + جيمس + ثنائية 12,000
app.records = [
    PassportData(full_name_ar="أ", room_type="ثنائية"),
    PassportData(full_name_ar="ب", room_type="ثنائية", wheelchair="نعم"),
]
n = app._apply_program_bulk([0, 1], PROGRAM_NAMES[0])
assert n == 2
for r in app.records:
    assert r.program == PROGRAM_NAMES[0] and r.hotel == "كونراد مكة"
    assert r.transport == "جيمس"
# ثنائية 12,000 + جيمس 40,000 = 52,000 ؛ والثاني + كرسي 1,000 = 53,000
assert app.records[0].program_value == "52,000", app.records[0].program_value
assert app.records[1].program_value == "53,000", app.records[1].program_value
assert app._apply_program_bulk([0], "غير معرّف") == 0
root.destroy()
print("  OK: طُبِّق على حاجَّين بتكلفة كلٍّ على حِدة")

print("\n*** PROGRAMS TESTS PASSED ***")
