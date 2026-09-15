# Research OS v1.2

نسخة ويب قابلة للتشغيل: واجهة عربية + FastAPI + بحث متوازٍ من OpenAlex وSemantic Scholar وCrossref + إزالة تكرار + Docker/Render.

## تشغيل محلي
```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
افتح: `http://127.0.0.1:8000`

## تشغيل Docker
```bash
docker build -t research-os .
docker run -p 8000:8000 research-os
```

## النشر
ارفع المجلد إلى GitHub ثم أنشئ Web Service في Render باستخدام Dockerfile الموجود. بعد النشر يصبح لديك رابط HTTPS عام.
