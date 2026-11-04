# -*- coding: utf-8 -*-
"""جلسات الدخول المحفوظة على القرص — تبقى بعد إعادة تشغيل الخادم (كل نشر).

مفتاح البيانات لا يُكتب على القرص كما هو: يُشفَّر بمفتاح عشوائي لكل جلسة لا
يوجد إلا في ملف ارتباط متصفّح صاحبها. فملفّات هذا المجلّد وحدها لا تفتح شيئاً،
وتُستعمل أيضاً لعرض «الجلسات النشطة» للمدير وإخراج أي جلسة منها.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

MAX_AGE = 14 * 86400               # مثل «تذكّرني»: جلسة بلا نشاط أطول من هذا تُحذف
TOUCH_EVERY = 120                  # ثوانٍ بين تحديثَين لوقت آخر نشاط على القرص
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def root() -> Path:
    from hajj_app.paths import data_dir
    p = Path(data_dir()) / "web_sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sid_id(sid: str) -> str:
    """معرّف الجلسة على القرص وفي صفحة المدير (لا يكشف رمز المتصفّح نفسه)."""
    return hashlib.sha256(("websess:" + str(sid)).encode("utf-8")).hexdigest()[:32]


def _path(sess_id: str) -> Path | None:
    return root() / f"{sess_id}.json" if _ID_RE.match(sess_id or "") else None


def save(sid: str, hs, *, ip: str = "", ua: str = "") -> str:
    """يحفظ الجلسة ويعيد مفتاحها (يوضع في ملف ارتباط المتصفّح فقط)."""
    sk = Fernet.generate_key()
    secret = json.dumps({"k": base64.b64encode(hs.data_key).decode("ascii")})
    rec = {"user": hs.username, "role": hs.role, "since": int(time.time()),
           "ip": (ip or "")[:64], "ua": (ua or "")[:300],
           "blob": Fernet(sk).encrypt(secret.encode("utf-8")).decode("ascii")}
    p = _path(sid_id(sid))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return sk.decode("ascii")


def _read(p: Path) -> dict | None:
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else None
    except (OSError, ValueError):
        return None


def restore(sid: str, sk: str):
    """يعيد بناء جلسة hajj_app من القرص بمفتاح المتصفّح، أو None."""
    from hajj_app import auth
    p = _path(sid_id(sid))
    try:
        if time.time() - p.stat().st_mtime > MAX_AGE:
            p.unlink(missing_ok=True)
            return None
    except OSError:
        return None
    rec = _read(p)
    if not rec:
        return None
    try:
        secret = json.loads(Fernet(sk.encode("ascii")).decrypt(rec["blob"].encode("ascii")))
        key = base64.b64decode(secret["k"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        return None
    return auth.Session(rec["user"], key, role=rec.get("role", "viewer"))


def touch(sid: str) -> None:
    """يحدّث وقت آخر نشاط (على الأكثر مرّة كل دقيقتين)."""
    p = _path(sid_id(sid))
    try:
        if time.time() - p.stat().st_mtime > TOUCH_EVERY:
            os.utime(p)
    except OSError:
        pass


def drop(sid: str) -> None:
    drop_id(sid_id(sid))


def drop_id(sess_id: str) -> None:
    p = _path(sess_id)
    if p is not None:
        p.unlink(missing_ok=True)


def drop_user(username: str) -> list:
    """يحذف كل جلسات مستخدم؛ يعيد معرّفاتها."""
    gone = [s["id"] for s in list_all() if s["user"].lower() == (username or "").lower()]
    for i in gone:
        drop_id(i)
    return gone


def clear() -> None:
    for p in root().glob("*.json"):
        p.unlink(missing_ok=True)


def list_all() -> list:
    """كل الجلسات الصالحة (الأحدث نشاطاً أولاً)، وتحذف المنتهية."""
    out, now = [], time.time()
    for p in root().glob("*.json"):
        try:
            last = p.stat().st_mtime
        except OSError:
            continue
        if now - last > MAX_AGE:
            p.unlink(missing_ok=True)
            continue
        rec = _read(p)
        if not rec:
            continue
        out.append({"id": p.stem, "user": rec.get("user", ""), "role": rec.get("role", ""),
                    "since": rec.get("since", 0), "last": last,
                    "ip": rec.get("ip", ""), "ua": rec.get("ua", "")})
    return sorted(out, key=lambda s: -s["last"])


def device(ua: str) -> str:
    """وصف مختصر للجهاز والمتصفّح من ترويسة User-Agent."""
    ua = ua or ""
    osname = next((n for k, n in (("iPhone", "آيفون"), ("iPad", "آيباد"), ("Android", "أندرويد"),
                                  ("Windows", "ويندوز"), ("Mac OS", "ماك"), ("CrOS", "كروم بوك"),
                                  ("Linux", "لينكس")) if k in ua), "جهاز غير معروف")
    browser = next((n for k, n in (("Edg/", "Edge"), ("SamsungBrowser", "Samsung"),
                                   ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                   ("CriOS", "Chrome"), ("Chrome/", "Chrome"),
                                   ("Safari/", "Safari")) if k in ua), "")
    return f"{osname} · {browser}" if browser else osname
