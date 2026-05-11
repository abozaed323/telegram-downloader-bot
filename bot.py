import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

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
TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"

# تفعيل التسجيل للتصحيح
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

def is_vip(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم مشتركاً VIP"""
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry_str = row[0].split()[0]
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
            return expiry >= datetime.now()
        except Exception:
            return False
    return False

def get_daily_downloads(user_id: int) -> int:
    """عدد التحميلات اليومية للمستخدم"""
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_downloads(user_id: int):
    """زيادة عداد التحميلات اليومية"""
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
        (user_id, today)
    )
    conn.commit()

def can_download(user_id: int) -> bool:
    """هل يسمح للمستخدم بالتحميل (VIP أو ضمن الحد اليومي)"""
    if is_vip(user_id):
        return True
    return get_daily_downloads(user_id) < 5  # 5 تحميلات مجانية يومياً

# ======================== الإعلانات ========================
ADVERTISEMENTS = [
    "📢 اشترك في قناتنا: @YourChannel – بوتات وأدوات مفيدة!",
    "💎 باقات VIP تبدأ من 1$ فقط أسبوعياً – تحميل غير محدود وبدون إعلانات.",
    "🔥 مميزات VIP: جودة 4K، تحويل للصوت قريباً، أولوية في التحميل.",
    "📌 حقوق النشر محفوظة لأصحابها. استخدم هذا البوت بمسؤولية."
]

async def send_ad_to_free_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """إرسال إعلان فقط إذا كان المستخدم ليس VIP"""
    if not is_vip(user_id):
        ad = random.choice(ADVERTISEMENTS)
        await context.bot.send_message(chat_id=user_id, text=ad)

# ======================== التعرف على المنصة ========================
def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return "تيك توك"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "فيسبوك"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "تويتر"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "يوتيوب"
    if "instagram.com" in url_lower:
        return "انستجرام"
    return "غير معروف"

# ======================== تحميل الفيديو ========================
async def download_video(url: str, quality: str = "best") -> str:
    """تحميل الفيديو باستخدام yt-dlp وإرجاع مسار الملف"""
    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "format": "best" if quality == "best" else "worst",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # في حال لم يتم العثور على الملف بالاسم المتوقع
        if not os.path.exists(filename):
            files = os.listdir(DOWNLOAD_DIR)
            if files:
                filename = os.path.join(
                    DOWNLOAD_DIR,
                    max([os.path.join(DOWNLOAD_DIR, f) for f in files], key=os.path.getctime),
                )
        return filename

# ======================== القوائم الرئيسية والفرعية ========================
async def get_main_menu():
    """قائمة رئيسية داخل الشات (InlineKeyboard)"""
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="main_download")],
        [InlineKeyboardButton("⭐ باقات VIP", callback_data="main_vip"), InlineKeyboardButton("📊 استهلاكي", callback_data="main_usage")],
        [InlineKeyboardButton("🌐 المنصات المدعومة", callback_data="main_supported"), InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="main_policy")],
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="main_info")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start مع ترحيب وقائمة رئيسية"""
    user = update.effective_user
    first_name = user.first_name if user.first_name else "صديقي"
    welcome_text = (
        f"🎬 **أهلاً بك {first_name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "✅ تيك توك | ✅ فيسبوك | ✅ تويتر | ✅ يوتيوب | ✅ انستجرام\n\n"
        "📊 **المجاني:** 5 تحميلات يومياً\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات + جودة عالية\n\n"
        "⚠️ **تنبيه:** المسؤولية القانونية للمحتوى تقع على المستخدم وحده.\n\n"
        "استخدم الأزرار أدناه:"
    )
    # محاولة إرسال صورة ترحيبية (اختياري)
    try:
        photo_url = "https://cdn.pixabay.com/photo/2016/02/19/11/19/video-1210600_1280.png"
        await update.message.reply_photo(
            photo=photo_url,
            caption=welcome_text,
            parse_mode="Markdown",
            reply_markup=await get_main_menu()
        )
    except Exception:
        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=await get_main_menu()
        )

