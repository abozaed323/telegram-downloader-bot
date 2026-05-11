#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تحميل فيديوهات واستوريهات من تيك توك، فيسبوك، تويتر، يوتيوب، انستجرام
مع دعم اللايف من تيك توك، ونظام VIP، وإعلانات، وحدود تحميل يومية.
الإصدار 4.0 - شامل ومستقر.
"""

import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

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
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"  # ضع التوكن الصحيح هنا
ADMIN_USERNAME = "@Mac_0980"  # اسم المستخدم الخاص بك (المشرف)
BOT_USERNAME = "ShamelDownloaderBot"  # اسم بوتك

# إعدادات التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مجلد التحميلات المؤقتة
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ======================== قاعدة البيانات ========================
DB_PATH = "bot_data.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# جدول المشتركين VIP
c.execute("""
CREATE TABLE IF NOT EXISTS vip (
    user_id INTEGER PRIMARY KEY,
    expiry_date TEXT NOT NULL
)
""")

# جدول عدد التحميلات اليومية للمستخدمين المجانيين
c.execute("""
CREATE TABLE IF NOT EXISTS daily_downloads (
    user_id INTEGER,
    date TEXT,
    count INTEGER,
    PRIMARY KEY (user_id, date)
)
""")

conn.commit()

# ======================== وظائف VIP والحد اليومي ========================
def is_vip(user_id: int) -> bool:
    """التحقق ما إذا كان المستخدم لديه اشتراك VIP فعال"""
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry = datetime.strptime(row[0], "%Y-%m-%d")
            return expiry >= datetime.now()
        except Exception:
            return False
    return False

def get_daily_count(user_id: int) -> int:
    """عدد التحميلات التي قام بها المستخدم اليوم"""
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_count(user_id: int):
    """زيادة عدد التحميلات اليومية للمستخدم"""
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
        INSERT INTO daily_downloads (user_id, date, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date)
        DO UPDATE SET count = count + 1
    """, (user_id, today))
    conn.commit()

def can_download(user_id: int) -> bool:
    """تحديد ما إذا كان مسموح للمستخدم بالتحميل (VIP أو ضمن الحد)"""
    if is_vip(user_id):
        return True
    return get_daily_count(user_id) < 5

# ======================== إعلانات للمستخدم المجاني ========================
ADVERTISEMENTS = [
    "📢 **إعلان:** اشترك في قناتنا @YourChannel للحصول على بوتات حصرية.",
    "⭐ **باقات VIP:** تحميل غير محدود، بدون إعلانات، وأولوية في المعالجة. تواصل مع @Mac_0980.",
    "🔥 **ميزة جديدة:** البوت يدعم الآن تحميل البث المباشر من تيك توك!",
    "💎 **عرض خاص:** اشتراك VIP لمدة سنة بـ 25$ فقط (وفر 11$).",
    "📌 **تذكير:** أنت المسؤول الوحيد عن المحتوى الذي تقوم بتحميله."
]

async def send_ad_to_free_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """إرسال إعلان عشوائي للمستخدمين غير المشتركين VIP"""
    if not is_vip(user_id):
        ad = random.choice(ADVERTISEMENTS)
        await context.bot.send_message(chat_id=user_id, text=ad, parse_mode="Markdown")

# ======================== التعرف على المنصة ودعم اللايف ========================
def detect_platform(url: str) -> Tuple[str, bool]:
    """
    تحليل الرابط لتحديد المنصة وإذا كان بثاً مباشراً من تيك توك.
    تعيد: (اسم المنصة, هل هو لايف تيك توك)
    """
    url_lower = url.lower()
    is_live = False

    if "tiktok.com" in url_lower:
        if "/live" in url_lower or "?live" in url_lower or "live.tiktok.com" in url_lower:
            is_live = True
            return ("تيك توك لايف", True)
        return ("تيك توك", False)

    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return ("فيسبوك", False)
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return ("تويتر", False)
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return ("يوتيوب", False)
    if "instagram.com" in url_lower:
        return ("انستجرام", False)

    return ("غير معروف", False)

