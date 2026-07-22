"""استخراج الاسم العربي من المنطقة المطبوعة في الجواز.

الاسم العربي **ليس** في سطري MRZ — مواصفة ICAO 9303 تحفظ الاسم بالحروف
اللاتينية فقط. الاسم العربي مطبوع في المنطقة المرئية العلوية من الصفحة
(Visual Inspection Zone)، فنقرأه بـ OCR عربي.

هذه القراءة **أقل موثوقية بكثير** من MRZ: لا خانات تحقق، والخطوط زخرفية،
وخلفية الجواز مزركشة أمنياً. لذلك نضع النتيجة دائماً كـ "تحتاج مراجعة".
"""

from __future__ import annotations

import re
import unicodedata

import cv2
import numpy as np
import pytesseract
from PIL import Image

from .tesseract_setup import arabic_supported, available_languages, configure_tesseract
from .translit import reconcile

_ARABIC_LETTERS = re.compile(r"[ء-ي]")
_ARABIC_ONLY = re.compile(r"[^ء-يّ\s]")

# صور العرض العربية (Arabic Presentation Forms): كثير من ملفات PDF يخزّن
# الحروف بأشكالها المتصلة بدل الحروف الأساسية، وأحياناً بترتيب بصري معكوس.
_PRESENTATION = re.compile(r"[ﭐ-﷿ﹰ-﻿]")
_FORMS = ("FINAL FORM", "INITIAL FORM", "MEDIAL FORM", "ISOLATED FORM")


def _letter_form(ch: str) -> str:
    """يعيد شكل الحرف العربي (ابتدائي/وسطي/نهائي/منفرد) أو نصاً فارغاً."""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    for form in _FORMS:
        if name.endswith(form):
            return form
    return ""


def _looks_reversed(text: str) -> bool:
    """يكشف إن كان النص مخزّناً بترتيب بصري معكوس.

    في الترتيب المنطقي الصحيح ينتهي الحرف الأخير من الكلمة بالشكل النهائي.
    فإذا وجدنا الشكل النهائي في *بداية* الكلمات فالنص معكوس.
    """
    reversed_hits = forward_hits = 0
    for word in text.split():
        letters = [c for c in word if _letter_form(c)]
        if len(letters) < 2:
            continue
        if _letter_form(letters[0]) == "FINAL FORM":
            reversed_hits += 1
        if _letter_form(letters[-1]) == "FINAL FORM":
            forward_hits += 1
    return reversed_hits > forward_hits


def normalize_arabic(text: str) -> str:
    """يحوّل صور العرض إلى حروف أساسية ويصحّح الترتيب البصري المعكوس.

    نعكس النص *قبل* التوحيد، لأن التوحيد يفكّ ligature لام-ألف إلى حرفين،
    وعكسها بعد التفكيك يقلب ترتيبهما.
    """
    if not _PRESENTATION.search(text):
        return text
    if _looks_reversed(text):
        text = "\n".join(line[::-1] for line in text.splitlines())
    return unicodedata.normalize("NFKC", text)

# عبارات مطبوعة ثابتة في الجوازات — ليست أسماء، فنستبعدها.
_LABELS = (
    "المملكة", "العربية", "السعودية", "جمهورية", "مصر", "دولة", "سلطنة",
    "جواز", "سفر", "باسبور", "الجنسية", "الجنس", "تاريخ", "الميلاد",
    "الاصدار", "الإصدار", "الانتهاء", "الانتهاء", "مكان", "الرقم", "رقم",
    "الاسم", "اللقب", "القب", "النوع", "السلطة", "المصدرة", "صالح",
    "توقيع", "حامل", "الوثيقة", "وزارة", "الداخلية", "الجوازات",
    "المهنة", "العنوان", "ملاحظات", "النسائي", "ذكر", "انثى", "أنثى",
    "محل", "الولادة", "الاقامة", "الإقامة", "نوع", "الوثيقه",
)

# تشكيل وعلامات لا تُفيد في الاسم
_DIACRITICS = re.compile(r"[ً-ْـ]")


