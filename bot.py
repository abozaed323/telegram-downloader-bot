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

# ======================== الإعدادات الأساسية ========================
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"
ADMIN_ID = 7799287060          # ضع معرف المشرف الصحيح

BOT_VERSION = "4.2.0"
DEFAULT_DAILY_LIMIT = 5

# ======================== إعدادات الدفع الجديدة ========================
VODAFONE_NUMBER = "01040757693"
INSTAPAY_NUMBER = "01128085081"

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

# ======================== دوال VIP والحد اليومي ========================
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

def activate_vip(user_id: int, days: int):
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()

# ======================== الإعلانات للمستخدم المجاني ========================
ADVERTISEMENTS = [
    f"📢 اشترك في قناتنا @YourChannel للحصول على بوتات حصرية",
    f"⭐ باقات VIP تبدأ من 1$ فقط أسبوعياً، تواصل مع {ADMIN_USERNAME}",
    "🔥 البوت يدعم الآن تحميل البث المباشر من تيك توك!",
    "💎 اشترك الآن واحصل على تحميل غير محدود بدون إعلانات"
]

async def send_ad(user_id: int, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADVERTISEMENTS))

# ======================== تحميل الفيديو ========================
def detect_platform(url: str) -> str:
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

# ======================== نظام الإحالات ========================
async def handle_referral(update: Update, context):
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
                    await update.message.reply_text("🎉 تم تسجيل إحالتك! سيحصل من دعاك على مكافأة عند تفعيل اشتراكك.")
        except Exception as e:
            logger.error(f"Referral error: {e}")

# ======================== القائمة الرئيسية ========================
async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("🔗 نظام الإحالات", callback_data="menu_referrals")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context):
    await handle_referral(update, context)
    user = update.effective_user
    name = user.first_name or user.username or "صديقي"
    remaining = get_remaining_downloads(user.id)
    limit_text = "غير محدود 🚀" if remaining == -1 else f"متبقي {remaining} تحميلات اليوم"
    text = (
        f"🎬 **أهلاً بك {name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "✅ تيك توك (فيديو أو لايف)\n✅ فيسبوك\n✅ تويتر\n"
        "✅ يوتيوب (فيديو أو شورتس)\n✅ انستجرام (منشور، ريلز، استوري)\n\n"
        f"📊 **حالتك:** {limit_text}\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات\n\n"
        "اختر من القائمة:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=await main_menu())

# ======================== أزرار القائمة الرئيسية ========================
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
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
        expiry = c.fetchone()[0]
        text = f"⭐ **أنت مشترك VIP** حتى {expiry}\nلا حدود للتحميل اليومي"
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
            [InlineKeyboardButton("💳 طرق الدفع", callback_data="vip_payment_menu")],
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
            "اضغط على 💳 طرق الدفع لاختيار وسيلة الدفع المناسبة."
        )
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_referrals(update: Update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    bot_username = BOT_USERNAME
    referral_link = f"https://t.me/{bot_username}?start=ref_{uid}"
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_activated=1", (uid,))
    active = c.fetchone()[0]
    text = (
        "🔗 **نظام الإحالات** 🔗\n\nادعُ أصدقاءك واحصل على مكافآت!\n\n"
        f"📢 **رابط الإحالة الخاص بك:**\n`{referral_link}`\n\n"
        f"📊 **إحصائياتك:**\n• عدد المدعوين: {total}\n• مدعوون نشطون: {active}\n\n"
        "🎁 **المكافآت:**\nكل 5 مدعوين نشطين = يوم VIP مجاني\nكل 10 مدعوين نشطين = أسبوع VIP مجاني"
    )
    keyboard = [
        [InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_referral")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def copy_referral(update: Update, context):
    q = update.callback_query
    await q.answer("تم نسخ الرابط! أرسله لأصدقائك ✅", show_alert=True)

async def menu_policy(update: Update, context):
    q = update.callback_query
    await q.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ **المسؤولية:** المستخدم هو المسؤول الوحيد عن المحتوى الذي يقوم بتحميله أو مشاركته.\n"
        "2️⃣ **حقوق النشر:** يُمنع تحميل المواد المحمية بحقوق الطبع والنشر دون إذن مسبق.\n"
        "3️⃣ **الخصوصية:** لا نقوم بتخزين الملفات بعد إرسالها للمستخدم.\n"
        f"4️⃣ **الإبلاغ:** للشكاوى أو الاستفسارات، تواصل مع المشرف {ADMIN_USERNAME}\n\n"
        f"📩 {ADMIN_USERNAME}"
    )
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]))

