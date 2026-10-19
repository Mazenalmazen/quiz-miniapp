import os
import json
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

async def generate_questions(topic: str, num_questions: int, difficulty: str):
    if not GROQ_API_KEY:
        print("❌ خطأ: مفتاح Groq غير موجود في .env")
        return []

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    أنت خبير تربوي. قم بإنشاء {num_questions} أسئلة اختيار من متعدد (MCQ) حول الموضوع التالي: "{topic}".
    مستوى الصعوبة: {difficulty}.
    
    يجب أن يكون الرد عبارة عن JSON فقط.
    التنسيق:
    {{
      "questions": [
        {{
          "question": "نص السؤال",
          "options": ["خيار 1", "خيار 2", "خيار 3", "خيار 4"],
          "correct_index": 0
        }}
      ]
    }}
    """

    payload = {
        "model": "openai/gpt-oss-120b", 
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    try:
        # زيادة وقت الانتظار وإضافة محاولات إعادة
        transport = httpx.AsyncHTTPTransport(retries=3)
        async with httpx.AsyncClient(timeout=120.0, transport=transport) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                print(f"❌ خطأ من Groq: {response.text}")
                return []

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # تنظيف الرد من أي علامات Markdown
            content = re.sub(r'```(?:json)?', '', content).strip()
            content = content.strip('` \n')
            
            parsed_data = json.loads(content)
            return parsed_data.get("questions", [])
            
    except httpx.ReadTimeout:
        print("❌ خطأ: انتهت مهلة الاتصال. النموذج 120b يحتاج إنترنت قوي. جرب نموذج openai/gpt-oss-20b إذا تكرر الخطأ.")
        return []
    except json.JSONDecodeError:
        print(f"❌ خطأ: الذكاء الاصطناعي لم يرسل JSON صالح. الرد كان:\n{content}")
        return []
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
        return []
