# نشر نسخة الويب مجاناً على PythonAnywhere

استضافة **مجانية** تحفظ البيانات وتبقى متاحة ٢٤/٧ (لا حاجة لتشغيل جهازك).
الرابط سيكون: `https://اسم-المستخدم.pythonanywhere.com`.

## المتطلّبات
- حساب مجاني على [pythonanywhere.com](https://www.pythonanywhere.com) (بلا بطاقة).
- المستودع الخاص على GitHub: `almustafahajj/almustafa-hajj`.

## الخطوات

### 1) أنشئ الحساب المجاني
سجّل حساباً من نوع **Beginner (مجاني)**. سيصبح لك رابط
`https://<username>.pythonanywhere.com`.

### 2) اجلب الشيفرة (Bash console)
من لوحة PythonAnywhere: **Consoles → Bash**، ثم:
```bash
git clone https://github.com/almustafahajj/almustafa-hajj.git
```
عند طلب كلمة المرور استخدم **رمز وصول (Personal Access Token)** من GitHub
(Settings → Developer settings → Tokens) لأن المستودع خاصّ.

### 3) جهّز بيئة بايثون والمكتبات
في نفس الـ Bash console:
```bash
cd ~/almustafa-hajj
python3.10 -m venv ~/venv          # أو أحدث إصدار متاح لديك
source ~/venv/bin/activate
pip install -r requirements-web.txt
```
(إن لم يتوفّر 3.10 اختر 3.11/3.13 المتاح — كلها تعمل.)

### 4) أنشئ تطبيق الويب
- **Web → Add a new web app → Manual configuration** (ليس Flask التلقائي).
- اختر نفس إصدار بايثون الذي أنشأت به البيئة.

### 5) اضبط البيئة الافتراضية (Virtualenv)
في صفحة **Web**، خانة **Virtualenv**، اكتب:
```
/home/<username>/venv
```

### 6) اضبط ملفّ WSGI
- في صفحة **Web** اضغط رابط **WSGI configuration file**.
- **احذف كل محتواه** والصق محتوى الملفّ الجاهز:
  [`webapp/pythonanywhere_wsgi.py`](pythonanywhere_wsgi.py) (من المستودع).
- احفظ. (الملفّ يشتقّ المسارات تلقائياً؛ لا تحتاج تعديل اسم المستخدم.)

### 7) شغّل
- ارجع لأعلى صفحة **Web** واضغط **Reload**.
- افتح `https://<username>.pythonanywhere.com`.
- ستظهر **صفحة التهيئة**: أنشئ حساب المالك واحفظ **مفتاح الاسترداد**.
- من **«👥 إدارة الحسابات»** أضِف مستخدميك وصلاحياتهم وشاركهم الرابط.

## أين تُحفظ البيانات؟
في `/home/<username>/hajj-data` (الكشف + الحسابات، مشفّرة) — تبقى دائمة.
**انسخها احتياطياً** من حين لآخر (من Bash: `tar czf backup.tgz ~/hajj-data`).

## عند أي تحديث للبرنامج مستقبلاً
```bash
cd ~/almustafa-hajj && git pull
source ~/venv/bin/activate && pip install -r requirements-web.txt
```
ثم **Reload** من صفحة Web. بياناتك لا تتأثّر (في مجلّد منفصل).

## ملاحظات النسخة المجانية
- **التجديد:** كل ٣ أشهر يطلب PythonAnywhere ضغطة زر «Run until 3 months from
  today» في صفحة Web لإبقاء التطبيق يعمل — مجّاني.
- **الأداء متواضع** ومناسب لمكتب صغير؛ للتوسّع لاحقاً يمكن الترقية أو الانتقال
  لخادم مدفوع بنفس الملفّات.
- التطبيق لا يحتاج إنترنت خارجياً (قيد النسخة المجانية على الاتصالات الصادرة
  لا يؤثّر فيه).
