#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import sqlite3
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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
TOKEN = os.getenv("BOT_TOKEN", "8640536149:AAFYu8mB_WDxbsgJHIQS4JERgS4_JiJqidI")
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "Down1loderBot"  # غير هذا لاسم البوت الجديد
ADMIN_ID = 7799287060
BOT_VERSION = "9.0.0"
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
CREATE TABLE IF NOT EXISTS favorite_platforms (
    user_id INTEGER PRIMARY KEY,
    platform TEXT DEFAULT 'all'
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
CREATE TABLE IF NOT EXISTS scheduled_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    url TEXT,
    schedule_time TEXT,
    status TEXT DEFAULT 'pending'
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

def can_download(user_id: int) -> bool:
    return is_vip(user_id) or get_daily_count(user_id) < DEFAULT_DAILY_LIMIT

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

def get_daily_bonus(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT bonus_count FROM daily_bonus WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    if row:
        return row[0]
    return 0

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
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].replace("ref_", ""))
            user_id = update.effective_user.id
            if referrer_id != user_id:
                c.execute("SELECT * FROM referrals WHERE referrer_id=? AND referred_id=?", (referrer_id, user_id))
                if not c.fetchone():
                    c.execute("INSERT INTO referrals (referrer_id, referred_id, is_activated) VALUES (?, ?, 0)", (referrer_id, user_id))
                    conn.commit()
                    await update.message.reply_text("🎉 تم تسجيل إحالتك! سيحصل من دعاك على مكافأة عند تفعيل اشتراكك.")
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
        [InlineKeyboardButton("📅 تحميل مجدول", callback_data="menu_scheduled")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings")],
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
        "📥 أرسل رابط فيديو من:\n✅ تيك توك\n✅ فيسبوك\n✅ تويتر\n✅ يوتيوب\n✅ انستجرام\n✅ كواي (تجريبي)\n\n"
        f"📊 حالتك: {limit_text}\n⭐ VIP: تحميل غير محدود + بدون إعلانات\n\n"
        f"📞 للاستفسار أو الاشتراك: {ADMIN_USERNAME}\n\nاختر من القائمة:"
    )
    await update.message.reply_text(text, reply_markup=await main_menu())

