import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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

def is_vip(user_id):
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

def get_daily_downloads(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_downloads(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1", (user_id, today))
    conn.commit()

def can_download(user_id):
    if is_vip(user_id):
        return True
    return get_daily_downloads(user_id) < 5

# ---------- إعلانات ----------
ADS = ["📢 اشترك في قناتنا @YourChannel", "💎 باقات VIP تبدأ من 1$", "🔥 تحميل غير محدود مع VIP"]

async def send_ad(user_id, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADS))

# ---------- تحميل الفيديو ----------
def detect_platform(url):
    u = url.lower()
    if "tiktok.com" in u: return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u: return "فيسبوك"
    if "twitter.com" in u or "x.com" in u: return "تويتر"
    if "youtube.com" in u or "youtu.be" in u: return "يوتيوب"
    if "instagram.com" in u: return "انستجرام"
    return "غير معروف"

async def download_video(url, quality="best"):
    opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'format': 'best' if quality == 'best' else 'worst',
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir("downloads")
            if files:
                filename = os.path.join("downloads", max([os.path.join("downloads", f) for f in files], key=os.path.getctime))
        return filename

# ---------- القائمة الدائمة أسفل الشاشة (الأزرار الثابتة) ----------
def reply_keyboard():
    keyboard = [
        [KeyboardButton("📥 تحميل فيديو"), KeyboardButton("⭐ باقات VIP")],
        [KeyboardButton("📊 استهلاكي"), KeyboardButton("🌐 المنصات")],
        [KeyboardButton("⚖️ سياسة"), KeyboardButton("ℹ️ معلومات")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------- أمر /start ----------
async def start(update, context):
    user = update.effective_user
    name = user.first_name or "صديقي"
    msg = f"🎬 أهلاً {name} في بوت التحميل الشامل!\n\n📥 أرسل رابط فيديو من تيك توك، فيسبوك، تويتر، يوتيوب، انستجرام.\n📊 المجاني: 5 تحميلات/يوم\n⭐ VIP: غير محدود\n\n⚠️ أنت المسؤول عن المحتوى."
    await update.message.reply_text(msg, reply_markup=reply_keyboard())

# ---------- معالج الأزرار الدائمة ----------
async def handle_buttons(update, context):
    text = update.message.text
    uid = update.effective_user.id

    if text == "📥 تحميل فيديو":
        await update.message.reply_text("أرسل رابط الفيديو.", reply_markup=reply_keyboard())

    elif text == "⭐ باقات VIP":
        if is_vip(uid):
            c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
            exp = c.fetchone()[0]
            await update.message.reply_text(f"✅ أنت VIP حتى {exp}", reply_markup=reply_keyboard())
        else:
            await update.message.reply_text(
                "⭐ **باقات VIP** ⭐\n\n• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\n"
                f"💰 الدفع: فودافون كاش 0123456789 أو إنستا باي instapay@example.com\n"
                f"📩 بعد الدفع أرسل الإيصال لـ {ADMIN_USERNAME}\n🔸 تجربة: /activate_vip_test",
                parse_mode="Markdown", reply_markup=reply_keyboard()
            )

    elif text == "📊 استهلاكي":
        if is_vip(uid):
            await update.message.reply_text("⭐ لا حدود للتحميل (VIP).", reply_markup=reply_keyboard())
        else:
            used = get_daily_downloads(uid)
            rem = 5 - used
            await update.message.reply_text(f"📊 اليوم: {used}/5 تحميلات\nمتبقي: {rem}", reply_markup=reply_keyboard())

    elif text == "🌐 المنصات":
        await update.message.reply_text(
            "🌐 المدعومة:\n✅ تيك توك\n✅ فيسبوك\n✅ تويتر\n✅ يوتيوب\n✅ انستجرام (ريلز، استوريهات عامة)",
            reply_markup=reply_keyboard()
        )

    elif text == "⚖️ سياسة":
        await update.message.reply_text(
            "⚖️ **سياسة الاستخدام**\n\n• أنت المسؤول الوحيد عن المحتوى.\n• لا نخزّن الملفات بعد الإرسال.\n• حقوق النشر محفوظة لأصحابها.\n"
            f"📩 للشكاوى: {ADMIN_USERNAME}",
            parse_mode="Markdown", reply_markup=reply_keyboard()
        )

    elif text == "ℹ️ معلومات":
        await update.message.reply_text(
            f"ℹ️ **{BOT_USERNAME}**\nالإصدار 3.0\nالمطور: {ADMIN_USERNAME}\nيعمل 24/7",
            parse_mode="Markdown", reply_markup=reply_keyboard()
        )

# ---------- استقبال الروابط العادية (لتحميل الفيديو) ----------
async def handle_link(update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)

    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً صحيحاً.", reply_markup=reply_keyboard())
        return

    if not can_download(uid):
        await update.message.reply_text("⚠️ انتهت تحميلات اليوم المجانية. اشترك في VIP.", reply_markup=reply_keyboard())
        return

    context.user_data['pending_url'] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")]
    ]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality(update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "cancel":
        await query.edit_message_text("❌ تم الإلغاء.")
        return

    url = context.user_data.get('pending_url')
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مجدداً.")
        return

    quality_type = "best" if query.data == "best" else "worst"
    if not can_download(uid):
        await query.edit_message_text("⚠️ تجاوزت حد التحميل.")
        return

    await query.edit_message_text("⏳ جاري التحميل...")
    try:
        path = await download_video(url, quality_type)
        with open(path, 'rb') as vid:
            await query.message.reply_video(vid, caption="✅ تم بنجاح!")
        os.remove(path)
        increment_daily_downloads(uid)
        await send_ad(uid, context)
    except Exception as e:
        await query.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        context.user_data.pop('pending_url', None)

async def test_vip(update, context):
    uid = update.effective_user.id
    exp = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (uid, exp))
    conn.commit()
    await update.message.reply_text("✅ VIP تجريبي لمدة ساعة (للاختبار).")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", test_vip))
    app.add_handler(MessageHandler(filters.Regex('^(📥 تحميل فيديو|⭐ باقات VIP|📊 استهلاكي|🌐 المنصات|⚖️ سياسة|ℹ️ معلومات)$'), handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(quality, pattern="^(best|worst|cancel)$"))
    print("✅ البوت يعمل مع قائمة أسفل الأزرار وجميع الوظائف.")
    app.run_polling()

if __name__ == "__main__":
    main()