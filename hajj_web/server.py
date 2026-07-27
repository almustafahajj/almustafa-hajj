"""تشغيل خادم الويب (waitress) — للاستعمال الفعلي داخل شبكة المكتب.

    python -m hajj_web            # يستمع على 0.0.0.0:8000

افتح من أجهزة الشبكة:  http://<ip-هذا-الجهاز>:8000
"""

from __future__ import annotations

import os
import socket

from waitress import serve

from .app import create_app


def _local_ip() -> str:
    """عنوان هذا الجهاز في الشبكة المحلية (لعرض الرابط)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main() -> None:
    host = os.environ.get("HAJJ_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("HAJJ_WEB_PORT", "8000"))
    app = create_app()
    ip = _local_ip()
    print("=" * 48)
    print("  برنامج موسم الحج — نسخة الويب")
    print(f"  على هذا الجهاز:   http://localhost:{port}")
    print(f"  من أجهزة الشبكة:  http://{ip}:{port}")
    print("  (أوقف الخادم بـ Ctrl+C)")
    print("=" * 48)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
