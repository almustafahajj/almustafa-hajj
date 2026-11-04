# -*- coding: utf-8 -*-
"""نسخة احتياطية خارج الخادم، تلقائياً: تُرسل بالبريد يومياً أو أسبوعياً.

النسخ اليومية على الخادم تحمي من الأخطاء، لكنها على القرص نفسه: لو ضاع القرص
أو حُذف المشروع ضاعت معه. هذه النسخة تصل لبريد يحدّده المدير (يُفضَّل Gmail)،
مشفّرة بكلمة مرور يختارها — بصيغة «.almbak» نفسها التي تُستعاد من صفحة النسخ.

كلمة مرور النسخ تُحفظ مشفّرة بمفتاح البيانات، فلا تُفتح إلا من جلسة مستخدم
داخل البورتال (ولهذا يجري الإرسال مع أوّل استعمال في يوم الاستحقاق).
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

FREQS = {"daily": ("يومياً", 1), "weekly": ("أسبوعياً", 7)}
MAX_ATTACH = 7 * 1024 * 1024       # حدّ آمن لمرفقات البريد
RETRY_AFTER = 3 * 3600             # بعد فشل: محاولة جديدة بعد ٣ ساعات
_RUN = threading.Lock()


def _path() -> Path:
    from webapp import backup
    return backup.data_dir() / "offsite_backup.json"


def load() -> dict:
    try:
        cfg = json.loads(_path().read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(cfg: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _update(**changes) -> dict:
    cfg = load()
    cfg.update(changes)
    _save(cfg)
    return cfg


def configure(hs, email: str, freq: str, password: str = "") -> dict:
    """يحفظ الإعداد. كلمة المرور مطلوبة أوّل مرّة، وفارغة = تبقى كما هي."""
    from webapp import mailer
    email = (email or "").strip()
    if not mailer.valid_email(email):
        raise ValueError("اكتب بريداً صحيحاً لاستلام النسخ.")
    if freq not in FREQS:
        raise ValueError("اختر كل كم تُرسل النسخة.")
    cfg = load()
    if password:
        if len(password) < 8:
            raise ValueError("كلمة مرور النسخ ٨ خانات على الأقل.")
        cfg["pw"] = hs.encrypt(password.encode("utf-8")).decode("ascii")
    elif not cfg.get("pw"):
        raise ValueError("اختر كلمة مرور للنسخ (تلزم لفتح النسخة عند الاستعادة).")
    if email.lower() != str(cfg.get("email", "")).lower() or password:
        cfg.pop("last_ok", None)                   # بريد/كلمة جديدة: أرسل قريباً
    cfg.update(email=email, freq=freq, enabled=True, last_err="", last_try=0)
    _save(cfg)
    return cfg


def disable() -> None:
    _update(enabled=False)


def _password(hs, cfg: dict) -> str | None:
    try:
        return hs.decrypt(cfg["pw"].encode("ascii")).decode("utf-8")
    except Exception:                              # noqa: BLE001
        return None


def due(cfg: dict | None = None, now: float | None = None) -> bool:
    cfg = load() if cfg is None else cfg
    now = time.time() if now is None else now
    if not cfg.get("enabled") or not cfg.get("pw") or not cfg.get("email"):
        return False
    if now - float(cfg.get("last_try") or 0) < RETRY_AFTER:
        return False
    days = FREQS.get(cfg.get("freq"), FREQS["weekly"])[1]
    # هامش ساعة كي لا تنزلق النسخة اليومية يوماً بعد يوم
    return now - float(cfg.get("last_ok") or 0) >= days * 86400 - 3600


def build_attachment(password: str) -> tuple[str, bytes]:
    """النسخة المشفّرة (.almbak) داخل ملف zip — صيغة تقبلها خدمات البريد."""
    from webapp import backup
    z = backup.tempfile_path(".zip")
    enc = backup.tempfile_path(".almbak")
    try:
        backup.build_zip(z, with_images=False)
        backup.encrypt_file(z, enc, password)
        data = enc.read_bytes()
    finally:
        z.unlink(missing_ok=True)
        enc.unlink(missing_ok=True)
    stamp = f"{datetime.now():%Y-%m-%d}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as out:
        out.writestr(f"almustafa-backup-{stamp}.almbak", data)
        out.writestr("اقرأني.txt", (
            "نسخة احتياطية مشفّرة من بورتال المصطفى للحج والعمرة.\n"
            "للاستعادة: الإدارة ← النسخ الاحتياطي ← «استعادة من ملف منزّل»،\n"
            "اختر هذا الملف (أو ملف .almbak داخله) واكتب كلمة مرور النسخ.\n").encode("utf-8"))
    return f"almustafa-backup-{stamp}.zip", buf.getvalue()


def send_now(password: str, email: str, wait: bool = True) -> tuple[bool, str]:
    """يبني النسخة ويرسلها الآن. يعيد (نجح؟، رسالة)، ويحفظ الحالة."""
    from webapp import mailer
    got = _RUN.acquire(timeout=90) if wait else _RUN.acquire(blocking=False)
    if not got:
        return False, "يجري إرسال نسخة الآن — انتظر قليلاً."
    try:
        _update(last_try=time.time())
        try:
            name, data = build_attachment(password)
        except Exception as exc:                   # noqa: BLE001
            _update(last_err=f"تعذّر بناء النسخة: {type(exc).__name__}")
            return False, load()["last_err"]
        size = len(data)
        when = f"{datetime.now():%Y-%m-%d %H:%M}"
        if size > MAX_ATTACH:
            msg = (f"النسخة ({size // 1024 // 1024} MB) أكبر من حدّ مرفقات البريد — "
                   "نزّل نسخة يدوياً من صفحة النسخ الاحتياطي.")
            mailer.send(email, "تنبيه: النسخة الاحتياطية كبيرة على البريد", mailer.wrap(
                "النسخة الاحتياطية لم تُرسل", f"<p>{msg}</p>"))
            _update(last_err=msg)
            return False, msg
        ok, why = mailer.send(email, f"نسخة احتياطية — {when}", mailer.wrap(
            "نسخة احتياطية تلقائية", (
                f"<p>مرفق نسخة مشفّرة من بيانات البورتال ({max(1, size // 1024)} KB) — {when}.</p>"
                "<p>احتفظ بهذه الرسالة. لفتح النسخة تلزم <b>كلمة مرور النسخ</b> التي اخترتها "
                "في صفحة النسخ الاحتياطي (بدونها لا تُفتح).</p>"
                "<p>الصور (الجوازات) لا تُرسل بالبريد لحجمها — نزّل نسخة كاملة يدوياً من حين لآخر.</p>")),
            attachments=[(name, data)])
        if not ok:
            _update(last_err=why)
            return False, why
        _update(last_ok=time.time(), last_err="", last_size=size)
        return True, f"أُرسلت نسخة ({max(1, size // 1024)} KB) إلى {email}."
    finally:
        _RUN.release()


def maybe_run(hs) -> bool:
    """يُستدعى مع الطلبات: إن حان موعد الإرسال يبدأه في الخلفية."""
    cfg = load()
    if hs is None or not due(cfg):
        return False
    pw = _password(hs, cfg)
    if pw is None:
        _update(last_try=time.time(),
                last_err="تعذّر فتح كلمة مرور النسخ (تغيّر مفتاح البيانات بعد استعادة؟) — أعد إدخالها.")
        return False
    _update(last_try=time.time())

    def _bg():
        ok, msg = send_now(pw, cfg["email"], wait=False)
        try:
            from hajj_app import audit
            audit.record("نسخة خارجية بالبريد" if ok else "فشل النسخة الخارجية", msg,
                         user="النظام")
        except Exception:                          # noqa: BLE001
            pass
    threading.Thread(target=_bg, daemon=True).start()
    return True


def status(hs=None) -> dict:
    """ملخّص لصفحة النسخ الاحتياطي."""
    cfg = load()
    fmt = (lambda t: datetime.fromtimestamp(float(t)).strftime("%Y-%m-%d %H:%M")
           if t else "")
    nxt = ""
    if cfg.get("enabled") and cfg.get("last_ok"):
        days = FREQS.get(cfg.get("freq"), FREQS["weekly"])[1]
        nxt = fmt(float(cfg["last_ok"]) + days * 86400)
    return {"enabled": bool(cfg.get("enabled")), "email": cfg.get("email", ""),
            "freq": cfg.get("freq", "weekly"), "has_pw": bool(cfg.get("pw")),
            "last_ok": fmt(cfg.get("last_ok")), "last_err": cfg.get("last_err", ""),
            "size_kb": int(cfg.get("last_size") or 0) // 1024, "next": nxt,
            "pw_ok": (hs is None or not cfg.get("pw") or _password(hs, cfg) is not None)}
