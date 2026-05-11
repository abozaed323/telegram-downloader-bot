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

# -------------------------------------------------------------------
# الإعدادات الأساسية (ثابتة)
# -------------------------------------------------------------------
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"
ADMIN_ID = 7799287060          # معرف المشرف (ضروري لأمر التفعيل)
BOT_VERSION = "6.0.0"
DEFAULT_DAILY_LIMIT = 5

# أرقام الدفع للتواصل مع المشرف
VODAFONE_NUMBER = "01040757693"
INSTAPAY_NUMBER = "01128085081"

# مفتاح Ammer Pay (للاستخدام المستقبلي فقط)
AMMER_PAY_API_KEY = "5775769170:LIVE:TG_LgpGu_wx9zf4gv6tdgdBYZ0A"

# -------------------------------------------------------------------
# إعدادات التسجيل والمجلدات
# -------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# -------------------------------------------------------------------
# قاعدة البيانات (تبقى كما هي)
# -------------------------------------------------------------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
c = conn.cursor()

c.execute("CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL)")
c.execute("CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))")
c.execute("CREATE TABLE IF NOT EXISTS referrals (referrer_id INTEGER, referred_id INTEGER, date TEXT DEFAULT CURRENT_TIMESTAMP, is_activated INTEGER DEFAULT 0, PRIMARY KEY (referrer_id, referred_id))")
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
    c.execute("INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1", (user_id, today))
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

# -------------------------------------------------------------------
# رسالة دعائية بعد التحميل (تحتوي على يوزر المشرف)
# -------------------------------------------------------------------
PROMO_MESSAGE = (
    f"🎁 **اشترك في قناتنا** 🎁\n"
    f"https://t.me/dawinlod\n\n"
    f"🔥 **عرض خاص:**\n"
    f"كل من يشترك في القناة ويبلغ المشرف {ADMIN_USERNAME}، يحصل على **5 تحميلات مجانية إضافية** كهدية!\n"
    f"ادعم صديقك وشارك القناة مع أصدقائك.\n\n"
    f"📞 للاشتراك VIP أو الاستفسار: {ADMIN_USERNAME}"
)

async def send_promotion(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=user_id, text=PROMO_MESSAGE, parse_mode="Markdown")

# -------------------------------------------------------------------
# تحميل الفيديو
# -------------------------------------------------------------------
def detect_platform(url: str):
    u = url.lower()
    if "tiktok.com" in u:
        if "/photo/" in u:
            return "تيك توك صورة"
        if "/live" in u or "?live" in u:
            return "تيك توك لايف"
        return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u: return "فيسبوك"
    if "twitter.com" in u or "x.com" in u: return "تويتر"
    if "youtube.com" in u or "youtu.be" in u: return "يوتيوب"
    if "instagram.com" in u: return "انستجرام"
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
    if "/photo/" in url:
        raise Exception("هذا الرابط لصورة وليس فيديو. يرجى إرسال رابط فيديو (يحتوي على /video/ أو /live/).")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir(DOWNLOAD_DIR)
            if files:
                filename = os.path.join(DOWNLOAD_DIR, max([os.path.join(DOWNLOAD_DIR, f) for f in files], key=os.path.getctime))
        return filename

# -------------------------------------------------------------------
# نظام الإحالات
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# القائمة الرئيسية
# -------------------------------------------------------------------
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
        f"📞 للاستفسار أو الاشتراك: {ADMIN_USERNAME}\n\n"
        "اختر من القائمة:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=await main_menu())

