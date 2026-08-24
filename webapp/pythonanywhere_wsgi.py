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
os.environ.setdefault("HTTPS", "1")                # PythonAnywhere يقدّم HTTPS
# مفتاح توقيع الجلسات يُولَّد ويُحفظ تلقائياً على الخادم (في مجلّد البيانات)،
# فلا حاجة لضبطه هنا ولا لتضمين أي سرّ في المستودع.

from webapp.server import app as application       # noqa: E402  (يتطلّبه PA)