# -------------------- الميزة 1: المكافآت اليومية --------------------
async def daily_bonus(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT bonus_count FROM daily_bonus WHERE user_id=? AND date=?", (uid, today))
    row = c.fetchone()
    
    if row:
        bonus_count = row[0]
        if bonus_count >= 3:
            text = "⚠️ لقد حصلت على مكافآتك اليومية الثلاثة اليوم! عد غداً لمزيد من المكافآت."
        else:
            bonus_amount = random.randint(1, 3)
            # منح تحميلات إضافية
            for _ in range(bonus_amount):
                increment_daily_count(uid)
                increment_daily_count(uid)  # عكسياً لأن increment_daily_count يزيد العدد
            text = f"🎁 تهانينا! حصلت على {bonus_amount} تحميلات إضافية اليوم!"
            add_daily_bonus(uid)
    else:
        bonus_amount = random.randint(1, 5)
        for _ in range(bonus_amount):
            increment_daily_count(uid)
            increment_daily_count(uid)
        text = f"🎁 مكافأة الترحيب! حصلت على {bonus_amount} تحميلات إضافية!"
        add_daily_bonus(uid)
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------- الميزة 2: التحميل المجدول --------------------
async def scheduled_download_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة تحميل مجدول", callback_data="schedule_add")],
        [InlineKeyboardButton("📋 قائمة التحميلات المجدولة", callback_data="schedule_list")],
        [InlineKeyboardButton("🗑️ حذف تحميل مجدول", callback_data="schedule_delete")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    await query.edit_message_text(
        "📅 التحميل المجدول\n\nيمكنك جدولة تحميل الفيديوهات في وقت محدد.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def schedule_add(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏰ أرسل رابط الفيديو ثم الوقت (مثال: 2024-12-31 15:30:00)\n\n"
        "لإلغاء العملية، اضغط /cancel",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_scheduled")]])
    )
    context.user_data["waiting_for_schedule"] = True

# -------------------- الميزة 3: الإحصائيات المتقدمة --------------------
async def advanced_stats(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    stats = get_user_stats(uid)
    total_downloads = stats["total"]
    favorite = stats["favorite"]
    
    c.execute("SELECT COUNT(*) FROM download_history WHERE user_id=? AND download_date LIKE ?", (uid, f"{datetime.now().strftime('%Y-%m-%d')}%"))
    today_downloads = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_activated=1", (uid,))
    active_referrals = c.fetchone()[0]
    
    text = (
        f"📊 **إحصائياتك الشخصية**\n\n"
        f"📥 إجمالي التحميلات: {total_downloads}\n"
        f"📈 تحميلات اليوم: {today_downloads}\n"
        f"⭐ المنصة المفضلة: {favorite}\n"
        f"🔗 مدعوون نشطون: {active_referrals}\n"
        f"👑 مشترك VIP: {'نعم' if is_vip(uid) else 'لا'}\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------- الميزة 4: الإعدادات (المنصة المفضلة) --------------------
async def settings_menu(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    c.execute("SELECT platform FROM favorite_platforms WHERE user_id=?", (uid,))
    row = c.fetchone()
    current = row[0] if row else "all"
    
    keyboard = [
        [InlineKeyboardButton("🎯 يوتيوب", callback_data="set_platform_youtube")],
        [InlineKeyboardButton("🎯 تيك توك", callback_data="set_platform_tiktok")],
        [InlineKeyboardButton("🎯 فيسبوك", callback_data="set_platform_facebook")],
        [InlineKeyboardButton("🎯 انستجرام", callback_data="set_platform_instagram")],
        [InlineKeyboardButton("🎯 تويتر", callback_data="set_platform_twitter")],
        [InlineKeyboardButton("🌐 الكل", callback_data="set_platform_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    
    text = f"⚙️ الإعدادات\n\nالمنصة المفضلة حالياً: {current}\n\nاختر منصتك المفضلة للحصول على توصيات مخصصة:"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_platform(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    platform = query.data.replace("set_platform_", "")
    
    c.execute("INSERT OR REPLACE INTO favorite_platforms (user_id, platform) VALUES (?, ?)", (uid, platform))
    conn.commit()
    
    await query.edit_message_text(
        f"✅ تم تعيين المنصة المفضلة إلى: {platform}\n\nسيتم تخصيص التوصيات بناءً على اختيارك.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_settings")]])
    )

# -------------------- الميزة 5: التوصيات والمحتوى المقترح --------------------
async def recommendations(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    
    c.execute("SELECT platform FROM favorite_platforms WHERE user_id=?", (uid,))
    row = c.fetchone()
    platform = row[0] if row else "all"
    
    recommendations_dict = {
        "youtube": "🎬 قنوات يوتيوب مقترحة:\n• قناة الألعاب\n• قناة التعليم\n• قناة الطبخ",
        "tiktok": "🎵 حسابات تيك توك مقترحة:\n• حسابات كوميدية\n• حسابات تعليمية\n• حسابات فنون",
        "facebook": "📘 صفحات فيسبوك مقترحة:\n• صفحات أخبار\n• صفحات ترفيه\n• صفحات تقنية",
        "instagram": "📸 حسابات انستجرام مقترحة:\n• مصورين محترفين\n• مؤثرين\n• علامات تجارية",
        "twitter": "🐦 حسابات تويتر مقترحة:\n• أخبار عاجلة\n• محللين سياسيين\n• تقنيين",
        "all": "🌟 محتوى مقترح عام:\n• أفضل فيديوهات الأسبوع\n• فيديوهات تعليمية مميزة\n• محتوى ترفيهي حصري"
    }
    
    text = recommendations_dict.get(platform, recommendations_dict["all"])
    text += "\n\n📌 سيتم تحديث التوصيات يومياً!"
    
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث التوصيات", callback_data="recommendations")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

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
        
        stats_btn = [[InlineKeyboardButton("📈 إحصائيات متقدمة", callback_data="advanced_stats")]]
        stats_btn.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(stats_btn))
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
            text = "⭐ باقات الاشتراك VIP ⭐\n\n• أسبوعي: 1$ - 7 أيام\n• شهري: 3$ - 30 يوماً\n• سنوي: 25$ - 365 يوماً\n\nمميزات VIP:\n✓ تحميل غير محدود\n✓ بدون إعلانات\n✓ جودة عالية\n✓ أولوية في التحميل\n✓ دعم فني مخصص\n\nاختر طريقة الاشتراك:"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "menu_referrals":
        uid = query.from_user.id
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_activated=1", (uid,))
        active = c.fetchone()[0]
        text = (
            f"🔗 نظام الإحالات\n\nرابط الإحالة الخاص بك:\n`{link}`\n\nإحصائياتك:\nالمدعوين: {total}\nنشطون: {active}\n\nكل 5 نشطين = يوم VIP مجاني\nكل 10 نشطين = أسبوع VIP مجاني\n\nللاستفسار: {ADMIN_USERNAME}"
        )
        keyboard = [
            [InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_referral")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "copy_referral":
        uid = query.from_user.id
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
        await query.answer(f"تم نسخ الرابط: {link}", show_alert=True)
    elif data == "menu_daily_bonus":
        await daily_bonus(update, context)
    elif data == "menu_scheduled":
        await scheduled_download_menu(update, context)
    elif data == "schedule_add":
        await schedule_add(update, context)
    elif data == "schedule_list":
        await query.edit_message_text("⏳ قائمة التحميلات المجدولة قيد التطوير...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_scheduled")]]))
    elif data == "schedule_delete":
        await query.edit_message_text("🗑️ حذف التحميلات المجدولة قيد التطوير...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_scheduled")]]))
    elif data == "menu_settings":
        await settings_menu(update, context)
    elif data.startswith("set_platform_"):
        await set_platform(update, context)
    elif data == "recommendations":
        await recommendations(update, context)
    elif data == "advanced_stats":
        await advanced_stats(update, context)
    elif data == "menu_policy":
        text = "⚖️ سياسة الاستخدام\n\n1️⃣ المسؤولية على المستخدم.\n2️⃣ يمنع تحميل المواد المحمية.\n3️⃣ لا نخزن الملفات.\n4️⃣ للشكاوى: " + ADMIN_USERNAME
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))
    elif data == "back":
        await query.edit_message_text("🏠 القائمة الرئيسية", reply_markup=await main_menu())
    elif data == "contact_admin":
        text = f"📞 للاشتراك عبر فودافون كاش: {VODAFONE_NUMBER}\n💰 أسبوعي 1$، شهري 3$، سنوي 25$\n📌 بعد التحويل تواصل مع {ADMIN_USERNAME} مع الإيصال."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_vip")]]))
    elif data == "pay_stars_weekly":
        await query.edit_message_text("⭐ سيتم إرسال فاتورة الدفع بالنجوم للأسبوعي...")
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
        await query.edit_message_text("⭐ سيتم إرسال فاتورة الدفع بالنجوم للشهري...")
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

