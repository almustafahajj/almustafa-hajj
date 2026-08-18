"""مشغّل تطبيق الويب (تطوير محلّي) — يفتح لوحة التحكم في المتصفّح.

    python run_web.py

للنشر السحابي لاحقاً يُستخدم خادم WSGI (gunicorn/waitress) مع HTTPS."""

import threading
import webbrowser

from webapp.server import app

if __name__ == "__main__":
    port = 5000
    threading.Timer(
        1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
