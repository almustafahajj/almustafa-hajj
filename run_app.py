"""نقطة تشغيل نسخة exe المبنيّة بـ PyInstaller.

بلا وسائط: يفتح **برنامج سطح المكتب**.
الوسيط ``web``: يشغّل **نسخة الويب** (خادم محلي) — نفس الملف التنفيذي.

    HajjApp.exe          -> سطح المكتب
    HajjApp.exe web      -> نسخة الويب

نستورد الحزمتين في الأعلى ليضمّهما PyInstaller في نسخة exe واحدة.
"""

import sys

import hajj_app.gui as _gui
import hajj_web.server as _web       # ليُضمّن في نسخة exe


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1].lower() == "web":
        _web.main()
    else:
        _gui.main()


if __name__ == "__main__":
    main()