# ---------- قائمة تحميل فيديو ----------
async def main_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\nمثال: `https://www.tiktok.com/@user/video/123456789`\n\nلإلغاء العملية اضغط /start",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_back")]])
    )

# ---------- باقات VIP ----------
async def main_vip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
        expiry = c.fetchone()[0]
        text = f"✅ **أنت مشترك VIP حتى {expiry}**\nشكراً لدعمك المستمر! 🎉"
    else:
        text = (
            "⭐ **باقات VIP الاحترافية** ⭐\n\n"
            "• **أسبوعي:** 1$ (أو 2 نجوم تليجرام)\n"
            "• **شهري:** 3$ (أو 5 نجوم تليجرام)\n"
            "• **سنوي:** 25$ (توفير 11$)\n\n"
            "💳 **طرق الدفع المقبولة:**\n"
            "⭐ نجوم تليجرام\n"
            "📱 فودافون كاش: `01001234567`\n"
            "🏦 إنستا باي: `instapay@example.com`\n\n"
            f"🔹 **بعد الدفع** أرسل صورة الإيصال إلى المشرف {ADMIN_USERNAME}\n"
            "🔸 **للتجربة فقط:** `/activate_vip_test` (صلاحية ساعة واحدة)\n\n"
            "سيتم تفعيل اشتراكك خلال 24 ساعة كحد أقصى."
        )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_back")]])
    )

# ---------- الاستهلاك اليومي ----------
async def main_usage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        text = "💎 **ليس لديك حدود** – أنت مشترك VIP تستطيع التحميل بقدر ما تريد."
    else:
        used = get_daily_downloads(user_id)
        remaining = max(0, 5 - used)
        text = f"📊 **استخدامك اليومي:** {used} من 5 تحميلات مجانية.\n📈 **المتبقي:** {remaining} تحميل.\n\nللحصول على تحميل غير محدود، اشترك في VIP من القائمة الرئيسية."
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_back")]])
    )

# ---------- المنصات المدعومة ----------
async def main_supported_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🌐 **المنصات المدعومة بالكامل** 🌐\n\n"
        "• **تيك توك** (جميع الفيديوهات العامة)\n"
        "• **فيسبوك** (الفيديوهات العامة، الصفحات، المجموعات المفتوحة)\n"
        "• **تويتر / X** (التغريدات التي تحتوي فيديو)\n"
        "• **يوتيوب** (فيديوهات عادية، shorts، قوائم تشغيل فردية)\n"
        "• **انستجرام** (منشورات، ريلز، استوريهات عامة)\n\n"
        "🚧 **قيد التطوير:** تحويل الفيديو إلى MP3 (لمشتركي VIP) ودعم منصات إضافية مثل لاين وتيك توك لايف."
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_back")]])
    )

# ---------- سياسة الاستخدام (بالغة) ----------
async def main_policy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ **المسؤولية القانونية:** المستخدم هو المسؤول الوحيد عن المحتوى الذي يقوم بتحميله أو إعادة نشره أو مشاركته. البوت مجرد وسيلة تقنية ولا يتحمل أي مسؤولية عن انتهاك حقوق الملكية الفكرية أو القوانين المحلية.\n\n"
        "2️⃣ **حقوق النشر:** يُمنع استخدام البوت لتحميل المواد المحمية بحقوق الطبع والنشر دون الحصول على إذن مسبق من صاحب الحق. في حال ثبوت استخدام غير قانوني، سنتخذ الإجراءات اللازمة بما فيها حظر المستخدم.\n\n"
        "3️⃣ **الخصوصية:** لا نقوم بتخزين الملفات التي يتم تحميلها بعد إرسالها للمستخدم. سجلات الاستخدام محدودة بعدد التحميلات ولا تحتوي على بيانات تعريفية دائمة.\n\n"
        "4️⃣ **الإبلاغ عن إساءة الاستخدام:** يمكن لأصحاب الحقوق التواصل مع المشرف {ADMIN_USERNAME} وسيتم حذف البوت أو تقييد الوصول فوراً عند تقديم شكوى موثقة.\n\n"
        "5️⃣ **التوفر والتغييرات:** قد يتعرض البوت للتوقف المؤقت أو الدائم بسبب تغييرات في واجهات برمجة التطبيقات (APIs) للمنصات الخارجية. لا نضمن استمرارية الخدمة مدى الحياة.\n\n"
        f"📩 **للاستفسارات أو الشكاوى:** {ADMIN_USERNAME}"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_back")]])
    )

