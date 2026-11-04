# -*- coding: utf-8 -*-
"""المواسم المحفوظة: عند الانتقال لموسم جديد يُحفظ الحالي كاملاً ويبدأ الجديد
بقوائم فارغة، ويمكن للمدير فتح موسم سابق كما كان.

كل موسم محفوظ مجلّد ``seasons/<الوضع>/<السنة>/`` داخل مجلّد البيانات، فيه نسخ
ملفّات الوضع كما هي (مشفّرة أصلاً): الكشف، المستندات، الخيام، و``season.json``
بمفاتيح الإعدادات الموسمية. الموسم المفتوح حالياً هو الملفّات الحيّة نفسها.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from hajj_app import app_mode, storage

# تُفرَّغ مع الموسم الجديد (قوائم الموسم وعملياته)
SEASONAL_KEYS = ("groups", "expenses", "travel", "umrah_vouchers",
                 "umrah_transport_requests", "umrah_quotes", "hajj_quotes",
                 "umrah_reminders")
# تنتقل للموسم الجديد كما هي، لكنها تُحفظ مع كل موسم فيعود بها عند فتحه
CARRY_KEYS = ("programs", "umrah_trips", "umrah_packages", "umrah_package_order",
              "umrah_pricings", "itinerary")
META = "season.json"


def root() -> Path:
    from hajj_app.paths import data_dir
    return Path(data_dir()) / "seasons"


def _dir(year: str, mode: str | None = None) -> Path:
    return root() / (mode or app_mode.get_mode()) / str(year)


def _live_files() -> list:
    """ملفّات الموسم الحيّة للوضع الحالي."""
    return [storage.default_data_path(), storage.documents_path(),
            storage.camps_path()]


def valid_year(year: str) -> bool:
    return str(year).isdigit() and len(str(year)) == 4


def has(year: str) -> bool:
    return valid_year(year) and (_dir(year) / META).is_file()


def list_saved(session=None) -> list:
    """المواسم المحفوظة للوضع الحالي، الأحدث سنةً أولاً."""
    base = root() / app_mode.get_mode()
    out = []
    for d in sorted(base.iterdir(), reverse=True) if base.is_dir() else []:
        if not (valid_year(d.name) and (d / META).is_file()):
            continue
        try:
            meta = json.loads((d / META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        count = None
        data = d / storage.default_data_path().name
        if data.is_file() and session is not None:
            try:
                count = len(storage._read_file(data, session))
            except Exception:                      # noqa: BLE001
                count = None
        elif not data.is_file():
            count = 0
        out.append({"year": d.name, "saved_at": meta.get("saved_at", ""),
                    "count": count})
    return out


def save_current(year: str) -> Path:
    """يحفظ الموسم الحيّ في مجلّده (يُكتب كاملاً ثم يحلّ محلّ السابق)."""
    dest = _dir(year)
    tmp = dest.with_name(f".tmp-{year}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for p in _live_files():
        if p.is_file():
            shutil.copy2(p, tmp / p.name)
    settings = storage.load_settings()
    meta = {"year": str(year), "saved_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "settings": {k: settings[k] for k in SEASONAL_KEYS + CARRY_KEYS
                         if k in settings}}
    (tmp / META).write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    old = dest.with_name(f".old-{year}")
    shutil.rmtree(old, ignore_errors=True)
    if dest.exists():
        os.replace(dest, old)
    os.replace(tmp, dest)
    shutil.rmtree(old, ignore_errors=True)
    return dest


def _drop_live() -> None:
    for p in _live_files():
        for f in (p, p.with_suffix(".bak")):
            f.unlink(missing_ok=True)


def switch(current: str, target: str) -> str:
    """ينتقل من موسم ``current`` إلى ``target`` للوضع الحالي.

    يحفظ الحالي أولاً (وأي خطأ هنا يوقف كل شيء دون تغيير). ثم إن كان
    ``target`` محفوظاً يُفتح كما كان ويُزال من المحفوظات (صار هو الحيّ)،
    وإلا يبدأ موسماً جديداً بقوائم فارغة مع نقل البرامج.
    يعيد ``"opened"`` أو ``"new"``."""
    if not valid_year(target) or str(target) == str(current):
        raise ValueError("سنة الموسم غير صالحة.")
    save_current(current)
    settings = storage.load_settings()
    src = _dir(target)
    if (src / META).is_file():
        meta = json.loads((src / META).read_text(encoding="utf-8"))
        _drop_live()
        for p in _live_files():
            if (src / p.name).is_file():
                tmp = p.with_suffix(".tmp")
                shutil.copy2(src / p.name, tmp)
                os.replace(tmp, p)
        for k in SEASONAL_KEYS + CARRY_KEYS:
            settings.pop(k, None)
        settings.update(meta.get("settings") or {})
        result = "opened"
    else:
        _drop_live()
        for k in SEASONAL_KEYS:
            settings.pop(k, None)
        result = "new"
    settings["season_year"] = str(target)
    storage.save_settings(settings)
    if result == "opened":
        shutil.rmtree(src, ignore_errors=True)
    return result
