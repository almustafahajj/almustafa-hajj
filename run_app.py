"""نقطة تشغيل نسخة exe المبنيّة بـ PyInstaller.

    HajjApp.exe          -> برنامج سطح المكتب
"""

import hajj_app.gui as _gui


def main() -> None:
    _gui.main()


if __name__ == "__main__":
    main()
