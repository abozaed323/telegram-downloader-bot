import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ======================== الإعدادات الأساسية ========================
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ======================== قاعدة البيانات ========================
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))")
conn.commit()

def is_vip(user_id: int) -> bool:
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry = datetime.strptime(row[0], "%Y-%m-%d")
            return expiry >= datetime.now()
        except:
            return False
    return False

def get_daily_downloads(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_downloads(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
        (user_id, today)
    )
    conn.commit()

def can_download(user_id: int) -> bool:
    return is_vip(user_id) or get_daily_downloads(user_id) < 5

# إعلانات بسيطة للمستخدم المجاني
ADS = [
    "📢 اشترك في قناتنا: @YourChannel",
    "⭐ لتحميل غير محدود، اشترك في VIP عبر القائمة",
    "🔥 البوت يدعم تيك توك لايف أيضاً"
]

async def send_ad(user_id: int, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADS))

# ======================== تحميل الفيديو ========================
def detect_platform(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u:
        return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u:
        return "فيسبوك"
    if "twitter.com" in u or "x.com" in u:
        return "تويتر"
    if "youtube.com" in u or "youtu.be" in u:
        return "يوتيوب"
    if "instagram.com" in u:
        return "انستجرام"
    return "غير معروف"

async def download_video(url: str, quality: str = "best") -> str:
    opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "format": "best" if quality == "best" else "worst",
    }
    # دعم خاص للبث المباشر
    if "/live" in url:
        opts["live_from_start"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir(DOWNLOAD_DIR)
            if files:
                filename = os.path.join(DOWNLOAD_DIR, max([os.path.join(DOWNLOAD_DIR, f) for f in files], key=os.path.getctime))
        return filename

# ======================== القائمة الرئيسية (4 أزرار فقط) ========================
async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك / VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================== أمر /start ========================
async def start(update: Update, context):
    user = update.effective_user
    name = user.first_name or "صديقي"
    text = (
        f"🎬 أهلاً بك {name} في بوت التحميل الشامل.\n\n"
        "📥 أرسل رابط فيديو من تيك توك، يوتيوب، فيسبوك، تويتر، انستجرام.\n"
        "📊 المجاني: 5 تحميلات يومياً\n"
        "⭐ الاشتراك VIP يمنحك تحميل غير محدود وبدون إعلانات.\n\n"
        "اختر من القائمة:"
    )
    await update.message.reply_text(text, reply_markup=await main_menu())

# ------------------- زر تحميل فيديو -------------------
async def menu_download(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 أرسل رابط الفيديو الآن.\nلإلغاء العملية، اضغط /start",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
    )

# ------------------- زر استهلاكي -------------------
async def menu_usage(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        text = "⭐ أنت مشترك VIP – لا حدود للتحميل اليومي."
    else:
        used = get_daily_downloads(user_id)
        remain = 5 - used
        text = f"📊 استخدمت اليوم {used} من 5 تحميلات.\nمتبقي: {remain} تحميل.\n\nللحصول على تحميل غير محدود، اشترك في VIP."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

# ------------------- زر الاشتراك / VIP -------------------
async def menu_vip(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
        expiry = c.fetchone()[0]
        text = f"✅ أنت مشترك VIP حتى {expiry}\nشكراً لدعمك!"
    else:
        text = (
            "⭐ **باقات VIP** ⭐\n\n"
            "• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\n"
            "💳 الدفع: فودافون كاش 0123456789، إنستا باي instapay@example.com\n"
            f"📩 بعد الدفع أرسل الإيصال إلى المشرف {ADMIN_USERNAME}\n"
            "🔸 للتجربة: /activate_vip_test\n\n"
            "سيتم تفعيل اشتراكك خلال 24 ساعة."
        )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

# ------------------- زر سياسة الاستخدام -------------------
async def menu_policy(update: Update, context):
    query = update.callback_query
    await query.answer()
    text = (
        "⚖️ **سياسة الاستخدام**\n\n"
        "• المستخدم هو المسؤول الوحيد عن المحتوى الذي يقوم بتحميله.\n"
        "• لا نقوم بتخزين الملفات بعد إرسالها.\n"
        "• حقوق النشر محفوظة لأصحابها.\n"
        f"• للاستفسار أو الشكاوى: {ADMIN_USERNAME}"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

# ------------------- زر الرجوع -------------------
async def back(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("القائمة الرئيسية:", reply_markup=await main_menu())

# ======================== معالج الروابط وجودة التحميل ========================
async def handle_link(update: Update, context):
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً صحيحاً.")
        return
    if not can_download(user_id):
        await update.message.reply_text("⚠️ لقد استنفدت تحميلات اليوم المجانية. اشترك في VIP أو انتظر حتى الغد.")
        return
    # تخزين الرابط مؤقتاً
    context.user_data["url"] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="worst")],
    ]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    quality = query.data  # "best" or "worst"
    url = context.user_data.get("url")
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    if not can_download(user_id):
        await query.edit_message_text("⚠️ تجاوزت الحد اليومي.")
        return
    await query.edit_message_text("⏳ جاري التحميل...")
    try:
        path = await download_video(url, quality)
        with open(path, "rb") as vid:
            await query.message.reply_video(vid, caption="✅ تم التحميل بنجاح!")
        os.remove(path)
        increment_daily_downloads(user_id)
        await send_ad(user_id, context)
    except Exception as e:
        await query.message.reply_text(f"❌ فشل التحميل: {str(e)[:100]}")
    finally:
        context.user_data.pop("url", None)

# ======================== أمر VIP تجريبي ========================
async def test_vip(update: Update, context):
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة.")

# ======================== التشغيل الرئيسي ========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", test_vip))

    # أزرار القائمة الرئيسية
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))

    # معالج الروابط وجودة التحميل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(quality_handler, pattern="^(best|worst)$"))

    logger.info("✅ البوت يعمل الآن مع الأزرار المطلوبة فقط.")
    app.run_polling()

if __name__ == "__main__":
    main()