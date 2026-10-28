# -*- coding: utf-8 -*-
"""النسخ الاحتياطي للبورتال واستعادته.

* نسخة يومية تلقائية على الخادم (ملفّات البيانات بلا الصور) — آخر ١٤ يوماً.
* تنزيل نسخة كاملة (مع الصور اختيارياً) **مشفّرة بكلمة مرور** يختارها المدير
  (AES-256-GCM على أجزاء، ومفتاح مشتقّ بـ PBKDF2) — تُحفظ خارج الخادم.
* استعادة من ملف منزّل أو من نسخة يومية، بعد حفظ نسخة أمان من الحالي.

ملفّات الكشف والصور مشفّرة أصلاً بمفتاح البيانات؛ والنسخة تتضمّن ``auth.json``
فتبقى قابلة للفتح بكلمات مرور الحسابات نفسها بعد الاستعادة.
"""
from __future__ import annotations

import fnmatch
import os
import secrets
import struct
import tempfile
import zipfile
from datetime import datetime, date
from pathlib import Path

MAGIC = b"ALMBAK1\n"
KEEP_DAYS = 14
_CHUNK = 1024 * 1024
_ITER = 300_000
# ما يُنسخ (أسماء في مجلّد البيانات) — لا مفتاح توقيع الجلسات ولا الملفّات المؤقّتة
_DATA_PATTERNS = ("auth.json", "hajjaj.json", "umrah.json", "settings.json",
                  "settings_umrah.json", "documents_*.json", "camps_*.json",
                  "audit.log", "public_links.json")
_IMAGES_DIR = "images"


def data_dir() -> Path:
    from hajj_app.paths import data_dir as _dd
    return Path(_dd())


def snaps_dir() -> Path:
    p = data_dir() / "backups_web"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _allowed(name: str) -> bool:
    """اسم داخل النسخة مسموح باستعادته (يمنع أي مسار خارج مجلّد البيانات)."""
    name = name.replace("\\", "/")
    if name.startswith("/") or ".." in name.split("/") or ":" in name:
        return False
    if name.startswith(_IMAGES_DIR + "/"):
        rest = name[len(_IMAGES_DIR) + 1:]
        return bool(rest) and "/" not in rest and not rest.startswith(".")
    return any(fnmatch.fnmatch(name, p) for p in _DATA_PATTERNS) and "/" not in name


def _members(with_images: bool) -> list:
    root = data_dir()
    out = []
    for p in sorted(root.iterdir()) if root.is_dir() else []:
        if p.is_file() and _allowed(p.name):
            out.append((p, p.name))
    img = root / _IMAGES_DIR
    if with_images and img.is_dir():
        for p in sorted(img.iterdir()):
            if p.is_file():
                out.append((p, f"{_IMAGES_DIR}/{p.name}"))
    return out


def build_zip(dest: Path, with_images: bool = True) -> int:
    """يكتب نسخة zip إلى ``dest``؛ يعيد عدد الملفّات."""
    files = _members(with_images)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BACKUP-INFO.txt",
                   f"المصطفى للحج والعمرة — نسخة احتياطية\n{datetime.now():%Y-%m-%d %H:%M}\n"
                   f"ملفّات: {len(files)}\n")
        for p, arc in files:
            # الصور مشفّرة أصلاً فلا يفيد ضغطها — تُخزَّن كما هي (أسرع)
            z.write(p, arc, compress_type=(zipfile.ZIP_STORED
                                           if arc.startswith(_IMAGES_DIR + "/")
                                           else zipfile.ZIP_DEFLATED))
    return len(files)


# ------------------------------------------------------------- التشفير
def _key(password: str, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITER, 32)


def encrypt_file(src: Path, dest: Path, password: str) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt = secrets.token_bytes(16)
    aes = AESGCM(_key(password, salt))
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        fo.write(MAGIC + salt)
        n = 0
        while True:
            chunk = fi.read(_CHUNK)
            last = len(chunk) < _CHUNK
            nonce = secrets.token_bytes(12)
            # رقم الجزء + علامة الأخير ضمن البيانات المصادَق عليها (منع الحذف/الترتيب)
            ct = aes.encrypt(nonce, chunk, struct.pack(">QB", n, last))
            fo.write(struct.pack(">I", len(ct)) + nonce + ct)
            n += 1
            if last:
                break


