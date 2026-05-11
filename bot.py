#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import random
import re
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

# ===================================================================
# الإعدادات الأساسية
# ===================================================================
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"
ADMIN_IDS = [7799287060]  # يمكن إضافة عدة مشرفين

# Ammer Pay
AMMER_PAY_API_KEY = "5775769170:LIVE:TG_LgpGu_wx9zf4gv6tdgdBYZ0A"
AMMER_PAY_API_URL = "https://ammer-pay.com/api/v1/invoice"

BOT_VERSION = "4.0.0"
DEFAULT_DAILY_LIMIT = 5

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ===================================================================
# قاعدة البيانات (VIP والحد اليومي والإحالات)
# ===================================================================
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS vip (
    user_id INTEGER PRIMARY KEY,
    expiry_date TEXT NOT NULL,
    subscribed_at TEXT DEFAULT CURRENT_TIMESTAMP
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

c.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    date TEXT DEFAULT CURRENT_TIMESTAMP,
    is_activated INTEGER DEFAULT 0,
    PRIMARY KEY (referrer_id, referred_id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS pending_payments (
    user_id INTEGER PRIMARY KEY,
    plan TEXT,
    amount REAL,
    payment_url TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ===================================================================
# دوال VIP والاستخدام
# ===================================================================
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

def get_vip_expiry(user_id: int) -> str or None:
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else None

def activate_vip(user_id: int, days: int):
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()

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
        return -1  # غير محدود
    return max(0, DEFAULT_DAILY_LIMIT - get_daily_count(user_id))

# ===================================================================
# الإعلانات
# ===================================================================
ADVERTISEMENTS = [
    "📢 اشترك في قناتنا: @YourChannel",
    "⭐ باقات VIP تبدأ من 1$ فقط أسبوعياً",
    "🔥 حمّل البث المباشر من تيك توك",
    "💎 لفترة محدودة: خصم 20% على الباقة السنوية",
    "📌 البوت يدعم تحميل القصص والريلز"
]

async def send_ad(user_id: int, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADVERTISEMENTS))

# ===================================================================
# Ammer Pay (دفع حقيقي)
# ===================================================================
def create_payment_invoice(amount: float, user_id: int, plan_name: str) -> str or None:
    headers = {
        "Authorization": f"Bearer {AMMER_PAY_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "amount": amount,
        "currency": "USD",
        "description": f"{plan_name} - @{BOT_USERNAME} للمستخدم {user_id}",
        "metadata": {
            "user_id": user_id,
            "plan": plan_name,
            "bot": BOT_USERNAME
        }
    }
    
    try:
        response = requests.post(AMMER_PAY_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            data = response.json()
            payment_url = data.get("payment_url") or data.get("invoice_url") or data.get("url")
            if payment_url:
                # حفظ حالة الدفع
                c.execute("""
                    INSERT OR REPLACE INTO pending_payments (user_id, plan, amount, payment_url, status)
                    VALUES (?, ?, ?, ?, 'pending')
                """, (user_id, plan_name, amount, payment_url))
                conn.commit()
                return payment_url
        logger.error(f"Ammer Pay error: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ammer Pay failed: {e}")
        return None

# ===================================================================
# تحميل الفيديو (يدعم جميع المنصات)
# ===================================================================
def detect_platform(url: str) -> tuple:
    u = url.lower()
    
    # تيك توك (عادي أو لايف)
    if "tiktok.com" in u:
        if "/live" in u or "?live" in u:
            return ("تيك توك لايف", True)
        return ("تيك توك", False)
    
    # فيسبوك (فيديو عادي، ريلز، ووتش)
    if "facebook.com" in u or "fb.watch" in u:
        if "/reel/" in u or "/reels/" in u:
            return ("فيسبوك ريلز", False)
        return ("فيسبوك", False)
    
    # تويتر/X
    if "twitter.com" in u or "x.com" in u:
        return ("تويتر", False)
    
    # يوتيوب (عادي، شورتس، بث)
    if "youtube.com" in u or "youtu.be" in u:
        if "/shorts/" in u:
            return ("يوتيوب Shorts", False)
        if "/live/" in u or "?live=" in u:
            return ("يوتيوب لايف", True)
        return ("يوتيوب", False)
    
    # انستجرام (منشور، ريلز، استوري)
    if "instagram.com" in u:
        if "/stories/" in u:
            return ("انستجرام استوري", True)
        if "/reel/" in u:
            return ("انستجرام ريلز", False)
        if "/p/" in u:
            return ("انستجرام منشور", False)
        return ("انستجرام", False)
    
    return ("غير معروف", False)

async def download_video(url: str, quality: str = "best") -> str:
    opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ignoreerrors": True,
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]" if quality == "best" else "worst",
    }
    
    # خيارات خاصة للبث المباشر
    if "/live" in url or "?live" in url:
        opts["live_from_start"] = True
        opts["format"] = "best[height<=480]"
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                files = os.listdir(DOWNLOAD_DIR)
                if files:
                    filename = os.path.join(DOWNLOAD_DIR, max(
                        [os.path.join(DOWNLOAD_DIR, f) for f in files], 
                        key=os.path.getctime
                    ))
            return filename
        except Exception as e:
            logger.error(f"Download error: {e}")
            raise e

# ===================================================================
# نظام الإحالات
# ===================================================================
async def handle_referral(update: Update, context):
    """معالجة رابط الإحالة عند بدء المستخدم"""
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].replace("ref_", ""))
            user_id = update.effective_user.id
            
            if referrer_id != user_id:
                c.execute("SELECT * FROM referrals WHERE referrer_id=? AND referred_id=?", (referrer_id, user_id))
                if not c.fetchone():
                    c.execute("INSERT INTO referrals (referrer_id, referred_id, is_activated) VALUES (?, ?, 0)", 
                             (referrer_id, user_id))
                    conn.commit()
                    
                    await update.message.reply_text(
                        "🎉 تم تسجيل إحالتك! سيحصل من دعاك على مكافأة عند تفعيل اشتراكك."
                    )
        except Exception as e:
            logger.error(f"Referral error: {e}")

