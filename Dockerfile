# نشر نسخة الويب على Railway/Docker — مع محرّك قراءة الجوازات (OCR) والعربية
FROM python:3.12-slim

# tesseract + اللغة العربية + مكتبة نظام يحتاجها opencv-headless
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara libglib2.0-0 && apt-get clean

WORKDIR /app

# التبعيات أولاً (طبقة مخبّأة) — الويب أساسي، وقراءة الجوازات اختيارية
COPY requirements-web.txt requirements-web-ocr.txt ./
# الويب إلزامي: فشله يوقف البناء (وهذا صحيح)
RUN pip install --no-cache-dir -r requirements-web.txt
# OCR/OpenCV اختياري: فشله لا يُسقِط نشر الويب (تبقى الميزات الأساسية تعمل)
RUN pip install --no-cache-dir -r requirements-web-ocr.txt \
    || echo "[warn] تعذّر تثبيت مكتبات OCR/OpenCV — تُعطَّل قراءة الجواز واقتصاص الوجه فقط"

# ثم الشيفرة
COPY . .

# HTTPS خلف موجّه Railway؛ HAJJ_DATA_DIR يُضبط من متغيّرات Railway
ENV HTTPS=1

# Railway يمرّر المنفذ في المتغيّر PORT
CMD ["gunicorn","wsgi:app","-c","gunicorn.conf.py"]
