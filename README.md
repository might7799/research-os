# Research OS v1.3

نظام ويب عربي للبحث الأكاديمي يجمع نتائج البحث من OpenAlex وSemantic Scholar وCrossref، ثم يزيل التكرار ويعرض النتائج في واجهة بسيطة ومباشرة.

## المميزات
- FastAPI كخادم API
- بحث متوازٍ عبر عدة مصادر أكاديمية
- إزالة التكرار تلقائيًا
- واجهة عربية مبسطة
- جاهز لـ Docker و Render

## التشغيل محلي
```bash
cp .env.example .env
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
export APP_ENV=development
export DATABASE_URL="sqlite:///$PWD/backend/data/research_os.db"
export JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export PYTHONPATH="$PWD/backend"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
افتح المتصفح على:
`http://127.0.0.1:8000`

## تشغيل الواجهة الأمامية
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```
افتح:
`http://localhost:5173`

## إعدادات البيئة
```env
APP_ENV=development
DATABASE_URL=sqlite:////workspaces/research-os/backend/data/research_os.db
JWT_SECRET=<generate-a-random-key-of-at-least-32-bytes>
JWT_ALGORITHM=HS256
```
يُستخدم SQLite للتطوير والاختبارات المعزولة فقط. في الإنتاج، اضبط `APP_ENV=production` ووفّر `DATABASE_URL` لـ PostgreSQL و`JWT_SECRET` قويًا من متغيرات بيئة المنصة. يتوقف التطبيق عند غياب الإعدادات أو فشل الاتصال، ولا ينفّذ تغييرات المخطط تلقائيًا.

لـ PostgreSQL استخدم قيمة مثل:
```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```
طبّق ملفات `backend/migrations/` يدويًا بعد مراجعتها، ولا تستخدم بيانات اتصال الإنتاج في الاختبارات.

## التحقق السريع
```bash
pytest backend/tests -q
```
تُشغّل الاختبارات على قاعدة SQLite مؤقتة منفصلة، ولا تستخدم قاعدة التطبيق المحلية أو الإنتاجية.

## تشغيل Docker
```bash
docker build -t research-os .
docker run -p 8000:8000 research-os
```

## النشر على Render
- ارفع المشروع إلى GitHub
- أنشئ Web Service جديد
- استخدم Dockerfile الموجود
- ثم قم بربطه بالنشر التلقائي أو التشغيل اليدوي

## نقاط النهاية
- `GET /` — الصفحة الرئيسية
- `GET /api/health` — فحص الخدمة
- `GET /api/search?q=AI` — البحث الأكاديمي
