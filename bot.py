#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import sqlite3
import random
from datetime import datetime, timedelta
from typing import Dict

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

# -------------------- الإعدادات --------------------
TOKEN = "7967186531:AAF0e9uU8uaD8ZYw9iYsGVsbKjM92Hofl1M"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "Down1lodBot"
ADMIN_ID = 7799287060
BOT_VERSION = "9.0.2"
DEFAULT_DAILY_LIMIT = 5

VODAFONE_NUMBER = "01131384851"
INSTAPAY_NUMBER = "غير متاح في الوقت الحالي"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# -------------------- قاعدة البيانات --------------------
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
CREATE TABLE IF NOT EXISTS bot_users (
    user_id INTEGER PRIMARY KEY,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    username TEXT,
    first_name TEXT,
    last_seen TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS download_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    platform TEXT,
    download_date TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS daily_bonus (
    user_id INTEGER,
    date TEXT,
    bonus_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, date)
)
""")
conn.commit()

# -------------------- الدوال المساعدة --------------------
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

def decrement_daily_count(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 0) "
        "ON CONFLICT(user_id, date) DO UPDATE SET count = count - 1",
        (user_id, today)
    )
    conn.commit()

def can_download(user_id: int) -> bool:
    if is_vip(user_id):
        return True
    return get_daily_count(user_id) < DEFAULT_DAILY_LIMIT

def get_remaining_downloads(user_id: int) -> int:
    if is_vip(user_id):
        return -1
    return max(0, DEFAULT_DAILY_LIMIT - get_daily_count(user_id))

def activate_vip(user_id: int, days: int):
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    c.execute("UPDATE referrals SET is_activated = 1 WHERE referred_id = ? AND is_activated = 0", (user_id,))
    conn.commit()
    grant_referral_rewards(user_id)

def grant_referral_rewards(user_id: int):
    c.execute("SELECT referrer_id FROM referrals WHERE referred_id = ? AND is_activated = 1", (user_id,))
    row = c.fetchone()
    if not row:
        return
    referrer_id = row[0]
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND is_activated = 1", (referrer_id,))
    active_count = c.fetchone()[0]
    if active_count >= 10:
        add_vip_days(referrer_id, 7)
    elif active_count >= 5:
        add_vip_days(referrer_id, 1)

def add_vip_days(user_id: int, days: int):
    current_expiry = datetime.now()
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry = datetime.strptime(row[0], "%Y-%m-%d")
            if expiry > current_expiry:
                current_expiry = expiry
        except:
            pass
    new_expiry = current_expiry + timedelta(days=days)
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, new_expiry.strftime("%Y-%m-%d")))
    conn.commit()

def register_user(user_id: int, username: str = None, first_name: str = None):
    username = username or ""
    first_name = first_name or ""
    c.execute(
        "INSERT OR IGNORE INTO bot_users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name)
    )
    c.execute("UPDATE bot_users SET last_seen = CURRENT_TIMESTAMP WHERE user_id=?", (user_id,))
    conn.commit()

def save_download_history(user_id: int, platform: str):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO download_history (user_id, platform, download_date) VALUES (?, ?, ?)",
        (user_id, platform, today)
    )
    conn.commit()

def get_user_stats(user_id: int) -> Dict:
    c.execute("SELECT COUNT(*) FROM download_history WHERE user_id=?", (user_id,))
    total_downloads = c.fetchone()[0]
    c.execute("SELECT platform, COUNT(*) FROM download_history WHERE user_id=? GROUP BY platform ORDER BY COUNT(*) DESC LIMIT 1", (user_id,))
    favorite = c.fetchone()
    favorite_platform = favorite[0] if favorite else "لا يوجد"
    return {"total": total_downloads, "favorite": favorite_platform}

def get_daily_bonus_count(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT bonus_count FROM daily_bonus WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def add_daily_bonus(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO daily_bonus (user_id, date, bonus_count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id, date) DO UPDATE SET bonus_count = bonus_count + 1",
        (user_id, today)
    )
    conn.commit()

# -------------------- الترويج --------------------
PROMO_MESSAGE = (
    "🎁 اشترك في قناتنا 🎁\n"
    "https://t.me/dawinlod\n\n"
    "🔥 عرض خاص: كل من يشترك في القناة ويبلغ المشرف " + ADMIN_USERNAME + " يحصل على 5 تحميلات مجانية إضافية!\n\n"
    "📞 للاشتراك VIP أو الاستفسار: " + ADMIN_USERNAME
)

async def send_promotion(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=PROMO_MESSAGE)

# -------------------- تحميل الفيديو --------------------
def detect_platform(url: str):
    u = url.lower()
    if "tiktok.com" in u:
        if "/photo/" in u:
            return "تيك توك صورة"
        return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u:
        return "فيسبوك"
    if "twitter.com" in u or "x.com" in u:
        return "تويتر"
    if "youtube.com" in u or "youtu.be" in u:
        return "يوتيوب"
    if "instagram.com" in u:
        return "انستجرام"
    if "kwai.com" in u or "kwaicdn.com" in u:
        return "كواي (تجريبي)"
    return "غير معروف"

async def download_video(url: str, quality: str = "best") -> str:
    opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s_%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best" if quality == "best" else "worst",
    }
    if "/live" in url:
        opts["live_from_start"] = True
        opts["format"] = "best[height<=480]"
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            if 'requested_downloads' in info and info['requested_downloads']:
                filename = info['requested_downloads'][0]['filepath']
            else:
                filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                files = os.listdir(DOWNLOAD_DIR)
                if files:
                    filename = os.path.join(DOWNLOAD_DIR, max(files, key=lambda f: os.path.getctime(os.path.join(DOWNLOAD_DIR, f))))
            return filename
        except Exception as e:
            raise Exception(f"فشل التحميل: {str(e)}")

# -------------------- الإحالات --------------------
async def handle_referral(update: Update, context):
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
                user_id = update.effective_user.id
                if referrer_id != user_id:
                    c.execute("SELECT * FROM referrals WHERE referrer_id=? AND referred_id=?", (referrer_id, user_id))
                    if not c.fetchone():
                        c.execute("INSERT INTO referrals (referrer_id, referred_id, is_activated) VALUES (?, ?, 0)", (referrer_id, user_id))
                        conn.commit()
                        await update.message.reply_text("🎉 تم تسجيل إحالتك بنجاح!")
            except Exception as e:
                logger.error(f"Referral error: {e}")

# -------------------- القائمة الرئيسية --------------------
async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي وإحصائيات", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("🔗 الإحالات", callback_data="menu_referrals")],
        [InlineKeyboardButton("🎁 المكافآت اليومية", callback_data="menu_daily_bonus")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------- أوامر البوت --------------------
async def start(update: Update, context):
    user = update.effective_user
    user_id = user.id
    register_user(user_id, user.username, user.first_name)
    await handle_referral(update, context)

    c.execute("SELECT is_activated FROM referrals WHERE referred_id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0] == 0:
        c.execute("UPDATE referrals SET is_activated = 1 WHERE referred_id = ?", (user_id,))
        conn.commit()
        grant_referral_rewards(user_id)

    name = user.first_name or "صديقي"
    remaining = get_remaining_downloads(user_id)
    limit_text = "غير محدود 🚀" if remaining == -1 else f"متبقي {remaining} تحميلات اليوم"
    
    text = (
        f"🎬 أهلاً بك {name} في بوت التحميل الشامل 🎬\n\n"
        "📥 أرسل رابط فيديو من:\n"
        "✅ تيك توك | ✅ فيسبوك | ✅ تويتر\n"
        "✅ يوتيوب | ✅ انستجرام | ✅ كواي (تجريبي)\n\n"
        f"📊 حالتك: {limit_text}\n"
        f"⭐ VIP: تحميل غير محدود + بدون إعلانات\n\n"
        f"📞 للاستفسار أو الاشتراك: {ADMIN_USERNAME}\n\n"
        "اختر من القائمة:"
    )
    await update.message.reply_text(text, reply_markup=await main_menu())

# -------------------- المكافآت اليومية --------------------
async def daily_bonus(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    bonus_count = get_daily_bonus_count(uid)
    
    if bonus_count >= 3:
        text = "⚠️ لقد حصلت على مكافآتك اليومية الثلاثة اليوم!\nعد غداً لمزيد من المكافآت."
    else:
        bonus_amount = random.randint(1, 3)
        for _ in range(bonus_amount):
            decrement_daily_count(uid)
        add_daily_bonus(uid)
        text = f"🎁 تهانينا! حصلت على {bonus_amount} تحميلات إضافية اليوم!"
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------- الإحصائيات المتقدمة --------------------
async def advanced_stats(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    stats = get_user_stats(uid)
    
    c.execute("SELECT COUNT(*) FROM download_history WHERE user_id=? AND download_date LIKE ?", (uid, f"{datetime.now().strftime('%Y-%m-%d')}%"))
    today_downloads = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_activated=1", (uid,))
    active_referrals = c.fetchone()[0]
    
    text = (
        f"📊 **إحصائياتك الشخصية**\n\n"
        f"📥 إجمالي التحميلات: {stats['total']}\n"
        f"📈 تحميلات اليوم: {today_downloads}\n"
        f"⭐ المنصة المفضلة: {stats['favorite']}\n"
        f"🔗 مدعوون نشطون: {active_referrals}\n"
        f"👑 مشترك VIP: {'نعم ✅' if is_vip(uid) else 'لا ❌'}\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------- معالج الأزرار الرئيسي --------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    print(f"DEBUG: Button clicked with data: {data}")
    logger.info(f"Callback data received: {data}")

    if data == "menu_download":
        await query.edit_message_text(
            "📥 أرسل رابط الفيديو الآن\nلإلغاء العملية، اضغط /start",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
        )
    elif data == "menu_usage":
        uid = query.from_user.id
        if is_vip(uid):
            c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
            expiry = c.fetchone()[0]
            text = f"⭐ أنت مشترك VIP حتى {expiry} - لا حدود للتحميل"
        else:
            used = get_daily_count(uid)
            remain = DEFAULT_DAILY_LIMIT - used
            text = f"📊 استخدمت اليوم {used}/{DEFAULT_DAILY_LIMIT}\n📈 المتبقي: {remain} تحميلات\n\nلرفع الحد، اشترك في VIP"
        
        keyboard = [
            [InlineKeyboardButton("📈 إحصائيات متقدمة", callback_data="advanced_stats")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "menu_vip":
        uid = query.from_user.id
        if is_vip(uid):
            c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
            expiry = c.fetchone()[0]
            text = f"✅ أنت مشترك VIP حتى {expiry}\nشكراً لدعمك!"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
        else:
            keyboard = [
                [InlineKeyboardButton("⭐ دفع بالنجوم (أسبوعي)", callback_data="pay_stars_weekly")],
                [InlineKeyboardButton("⭐ دفع بالنجوم (شهري)", callback_data="pay_stars_monthly")],
                [InlineKeyboardButton("📞 تواصل مع المشرف", callback_data="contact_admin")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
            ]
            text = "⭐ باقات الاشتراك VIP ⭐\n\n• أسبوعي: 1$ - 7 أيام\n• شهري: 3$ - 30 يوماً\n• سنوي: 25$ - 365 يوماً\n\nمميزات VIP:\n✓ تحميل غير محدود\n✓ بدون إعلانات\n✓ جودة عالية\n\nاختر طريقة الاشتراك:"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "menu_referrals":
        uid = query.from_user.id
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_activated=1", (uid,))
        active = c.fetchone()[0]
        text = (
            f"🔗 **نظام الإحالات**\n\n"
            f"📋 رابط الإحالة الخاص بك:\n"
            f"`{link}`\n\n"
            f"📊 **إحصائياتك:**\n"
            f"👥 عدد المدعوين: {total}\n"
            f"✅ مدعوون نشطون: {active}\n\n"
            f"🎁 **المكافآت:**\n"
            f"• كل 5 مدعوين نشطين = يوم VIP مجاني\n"
            f"• كل 10 مدعوين نشطين = أسبوع VIP مجاني\n\n"
            f"📞 للاستفسار: {ADMIN_USERNAME}"
        )
        keyboard = [
            [InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_referral")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "copy_referral":
        uid = query.from_user.id
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
        await query.answer(f"✅ تم نسخ الرابط!\n{link}", show_alert=True)
    elif data == "menu_daily_bonus":
        await daily_bonus(update, context)
    elif data == "menu_policy":
        text = (
            "⚖️ **سياسة الاستخدام**\n\n"
            "1️⃣ المسؤولية على المستخدم.\n"
            "2️⃣ يمنع تحميل المواد المحمية.\n"
            "3️⃣ لا نخزن الملفات.\n"
            f"4️⃣ للشكاوى: {ADMIN_USERNAME}"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    elif data == "back":
        await query.edit_message_text("🏠 القائمة الرئيسية", reply_markup=await main_menu())
    elif data == "advanced_stats":
        await advanced_stats(update, context)
    elif data == "contact_admin":
        text = f"📞 للاشتراك عبر فودافون كاش: {VODAFONE_NUMBER}\n💰 أسبوعي 1$، شهري 3$، سنوي 25$\n📌 بعد التحويل تواصل مع {ADMIN_USERNAME} مع الإيصال."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_vip")]]))
    elif data == "pay_stars_weekly":
        await query.edit_message_text("⭐ جاري إرسال فاتورة الدفع بالنجوم للأسبوعي...")
        prices = [LabeledPrice("VIP أسبوعي", 100)]
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title="⭐ VIP أسبوعي",
            description="7 أيام تحميل غير محدود",
            payload="vip_weekly_stars",
            provider_token="",
            currency="XTR",
            prices=prices,
        )
    elif data == "pay_stars_monthly":
        await query.edit_message_text("⭐ جاري إرسال فاتورة الدفع بالنجوم للشهري...")
        prices = [LabeledPrice("VIP شهري", 300)]
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title="⭐ VIP شهري",
            description="30 يوماً تحميل غير محدود",
            payload="vip_monthly_stars",
            provider_token="",
            currency="XTR",
            prices=prices,
        )
    elif data == "cancel":
        await query.edit_message_text("❌ تم الإلغاء.", reply_markup=await main_menu())
    else:
        await query.edit_message_text("⚠️ زر غير معروف، استخدم القائمة الرئيسية.", reply_markup=await main_menu())

# -------------------- استلام الروابط (الإصلاح الرئيسي) --------------------
async def handle_link(update: Update, context):
    """معالج الروابط - يتم استدعاؤه عند إرسال المستخدم رابطاً"""
    uid = update.effective_user.id
    url = update.message.text.strip()
    
    print(f"DEBUG: Link received: {url}")
    logger.info(f"Link received from {uid}: {url}")
    
    platform = detect_platform(url)
    
    if platform == "غير معروف":
        await update.message.reply_text(
            "❌ الرابط غير مدعوم.\n\n"
            "المنصات المدعومة:\n"
            "✅ تيك توك\n✅ فيسبوك\n✅ تويتر\n✅ يوتيوب\n✅ انستجرام\n✅ كواي (تجريبي)"
        )
        return
    
    if platform == "تيك توك صورة":
        await update.message.reply_text("❌ هذا الرابط لصورة وليس فيديو.\nيرجى إرسال رابط فيديو.")
        return
    
    if not can_download(uid):
        await update.message.reply_text(
            f"⚠️ استنفدت تحميلات اليوم المجانية!\n"
            f"📊 استخدمت {get_daily_count(uid)}/{DEFAULT_DAILY_LIMIT}\n\n"
            "⭐ اشترك في VIP للتحميل غير المحدود"
        )
        return
    
    # حفظ الرابط والمنصة في context
    context.user_data["url"] = url
    context.user_data["platform"] = platform
    
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
    ]
    
    await update.message.reply_text(
        f"📌 **المنصة:** {platform}\n\n"
        f"اختر جودة التحميل:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def quality_callback(update: Update, context):
    """معالج اختيار جودة التحميل"""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    quality = "best" if query.data == "quality_best" else "worst"
    url = context.user_data.get("url")
    platform = context.user_data.get("platform", "غير معروف")
    
    if not url:
        await query.edit_message_text(
            "⚠️ انتهت صلاحية الرابط، أرسله مرة أخرى.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
        )
        return
    
    if not can_download(uid):
        await query.edit_message_text(
            "⚠️ تجاوزت الحد اليومي للتحميل.\n⭐ اشترك في VIP للاستمرار.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ اشتراك VIP", callback_data="menu_vip")]])
        )
        return
    
    await query.edit_message_text("⏳ جاري التحميل... قد يستغرق بضع ثوانٍ.")
    
    try:
        file_path = await download_video(url, quality)
        
        with open(file_path, "rb") as f:
            await context.bot.send_video(
                chat_id=uid, 
                video=f, 
                caption=f"✅ **تم التحميل بنجاح!**\n\n📌 المنصة: {platform}\n🎥 الجودة: {'عالية' if quality == 'best' else 'منخفضة'}"
            )
        
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if not is_vip(uid):
            increment_daily_count(uid)
        
        save_download_history(uid, platform)
        await send_promotion(uid, context)
        
        await context.bot.send_message(
            chat_id=uid, 
            text="🏠 **تم التحميل بنجاح!**\nاختر من القائمة:",
            parse_mode="Markdown",
            reply_markup=await main_menu()
        )
        
    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Download error: {e}")
        await context.bot.send_message(
            chat_id=uid, 
            text=f"❌ **فشل التحميل**\n\nالسبب: {error_msg}\n\n"
                 f"تأكد من:\n• الرابط صحيح\n• الفيديو ليس خاصاً\n\n📞 للدعم: {ADMIN_USERNAME}"
        )
    finally:
        context.user_data.pop("url", None)
        context.user_data.pop("platform", None)

# -------------------- الدفع والتحقق --------------------
async def precheckout_callback(update: Update, context):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_callback(update: Update, context):
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload
    days = 30 if "monthly" in payload else 7
    activate_vip(user_id, days)
    await update.message.reply_text(
        f"✅ **تم تفعيل اشتراك VIP بنجاح!**\n\n"
        f"📅 المدة: {days} يوماً\n🚀 تحميل غير محدود\n✨ بدون إعلانات\n\nاستمتع بالتحميل! 🎉"
    )

# -------------------- أوامر المشرف --------------------
async def activate_vip_cmd(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        activate_vip(user_id, days)
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً.")
    except:
        await update.message.reply_text("⚠️ الاستخدام: /activate_vip <user_id> <أيام>")

async def stats(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    
    total_users = c.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
    vip_count = c.execute("SELECT COUNT(*) FROM vip").fetchone()[0]
    today_downloads = c.execute("SELECT COUNT(*) FROM daily_downloads WHERE date=?", (datetime.now().strftime("%Y-%m-%d"),)).fetchone()[0]
    total_downloads = c.execute("SELECT COUNT(*) FROM download_history").fetchone()[0]
    total_referrals = c.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
    
    await update.message.reply_text(
        f"📊 **إحصائيات البوت**\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"👑 مشتركي VIP: {vip_count}\n"
        f"📥 تحميلات اليوم: {today_downloads}\n"
        f"📈 إجمالي التحميلات: {total_downloads}\n"
        f"🔗 إجمالي الإحالات: {total_referrals}\n"
        f"🚀 الإصدار: {BOT_VERSION}"
    )

# -------------------- التشغيل --------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip", activate_vip_cmd))
    app.add_handler(CommandHandler("stats", stats))

    # معالج الأزرار
    app.add_handler(CallbackQueryHandler(button_callback))

    # معالج جودة التحميل
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_"))

    # معالجات الدفع
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # معالج الروابط - الأهم
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info(f"✅ البوت يعمل - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()