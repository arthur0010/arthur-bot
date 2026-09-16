import os
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db

# ============ تنظیمات ============
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

flask_app = Flask(__name__)
bot = telegram.Bot(token=TOKEN)


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


# ============ هندلرها ============
def handle_start(message, user):
    chat_id = message.chat_id
    if user.id == ADMIN_ID:
        bot.send_message(
            chat_id=chat_id,
            text=(
                "👑 سلام ادمین!\n\n"
                "📋 دستورات:\n"
                "• /users — لیست کاربران\n"
                "• /blocked — لیست مسدودها\n"
                "• /block <id> — بلاک\n"
                "• /unblock <id> — آنبلاک\n"
                "• /find <متن> — جستجو\n"
                "• /stats — آمار ربات\n\n"
                "برای جواب، روی پیام کاربر ریپلای بزن."
            )
        )
        return
    db.save_user(user.id, user.username or "", user.full_name or "")
    if db.is_blocked(user.id):
        bot.send_message(chat_id=chat_id, text="⛔ شما توسط مدیریت مسدود شده‌اید.")
        return
    bot.send_message(chat_id=chat_id, text="سلام 👋\nپیامت رو بگو تا به امیر منتقل کنم ✉️")


def handle_user_message(message, user):
    db.save_user(user.id, user.username or "", user.full_name or "")
    if db.is_blocked(user.id):
        bot.send_message(chat_id=message.chat_id, text="⛔ شما مسدود هستید.")
        return

    blocked = db.is_blocked(user.id)
    status = "⛔ (بلاک‌شده)" if blocked else ""
    header_text = f"📩 پیام جدید {status}\n{user_info_text(user)}\n➖➖➖➖➖➖"

    try:
        header = bot.send_message(
            chat_id=ADMIN_ID, text=header_text,
            parse_mode="HTML", reply_markup=admin_buttons(user.id, blocked)
        )
        bot.copy_message(
            chat_id=ADMIN_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        db.save_msg_map(header.message_id, user.id)
        bot.send_message(chat_id=message.chat_id, text="✅ ارسال شد. منتظر جواب باش.")
    except Exception as e:
        print(f"[handle_user_message] خطا: {e}")


def handle_admin_message(message, user):
    text = message.text or ""

    if text == "/users":
        rows = db.get_all_users()
        if not rows:
            bot.send_message(chat_id=ADMIN_ID, text="هیچ کاربری ثبت نشده.")
            return
        t = "👥 لیست کاربران:\n\n"
        for uid, uname, fname, blocked in rows[:50]:
            s = "⛔" if blocked else "✅"
            t += f"{s} {esc(fname)} | @{esc(uname) or '—'} | <code>{uid}</code>\n"
        bot.send_message(chat_id=ADMIN_ID, text=t, parse_mode="HTML")
        return

    if text == "/blocked":
        rows = db.get_blocked_users()
        if not rows:
            bot.send_message(chat_id=ADMIN_ID, text="لیست مسدودها خالیه ✅")
            return
        t = "⛔ کاربران مسدود:\n\n"
        for uid, uname, fname in rows:
            t += f"• {esc(fname)} | @{esc(uname) or '—'} | <code>{uid}</code>\n"
        bot.send_message(chat_id=ADMIN_ID, text=t, parse_mode="HTML")
        return

    if text == "/stats":
        total, blocked = db.count_users()
        bot.send_message(chat_id=ADMIN_ID, text=f"📊 کل: {total}\n⛔ مسدود: {blocked}\n✅ فعال: {total - blocked}")
        return

    if text.startswith("/block "):
        try:
            uid = int(text.split()[1])
        except (IndexError, ValueError):
            bot.send_message(chat_id=ADMIN_ID, text="استفاده: /block <user_id>")
            return
        if uid == ADMIN_ID:
            bot.send_message(chat_id=ADMIN_ID, text="خودت رو نمی‌تونی بلاک کنی 😅")
            return
        db.block_user(uid)
        bot.send_message(chat_id=ADMIN_ID, text=f"⛔ کاربر {uid} بلاک شد.")
        try:
            bot.send_message(chat_id=uid, text="⛔ شما توسط مدیریت مسدود شدید.")
        except Exception:
            pass
        return

    if text.startswith("/unblock "):
        try:
            uid = int(text.split()[1])
        except (IndexError, ValueError):
            bot.send_message(chat_id=ADMIN_ID, text="استفاده: /unblock <user_id>")
            return
        db.unblock_user(uid)
        bot.send_message(chat_id=ADMIN_ID, text=f"✅ کاربر {uid} آنبلاک شد.")
        try:
            bot.send_message(chat_id=uid, text="✅ شما آنبلاک شدید.")
        except Exception:
            pass
        return

    if text.startswith("/find "):
        query = text[len("/find "):].strip()
        rows = db.search_users(query)
        if not rows:
            bot.send_message(chat_id=ADMIN_ID, text="چیزی پیدا نشد.")
            return
        t = f"🔍 نتایج «{esc(query)}»:\n\n"
        for uid, uname, fname, blocked in rows:
            s = "⛔" if blocked else "✅"
            t += f"{s} {esc(fname)} | @{esc(uname) or '—'} | <code>{uid}</code>\n"
        bot.send_message(chat_id=ADMIN_ID, text=t, parse_mode="HTML")
        return

    # ریپلای روی پیام کاربر
    if message.reply_to_message:
        target_id = db.get_user_from_msg(message.reply_to_message.message_id)
        if not target_id:
            bot.send_message(chat_id=ADMIN_ID, text="❌ کاربر پیدا نشد.")
            return
        try:
            bot.send_message(chat_id=target_id, text="📬 پاسخ مدیریت:\n➖➖➖➖➖➖")
            bot.copy_message(
                chat_id=target_id,
                from_chat_id=ADMIN_ID,
                message_id=message.message_id
            )
            bot.send_message(chat_id=ADMIN_ID, text="✅ ارسال شد.")
        except Exception as e:
            bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ خطا: {e}")
        return

    bot.send_message(chat_id=ADMIN_ID, text="برای جواب، روی پیام کاربر ریپلای بزن ↩️")


def handle_callback(cb):
    try:
        action, uid_str = cb.data.split(":")
        uid = int(uid_str)
    except Exception:
        return

    if action == "block":
        db.block_user(uid)
        try:
            bot.edit_message_reply_markup(
                chat_id=cb.message.chat_id,
                message_id=cb.message.message_id,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ آنبلاک", callback_data=f"unblock:{uid}")
                ]])
            )
        except Exception:
            pass
        try:
            bot.answer_callback_query(callback_query_id=cb.id, text="بلاک شد")
        except Exception:
            pass
        try:
            bot.send_message(chat_id=uid, text="⛔ شما مسدود شدید.")
        except Exception:
            pass

    elif action == "unblock":
        db.unblock_user(uid)
        try:
            bot.edit_message_reply_markup(
                chat_id=cb.message.chat_id,
                message_id=cb.message.message_id,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⛔ بلاک", callback_data=f"block:{uid}")
                ]])
            )
        except Exception:
            pass
        try:
            bot.answer_callback_query(callback_query_id=cb.id, text="آنبلاک شد")
        except Exception:
            pass
        try:
            bot.send_message(chat_id=uid, text="✅ آنبلاک شدید.")
        except Exception:
            pass