# ===================================================================
# القائمة الرئيسية
# ===================================================================
async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي اليومي", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("🔗 نظام الإحالات", callback_data="menu_referrals")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context):
    """رسالة الترحيب والقائمة الرئيسية"""
    await handle_referral(update, context)
    
    user = update.effective_user
    name = user.first_name or user.username or "صديقي"
    
    remaining = get_remaining_downloads(user.id)
    limit_text = "غير محدود 🚀" if remaining == -1 else f"{remaining} تحميلات متبقية اليوم"
    
    text = (
        f"🎬 **أهلاً بك {name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابطاً من:**\n"
        "• تيك توك (فيديو أو لايف)\n"
        "• فيسبوك (فيديو، ريلز)\n"
        "• تويتر (X)\n"
        "• يوتيوب (فيديو، شورتس، لايف)\n"
        "• انستجرام (منشور، ريلز، استوري)\n\n"
        f"📊 **حالتك:** {limit_text}\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات + أولوية\n\n"
        "اختر من القائمة:"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=await main_menu())

# ===================================================================
# أزرار القائمة
# ===================================================================
async def menu_download(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\n"
        "مثال: https://www.tiktok.com/@user/video/123456789\n"
        "أو رابط بث مباشر: https://www.tiktok.com/@user/live\n\n"
        "لإلغاء العملية، اضغط /start",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
    )

