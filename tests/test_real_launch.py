# -*- coding: utf-8 -*-
"""Launch the app exactly as the .bat does, against the real data path."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from tkinter import Tk
from hajj_app.gui import HajjApp
from hajj_app.mrz import PassportData

root = Tk(); root.withdraw()
app = HajjApp(root)
print("data path :", app.data_path)
print("tesseract :", app.tesseract_path)
print("records   :", len(app.records))
print("status    :", app.status.get())

# write a record through the real path, then reload in a fresh instance
app.records.append(PassportData(full_name_ar="اختبار الحفظ",
                                passport_number="TEST0001"))
app.refresh()
assert app.save_data(), "save failed"
assert Path(app.data_path).is_file()
print("saved ok  :", Path(app.data_path).stat().st_size, "bytes")
root.destroy()

root2 = Tk(); root2.withdraw()
app2 = HajjApp(root2)
print("reloaded  :", len(app2.records), "->",
      [r.full_name_ar for r in app2.records])
assert any(r.passport_number == "TEST0001" for r in app2.records)

# clean up the test row so the user starts empty
app2.records = [r for r in app2.records if r.passport_number != "TEST0001"]
app2.refresh(); app2.save_data()
root2.destroy()

leftover, _ = __import__("hajj_app.storage", fromlist=["x"]).load_records()
print("after cleanup:", len(leftover), "records")
assert not any(r.passport_number == "TEST0001" for r in leftover)
print("\n*** REAL LAUNCH + PERSISTENCE OK ***")
