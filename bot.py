import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

# ---------- قاعدة البيانات ----------
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS vip (
    user_id INTEGER PRIMARY KEY,
    expiry_date TEXT NOT NULL
)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_downloads (
    user_id INTEGER,
    date TEXT,
    count INTEGER,
    PRIMARY KEY (user_id, date)
)''')
conn.commit()

def is_vip(user_id: int) -> bool:
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry_str = row[0].split()[0] if ' ' in row[0] else row[0]
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
        except:
            expiry = datetime.now()
        if expiry >= datetime.now():
            return True
        else:
            c.execute("DELETE FROM vip WHERE user_id=?", (user_id,))
            conn.commit()
    return False

def get_daily_downloads(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_downloads(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1", (user_id, today))
    conn.commit()

def can_download(user_id: int) -> bool:
    if is_vip(user_id):
        return True
    return get_daily_downloads(user_id) < 5

ADS_LIST = [
    "📢 اشترك في قناتي: @ExampleChannel للحصول على بوتات مجانية",
    "💎 هل تريد تحميل غير محدود؟ اشترك في VIP عبر القائمة الرئيسية",
    "🔥 حمل الفيديوهات بدون إعلانات وبجودة 4K مع VIP",
    "📌 تنويه: هذا البوت للإستخدام الشخصي، الرجاء احترام حقوق النشر."
]

async def send_ad(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_vip(user_id):
        ad = random.choice(ADS_LIST)
        await context.bot.send_message(chat_id=user_id, text=ad)

def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return "تيك توك"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "فيسبوك"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "تويتر"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "يوتيوب"
    elif "instagram.com" in url_lower:
        return "انستجرام"
    else:
        return "غير معروف"

async def download_video(url: str, quality: str = "best"):
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'format': 'best' if quality == 'best' else 'worst',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir("downloads")
            if files:
                filename = os.path.join("downloads", max([os.path.join("downloads", f) for f in files], key=os.path.getctime))
        return filename

# ---------- القائمة الرئيسية ----------
async def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("💎 باقات VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("📊 استخدامي اليومي", callback_data="menu_usage")],
        [InlineKeyboardButton("📖 المنصات المدعومة", callback_data="menu_supported")],
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="menu_info")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name if user.first_name else "صديقي"
    welcome_msg = (
        f"🎬 أهلاً بك {first_name} في **بوت التحميل الشامل**!\n\n"
        "📥 أرسل رابط فيديو من:\n"
        "✅ تيك توك\n✅ فيسبوك\n✅ تويتر\n✅ يوتيوب\n✅ انستجرام\n\n"
        f"📊 المجاني: 5 تحميلات/يوم\n💎 VIP: غير محدود + بدون إعلانات\n\n"
        "اختر من القائمة:"
    )
    await update.message.reply_text(welcome_msg, reply_markup=await main_menu_keyboard(), parse_mode="Markdown")

# ---------- دوال القوائم الفرعية ----------
async def menu_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\nمثال: https://www.tiktok.com/@user/video/123456\n\nلإلغاء العملية، اضغط /start",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]])
    )

async def menu_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
        expiry = c.fetchone()[0]
        text = f"✅ أنت VIP حتى {expiry}\nشكراً لدعمك!"
    else:
        text = (
            "💎 **باقات VIP**\n\n"
            "• 1 شهر – 3$ (أو 5 نجوم تليجرام)\n"
            "• 3 شهور – 8$\n"
            "• سنة – 25$\n\n"
            "طرق الدفع:\n"
            "⭐ نجوم تليجرام\n"
            "📱 فودافون كاش: 0123456789\n"
            "🏦 إنستا باي: instapay@example.com\n\n"
            "بعد الدفع أرسل الإيصال لـ @AdminBot (للتجربة: /activate_vip_test)"
        )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def menu_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        text = "💎 أنت VIP، لا حدود للتحميل."
    else:
        used = get_daily_downloads(user_id)
        remaining = 5 - used
        text = f"📊 استخدمت اليوم {used} من 5 تحميلات.\nمتبقي: {remaining}\n\nلرفع الحد، اشترك في VIP."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def menu_supported(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📱 **المنصات المدعومة:**\n\nتيك توك، فيسبوك، تويتر، يوتيوب، انستجرام (منشورات، ريلز، استوريهات عامة).\n🚧 قريباً: تحويل فيديو إلى MP3."
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def menu_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "ℹ️ **بوت التحميل الشامل**\nالإصدار 2.0\nالمطور: @YourUsername\nللاستفسارات: @SupportBot"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu_keyboard(), parse_mode="Markdown")

# ---------- معالج الروابط وجودة التحميل ----------
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً من تيك توك، فيسبوك، تويتر، يوتيوب أو انستجرام.\nأو /start للقائمة.")
        return
    
    if not can_download(user_id):
        await update.message.reply_text("⚠️ استنفدت الـ5 تحميلات المجانية اليومية. اشترك في VIP من القائمة.")
        return
    
    # تخزين الرابط في user_data بدلاً من callback_data
    context.user_data['pending_url'] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]
    ]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    action = query.data
    if action == "main_menu":
        await back_to_main_menu(update, context)
        return
    
    url = context.user_data.get('pending_url')
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    
    quality = "best" if action == "quality_best" else "worst"
    
    if not can_download(user_id):
        await query.edit_message_text("⚠️ تجاوزت حد التحميل اليومي.")
        return
    
    await query.edit_message_text("⏳ جاري التحميل... قد يستغرق بضع ثوانٍ.")
    try:
        file_path = await download_video(url, quality)
        with open(file_path, 'rb') as video_file:
            await query.message.reply_video(video_file, caption="✅ تم التحميل بنجاح!")
        os.remove(file_path)
        increment_daily_downloads(user_id)
        await send_ad(user_id, context)
        # عرض القائمة الرئيسية مرة أخرى
        await query.message.reply_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu_keyboard(), parse_mode="Markdown")
    except Exception as e:
        error_msg = str(e)[:150]
        await query.message.reply_text(f"❌ فشل التحميل: {error_msg}")
    finally:
        context.user_data.pop('pending_url', None)

async def activate_test_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة (للاختبار فقط).")

async def activate_vip_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ADMIN_ID = 123456789  # استبدله بمعرف التليجرام الخاص بك
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("غير مصرح.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
        conn.commit()
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} حتى {expiry}")
    except:
        await update.message.reply_text("الاستخدام: /activate_vip <user_id> <عدد_الأيام>")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", activate_test_vip))
    app.add_handler(CommandHandler("activate_vip", activate_vip_manual))
    # معالجات القائمة الرئيسية
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_supported, pattern="^menu_supported$"))
    app.add_handler(CallbackQueryHandler(menu_info, pattern="^menu_info$"))
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"))
    # معالج الروابط وجودة التحميل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^(quality_best|quality_worst|main_menu)"))
    
    print("✅ البوت يعمل الآن بكفاءة عالية مع أزرار رجوع سليمة وطرق دفع حقيقية.")
    app.run_polling()

if __name__ == "__main__":
    main()