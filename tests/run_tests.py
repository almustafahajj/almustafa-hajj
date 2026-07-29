# -*- coding: utf-8 -*-
"""يشغّل كل الاختبارات بالترتيب ويطبع ملخّصاً.

    .venv\\Scripts\\python.exe tests\\run_tests.py

الترتيب مقصود: `test_ocr` و`test_pdfin` ينتجان ملفات عيّنة في `tests/_out`
يقرأها `test_gui_pdf` لاحقاً، فلا تُعِد ترتيبهما.
"""
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))

# الترتيب: الوحدات المستقلة أولاً، ثم ما يعتمد على مخرجاتها.
TESTS = [
    "test_core.py",           # MRZ + دورة إكسل + PDF
    "test_fields.py",         # الأعمدة الـ26 والحقول المحسوبة
    "test_excel_import.py",   # مطابقة الرؤوس واختيار الورقة الصحيحة
    "test_rooming.py",        # كشف التسكين: السعة والتوزيع والقواعد
    "test_airline.py",        # كشف الطيران الإنجليزي وإدخالات أماديوس
    "test_camps.py",          # كشف تسكين المخيمات: الفصل بالجنس والعائلة والخيام
    "test_quality.py",        # فحص الجودة: تكرار الجواز، صلاحيته، ونقص البيانات
    "test_stats.py",          # الإحصاءات والملخّص المالي وإيصال الدفع
    "test_payments.py",       # سجلّ الدفعات (الأقساط): التخزين والمزامنة والنافذة
    "test_productivity.py",   # تعديل جماعي، مواصلات، وبطاقات QR
    "test_programs.py",       # برامج الحملة: النموذج، الاحتساب، والتطبيق
    "test_travel.py",         # مواعيد وتعليمات السفر: القوالب والتخزين وPDF
    "test_whatsapp.py",       # رسائل واتساب: تطبيع الأرقام والرابط والنافذة
    "test_audit.py",          # سجلّ التدقيق: الوحدة وتسجيل العمليات
    "test_ocr.py",            # قراءة MRZ من صورة  -> ينتج fake_passport.png
    "test_pdfin.py",          # استيراد PDF        -> ينتج passports_text.pdf
    "test_arabic.py",         # الاسم العربي: طبقة نصية + OCR + الترشيح
    "test_names.py",          # كشف الأسماء الفاسدة + الإضافة اليدوية
    "test_optional.py",       # حذف KKKK مع بقاء الأرقام الحقيقية
    "test_translit.py",       # المطابقة الصوتية بالاسم اللاتيني
    "test_auth.py",           # الدخول وتشفير ملف البيانات
    "test_recovery.py",       # مفتاح الاسترداد وإعادة تعيين كلمة المرور
    "test_images.py",         # تخزين الصور مشفّراً وطباعة الجوازات
    "test_storage.py",        # الحفظ والاستعادة واستعادة الملف التالف
    "test_backup.py",         # النسخ الاحتياطية المؤرّخة (اللقطات) والتقليم
    "test_i18n.py",           # الواجهة ثنائية اللغة (عربي/إنجليزي)
    "test_app_mode.py",       # وضع التشغيل (حج/عمرة): فصل الملفّات وإخفاء المناسك
    "test_gui.py",            # الواجهة والجدول ونافذة التعديل
    "test_gui_pdf.py",        # دفعة مختلطة عبر الواجهة (يحتاج ما سبق)
    "test_web.py",            # نسخة الويب: الدخول والجلسة وعرض الكشف والبحث
    "test_real_passport.py",  # جواز حقيقي — يتخطّى نفسه إن لم تتوفّر الصورة
]


def main() -> int:
    results = []
    for name in TESTS:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            results.append((name, "مفقود", 0.0))
            continue
        print(f"\n{'=' * 70}\n>>> {name}\n{'=' * 70}", flush=True)
        started = time.monotonic()
        proc = subprocess.run([sys.executable, path], cwd=HERE)
        elapsed = time.monotonic() - started
        results.append((name, "نجح" if proc.returncode == 0 else "فشل", elapsed))

    print(f"\n{'=' * 70}\nالملخّص\n{'=' * 70}")
    for name, status, elapsed in results:
        mark = {"نجح": "OK  ", "فشل": "FAIL", "مفقود": "MISS"}[status]
        print(f"  [{mark}] {name:24} {elapsed:6.1f}s")

    failed = [n for n, s, _ in results if s != "نجح"]
    if failed:
        print(f"\n*** فشل {len(failed)} من {len(results)}: {', '.join(failed)} ***")
        return 1
    print(f"\n*** كل الاختبارات الـ{len(results)} نجحت ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