# ======================== تحميل الفيديو (عادي ولايف) ========================
async def download_video(url: str, quality: str = "best", is_live: bool = False) -> str:
    """
    تحميل فيديو عادي أو بث مباشر من تيك توك.
    تعيد مسار الملف المحمل.
    """
    # خيارات عامة
    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best" if quality == "best" else "worst",
        "ignoreerrors": True,
    }

    # إذا كان بثاً مباشراً، نضبط خيارات خاصة
    if is_live:
        ydl_opts["live_from_start"] = True   # يحاول البدء من بداية البث إذا كان لا يزال حياً
        ydl_opts["format"] = "best"          # اللايف عادةً جودة واحدة
        ydl_opts["wait_for_video"] = False   # لا ينتظر إذا لم يبدأ البث بعد

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # في بعض الأحيان قد يكون العنوان مختلفاً، نبحث عن أحدث ملف في المجلد
            if not os.path.exists(filename):
                files = os.listdir(DOWNLOAD_DIR)
                if files:
                    latest = max([os.path.join(DOWNLOAD_DIR, f) for f in files], key=os.path.getctime)
                    filename = latest
            return filename
        except Exception as e:
            # إذا فشل التحميل كبث مباشر، نحاول كفيديو عادي (قد يكون انتهى وصار متاحاً)
            if is_live:
                logger.warning(f"فشل تحميل البث المباشر، نحاول كفيديو عادي: {e}")
                return await download_video(url, quality, is_live=False)
            else:
                raise e

# ======================== القائمة الرئيسية (InlineKeyboard) ========================
async def main_menu_keyboard():
    """أزرار القائمة الرئيسية داخل الدردشة"""
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("📊 استهلاكي اليومي", callback_data="menu_usage")],
        [InlineKeyboardButton("⭐ الاشتراك / VIP", callback_data="menu_vip")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
        # يمكن إضافة زر معلومات البوت إذا أردت، لكن حسب الطلب تم إلغاؤه
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================== أمر /start ========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب وإظهار القائمة الرئيسية"""
    user = update.effective_user
    first_name = user.first_name if user.first_name else "صديقي"
    welcome_text = (
        f"🎬 **أهلاً بك {first_name} في بوت التحميل الشامل!** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "• تيك توك (فيديو أو بث مباشر)\n"
        "• فيسبوك\n• تويتر (X)\n• يوتيوب\n• انستجرام (منشورات، ريلز، استوريهات عامة)\n\n"
        "📊 **المستخدم المجاني:** 5 تحميلات يومياً\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات + جودة عالية\n\n"
        "⚠️ **تنبيه:** المسؤولية القانونية للمحتوى تقع على المستخدم وحده.\n\n"
        "استخدم الأزرار أدناه:"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=await main_menu_keyboard())

# ======================== القوائم الفرعية والأزرار ========================
async def menu_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الضغط على زر تحميل فيديو"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\n"
        "مثال للفيديو العادي: `https://www.tiktok.com/@user/video/123456789`\n"
        "مثال للبث المباشر: `https://www.tiktok.com/@user/live`\n\n"
        "لإلغاء العملية، أرسل /start.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_main")]])
    )

async def menu_usage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الضغط على زر استهلاكي اليومي"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if is_vip(user_id):
        # نحتاج إلى معرف تاريخ انتهاء الاشتراك
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
        expiry = c.fetchone()[0]
        text = f"⭐ **أنت مشترك VIP** – لا حدود للتحميل اليومي.\nينتهي اشتراكك في {expiry}."
    else:
        used = get_daily_count(user_id)
        remaining = max(0, 5 - used)
        text = f"📊 **استخدامك اليومي:** {used} من 5 تحميلات مجانية.\n📈 **المتبقي:** {remaining} تحميل.\n\nلرفع الحد إلى غير محدود، اشترك في VIP عبر القائمة الرئيسية."

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_main")]]))

async def menu_vip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الضغط على زر الاشتراك VIP"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if is_vip(user_id):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
        expiry = c.fetchone()[0]
        text = f"✅ **أنت بالفعل مشترك VIP حتى {expiry}**\nشكراً لدعمك المستمر! 🎉"
    else:
        text = (
            "⭐ **باقات VIP الاحترافية** ⭐\n\n"
            "• **أسبوعي:** 1$ (أو 2 نجوم تليجرام)\n"
            "• **شهري:** 3$ (أو 5 نجوم تليجرام)\n"
            "• **سنوي:** 25$ (توفير 11$)\n\n"
            "💳 **طرق الدفع المقبولة:**\n"
            "• نجوم تليجرام (Telegram Stars)\n"
            "• فودافون كاش: `0123456789`\n"
            "• إنستا باي: `instapay@example.com`\n\n"
            f"🔹 **بعد الدفع** أرسل صورة الإيصال إلى المشرف {ADMIN_USERNAME}\n"
            "سيتم تفعيل اشتراكك خلال 24 ساعة كحد أقصى.\n\n"
            "🔸 **للتجربة فقط:** أرسل الأمر `/activate_vip_test` (يمنحك VIP تجريبي لمدة ساعة واحدة)."
        )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_main")]]))

async def menu_policy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الضغط على زر سياسة الاستخدام"""
    query = update.callback_query
    await query.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ **المسؤولية القانونية:** المستخدم هو المسؤول الوحيد عن أي محتوى يقوم بتحميله أو إعادة نشره. هذا البوت مجرد أداة تقنية ولا يتحمل أي مسؤولية عن انتهاك حقوق النشر أو القوانين المحلية.\n\n"
        "2️⃣ **حقوق النشر:** يُمنع تحميل المواد المحمية بحقوق الطبع والنشر دون إذن مسبق. البوت لا يشجع على القرصنة.\n\n"
        "3️⃣ **الخصوصية:** لا نقوم بتخزين الملفات بعد إرسالها للمستخدم. سجلات التحميل محدودة بعدد الاستخدامات ولا تحتوي على بيانات تعريفية دائمة.\n\n"
        "4️⃣ **الإبلاغ:** لأصحاب الحقوق، يمكنكم التواصل مع المشرف {ADMIN_USERNAME} وسيتم حظر البوت فوراً عند تقديم شكوى موثقة.\n\n"
        "5️⃣ **التوفر:** قد يتعذر خدمة بعض الفيديوهات الخاصة أو المحظورة. لا نضمن استمرارية الخدمة إلى الأبد.\n\n"
        f"📩 **للاستفسارات أو الشكاوى:** {ADMIN_USERNAME}"
    ).replace("{ADMIN_USERNAME}", ADMIN_USERNAME)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_main")]]))