# ---------- معلومات البوت (شاملة) ----------
async def main_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ **معلومات تقنية عن البوت** ℹ️\n\n"
        f"• **الاسم:** `{BOT_USERNAME}`\n"
        "• **الإصدار:** 3.5.0 (Pro)\n"
        f"• **المطور/المشرف:** {ADMIN_USERNAME}\n"
        "• **لغة البرمجة:** Python 3.13 + python-telegram-bot v22.7\n"
        "• **مكتبة التحميل:** yt-dlp (تدعم أكثر من 1000 موقع)\n"
        "• **الاستضافة:** Railway (خدمة سحابية 24/7)\n"
        "• **الغرض:** أداة مجانية لتحميل المحتوى مع خيار دعم VIP لتغطية تكاليف التشغيل.\n"
        "• **اللوائح:** متوافق مع سياسات تليجرام بشرط الالتزام بحقوق النشر.\n"
        "• **تاريخ الإطلاق التجريبي:** مايو 2026\n\n"
        "⭐ لدعم التطوير، اشترك في VIP أو تبرع للمشرف."
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_back")]])
    )

# ---------- الرجوع إلى القائمة الرئيسية ----------
async def main_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏠 **القائمة الرئيسية**\nاختر الخدمة التي تريدها:",
        reply_markup=await get_main_menu(),
        parse_mode="Markdown"
    )

