import asyncio
import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from app.database import save_user, check_quota, save_quiz
from app.ai_generator import generate_questions
from app.validators import validate_questions

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ─── States (Wizard Flow) ───
(SELECT_MODE, AI_DIFF, AI_COUNT, AI_TOPIC, PREVIEW, DESTINATION,
 MANUAL_TITLE, MANUAL_MENU, MANUAL_Q_TEXT, MANUAL_OPT_LOOP, MANUAL_CORRECT) = range(11)

# ─── Menus ───
MAIN_MENU = [
    ["/create_quiz", "/quizzes"],
    ["/cancel", "/help"],
    ["/ask", "/import"]
]

# ═══════════════════════════════════════════
# 1. الأوامر الأساسية (مطابقة للصورة الأولى)
# ═══════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user.id, user.username, user.first_name, user.last_name, user.language_code)
    await update.message.reply_text(
        "مرحباً بك في **رفيق المعلم الذكي نهج**.\n"
        "استخدم الأوامر أو الأزرار في الأسفل للبدء:",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True),
        parse_mode="Markdown"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية والعودة للقائمة الرئيسية.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
    return ConversationHandler.END

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("هذا البوت يساعدك على إنشاء اختبارات تفاعلية بسهولة. استخدم /create_quiz للبدء.")

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("المساعد الذكي قيد التطوير. يرجى استخدام /create_quiz.")

async def import_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("استيراد من QuizBot غير مدعوم حالياً. يرجى الإنشاء المباشر.")

async def my_quizzes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لا توجد اختبارات محفوظة حالياً (قيد التطوير).")

# ═══════════════════════════════════════════
# 2. Wizard Flow (تدفق الإنشاء)
# ═══════════════════════════════════════════
async def create_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🤖 ذكاء اصطناعي (AI)", callback_data="mode_ai")],
          [InlineKeyboardButton("✍️ إنشاء يدوي", callback_data="mode_manual")]]
    await update.message.reply_text(
        "**اختر طريقة الإنشاء:**", 
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    return SELECT_MODE

async def select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "mode_ai":
        if not await check_quota(update.effective_user.id):
            await query.edit_message_text("❌ لقد وصلت للحد الأقصى اليومي. يرجى المحاولة غداً.")
            return ConversationHandler.END
            
        kb = [["سهل", "متوسط", "صعب"]]
        await query.edit_message_text("اختر مستوى الصعوبة:", reply_markup=InlineKeyboardMarkup([ [InlineKeyboardButton(d, callback_data=f"diff_{d}") for d in ["سهل", "متوسط", "صعب"]] ]))
        return AI_DIFF
        
    elif query.data == "mode_manual":
        await query.edit_message_text("أرسل **اسم الاختبار** (مثال: مراجعة الوحدة الأولى):", parse_mode="Markdown")
        return MANUAL_TITLE

# --- مسار الذكاء الاصطناعي (AI Mode) ---
async def ai_diff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["diff"] = query.data.split("_")[1]
    await query.edit_message_text("كم عدد الأسئلة؟ (أرسل رقماً من 1 إلى 20):")
    return AI_COUNT

async def ai_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text)
        if not (1 <= count <= 20): raise ValueError
        context.user_data["count"] = count
        await update.message.reply_text("أرسل **موضوع الاختبار** (أو أرفق ملف PDF/DOCX):")
        return AI_TOPIC
    except:
        await update.message.reply_text("أدخل رقماً صحيحاً بين 1 و 20.")
        return AI_COUNT

async def ai_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ملاحظة: استخراج الملفات يتم هنا إذا أرسل المستند
    topic_text = update.message.text or update.message.document.file_name
    msg = await update.message.reply_text("⏳ جاري توليد الأسئلة...")
    
    questions = await generate_questions(topic_text, context.user_data["count"], context.user_data["diff"])
    
    # Quality Gate
    is_valid, error_msg = validate_questions(questions)
    if not is_valid:
        await msg.edit_text(f"❌ فشل الفحص: {error_msg}")
        return ConversationHandler.END
        
    context.user_data['temp_questions'] = questions
    context.user_data['quiz_title'] = topic_text
    
    await msg.edit_text(f"✅ تم توليد {len(questions)} أسئلة بنجاح.\nأين تريد إرسال الاختبار؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 إرسال هنا", callback_data="dest_here")],
            [InlineKeyboardButton("📢 إرسال لقناة/مجموعة", callback_data="dest_channel")]
        ])
    )
    return DESTINATION

# --- مسار الإنشاء اليدوي (Manual Mode) ---
async def manual_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quiz_title'] = update.message.text
    context.user_data['temp_questions'] = []
    
    await update.message.reply_text(
        f"✅ تم إنشاء الاختبار: **{update.message.text}**\nماذا تريد أن تفعل؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة سؤال", callback_data="add_q")],
            [InlineKeyboardButton("🚀 نشر الاختبار", callback_data="publish")]
        ]), parse_mode="Markdown"
    )
    return MANUAL_MENU

async def manual_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_q":
        await query.edit_message_text("أرسل **نص السؤال**:", parse_mode="Markdown")
        return MANUAL_Q_TEXT
    elif query.data == "publish":
        questions = context.user_data['temp_questions']
        if not questions:
            await query.edit_message_text("لا يمكن النشر بدون أسئلة!")
            return MANUAL_MENU
            
        await query.edit_message_text("أين تريد إرسال الاختبار؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 إرسال هنا", callback_data="dest_here")],
                [InlineKeyboardButton("📢 إرسال لقناة/مجموعة", callback_data="dest_channel")]
            ])
        )
        return DESTINATION