async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر الرجوع إلى القائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏠 **القائمة الرئيسية**\nاختر الخدمة التي تريدها:",
        parse_mode="Markdown",
        reply_markup=await main_menu_keyboard()
    )

# ======================== معالج الروابط وجودة التحميل ========================
async def handle_any_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أي رسالة نصية (يفترض أنها رابط)"""
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform, is_live = detect_platform(url)

    # التحقق من صحة الرابط
    if platform == "غير معروف":
        await update.message.reply_text(
            "❌ **رابط غير مدعوم**\n"
            "الروابط المقبولة فقط من:\n"
            "تيك توك (فيديو أو لايف)، فيسبوك، تويتر، يوتيوب، انستجرام.\n"
            "أعد إرسال رابط صحيح، أو استخدم /start للقائمة الرئيسية.",
            parse_mode="Markdown"
        )
        return

    # التحقق من حد التحميل اليومي
    if not can_download(user_id):
        await update.message.reply_text(
            "⚠️ **لقد استنفدت حد التحميلات المجاني اليومي (5/5)**\n"
            "لتتمكن من التحميل مجدداً، انتظر حتى الغد أو اشترك في VIP.\n"
            "استخدم القائمة الرئيسية لعرض باقات VIP (⭐ الاشتراك / VIP).",
            parse_mode="Markdown"
        )
        return

    # تخزين معلومات الرابط في سياق المستخدم مؤقتاً لحين اختيار الجودة
    context.user_data["pending_url"] = url
    context.user_data["pending_is_live"] = is_live

    # أزرار اختيار الجودة (مع تعليمات خاصة لللايف)
    if is_live:
        keyboard = [
            [InlineKeyboardButton("🎥 تحميل البث المباشر", callback_data="quality_best")],
            [InlineKeyboardButton("🔙 إلغاء", callback_data="quality_cancel")],
        ]
        await update.message.reply_text(
            f"📺 **منصة: {platform}**\n"
            "سيتم تحميل البث المباشر بأفضل جودة متاحة. قد يستغرق وقتاً أطول حسب طول البث.\n"
            "اضغط الزر أدناه لبدء التحميل:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🎥 جودة عالية (أفضل)", callback_data="quality_best")],
            [InlineKeyboardButton("📱 جودة منخفضة (موفرة للبيانات)", callback_data="quality_worst")],
            [InlineKeyboardButton("🔙 إلغاء", callback_data="quality_cancel")],
        ]
        await update.message.reply_text(
            f"📌 **المنصة:** {platform}\nاختر جودة التحميل المناسبة لك:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def quality_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار جودة التحميل (أو تأكيد تحميل اللايف)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    action = query.data  # quality_best, quality_worst, quality_cancel
    if action == "quality_cancel":
        await query.edit_message_text("❌ تم إلغاء عملية التحميل.")
        # تنظيف البيانات المؤقتة
        context.user_data.pop("pending_url", None)
        context.user_data.pop("pending_is_live", None)
        return

    # استرجاع الرابط من الجلسة
    url = context.user_data.get("pending_url")
    is_live = context.user_data.get("pending_is_live", False)
    if not url:
        await query.edit_message_text("⚠️ انتهت صلاحية الرابط، يرجى إرساله مرة أخرى.")
        return

    quality = "best" if action == "quality_best" else "worst"

    # إعادة التحقق من الحد اليومي (احتياطاً)
    if not can_download(user_id):
        await query.edit_message_text("⚠️ لقد تجاوزت الحد اليومي أثناء عملية الاختيار. اشترك في VIP.")
        return

    # إعلام المستخدم ببدء التحميل
    await query.edit_message_text("⏳ **جاري التحميل...**\nقد يستغرق بضع ثوانٍ حسب حجم الملف وسرعة السيرفر.")

    try:
        # تحميل الفيديو (أو البث)
        file_path = await download_video(url, quality, is_live)

        # إرسال الفيديو إلى المستخدم
        with open(file_path, "rb") as video_file:
            caption = "✅ **تم التحميل بنجاح!**\n"
            if is_vip(user_id):
                caption += "⭐ أنت مشترك VIP – استمتع بالتحميل غير المحدود."
            else:
                caption += "🚀 إذا أعجبك البوت، شاركه مع أصدقائك.\n⭐ للحصول على تجربة بدون إعلانات وبدون حدود، اشترك في VIP عبر القائمة الرئيسية."

            await query.message.reply_video(
                video=video_file,
                caption=caption,
                parse_mode="Markdown"
            )

        # حذف الملف من السيرفر
        os.remove(file_path)

        # تحديث عداد التحميلات للمستخدم المجاني
        increment_daily_count(user_id)

        # إرسال إعلان للمستخدم المجاني فقط
        await send_ad_to_free_user(user_id, context)

        # عرض القائمة الرئيسية تلقائياً بعد التحميل (اختياري)
        await query.message.reply_text(
            "🏠 **القائمة الرئيسية**\nاختر خدمة أخرى:",
            reply_markup=await main_menu_keyboard(),
            parse_mode="Markdown"
        )

    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"فشل التحميل للمستخدم {user_id}: {e}")
        await query.message.reply_text(
            f"❌ **فشلت عملية التحميل.**\n\nالسبب: {error_msg}\n\n"
            "تأكد من:\n"
            "- أن الرابط صحيح ويعمل (الفيديو ليس خاصاً أو محذوفاً).\n"
            "- للبث المباشر: إذا كان لا يزال يُبث، قد تحتاج إلى الانتظار حتى انتهائه ثم إعادة المحاولة.\n"
            "- اتصالك بالإنترنت (من جهة السيرفر).\n\n"
            "إذا تكررت المشكلة، أبلغ المشرف.",
            parse_mode="Markdown"
        )
    finally:
        # حذف البيانات المؤقتة
        context.user_data.pop("pending_url", None)
        context.user_data.pop("pending_is_live", None)

# ======================== أوامر VIP التجريبية والمشرف ========================
async def test_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل VIP تجريبي لمدة ساعة (لأغراض الاختبار فقط)"""
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    await update.message.reply_text(
        "✅ **تم تفعيل الاشتراك التجريبي VIP لمدة ساعة واحدة.**\n"
        "استمتع بالتحميل غير المحدود وبدون إعلانات خلال هذه الفترة.\n"
        "بعد انتهاء الصلاحية، ستعود إلى الخطة المجانية (5 تحميلات يومياً).",
        parse_mode="Markdown"
    )