def decrypt_file(src: Path, dest: Path, password: str) -> None:
    """يفكّ تشفير نسخة؛ يرفع ValueError عند كلمة مرور خاطئة أو ملف تالف."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        if fi.read(len(MAGIC)) != MAGIC:
            raise ValueError("الملف ليس نسخة احتياطية من البورتال.")
        aes = AESGCM(_key(password, fi.read(16)))
        n = 0
        while True:
            head = fi.read(4)
            if len(head) < 4:
                raise ValueError("النسخة ناقصة أو تالفة.")
            size = struct.unpack(">I", head)[0]
            nonce, ct = fi.read(12), fi.read(size)
            pt = None
            for last in (False, True):
                try:
                    pt = aes.decrypt(nonce, ct, struct.pack(">QB", n, last))
                    break
                except InvalidTag:
                    continue
            if pt is None:
                raise ValueError("كلمة مرور النسخة غير صحيحة، أو الملف تالف.")
            fo.write(pt)
            n += 1
            if last:
                break


# ------------------------------------------------------------- اليومية
def snapshot(tag: str = "auto", with_images: bool = False) -> Path:
    """نسخة zip على الخادم (بلا تشفير إضافي: ملفّات الكشف مشفّرة أصلاً)."""
    p = snaps_dir() / f"{datetime.now():%Y-%m-%d_%H%M%S}_{tag}.zip"
    tmp = p.with_suffix(".tmp")
    build_zip(tmp, with_images)
    os.replace(tmp, p)
    return p


def list_snapshots() -> list:
    return sorted(snaps_dir().glob("*.zip"), reverse=True)


def prune(keep: int = KEEP_DAYS) -> None:
    autos = [p for p in list_snapshots() if p.stem.endswith("_auto")]
    for p in autos[keep:]:
        p.unlink(missing_ok=True)
    others = [p for p in list_snapshots() if not p.stem.endswith("_auto")]
    for p in others[keep:]:
        p.unlink(missing_ok=True)


_LAST_CHECK = {"day": None}


def daily(today: date | None = None) -> Path | None:
    """نسخة اليوم إن لم تُؤخذ بعد (يُستدعى مع الطلبات؛ يتحقّق مرّة في اليوم)."""
    today = today or date.today()
    if _LAST_CHECK["day"] == today:
        return None
    _LAST_CHECK["day"] = today
    stamp = today.strftime("%Y-%m-%d")
    if any(p.name.startswith(stamp) and p.stem.endswith("_auto")
           for p in list_snapshots()):
        return None
    if not (data_dir() / "auth.json").exists():
        return None
    p = snapshot("auto")
    prune()
    return p


# ------------------------------------------------------------- الاستعادة
def _current_files(root: Path, with_images: bool) -> list:
    """ملفّات البيانات الحالية التي تحلّ النسخة محلّها (مع احتياطيات .bak، والصور
    فقط إن كانت النسخة تحوي صوراً — النسخ اليومية بلا صور فتبقى الحالية)."""
    out = [p for p in root.iterdir() if p.is_file()
           and (_allowed(p.name) or p.name.endswith(".json.bak"))
           and p.name != "audit.log"] if root.is_dir() else []
    img = root / _IMAGES_DIR
    if with_images and img.is_dir():
        out += [p for p in img.iterdir() if p.is_file()]
    return out


def restore_zip(zpath: Path) -> list:
    """يستعيد نسخة zip **كاملةً أو لا شيء**.

    ١) تُفكّ النسخة كلها وتُفحص في مجلّد مؤقّت داخل مجلّد البيانات؛ أي خطأ هنا
       لا يمسّ البيانات. ٢) تُنقل الملفّات الحالية جانباً (وما ليس في النسخة لا
       يبقى ليختلط بها). ٣) تُنقل الجديدة مكانها؛ وعند أي خطأ تُعاد القديمة كما
       كانت. سجلّ التدقيق لا يُستبدل أبداً (يبقى أثر كل ما حدث)."""
    import shutil
    root = data_dir()
    stage = root / ".restore-stage"
    old = root / ".restore-old"
    for d in (stage, old):
        shutil.rmtree(d, ignore_errors=True)
    stage.mkdir(parents=True)
    try:
        try:
            with zipfile.ZipFile(zpath) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
                if "auth.json" not in names:
                    raise ValueError("النسخة لا تحوي ملف الحسابات (auth.json) — ليست نسخة صالحة.")
                if any(n not in ("BACKUP-INFO.txt", "audit.log") and not _allowed(n)
                       for n in names):
                    raise ValueError("النسخة تحوي ملفّات غير متوقّعة — رُفضت للأمان.")
                wanted = [n for n in names if n not in ("BACKUP-INFO.txt", "audit.log")]
                for n in wanted:
                    dest = stage / n
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(n) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out, _CHUNK)
        except ValueError:
            raise
        except (zipfile.BadZipFile, OSError, RuntimeError, KeyError) as exc:
            raise ValueError("تعذّر قراءة النسخة كاملة (تالفة أو لا مساحة كافية) — "
                             "لم يتغيّر شيء.") from exc
        # ٢+٣: تبديل بالنقل (سريع وعلى القرص نفسه) مع إرجاع كامل عند أي خطأ
        moved, placed = [], []
        try:
            old.mkdir(parents=True)
            has_img = any(n.startswith(_IMAGES_DIR + "/") for n in wanted)
            for p in _current_files(root, has_img):
                rel = p.relative_to(root)
                dst = old / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(p, dst)
                moved.append(rel)
            for n in wanted:
                dst = root / n
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / n, dst)
                placed.append(n)
        except BaseException as exc:
            for n in placed:
                (root / n).unlink(missing_ok=True)
            for rel in moved:
                try:
                    os.replace(old / rel, root / rel)
                except OSError:
                    pass
            if isinstance(exc, Exception):
                raise ValueError("تعذّرت الاستعادة وأُعيدت البيانات كما كانت.") from exc
            raise
        return wanted
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(old, ignore_errors=True)


def tempfile_path(suffix: str) -> Path:
    fd, p = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(p)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

