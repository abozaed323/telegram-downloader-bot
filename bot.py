import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

conn = sqlite3.connect('bot_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))''')
conn.commit()

def is_vip(user_id: int) -> bool:
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        try:
            expiry_str = row[0].split()[0] if ' ' in row[0] else row[0]
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
        except:
            expiry = datetime.now()
        if expiry >= datetime.now():
            return True
        else:
            c.execute("DELETE FROM vip WHERE user_id=?", (user_id,))
            conn.commit()
    return False

def get_daily_downloads(user_id: int) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_downloads(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1", (user_id, today))
    conn.commit()

def can_download(user_id: int) -> bool:
    if is_vip(user_id):
        return True
    return get_daily_downloads(user_id) < 5

ADS_LIST = [
    "📢 اشترك في قناتنا: @YourChannel\nلأحدث البوتات والتحديثات",
    "💎 هل تريد التحميل بلا حدود؟ اشترك في VIP عبر القائمة الرئيسية",
    "🔥 باقات VIP تبدأ من 1$ فقط أسبوعياً – مميزات لا محدودة",
    "📌 هذا البوت للإستخدام الشخصي، يرجى احترام حقوق النشر."
]

async def send_ad(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_vip(user_id):
        ad = random.choice(ADS_LIST)
        await context.bot.send_message(chat_id=user_id, text=ad)

def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return "تيك توك"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "فيسبوك"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "تويتر"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "يوتيوب"
    elif "instagram.com" in url_lower:
        return "انستجرام"
    else:
        return "غير معروف"

async def download_video(url: str, quality: str = "best"):
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'format': 'best' if quality == 'best' else 'worst',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir("downloads")
            if files:
                filename = os.path.join("downloads", max([os.path.join("downloads", f) for f in files], key=os.path.getctime))
        return filename

async def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("⭐ باقات VIP والاشتراك", callback_data="menu_vip")],
        [InlineKeyboardButton("📊 استهلاكي اليومي", callback_data="menu_usage")],
        [InlineKeyboardButton("🌐 المنصات المدعومة", callback_data="menu_supported")],
        [InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="menu_info")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ✅ دالة start مصححة – ترسل صورة مع النص مباشرة
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    first_name = user.first_name if user.first_name else "صديقي"
    
    welcome_msg = (
        f"🎬 **أهلاً بك {first_name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "✅ تيك توك  |  ✅ فيسبوك  |  ✅ تويتر\n"
        "✅ يوتيوب  |  ✅ انستجرام (منشورات، ريلز، استوريهات عامة)\n\n"
        "📊 **المستخدم المجاني:** 5 تحميلات يومياً\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات + جودة عالية\n\n"
        "⚠️ **تنبيه هام:** هذا البوت لا يشجع على انتهاك حقوق النشر. المستخدم مسؤول عن المحتوى الذي يقوم بتحميله واستخدامه.\n\n"
        "اختر من القائمة أدناه:"
    )
    
    # إرسال صورة مصغرة (thumbnail) مع النص كـ caption
    photo_url = "https://cdn.pixabay.com/photo/2016/02/19/11/19/video-1210600_1280.png"
    try:
        await update.message.reply_photo(
            photo=photo_url,
            caption=welcome_msg,
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard()
        )
    except Exception as e:
        # لو فشل إرسال الصورة، نرسل نصاً فقط
        logging.error(f"فشل إرسال الصورة: {e}")
        await update.message.reply_text(
            welcome_msg,
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard()
        )

async def menu_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\nمثال: https://www.tiktok.com/@user/video/123456789\n\nلإلغاء العملية، اضغط /start",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]])
    )

async def menu_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
        expiry = c.fetchone()[0]
        text = f"✅ **أنت مشترك VIP حتى {expiry}**\nشكراً لدعمك! 🎉"
    else:
        text = (
            "⭐ **باقات VIP الاحترافية** ⭐\n\n"
            "• **أسبوعي:** 1$ (أو 2 نجوم تليجرام)\n"
            "• **شهري:** 3$ (أو 5 نجوم تليجرام)\n"
            "• **سنوي:** 25$ (توفير 11$)\n\n"
            "💳 **طرق الدفع المتاحة:**\n"
            "⭐ نجوم تليجرام (Telegram Stars)\n"
            "📱 فودافون كاش: 0123456789\n"
            "🏦 إنستا باي: instapay@example.com\n\n"
            f"🔹 **بعد الدفع، أرسل إيصال الدفع مباشرة إلى المشرف:** {ADMIN_USERNAME}\n"
            "سيتم تفعيل الاشتراك خلال 24 ساعة.\n\n"
            "🔸 **للتجربة:** استخدم الأمر `/activate_vip_test` (تجربة ساعة واحدة فقط)"
        )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def menu_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_vip(user_id):
        text = "⭐ **أنت مشترك VIP** – لا حدود للتحميل."
    else:
        used = get_daily_downloads(user_id)
        remaining = 5 - used
        text = f"📊 **استخدمت اليوم {used} من 5 تحميلات مجانية.**\nمتبقي: {remaining} تحميل.\n\nلرفع الحد، اشترك في VIP من القائمة الرئيسية."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]), parse_mode="Markdown")