async def manual_activate_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر للمشرف لتفعيل VIP يدوياً (للمستخدمين الذين دفعوا)"""
    ADMIN_ID = 123456789  # ⚠️ استبدل هذا برقم معرفك من تليجرام (جربه من @userinfobot)
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر مخصص فقط لمشرف البوت.")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
        conn.commit()
        await update.message.reply_text(
            f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً.\nينتهي في {expiry}."
        )
    except Exception:
        await update.message.reply_text(
            "⚠️ الاستخدام الصحيح: `/activate_vip <user_id> <عدد_الأيام>`\n"
            "مثال: `/activate_vip 123456789 30`",
            parse_mode="Markdown"
        )

# ======================== الدالة الرئيسية ========================
def main():
    """تشغيل البوت وتسجيل المعالجات"""
    app = Application.builder().token(TOKEN).build()

    # الأوامر النصية
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("activate_vip_test", test_vip_command))
    app.add_handler(CommandHandler("activate_vip", manual_activate_vip))

    # معالجات الأزرار (القوائم)
    app.add_handler(CallbackQueryHandler(menu_download_callback, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_usage_callback, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_vip_callback, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_policy_callback, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(back_to_main_callback, pattern="^back_to_main$"))

    # معالج الروابط (أي نص ليس أمراً)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_link))

    # معالج اختيار الجودة
    app.add_handler(CallbackQueryHandler(quality_selection_callback, pattern="^(quality_best|quality_worst|quality_cancel)$"))

    # بدء البوت
    logger.info("✅ البوت يعمل الآن بكفاءة عالية مع جميع الأزرار ودعم اللايف.")
    app.run_polling()

if __name__ == "__main__":
    main()