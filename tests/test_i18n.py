# -*- coding: utf-8 -*-
"""اختبار الواجهة ثنائية اللغة (عربي/إنجليزي) وإمكانية الاختيار."""
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
from hajj_app import i18n
from hajj_app.auth import Session

WORK = pathlib.Path(_OUTDIR) / "i18n"
WORK.mkdir(parents=True, exist_ok=True)
DB = WORK / "d.json"
_st.default_data_path = lambda: DB
_g.default_data_path = lambda: DB
for _f in WORK.glob("*"):
    if _f.is_file():
        _f.unlink()

print("=== دالة الترجمة ===")
i18n.set_lang("ar")
assert i18n.tr("🚪  تسجيل الخروج") == "🚪  تسجيل الخروج"
i18n.set_lang("en")
assert i18n.tr("🚪  تسجيل الخروج") == "🚪  Sign Out"
assert i18n.tr("نصّ غير مترجم") == "نصّ غير مترجم"          # يرجع العربي
assert i18n.field_label("full_name_ar", "اسم الحاج بالعربي") == "Name (AR)"
i18n.set_lang("ar")
assert i18n.field_label("full_name_ar", "اسم الحاج بالعربي") == "اسم الحاج بالعربي"
print("  OK: tr يترجم حسب اللغة ويرجع العربي عند غياب الترجمة")

print("\n=== الواجهة بالإنجليزية ===")
_st.save_settings({"ui": {"ui_lang": "en"}})
from hajj_app.gui import HajjApp
root = tk.Tk(); root.withdraw()
app = HajjApp(root, session=Session("MHU", b"0" * 32, role="admin"))
assert i18n.get_lang() == "en"
labels = []
for m in app._menus:
    end = m.index("end")
    for i in range(0, (end + 1) if end is not None else 0):
        try:
            labels.append(m.entrycget(i, "label"))
        except Exception:
            pass
assert any("New Season" in x for x in labels), "قوائم البرامج لم تُترجم"
assert any("Sign Out" in x for x in labels) and any("Backup Now" in x for x in labels)
assert app._col_labels["full_name_ar"] == "Name (AR)"      # رأس العمود إنجليزي
assert app._col_labels["passport_number"] == "Passport No."
print("  OK: القوائم ورؤوس الأعمدة بالإنجليزية")

print("\n=== تبديل اللغة يعيد البناء ويحفظ الاختيار ===")
_g.messagebox.askyesno = lambda *a, **k: True
app.change_language()                                      # يدمّر النافذة داخلياً
assert app._exit_action == "restart"                       # يطلب إعادة البناء
assert _st.load_settings()["ui"]["ui_lang"] == "ar"        # عاد للعربية وحُفظ
i18n.set_lang("ar")
print("  OK: التبديل يحفظ اللغة ويطلب إعادة بناء الواجهة")

print("\n*** I18N TESTS PASSED ***")
