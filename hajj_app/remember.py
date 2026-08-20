"""حفظ بيانات الدخول (اسم المستخدم وكلمة المرور) محلياً بشكل آمن — لتعبئتها
تلقائياً عند فتح البرنامج. يُشفَّر بـ Windows DPAPI (مربوط بحساب ويندوز الحالي،
فلا يُفكّ على جهاز/مستخدم آخر). على غير ويندوز يُخزَّن مموّهاً (Base64) كحلٍّ
احتياطي فقط."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

_WIN = sys.platform.startswith("win")
_SEP = "\x00"


def _store_dir(auth_path=None) -> Path:
    if auth_path:
        return Path(auth_path).parent
    from .auth import default_auth_path
    return default_auth_path().parent


def _file(auth_path=None) -> Path:
    return _store_dir(auth_path) / "remember.dat"


# ---- Windows DPAPI عبر ctypes (بلا اعتماديات إضافية) ----
def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(bytes(data), len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    fn = (ctypes.windll.crypt32.CryptProtectData if protect
          else ctypes.windll.crypt32.CryptUnprotectData)
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI operation failed")
    n = int(out.cbData)
    res = ctypes.cast(out.pbData, ctypes.POINTER(ctypes.c_char * n)).contents.raw
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return res


def save(username: str, password: str, auth_path=None) -> None:
    """يحفظ بيانات الدخول مشفّرةً."""
    blob = f"{username}{_SEP}{password}".encode("utf-8")
    try:
        enc = _dpapi(blob, True) if _WIN else b"B64:" + base64.b64encode(blob)
    except Exception:
        enc = b"B64:" + base64.b64encode(blob)
    try:
        p = _file(auth_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(enc)
    except OSError:
        pass


def load(auth_path=None):
    """يعيد (اسم المستخدم، كلمة المرور) المحفوظين، أو ``None``."""
    p = _file(auth_path)
    if not p.is_file():
        return None
    try:
        raw = p.read_bytes()
        blob = (base64.b64decode(raw[4:]) if raw.startswith(b"B64:")
                else _dpapi(raw, False))
        user, pw = blob.decode("utf-8").split(_SEP, 1)
        return user, pw
    except Exception:
        return None


def clear(auth_path=None) -> None:
    """يحذف بيانات الدخول المحفوظة."""
    try:
        _file(auth_path).unlink(missing_ok=True)
    except OSError:
        pass