async def menu_usage(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if is_vip(uid):
        expiry = get_vip_expiry(uid)
        text = f"⭐ **أنت مشترك VIP**\n📅 ينتهي في: {expiry}\n📥 تحميل غير محدود"
    else:
        used = get_daily_count(uid)
        remaining = DEFAULT_DAILY_LIMIT - used
        text = f"📊 **استخدامك اليومي:** {used}/{DEFAULT_DAILY_LIMIT}\n📈 **المتبقي:** {remaining} تحميلات\n\nللحصول على تحميل غير محدود، اشترك في VIP."
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def menu_vip(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if is_vip(uid):
        expiry = get_vip_expiry(uid)
        text = f"✅ **أنت مشترك VIP**\n📅 حتى: {expiry}\nشكراً لدعمك المستمر! 🎉"
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
            "• **سنوي:** 25$ – 365 يوماً (وفر 11$)\n\n"
            "🎁 **مميزات VIP:**\n"
            "✓ تحميل غير محدود يومياً\n"
            "✓ بدون إعلانات\n"
            "✓ جودة عالية 4K/8K\n"
            "✓ أولوية في المعالجة\n\n"
            "اختر الباقة المناسبة:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def plan_handler(update: Update, context, plan_name: str, price: float, duration_days: int):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    if is_vip(uid):
        await query.edit_message_text(
            "✅ أنت بالفعل مشترك VIP!\nيمكنك الاستمرار في التحميل بدون حدود.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
        )
        return
    
    # إنشاء رابط دفع أمّر باي
    payment_url = create_payment_invoice(price, uid, plan_name)
    
    if payment_url:
        text = (
            f"⭐ **باقة {plan_name}**\n💰 **المبلغ:** {price}$\n\n"
            "🔗 **رابط الدفع الآمن:**\n"
            f"[اضغط هنا للدفع عبر Ammer Pay]({payment_url})\n\n"
            "💳 **طرق الدفع المتاحة:**\n"
            "• بطاقات الائتمان (فيزا، ماستركارد)\n"
            "• فودافون كاش\n"
            "• إنستا باي\n"
            "• تحويل بنكي\n\n"
            "📩 **بعد إتمام الدفع**، سيتم تفعيل اشتراكك تلقائياً.\n"
            "📞 للدعم أو الاستفسار: {ADMIN_USERNAME}\n\n"
            "_سيتم تفعيل الاشتراك خلال 24 ساعة من الدفع._"
        )
    else:
        # في حالة فشل إنشاء رابط الدفع، نعرض الطرق اليدوية
        text = (
            f"⭐ **باقة {plan_name}**\n💰 **المبلغ:** {price}$\n\n"
            "⚠️ **طرق الدفع الحالية:**\n\n"
            "📱 **فودافون كاش:**\n"
            "`01001234567` - أحمد محمد\n\n"
            "🏦 **إنستا باي:**\n"
            "`instapay@example.com`\n\n"
            f"📩 **بعد التحويل**، أرسل صورة الإيصال إلى:\n"
            f"{ADMIN_USERNAME}\n"
            "🕒 سيتم تفعيل الاشتراك خلال 24 ساعة."
        )
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع إلى الباقات", callback_data="menu_vip")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def plan_weekly(update: Update, context):
    await plan_handler(update, context, "أسبوعي", 1.0, 7)

async def plan_monthly(update: Update, context):
    await plan_handler(update, context, "شهري", 3.0, 30)

async def plan_yearly(update: Update, context):
    await plan_handler(update, context, "سنوي", 25.0, 365)

async def menu_referrals(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    # رابط الإحالة الخاص بالمستخدم
    bot_username = BOT_USERNAME
    referral_link = f"https://t.me/{bot_username}?start=ref_{uid}"
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,))
    total_referrals = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_activated=1", (uid,))
    active_referrals = c.fetchone()[0]
    
    text = (
        "🔗 **نظام الإحالات** 🔗\n\n"
        "ادعُ أصدقاءك واحصل على مكافآت!\n\n"
        f"📢 **رابط الإحالة الخاص بك:**\n"
        f"`{referral_link}`\n\n"
        f"📊 **إحصائياتك:**\n"
        f"• عدد المدعوين: {total_referrals}\n"
        f"• مدعوون نشطون: {active_referrals}\n\n"
        "🎁 **المكافآت:**\n"
        "• كل 5 مدعوين نشطين = يوم VIP مجاني\n"
        "• كل 10 مدعوين نشطين = أسبوع VIP مجاني\n\n"
        "شارك الرابط مع أصدقائك واحصل على مميزات إضافية!"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_referral")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def copy_referral(update: Update, context):
    query = update.callback_query
    await query.answer("تم نسخ الرابط! أرسله لأصدقائك ✅", show_alert=True)

async def menu_policy(update: Update, context):
    query = update.callback_query
    await query.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ **المسؤولية:** المستخدم هو المسؤول الوحيد عن المحتوى الذي يقوم بتحميله أو مشاركته.\n"
        "2️⃣ **حقوق النشر:** يمنع تحميل المواد المحمية بحقوق الطبع والنشر دون إذن مسبق.\n"
        "3️⃣ **الخصوصية:** لا نقوم بتخزين الملفات بعد إرسالها للمستخدم.\n"
        "4️⃣ **الإبلاغ:** للحقوق أو الشكاوى، تواصل مع {ADMIN_USERNAME}\n"
        f"5️⃣ **التوفر:** قد يتعذر تحميل بعض المحتويات الخاصة أو المحذوفة.\n\n"
        f"📩 **للاستفسارات:** {ADMIN_USERNAME}"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def back(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏠 **القائمة الرئيسية**", parse_mode="Markdown", reply_markup=await main_menu())

# ===================================================================
# معالج الروابط وجودة التحميل
# ===================================================================
async def handle_link(update: Update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform, is_live = detect_platform(url)
    
    if platform == "غير معروف":
        await update.message.reply_text(
            "❌ **رابط غير مدعوم**\n\n"
            "الروابط المقبولة:\n"
            "• تيك توك (فيديو أو لايف)\n"
            "• فيسبوك (فيديو، ريلز)\n"
            "• تويتر/X\n"
            "• يوتيوب (فيديو، شورتس، لايف)\n"
            "• انستجرام (منشور، ريلز، استوري)",
            parse_mode="Markdown"
        )
        return
    
    if not can_download(uid):
        remain = get_remaining_downloads(uid)
        await update.message.reply_text(
            f"⚠️ **انتهت تحميلات اليوم المجانية**\n\n"
            f"اليوم استخدمت {get_daily_count(uid)}/{DEFAULT_DAILY_LIMIT}\n"
            f"المتبقي: {remain} تحميلات\n\n"
            "⭐ **اشترك VIP لتحميل غير محدود**\n"
            "استخدم القائمة الرئيسية ← الاشتراك VIP",
            parse_mode="Markdown"
        )
        return
    
    context.user_data["url"] = url
    
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
    ]
    
    live_notice = "\n⚠️ **تنبيه:** البث المباشر قد يستغرق وقتاً أطول للتحميل." if is_live else ""
    
    await update.message.reply_text(
        f"📌 **المنصة:** {platform}\n🎬 جاري التحضير للتحميل...{live_notice}\n\nاختر الجودة المناسبة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def quality_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    quality = "best" if query.data == "quality_best" else "worst"
    url = context.user_data.get("url")
    
    if not url:
        await query.edit_message_text("⚠️ انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    
    if not can_download(uid):
        await query.edit_message_text("⚠️ لقد تجاوزت حد التحميل اليومي. اشترك VIP للاستمرار.")
        return
    
    await query.edit_message_text("⏳ **جاري التحميل...**\nقد يستغرق بضع ثوانٍ حسب حجم الفيديو.", parse_mode="Markdown")
    
    try:
        file_path = await download_video(url, quality)
        
        # إرسال الفيديو
        with open(file_path, "rb") as video_file:
            caption = "✅ **تم التحميل بنجاح!**\n\n"
            if is_vip(uid):
                caption += "⭐ أنت مشترك VIP – تحميل غير محدود."
            else:
                caption += f"📊 تبقت لك {get_remaining_downloads(uid)} تحميلات اليوم.\n⭐ اشترك VIP لإزالة الحدود والإعلانات."
            
            await query.message.reply_video(video_file, caption=caption, parse_mode="Markdown")
        
        # تنظيف
        os.remove(file_path)
        
        # تحديث العداد فقط إذا كان المستخدم غير VIP
        if not is_vip(uid):
            increment_daily_count(uid)
        
        # إعلان للمستخدم المجاني
        await send_ad(uid, context)
        
    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Download error for user {uid}: {e}")
        await query.message.reply_text(
            f"❌ **فشل التحميل**\n\n"
            f"السبب: {error_msg}\n\n"
            "تأكد من:\n"
            "• الرابط صحيح ويعمل\n"
            "• الفيديو ليس خاصاً أو محذوفاً\n"
            "• البث المباشر قد لا يكون متاحاً بعد\n\n"
            "إذا تكررت المشكلة، تواصل مع المشرف.",
            parse_mode="Markdown"
        )
    finally:
        context.user_data.pop("url", None)

# ===================================================================
# أوامر المشرف (VIP اليدوي)
# ===================================================================
async def activate_vip(update: Update, context):
    """تفعيل VIP يدوياً للمستخدمين الذين دفعوا (للمشرفين فقط)"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذا الأمر للمشرفين فقط.")
        return
    
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        activate_vip(user_id, days)
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً.")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ الاستخدام: /activate_vip <user_id> <أيام>\nمثال: /activate_vip 123456789 30")

async def stats(update: Update, context):
    """إحصائيات البوت (للمشرفين فقط)"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذا الأمر للمشرفين فقط.")
        return
    
    c.execute("SELECT COUNT(*) FROM vip")
    vip_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM daily_downloads WHERE date=?", (datetime.now().strftime("%Y-%m-%d"),))
    today_downloads = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals")
    total_referrals = c.fetchone()[0]
    
    text = (
        "📊 **إحصائيات البوت**\n\n"
        f"👑 المشتركين VIP: {vip_count}\n"
        f"📥 تحميلات اليوم: {today_downloads}\n"
        f"🔗 إحالات مسجلة: {total_referrals}\n"
        f"🤖 الإصدار: {BOT_VERSION}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ===================================================================
# التشغيل الرئيسي
# ===================================================================
def main():
    app = Application.builder().token(TOKEN).build()
    
    # الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip", activate_vip))
    app.add_handler(CommandHandler("stats", stats))  # للمشرف
    
    # أزرار القائمة الرئيسية
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_referrals, pattern="^menu_referrals$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(copy_referral, pattern="^copy_referral$"))
    
    # أزرار الباقات
    app.add_handler(CallbackQueryHandler(plan_weekly, pattern="^plan_weekly$"))
    app.add_handler(CallbackQueryHandler(plan_monthly, pattern="^plan_monthly$"))
    app.add_handler(CallbackQueryHandler(plan_yearly, pattern="^plan_yearly$"))
    
    # جودة التحميل
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_(best|worst)$"))
    
    # الروابط والوسائط
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    logger.info(f"✅ البوت يعمل الآن - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()