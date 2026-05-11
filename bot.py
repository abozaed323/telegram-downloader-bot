import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "8606881282:AAFUnul-fEQI2Y6JPnCFV9dxTDaV8n0onT4"
ADMIN_USERNAME = "@Mac_0980"
BOT_USERNAME = "ShamelDownloaderBot"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

# ---------- قاعدة البيانات ----------
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_downloads (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY (user_id, date))''')
conn.commit()

def is_vip(user_id):
    c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        expiry_str = row[0].split()[0]
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
        if expiry >= datetime.now():
            return True
        else:
            c.execute("DELETE FROM vip WHERE user_id=?", (user_id,))
            conn.commit()
    return False

def get_daily_downloads(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT count FROM daily_downloads WHERE user_id=? AND date=?", (user_id, today))
    row = c.fetchone()
    return row[0] if row else 0

def increment_daily_downloads(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO daily_downloads (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1", (user_id, today))
    conn.commit()

def can_download(user_id):
    if is_vip(user_id):
        return True
    return get_daily_downloads(user_id) < 5

ADS = ["📢 اشترك في قناتنا @YourChannel", "💎 باقات VIP تبدأ من 1$", "🔥 تحميل غير محدود مع VIP"]

async def send_ad(user_id, context):
    if not is_vip(user_id):
        await context.bot.send_message(chat_id=user_id, text=random.choice(ADS))

# ---------- تحميل الفيديو ----------
def detect_platform(url):
    u = url.lower()
    if "tiktok.com" in u: return "تيك توك"
    if "facebook.com" in u or "fb.watch" in u: return "فيسبوك"
    if "twitter.com" in u or "x.com" in u: return "تويتر"
    if "youtube.com" in u or "youtu.be" in u: return "يوتيوب"
    if "instagram.com" in u: return "انستجرام"
    return "غير معروف"

async def download_video(url, quality="best"):
    opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'format': 'best' if quality == 'best' else 'worst',
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if not os.path.exists(filename):
            files = os.listdir("downloads")
            if files:
                filename = os.path.join("downloads", max([os.path.join("downloads", f) for f in files], key=os.path.getctime))
        return filename

# ---------- القائمة الرئيسية (Inline Keyboard) ----------
async def main_menu():
    keyboard = [
        [InlineKeyboardButton("📥 تحميل فيديو", callback_data="menu_download")],
        [InlineKeyboardButton("⭐ باقات VIP", callback_data="menu_vip"), InlineKeyboardButton("📊 استهلاكي اليومي", callback_data="menu_usage")],
        [InlineKeyboardButton("🌐 المنصات المدعومة", callback_data="menu_supported"), InlineKeyboardButton("⚖️ سياسة الاستخدام", callback_data="menu_policy")],
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="menu_info")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------- أمر /start ----------
async def start(update, context):
    user = update.effective_user
    name = user.first_name or "صديقي"
    msg = (
        f"🎬 **أهلاً بك {name} في بوت التحميل الشامل** 🎬\n\n"
        "📥 **أرسل رابط فيديو من:**\n"
        "✅ تيك توك | ✅ فيسبوك | ✅ تويتر\n"
        "✅ يوتيوب | ✅ انستجرام (ريلز، استوريهات عامة)\n\n"
        "📊 **المستخدم المجاني:** 5 تحميلات يومياً\n"
        "⭐ **VIP:** تحميل غير محدود + بدون إعلانات + جودة عالية\n\n"
        "⚠️ **تنبيه:** أنت المسؤول الوحيد عن المحتوى الذي تقوم بتحميله.\n\n"
        "اختر من القائمة أدناه:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=await main_menu())

# ---------- القوائم الفرعية ----------
async def menu_download(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📥 **أرسل رابط الفيديو الآن**\n\nمثال: https://www.tiktok.com/@user/video/123456789\n\nلإلغاء العملية اضغط /start",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")]])
    )

async def menu_vip(update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if is_vip(uid):
        c.execute("SELECT expiry_date FROM vip WHERE user_id=?", (uid,))
        exp = c.fetchone()[0]
        text = f"✅ **أنت مشترك VIP حتى {exp}**\nشكراً لدعمك! 🎉"
    else:
        text = (
            "⭐ **باقات VIP الاحترافية** ⭐\n\n"
            "• **أسبوعي:** 1$ (أو 2 نجوم تليجرام)\n"
            "• **شهري:** 3$ (أو 5 نجوم تليجرام)\n"
            "• **سنوي:** 25$ (توفير 11$)\n\n"
            "💳 **طرق الدفع المتاحة:**\n"
            "⭐ نجوم تليجرام\n📱 فودافون كاش: 0123456789\n🏦 إنستا باي: instapay@example.com\n\n"
            f"🔹 **بعد الدفع، أرسل الإيصال مباشرة إلى المشرف:** {ADMIN_USERNAME}\n"
            "🔸 **للتجربة:** استخدم الأمر `/activate_vip_test` (تجربة ساعة واحدة)"
        )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")]]))

async def menu_usage(update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if is_vip(uid):
        text = "⭐ **أنت مشترك VIP** – لا حدود للتحميل اليومي."
    else:
        used = get_daily_downloads(uid)
        rem = 5 - used
        text = f"📊 **استخدمت اليوم {used} من 5 تحميلات مجانية.**\nمتبقي: {rem} تحميل.\n\nلرفع الحد، اشترك في VIP."
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")]]))

async def menu_supported(update, context):
    query = update.callback_query
    await query.answer()
    text = (
        "🌐 **المنصات المدعومة حالياً** 🌐\n\n"
        "• **تيك توك** - فيديوهات عادية\n"
        "• **فيسبوك** - فيديوهات عامة\n"
        "• **تويتر / X** - فيديوهات داخل التغريدات\n"
        "• **يوتيوب** - فيديوهات عادية وقصيرة (Short)\n"
        "• **انستجرام** - منشورات، ريلز، استوريهات عامة\n\n"
        "🚧 **قريباً:** تحويل الفيديو إلى MP3 للمشتركين VIP."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")]]))

async def menu_policy(update, context):
    query = update.callback_query
    await query.answer()
    text = (
        "⚖️ **سياسة الاستخدام وإخلاء المسؤولية** ⚖️\n\n"
        "1️⃣ **المسؤولية:** المستخدم هو المسؤول الوحيد عن أي محتوى يقوم بتحميله أو مشاركته.\n"
        "2️⃣ **حقوق النشر:** هذا البوت لا يشجع على انتهاك حقوق الملكية الفكرية. يُمنع استخدامه لتحميل المواد المحمية دون إذن.\n"
        "3️⃣ **الخصوصية:** لا نقوم بتخزين الملفات التي يتم تحميلها أو سجلات المستخدمين الدائمة.\n"
        "4️⃣ **الإبلاغ:** في حال تلقي أي شكوى قانونية موثقة، سنقوم بحظر البوت أو تقييد الوصول.\n"
        "5️⃣ **التوفر:** قد يتعرض البوت للتوقف بسبب تحديثات أو تغيير في سياسات منصات التواصل.\n\n"
        f"📩 **للاستفسارات أو الإبلاغ:** {ADMIN_USERNAME}"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")]]))

async def menu_info(update, context):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ **معلومات البوت** ℹ️\n\n"
        f"• **الاسم:** `{BOT_USERNAME}`\n"
        "• **الإصدار:** 3.0 (Pro)\n"
        f"• **المطور والمشرف:** {ADMIN_USERNAME}\n"
        "• **الهدف:** توفير أداة تحميل سريعة ومجانية مع خيار VIP لدعم التطوير.\n"
        "• **اللغات المدعومة:** العربية\n"
        "• **الاستضافة:** خوادم عالية الأداء – تشغيل 24/7\n"
        "• **تاريخ الإطلاق:** مايو 2026\n\n"
        "⭐ **لشراء VIP أو للدعم الفني:** تواصل مع المشرف بالضغط على اسمه أعلاه."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")]]))

async def back_to_main(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏠 **القائمة الرئيسية**\nاختر أحد الخيارات:",
        reply_markup=await main_menu(),
        parse_mode="Markdown"
    )

# ---------- معالج الروابط وجودة التحميل ----------
async def handle_link(update, context):
    uid = update.effective_user.id
    url = update.message.text.strip()
    platform = detect_platform(url)

    if platform == "غير معروف":
        await update.message.reply_text("❌ رابط غير مدعوم. أرسل رابطاً من تيك توك، فيسبوك، تويتر، يوتيوب أو انستجرام.\nاستخدم /start للقائمة الرئيسية.")
        return

    if not can_download(uid):
        await update.message.reply_text("⚠️ استنفدت الـ5 تحميلات المجانية اليومية. اشترك في VIP عبر القائمة الرئيسية.")
        return

    context.user_data['pending_url'] = url
    keyboard = [
        [InlineKeyboardButton("🎥 جودة عالية", callback_data="best")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data="worst")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="cancel_quality")]
    ]
    await update.message.reply_text(f"📌 **المنصة:** {platform}\nاختر جودة التحميل:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def quality_callback(update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "cancel_quality":
        await query.edit_message_text("❌ تم إلغاء التحميل.")
        return

    url = context.user_data.get('pending_url')
    if not url:
        await query.edit_message_text("انتهت صلاحية الرابط، أرسله مجدداً.")
        return

    q = "best" if query.data == "best" else "worst"
    if not can_download(uid):
        await query.edit_message_text("⚠️ تجاوزت حد التحميل اليومي.")
        return

    await query.edit_message_text("⏳ جاري التحميل... قد يستغرق بضع ثوانٍ.")
    try:
        path = await download_video(url, q)
        with open(path, 'rb') as vid:
            await query.message.reply_video(vid, caption="✅ تم التحميل بنجاح!\nلرفع الحدود والإعلانات اشترك في VIP.")
        os.remove(path)
        increment_daily_downloads(uid)
        await send_ad(uid, context)
        # عرض القائمة الرئيسية بعد التحميل
        await query.message.reply_text("🏠 **القائمة الرئيسية**", reply_markup=await main_menu(), parse_mode="Markdown")
    except Exception as e:
        await query.message.reply_text(f"❌ فشل التحميل: {str(e)[:100]}")
    finally:
        context.user_data.pop('pending_url', None)

async def test_vip(update, context):
    uid = update.effective_user.id
    exp = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO vip (user_id, expiry_date) VALUES (?, ?)", (uid, exp))
    conn.commit()
    await update.message.reply_text("✅ تم تفعيل VIP تجريبي لمدة ساعة (للاختبار فقط).")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate_vip_test", test_vip))
    # قوائم الدردشة
    app.add_handler(CallbackQueryHandler(menu_download, pattern="^menu_download$"))
    app.add_handler(CallbackQueryHandler(menu_vip, pattern="^menu_vip$"))
    app.add_handler(CallbackQueryHandler(menu_usage, pattern="^menu_usage$"))
    app.add_handler(CallbackQueryHandler(menu_supported, pattern="^menu_supported$"))
    app.add_handler(CallbackQueryHandler(menu_policy, pattern="^menu_policy$"))
    app.add_handler(CallbackQueryHandler(menu_info, pattern="^menu_info$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^main_menu$"))
    # معالج الروابط وجودة التحميل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^(best|worst|cancel_quality)$"))

    print("✅ البوت يعمل مع أزرار داخل الدردشة (بدون قائمة سفلية) ومعلومات وسياسة غنية.")
    app.run_polling()

if __name__ == "__main__":
    main()