async def menu_supported(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🌐 **المنصات المدعومة حالياً:**\n\n"
        "• تيك توك (فيديوهات)\n"
        "• فيسبوك (فيديوهات عامة)\n"
        "• تويتر/X (فيديوهات)\n"
        "• يوتيوب (فيديوهات)\n"
        "• انستجرام (منشورات، ريلز، استوريهات عامة)\n\n"
        "🚧 **قريباً:** تحويل الفيديو إلى MP3 للمشتركين VIP."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def menu_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ هذا البوت يوفر خدمة تحميل المحتوى من المنصات العامة.\n"
        "2️⃣ **المستخدم هو المسؤول الوحيد** عن أي محتوى يقوم بتحميله أو مشاركته.\n"
        "3️⃣ لا يشجع البوت ولا يدعم قرصنة أو انتهاك حقوق النشر أو الملكية الفكرية.\n"
        "4️⃣ **لا يتم تخزين أي ملفات محملة على خوادم البوت** بعد إرسالها للمستخدم.\n"
        "5️⃣ **حقوق الطبع والنشر محفوظة لأصحابها الأصليين.**\n"
        "6️⃣ في حال تلقي أي شكوى قانونية، سيتم حظر البوت فوراً ولن نتحمل أي مسؤولية.\n\n"
        f"📩 لأي استفسار أو شكوى: {ADMIN_USERNAME}"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def menu_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ **معلومات البوت** ℹ️\n\n"
        f"• **الاسم:** {BOT_USERNAME}\n"
        "• **الإصدار:** 3.0 (Pro)\n"
        f"• **المطور والمشرف:** {ADMIN_USERNAME}\n"
        "• **الهدف:** توفير أداة تحميل سريعة ومجانية مع خيار VIP.\n"
        "• **اللغات المدعومة:** العربية فقط حالياً.\n"
        "• **الاستضافة:** خوادم عالية الأداء – تشغيل 24/7\n\n"
        "⭐ **لشراء VIP أو للدعم الفني:** تواصل مع المشرف بالضغط على اسمه أعلاه."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu_keyboard(), parse_mode="Markdown")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)
    
    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً من تيك توك، فيسبوك، تويتر، يوتيوب أو انستجرام.\nأو /start للقائمة.")
        return
    
    if not can_download(user_id):
        await update.message.reply_text("⚠️ استنفدت الـ5 تحميلات المجانية اليومية. اشترك في VIP من القائمة.")
        return
    
    context.user_data['pending_url'] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="quality_best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="quality_worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]
    ]
    await update.message.reply_text(f"📌 **المنصة:** {platform}\nاختر جودة التحميل:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    action = query.data
    if action == "main_menu":
        await back_to_main_menu(update, context)
        return
    
    url = context.user_data.get('pending_url')
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مرة أخرى.")
        return
    
    quality = "best" if action == "quality_best" else "worst"
    
    if not can_download(user_id):
        await query.edit_message_text("⚠️ تجاوزت حد التحميل اليومي.")
        return
    
    await query.edit_message_text("⏳ جاري التحميل... قد يستغرق بضع ثوانٍ.")
    try:
        file_path = await download_video(url, quality)
        with open(file_path, 'rb') as video_file:
            await query.message.reply_video(video_file, caption="✅ تم التحميل بنجاح!")
        os.remove(file_path)
        increment_daily_downloads(user_id)
        await send_ad(user_id, context)
        await query.message.reply_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu_keyboard(), parse_mode="Markdown")
    except Exception as e:
        error_msg = str(e)[:150]
        await query.message.reply_text(f"❌ فشل التحميل: {error_msg}")
    finally:
        context.user_data.pop('pending_url', None)

async def activate_test_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة (للاختبار فقط).")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", activate_test_vip))
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_supported, pattern="^menu_supported$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(menu_info, pattern="^menu_info$"))
    app.add_handler(CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^(quality_best|quality_worst|main_menu)"))
    
    print("✅ البوت يعمل بواجهة محترفة: أزرار بإيموجي، سياسة استخدام، باقات أسبوعي/شهري/سنوي، مع مشرف مخصص.")
    app.run_polling()

if __name__ == "__main__":
    main()