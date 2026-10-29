# -*- coding: utf-8 -*-
"""إرسال البريد عبر Brevo (رسائل فردية آلية — Transactional) بلا مكتبات إضافية.

الإعداد من متغيّرات البيئة في Railway:
  BREVO_API_KEY    مفتاح الـ API (يبدأ بـ xkeysib-)
  MAIL_FROM        عنوان المرسل الموثَّق في Brevo، مثل noreply@ntravel.ae
  MAIL_FROM_NAME   اسم المرسل (اختياري)

بلا مفتاح أو مرسل تبقى ميزات البريد متوقّفة ولا يتعطّل شيء آخر.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request

API_URL = "https://api.brevo.com/v3/smtp/email"
_EMAIL_RE = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[A-Za-z]{2,}$")

# للاختبارات: إن كانت قائمة، تُلحق بها الرسائل بدل إرسالها فعلاً
OUTBOX: list | None = None


def valid_email(text: str) -> bool:
    text = (text or "").strip()
    return len(text) <= 254 and bool(_EMAIL_RE.match(text))


def _key() -> str:
    return (os.environ.get("BREVO_API_KEY") or "").strip()


def sender() -> str:
    return (os.environ.get("MAIL_FROM") or "").strip()


def configured() -> bool:
    """هل البريد جاهز للإرسال (مفتاح + مرسل صالح)؟"""
    return OUTBOX is not None or (bool(_key()) and valid_email(sender()))


def status() -> str:
    """وصف قصير لحالة الإعداد (لصفحة الحسابات)."""
    if OUTBOX is not None:
        return "ok"
    if not _key():
        return "no-key"
    if not valid_email(sender()):
        return "no-sender"
    return "ok"


def wrap(title: str, body_html: str) -> str:
    """قالب الرسالة: عربي من اليمين لليسار، بسيط ليظهر جيداً في كل البرامج."""
    return (
        '<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;font-size:15px;'
        'line-height:1.8;color:#222;max-width:560px;margin:auto">'
        '<div style="background:#13795B;color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;'
        'font-size:17px;font-weight:bold">المصطفى للحج والعمرة</div>'
        '<div style="border:1px solid #dfe6e2;border-top:0;padding:18px;border-radius:0 0 10px 10px">'
        f'<h2 style="margin:0 0 10px;font-size:17px">{html.escape(title)}</h2>{body_html}'
        '<p style="color:#888;font-size:12px;margin-top:22px">رسالة آلية من بورتال المصطفى — '
        'لا تردّ عليها.</p></div></div>')


def send(to: str, subject: str, body_html: str) -> tuple[bool, str]:
    """يرسل رسالة واحدة. يعيد (نجح؟، سبب الفشل)."""
    if not valid_email(to):
        return False, "عنوان البريد غير صالح."
    if OUTBOX is not None:
        OUTBOX.append({"to": to, "subject": subject, "html": body_html})
        return True, ""
    if not configured():
        return False, "البريد غير مفعّل على الخادم."
    payload = {
        "sender": {"email": sender(),
                   "name": (os.environ.get("MAIL_FROM_NAME") or "").strip()
                   or "المصطفى للحج والعمرة"},
        "to": [{"email": to.strip()}],
        "subject": subject,
        "htmlContent": body_html,
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"api-key": _key(), "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                return True, ""
            return False, f"رفض الخادم ({resp.status})."
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode("utf-8", "replace")).get("message", "")
        except Exception:                          # noqa: BLE001
            msg = ""
        return False, f"رفضت Brevo الإرسال ({exc.code}){': ' + msg[:200] if msg else ''}."
    except Exception as exc:                       # noqa: BLE001
        return False, f"تعذّر الاتصال بخدمة البريد: {type(exc).__name__}."