async def back(update: Update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu(), parse_mode="Markdown")

# ======================== لوحة الدفع الاحترافية ========================
async def vip_payment_menu(update: Update, context):
    q = update.callback_query
    await q.answer()
    keyboard = [
        [InlineKeyboardButton("⭐ الدفع بالنجوم Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton("📱 فودافون كاش", callback_data="pay_vodafone")],
        [InlineKeyboardButton("🏦 إنستا باي", callback_data="pay_instapay")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back")],
    ]
    await q.edit_message_text(
        "💳 **اختر طريقة الدفع المناسبة**\n\n"
        "⭐ الدفع بالنجوم: تفعيل فوري تلقائي\n"
        "📱 فودافون كاش: تحويل ثم إرسال الإيصال\n"
        "🏦 إنستا باي: تحويل ثم إرسال الإيصال\n\n"
        f"للاستفسار: {ADMIN_USERNAME}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== دفع النجوم (مباشر) ==========
async def pay_stars(update: Update, context):
    q = update.callback_query
    await q.answer()
    prices = [LabeledPrice("VIP اشتراك أسبوعي", 100)]  # 100 نجمة
    await context.bot.send_invoice(
        chat_id=q.from_user.id,
        title="⭐ اشتراك VIP - أسبوعي",
        description="✅ تحميل غير محدود\n✅ بدون إعلانات\n✅ جودة عالية 4K",
        payload="vip_weekly_stars",
        provider_token="",  # يترك فارغاً للنجوم
        currency="XTR",
        prices=prices,
        need_name=False,
        need_phone_number=False,
        need_email=False
    )

async def precheckout_callback(update: Update, context):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_callback(update: Update, context):
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    activate_vip(user_id, 7)
    await update.message.reply_text(
        f"✅ **تم تفعيل اشتراك VIP بنجاح عبر النجوم!**\n\n📅 ينتهي في: {expiry}\n🎉 استمتع بالتحميل غير المحدود.",
        parse_mode="Markdown"
    )

# ========== فودافون كاش (يدوي مع إرسال الإيصال) ==========
async def pay_vodafone(update: Update, context):
    q = update.callback_query
    await q.answer()
    text = (
        f"📱 **الدفع عبر فودافون كاش**\n\n"
        f"🔹 **رقم الحساب:** `{VODAFONE_NUMBER}`\n"
        "🔹 **الاسم:** أحمد محمد\n\n"
        "💸 **المطلوب:** `1$` قيمة الاشتراك الأسبوعي\n\n"
        "📌 **بعد التحويل**، اضغط الزر أدناه لرفع صورة الإيصال مع معرفك التلقائي.\n"
        "🕒 سيتم التفعيل خلال 24 ساعة.\n\n"
        f"للاستفسار: {ADMIN_USERNAME}"
    )
    keyboard = [[InlineKeyboardButton("📸 إرسال إيصال الدفع", callback_data="send_receipt_vodafone")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== إنستا باي (يدوي مع إرسال الإيصال) ==========
async def pay_instapay(update: Update, context):
    q = update.callback_query
    await q.answer()
    text = (
        f"🏦 **الدفع عبر إنستا باي**\n\n"
        f"🔹 **رقم الهاتف:** `{INSTAPAY_NUMBER}`\n"
        "🔹 **الاسم:** أحمد محمد\n\n"
        "💸 **المطلوب:** `1$` أو ما يعادله بالجنيه\n\n"
        "📌 **بعد التحويل**، اضغط الزر أدناه لرفع صورة الإيصال مع معرفك التلقائي.\n"
        "🕒 سيتم التفعيل خلال 24 ساعة.\n\n"
        f"للاستفسار: {ADMIN_USERNAME}"
    )
    keyboard = [[InlineKeyboardButton("📸 إرسال إيصال الدفع", callback_data="send_receipt_instapay")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== معالج رفع الإيصال (لأي طريقة يدوية) ==========
async def request_receipt(update: Update, context, method: str):
    q = update.callback_query
    await q.answer()
    # نطلب من المستخدم رفع الصورة
    context.user_data["payment_method"] = method
    await q.edit_message_text(
        f"📸 **أرسل صورة الإيصال الآن**\n\n"
        f"- طريقة الدفع: {method}\n"
        f"- سيتم إرسال معرفك ({update.effective_user.id}) تلقائياً مع الصورة للمشرف.\n\n"
        "⚠️ تأكد من أن الصورة واضحة وتظهر عملية التحويل.\n"
        "🕒 سيتم التفعيل خلال 24 ساعة بعد استلام الإيصال.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="vip_payment_menu")]])
    )

async def send_receipt_vodafone(update: Update, context):
    await request_receipt(update, context, "فودافون كاش")

async def send_receipt_instapay(update: Update, context):
    await request_receipt(update, context, "إنستا باي")

# ========== استقبال صورة الإيصال من المستخدم ==========
async def handle_receipt_photo(update: Update, context):
    user = update.effective_user
    user_id = user.id
    user_name = user.username or user.first_name or "لا يوجد"
    method = context.user_data.get("payment_method", "غير محدد")

    # الحصول على الصورة
    photo_file = await update.message.photo[-1].get_file()
    photo_path = f"receipt_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await photo_file.download_to_drive(photo_path)

    # إرسال إشعار للمشرف مع الصورة والبيانات
    caption = (
        f"🧾 **طلب تفعيل VIP - إيصال دفع**\n\n"
        f"👤 **المستخدم:** [{user_name}](tg://user?id={user_id})\n"
        f"🆔 **المعرف:** `{user_id}`\n"
        f"💳 **طريقة الدفع:** {method}\n"
        f"📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"✅ **لتفعيل VIP استخدم:** `/activate_vip {user_id} 7`"
    )
    with open(photo_path, "rb") as photo:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo,
            caption=caption,
            parse_mode="Markdown"
        )
    # حذف الصورة من الخادم بعد الإرسال
    os.remove(photo_path)

    # تأكيد للمستخدم
    await update.message.reply_text(
        "✅ **تم استلام إيصالك بنجاح!**\n"
        "سيتواصل معك المشرف بعد التحقق من الدفع وتفعيل اشتراكك.\n"
        f"للاستفسار: {ADMIN_USERNAME}",
        parse_mode="Markdown"
    )
    # تنظيف
    context.user_data.pop("payment_method", None)

# ======================== معالج الروابط وجودة التحميل ========================
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
            f"⚠️ **استنفدت تحميلات اليوم المجانية**\n"
            f"📊 استخدمت {get_daily_count(uid)}/{DEFAULT_DAILY_LIMIT}\n"
            f"📈 المتبقي: {remain} تحميلات\n\n"
            "⭐ اشترك في VIP للتحميل غير المحدود\nاستخدم القائمة الرئيسية ← الاشتراك VIP",
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
    await q.edit_message_text("⏳ **جاري التحميل...**\nقد يستغرق بضع ثوانٍ.", parse_mode="Markdown")
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
            "تأكد من:\n• الرابط صحيح ويعمل\n• الفيديو ليس خاصاً أو محذوفاً\n• إذا كان بثاً مباشراً، قد تحتاج للانتظار حتى انتهائه",
            parse_mode="Markdown"
        )
    finally:
        context.user_data.pop("url", None)

# ======================== أوامر المشرف ========================
async def activate_vip(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        activate_vip(user_id, days)
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

# ======================== التشغيل الرئيسي ========================
def main():
    app = Application.builder().token(TOKEN).build()

    # الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip", activate_vip))
    app.add_handler(CommandHandler("stats", stats))

    # أزرار القائمة الرئيسية
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_referrals, pattern="^menu_referrals$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(copy_referral, pattern="^copy_referral$"))

    # لوحة الدفع
    app.add_handler(CallbackQueryHandler(vip_payment_menu, pattern="^vip_payment_menu$"))
    app.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars$"))
    app.add_handler(CallbackQueryHandler(pay_vodafone, pattern="^pay_vodafone$"))
    app.add_handler(CallbackQueryHandler(pay_instapay, pattern="^pay_instapay$"))
    app.add_handler(CallbackQueryHandler(send_receipt_vodafone, pattern="^send_receipt_vodafone$"))
    app.add_handler(CallbackQueryHandler(send_receipt_instapay, pattern="^send_receipt_instapay$"))

    # الدفع بالنجوم
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # استقبال صور الإيصالات
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt_photo))

    # جودة التحميل والروابط
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_(best|worst)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info(f"✅ البوت يعمل الآن - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()