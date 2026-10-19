import re

def validate_questions(questions: list) -> tuple[bool, str]:
    """بوابة الجودة: فحص الأسئلة قبل الإرسال"""
    if not questions:
        return False, "لم يتم توليد أي أسئلة."
        
    for idx, q in enumerate(questions, 1):
        # 1. فحص النص
        if not q.get("question") or not str(q["question"]).strip():
            return False, f"السؤال رقم {idx} فارغ."
            
        # 2. فحص الخيارات
        options = q.get("options", [])
        if len(options) < 2 or len(options) > 10:
            return False, f"السؤال رقم {idx} يجب أن يحتوي على 2 إلى 10 خيارات."
            
        # 3. إزالة التكرار في الخيارات
        clean_options = list(dict.fromkeys([str(o).strip() for o in options]))
        if len(clean_options) != len(options):
            q["options"] = clean_options # تصحيح تلقائي
            options = clean_options
            
        # 4. فحص مؤشر الإجابة الصحيحة
        correct_idx = q.get("correct_index")
        if correct_idx is None or not (0 <= correct_idx < len(options)):
            return False, f"الإجابة الصحيحة للسؤال رقم {idx} غير صالحة."
            
        # 5. حدود الطول (تجنب مشاكل العرض في تليجرام)
        if len(q["question"]) > 300:
            return False, f"نص السؤال رقم {idx} طويل جداً."
        for opt in options:
            if len(opt) > 100:
                return False, f"أحد خيارات السؤال رقم {idx} طويل جداً."
                
    return True, "OK"
