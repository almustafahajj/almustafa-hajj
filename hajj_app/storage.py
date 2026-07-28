"""حفظ كشف الحجاج على القرص واستعادته عند إعادة التشغيل.

الحفظ تلقائي بعد كل تعديل، ويجري بأسلوب "الكتابة الذرّية": نكتب في ملف
مؤقت ثم نستبدل به الأصل. هكذا لا يفسد الملف إن انقطعت الكهرباء أو أُغلق
البرنامج أثناء الكتابة — إمّا النسخة القديمة كاملة أو الجديدة كاملة.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path

from .auth import AuthError, Session
from .mrz import PassportData

SCHEMA_VERSION = 1

# بادئة تسبق المحتوى المشفّر. وجودها يميّز الملف المشفّر عن ملف قديم بنص
# صريح، فيُفتح الاثنان دون أن يضيع كشف أُنشئ قبل تفعيل التشفير.
_ENCRYPTED_MAGIC = b"HAJJ-ENC1\n"

# أسماء الحقول المسموح تحميلها — يحمي من مفاتيح غريبة في ملف معدّل يدوياً
_FIELD_NAMES = {f.name for f in dataclass_fields(PassportData)}


def settings_path() -> Path:
    """مسار ملف الإعدادات (غير مشفّر — لا يحوي بيانات حسّاسة)."""
    return default_data_path().parent / "settings.json"


def load_settings() -> dict:
    """يحمّل إعدادات البرنامج (كالسنة الهجرية). يعيد قاموساً فارغاً إن تعذّر."""
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    """يحفظ الإعدادات كتابةً ذرّية."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def default_data_path() -> Path:
    """مسار ملف البيانات الافتراضي: مجلد data الدائم بجوار البرنامج."""
    from .paths import data_dir
    return data_dir() / "hajjaj.json"


def _to_dict(record: PassportData) -> dict:
    """يحوّل السجل إلى قاموس مع الاحتفاظ بالتحذيرات كقائمة."""
    return {name: getattr(record, name) for name in _FIELD_NAMES}


def _from_dict(raw: dict) -> PassportData:
    """يبني سجلاً من قاموس، متجاهلاً المفاتيح غير المعروفة.

    التسامح مع الحقول الناقصة أو الزائدة يجعل الملفات القديمة تُفتح بعد
    تغيّر الأعمدة، بدل أن يفشل التحميل ويضيع الكشف كله.
    """
    record = PassportData()
    for key, value in raw.items():
        if key not in _FIELD_NAMES:
            continue
        if key == "warnings":
            record.warnings = [str(w) for w in value] if isinstance(value, list) else []
        elif key == "checksum_ok":
            record.checksum_ok = bool(value)
        elif key == "payments":
            record.payments = _clean_payments(value)
        else:
            setattr(record, key, "" if value is None else str(value))
    return record


_PAYMENT_KEYS = ("date", "amount", "method", "note")


