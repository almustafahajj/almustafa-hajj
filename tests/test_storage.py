# -*- coding: utf-8 -*-
"""Persistence: round trip, corruption recovery, schema drift, GUI lifecycle."""
import sys, io, os, json, shutil
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from hajj_app.storage import save_records, load_records, default_data_path
from hajj_app.mrz import PassportData

OUT = Path(_OUTDIR)
DB = OUT / "store" / "hajjaj.json"
if DB.parent.exists(): shutil.rmtree(DB.parent)

print("default path:", default_data_path())

# ---------- 1. empty / missing file ----------
recs, note = load_records(DB)
assert recs == [] and note == "", (recs, note)
print("OK: missing file -> empty, no scary message")

# ---------- 2. round trip with every field populated ----------
full = PassportData(
    full_name_en="AYMAN MOHAMMED ALSHEHABI", full_name_ar="أيمن محمد الشهابي",
    family_number="F-12", reference_number="REF-9001", phone="0559876543",
    hotel="فندق الصفوة", room_type="رباعية", sex="ذكر", nationality_ar="السعودية",
    birth_date="1985-01-01", passport_number="A1234567", expiry_date="2030-12-01",
    airline="السعودية SV1023", arrival_date="2026-05-20", arrival_time="14:30",
    departure_date="2026-06-05", departure_time="09:45", transport="باص مكيف",
    hady="نعم", wheelchair="لا", executive_service="نعم",
    program_value="15,000", paid_amount="5,000", notes="مرافق لوالدته",
    surname_en="ALSHEHABI", given_names_en="AYMAN MOHAMMED", nationality="SAU",
    issuing_country="SAU", personal_number="1098", source_file="scan.pdf (صفحة 1)",
    checksum_ok=True, warnings=["الاسم العربي مقروء ضوئياً — يجب التأكد منه"],
)
second = PassportData(full_name_ar="فاطمة خان", passport_number="AB987654")
save_records([full, second], DB)
print("saved:", DB.stat().st_size, "bytes")

back, note = load_records(DB)
assert note == "" and len(back) == 2, (note, len(back))
b = back[0]
from dataclasses import fields as dfields
for f in dfields(PassportData):
    assert getattr(b, f.name) == getattr(full, f.name), \
        (f.name, getattr(b, f.name), getattr(full, f.name))
print("OK: all", len(dfields(PassportData)), "fields survived round trip")
assert b.warnings == ["الاسم العربي مقروء ضوئياً — يجب التأكد منه"]
assert b.checksum_ok is True
print("OK: warnings list + bool preserved with correct types")

# ---------- 3. Arabic must be stored readably, not escaped ----------
raw = DB.read_text(encoding="utf-8")
assert "أيمن محمد الشهابي" in raw, "Arabic got escaped"
assert '"schema": 1' in raw
print("OK: Arabic stored as readable UTF-8")

# ---------- 4. backup created on overwrite ----------
save_records([full], DB)
assert DB.with_suffix(".bak").is_file(), "no .bak written"
bak = json.loads(DB.with_suffix(".bak").read_text(encoding="utf-8"))
assert bak["count"] == 2, bak["count"]     # backup holds the PREVIOUS state
print("OK: .bak holds previous state (2 records) while main has 1")

# ---------- 5. corrupt file -> recover from backup ----------
DB.write_text("{ this is not valid json at all", encoding="utf-8")
recs, note = load_records(DB)
print("\ncorruption note:\n  " + note.replace("\n", "\n  "))
assert len(recs) == 2, f"backup recovery failed: {len(recs)}"
assert "الاحتياطية" in note
salvaged = list(DB.parent.glob("*تالف*"))
assert salvaged, "corrupt file was not preserved"
print("OK: recovered 2 from backup; corrupt file kept as", salvaged[0].name)

# ---------- 6. corrupt with NO backup -> empty + clear message, file kept ----------
shutil.rmtree(DB.parent); DB.parent.mkdir(parents=True)
DB.write_text("!!!broken!!!", encoding="utf-8")
recs, note = load_records(DB)
assert recs == [] and "تالف" in note, (recs, note)
assert list(DB.parent.glob("*تالف*")), "corrupt file lost"
print("OK: no backup -> empty list, corrupt file preserved, clear message")

# ---------- 7. schema drift: old/unknown fields ----------
DB.write_text(json.dumps({
    "schema": 99, "records": [
        {"full_name_ar": "عمر حسن", "passport_number": "C555",
         "age": "35", "group_name": "الفوج الأول",      # removed columns
         "hotel": None, "warnings": "not-a-list"},       # wrong types
        "this is not a dict",                            # junk entry
    ]}, ensure_ascii=False), encoding="utf-8")
recs, note = load_records(DB)
assert len(recs) == 1, len(recs)
assert recs[0].full_name_ar == "عمر حسن" and recs[0].passport_number == "C555"
assert recs[0].hotel == "" and recs[0].warnings == []
print("OK: unknown fields ignored, bad types coerced, junk row skipped")

# ---------- 8. GUI lifecycle: data survives a close/reopen ----------
print("\n=== GUI LIFECYCLE ===")
shutil.rmtree(DB.parent); DB.parent.mkdir(parents=True)
from tkinter import Tk
import hajj_app.gui as guimod
from hajj_app.gui import HajjApp

root = Tk(); root.withdraw()
app = HajjApp(root)
app.data_path = DB                      # redirect off the real user file
app.records = [full, second]
app.refresh(); app.save_data()
assert DB.is_file()
root.destroy()
print("  session 1: saved", len(app.records), "records")

root2 = Tk(); root2.withdraw()
guimod.default_data_path = lambda: DB   # simulate app restarting on that file
app2 = HajjApp(root2)
print("  session 2: loaded", len(app2.records), "records")
print("  status:", app2.status.get())
assert len(app2.records) == 2, len(app2.records)
assert app2.records[0].full_name_ar == "أيمن محمد الشهابي"
assert len(app2.tree.get_children()) == 2
assert "استعادة" in app2.status.get()

# deleting must persist too
app2.data_path = DB
del app2.records[1]
app2.refresh(); app2.save_data()
again, _ = load_records(DB)
assert len(again) == 1, len(again)
print("  OK: delete persisted -> 1 record on disk")

# closing via the window button saves
app2.records.append(second)
app2._on_close()
final, _ = load_records(DB)
assert len(final) == 2, len(final)
print("  OK: closing the window saved", len(final), "records")

print("\n*** STORAGE TESTS PASSED ***")