# ============ Webhook Endpoint ============
@flask_app.route("/", methods=["GET"])
def index():
    return "Relay Bot is running ✅", 200

@flask_app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)
        if not data:
            return "OK", 200

        update = telegram.Update.de_json(data, bot)

        if update.callback_query:
            cb = update.callback_query
            if cb.from_user.id == ADMIN_ID:
                handle_callback(cb)
            return "OK", 200

        if update.message:
            msg = update.message
            user = msg.from_user

            if msg.text == "/start":
                handle_start(msg, user)
                return "OK", 200

            if user.id == ADMIN_ID:
                handle_admin_message(msg, user)
                return "OK", 200

            handle_user_message(msg, user)
            return "OK", 200

        return "OK", 200
    except Exception as e:
        print(f"[webhook] خطا: {e}")
        import traceback
        traceback.print_exc()
        return "OK", 200


# ============ ست کردن Webhook ============
def setup_webhook():
    if not RENDER_URL:
        print("⚠️ RENDER_EXTERNAL_URL ست نشده")
        return
    webhook_url = f"{RENDER_URL}/webhook"
    print(f"🔧 در حال ست کردن Webhook روی: {webhook_url}")
    try:
        bot.delete_webhook()
        result = bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        print(f"✅ Webhook ست شد: {result}")
    except Exception as e:
        print(f"❌ خطا تو ست کردن Webhook: {e}")


# ============ اجرا ============
if __name__ == "__main__":
    db.init_db()
    setup_webhook()
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)