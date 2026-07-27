"""نقطة تشغيل نسخة exe المبنيّة بـ PyInstaller.

مكافئ لـ ``python -m hajj_app`` لكنه ملف مستقل يشير إليه ملف الإعداد
``HajjApp.spec``.
"""

from hajj_app.gui import main

if __name__ == "__main__":
    main()
