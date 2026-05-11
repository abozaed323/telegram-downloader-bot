#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)

TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"
ADMIN_ID = 7799287060
BOT_VERSION = "6.2.0"
DEFAULT_DAILY_LIMIT = 5

VODAFONE_NUMBER = "01040757693"
INSTAPAY_NUMBER = "01128085081"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --------------------- قاعدة البيانات ---------------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL)")
c.execute("CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))")
c.execute("CREATE TABLE IF NOT EXISTS referrals (referrer_id INTEGER, referred_id INTEGER, date TEXT DEFAULT CURRENT_TIMESTAMP, is_activated INTEGER DEFAULT 0, PRIMARY KEY (referrer_id, referred_id))")
conn.commit()

def is_vip(user_id):
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry = datetime.strptime(row[0], "%Y-%m-%d")
            return expiry >= datetime.now()
        except:
            return False
    return False

def get_daily_count(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_count(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1", (user_id, today))
    conn.commit()

def can_download(user_id):
    return is_vip(user_id) or get_daily_count(user_id) < DEFAULT_DAILY_LIMIT

def get_remaining_downloads(user_id):
    if is_vip(user_id):
        return -1
    return max(0, DEFAULT_DAILY_LIMIT - get_daily_count(user_id))

def activate_vip(user_id, days):
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()

PROMO_MESSAGE = (
    f"🎁 **اشترك في قناتنا** 🎁\nhttps://t.me/dawinlod\n\n"
    f"🔥 **عرض خاص:** كل من يشترك في القناة ويبلغ المشرف {ADMIN_USERNAME} يحصل على **5 تحميلات مجانية إضافية**!\n\n"
    f"📞 للاشتراك VIP: {ADMIN_USERNAME}"
)

async def send_promotion(user_id, context):
    await context.bot.send_message(chat_id=user_id, text=PROMO_MESSAGE, parse_mode="Markdown")

def detect_platform(url):
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

async def download_video(url, quality="best"):
    opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "quiet": True,
        "format": "best" if quality == "best" else "worst",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("🔗 الإحالات", callback_data="menu_referrals")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --------------------- الأوامر ---------------------
async def start(update, context):
    user = update.effective_user
    name = user.first_name or "صديقي"
    remaining = get_remaining_downloads(user.id)
    limit_text = "غير محدود 🚀" if remaining == -1 else f"متبقي {remaining} تحميلات اليوم"
    text = f"🎬 أهلاً بك {name}!\n\n📊 حالتك: {limit_text}\n⭐ اشترك VIP للتحميل غير المحدود\n\n📞 {ADMIN_USERNAME}"
    await update.message.reply_text(text, reply_markup=await main_menu())

async def menu_download(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("📥 أرسل رابط الفيديو الآن", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def menu_usage(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_vip(uid):
        text = "⭐ أنت مشترك VIP - لا حدود للتحميل"
    else:
        used = get_daily_count(uid)
        remain = DEFAULT_DAILY_LIMIT - used
        text = f"📊 استخدمت {used}/{DEFAULT_DAILY_LIMIT} اليوم\n📈 المتبقي: {remain}"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def menu_vip(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_vip(uid):
        text = "✅ أنت مشترك VIP بالفعل"
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    else:
        keyboard = [
            [InlineKeyboardButton("⭐ دفع بالنجوم (تفعيل فوري)", callback_data="pay_stars")],
            [InlineKeyboardButton("📞 تواصل مع المشرف", callback_data="contact_admin")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        text = f"⭐ للاشتراك VIP:\n• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\nاختر طريقة الدفع:\n📞 {ADMIN_USERNAME}"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def contact_admin(update, context):
    q = update.callback_query
    await q.answer()
    text = (
        f"📞 **للاشتراك عبر فودافون كاش أو إنستا باي**\n\n"
        f"📱 **فودافون كاش:** `{VODAFONE_NUMBER}`\n"
        f"🏦 **إنستا باي:** `{INSTAPAY_NUMBER}`\n\n"
        f"💰 المبلغ: 1$ أسبوعياً\n\n"
        f"📌 بعد التحويل، تواصل مع المشرف {ADMIN_USERNAME} وأرسل الإيصال.\n"
        f"🕒 سيتم التفعيل خلال 24 ساعة."
    )
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_vip")]]))

async def pay_stars(update, context):
    q = update.callback_query
    await q.answer()
    prices = [LabeledPrice("VIP اشتراك", 100)]
    await context.bot.send_invoice(
        chat_id=q.from_user.id,
        title="⭐ اشتراك VIP - أسبوعي",
        description="تحميل غير محدود بدون إعلانات",
        payload="vip_weekly",
        provider_token="",
        currency="XTR",
        prices=prices,
    )

async def precheckout_callback(update, context):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_callback(update, context):
    activate_vip(update.effective_user.id, 7)
    await update.message.reply_text(f"✅ تم تفعيل VIP بنجاح! شكراً لدعمك.\n📞 {ADMIN_USERNAME}")

async def menu_referrals(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    text = f"🔗 رابط الإحالة الخاص بك:\n{link}\n\nادع أصدقاءك واحصل على مكافآت!"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def menu_policy(update, context):
    q = update.callback_query
    await q.answer()
    text = f"⚖️ سياسة الاستخدام:\nالمستخدم مسؤول عن المحتوى.\nللاستفسار: {ADMIN_USERNAME}"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def back(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 القائمة الرئيسية", reply_markup=await main_menu())

async def handle_link(update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم")
        return
    if not can_download(uid):
        await update.message.reply_text("⚠️ استنفدت تحميلات اليوم المجانية")
        return
    await update.message.reply_text("⏳ جاري التحميل...")
    try:
        path = await download_video(url)
        with open(path, "rb") as f:
            await update.message.reply_video(f, caption="✅ تم التحميل!")
        os.remove(path)
        if not is_vip(uid):
            increment_daily_count(uid)
        await send_promotion(uid, context)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")

# --------------------- أوامر المشرف ---------------------
async def activate_vip_cmd(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ للمشرف فقط")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        activate_vip(user_id, days)
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً")
    except:
        await update.message.reply_text("⚠️ استخدم: /activate_vip <user_id> <أيام>")

async def stats_cmd(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ للمشرف فقط")
        return
    c.execute("SELECT COUNT(*) FROM vip")
    vip_count = c.fetchone()[0]
    await update.message.reply_text(f"📊 الإحصائيات:\n👑 عدد VIP: {vip_count}\n🚀 الإصدار {BOT_VERSION}")

# --------------------- التشغيل ---------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip", activate_vip_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_referrals, pattern="^menu_referrals$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars$"))
    app.add_handler(CallbackQueryHandler(contact_admin, pattern="^contact_admin$"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    logger.info(f"✅ البوت يعمل - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()