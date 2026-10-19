
import asyncio
from app.database import save_user

async def test():
    print("جاري اختبار الاتصال...")
    result = await save_user(
        telegram_id=999999,
        username="test_user",
        first_name="Test",
        last_name="User",
        language_code="ar"
    )
    print(f"النتيجة: {result}")

asyncio.run(test())
x