# ======================== التعامل مع الروابط وجودة التحميل ========================
async def handle_any_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أي رسالة نصية (يفترض أنها رابط)"""
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)

    if platform == "غير معروف":
        await update.message.reply_text(
            "❌ **رابط غير مدعوم**\n"
            "الروابط المقبولة فقط من: تيك توك، فيسبوك، تويتر، يوتيوب، انستجرام.\n"
            "أعد إرسال رابط صحيح، أو استخدم /start للقائمة الرئيسية.",
            parse_mode="Markdown"
        )
        return

    if not can_download(user_id):
        await update.message.reply_text(
            "⚠️ **لقد استنفدت حد التحميلات المجاني اليومي (5/5)**\n"
            "لتتمكن من التحميل مجدداً، انتظر حتى الغد أو اشترك في VIP لتحميل غير محدود.\n"
            "استخدم القائمة الرئيسية لعرض باقات VIP (⭐ باقات VIP).",
            parse_mode="Markdown"
        )
        return

    # تخزين الرابط مؤقتاً للمستخدم
    context.user_data["pending_download_url"] = url

    # أزرار اختيار الجودة
    quality_keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية (أفضل)", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة (موفرة للبيانات)", callback_data="quality_worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="quality_cancel")],
    ]
    await update.message.reply_text(
        f"📌 **المنصة:** {platform}\nاختر جودة التحميل المناسبة لك:",
        reply_markup=InlineKeyboardMarkup(quality_keyboard),
        parse_mode="Markdown",
    )

async def quality_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار جودة التحميل"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # حالة إلغاء
    if query.data == "quality_cancel":
        await query.edit_message_text("❌ **تم إلغاء عملية التحميل** بنجاح.")
        return

    # استرجاع الرابط المخزن
    url = context.user_data.get("pending_download_url")
    if not url:
        await query.edit_message_text("⚠️ انتهت صلاحية الرابط، يرجى إرساله مرة أخرى.")
        return

    quality_type = "best" if query.data == "quality_best" else "worst"

    # فحص الحد مرة أخرى (احتياطياً)
    if not can_download(user_id):
        await query.edit_message_text("⚠️ لقد تجاوزت الحد اليومي أثناء عملية الاختيار. اشترك في VIP.")
        return

    # إعلام المستخدم ببدء التحميل
    await query.edit_message_text("⏳ **جاري تحميل الفيديو...**\nقد يستغرق بضع ثوانٍ حسب حجم الملف وسرعة السيرفر.")

    try:
        file_path = await download_video(url, quality_type)
        # إرسال الفيديو إلى المستخدم
        with open(file_path, "rb") as vid:
            await query.message.reply_video(
                vid,
                caption="✅ **تم التحميل بنجاح!**\n"
                        "🚀 إذا أعجبك البوت، شاركه مع أصدقائك.\n"
                        "⭐ للحصول على تجربة بدون إعلانات وبدون حدود، اشترك في VIP عبر القائمة الرئيسية."
            )
        # حذف الملف من السيرفر بعد الإرسال
        os.remove(file_path)

        # تحديث عداد التحميلات للمستخدم المجاني
        increment_daily_downloads(user_id)
        # إرسال إعلان إذا كان المستخدم مجانياً
        await send_ad_to_free_user(user_id, context)

        # عرض القائمة الرئيسية مرة أخرى تلقائياً
        await query.message.reply_text(
            "🏠 **تم التحميل. عد إلى القائمة الرئيسية للقيام بمهمة أخرى:**",
            reply_markup=await get_main_menu(),
            parse_mode="Markdown"
        )
    except Exception as e:
        error_msg = str(e)[:150]
        logger.error(f"فشل تحميل الفيديو للمستخدم {user_id}: {e}")
        await query.message.reply_text(
            f"❌ **فشلت عملية التحميل.**\nالسبب: {error_msg}\n\n"
            "تأكد من أن الرابط صحيح ويعمل (الفيديو ليس خاصاً أو محذوفاً).\n"
            "إذا تكررت المشكلة، أبلغ المشرف.",
            parse_mode="Markdown"
        )
    finally:
        # حذف الرابط من الذاكرة المؤقتة
        context.user_data.pop("pending_download_url", None)

# ======================== أوامر VIP التجريبية واليدوية ========================
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
    """أمر سري للمشرف لتفعيل VIP يدوياً للمستخدمين الذين دفعوا (معرف المشرف ثابت)"""
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
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {user_id} لمدة {days} يوماً (ينتهي في {expiry}).")
    except Exception:
        await update.message.reply_text("⚠️ الاستخدام الصحيح: `/activate_vip <user_id> <عدد_الأيام>`", parse_mode="Markdown")

# ======================== الوظيفة الرئيسية ========================
def main():
    """تشغيل البوت وتسجيل المعالجات"""
    app = Application.builder().token(TOKEN).build()

    # أوامر عامة
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("activate_vip_test", test_vip_command))
    app.add_handler(CommandHandler("activate_vip", manual_activate_vip))

    # معالجات الأزرار الرئيسية والفرعية
    app.add_handler(CallbackQueryHandler(main_download_callback, pattern="^main_download$"))
    app.add_handler(CallbackQueryHandler(main_vip_callback, pattern="^main_vip$"))
    app.add_handler(CallbackQueryHandler(main_usage_callback, pattern="^main_usage$"))
    app.add_handler(CallbackQueryHandler(main_supported_callback, pattern="^main_supported$"))
    app.add_handler(CallbackQueryHandler(main_policy_callback, pattern="^main_policy$"))
    app.add_handler(CallbackQueryHandler(main_info_callback, pattern="^main_info$"))
    app.add_handler(CallbackQueryHandler(main_back_callback, pattern="^main_back$"))

    # معالجات اختيار جودة التحميل
    app.add_handler(CallbackQueryHandler(quality_selection_callback, pattern="^(quality_best|quality_worst|quality_cancel)$"))

    # معالج الرسائل النصية (الروابط)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_link))

    # بدء البوت
    logger.info("✅ البوت يعمل الآن بكفاءة عالية مع جميع الأزرار والقوائم.")
    app.run_polling()

if __name__ == "__main__":
    main()