# -*- coding: utf-8 -*-
"""اختبار سجلّ التدقيق: الوحدة وتسجيل العمليات من الواجهة."""
import sys, io
import os as _os
import pathlib as _pl
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.audit import record, read_entries, clear_log, prune

print("=== وحدة السجلّ: كتابة/قراءة/تجاهل التالف ===")
LOG = _pl.Path(_OUTDIR) / "audit_unit.log"
LOG.unlink(missing_ok=True)
record("إضافة يدوية", "محمد", user="أيمن", path=LOG)
record("حذف سجلات", "2 سجل", user="أيمن", path=LOG)
ents = read_entries(path=LOG)
assert len(ents) == 2, len(ents)
assert ents[0]["action"] == "حذف سجلات", ents[0]     # الأحدث أولاً
assert ents[0]["user"] == "أيمن" and ents[0]["ts"]
# سطر تالف لا يُعطّل القراءة
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("{ليس JSON}\n")
assert len(read_entries(path=LOG)) == 2
# التقليم يُبقي الأحدث
for i in range(10):
    record("عملية", str(i), path=LOG)
prune(LOG, keep=5)
assert len(read_entries(path=LOG)) == 5
clear_log(LOG)
assert read_entries(path=LOG) == []
print("  OK: كتابة، قراءة (الأحدث أولاً)، تجاهل التالف، تقليم، مسح")

print("\n=== تسجيل العمليات من الواجهة (معزول) ===")
import hajj_app.storage as _st
_TESTDB = _pl.Path(_OUTDIR) / "audit_gui" / "hajjaj.json"
_TESTDB.parent.mkdir(parents=True, exist_ok=True)
for _p in _TESTDB.parent.glob("*"):
    _p.unlink()
_st.default_data_path = lambda: _TESTDB          # يعزل مسار audit.log أيضاً
import hajj_app.gui as _g
_g.default_data_path = lambda: _TESTDB
import tkinter.messagebox as _mb
_mb.askyesno = lambda *a, **k: True
from tkinter import Tk
from hajj_app.gui import HajjApp, AuditDialog
from hajj_app.mrz import PassportData
root = Tk(); root.withdraw()
app = HajjApp(root)
app.records = [PassportData(full_name_ar=f"حاج {i}", passport_number=f"A{i}")
               for i in range(3)]
app.refresh()
app.tree.selection_set(app.tree.get_children()[0])
app.delete_selected()                            # يجب أن يُسجَّل
from hajj_app.audit import audit_path
entries = read_entries(path=audit_path())
assert any(e["action"] == "حذف سجلات" for e in entries), entries
assert entries[0]["user"] == "مفتوح"             # لا جلسة -> وضع مفتوح
# النافذة تعرض القيود
d = AuditDialog(root); d.update()
assert len(d.tree.get_children()) >= 1
d.destroy()
root.destroy()
print("  OK: الحذف يُسجَّل ويظهر في النافذة")

print("\n*** AUDIT TESTS PASSED ***")
