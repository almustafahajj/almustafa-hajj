# -*- coding: utf-8 -*-
"""Drive the real GUI worker thread over a mixed batch: PDF + image + bad file."""
import sys, io, os, time
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tkinter import Tk
from hajj_app.gui import HajjApp, SCAN_TYPES
# --- isolate tests from the user's real data file ---
import hajj_app.gui as _g, hajj_app.storage as _st, pathlib as _pl
_TESTDB = _pl.Path(_OUTDIR) / "testdata" / "hajjaj.json"
_TESTDB.parent.mkdir(parents=True, exist_ok=True)
for _p in (_TESTDB, _TESTDB.with_suffix('.bak')):
    _p.unlink(missing_ok=True)
_g.default_data_path = lambda: _TESTDB
_st.default_data_path = lambda: _TESTDB   # عزل مجلد الصور أيضاً
# كتم نوافذ الرسائل: الدفعة تتضمّن ملفاً تالفاً عمداً (notapdf.pdf) فلا
# نريد نافذة «ملفات تعذّرت قراءتها» أن تقفز وتطلب ضغطاً أثناء الاختبار.
_g.messagebox.showwarning = lambda *a, **k: None
_g.messagebox.showerror = lambda *a, **k: None
_g.messagebox.showinfo = lambda *a, **k: None

OUT = _OUTDIR

exts = SCAN_TYPES[0][1]
print("file dialog accepts:", exts)
assert "*.pdf" in exts, exts

root = Tk(); root.withdraw()
app = HajjApp(root)

# Mixed batch: 3-passport PDF + single image + a corrupt file that must fail cleanly
batch = [
    os.path.join(OUT, "passports_text.pdf"),
    os.path.join(OUT, "fake_passport.png"),
    os.path.join(OUT, "notapdf.pdf"),
]
for b in batch:
    assert os.path.exists(b), b

app.progress.configure(maximum=len(batch), value=0)
app._scan_state = {"failures": [], "notes": [], "added": 0}

import threading
threading.Thread(target=app._scan_worker, args=(batch,), daemon=True).start()

# pump the Tk event loop until the worker signals done
deadline = time.time() + 240
while time.time() < deadline:
    app._drain_results(len(batch))
    root.update()
    if app._scan_state["added"] and not app.progress["value"]:
        break
    time.sleep(0.2)

print("\nrecords loaded:", len(app.records))
for r in app.records:
    print(f"  {r.passport_number:>10} | {r.full_name_en[:32]:32} | {r.source_file}")
print("failures:", [f[0] for f in app._scan_state["failures"]])
print("status:", app.status.get())

# 3 from the PDF + 1 from the image
assert len(app.records) == 4, f"expected 4, got {len(app.records)}"
assert len(app._scan_state["failures"]) == 1, app._scan_state["failures"]
assert app._scan_state["failures"][0][0] == "notapdf.pdf"
nums = sorted(r.passport_number for r in app.records)
assert nums == ["A1234567", "A1234567", "AB987654", "C5551234"], nums

# table must show all 4
app.refresh()
assert len(app.tree.get_children()) == 4
print("OK: table shows all 4")

# صورة الجواز الممسوحة تُحفظ تلقائياً: الصورة المفردة (fake_passport.png)
# أنتجت حاجاً واحداً، فيجب أن تُرفَق صورته. أما الـ PDF (3 حجاج) فلا يُرفَق.
from hajj_app import images as _img
img_recs = [r for r in app.records if r.image_id and _img.has_image(r.image_id, _img.PASSPORT)]
assert len(img_recs) == 1, f"صورة الجواز لم تُحفظ تلقائياً: {len(img_recs)}"
data = _img.load_image(img_recs[0].image_id, _img.PASSPORT, None)
assert data and data[:3] in (b"\x89PN", b"\xff\xd8\xff"), "الصورة المحفوظة تالفة"
print("OK: صورة الجواز الممسوحة (صورة مفردة) حُفظت تلقائياً")

# exporting the combined set must work
xl = os.path.join(OUT, "gui_mixed.xlsx"); pf = os.path.join(OUT, "gui_mixed.pdf")
from hajj_app.excel_io import export_excel
from hajj_app.pdf_io import export_pdf
export_excel(app.records, xl); export_pdf(app.records, pf)
assert os.path.getsize(xl) > 3000 and os.path.getsize(pf) > 3000
print("OK: exported mixed set to Excel + PDF")

root.destroy()
print("\n*** GUI PDF INTEGRATION PASSED ***")
