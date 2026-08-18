"""تخزين عروض أسعار/برامج الحج المحفوظة داخل ملفّ الإعدادات (مثل تسعيرات
العمرة). كلّ عرض قاموس محتواه ما يبنيه محرّر «برنامج الحج» مع رقمٍ مرجعي."""

from __future__ import annotations


def next_hajj_quote_number(settings: dict) -> str:
    """يخصّص رقماً مرجعياً لعرض سعر حج تسلسلياً (MA-H0001…) ويحجزه."""
    try:
        seq = int(settings.get("hajj_quote_seq", 0) or 0)
    except (TypeError, ValueError):
        seq = 0
    seq += 1
    settings["hajj_quote_seq"] = seq
    return f"MA-H{seq:04d}"


def load_hajj_quotes(settings: dict) -> list:
    """يعيد عروض أسعار الحج المحفوظة (قائمة قواميس)."""
    lst = settings.get("hajj_quotes")
    return list(lst) if isinstance(lst, list) else []


def save_hajj_quote(settings: dict, quote: dict) -> None:
    """يحفظ عرض سعر حج؛ يحدّث الموجود بنفس الرقم أو يضيف جديداً."""
    lst = settings.get("hajj_quotes")
    if not isinstance(lst, list):
        lst = []
        settings["hajj_quotes"] = lst
    num = str(quote.get("number") or "")
    for i, q in enumerate(lst):
        if num and str(q.get("number") or "") == num:
            lst[i] = dict(quote)
            return
    lst.append(dict(quote))


def delete_hajj_quote(settings: dict, number: str) -> None:
    """يحذف عرض سعر حج بحسب رقمه المرجعي."""
    lst = settings.get("hajj_quotes")
    if isinstance(lst, list):
        settings["hajj_quotes"] = [
            q for q in lst if str(q.get("number") or "") != str(number)]
