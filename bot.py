#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

# ========== الإعدادات ==========
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"
ADMIN_ID = 7799287060

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ========== قاعدة البيانات ==========
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

def get_daily_count(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_count(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
        (user_id, today)
    )
    conn.commit()

def can_download(user_id: int) -> bool:
    return is_vip(user_id) or get_daily_count(user_id) < 5

ADS = ["📢 اشترك في قناتنا: @YourChannel", "⭐ اشترك VIP لتحميل غير محدود", "🔥 البوت يدعم تيك توك لايف"]
async def send_ad(user_id: int, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADS))

# ========== تحميل الفيديو ==========
def detect_platform(url: str):
    u = url.lower()
    if "tiktok.com" in u:
        return "تيك توك لايف" if "/live" in u else "تيك توك"
    if "facebook.com" in u or "fb.watch" in u: return "فيسبوك"
    if "twitter.com" in u or "x.com" in u: return "تويتر"
    if "youtube.com" in u or "youtu.be" in u: return "يوتيوب"
    if "instagram.com" in u: return "انستجرام"
    return "غير معروف"

async def download_video(url: str, quality: str = "best") -> str:
    opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "format": "best" if quality == "best" else "worst",
    }
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

# ========== القوائم ==========
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
    name = user.first_name or "صديقي"
    text = (
        f"🎬 أهلاً بك {name} في بوت التحميل الشامل.\n\n"
        "📥 أرسل رابط فيديو من تيك توك، فيسبوك، تويتر، يوتيوب، انستجرام.\n"
        "📊 المجاني: 5 تحميلات يومياً\n⭐ VIP: تحميل غير محدود + بدون إعلانات\n\nاختر من القائمة:"
    )
    await update.message.reply_text(text, reply_markup=await main_menu())

async def menu_download(update: Update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "📥 أرسل رابط الفيديو الآن.\nلإلغاء العملية، أرسل /start",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
    )

async def menu_usage(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_vip(uid):
        text = "⭐ أنت مشترك VIP – لا حدود للتحميل."
    else:
        used = get_daily_count(uid)
        remain = 5 - used
        text = f"📊 استخدمت {used}/5 تحميلات اليوم.\nمتبقي: {remain}"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def menu_vip(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_vip(uid):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
        expiry = c.fetchone()[0]
        text = f"✅ أنت مشترك VIP حتى {expiry}\nشكراً لدعمك!"
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    else:
        keyboard = [
            [InlineKeyboardButton("📅 أسبوعي - 1$", callback_data="plan_weekly")],
            [InlineKeyboardButton("📆 شهري - 3$", callback_data="plan_monthly")],
            [InlineKeyboardButton("🎉 سنوي - 25$ (توفير 11$)", callback_data="plan_yearly")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        await q.edit_message_text(
            "⭐ **اختر الباقة المناسبة لك:**\n\n• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\nبعد الاختيار، ستظهر لك طرق الدفع.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def show_payment_methods(update: Update, context, plan: str, price: str):
    q = update.callback_query
    await q.answer()
    text = (
        f"⭐ **باقة {plan}**\n💰 المبلغ: {price}\n\n"
        "💳 **طرق الدفع المتاحة:**\n• ⭐ نجوم تليجرام (Telegram Stars)\n• 📱 فودافون كاش: 0123456789\n• 🏦 إنستا باي: instapay@example.com\n\n"
        f"📩 **بعد الدفع**، أرسل صورة الإيصال إلى المشرف {ADMIN_USERNAME}\n🕒 سيتم التفعيل خلال 24 ساعة.\n\n🔸 **للتجربة فقط:** ارسل /activate_vip_test (VIP لمدة ساعة)"
    )
    keyboard = [[InlineKeyboardButton("🔙 رجوع إلى الباقات", callback_data="menu_vip")], [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def plan_weekly(update: Update, context): await show_payment_methods(update, context, "أسبوعي", "1$")
async def plan_monthly(update: Update, context): await show_payment_methods(update, context, "شهري", "3$")
async def plan_yearly(update: Update, context): await show_payment_methods(update, context, "سنوي", "25$")

async def menu_policy(update: Update, context):
    q = update.callback_query
    await q.answer()
    text = (
        "⚖️ **سياسة الاستخدام**\n\n• المستخدم مسؤول وحيد عن المحتوى.\n• لا نقوم بتخزين الملفات.\n• حقوق النشر محفوظة لأصحابها.\n"
        f"• للشكاوى: {ADMIN_USERNAME}"
    )
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def back(update: Update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 القائمة الرئيسية:", reply_markup=await main_menu())

# ========== معالج الروابط والجودة ==========
async def handle_link(update: Update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً صحيحاً.")
        return
    if not can_download(uid):
        await update.message.reply_text("⚠️ استنفدت تحميلات اليوم المجانية. اشترك VIP أو انتظر غداً.")
        return
    context.user_data["url"] = url
    keyboard = [[InlineKeyboardButton("🎥 جودة عالية", callback_data="best")], [InlineKeyboardButton("📱 جودة منخفضة", callback_data="worst")]]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    quality = q.data
    url = context.user_data.get("url")
    if not url:
        await q.edit_message_text("انتهى الرابط، أرسله مجدداً.")
        return
    if not can_download(uid):
        await q.edit_message_text("⚠️ تجاوزت الحد اليومي.")
        return
    await q.edit_message_text("⏳ جاري التحميل...")
    try:
        path = await download_video(url, quality)
        with open(path, "rb") as vid:
            await q.message.reply_video(vid, caption="✅ تم التحميل!")
        os.remove(path)
        increment_daily_count(uid)
        await send_ad(uid, context)
    except Exception as e:
        await q.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        context.user_data.pop("url", None)

# ========== أوامر VIP ==========
async def test_vip(update: Update, context):
    uid = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (uid, expiry))
    conn.commit()
    await update.message.reply_text("✅ تفعيل VIP تجريبي لمدة ساعة.")

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
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً.")
    except:
        await update.message.reply_text("⚠️ الاستخدام: /activate_vip <user_id> <أيام>")

# ========== التشغيل ==========
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", test_vip))
    app.add_handler(CommandHandler("activate_vip", activate_vip))
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(plan_weekly, pattern="^plan_weekly$"))
    app.add_handler(CallbackQueryHandler(plan_monthly, pattern="^plan_monthly$"))
    app.add_handler(CallbackQueryHandler(plan_yearly, pattern="^plan_yearly$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(quality, pattern="^(best|worst)$"))
    logger.info("✅ البوت يعمل مع نظام الباقات وطرق الدفع.")
    app.run_polling()

if __name__ == "__main__":
    main()