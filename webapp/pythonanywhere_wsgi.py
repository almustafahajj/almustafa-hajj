"""ملفّ WSGI لاستضافة PythonAnywhere (النسخة المجانية).

انسخ محتوى هذا الملفّ والصقه في محرّر WSGI لدى PythonAnywhere:
  Web  ←  WSGI configuration file  ←  استبدل كل محتواه بهذا.

يشتقّ المسارات من مجلد المستخدم تلقائياً (لا حاجة لكتابة اسم المستخدم)، ويضبط
متغيّرات البيئة: مجلّد بيانات دائم في المنزل، مفتاح جلسات ثابت، وHTTPS.
"""

import os
import sys

HOME = os.path.expanduser("~")                     # /home/<username>
PROJECT = os.path.join(HOME, "almustafa-hajj")     # مجلّد المستودع بعد git clone
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

# مجلّد بيانات دائم داخل المنزل — يبقى عبر إعادات التشغيل والتحديثات
os.environ.setdefault("HAJJ_DATA_DIR", os.path.join(HOME, "hajj-data"))
# مفتاح توقيع الجلسات (ثابت — يُبقي الجلسات صالحة). غيّره إن شئت.
os.environ.setdefault(
    "SECRET_KEY",
    "250bbe0a6c97fcc517ab2a728bf4c9650ca7c84808457e8160ac59d49a7b7385")
os.environ.setdefault("HTTPS", "1")                # PythonAnywhere يقدّم HTTPS

from webapp.server import app as application       # noqa: E402  (يتطلّبه PA)
