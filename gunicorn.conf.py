import os
# منفذ Railway من البيئة
bind = "0.0.0.0:" + os.environ.get("PORT", "8080")
# عامل واحد فقط: جلسات الدخول محفوظة في ذاكرة العملية (مشتركة)، فلا تُطرد
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
timeout = 120
