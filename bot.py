#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import random
import sqlite3
import re
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
ADMIN_ID = 7799287060

BOT_VERSION = "4.1.0"
DEFAULT_DAILY_LIMIT = 5

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

# ======================== دوال VIP ========================
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

def get_daily_count(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_count(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
        INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
    """, (user_id, today))
    conn.commit()

def can_download(user_id: int) -> bool:
    return is_vip(user_id) or get_daily_count(user_id) < DEFAULT_DAILY_LIMIT

def get_remaining_downloads(user_id: int) -> int:
    if is_vip(user_id):
        return -1
    return max(0, DEFAULT_DAILY_LIMIT - get_daily_count(user_id))

# ======================== الإعلانات ========================
ADVERTISEMENTS = [
    "📢 اشترك في قناتنا للحصول على بوتات حصرية @YourChannel",
    "⭐ باقات VIP تبدأ من 1$ فقط أسبوعياً، تواصل مع @Mac_0980",
    "🔥 البوت يدعم الآن تحميل البث المباشر من تيك توك!",
    "💎 اشترك الآن واحصل على تحميل غير محدود بدون إعلانات"
]

async def send_ad(user_id: int, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADVERTISEMENTS))

# ======================== تحميل الفيديو ========================
def detect_platform(url: str):
    u = url.lower()
    if "tiktok.com" in u:
        if "/live" in u or "?live" in u:
            return "تيك توك لايف 🎥"
        return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u:
        return "فيسبوك"
    if "twitter.com" in u or "x.com" in u:
        return "تويتر"
    if "youtube.com" in u or "youtu.be" in u:
        if "/shorts/" in u:
            return "يوتيوب Shorts"
        return "يوتيوب"
    if "instagram.com" in u:
        if "/stories/" in u:
            return "انستجرام استوري"
        if "/reel/" in u:
            return "انستجرام ريلز"
        if "/p/" in u:
            return "انستجرام منشور"
        return "انستجرام"
    return "غير معروف"

async def download_video(url: str, quality: str = "best") -> str:
    opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best" if quality == "best" else "worst",
    }
    if "/live" in url:
        opts["live_from_start"] = True
        opts["format"] = "best[height<=480]"
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir(DOWNLOAD_DIR)
            if files:
                filename = os.path.join(DOWNLOAD_DIR, max([os.path.join(DOWNLOAD_DIR, f) for f in files], key=os.path.getctime))
        return filename

# ======================== القائمة الرئيسية ========================
async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context):
    user = update.effective_user
    name = user.first_name or user.username or "صديقي"
    remaining = get_remaining_downloads(user.id)
    limit_text = "غير محدود 🚀" if remaining == -1 else f"متبقي {remaining} تحميلات اليوم"
    
    text = (
        f"🎬 **أهلاً بك {name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "✅ تيك توك (فيديو أو لايف)\n"
        "✅ فيسبوك\n✅ تويتر\n✅ يوتيوب (فيديو أو شورتس)\n"
        "✅ انستجرام (منشور، ريلز، استوري)\n\n"
        f"📊 **حالتك:** {limit_text}\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات\n\n"
        "اختر من القائمة:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=await main_menu())

# ========== أزرار القائمة ==========
async def menu_download(update: Update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\nلإلغاء العملية، اضغط /start",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
    )

async def menu_usage(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_vip(uid):
        text = "⭐ **أنت مشترك VIP** – لا حدود للتحميل اليومي"
    else:
        used = get_daily_count(uid)
        remain = DEFAULT_DAILY_LIMIT - used
        text = f"📊 **استخدمت اليوم {used}/{DEFAULT_DAILY_LIMIT}**\n📈 **المتبقي:** {remain} تحميلات\n\nلرفع الحد، اشترك في VIP"
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def menu_vip(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_vip(uid):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
        expiry = c.fetchone()[0]
        text = f"✅ **أنت مشترك VIP حتى {expiry}**\nشكراً لدعمك المستمر 🎉"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    else:
        keyboard = [
            [InlineKeyboardButton("📅 أسبوعي - 1$", callback_data="plan_weekly")],
            [InlineKeyboardButton("📆 شهري - 3$", callback_data="plan_monthly")],
            [InlineKeyboardButton("🎉 سنوي - 25$ (وفر 11$)", callback_data="plan_yearly")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        text = (
            "⭐ **باقات الاشتراك VIP** ⭐\n\n"
            "• **أسبوعي:** 1$ – 7 أيام\n"
            "• **شهري:** 3$ – 30 يوماً\n"
            "• **سنوي:** 25$ – 365 يوماً (توفير 11$)\n\n"
            "🎁 **مميزات VIP:**\n"
            "✓ تحميل غير محدود\n"
            "✓ بدون إعلانات\n"
            "✓ جودة عالية 4K/8K\n\n"
            "اختر الباقة المناسبة لك:"
        )
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== عرض طرق الدفع عند اختيار الباقة ==========
async def show_payment_methods(update: Update, context, plan: str, price: str):
    q = update.callback_query
    await q.answer()
    
    text = (
        f"⭐ **باقة {plan}**\n💰 **السعر:** {price}\n\n"
        "💳 **طرق الدفع المتاحة:**\n"
        "• ⭐ **نجوم تليجرام (Telegram Stars)**\n"
        "• 📱 **فودافون كاش:** 01001234567\n"
        "• 🏦 **إنستا باي:** instapay@example.com\n\n"
        f"📩 **بعد الدفع**، أرسل صورة الإيصال إلى المشرف {ADMIN_USERNAME}\n"
        "🕒 سيتم تفعيل اشتراكك خلال 24 ساعة كحد أقصى\n\n"
        "📌 ملاحظة: هذا البوت لا يخزن بيانات الدفع الخاصة بك"
    )
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع إلى الباقات", callback_data="menu_vip")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back")]
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def plan_weekly(update: Update, context):
    await show_payment_methods(update, context, "أسبوعي", "1$")

async def plan_monthly(update: Update, context):
    await show_payment_methods(update, context, "شهري", "3$")

async def plan_yearly(update: Update, context):
    await show_payment_methods(update, context, "سنوي", "25$")

async def menu_policy(update: Update, context):
    q = update.callback_query
    await q.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ **المسؤولية:** المستخدم هو المسؤول الوحيد عن أي محتوى يقوم بتحميله أو مشاركته.\n"
        "2️⃣ **حقوق النشر:** يُمنع تحميل المواد المحمية بحقوق الطبع والنشر دون إذن مسبق.\n"
        "3️⃣ **الخصوصية:** لا نقوم بتخزين الملفات بعد إرسالها للمستخدم.\n"
        f"4️⃣ **الإبلاغ:** للشكاوى أو الاستفسارات، تواصل مع {ADMIN_USERNAME}\n\n"
        f"📩 {ADMIN_USERNAME}"
    )
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def back(update: Update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu(), parse_mode="Markdown")

# ========== معالج الروابط وجودة التحميل ==========
async def handle_link(update: Update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == "غير معروف":
        await update.message.reply_text("❌ الرابط غير مدعوم. أرسل رابطاً من إحدى المنصات المدعومة.")
        return
    
    if not can_download(uid):
        remain = get_remaining_downloads(uid)
        await update.message.reply_text(
            f"⚠️ **لقد استنفدت تحميلات اليوم المجانية**\n"
            f"📊 استخدمت {get_daily_count(uid)}/{DEFAULT_DAILY_LIMIT}\n"
            f"📈 المتبقي: {remain} تحميلات\n\n"
            "⭐ اشترك في VIP للتحميل غير المحدود\n"
            "استخدم القائمة الرئيسية ← الاشتراك VIP",
            parse_mode="Markdown"
        )
        return
    
    context.user_data["url"] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
    ]
    await update.message.reply_text(
        f"📌 **المنصة:** {platform}\nاختر جودة التحميل:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def quality_callback(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    quality = "best" if q.data == "quality_best" else "worst"
    url = context.user_data.get("url")
    
    if not url:
        await q.edit_message_text("⚠️ انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    
    if not can_download(uid):
        await q.edit_message_text("⚠️ تجاوزت حد التحميل اليومي. اشترك VIP للاستمرار.")
        return
    
    await q.edit_message_text("⏳ **جاري التحميل...**\nقد يستغرق بضع ثوانٍ حسب حجم الفيديو.", parse_mode="Markdown")
    
    try:
        file_path = await download_video(url, quality)
        with open(file_path, "rb") as video:
            caption = "✅ **تم التحميل بنجاح!**\n\n"
            if is_vip(uid):
                caption += "⭐ أنت مشترك VIP – تحميل غير محدود"
            else:
                caption += f"📊 تبقت لك {get_remaining_downloads(uid)} تحميلات اليوم\n⭐ اشترك VIP لإزالة الحدود والإعلانات"
            await q.message.reply_video(video, caption=caption, parse_mode="Markdown")
        
        os.remove(file_path)
        
        if not is_vip(uid):
            increment_daily_count(uid)
        
        await send_ad(uid, context)
        
    except Exception as e:
        error_msg = str(e)[:150]
        logger.error(f"Download error: {e}")
        await q.message.reply_text(
            f"❌ **فشل التحميل**\n\nالسبب: {error_msg}\n\n"
            "تأكد من:\n"
            "• الرابط صحيح ويعمل\n"
            "• الفيديو ليس خاصاً أو محذوفاً\n"
            "• إذا كان بثاً مباشراً، قد تحتاج للانتظار حتى انتهائه",
            parse_mode="Markdown"
        )
    finally:
        context.user_data.pop("url", None)

# ========== أوامر المشرف ==========
async def activate_vip(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
        conn.commit()
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً (ينتهي {expiry})")
    except:
        await update.message.reply_text("⚠️ الاستخدام: `/activate_vip <user_id> <أيام>`", parse_mode="Markdown")

async def stats(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    c.execute("SELECT COUNT(*) FROM vip")
    vip_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM daily_downloads WHERE date=?", (datetime.now().strftime("%Y-%m-%d"),))
    today_downloads = c.fetchone()[0]
    text = (
        "📊 **إحصائيات البوت**\n\n"
        f"👑 المشتركين VIP: {vip_count}\n"
        f"📥 تحميلات اليوم: {today_downloads}\n"
        f"🚀 الإصدار: {BOT_VERSION}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ========== تشغيل البوت ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip", activate_vip))
    app.add_handler(CommandHandler("stats", stats))
    
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    
    app.add_handler(CallbackQueryHandler(plan_weekly, pattern="^plan_weekly$"))
    app.add_handler(CallbackQueryHandler(plan_monthly, pattern="^plan_monthly$"))
    app.add_handler(CallbackQueryHandler(plan_yearly, pattern="^plan_yearly$"))
    
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_(best|worst)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info(f"✅ البوت يعمل الآن - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()