def _preprocess(img: np.ndarray) -> list[np.ndarray]:
    """معالجات متعددة للمنطقة العربية — الخلفيات الأمنية تربك العتبة الواحدة."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

    # تكبير: الحروف العربية المتصلة تحتاج دقة أعلى من اللاتينية
    h, w = gray.shape[:2]
    if w < 1800:
        scale = 1800 / w
        gray = cv2.resize(gray, (1800, int(h * scale)), interpolation=cv2.INTER_CUBIC)

    denoised = cv2.bilateralFilter(gray, 7, 60, 60)
    out = [denoised]

    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out.append(otsu)

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(denoised)
    out.append(clahe)

    # عتبة تكيّفية بنافذة كبيرة: تتجاهل الزخرفة الأمنية الخفيفة
    out.append(cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 20
    ))
    return out


def _clean_line(line: str) -> str:
    """يبقي الحروف العربية والفراغات فقط."""
    line = _DIACRITICS.sub("", line)
    line = _ARABIC_ONLY.sub(" ", line)
    return re.sub(r"\s+", " ", line).strip()


def _is_label(word: str) -> bool:
    return any(lbl in word or word in lbl for lbl in _LABELS)


# حدود طول الكلمة في الأسماء العربية. أطول ما يرد عملياً مثل "عبدالرحمن"
# تسع حروف؛ ما تجاوز ذلك غالباً نص لاتيني قرأه OCR حروفاً عربية.
_MIN_WORD, _MAX_WORD = 2, 11


def _best_window(line: str) -> tuple[str, float]:
    """يختار أفضل مقطع متتالٍ من السطر يشبه اسم شخص.

    لا نشترط أن يكون السطر كله اسماً: في الجوازات يقع الاسم اللاتيني على
    يسار الاسم العربي في نفس السطر البصري، فيلتقطهما OCR معاً ويحوّل
    اللاتيني إلى حروف عربية مشوّهة. لذلك نقصّ الكلمات غير الصالحة ونبحث
    عن أفضل نافذة متتالية بينها.
    """
    segments: list[list[str]] = []
    current: list[str] = []
    for word in line.split():
        if _MIN_WORD <= len(word) <= _MAX_WORD and not _is_label(word):
            current.append(word)
        else:
            if current:
                segments.append(current)
            current = []
    if current:
        segments.append(current)

    best, best_score = "", 0.0
    for seg in segments:
        for size in range(2, 6):
            for i in range(len(seg) - size + 1):
                window = seg[i:i + size]
                letters = sum(len(w) for w in window)
                if not (6 <= letters <= 40):
                    continue
                if not (2.5 <= letters / size <= 9):
                    continue
                score = size + min(letters, 25) * 0.1
                if score > best_score:
                    best, best_score = " ".join(window), score
    return best, best_score


def _score(line: str) -> float:
    """درجة شبه السطر باسم شخص (0 = ليس اسماً)."""
    return _best_window(line)[1]


def best_arabic_name_in_text(text: str) -> str:
    """يختار أفضل سطر يشبه اسم شخص من نص عربي.

    يُستخدم مع نص PDF المضمّن (أدق بكثير من OCR) ومع مخرجات OCR معاً.
    """
    best, best_score = "", 0.0
    for raw in normalize_arabic(text).splitlines():
        line = _clean_line(raw)
        if not line or not _ARABIC_LETTERS.search(line):
            continue
        candidate, score = _best_window(line)
        if score > best_score:
            best, best_score = candidate, score
    return best


def extract_arabic_name(img: np.ndarray, latin_name: str = "") -> str:
    """يحاول قراءة الاسم العربي من صورة صفحة الجواز.

    latin_name: الاسم اللاتيني من MRZ إن توفّر. وجوده يرفع الدقة كثيراً،
    لأنه محمي بخانة تحقق فيصلح مرجعاً صوتياً يحسم بين قراءات OCR
    المتشابهة (انظر `translit.reconcile`).

    يعيد نصاً فارغاً إن لم يجد مرشحاً مقنعاً — الفراغ أوضح من اسم مخترع.
    """
    if not configure_tesseract() or not arabic_supported():
        return ""

    h, w = img.shape[:2]
    top = img[: int(h * 0.62), :]
    mid = img[int(h * 0.12): int(h * 0.55), :]
    # النص العربي في هذه الوثائق محاذى لليمين، والنص اللاتيني لليسار.
    # قصّ الجهة اليمنى يمنع اختلاط الاثنين في سطر واحد عند القراءة.
    regions = [
        top[:, int(w * 0.40):],
        mid[:, int(w * 0.40):],
        top,
        mid,
    ]

    candidates: list[str] = []
    for region in regions:
        for variant in _preprocess(region):
            try:
                text = pytesseract.image_to_string(
                    Image.fromarray(variant), lang="ara", config="--psm 6 --oem 1"
                )
            except Exception:
                continue
            candidate = best_arabic_name_in_text(text)
            if candidate:
                candidates.append(candidate)

    # المطابقة بالاسم اللاتيني أقوى من التصويت: التصويت يشترط تطابق الكلمة
    # حرفياً في أغلب القراءات، فيسقط الاسم كله حين يخطئ OCR في نفس الحرف
    # كل مرة (وهو الشائع: الباء تُقرأ ياءً). نعود للتصويت إن لم تكفِ الثقة.
    if latin_name:
        reconciled, _score_ = reconcile(candidates, latin_name)
        if reconciled:
            return reconciled

    return _consensus(candidates)


def _consensus(candidates: list[str]) -> str:
    """يستخلص الاسم المتفق عليه بين عدة قراءات.

    النص الحقيقي يخرج ثابتاً من كل المعالجات، أما ضجيج OCR (كالنص اللاتيني
    الذي يُقرأ حروفاً عربية) فيختلف من محاولة لأخرى. لذلك نُبقي الكلمات
    التي تكررت في عدد معتبر من القراءات ونحذف ما عداها.
    """
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]

    frequency: dict[str, int] = {}
    for candidate in candidates:
        for word in set(candidate.split()):
            frequency[word] = frequency.get(word, 0) + 1

    threshold = max(2, round(len(candidates) * 0.4))

    # نستخلص المقطع المستقر من *كل* قراءة، لا من أعلاها درجة وحدها:
    # الضجيج قد يسجّل درجة أعلى من الاسم صدفةً، فالاعتماد عليه وحده
    # يُضيع الاسم تماماً. أما التكرار عبر القراءات فلا يزوّره الضجيج.
    runs: dict[str, int] = {}
    for candidate in candidates:
        run = _longest_stable_run(candidate.split(), frequency, threshold)
        if len(run) >= 2:
            text = " ".join(run)
            runs[text] = runs.get(text, 0) + 1

    if not runs:
        return ""
    # الأكثر تكراراً أولاً، ثم الأطول، ثم الأعلى درجة
    return max(runs, key=lambda t: (runs[t], len(t.split()), _score(t)))


def _longest_stable_run(
    words: list[str], frequency: dict[str, int], threshold: int
) -> list[str]:
    """أطول تتابع من الكلمات التي تكررت في عدد كافٍ من القراءات."""
    best: list[str] = []
    current: list[str] = []
    for word in words:
        if frequency.get(word, 0) >= threshold:
            current.append(word)
        else:
            if len(current) > len(best):
                best = current
            current = []
    return current if len(current) > len(best) else best


