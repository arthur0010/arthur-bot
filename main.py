import os
import asyncio
import threading
from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

import database as db

# ============ تنظیمات ============
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# ============ Flask (برای بیدار نگه داشتن Render) ============
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Relay Bot is running ✅", 200

@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


# ============ ابزار کمکی ============
def esc(text):
    import html
    return html.escape(str(text or ""))

def user_info_text(user):
    username = f"@{esc(user.username)}" if user.username else "—"
    return f"👤 {esc(user.full_name)}\n🆔 {username}\n🔢 <code>{user.id}</code>"

def admin_buttons(user_id, is_blocked):
    if is_blocked:
        btn = InlineKeyboardButton("✅ آنبلاک", callback_data=f"unblock:{user_id}")
    else:
        btn = InlineKeyboardButton("⛔ بلاک", callback_data=f"block:{user_id}")
    return InlineKeyboardMarkup([[btn]])

async def send_any_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    blocked = db.is_blocked(user.id)
    status = "⛔ (بلاک‌شده)" if blocked else ""
    header_text = f"📩 پیام جدید {status}\n{user_info_text(user)}\n➖➖➖➖➖➖"
    try:
        header = await context.bot.send_message(
            chat_id=ADMIN_ID, text=header_text,
            parse_mode="HTML", reply_markup=admin_buttons(user.id, blocked)
        )
        copied = await msg.copy(chat_id=ADMIN_ID)
        db.save_msg_map(header.message_id, user.id)
        db.save_msg_map(copied.message_id, user.id)
        db.clean_old_msg_map()
    except Exception as e:
        print(f"[send_any_to_admin] خطا: {e}")


# ============ دستورات ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        context.user_data["broadcast_mode"] = False
        await update.message.reply_text(
            "👑 سلام ادمین!\n\n"
            "📋 دستورات:\n"
            "• /users — لیست کاربران\n"
            "• /blocked — لیست مسدودها\n"
            "• /block <id> — بلاک\n"
            "• /unblock <id> — آنبلاک\n"
            "• /find <متن> — جستجو\n"
            "• /stats — آمار ربات\n"
            "• /broadcast — ارسال همگانی\n\n"
            "برای جواب، روی پیام کاربر ریپلای بزن."
        )
        return
    db.save_user(user.id, user.username or "", user.full_name)
    if db.is_blocked(user.id):
        await update.message.reply_text("⛔ شما توسط مدیریت مسدود شده‌اید.")
        return
    await update.message.reply_text("سلام 👋\nپیامت رو بگو تا به امیر منتقل کنم ✉️")


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return
    db.save_user(user.id, user.username or "", user.full_name)
    if db.is_blocked(user.id):
        await update.message.reply_text("⛔ شما مسدود هستید.")
        return
    await send_any_to_admin(update, context)
    await update.message.reply_text("✅ ارسال شد. منتظر جواب باش.")


async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.from_user.id != ADMIN_ID:
        return
    if context.user_data.get("broadcast_mode"):
        context.user_data["broadcast_mode"] = False
        await do_broadcast(update, context, msg)
        return
    if not msg.reply_to_message:
        await msg.reply_text("برای جواب، روی پیام کاربر ریپلای بزن ↩️")
        return
    target_id = db.get_user_from_msg(msg.reply_to_message.message_id)
    if not target_id:
        await msg.reply_text("❌ کاربر پیدا نشد.")
        return
    try:
        await context.bot.send_message(chat_id=target_id, text="📬 پاسخ مدیریت:\n➖➖➖➖➖➖")
        await msg.copy(chat_id=target_id)
        await msg.reply_text("✅ ارسال شد.")
    except Exception as e:
        await msg.reply_text(f"⚠️ خطا: {e}")


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        context.user_data["broadcast_mode"] = False
        return await func(update, context)
    return wrapper


