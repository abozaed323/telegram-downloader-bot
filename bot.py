import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

conn = sqlite3.connect('bot_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))''')
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
    "📢 اشترك في قناتنا: @YourChannel\nلأحدث البوتات والتحديثات",
    "💎 هل تريد التحميل بلا حدود؟ اشترك في VIP عبر القائمة",
    "🔥 باقات VIP تبدأ من 1$ فقط أسبوعياً",
    "📌 هذا البوت للإستخدام الشخصي، يرجى احترام حقوق النشر."
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

# ---------- قائمة دائمة أسفل الشات (Reply Keyboard) ----------
async def get_main_reply_keyboard():
    keyboard = [
        [KeyboardButton("📥 تحميل فيديو"), KeyboardButton("⭐ باقات VIP")],
        [KeyboardButton("⚖️ سياسة الاستخدام"), KeyboardButton("📊 استهلاكي اليومي")],
        [KeyboardButton("🌐 المنصات المدعومة"), KeyboardButton("ℹ️ معلومات البوت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------- القائمة inline (للردود المتقدمة) ----------
async def main_menu_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("⭐ باقات VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("📊 استهلاكي اليومي", callback_data="menu_usage")],
        [InlineKeyboardButton("🌐 المنصات المدعومة", callback_data="menu_supported")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="menu_info")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------- دالة start مع القائمة الدائمة ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name if user.first_name else "صديقي"
    welcome_msg = (
        f"🎬 **أهلاً بك {first_name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "✅ تيك توك  |  ✅ فيسبوك  |  ✅ تويتر\n"
        "✅ يوتيوب  |  ✅ انستجرام\n\n"
        "📊 **المجاني:** 5 تحميلات/يوم\n"
        "⭐ **VIP:** غير محدود + بدون إعلانات\n\n"
        "⚠️ **تنبيه:** المستخدم مسؤول عن المحتوى.\n\n"
        "استخدم الأزرار أدناه:"
    )
    # إرسال الصورة + النص + القائمة الدائمة
    photo_url = "https://cdn.pixabay.com/photo/2016/02/19/11/19/video-1210600_1280.png"
    try:
        await update.message.reply_photo(
            photo=photo_url,
            caption=welcome_msg,
            parse_mode="Markdown",
            reply_markup=await get_main_reply_keyboard()
        )
    except:
        await update.message.reply_text(
            welcome_msg,
            parse_mode="Markdown",
            reply_markup=await get_main_reply_keyboard()
        )

# ---------- معالجة الأزرار من القائمة الدائمة (نصوص) ----------
async def handle_reply_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📥 تحميل فيديو":
        await update.message.reply_text(
            "📥 أرسل رابط الفيديو الآن.\nلإلغاء العملية اضغط /start",
            reply_markup=await get_main_reply_keyboard()
        )
    elif text == "⭐ باقات VIP":
        user_id = update.effective_user.id
        if is_vip(user_id):
            c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
            expiry = c.fetchone()[0]
            msg = f"✅ أنت VIP حتى {expiry}"
        else:
            msg = (
                "⭐ **باقات VIP** ⭐\n\n"
                "• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\n"
                "💳 الدفع: فودافون كاش 0123456789، إنستا باي instapay@example.com\n"
                f"📩 بعد الدفع أرسل الإيصال لـ {ADMIN_USERNAME}\n"
                "🔸 للتجربة: /activate_vip_test"
            )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=await get_main_reply_keyboard())
    elif text == "⚖️ سياسة الاستخدام":
        msg = (
            "⚖️ **سياسة الاستخدام**\n\n"
            "1️⃣ المستخدم مسؤول عن المحتوى.\n"
            "2️⃣ لا نُخزّن الملفات.\n"
            "3️⃣ حقوق النشر محفوظة لأصحابها.\n"
            f"📩 للاستفسار: {ADMIN_USERNAME}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=await get_main_reply_keyboard())
    elif text == "📊 استهلاكي اليومي":
        user_id = update.effective_user.id
        if is_vip(user_id):
            msg = "⭐ أنت VIP، لا حدود للتحميل."
        else:
            used = get_daily_downloads(user_id)
            remaining = 5 - used
            msg = f"📊 استخدمت اليوم {used} من 5 تحميلات.\nمتبقي: {remaining}"
        await update.message.reply_text(msg, reply_markup=await get_main_reply_keyboard())
    elif text == "🌐 المنصات المدعومة":
        msg = "🌐 تيك توك، فيسبوك، تويتر، يوتيوب، انستجرام (ريلز، استوريهات عامة)."
        await update.message.reply_text(msg, reply_markup=await get_main_reply_keyboard())
    elif text == "ℹ️ معلومات البوت":
        msg = f"ℹ️ **{BOT_USERNAME}**\nالإصدار 3.0\nالمطور: {ADMIN_USERNAME}\nيعمل 24/7"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=await get_main_reply_keyboard())
    else:
        # إذا كان النص ليس زراً، نتعامل معه كرابط عادي
        await handle_link(update, context)

# ---------- معالج الروابط ----------
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً من تيك توك، فيسبوك، تويتر، يوتيوب أو انستجرام.")
        return
    
    if not can_download(user_id):
        await update.message.reply_text("⚠️ استنفدت الـ5 تحميلات المجانية اليومية. اشترك في VIP.")
        return
    
    context.user_data['pending_url'] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]
    ]
    await update.message.reply_text(f"📌 **المنصة:** {platform}\nاختر جودة التحميل:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    action = query.data
    if action == "main_menu":
        await query.edit_message_text("🏠 القائمة الرئيسية", reply_markup=await main_menu_inline_keyboard())
        return
    
    url = context.user_data.get('pending_url')
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    
    quality = "best" if action == "quality_best" else "worst"
    
    if not can_download(user_id):
        await query.edit_message_text("⚠️ تجاوزت حد التحميل اليومي.")
        return
    
    await query.edit_message_text("⏳ جاري التحميل...")
    try:
        file_path = await download_video(url, quality)
        with open(file_path, 'rb') as video_file:
            await query.message.reply_video(video_file, caption="✅ تم التحميل بنجاح!")
        os.remove(file_path)
        increment_daily_downloads(user_id)
        await send_ad(user_id, context)
    except Exception as e:
        await query.message.reply_text(f"❌ فشل التحميل: {str(e)[:150]}")
    finally:
        context.user_data.pop('pending_url', None)

# ---------- أوامر VIP التجريبية ----------
async def activate_test_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة.")

# ---------- الرئيسية ----------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", activate_test_vip))
    # معالج الأزرار الدائمة (نصوص)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_buttons))
    # معالج الكال بك للجودة والقوائم inline
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^(quality_best|quality_worst|main_menu)"))
    
    print("✅ البوت يعمل مع قائمة دائمة أسفل الشات وكل الأزرار تعمل.")
    app.run_polling()

if __name__ == "__main__":
    main()