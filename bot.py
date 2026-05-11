#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import random
import sqlite3
import requests
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

# ========== الإعدادات الأساسية ==========
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"
ADMIN_ID = 7799287060

# Ammer Pay Live
AMMER_PAY_API_KEY = "5775769170:LIVE:TG_LgpGu_wx9zf4gv6tdgdBYZ0A"
AMMER_PAY_API_URL = "https://ammer-pay.com/api/v1/invoice"

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

# ========== Ammer Pay ==========
def create_ammer_pay_invoice(amount: float, user_id: int, plan_name: str) -> str or None:
    headers = {
        "Authorization": f"Bearer {AMMER_PAY_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "amount": amount,
        "currency": "USD",
        "description": f"اشتراك {plan_name} في بوت {BOT_USERNAME} للمستخدم {user_id}",
        "callback_url": "",
        "success_url": "",
        "cancel_url": "",
        "metadata": {"user_id": user_id, "plan": plan_name, "bot": BOT_USERNAME}
    }
    try:
        response = requests.post(AMMER_PAY_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            data = response.json()
            payment_url = data.get("payment_url") or data.get("invoice_url") or data.get("url")
            if payment_url:
                return payment_url
        logger.error(f"Ammer Pay error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        logger.error(f"Ammer Pay request failed: {e}")
        return None

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

# ========== القائمة الرئيسية ==========
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

# ========== أزرار القائمة الرئيسية ==========
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
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if is_vip(uid):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
        expiry = c.fetchone()[0]
        text = f"✅ أنت مشترك VIP حتى {expiry}\nشكراً لدعمك!"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    else:
        # عرض أزرار الباقات - تم تغيير الـ callback_data إلى أسماء مميزة
        keyboard = [
            [InlineKeyboardButton("📅 أسبوعي - 1$", callback_data="vip_plan_weekly")],
            [InlineKeyboardButton("📆 شهري - 3$", callback_data="vip_plan_monthly")],
            [InlineKeyboardButton("🎉 سنوي - 25$ (توفير 11$)", callback_data="vip_plan_yearly")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        await query.edit_message_text(
            "⭐ **اختر الباقة المناسبة لك:**\n\n• أسبوعي: 1$\n• شهري: 3$\n• سنوي: 25$\n\nبعد الاختيار، ستظهر لك طرق الدفع.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# ========== معالجات الباقات (أسبوعي، شهري، سنوي) ==========
async def vip_plan_weekly(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    plan_name = "أسبوعي"
    price = 1.0
    duration_days = 7
    
    payment_url = create_ammer_pay_invoice(price, user_id, plan_name)
    
    if payment_url:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 المبلغ: {price}$\n\n"
            "🔗 **رابط الدفع الآمن عبر Ammer Pay:**\n"
            f"[اضغط هنا للدفع]({payment_url})\n\n"
            "📩 **بعد إتمام الدفع**، سيتم تفعيل اشتراكك تلقائياً خلال دقائق.\n"
            "🔸 **للتجربة فقط:** ارسل /activate_vip_test (VIP لمدة ساعة)"
        )
    else:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 المبلغ: {price}$\n\n"
            "⚠️ عذراً، لم نتمكن من إنشاء رابط الدفع الآلي حالياً. يمكنك الدفع يدوياً:\n"
            "• 📱 فودافون كاش: 0123456789\n"
            "• 🏦 إنستا باي: instapay@example.com\n\n"
            f"📩 بعد الدفع أرسل الإيصال إلى {ADMIN_USERNAME}\n🕒 سيتم التفعيل خلال 24 ساعة."
        )
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع إلى الباقات", callback_data="menu_vip")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def vip_plan_monthly(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    plan_name = "شهري"
    price = 3.0
    duration_days = 30
    
    payment_url = create_ammer_pay_invoice(price, user_id, plan_name)
    
    if payment_url:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 المبلغ: {price}$\n\n"
            "🔗 **رابط الدفع الآمن عبر Ammer Pay:**\n"
            f"[اضغط هنا للدفع]({payment_url})\n\n"
            "📩 **بعد إتمام الدفع**، سيتم تفعيل اشتراكك تلقائياً خلال دقائق.\n"
            "🔸 **للتجربة فقط:** ارسل /activate_vip_test (VIP لمدة ساعة)"
        )
    else:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 المبلغ: {price}$\n\n"
            "⚠️ عذراً، لم نتمكن من إنشاء رابط الدفع الآلي حالياً. يمكنك الدفع يدوياً:\n"
            "• 📱 فودافون كاش: 0123456789\n"
            "• 🏦 إنستا باي: instapay@example.com\n\n"
            f"📩 بعد الدفع أرسل الإيصال إلى {ADMIN_USERNAME}\n🕒 سيتم التفعيل خلال 24 ساعة."
        )
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع إلى الباقات", callback_data="menu_vip")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def vip_plan_yearly(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    plan_name = "سنوي"
    price = 25.0
    duration_days = 365
    
    payment_url = create_ammer_pay_invoice(price, user_id, plan_name)
    
    if payment_url:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 المبلغ: {price}$\n\n"
            "🔗 **رابط الدفع الآمن عبر Ammer Pay:**\n"
            f"[اضغط هنا للدفع]({payment_url})\n\n"
            "📩 **بعد إتمام الدفع**، سيتم تفعيل اشتراكك تلقائياً خلال دقائق.\n"
            "🔸 **للتجربة فقط:** ارسل /activate_vip_test (VIP لمدة ساعة)"
        )
    else:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 المبلغ: {price}$\n\n"
            "⚠️ عذراً، لم نتمكن من إنشاء رابط الدفع الآلي حالياً. يمكنك الدفع يدوياً:\n"
            "• 📱 فودافون كاش: 0123456789\n"
            "• 🏦 إنستا باي: instapay@example.com\n\n"
            f"📩 بعد الدفع أرسل الإيصال إلى {ADMIN_USERNAME}\n🕒 سيتم التفعيل خلال 24 ساعة."
        )
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع إلى الباقات", callback_data="menu_vip")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

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

# ========== معالج الروابط وجودة التحميل ==========
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
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
    ]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality_callback(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    quality = "best" if q.data == "quality_best" else "worst"
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
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة.")

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

# ========== التشغيل الرئيسي ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    # الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", test_vip))
    app.add_handler(CommandHandler("activate_vip", activate_vip))
    
    # أزرار القائمة الرئيسية
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    
    # أزرار الباقات (أسبوعي، شهري، سنوي) - تم إصلاحها
    app.add_handler(CallbackQueryHandler(vip_plan_weekly, pattern="^vip_plan_weekly$"))
    app.add_handler(CallbackQueryHandler(vip_plan_monthly, pattern="^vip_plan_monthly$"))
    app.add_handler(CallbackQueryHandler(vip_plan_yearly, pattern="^vip_plan_yearly$"))
    
    # جودة التحميل
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_(best|worst)$"))
    
    # الروابط
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info("✅ البوت يعمل وجميع الأزرار مفعلة (أسبوعي، شهري، سنوي).")
    app.run_polling()

if __name__ == "__main__":
    main()