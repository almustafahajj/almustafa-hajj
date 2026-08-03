# -*- coding: utf-8 -*-
"""اختبار وضع التشغيل (حج/عمرة): فصل الملفّات، المسمّيات، وإخفاء ميزات الحج."""
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
from hajj_app import app_mode
import hajj_app.storage as _st
import hajj_app.gui as _g

print("=== الافتراضي والتبديل ===")
assert app_mode.get_mode() == "hajj" and app_mode.is_hajj()
app_mode.set_mode("umrah")
assert app_mode.is_umrah() and not app_mode.is_hajj()
app_mode.set_mode("مجهول")                 # قيمة غير معروفة -> تعود للحج
assert app_mode.get_mode() == "hajj"
print("  OK: الافتراضي حج، والتبديل، وحماية القيم غير المعروفة")

print("\n=== فصل ملفّات البيانات والإعدادات ===")
WORK = pathlib.Path(_OUTDIR) / "mode"
WORK.mkdir(parents=True, exist_ok=True)
_st.default_data_path = lambda: WORK / app_mode.data_filename()
app_mode.set_mode("hajj")
assert _st.default_data_path().name == "hajjaj.json"
assert _st.settings_path().name == "settings.json"
app_mode.set_mode("umrah")
assert _st.default_data_path().name == "umrah.json"
assert _st.settings_path().name == "settings_umrah.json"
# الكتابة في وضعٍ لا تظهر في الآخر
_st.save_settings({"company": "عمرة"})
assert _st.load_settings().get("company") == "عمرة"
app_mode.set_mode("hajj")
assert _st.load_settings().get("company") != "عمرة"   # ملفّ منفصل
_st.save_settings({"company": "حج"})
app_mode.set_mode("umrah")
assert _st.load_settings().get("company") == "عمرة"
print("  OK: لكلّ وضع ملفّ بيانات وإعدادات مستقلّ لا يختلط بالآخر")

print("\n=== المسمّيات ===")
app_mode.set_mode("hajj")
assert "الحج" in app_mode.label("window_title") and app_mode.label("splash") == "برنامج الحج"
assert app_mode.mode_label("hajj") == "الحج"
app_mode.set_mode("umrah")
assert "العمرة" in app_mode.label("window_title") and "المعتمرين" in app_mode.label("window_title")
assert app_mode.label("program_season") == "برنامج العمرة موسم"
assert app_mode.mode_label("umrah") == "العمرة"
print("  OK: العنوان والمسمّيات تتبع الوضع")

print("\n=== إخفاء ميزات الحج في واجهة العمرة ===")
_st.default_data_path = lambda: WORK / app_mode.data_filename()
_g.default_data_path = _st.default_data_path

def _menu_labels(app):
    """يجمع نصوص كل عناصر القوائم (كل عنصر في app._menus قائمة tk.Menu)."""
    found = set()
    for menu in getattr(app, "_menus", []):
        try:
            end = menu.index("end")
        except Exception:
            end = None
        if end is None:
            continue
        for i in range(end + 1):
            try:
                found.add(menu.entrycget(i, "label"))
            except Exception:
                pass                       # فاصل بلا عنوان
    return found

# وضع العمرة: لا «جدول المناسك» ولا «خيام المخيمات»
app_mode.set_mode("umrah")
root = tk.Tk(); root.withdraw()
app = _g.HajjApp(root, session=None)
labels_umrah = " ".join(_menu_labels(app))
assert "جدول المناسك" not in labels_umrah, labels_umrah
assert "خيام المخيمات" not in labels_umrah, labels_umrah
# زرّ التبديل يعرض الوضع الآخر (الحج)
assert "التبديل إلى الحج" in labels_umrah, labels_umrah
assert hasattr(app, "switch_mode")
root.destroy()
print("  OK: العمرة تُخفي المناسك والخيام وتعرض «التبديل إلى الحج»")

# وضع الحج: الميزتان ظاهرتان وزرّ التبديل يعرض العمرة
app_mode.set_mode("hajj")
root2 = tk.Tk(); root2.withdraw()
app2 = _g.HajjApp(root2, session=None)
labels_hajj = " ".join(_menu_labels(app2))
assert "جدول المناسك" in labels_hajj, labels_hajj
assert "خيام المخيمات" in labels_hajj, labels_hajj
assert "التبديل إلى العمرة" in labels_hajj, labels_hajj
root2.destroy()
print("  OK: الحج يُظهر المناسك والخيام ويعرض «التبديل إلى العمرة»")

print("\n=== التبديل المباشر بين النافذتين ===")
import tkinter.messagebox as _mbx
_mbx.askyesno = lambda *a, **k: True        # نؤكّد التبديل تلقائياً
# زرّ التبديل ظاهر في ترويسة نافذة الحج (وصولٌ سهل لا مدفون في القوائم)
app_mode.set_mode("hajj")
r3 = tk.Tk(); r3.withdraw()
app3 = _g.HajjApp(r3, session=None)
app3.switch_mode()                          # يهدم r3 ويضبط وجهة التبديل
assert app3._exit_action == "switch:umrah", app3._exit_action  # مباشرةً للعمرة
# ومن نافذة العمرة → مباشرةً إلى الحج
app_mode.set_mode("umrah")
import hajj_app.umrah_gui as _ug
r4 = tk.Tk(); r4.withdraw()
app4 = _ug.UmrahApp(r4, session=None)
app4.switch_mode()
assert app4._exit_action == "switch:hajj", app4._exit_action
print("  OK: التبديل ينتقل مباشرةً إلى نافذة الوضع الآخر (بلا شاشة اختيار)")

app_mode.set_mode("hajj")                  # إعادة للوضع الافتراضي
print("\n*** APP MODE TESTS PASSED ***")
