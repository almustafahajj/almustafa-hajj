# -*- coding: utf-8 -*-
"""اختبار تخزين صور الحجاج مشفّرة، وطباعة كل الجوازات."""
import sys, io, shutil
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from PIL import Image as PILImage
import hajj_app.storage as _storage
from hajj_app import auth, images
from hajj_app.pdf_io import export_passports_pdf

# عزل مجلد البيانات عن بيانات المستخدم
WORK = Path(_OUTDIR) / "imgdata"
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True, exist_ok=True)
_storage.default_data_path = lambda: WORK / "hajjaj.json"

session, _rk = auth.create_account("almustafa", "Hajj-2026-Secure", WORK / "auth.json")

# نصنع صورة اختبار
src = WORK / "sample.png"
PILImage.new("RGB", (300, 200), (30, 120, 90)).save(src)
sample_bytes = src.read_bytes()

print("=== حفظ الصورة مشفّرة ===")
image_id = images.new_image_id()
images.save_image(image_id, images.PASSPORT, src, session)
assert images.has_image(image_id, images.PASSPORT)
stored = images._image_path(image_id, images.PASSPORT).read_bytes()
assert stored != sample_bytes, "الصورة محفوظة بلا تشفير!"
assert sample_bytes[:8] not in stored, "بايتات الصورة الأصلية ظاهرة في الملف المشفّر"
print(f"  OK: الملف مشفّر ({len(stored)} بايت)، لا يطابق الأصل")

print("\n=== فكّ التشفير يعيد الصورة الأصلية ===")
back = images.load_image(image_id, images.PASSPORT, session)
assert back == sample_bytes, "فكّ التشفير لم يُرجع الصورة كما هي"
print("  OK: الصورة المفكوكة تطابق الأصل تماماً")

print("\n=== مفتاح خاطئ لا يفكّ الصورة ===")
other, _ = auth.create_account("x", "Another-Pass-99", WORK / "other.json")
assert images.load_image(image_id, images.PASSPORT, other) is None
print("  OK: جلسة أخرى لا تقرأ الصورة")

print("\n=== الأنواع الأربعة (جواز، شخصية، هوية، تصريح) ===")
assert set(images.KINDS) == {images.PASSPORT, images.PHOTO, images.ID_CARD, images.PERMIT}
for kind in images.KINDS:
    images.save_image(image_id, kind, src, session)
    assert images.has_image(image_id, kind), kind
    assert images.KIND_LABELS[kind]
print("  OK: تُحفظ الأنواع الأربعة، ولكلٍّ عنوان")

print("\n=== الحذف ===")
images.delete_all(image_id)
for kind in images.KINDS:
    assert not images.has_image(image_id, kind), kind
print("  OK: delete_all يحذف كل الأنواع الأربعة")

print("\n=== رفع ملف PDF كصورة جواز ===")
# نصنع PDF من صفحتين
import fitz as _fitz
pdf_src = WORK / "scan.pdf"
_doc = _fitz.open()
for _ in range(2):
    _doc.new_page(width=400, height=560)
_doc.save(str(pdf_src))
_doc.close()

pid = images.new_image_id()
images.save_image(pid, images.PASSPORT, pdf_src, session)
raw = images.load_image(pid, images.PASSPORT, session)
assert images.is_pdf(raw), "لم يُتعرَّف على الـ PDF"
# المعاينة تُنتج صورة (أول صفحة)
prev = images.to_pil_image(raw)
assert prev is not None and prev.width > 0
print(f"  OK: PDF مخزّن مشفّراً، والمعاينة تُنتج صورة {prev.size}")
# الطباعة تُنتج صفحتين (ورقتا الـ PDF)
pages = images.render_pages_png(raw)
assert len(pages) == 2, len(pages)
assert all(p[:8].startswith(b"\x89PNG") for p in pages)
print("  OK: render_pages_png أنتج صفحتين PNG من PDF بصفحتين")
# صورة عادية تبقى صفحة واحدة
one = images.render_pages_png(sample_bytes)
assert len(one) == 1 and one[0] == sample_bytes
print("  OK: الصورة العادية تبقى صفحة واحدة كما هي")
images.delete_all(pid)

print("\n=== طباعة كل الجوازات في PDF واحد ===")
# ثلاث صور بأسماء
paths = []
for i, color in enumerate([(200, 60, 60), (60, 60, 200), (60, 200, 60)]):
    p = WORK / f"p{i}.png"
    PILImage.new("RGB", (600, 400), color).save(p)
    paths.append((f"حاج رقم {i+1}", str(p)))
pdf = _os.path.join(_OUTDIR, "passports.pdf")
export_passports_pdf(paths, pdf)
assert _os.path.getsize(pdf) > 3000
with open(pdf, "rb") as fh:
    assert fh.read(5) == b"%PDF-"
# ثلاث صفحات (جواز لكل صفحة)
import fitz
doc = fitz.open(pdf)
assert doc.page_count == 3, doc.page_count
doc.close()
print(f"  OK: PDF فيه 3 صفحات، جواز لكل حاج")

print("\n*** IMAGE TESTS PASSED ***")
