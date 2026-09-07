# نشر نسخة الويب على Railway/Docker — مع محرّك قراءة الجوازات (OCR) والعربية
FROM python:3.12-slim

# tesseract + اللغة العربية + مكتبة نظام يحتاجها opencv-headless
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara libglib2.0-0 && apt-get clean

WORKDIR /app

# التبعيات أولاً (طبقة مخبّأة) — الويب + قراءة الجوازات
COPY requirements-web.txt requirements-web-ocr.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt -r requirements-web-ocr.txt

# ثم الشيفرة
COPY . .

# HTTPS خلف موجّه Railway؛ HAJJ_DATA_DIR يُضبط من متغيّرات Railway
ENV HTTPS=1

# Railway يمرّر المنفذ في المتغيّر PORT
CMD ["gunicorn","wsgi:app","-c","gunicorn.conf.py"]
