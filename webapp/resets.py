# -*- coding: utf-8 -*-
"""طلبات «نسيت كلمة المرور» عبر الإيميل: تنتظر موافقة المدير، ثم رابط لمرة واحدة.

تُحفظ في ``reset_requests.json`` داخل مجلّد البيانات (خارج النسخ الاحتياطية).
لا يُحفظ سرّ الرابط نفسه — بصمته (SHA-256) فقط، ومعه مفتاح البيانات مغلَّفاً
بالسرّ فلا يُفتح إلا بالرابط.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

PENDING_TTL = 48 * 3600          # طلب ينتظر المدير
LINK_TTL = 30 * 60               # الرابط بعد الموافقة


def _path() -> Path:
    from hajj_app.paths import data_dir
    return Path(data_dir()) / "reset_requests.json"


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def load() -> dict:
    """الطلبات الصالحة فقط (تُحذف المنتهية)."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    now = time.time()
    return {k: v for k, v in data.items()
            if isinstance(v, dict) and v.get("exp", 0) > now}


def save(data: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def clear() -> None:
    try:
        _path().unlink()
    except OSError:
        pass


def add(username: str, ip: str) -> tuple[str, bool]:
    """يسجّل طلباً جديداً (أو يعيد القائم لنفس الحساب). يعيد (المعرّف، جديد؟)."""
    data = load()
    for rid, r in data.items():
        if r["user"].lower() == username.lower() and r["status"] == "pending":
            return rid, False
    rid = secrets.token_hex(8)
    data[rid] = {"user": username, "ip": ip, "created": time.time(),
                 "status": "pending", "exp": time.time() + PENDING_TTL}
    save(data)
    return rid, True


def approve(rid: str, wrapped: dict, token: str) -> dict | None:
    data = load()
    r = data.get(rid)
    if not r or r["status"] != "pending":
        return None
    r.update(status="approved", wrapped=wrapped, token=token_hash(token),
             exp=time.time() + LINK_TTL)
    save(data)
    return r


def revert(rid: str) -> None:
    """فشل إرسال الرابط: يعود الطلب منتظراً."""
    data = load()
    r = data.get(rid)
    if r:
        for k in ("wrapped", "token"):
            r.pop(k, None)
        r.update(status="pending", exp=r.get("created", time.time()) + PENDING_TTL)
        save(data)


def remove(rid: str) -> dict | None:
    data = load()
    r = data.pop(rid, None)
    save(data)
    return r


def by_token(token: str) -> tuple[str, dict] | tuple[None, None]:
    h = token_hash(token)
    for rid, r in load().items():
        if r.get("status") == "approved" and secrets.compare_digest(r.get("token", ""), h):
            return rid, r
    return None, None


def pending() -> list[dict]:
    return sorted(({"id": k, **v} for k, v in load().items()),
                  key=lambda r: r["created"])
