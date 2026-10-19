import os
import httpx
from datetime import datetime, timezone, date
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

async def save_user(telegram_id: int, username: str, first_name: str, last_name: str, language_code: str):
    if not SUPABASE_URL: return False
    url = f"{SUPABASE_URL}/rest/v1/users?on_conflict=telegram_id"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "telegram_id": telegram_id, "username": username, "first_name": first_name,
        "last_name": last_name, "language_code": language_code, "last_seen_at": now
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=HEADERS, json=data)
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

async def check_quota(telegram_id: int) -> bool:
    """فحص الحصة اليومية لتوفير الباقة المجانية"""
    url = f"{SUPABASE_URL}/rest/v1/quotas?user_id=eq.{telegram_id}"
    try:
        async with httpx.AsyncClient() as client:
            # 1. قراءة الحصة
            res = await client.get(url, headers=HEADERS)
            data = res.json()
            today = date.today().isoformat()
            
            if not data:
                # إنشاء سجل حصة لأول مرة
                new_quota = {"user_id": telegram_id, "requests_used": 1, "last_reset_date": today}
                await client.post(f"{SUPABASE_URL}/rest/v1/quotas", headers=HEADERS, json=new_quota)
                return True
            
            quota = data[0]
            if quota["last_reset_date"] != today:
                # تصفير العداد في يوم جديد
                await client.patch(url, headers=HEADERS, json={"requests_used": 1, "last_reset_date": today})
                return True
                
            if quota["requests_used"] >= quota["daily_limit"]:
                return False # تم استهلاك الحد
                
            # زيادة العداد
            await client.patch(url, headers=HEADERS, json={"requests_used": quota["requests_used"] + 1})
            return True
    except Exception as e:
        print(f"Quota Error: {e}")
        return False

async def save_quiz(telegram_id: int, title: str, mode: str, questions: list):
    """حفظ الاختبار في قاعدة البيانات عند النشر فقط"""
    url = f"{SUPABASE_URL}/rest/v1/quizzes"
    data = {"user_id": telegram_id, "title": title, "mode": mode, "questions": questions}
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=HEADERS, json=data)
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
