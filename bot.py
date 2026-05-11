```python
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

# ======================== التهيئة الأساسية ========================
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
DB_PATH = "bot_data.db"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS vip (
    user_id INTEGER PRIMARY KEY,
    expiry_date TEXT NOT NULL
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS daily_downloads (
    user_id INTEGER,
    date TEXT,
    count INTEGER,
    PRIMARY KEY (user_id, date)
)
""")

conn.commit()

# ======================== وظائف VIP ========================
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

    c.execute(
        "SELECT count FROM daily_downloads WHERE user_id=? AND date=?",
        (user_id, today)
    )

    row = c.fetchone()

    return row[0] if row else 0


def increment_daily_downloads(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")

    c.execute(
        """
        INSERT INTO daily_downloads (user_id, date, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date)
        DO UPDATE SET count = count + 1
        """,
        (user_id, today)
    )

    conn.commit()


def can_download(user_id: int) -> bool:
    if is_vip(user_id):
        return True

    return get_daily_downloads(user_id) < 5


# ======================== الإعلانات ========================
ADVERTISEMENTS = [
    "📢 اشترك في قناتنا للحصول على أحدث البوتات.",
    "⭐ اشترك VIP لتحميل غير محدود.",
    "🚀 البوت يدعم الآن تيك توك لايف."
]


async def send_ad_to_free_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_vip(user_id):
        ad = random.choice(ADVERTISEMENTS)

        await context.bot.send_message(
            chat_id=user_id,
            text=ad
        )


# ======================== التعرف على المنصة ========================
def detect_platform(url: str) -> str:
    url_lower = url.lower()

    if "tiktok.com" in url_lower:
        if "/live" in url_lower:
            return "تيك توك لايف"
        return "تيك توك"

    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "فيسبوك"

    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "تويتر"

    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "يوتيوب"

    if "instagram.com" in url_lower:
        return "انستجرام"

    return "غير معروف"


# ======================== تحميل الفيديو ========================
async def download_video(url: str, quality: str = "best") -> str:

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "format": "best" if quality == "best" else "worst",
        "noplaylist": True,
    }

    if "/live" in url:
        ydl_opts["format"] = "best"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            files = os.listdir(DOWNLOAD_DIR)

            if files:
                filename = os.path.join(
                    DOWNLOAD_DIR,
                    max(
                        [os.path.join(DOWNLOAD_DIR, f) for f in files],
                        key=os.path.getctime,
                    ),
                )

        return filename


# ======================== القائمة الرئيسية ========================
async def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="main_download")],
        [
            InlineKeyboardButton("⭐ VIP", callback_data="main_vip"),
            InlineKeyboardButton("📊 استهلاكي", callback_data="main_usage")
        ],
        [
            InlineKeyboardButton("🌐 المنصات", callback_data="main_supported"),
            InlineKeyboardButton("⚖️ السياسة", callback_data="main_policy")
        ],
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="main_info")]
    ]

    return InlineKeyboardMarkup(keyboard)


# ======================== START ========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    welcome_text = (
        f"🎬 أهلاً {user.first_name} في بوت التحميل الشامل\n\n"
        "📥 أرسل أي رابط فيديو وسيتم تحميله فوراً.\n\n"
        "✅ تيك توك\n"
        "✅ تيك توك لايف\n"
        "✅ يوتيوب\n"
        "✅ تويتر\n"
        "✅ فيسبوك\n"
        "✅ انستجرام\n\n"
        "⭐ المجاني: 5 تحميلات يومياً"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=await get_main_menu()
    )


# ======================== معلومات البوت ========================
async def main_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    text = (
        "ℹ️ **معلومات البوت** ℹ️\n\n"
        f"🤖 الاسم: @{BOT_USERNAME}\n"
        "⚡ الإصدار: 3.5.0 Pro\n"
        f"👨‍💻 المطور: {ADMIN_USERNAME}\n"
        "🐍 البرمجة: Python + python-telegram-bot\n"
        "☁️ الاستضافة: Railway 24/7\n"
        "📥 يدعم تحميل:\n"
        "• تيك توك\n"
        "• تيك توك لايف\n"
        "• يوتيوب\n"
        "• تويتر / X\n"
        "• فيسبوك\n"
        "• انستجرام\n\n"
        "⭐ VIP = تحميل غير محدود + بدون إعلانات"
    )

    await query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
        ])
    )


# ======================== المنصات ========================
async def main_supported_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    text = (
        "🌐 **المنصات المدعومة بالكامل** 🌐\n\n"
        "• تيك توك\n"
        "• تيك توك لايف\n"
        "• فيسبوك\n"
        "• تويتر / X\n"
        "• يوتيوب\n"
        "• انستجرام\n"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
        ])
    )


# ======================== VIP ========================
async def main_vip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    text = (
        "⭐ VIP\n\n"
        "• تحميل غير محدود\n"
        "• بدون إعلانات\n"
        "• سرعة أعلى\n\n"
        f"للتفعيل تواصل مع {ADMIN_USERNAME}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
        ])
    )


# ======================== الاستخدام ========================
async def main_usage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if is_vip(user_id):
        text = "⭐ أنت مشترك VIP بدون حدود."
    else:
        used = get_daily_downloads(user_id)

        text = f"📊 استخدمت {used}/5 تحميلات اليوم."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
        ])
    )


# ======================== السياسة ========================
async def main_policy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    text = (
        "⚖️ استخدم البوت بشكل قانوني.\n"
        "المستخدم مسؤول عن أي محتوى يقوم بتحميله."
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
        ])
    )


# ======================== الرجوع ========================
async def main_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        "🏠 القائمة الرئيسية",
        reply_markup=await get_main_menu()
    )


# ======================== تحميل الفيديو ========================
async def handle_any_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    url = update.message.text.strip()

    platform = detect_platform(url)

    if platform == "غير معروف":
        await update.message.reply_text("❌ الرابط غير مدعوم.")
        return

    if not can_download(user_id):
        await update.message.reply_text("⚠️ وصلت للحد اليومي.")
        return

    quality_keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data=f"download_best|{url}")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data=f"download_worst|{url}")]
    ]

    await update.message.reply_text(
        f"📌 المنصة: {platform}\nاختر الجودة:",
        reply_markup=InlineKeyboardMarkup(quality_keyboard)
    )


# ======================== اختيار الجودة ========================
async def quality_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    data = query.data.split("|")

    quality = data[0].replace("download_", "")
    url = data[1]

    await query.edit_message_text("⏳ جاري التحميل...")

    try:
        file_path = await download_video(url, quality)

        with open(file_path, "rb") as video:

            await query.message.reply_video(
                video=video,
                caption="✅ تم التحميل بنجاح"
            )

        os.remove(file_path)

        increment_daily_downloads(query.from_user.id)

        await send_ad_to_free_user(query.from_user.id, context)

    except Exception as e:

        logger.error(e)

        await query.message.reply_text(
            f"❌ فشل التحميل:\n{str(e)}"
        )


# ======================== تشغيل البوت ========================
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))

    app.add_handler(
        CallbackQueryHandler(
            main_info_callback,
            pattern="^main_info$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            main_supported_callback,
            pattern="^main_supported$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            main_vip_callback,
            pattern="^main_vip$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            main_usage_callback,
            pattern="^main_usage$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            main_policy_callback,
            pattern="^main_policy$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            main_back_callback,
            pattern="^main_back$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            quality_selection_callback,
            pattern="^download_"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_any_link
        )
    )

    logger.info("✅ البوت يعمل الآن")

    app.run_polling()


if __name__ == "__main__":
    main()
```
