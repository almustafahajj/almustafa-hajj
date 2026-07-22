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


def save_image(image_id: str, kind: str, source: str | Path, session) -> None:
    """يقرأ صورة من مسار خارجي ويحفظها مشفّرة داخلياً (كتابة ذرّية).

    session: جلسة الدخول للتشفير. بدونها تُحفظ الصورة كما هي (اختبارات فقط).
    """
    data = Path(source).read_bytes()
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
