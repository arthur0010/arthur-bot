import sqlite3
from datetime import datetime

DB_NAME = "relay.db"


def init_db():
    """ساخت جدول‌ها اگه وجود نداشته باشن."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # جدول کاربران
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            is_blocked  INTEGER DEFAULT 0,
            first_seen  TEXT,
            last_seen   TEXT
        )
    """)

    # جدول نگاشت پیام ادمین → کاربر
    c.execute("""
        CREATE TABLE IF NOT EXISTS msg_map (
            admin_msg_id  INTEGER PRIMARY KEY,
            user_id       INTEGER
        )
    """)

    conn.commit()
    conn.close()


def _now():
    """زمان فعلی به صورت رشته."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============ مدیریت کاربران ============

def save_user(user_id, username, full_name):
    """ذخیره یا به‌روزرسانی کاربر."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute("""
            UPDATE users SET username = ?, full_name = ?, last_seen = ?
            WHERE user_id = ?
        """, (username, full_name, _now(), user_id))
    else:
        c.execute("""
            INSERT INTO users (user_id, username, full_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, full_name, _now(), _now()))
    conn.commit()
    conn.close()


def get_user_by_id(user_id):
    """دریافت یک کاربر با آیدی."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "SELECT user_id, username, full_name, is_blocked FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return row


def get_all_users():
    """لیست همه‌ی کاربران (جدیدترین فعالیت اول)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT user_id, username, full_name, is_blocked
        FROM users ORDER BY last_seen DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def get_active_user_ids():
    """آیدی همه‌ی کاربران بلاک‌نشده (برای broadcast)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_blocked = 0")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows


def search_users(query):
    """جستجو بر اساس اسم/یوزرنیم/آیدی."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    like = f"%{query}%"
    c.execute("""
        SELECT user_id, username, full_name, is_blocked FROM users
        WHERE full_name LIKE ? OR username LIKE ? OR CAST(user_id AS TEXT) LIKE ?
        ORDER BY last_seen DESC LIMIT 30
    """, (like, like, like))
    rows = c.fetchall()
    conn.close()
    return rows


def count_users():
    """تعداد کل و بلاک‌شده‌ها."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
    blocked = c.fetchone()[0]
    conn.close()
    return total, blocked


# ============ مدیریت بلاک ============

def is_blocked(user_id):
    """آیا کاربر بلاک شده؟"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def block_user(user_id):
    """بلاک کردن کاربر."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def unblock_user(user_id):
    """آنبلاک کردن کاربر."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_blocked_users():
    """لیست کاربران بلاک‌شده."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id, username, full_name FROM users WHERE is_blocked = 1")
    rows = c.fetchall()
    conn.close()
    return rows


# ============ نگاشت پیام‌ها ============

def save_msg_map(admin_msg_id, user_id):
    """ذخیره‌ی ارتباط بین پیام ادمین و کاربر."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO msg_map (admin_msg_id, user_id) VALUES (?, ?)",
        (admin_msg_id, user_id)
    )
    conn.commit()
    conn.close()


def get_user_from_msg(admin_msg_id):
    """پیدا کردن کاربر از روی پیام ادمین."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM msg_map WHERE admin_msg_id = ?", (admin_msg_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def clean_old_msg_map(limit=5000):
    """نگه‌داشتن فقط آخرین N نگاشت برای جلوگیری از حجیم شدن دیتابیس."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        DELETE FROM msg_map WHERE admin_msg_id NOT IN (
            SELECT admin_msg_id FROM msg_map ORDER BY admin_msg_id DESC LIMIT ?
        )
    """, (limit,))
    conn.commit()
    conn.close()