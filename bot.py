import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

# ---------- قاعدة البيانات ----------
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))''')
conn.commit()

def is_vip(user_id: int) -> bool:
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        expiry_str = row[0].split()[0]
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
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
    "📢 اشترك في قناتنا: @YourChannel",
    "💎 هل تريد التحميل بلا حدود؟ اشترك في VIP",
    "🔥 باقات VIP تبدأ من 1$ أسبوعياً"
]

async def send_ad(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_vip(user_id):
        ad = random.choice(ADS_LIST)
        await context.bot.send_message(chat_id=user_id, text=ad)

def detect_platform(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u: return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u: return "فيسبوك"
    if "twitter.com" in u or "x.com" in u: return "تويتر"
    if "youtube.com" in u or "youtu.be" in u: return "يوتيوب"
    if "instagram.com" in u: return "انستجرام"
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

# ---------- قائمة دائمة أنيقة ----------
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📥 تحميل فيديو"), KeyboardButton("⭐ باقات VIP")],
        [KeyboardButton("📊 استهلاكي اليومي"), KeyboardButton("🌐 المنصات")],
        [KeyboardButton("⚖️ سياسة الاستخدام"), KeyboardButton("ℹ️ معلومات البوت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name or "صديقي"
    welcome = f"🎬 أهلاً بك {first_name} في بوت التحميل الشامل!\n\n📥 أرسل رابط فيديو من تيك توك، فيسبوك، تويتر، يوتيوب، انستجرام.\n📊 المجاني: 5 تحميلات/يوم\n⭐ VIP: غير محدود + بدون إعلانات\n\n⚠️ المستخدم مسؤول عن المحتوى."
    await update.message.reply_text(welcome, reply_markup=get_main_keyboard())

# ---------- معالج الأزرار (يتم التعرف على النصوص المطابقة) ----------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📥 تحميل فيديو":
        await update.message.reply_text("أرسل رابط الفيديو الآن.", reply_markup=get_main_keyboard())

    elif text == "⭐ باقات VIP":
        if is_vip(user_id):
            c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
            expiry = c.fetchone()[0]
            msg = f"✅ أنت مشترك VIP حتى {expiry}"
        else:
            msg = (
                "⭐ **باقات VIP** ⭐\n\n"
                "• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\n"
                "💳 الدفع: فودافون كاش 0123456789، إنستا باي instapay@example.com\n"
                f"📩 بعد الدفع أرسل الإيصال لـ {ADMIN_USERNAME}\n"
                "🔸 للتجربة: /activate_vip_test"
            )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif text == "📊 استهلاكي اليومي":
        if is_vip(user_id):
            msg = "⭐ أنت مشترك VIP – لا حدود للتحميل."
        else:
            used = get_daily_downloads(user_id)
            remaining = 5 - used
            msg = f"📊 استخدمت اليوم {used} من 5 تحميلات.\nمتبقي: {remaining}"
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())

    elif text == "🌐 المنصات":
        msg = "🌐 المنصات المدعومة:\n✅ تيك توك\n✅ فيسبوك\n✅ تويتر\n✅ يوتيوب\n✅ انستجرام (منشورات، ريلز، استوريهات عامة)"
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())

    elif text == "⚖️ سياسة الاستخدام":
        msg = (
            "⚖️ **سياسة الاستخدام** ⚖️\n\n"
            "• المستخدم مسؤول وحيد عن المحتوى.\n"
            "• لا يتم تخزين الملفات بعد إرسالها.\n"
            "• حقوق النشر محفوظة لأصحابها.\n"
            f"• للاستفسار: {ADMIN_USERNAME}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif text == "ℹ️ معلومات البوت":
        msg = f"ℹ️ **معلومات البوت**\n\nالاسم: {BOT_USERNAME}\nالإصدار: 3.0\nالمطور: {ADMIN_USERNAME}\nيعمل 24/7"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ---------- معالج الروابط (لأي نص ليس من الأزرار) ----------
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)

    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً من تيك توك، فيسبوك، تويتر، يوتيوب أو انستجرام.", reply_markup=get_main_keyboard())
        return

    if not can_download(user_id):
        await update.message.reply_text("⚠️ استنفدت الـ5 تحميلات اليومية. اشترك في VIP.", reply_markup=get_main_keyboard())
        return

    context.user_data['pending_url'] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")]
    ]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر جودة التحميل:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ تم الإلغاء.", reply_markup=None)
        return

    url = context.user_data.get('pending_url')
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return

    quality = "best" if query.data == "best" else "worst"
    if not can_download(user_id):
        await query.edit_message_text("⚠️ تجاوزت حد التحميل اليومي.")
        return

    await query.edit_message_text("⏳ جاري التحميل...")
    try:
        file_path = await download_video(url, quality)
        with open(file_path, 'rb') as video:
            await query.message.reply_video(video, caption="✅ تم التحميل بنجاح!")
        os.remove(file_path)
        increment_daily_downloads(user_id)
        await send_ad(user_id, context)
    except Exception as e:
        await query.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        context.user_data.pop('pending_url', None)

async def activate_test_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", activate_test_vip))
    # أولاً: معالج الأزرار (نصوص محددة)
    app.add_handler(MessageHandler(filters.Regex('^(📥 تحميل فيديو|⭐ باقات VIP|📊 استهلاكي اليومي|🌐 المنصات|⚖️ سياسة الاستخدام|ℹ️ معلومات البوت)$'), handle_buttons))
    # ثانياً: معالج الروابط (أي نص آخر)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    # معالج الاستجابة لجودة التحميل
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^(best|worst|cancel)$"))

    print("✅ البوت يعمل مع قائمة أسفل الشات وكل الأزرار تعمل.")
    app.run_polling()

if __name__ == "__main__":
    main()