# -------------------- استلام الروابط واختيار الجودة --------------------
async def handle_link(update: Update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    if platform == "غير معروف":
        await update.message.reply_text("❌ الرابط غير مدعوم.")
        return
    if platform == "تيك توك صورة":
        await update.message.reply_text("❌ هذا الرابط لصورة وليس فيديو.")
        return
    if not can_download(uid):
        await update.message.reply_text("⚠️ استنفدت تحميلات اليوم المجانية. اشترك VIP.")
        return
    context.user_data["url"] = url
    context.user_data["platform"] = platform
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
    ]
    await update.message.reply_text(f"📌 المنصة: {platform}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def quality_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    quality = "best" if query.data == "quality_best" else "worst"
    url = context.user_data.get("url")
    platform = context.user_data.get("platform", "غير معروف")
    if not url:
        await query.edit_message_text("⚠️ انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    if not can_download(uid):
        await query.edit_message_text("⚠️ تجاوزت الحد اليومي. اشترك VIP.")
        return
    await query.edit_message_text("⏳ جاري التحميل...")
    try:
        file_path = await download_video(url, quality)
        with open(file_path, "rb") as f:
            await context.bot.send_video(chat_id=uid, video=f, caption="✅ تم التحميل!")
        os.remove(file_path)
        if not is_vip(uid):
            increment_daily_count(uid)
        save_download_history(uid, platform)
        await send_promotion(uid, context)
        await context.bot.send_message(chat_id=uid, text="🏠 القائمة الرئيسية", reply_markup=await main_menu())
    except Exception as e:
        await context.bot.send_message(chat_id=uid, text=f"❌ فشل التحميل: {str(e)[:150]}")
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
    await update.message.reply_text(f"✅ تم تفعيل VIP لمدة {days} يوماً! استمتع.")

# -------------------- أوامر المشرف --------------------
async def activate_vip_cmd(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ للمشرف فقط.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        activate_vip(user_id, days)
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً.")
    except:
        await update.message.reply_text("⚠️ استخدم: /activate_vip <user_id> <أيام>")

async def stats(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ للمشرف فقط.")
        return
    total_users = c.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
    vip_count = c.execute("SELECT COUNT(*) FROM vip").fetchone()[0]
    today_downloads = c.execute("SELECT COUNT(*) FROM daily_downloads WHERE date=?", (datetime.now().strftime("%Y-%m-%d"),)).fetchone()[0]
    total_downloads = c.execute("SELECT COUNT(*) FROM download_history").fetchone()[0]
    total_referrals = c.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
    await update.message.reply_text(
        f"📊 **إحصائيات البوت**\n\n"
        f"👥 مستخدمين: {total_users}\n"
        f"👑 VIP: {vip_count}\n"
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

    # معالج الأزرار العام
    app.add_handler(CallbackQueryHandler(button_callback))

    # معالج جودة التحميل
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_"))

    # معالجات الدفع
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # معالج الروابط
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info(f"✅ البوت يعمل - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()