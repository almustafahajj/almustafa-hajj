# -*- coding: utf-8 -*-
"""اختبار «مواعيد وتعليمات السفر»: التخزين والقوالب والنافذة وتصدير PDF."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pathlib
import tkinter as tk
import hajj_app.storage as _st
import hajj_app.gui as _g
from hajj_app import travel
from hajj_app.pdf_io import export_travel_pdf

WORK = pathlib.Path(_OUTDIR) / "travel"
WORK.mkdir(parents=True, exist_ok=True)
for _f in WORK.glob("*"):
    if _f.is_file():
        _f.unlink()
DB = WORK / "d.json"
_st.default_data_path = lambda: DB
_g.default_data_path = lambda: DB

print("=== القوالب والتخزين ===")
s = {}
d0 = travel.load_travel(s, 0)
assert d0["flight"]["out_flight"] == "SV 569"          # مثال البرنامج الأول
assert d0["instructions"].startswith("1-") and "الوزن المسموح" in d0["luggage"]
assert travel.load_travel(s, 1)["flight"] == {}        # البرامج الأخرى بلا مثال
travel.save_travel(s, 0, {"flight": {"out_flight": "SV 999"},
                          "instructions": "خاص", "luggage": "",
                          "notes": "", "contacts": ""})
d0b = travel.load_travel(s, 0)
assert d0b["flight"]["out_flight"] == "SV 999" and d0b["instructions"] == "خاص"
print("  OK: قوالب افتراضية + مثال البرنامج الأول + حفظ يعلو الافتراضي")

print("\n=== تصدير PDF ===")
PDF = WORK / "t.pdf"
export_travel_pdf(PDF, program_name="البرنامج الأول",
                  data=travel.default_travel(0),
                  itinerary=[["8 ذو الحجة", "2026-5-25", "التوجه إلى منى", "منى", ""]],
                  season="1447")
assert PDF.read_bytes()[:5] == b"%PDF-" and PDF.stat().st_size > 3000
print("  OK: PDF مواعيد وتعليمات السفر صالح")

print("\n=== النافذة: تعديل وحفظ وتصدير ===")
_out = WORK / "dlg.pdf"
_g.open_preview = lambda parent, fn, name, ext: (fn(str(_out)), str(_out))[1]
root = tk.Tk(); root.withdraw()
app = _g.HajjApp(root, session=None)
dlg = _g.TravelInfoDialog(root, app)
dlg._flight_vars["out_flight"].set("SV 111")
dlg._texts["notes"].delete("1.0", "end"); dlg._texts["notes"].insert("1.0", "ملاحظة")
dlg._save()
saved = travel.load_travel(_st.load_settings(), 0)
assert saved["flight"]["out_flight"] == "SV 111" and saved["notes"] == "ملاحظة"
# التبديل بين البرامج يحفظ الحالة
dlg._sel.set("1"); dlg._switch()
assert dlg._current == 1
dlg._export()
assert _out.read_bytes()[:5] == b"%PDF-"
root.destroy()
print("  OK: النافذة تحفظ الرحلة والنصوص وتصدّر PDF، والتبديل يعمل")

print("\n*** TRAVEL TESTS PASSED ***")
