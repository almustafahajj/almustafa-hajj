"""استخراج نص MRZ من صورة الجواز باستخدام Tesseract محلياً.

منطقة MRZ تقع في الشريط السفلي من صفحة الجواز، وتُطبع بخط OCR-B
بأحرف كبيرة وأرقام والرمز '<' فقط. نحن نستغل هذه القيود:
نقصّ الشريط السفلي، ننظّف الصورة، ونقيّد Tesseract بمجموعة الأحرف تلك.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

from .arabic_ocr import extract_arabic_name
from .mrz import MRZError, PassportData, parse_text
from .tesseract_setup import arabic_supported, configure_tesseract

# مجموعة أحرف MRZ الوحيدة الممكنة — تقييدها يرفع الدقة بشكل كبير
_MRZ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
_CONFIG = f"--psm 6 --oem 3 -c tessedit_char_whitelist={_MRZ_CHARS}"

def _load_image(path: str | Path) -> np.ndarray:
    """يقرأ الصورة بدعم المسارات التي تحتوي حروفاً عربية."""
    raw = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if img is None:
        raise MRZError(f"تعذّر فتح الصورة: {path}")
    return img


def _upscale(img: np.ndarray, target_width: int = 1600) -> np.ndarray:
    """يكبّر الصورة إن كانت صغيرة — Tesseract يحتاج ارتفاع حرف ~30 بكسل."""
    h, w = img.shape[:2]
    if w >= target_width:
        return img
    scale = target_width / w
    return cv2.resize(img, (target_width, int(h * scale)), interpolation=cv2.INTER_CUBIC)


def _variants(img: np.ndarray) -> list[np.ndarray]:
    """يولّد عدة معالجات للصورة — نجرّبها بالترتيب حتى ينجح التحليل.

    الصور الملتقطة بالجوال تختلف كثيراً في الإضاءة، فبدل ضبط عتبة واحدة
    نجرّب عدة أساليب: تكيّفية، Otsu، والرمادي الخام.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = _upscale(gray)
    # إزالة الضجيج مع الحفاظ على حواف الحروف
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)

    out = [denoised]

    # عتبة Otsu — تعمل جيداً مع الإضاءة المتجانسة
    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out.append(otsu)

    # عتبة تكيّفية — تعمل جيداً مع الظلال والإضاءة غير المتساوية
    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    out.append(adaptive)

    # زيادة التباين ثم Otsu — تنقذ الصور الباهتة
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(denoised)
    _, clahe_otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out.append(clahe_otsu)

    return out


def _crop_regions(img: np.ndarray) -> list[np.ndarray]:
    """يعيد الصورة كاملة ثم قصاصات من الشريط السفلي حيث تقع MRZ."""
    h = img.shape[0]
    return [
        img,                        # كامل الصورة
        img[int(h * 0.68):, :],     # الثلث السفلي تقريباً
        img[int(h * 0.78):, :],     # الخُمس السفلي
        img[int(h * 0.55):, :],     # النصف السفلي (جوازات ذات تخطيط مختلف)
    ]


def image_to_text(path: str | Path) -> str:
    """يشغّل OCR على الصورة ويعيد النص الخام (للتشخيص)."""
    img = _load_image(path)
    chunks = []
    for region in _crop_regions(img):
        for variant in _variants(region):
            chunks.append(pytesseract.image_to_string(Image.fromarray(variant), config=_CONFIG))
    return "\n".join(chunks)


def ensure_tesseract() -> None:
    """يتأكد من توفّر Tesseract أو يرفع خطأً واضحاً."""
    cmd = pytesseract.pytesseract.tesseract_cmd
    if cmd and Path(cmd).is_file():
        return
    if not configure_tesseract():
        raise MRZError(
            "برنامج Tesseract غير مثبّت أو غير موجود.\n"
            "ثبّته من: https://github.com/UB-Mannheim/tesseract/wiki"
        )


def extract_from_array(
    img: np.ndarray, source_name: str = "", *, read_arabic: bool = True
) -> PassportData:
    """يستخرج بيانات الجواز من صورة محمّلة في الذاكرة.

    يجرّب كل تركيبة (منطقة × معالجة) ويعيد أول نتيجة نظيفة تماماً،
    وإلا أفضل نتيجة جزئية — أفضل من لا شيء، مع تحذيرات واضحة.

    read_arabic: يحاول أيضاً قراءة الاسم العربي من المنطقة المطبوعة.
    """
    ensure_tesseract()
    best: PassportData | None = None

    for region in _crop_regions(img):
        for variant in _variants(region):
            try:
                text = pytesseract.image_to_string(Image.fromarray(variant), config=_CONFIG)
                data = parse_text(text)
            except (MRZError, ValueError):
                continue

            data.source_file = source_name
            # قراءة مثالية: كل خانات التحقق سليمة والاسم نظيف
            if data.checksum_ok and not data.warnings:
                best = data
                break
            # وإلا نحتفظ بالأفضل: الأولوية لصحة خانات التحقق، ثم لأقل التحذيرات
            if best is None or (data.checksum_ok, -len(data.warnings)) > (
                best.checksum_ok, -len(best.warnings)
            ):
                best = data
        if best is not None and best.checksum_ok and not best.warnings:
            break

    if best is None:
        raise MRZError(
            "تعذّر قراءة سطري MRZ من الصورة.\n"
            "تأكد أن الصورة واضحة، وأن الشريط السفلي للجواز ظاهر بالكامل وغير مائل."
        )

    if not best.checksum_ok:
        best.warnings.insert(0, "قراءة غير مؤكدة — يُرجى مراجعة البيانات يدوياً")

    # الاسم العربي مطبوع في المنطقة المرئية، لا في MRZ — قراءة منفصلة
    if read_arabic and arabic_supported():
        try:
            # نمرّر الاسم اللاتيني: هو مرجع صوتي محمي بخانة تحقق
            arabic = extract_arabic_name(img, best.full_name_en)
        except Exception:
            arabic = ""
        if arabic:
            best.full_name_ar = arabic
            best.warnings.append("الاسم العربي مقروء ضوئياً — يجب التأكد منه")

    return best


def extract_passport(path: str | Path) -> PassportData:
    """يستخرج بيانات الجواز من ملف صورة."""
    ensure_tesseract()
    return extract_from_array(_load_image(path), Path(path).name)
