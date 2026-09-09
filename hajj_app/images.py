"""تخزين صور الجوازات والصور الشخصية للحجاج — مشفّرة داخل مجلد البيانات.

صور الجوازات بيانات شخصية بالغة الحساسية، والبرنامج يَعِد بأن البيانات
مشفّرة. لذلك تُخزَّن كل صورة **مشفّرة بمفتاح الجلسة** نفسه (كملف البيانات)،
فلا تُقرأ إلا داخل البرنامج بعد تسجيل الدخول.

كل حاج له `image_id` ثابت، وتُحفظ صوره باسم `<image_id>.passport` و
`<image_id>.photo` داخل `data\\images`.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from . import storage

PASSPORT = "passport"
PHOTO = "photo"
ID_CARD = "id"
PERMIT = "permit"
KINDS = (PASSPORT, PHOTO, ID_CARD, PERMIT)

# العناوين المعروضة لكل نوع صورة
KIND_LABELS = {
    PASSPORT: "صورة الجواز",
    PHOTO: "الصورة الشخصية",
    ID_CARD: "صورة الهوية",
    PERMIT: "التصريح السعودي",
}


def images_dir() -> Path:
    """مجلد الصور بجوار ملف البيانات."""
    return storage.default_data_path().parent / "images"


def new_image_id() -> str:
    """معرّف صورة جديد فريد."""
    return uuid.uuid4().hex


def _image_path(image_id: str, kind: str) -> Path:
    return images_dir() / f"{image_id}.{kind}"


def has_image(image_id: str, kind: str) -> bool:
    """هل توجد صورة من هذا النوع لهذا الحاج؟"""
    return bool(image_id) and _image_path(image_id, kind).is_file()


# حدّ ضغط الصور المخزَّنة — توفير مساحة دون التأثير على القراءة (OCR يقرأ الأصل).
STORAGE_MAX_SIDE = 1800          # أطول ضلع بالبكسل (كافٍ لعرض/طباعة الجواز بوضوح)
STORAGE_JPEG_QUALITY = 85


def compress_for_storage(data: bytes, *, max_side: int = STORAGE_MAX_SIDE,
                         quality: int = STORAGE_JPEG_QUALITY) -> bytes:
    """يصغّر صورة نقطية ويعيد ترميزها JPEG لتوفير المساحة قبل التخزين.

    - ملفّات PDF تُترك كما هي (الجواز الممسوح PDF)، والصور الصغيرة أصلاً كذلك.
    - يُستخدم الناتج فقط إن كان أصغر فعلاً؛ وأي خطأ يُعيد الأصل بلا مساس.
    - لا يؤثّر على دقّة قراءة الجواز (OCR يقرأ الملف الأصلي قبل الحفظ).
    """
    if not data or is_pdf(data):
        return data
    try:
        from io import BytesIO
        from PIL import Image as _PILImage
        im = _PILImage.open(BytesIO(data))
        im.load()
        # تدوير حسب بيانات EXIF إن وُجدت ثم إسقاطها
        try:
            from PIL import ImageOps
            im = ImageOps.exif_transpose(im)
        except Exception:                          # noqa: BLE001
            pass
        w, h = im.size
        scale = min(1.0, float(max_side) / float(max(w, h) or 1))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                           _PILImage.LANCZOS)
        if im.mode in ("RGBA", "P", "LA", "CMYK"):
            im = im.convert("RGB")
        out = BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        result = out.getvalue()
        return result if 0 < len(result) < len(data) else data
    except Exception:                              # noqa: BLE001
        return data


def save_image(image_id: str, kind: str, source: str | Path, session) -> None:
    """يقرأ صورة من مسار خارجي ويحفظها مشفّرة داخلياً (كتابة ذرّية).

    تُصغَّر الصور النقطية وتُعاد ترميزها لتوفير المساحة (PDF يبقى كما هو).
    session: جلسة الدخول للتشفير. بدونها تُحفظ الصورة كما هي (اختبارات فقط).
    """
    data = compress_for_storage(Path(source).read_bytes())
    blob = session.encrypt(data) if session is not None else data
    directory = images_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = _image_path(image_id, kind)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def load_image(image_id: str, kind: str, session) -> bytes | None:
    """يعيد بايتات الصورة بعد فكّ التشفير، أو None إن لم توجد أو تعذّر الفك."""
    path = _image_path(image_id, kind)
    if not path.is_file():
        return None
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    if session is None:
        return blob
    try:
        return session.decrypt(blob)
    except Exception:
        return None


def delete_image(image_id: str, kind: str) -> None:
    """يحذف صورة إن وُجدت (بلا خطأ إن لم توجد)."""
    if not image_id:
        return
    try:
        _image_path(image_id, kind).unlink(missing_ok=True)
    except OSError:
        pass


def delete_all(image_id: str) -> None:
    """يحذف كل صور حاج — يُستدعى عند حذف سجله."""
    for kind in KINDS:
        delete_image(image_id, kind)


# --------------------------------------------------------- دعم ملفات PDF
def is_pdf(blob: bytes) -> bool:
    """هل المحتوى ملف PDF؟ (نقبل رفع الجوازات والتصاريح الممسوحة كـ PDF)."""
    return blob[:5] == b"%PDF-"


def to_pil_image(blob: bytes):
    """يحوّل بايتات صورة أو أول صفحة PDF إلى صورة PIL للمعاينة. None إن تعذّر."""
    from io import BytesIO

    from PIL import Image as PILImage

    try:
        if is_pdf(blob):
            import fitz
            doc = fitz.open(stream=blob, filetype="pdf")
            if doc.page_count == 0:
                doc.close()
                return None
            png = doc[0].get_pixmap(dpi=150).tobytes("png")
            doc.close()
            return PILImage.open(BytesIO(png))
        return PILImage.open(BytesIO(blob))
    except Exception:
        return None


def render_pages_png(blob: bytes) -> list[bytes]:
    """يعيد صفحات المحتوى كصور PNG: صفحة لكل ورقة PDF، أو الصورة كما هي.

    يُستعمل للطباعة، فيظهر كل صفحة جواز/تصريح مرفوعة كـ PDF في صفحة مستقلة.
    """
    if not is_pdf(blob):
        return [blob]       # صورة عادية — ImageReader يقرؤها مباشرة
    try:
        import fitz
        doc = fitz.open(stream=blob, filetype="pdf")
        pages = [doc[i].get_pixmap(dpi=200).tobytes("png") for i in range(doc.page_count)]
        doc.close()
        return pages
    except Exception:
        return []


# ------------------------------------------ اقتصاص الوجه (الصورة الشخصية) من الجواز
_FACE_CASCADES = None
# نُفضّل alt/alt2 (أدقّ على صور الهوية) ثم default احتياطاً
_CASCADE_FILES = ("haarcascade_frontalface_alt.xml",
                  "haarcascade_frontalface_alt2.xml",
                  "haarcascade_frontalface_default.xml")


def _face_cascades():
    """قائمة كواشف الوجوه Haar (المحزومة أوّلاً ثم بيانات OpenCV). تُحمَّل مرّة."""
    global _FACE_CASCADES
    if _FACE_CASCADES is not None:
        return _FACE_CASCADES
    _FACE_CASCADES = []
    try:
        import cv2
    except Exception:                                  # noqa: BLE001
        return _FACE_CASCADES
    dirs = []
    try:
        from .paths import resource_dir
        dirs.append(str(resource_dir() / "assets"))
    except Exception:                                  # noqa: BLE001
        pass
    try:
        dirs.append(cv2.data.haarcascades)
    except Exception:                                  # noqa: BLE001
        pass
    for name in _CASCADE_FILES:
        for d in dirs:
            path = os.path.join(d, name)
            if os.path.isfile(path):
                clf = cv2.CascadeClassifier(path)
                if not clf.empty():
                    _FACE_CASCADES.append(clf)
                    break
    return _FACE_CASCADES


def _detect_face(img):
    """يعيد أكبر وجه (x, y, w, h) مكتشَف في صورة BGR، أو None.

    يتدرّج: رمادي عادي ← معادلة تباين ← تكبير ٢×، عبر كواشف alt/alt2/default؛
    ويختار أكبر وجه (صورة الهوية عادةً أكبر من الإيجابيات الكاذبة الصغيرة).
    """
    import cv2
    cascades = _face_cascades()
    if not cascades:
        return None
    H, W = img.shape[:2]
    base = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ms = max(32, min(W, H) // 16)
    variants = [(base, 1.0),
                (cv2.equalizeHist(base), 1.0),
                (cv2.resize(base, (W * 2, H * 2)), 2.0)]
    for gray, scale in variants:
        for clf in cascades:
            found = clf.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4,
                minSize=(int(ms * scale), int(ms * scale)))
            if len(found):
                x, y, w, h = max(found, key=lambda f: int(f[2]) * int(f[3]))
                return (x / scale, y / scale, w / scale, h / scale)
    return None


def face_crop(blob: bytes, *, target_aspect: float = 0.9,
              out_quality: int = 92) -> bytes | None:
    """يستخرج الوجه (الصورة الشخصية) من صورة جواز/هوية ويعيده JPEG.

    الاقتصاص **محكم حول الوجه** (رأس وأكتاف بلا كتابات ولا هوامش الوثيقة)،
    وبنسبة ``target_aspect`` (عرض/ارتفاع) نفسها إطار البطاقة ليملأه تماماً.
    يعيد None إن تعذّر (لا OpenCV، أو لم يُكتشف وجه) — فلا تُعرض الوثيقة كاملةً.
    """
    if not blob:
        return None
    try:
        import cv2
        import numpy as np
    except Exception:                                  # noqa: BLE001
        return None
    img = None
    try:
        if is_pdf(blob):                               # الجواز الممسوح PDF
            pil = to_pil_image(blob)
            if pil is None:
                return None
            img = cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
    except Exception:                                  # noqa: BLE001
        img = None
    if img is None or getattr(img, "size", 0) == 0:
        return None
    face = _detect_face(img)
    if face is None:
        return None
    x, y, w, h = face
    H, W = img.shape[:2]
    A = float(target_aspect) if target_aspect and target_aspect > 0 else 0.9
    ch = h * 1.85                                      # ارتفاع الإطار: رأس + أكتاف
    cw = ch * A                                        # العرض من نسبة الإطار
    cx = x + w / 2.0
    cy = y + h / 2.0 + h * 0.30                        # نزول لتضمين الأكتاف
    s = min(1.0, W / cw, H / ch)                       # حصر ضمن الصورة بلا تشويه النسبة
    cw *= s
    ch *= s
    x0 = min(max(0.0, cx - cw / 2), W - cw)
    y0 = min(max(0.0, cy - ch / 2), H - ch)
    x0i, y0i, x1i, y1i = (int(round(x0)), int(round(y0)),
                          int(round(x0 + cw)), int(round(y0 + ch)))
    if x1i - x0i < 10 or y1i - y0i < 10:
        return None
    try:
        ok, buf = cv2.imencode(".jpg", img[y0i:y1i, x0i:x1i],
                               [cv2.IMWRITE_JPEG_QUALITY, int(out_quality)])
        return buf.tobytes() if ok else None
    except Exception:                                  # noqa: BLE001
        return None