def _clean_payments(value) -> list:
    """يعقّم قائمة الدفعات: عناصر قواميس بقيم نصّية فقط."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, dict):
            out.append({k: str(item.get(k, "") or "") for k in _PAYMENT_KEYS})
    return out


def save_records(
    records: list[PassportData],
    path: str | Path | None = None,
    session: Session | None = None,
) -> Path:
    """يحفظ السجلات. يعيد مسار الملف المحفوظ.

    session: جلسة الدخول. بوجودها يُشفَّر الملف، وبدونها يُكتب نصاً صريحاً
    (يُستعمل في الاختبارات وفي الكشوف التي أُنشئت قبل تفعيل التشفير).
    """
    path = Path(path) if path else default_data_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    blob = _encode_records(records, session)

    # نسخة احتياطية من آخر حالة سليمة قبل الاستبدال
    if path.is_file():
        try:
            shutil.copy2(path, path.with_suffix(".bak"))
        except OSError:
            pass

    temp = path.with_suffix(".tmp")
    with open(temp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)      # عملية ذرّية على ويندوز ولينكس
    return path


def _encode_records(records: list[PassportData], session: Session | None) -> bytes:
    """يبني محتوى ملف الكشف (مشفّراً إن وُجدت جلسة)."""
    payload = {
        "schema": SCHEMA_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(records),
        "records": [_to_dict(r) for r in records],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    return _ENCRYPTED_MAGIC + session.encrypt(text) if session else text


# ----------------------------------------------- نسخ احتياطية مؤرّخة (لقطات)
def backups_dir() -> Path:
    """مجلد النسخ الاحتياطية المؤرّخة، بجوار ملف البيانات."""
    return default_data_path().parent / "backups"


def list_snapshots() -> list[Path]:
    """لقطات النسخ الاحتياطية، الأحدث أولاً (الاسم يتضمّن الطابع الزمني)."""
    folder = backups_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob("hajjaj-*.json"), key=lambda p: p.name, reverse=True)


def prune_snapshots(keep: int = 20) -> None:
    """يُبقي أحدث `keep` لقطة ويحذف ما قبلها."""
    for old in list_snapshots()[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def write_snapshot(
    records: list[PassportData], session: Session | None = None,
    *, stamp: str | None = None, keep: int = 20,
) -> Path:
    """يكتب لقطة نسخة احتياطية مؤرّخة (مشفّرة كالأصل)، ويقلّم القديمة."""
    folder = backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = stamp or f"{datetime.now():%Y%m%d-%H%M%S}"
    path = folder / f"hajjaj-{stamp}.json"
    blob = _encode_records(records, session)
    temp = path.with_suffix(".tmp")
    with open(temp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)
    prune_snapshots(keep)
    return path


def snapshot_label(path: Path) -> str:
    """طابع زمني مقروء من اسم اللقطة: 'hajjaj-20260722-113605' -> '2026-07-22 11:36'."""
    name = Path(path).stem
    try:
        stamp = name.split("hajjaj-", 1)[1]
        dt = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except (IndexError, ValueError):
        return name


def is_encrypted(path: str | Path | None = None) -> bool:
    """هل ملف البيانات مشفّر؟ يُستعمل لعرض حالة الحماية للمستخدم."""
    path = Path(path) if path else default_data_path()
    try:
        with open(path, "rb") as fh:
            return fh.read(len(_ENCRYPTED_MAGIC)) == _ENCRYPTED_MAGIC
    except OSError:
        return False


def _read_file(path: Path, session: Session | None) -> list[PassportData]:
    with open(path, "rb") as fh:
        blob = fh.read()

    if blob.startswith(_ENCRYPTED_MAGIC):
        if session is None:
            raise AuthError("الملف مشفّر — يلزم تسجيل الدخول لفتحه.")
        blob = session.decrypt(blob[len(_ENCRYPTED_MAGIC):])

    payload = json.loads(blob.decode("utf-8"))
    raw_records = payload.get("records", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_records, list):
        raise ValueError("بنية الملف غير متوقعة")
    return [_from_dict(r) for r in raw_records if isinstance(r, dict)]


def load_records(
    path: str | Path | None = None, session: Session | None = None
) -> tuple[list[PassportData], str]:
    """يحمّل السجلات المحفوظة.

    يعيد: (السجلات، ملاحظة للمستخدم — فارغة إن سار كل شيء)

    عند تلف الملف نجرّب النسخة الاحتياطية، ولا نحذف الملف التالف أبداً
    بل نحفظه جانباً ليمكن إنقاذه يدوياً.
    """
    path = Path(path) if path else default_data_path()
    if not path.is_file():
        return [], ""

    try:
        return _read_file(path, session), ""
    except AuthError:
        # كلمة مرور خاطئة ليست تلفاً: الملف سليم ولا يجوز إزاحته جانباً
        # ولا بدء كشف فارغ — نُبلّغ المُنادي ليعيد طلب كلمة المرور.
        raise
    except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError) as exc:
        problem = str(exc)

    # الملف تالف — نحاول النسخة الاحتياطية
    backup = path.with_suffix(".bak")
    salvaged = path.with_name(
        f"{path.stem}-تالف-{datetime.now():%Y%m%d-%H%M%S}{path.suffix}"
    )
    try:
        os.replace(path, salvaged)
    except OSError:
        salvaged = path

    if backup.is_file():
        try:
            records = _read_file(backup, session)
            shutil.copy2(backup, path)
            return records, (
                f"ملف البيانات كان تالفاً ({problem}).\n"
                f"تمت الاستعادة من النسخة الاحتياطية: {len(records)} سجل.\n"
                f"الملف التالف محفوظ في: {salvaged.name}"
            )
        except Exception:
            pass

    return [], (
        f"تعذّرت قراءة ملف البيانات ({problem}).\n"
        f"تم حفظ الملف التالف باسم: {salvaged.name}\n"
        "بدأ البرنامج بكشف فارغ."
    )
