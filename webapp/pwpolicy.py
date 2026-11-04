# -*- coding: utf-8 -*-
"""تاريخ آخر تغيير لكلمة مرور كل حساب، لسياسة «انتهاء كلمة المرور».

الحساب الذي لا تاريخ له (من قبل هذه الميزة) يبدأ العدّ له من أوّل دخول بعدها.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

CHOICES = (90, 180, 365)           # أيام؛ 0 = لا تنتهي
_LOCK = threading.Lock()


def _path() -> Path:
    from hajj_app.paths import data_dir
    return Path(data_dir()) / "password_dates.json"


def _load() -> dict:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def mark(username: str, when: float | None = None) -> None:
    """كلمة مرور هذا الحساب تغيّرت الآن."""
    with _LOCK:
        d = _load()
        d[(username or "").strip().lower()] = when if when is not None else time.time()
        _save(d)


def changed_at(username: str) -> float:
    """وقت آخر تغيير (ويسجّل الآن لحساب بلا تاريخ)."""
    key = (username or "").strip().lower()
    d = _load()
    if key not in d:
        mark(username)
        return time.time()
    return float(d[key])


def days_left(username: str, days: int) -> int | None:
    """الأيام المتبقّية قبل انتهاء كلمة المرور (None = لا سياسة)."""
    if not days:
        return None
    return int(days - (time.time() - changed_at(username)) // 86400)


def forget(username: str) -> None:
    with _LOCK:
        d = _load()
        if d.pop((username or "").strip().lower(), None) is not None:
            _save(d)
