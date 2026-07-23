# -*- coding: utf-8 -*-
"""اختبار رسائل واتساب الجماعية: تطبيع الأرقام، الرابط، والنافذة."""
import sys, io
import os as _os
import pathlib as _pl
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.whatsapp import to_intl, wa_link, render_message
from hajj_app.mrz import PassportData


def rec(**kw):
    return PassportData(**kw)


print("=== تطبيع الأرقام إلى صيغة دولية ===")
assert to_intl("0501112233") == "971501112233"
assert to_intl("٠٥٠١١١٢٢٣٣") == "971501112233"          # أرقام عربية
assert to_intl("+971501112233") == "971501112233"
assert to_intl("00971501112233") == "971501112233"
assert to_intl("971501112233") == "971501112233"
assert to_intl("501112233") == "971501112233"           # محلي بلا صفر
assert to_intl("0501112233", default_cc="966") == "966501112233"
assert to_intl("050-111 2233") == "971501112233"        # يزيل الفواصل
assert to_intl("") is None and to_intl("123") is None   # فارغ/قصير
print("  OK: كل الصيغ تُحوَّل بشكل صحيح")

print("\n=== القالب والرابط ===")
r = rec(full_name_ar="محمد الشامسي", hotel="كونراد", program="البرنامج الأول",
        phone="0501112233")
msg = render_message("مرحباً {الاسم}، فندقكم {الفندق} ضمن {البرنامج}", r)
assert msg == "مرحباً محمد الشامسي، فندقكم كونراد ضمن البرنامج الأول", msg
link = wa_link(r.phone, msg)
assert link.startswith("https://wa.me/971501112233?text=") and "%" in link
assert wa_link("", "x") is None                          # بلا رقم -> لا رابط
print("  OK: العناصر النائبة تُستبدَل والرابط يُرمَّز")

print("\n=== النافذة: تصفية الأرقام والفتح المتسلسل ===")
import webbrowser
import hajj_app.storage as _st
_SET = _pl.Path(_OUTDIR) / "wa_settings.json"
_SET.unlink(missing_ok=True)
_st.settings_path = lambda: _SET
_st.default_data_path = lambda: _pl.Path(_OUTDIR) / "wa" / "hajjaj.json"
import hajj_app.gui as _g
_TESTDB = _pl.Path(_OUTDIR) / "wa" / "hajjaj.json"
_TESTDB.parent.mkdir(parents=True, exist_ok=True)
for _p in (_TESTDB, _TESTDB.with_suffix(".bak")):
    _p.unlink(missing_ok=True)
_g.default_data_path = lambda: _TESTDB

_opened = []
webbrowser.open = lambda u: _opened.append(u)
from tkinter import Tk
from hajj_app.gui import HajjApp, WhatsAppDialog
root = Tk(); root.withdraw()
app = HajjApp(root)
recs = [rec(full_name_ar="محمد الشامسي", phone="0501112233"),
        rec(full_name_ar="بلا هاتف", phone=""),
        rec(full_name_ar="سالم", phone="0555555555")]
d = WhatsAppDialog(root, recs, app)
d.update()
assert len(d._order) == 2, len(d._order)         # المستبعَد بلا رقم صالح
d.txt.delete("1.0", "end"); d.txt.insert("1.0", "مرحباً {الاسم}")
d._open_next()
assert len(_opened) == 1 and "wa.me/971501112233" in _opened[0]
d._open_next()
assert len(_opened) == 2 and "wa.me/971555555555" in _opened[1]
assert app._settings.get("whatsapp_cc") == "971"  # حُفظ رمز الدولة
# تغيير رمز الدولة يعيد بناء الأرقام
d.v_cc.set("966"); d._rebuild()
_opened.clear(); d._open_next()
assert "wa.me/966501112233" in _opened[0], _opened
root.destroy()
print("  OK: يستبعد بلا رقم، يفتح بالترتيب، ويحفظ رمز الدولة")

print("\n*** WHATSAPP TESTS PASSED ***")
