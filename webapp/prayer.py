# -*- coding: utf-8 -*-
"""مواقيت الصلاة في مكة المكرمة والمدينة المنورة بطريقة «أمّ القرى» — حساب فلكي
محلّي (خوارزمية PrayTimes المعروفة) بلا أي خدمة خارجية، لقسم «في الحرم» في صفحة
«رحلتي». تقريبية بدقيقة أو اثنتين، والصفحة تنبّه إلى اتّباع أذان الحرم.

طريقة أمّ القرى: الفجر عند انخفاض الشمس 18.5°، والعصر بظلّ المِثل (الجمهور)،
والعشاء بعد المغرب بـ 90 دقيقة (120 في رمضان)، والتوقيت +3 (السعودية).
"""
import math
from datetime import date, timedelta

CITIES = {"makkah": ("مكة المكرمة", 21.4225, 39.8262),
          "madinah": ("المدينة المنورة", 24.4672, 39.6111)}
NAMES = ("الفجر", "الشروق", "الظهر", "العصر", "المغرب", "العشاء")
TZ = 3.0
_FAJR_ANGLE = 18.5
_RISE_SET = 0.833


def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))
def _tan(d): return math.tan(math.radians(d))
def _asin(x): return math.degrees(math.asin(x))
def _acos(x): return math.degrees(math.acos(x))
def _acot(x): return math.degrees(math.atan(1 / x))
def _atan2(y, x): return math.degrees(math.atan2(y, x))
def _fix(a, b): return a - b * math.floor(a / b)


def _julian(y: int, m: int, d: int) -> float:
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def _sun(jd: float):
    """ميل الشمس ومعادلة الزمن ليومٍ جولياني."""
    n = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * n, 360)
    q = _fix(280.459 + 0.98564736 * n, 360)
    lon = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * n
    ra = _atan2(_cos(e) * _sin(lon), _cos(lon)) / 15
    eqt = q / 15 - _fix(ra, 24)
    decl = _asin(_sin(e) * _sin(lon))
    return decl, eqt


def _hm(hours: float) -> str:
    h = _fix(hours + 0.5 / 60, 24)                    # تقريب لأقرب دقيقة
    hh = int(h)
    return f"{hh:02d}:{int((h - hh) * 60):02d}"


def times(day: date, lat: float, lng: float, ramadan: bool = False) -> list:
    """[الفجر، الشروق، الظهر، العصر، المغرب، العشاء] بصيغة HH:MM (توقيت السعودية)."""
    jd = _julian(day.year, day.month, day.day) - lng / (15 * 24)

    def noon(t):
        return _fix(12 - _sun(jd + t)[1], 24)

    def at_angle(angle, t, before_noon=False):
        decl = _sun(jd + t)[0]
        x = (-_sin(angle) - _sin(decl) * _sin(lat)) / (_cos(decl) * _cos(lat))
        span = _acos(max(-1.0, min(1.0, x))) / 15
        return noon(t) + (-span if before_noon else span)

    def asr(t, factor=1):
        decl = _sun(jd + t)[0]
        return at_angle(-_acot(factor + _tan(abs(lat - decl))), t)

    fajr = at_angle(_FAJR_ANGLE, 5 / 24, True)
    rise = at_angle(_RISE_SET, 6 / 24, True)
    dhuhr = noon(12 / 24)
    asr_t = asr(13 / 24)
    maghrib = at_angle(_RISE_SET, 18 / 24)
    adj = TZ - lng / 15
    vals = [v + adj for v in (fajr, rise, dhuhr, asr_t, maghrib)]
    vals.append(vals[4] + (2.0 if ramadan else 1.5))
    return [_hm(v) for v in vals]


def table(start: date, days: int, is_ramadan=lambda d: False) -> dict:
    """مواقيت المدينتين لعدّة أيام: {"YYYY-MM-DD": {"makkah": [...], "madinah": [...]}}."""
    out = {}
    for i in range(max(0, int(days))):
        d = start + timedelta(days=i)
        r = bool(is_ramadan(d))
        out[d.isoformat()] = {k: times(d, lat, lng, r) for k, (_n, lat, lng) in CITIES.items()}
    return out