# -------------------------------------------------------------------
# أزرار القائمة الرئيسية
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# قسم VIP الجديد (بدون قائمة طرق دفع معقدة)
# -------------------------------------------------------------------
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
        # زر واحد فقط: اشتراك VIP يفتح خيارين: نجوم أو تواصل مع المشرف
        keyboard = [
            [InlineKeyboardButton("⭐ دفع بالنجوم (تفعيل فوري)", callback_data="pay_stars")],
            [InlineKeyboardButton("📞 تواصل مع المشرف للاشتراك", callback_data="contact_admin")],
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
            "اختر طريقة الاشتراك:"
        )
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def contact_admin(update: Update, context):
    q = update.callback_query
    await q.answer()
    text = (
        f"📞 **للاشتراك عبر فودافون كاش أو إنستا باي**\n\n"
        f"📱 **فودافون كاش:** `{VODAFONE_NUMBER}`\n"
        f"🏦 **إنستا باي:** `{INSTAPAY_NUMBER}`\n\n"
        f"💰 **المبلغ:** 1$ للأسبوع، 3$ للشهر، 25$ للسنة\n\n"
        f"📌 **بعد التحويل**، تواصل مع المشرف {ADMIN_USERNAME} وأرسل صورة الإيصال مع معرف التليجرام الخاص بك.\n"
        f"🕒 سيتم تفعيل اشتراكك خلال 24 ساعة.\n\n"
        f"للاستفسار: {ADMIN_USERNAME}"
    )
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="menu_vip")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# -------------------------------------------------------------------
# دفع النجوم (مباشر)
# -------------------------------------------------------------------
async def pay_stars(update: Update, context):
    q = update.callback_query
    await q.answer()
    prices = [LabeledPrice("VIP اشتراك أسبوعي", 100)]
    await context.bot.send_invoice(
        chat_id=q.from_user.id,
        title="⭐ اشتراك VIP - أسبوعي",
        description="✅ تحميل غير محدود\n✅ بدون إعلانات\n✅ جودة عالية 4K",
        payload="vip_weekly_stars",
        provider_token="",
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
    activate_vip(user_id, 7)
    await update.message.reply_text(
        f"✅ **تم تفعيل اشتراك VIP بنجاح عبر النجوم!**\n\n📅 لمدة 7 أيام.\n🎉 استمتع بالتحميل غير المحدود.\n\n📞 للاستفسار: {ADMIN_USERNAME}",
        parse_mode="Markdown"
    )

# -------------------------------------------------------------------
# باقي أزرار القائمة (الإحالات، سياسة، رجوع)
# -------------------------------------------------------------------
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
        "🎁 **المكافآت:**\nكل 5 مدعوين نشطين = يوم VIP مجاني\nكل 10 مدعوين نشطين = أسبوع VIP مجاني\n\n"
        f"📞 للاستفسار: {ADMIN_USERNAME}"
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

# -------------------------------------------------------------------
# معالج الروابط وجودة التحميل
# -------------------------------------------------------------------
async def handle_link(update: Update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    if platform == "غير معروف":
        await update.message.reply_text("❌ الرابط غير مدعوم. أرسل رابطاً من إحدى المنصات المدعومة.")
        return
    if platform == "تيك توك صورة":
        await update.message.reply_text("❌ هذا الرابط لصورة وليس فيديو. يرجى إرسال رابط فيديو.")
        return
    if not can_download(uid):
        await update.message.reply_text(
            f"⚠️ **استنفدت تحميلات اليوم المجانية**\n"
            f"📊 استخدمت {get_daily_count(uid)}/{DEFAULT_DAILY_LIMIT}\n\n"
            "⭐ اشترك في VIP للتحميل غير المحدود.\nاستخدم القائمة الرئيسية ← الاشتراك VIP",
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
            await q.message.reply_video(video, caption="✅ **تم التحميل بنجاح!**", parse_mode="Markdown")
        os.remove(file_path)
        if not is_vip(uid):
            increment_daily_count(uid)
        await send_promotion(uid, context)
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

# -------------------------------------------------------------------
# أوامر المشرف
# -------------------------------------------------------------------
async def activate_vip(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        activate_vip(user_id, days)
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً.")
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
        f"🚀 الإصدار: {BOT_VERSION}\n"
        f"📞 المشرف: {ADMIN_USERNAME}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# -------------------------------------------------------------------
# التشغيل الرئيسي
# -------------------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip", activate_vip))
    app.add_handler(CommandHandler("stats", stats))

    # أزرار القائمة
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_referrals, pattern="^menu_referrals$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(copy_referral, pattern="^copy_referral$"))

    # أزرار الاشتراك الجديدة
    app.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars$"))
    app.add_handler(CallbackQueryHandler(contact_admin, pattern="^contact_admin$"))

    # دفع النجوم
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # تحميل
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_(best|worst)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info(f"✅ البوت يعمل الآن - الإصدار {BOT_VERSION}")
    app.run_polling()

if __name__ == "__main__":
    main()