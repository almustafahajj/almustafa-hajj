# -*- coding: utf-8 -*-
"""Garbage-name detection + manual-add button."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.mrz import parse_mrz, check_digit, _clean_name, _is_plausible_name

def mrz2(pnum="A1234567", nat="SAU", birth="850101", sex="M", expiry="301201"):
    p9 = pnum.ljust(9, "<"); per = "".ljust(14, "<")
    l2 = (p9 + check_digit(p9) + nat + birth + check_digit(birth) + sex
          + expiry + check_digit(expiry) + per + check_digit(per))
    return l2 + check_digit(l2[0:10] + l2[13:20] + l2[21:43])
GOOD_L2 = mrz2()

print("=== _clean_name quality ===")
cases = [
    ("ALSHEHABI",                    "ALSHEHABI",        "ok"),
    ("AYMAN<MOHAMMED",               "AYMAN MOHAMMED",   "ok"),
    ("AYMAN<K<MOHAMMED",             "AYMAN MOHAMMED",   "noisy"),   # stray '<'->K
    ("KKKKKKKKKKKKKKKK",             "",                 "garbage"), # from screenshot
    # a lone token with a 3-run is only suspicious, not provably garbage —
    # the whole-name verdict is made in parse_mrz from both halves together
    ("MAHAXGHKAXKKK",                "MAHAXGHKAX",       "noisy"),
    ("XXXXXXXX",                     "",                 "garbage"), # no vowel
    ("<<<<<<<<",                     "",                 "ok"),      # pure filler = legit
    ("BBBB",                         "",                 "garbage"),
]
for raw, want_name, want_q in cases:
    name, q = _clean_name(raw)
    status = "OK " if (name, q) == (want_name, want_q) else "FAIL"
    print(f"  {status} {raw:22} -> {name!r:20} {q}")
    assert (name, q) == (want_name, want_q), (raw, name, q, want_name, want_q)

print("\n=== plausibility ===")
for n, want in [("ALSHEHABI", True), ("AYMAN MOHAMMED", True), ("XXXX", False),
                ("AAAAB", False), ("MOHAMMED", True), ("A", False)]:
    got = _is_plausible_name(n)
    print(f"  {n:18} plausible={got}")
    assert got == want, (n, got, want)

# ---- the exact failure from the user's screenshot ----
print("\n=== SCREENSHOT CASE ===")
bad_l1 = "P<SAUMAHAXGHKAXKKK<<KKKKKKKKKKKKKKKK<MA<<<<<"
d = parse_mrz(bad_l1, GOOD_L2)
print("  full_name_en:", repr(d.full_name_en))
print("  passport    :", d.passport_number, "| birth:", d.birth_date)
print("  checksum_ok :", d.checksum_ok)
print("  warnings    :", d.warnings)
assert d.full_name_en == "", f"garbage name leaked: {d.full_name_en!r}"
assert any("تعذّرت قراءة الاسم" in w for w in d.warnings), d.warnings
# verified fields must SURVIVE — only the name is discarded
assert d.passport_number == "A1234567" and d.birth_date == "1985-01-01"
assert d.checksum_ok, "checksums are independent of the name"
print("  OK: garbage name blanked, verified fields kept, warned")

# ---- a good name must still pass untouched ----
good_l1 = "P<SAUALSHEHABI<<AYMAN<MOHAMMED<<<<<<<<<<<<<<"
g = parse_mrz(good_l1, GOOD_L2)
assert g.full_name_en == "AYMAN MOHAMMED ALSHEHABI", g.full_name_en
assert g.warnings == [], g.warnings
print("  OK: clean name unaffected ->", g.full_name_en)

# ---- single-name passport (no given names) is legitimate ----
solo = parse_mrz("P<SAUSUKARNO<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", GOOD_L2)
assert solo.full_name_en == "SUKARNO", solo.full_name_en
assert solo.warnings == [], solo.warnings
print("  OK: single-name passport ->", solo.full_name_en)

# ---- MANUAL ADD BUTTON ----
print("\n=== MANUAL ADD ===")
from tkinter import Tk
from hajj_app.gui import HajjApp, EditDialog
# --- isolate tests from the user's real data + settings files ---
import hajj_app.gui as _g, hajj_app.storage as _st, pathlib as _pl
_TESTDB = _pl.Path(_OUTDIR) / "testdata" / "hajjaj.json"
_TESTDB.parent.mkdir(parents=True, exist_ok=True)
for _p in (_TESTDB, _TESTDB.with_suffix('.bak')):
    _p.unlink(missing_ok=True)
_g.default_data_path = lambda: _TESTDB
_st.default_data_path = lambda: _TESTDB     # يعزل settings.json الحقيقي أيضاً
from hajj_app.mrz import PassportData

root = Tk(); root.withdraw()
app = HajjApp(root)

labels, menus = [], []
def walk(w):
    for c in w.winfo_children():
        name = c.__class__.__name__
        if name == "Button":
            labels.append(c.cget("text"))
        elif name == "Menubutton":
            menus.append(c.cget("text"))
        walk(c)
walk(root)
print("  toolbar buttons:", labels)
print("  toolbar menus:", menus)
# البرنامج مقسّم إلى قوائم مصنّفة: الحجّاج / الكشوفات / المالية / الحماية
assert any("الحجّاج" in t for t in menus), menus
assert any("الكشوفات" in t for t in menus), menus
assert any("المالية" in t for t in menus), menus
assert callable(app.add_manual) and callable(app.edit_selected)
assert callable(app.do_stats_pdf)
assert callable(app._invoice_selected) and callable(app._contract_selected)
assert callable(app._receipt_selected) and callable(app._company_info)

# empty record must be rejected
rec = PassportData(source_file="إدخال يدوي")
added = []
dlg = EditDialog(root, rec, on_save=lambda r: added.append(r),
                 title="إضافة حاج جديد", save_text="إضافة")
assert dlg.title() == "إضافة حاج جديد"
import tkinter.messagebox as mb
_orig = mb.showwarning; blocked = []
mb.showwarning = lambda *a, **k: blocked.append(a)
dlg._save()
mb.showwarning = _orig
assert not added and blocked, "empty record should be rejected"
assert dlg.winfo_exists(), "dialog should stay open on rejection"
print("  OK: empty record rejected, dialog stays open")

# now fill it in
dlg.vars["full_name_ar"].set("محمد عبدالله")
dlg.vars["phone"].set("0551112233")
dlg.vars["program_value"].set("١٢٠٠٠")      # Arabic digits
dlg.vars["paid_amount"].set("4000")
dlg.vars["arrival_time"].set("3:15 PM")
dlg._save()
assert added, "record not saved"
r = added[0]
print(f"  saved: {r.full_name_ar} | {r.phone} | {r.program_value} | {r.arrival_time}")
assert r.program_value == "12,000", r.program_value
assert r.arrival_time == "15:15", r.arrival_time

app.records.clear()
app._after_manual_add(r)
assert len(app.records) == 1 and len(app.tree.get_children()) == 1
assert app.tree.selection() == ("0",), app.tree.selection()
print("  status:", app.status.get())
from hajj_app.fields import row_dict
assert row_dict(r, 1)["remaining_amount"] == "8,000"
print("  OK: added to table, selected, remaining derived = 8,000")

root.destroy()
print("\n*** NAME QUALITY + MANUAL ADD PASSED ***")
