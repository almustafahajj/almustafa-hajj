"""استخراج بيانات الجوازات من ملفات PDF.

ملفات PDF للجوازات تأتي على نوعين:
  1. فيها طبقة نصية (منتَجة رقمياً أو ممسوحة مع OCR مسبق) — نقرأ النص مباشرة،
     وهذا أسرع وأدق بكثير من إعادة المسح.
  2. صور ممسوحة بلا نص — نحوّل الصفحة إلى صورة ونمرّرها على نفس مسار OCR.

نجرّب النص أولاً لكل صفحة، ونرجع إلى OCR عند الفشل.
كل صفحة قد تحمل جوازاً مختلفاً، فنعالجها جميعاً ونحذف المكرر.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np

from .arabic_ocr import best_arabic_name_in_text, extract_arabic_name
from .mrz import MRZError, PassportData, parse_text
from .ocr import extract_from_array
from .tesseract_setup import arabic_supported

# دقة تحويل الصفحة إلى صورة. 300 نقطة/بوصة تكفي لقراءة خط MRZ الصغير،
# وأعلى منها يبطئ المعالجة دون فائدة تُذكر.
_RENDER_DPI = 300
# حد أقصى للصفحات حمايةً من ملف ضخم يجمّد البرنامج
_MAX_PAGES = 200


class PDFError(Exception):
    """يُرفع عند تعذّر فتح ملف PDF أو قراءته."""


def _pix_to_array(pix: fitz.Pixmap) -> np.ndarray:
    """يحوّل Pixmap إلى مصفوفة BGR التي يتوقعها OpenCV."""
    if pix.n > 3:                       # قناة شفافية أو CMYK
        pix = fitz.Pixmap(fitz.csRGB, pix)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _page_to_array(page: fitz.Page, dpi: int = _RENDER_DPI) -> np.ndarray:
    """يرسم صفحة PDF كاملة كصورة بالدقة المطلوبة."""
    return _pix_to_array(page.get_pixmap(dpi=dpi, alpha=False))


def _embedded_images(page: fitz.Page) -> list[np.ndarray]:
    """يستخرج الصور المضمّنة في الصفحة بدقتها الأصلية.

    الصفحة الممسوحة ضوئياً غالباً صورة واحدة كبيرة. استخراجها كما هي
    أفضل من رسم الصفحة، لأن الرسم يعيد تشكيل البكسل فيفقد تفاصيل خط MRZ
    الدقيق. نرتّب الصور من الأكبر إلى الأصغر لأن صورة الجواز هي الأكبر.
    """
    doc = page.parent
    out: list[tuple[int, np.ndarray]] = []

    for info in page.get_images(full=True):
        xref = info[0]
        try:
            pix = fitz.Pixmap(doc, xref)
            arr = _pix_to_array(pix)
        except Exception:
            continue
        h, w = arr.shape[:2]
        # نتجاهل الشعارات والأيقونات الصغيرة
        if w < 600 or h < 300:
            continue
        out.append((w * h, arr))

    out.sort(key=lambda t: t[0], reverse=True)
    return [arr for _, arr in out[:3]]


def _scan_sources(page: fitz.Page):
    """يولّد صور الصفحة بترتيب تصاعدي في الكلفة.

    نبدأ بالصور المضمّنة بدقتها الأصلية (الأدق والأسرع للصفحات الممسوحة)،
    ثم نرسم الصفحة بدقة متزايدة للصفحات المركّبة من رسومات ومتجهات.
    المولّد كسول، فلا نرسم بدقة عالية إلا إذا فشل ما قبلها.
    """
    try:
        yield from _embedded_images(page)
    except Exception:
        pass
    for dpi in (_RENDER_DPI, 400):
        try:
            yield _page_to_array(page, dpi)
        except Exception:
            continue


def _dedupe(records: list[PassportData]) -> list[PassportData]:
    """يحذف السجلات المكررة.

    الجواز الواحد قد يمتد على صفحتين (صورة الصفحة + تكبير لمنطقة MRZ)،
    فنوحّد حسب رقم الجواز ونُبقي القراءة الأفضل.
    """
    best: dict[str, PassportData] = {}
    order: list[str] = []
    unnamed: list[PassportData] = []

    for rec in records:
        key = rec.passport_number.strip().upper()
        if not key:
            unnamed.append(rec)
            continue
        current = best.get(key)
        if current is None:
            best[key] = rec
            order.append(key)
        elif (rec.checksum_ok, -len(rec.warnings)) > (
            current.checksum_ok, -len(current.warnings)
        ):
            best[key] = rec

    return [best[k] for k in order] + unnamed


def _fill_arabic_name(rec: PassportData, page_text: str, image) -> None:
    """يملأ الاسم العربي من نص الصفحة إن وُجد، وإلا من قراءة ضوئية للصورة.

    نص PDF المضمّن أدق بكثير من OCR، فنجرّبه أولاً ولا نضيف تحذيراً معه.
    """
    if rec.full_name_ar:
        return

    if page_text and page_text.strip():
        name = best_arabic_name_in_text(page_text)
        if name:
            rec.full_name_ar = name
            return

    if image is not None and arabic_supported():
        try:
            name = extract_arabic_name(image, rec.full_name_en)
        except Exception:
            name = ""
        if name:
            rec.full_name_ar = name
            rec.warnings.append("الاسم العربي مقروء ضوئياً — يجب التأكد منه")


def extract_from_pdf(
    path: str | Path, *, progress=None
) -> tuple[list[PassportData], list[str]]:
    """يستخرج كل الجوازات الموجودة في ملف PDF.

    progress: دالة اختيارية تُستدعى بـ (رقم الصفحة، إجمالي الصفحات).

    يعيد: (السجلات، رسائل عن الصفحات التي تعذّرت قراءتها)
    """
    path = Path(path)
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise PDFError(f"تعذّر فتح ملف PDF:\n{exc}") from exc

    if doc.needs_pass:
        doc.close()
        raise PDFError("ملف PDF محمي بكلمة مرور — أزل الحماية ثم أعد المحاولة.")

    total = doc.page_count
    if total == 0:
        doc.close()
        raise PDFError("ملف PDF لا يحتوي أي صفحات.")

    records: list[PassportData] = []
    notes: list[str] = []
    pages = min(total, _MAX_PAGES)
    if total > _MAX_PAGES:
        notes.append(f"الملف يحتوي {total} صفحة — تمت معالجة أول {_MAX_PAGES} فقط.")

    try:
        for i in range(pages):
            if progress:
                progress(i + 1, pages)
            page = doc[i]
            label = f"{path.name} (صفحة {i + 1})"
            rec = None

            # 1) الطبقة النصية — أسرع وأدق حين تتوفر
            try:
                text = page.get_text("text")
            except Exception:
                text = ""
            if text.strip():
                try:
                    rec = parse_text(text)
                    rec.source_file = label
                except (MRZError, ValueError):
                    rec = None

            # 2) وإلا نمسح الصفحة ضوئياً بمحاولات متصاعدة الجودة.
            # نؤجّل قراءة الاسم العربي: تشغيلها في كل محاولة يضاعف الزمن
            # بلا فائدة، فنجريها مرة واحدة بعد اختيار أفضل قراءة.
            first_source = None
            if rec is None or not rec.checksum_ok:
                for source in _scan_sources(page):
                    if first_source is None:
                        first_source = source
                    try:
                        scanned = extract_from_array(source, label, read_arabic=False)
                    except MRZError:
                        continue
                    except Exception as exc:
                        notes.append(f"صفحة {i + 1}: خطأ أثناء المعالجة — {exc}")
                        continue

                    # نُبقي الأفضل بين قراءة النص وقراءات الصور
                    if rec is None or (scanned.checksum_ok, -len(scanned.warnings)) > (
                        rec.checksum_ok, -len(rec.warnings)
                    ):
                        rec = scanned
                    # قراءة نظيفة تماماً: لا داعي لمحاولات أثقل
                    if rec.checksum_ok and not rec.warnings:
                        break

            if rec is None:
                notes.append(f"صفحة {i + 1}: لم يُعثر على بيانات جواز.")
            else:
                _fill_arabic_name(rec, text, first_source)
                records.append(rec)
    finally:
        doc.close()

    records = _dedupe(records)

    if not records:
        raise MRZError(
            f"تعذّر العثور على أي جواز في الملف ({pages} صفحة).\n"
            "تأكد أن الشريط السفلي للجواز (سطرا MRZ) ظاهر وواضح في الصفحات."
        )

    return records, notes
