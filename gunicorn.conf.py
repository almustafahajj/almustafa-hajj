import os
# يقرأ منفذ Railway من متغيّر البيئة مباشرة (يتفادى مشكلة عدم توسيع $PORT)
bind = "0.0.0.0:" + os.environ.get("PORT", "8080")
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
timeout = 120
