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
DATABASE_URL=sqlite:////workspaces/research-os/backend/data/research_os.db
JWT_SECRET=change-me-to-a-long-random-string
JWT_ALGORITHM=HS256
```
لـ PostgreSQL استخدم قيمة مثل:
```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

## التحقق السريع
```bash
pytest backend/tests -q
```

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
