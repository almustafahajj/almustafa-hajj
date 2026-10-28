# -*- coding: utf-8 -*-
"""سجلّ الروابط العامة (بلا تسجيل دخول): التحقّق من المستندات بـ QR، وصفحة
المعتمر الخاصة.

الكشف مشفّر بمفتاح الجلسة فلا تقرؤه صفحة عامة؛ لذا يُحفظ هنا عند الإصدار
**أقلّ قدر لازم** فقط (رقم المستند، الفندق والتواريخ، اسم مختصر)، ويُعرَّف كل
رابط برمز عشوائي طويل لا يُخمَّن. لا أرقام جوازات ولا هواتف ولا مبالغ.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime

_LOCK = threading.Lock()


def _path():
    from hajj_app.paths import data_dir
    return data_dir() / "public_links.json"


def _load() -> dict:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("docs", {})
            raw.setdefault("people", {})
            return raw
    except (OSError, ValueError):
        pass
    return {"docs": {}, "people": {}}


def _save(reg: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def mask_name(name: str) -> str:
    """الاسم الأول كاملاً وبقية الأسماء بحرفها الأول: «أحمد م. ع.»."""
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "—"
    return " ".join([parts[0]] + [p[0] + "." for p in parts[1:3]])


def doc_token(info: dict) -> str:
    """رمز التحقّق لمستند — ثابت لنفس (النظام، النوع، الرقم) فيبقى QR صالحاً
    عند إعادة إصدار الفاوتشر نفسه، وتُحدَّث بياناته."""
    with _LOCK:
        reg = _load()
        key = (info.get("mode"), info.get("kind"), str(info.get("number") or ""))
        tok = None
        if key[2]:
            tok = next((t for t, d in reg["docs"].items()
                        if (d.get("mode"), d.get("kind"), str(d.get("number") or "")) == key),
                       None)
        tok = tok or secrets.token_urlsafe(12)
        old = reg["docs"].get(tok, {})
        reg["docs"][tok] = {**info, "issued": old.get("issued") or _now(),
                            "updated": _now()}
        _save(reg)
        return tok


def get_doc(token: str) -> dict | None:
    return _load()["docs"].get(str(token or "")) if token else None


def person_token(mode: str, uid: str, info: dict, *, rotate: bool = False) -> str:
    """رابط المعتمر الخاص — ثابت لكل شخص حتى يُجدَّد (فيبطل القديم)."""
    with _LOCK:
        reg = _load()
        old = next((t for t, p in reg["people"].items()
                    if p.get("mode") == mode and p.get("uid") == uid), None)
        if old and rotate:
            reg["people"].pop(old, None)
            old = None
        tok = old or secrets.token_urlsafe(16)
        reg["people"][tok] = {**info, "mode": mode, "uid": uid, "updated": _now()}
        _save(reg)
        return tok


def find_person(mode: str, uid: str) -> str | None:
    return next((t for t, p in _load()["people"].items()
                 if p.get("mode") == mode and p.get("uid") == uid), None)


def revoke_person(mode: str, uid: str) -> bool:
    with _LOCK:
        reg = _load()
        toks = [t for t, p in reg["people"].items()
                if p.get("mode") == mode and p.get("uid") == uid]
        for t in toks:
            reg["people"].pop(t, None)
        if toks:
            _save(reg)
        return bool(toks)


def get_person(token: str) -> dict | None:
    return _load()["people"].get(str(token or "")) if token else None


def person_docs(mode: str, uid: str) -> list:
    """رموز تحقّق مستندات هذا الشخص (لروابطها في صفحته)."""
    return [(t, d) for t, d in _load()["docs"].items()
            if d.get("mode") == mode and uid and d.get("uid") == uid]
