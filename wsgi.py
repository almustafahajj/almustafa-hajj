"""مدخل WSGI للنشر السحابي (Linux) — يُشغَّل عبر:  gunicorn wsgi:app

يستورد تطبيق Flask من webapp.server. مسارات البيانات والأمان تُضبط من متغيّرات
البيئة (HAJJ_DATA_DIR على قرص دائم، SECRET_KEY ثابت، HTTPS=1)."""

from webapp.server import app  # noqa: F401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