async def manual_q_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_q'] = update.message.text
    context.user_data['current_opts'] = []
    
    await update.message.reply_text(
        f"السؤال: {update.message.text}\nالخيارات الحالية: (فارغ)\n\nأضف الخيارات:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة خيار", callback_data="add_opt")],
            [InlineKeyboardButton("✅ حفظ السؤال", callback_data="save_q")]
        ])
    )
    return MANUAL_OPT_LOOP

async def manual_opt_loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_opt":
        await query.message.reply_text("أرسل نص الخيار:")
        return "WAIT_FOR_OPT_TEXT"
    elif query.data == "save_q":
        opts = context.user_data['current_opts']
        if len(opts) < 2:
            await query.message.reply_text("أضف خيارين على الأقل أولاً.")
            return MANUAL_OPT_LOOP
            
        kb = [[InlineKeyboardButton(f"{i+1}. {opt}", callback_data=f"corr_{i}")] for i, opt in enumerate(opts)]
        await query.edit_message_text("اختر الإجابة الصحيحة بالضغط على الزر:", reply_markup=InlineKeyboardMarkup(kb))
        return MANUAL_CORRECT

async def manual_receive_opt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_opts'].append(update.message.text)
    opts = context.user_data['current_opts']
    
    await update.message.reply_text(
        f"الخيارات الحالية:\n" + "\n".join([f"- {o}" for o in opts]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة خيار", callback_data="add_opt")],
            [InlineKeyboardButton("✅ حفظ السؤال", callback_data="save_q")]
        ])
    )
    return MANUAL_OPT_LOOP

async def manual_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    correct_idx = int(query.data.split("_")[1])
    q_data = {
        "question": context.user_data['current_q'],
        "options": context.user_data['current_opts'],
        "correct_index": correct_idx
    }
    context.user_data['temp_questions'].append(q_data)
    
    await query.edit_message_text(
        f"✅ تم حفظ السؤال. لديك {len(context.user_data['temp_questions'])} سؤال.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة سؤال آخر", callback_data="add_q")],
            [InlineKeyboardButton("🚀 نشر الاختبار", callback_data="publish")]
        ])
    )
    return MANUAL_MENU

# ═══════════════════════════════════════════
# 3. اختيار الوجهة والنشر (Destination)
# ═══════════════════════════════════════════
async def destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "dest_here":
        await publish_quiz(query.message.chat_id, context, query)
        return ConversationHandler.END
    elif query.data == "dest_channel":
        await query.edit_message_text("أرسل معرف القناة (مثال: @my_channel) أو ID المجموعة:")
        return "WAIT_FOR_CHANNEL_ID"

async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.text
    await publish_quiz(chat_id, context, update.message)
    return ConversationHandler.END

async def publish_quiz(chat_id, context, msg_obj):
    questions = context.user_data['temp_questions']
    title = context.user_data['quiz_title']
    
    await msg_obj.reply_text("⏳ جاري النشر...")
    
    success_count = 0
    for q in questions:
        try:
            await context.bot.send_poll(
                chat_id=chat_id, question=q["question"],
                options=q["options"], type="quiz", correct_option_id=q["correct_index"], is_anonymous=False
            )
            success_count += 1
        except Exception as e:
            await msg_obj.reply_text(f"❌ فشل إرسال سؤال: {e}")
            break
            
    if success_count == len(questions):
        await save_quiz(update.effective_user.id, title, "wizard", questions)
        await msg_obj.reply_text("🎉 تم نشر الاختبار بنجاح!", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))
    else:
        await msg_obj.reply_text("حدثت بعض الأخطاء أثناء النشر.", reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True))

# ═══════════════════════════════════════════
# التشغيل الرئيسي
# ═══════════════════════════════════════════
async def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create_quiz", create_quiz)],
        states={
            SELECT_MODE: [CallbackQueryHandler(select_mode, pattern="^mode_")],
            
            # AI Flow
            AI_DIFF: [CallbackQueryHandler(ai_diff, pattern="^diff_")],
            AI_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_count)],
            AI_TOPIC: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, ai_topic)],
            
            # Manual Flow
            MANUAL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_title)],
            MANUAL_MENU: [CallbackQueryHandler(manual_menu, pattern="^(add_q|publish)$")],
            MANUAL_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_q_text)],
            MANUAL_OPT_LOOP: [CallbackQueryHandler(manual_opt_loop, pattern="^(add_opt|save_q)$")],
            "WAIT_FOR_OPT_TEXT": [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_receive_opt)],
            MANUAL_CORRECT: [CallbackQueryHandler(manual_correct, pattern="^corr_")],
            
            # Destination
            DESTINATION: [CallbackQueryHandler(destination, pattern="^dest_")],
            "WAIT_FOR_CHANNEL_ID": [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("import", import_cmd))
    app.add_handler(CommandHandler("quizzes", my_quizzes))
    app.add_handler(conv_handler)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("✅ البوت يعمل الآن بنظام Wizard Flow الاحترافي المطابق للصور والـ PDF.")
    
    try:
        while True: await asyncio.sleep(3600)
    except asyncio.CancelledError: pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
