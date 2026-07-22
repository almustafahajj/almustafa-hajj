# -*- coding: utf-8 -*-
"""اختبار النسخ الاحتياطية المؤرّخة (اللقطات): كتابة، تقليم، استعادة."""
import sys, io
import os as _os
import pathlib as _pl
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import hajj_app.storage as st
from hajj_app.mrz import PassportData

# عزل: ملف بيانات وهمي في مجلد الاختبار، فالنسخ تذهب لمجلده لا لمجلد المستخدم
_DB = _pl.Path(_OUTDIR) / "backupdata" / "hajjaj.json"
if _DB.parent.exists():
    import shutil
    shutil.rmtree(_DB.parent)
_DB.parent.mkdir(parents=True, exist_ok=True)
st.default_data_path = lambda: _DB


def rec(name, pp):
    return PassportData(full_name_ar=name, passport_number=pp)


print("=== كتابة لقطات مؤرّخة واستعادتها ===")
recs1 = [rec("أول", "P1"), rec("ثانٍ", "P2")]
p1 = st.write_snapshot(recs1, session=None, stamp="20260101-100000")
assert p1.is_file() and p1.parent == st.backups_dir()
recs2 = [rec("ثالث", "P3")]
st.write_snapshot(recs2, session=None, stamp="20260102-110000")

snaps = st.list_snapshots()
assert len(snaps) == 2
# الأحدث أولاً
assert snaps[0].name == "hajjaj-20260102-110000.json", [s.name for s in snaps]
# الاستعادة عبر load_records
restored, note = st.load_records(snaps[1], session=None)
assert [r.full_name_ar for r in restored] == ["أول", "ثانٍ"], restored
print(f"  OK: لقطتان، الأحدث {st.snapshot_label(snaps[0])}، والاستعادة سليمة")

print("\n=== الطابع الزمني المقروء ===")
assert st.snapshot_label(p1) == "2026-01-01 10:00", st.snapshot_label(p1)
print(f"  OK: {st.snapshot_label(p1)}")

print("\n=== التقليم يُبقي الأحدث فقط ===")
for i in range(6):
    st.write_snapshot(recs1, session=None, stamp=f"20260110-1000{i:02d}", keep=3)
snaps = st.list_snapshots()
assert len(snaps) == 3, len(snaps)          # keep=3
# الأحدث محفوظة، والأقدم حُذفت
names = [s.name for s in snaps]
assert names[0] == "hajjaj-20260110-100005.json", names
assert "hajjaj-20260101-100000.json" not in names
print(f"  OK: بقيت 3 لقطات أحدث بعد التقليم")

print("\n*** BACKUP TESTS PASSED ***")