@admin_only
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_all_users()
    if not rows:
        await update.message.reply_text("هیچ کاربری ثبت نشده.")
        return
    text = "👥 لیست کاربران:\n\n"
    for uid, uname, fname, blocked in rows[:50]:
        status = "⛔" if blocked else "✅"
        text += f"{status} {esc(fname)} | @{esc(uname) or '—'} | <code>{uid}</code>\n"
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def blocked_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_blocked_users()
    if not rows:
        await update.message.reply_text("لیست مسدودها خالیه ✅")
        return
    text = "⛔ کاربران مسدود:\n\n"
    for uid, uname, fname in rows:
        text += f"• {esc(fname)} | @{esc(uname) or '—'} | <code>{uid}</code>\n"
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /block <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("آیدی باید عدد باشه.")
        return
    if uid == ADMIN_ID:
        await update.message.reply_text("خودت رو نمی‌تونی بلاک کنی 😅")
        return
    if not db.get_user_by_id(uid):
        await update.message.reply_text("کاربر پیدا نشد.")
        return
    db.block_user(uid)
    await update.message.reply_text(f"⛔ کاربر {uid} بلاک شد.")
    try:
        await context.bot.send_message(uid, "⛔ شما توسط مدیریت مسدود شدید.")
    except Exception:
        pass


@admin_only
async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /unblock <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("آیدی باید عدد باشه.")
        return
    if not db.get_user_by_id(uid):
        await update.message.reply_text("کاربر پیدا نشد.")
        return
    db.unblock_user(uid)
    await update.message.reply_text(f"✅ کاربر {uid} آنبلاک شد.")
    try:
        await context.bot.send_message(uid, "✅ شما آنبلاک شدید.")
    except Exception:
        pass


@admin_only
async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /find <متن>")
        return
    query = " ".join(context.args)
    rows = db.search_users(query)
    if not rows:
        await update.message.reply_text("چیزی پیدا نشد.")
        return
    text = f"🔍 نتایج «{esc(query)}»:\n\n"
    for uid, uname, fname, blocked in rows:
        status = "⛔" if blocked else "✅"
        text += f"{status} {esc(fname)} | @{esc(uname) or '—'} | <code>{uid}</code>\n"
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total, blocked = db.count_users()
    await update.message.reply_text(f"📊 کل: {total}\n⛔ مسدود: {blocked}\n✅ فعال: {total - blocked}")


@admin_only
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast_mode"] = True
    await update.message.reply_text("📣 حالت ارسال همگانی فعال شد.\nپیام مورد نظر رو بفرست.\nبرای لغو: /cancel")


@admin_only
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast_mode"] = False
    await update.message.reply_text("❌ لغو شد.")


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, msg):
    user_ids = db.get_active_user_ids()
    total = len(user_ids)
    if total == 0:
        await msg.reply_text("کاربر فعالی وجود نداره.")
        return
    status_msg = await msg.reply_text(f"📤 شروع ارسال به {total} کاربر...")
    success, failed = 0, 0
    for i, uid in enumerate(user_ids, 1):
        try:
            await msg.copy(chat_id=uid)
            success += 1
        except Exception:
            failed += 1
        if i % 25 == 0:
            await asyncio.sleep(1)
    await status_msg.edit_text(f"✅ تمام شد.\n👥 کل: {total}\n✅ موفق: {success}\n❌ ناموفق: {failed}")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    try:
        action, uid_str = query.data.split(":")
        uid = int(uid_str)
    except Exception:
        return
    if action == "block":
        db.block_user(uid)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ آنبلاک", callback_data=f"unblock:{uid}")
        ]]))
        await query.message.reply_text(f"⛔ کاربر {uid} بلاک شد.")
        try:
            await context.bot.send_message(uid, "⛔ شما مسدود شدید.")
        except Exception:
            pass
    elif action == "unblock":
        db.unblock_user(uid)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⛔ بلاک", callback_data=f"block:{uid}")
        ]]))
        await query.message.reply_text(f"✅ کاربر {uid} آنبلاک شد.")
        try:
            await context.bot.send_message(uid, "✅ آنبلاک شدید.")
        except Exception:
            pass


# ============ اجرا ============
def run_bot():
    # ⚠️ مهم: تو پایتون ۳.۱۲+ هر ترد جدید باید event loop خودش رو داشته باشه
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    db.init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("blocked", blocked_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.User(ADMIN_ID) & ~filters.COMMAND, handle_admin_message))
    app.add_handler(MessageHandler(~filters.User(ADMIN_ID), handle_user_message))

    print("🤖 ربات روشن شد...")
    app.run_polling()


if __name__ == "__main__":
    # ربات رو تو ترد جداگانه اجرا کن
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    # Flask رو تو ترد اصلی اجرا کن (پورت باز بمونه)
    run_flask()