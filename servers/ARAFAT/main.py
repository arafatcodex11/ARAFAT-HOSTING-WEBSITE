import telebot
import os
import time
import sqlite3
import threading
import re
import random
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from telebot import types

# --- SETTINGS ---
BOT_TOKEN = '8746191675:AAEKrZoS9SjKvjtOKcdUd4nGkK60itj8p9E'
ADMIN_IDS = [7705767559]
MAIN_OWNER = 7705767559

CHATS_FILE = "all_chats.txt"
DB_FILE = "files_data.db"
BANNED_FILE = "banned_users.db"
BACKUP_FOLDER = "backups"

# --- BOT INIT ---
bot = telebot.TeleBot(BOT_TOKEN)

# --- THIRD PARTY API KEYS ---
OPENAI_API_KEY = "এখানে_তোমার_নতুন_OpenAI_key_বসাও"  # platform.openai.com থেকে নাও
EXEIO_API_KEY = "e1451d78c7e78c59df62c4d65d257f39025ce6a9"
BKASH_NUMBER = "01304057101"
EXEIO_DOMAIN = "exe.io"  # অথবা তোমার custom domain

# --- FIXED CHANNELS (DEFAULT) ---
FIXED_CH = "arafat_codex7"
FIXED_GR = "arafat_source"

# Bot start time for uptime
START_TIME = time.time()

# Anti-spam tracking: {user_id: [timestamps]}
spam_tracker = defaultdict(list)
# Muted users: {user_id: unmute_timestamp}
muted_users = {}
# Captcha pending: {user_id: (chat_id, answer)}
captcha_pending = {}
# New users waiting for captcha: {(chat_id, user_id)}
captcha_waiting = set()

# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS files (key TEXT PRIMARY KEY, file_id TEXT, type TEXT, caption TEXT, downloads INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS extra_menu (username TEXT PRIMARY KEY, button_name TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, permissions TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, reason TEXT, banned_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS warnings (user_id INTEGER, warning_count INTEGER, reason TEXT, PRIMARY KEY(user_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS user_activity (user_id INTEGER, command TEXT, timestamp TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS filters (keyword TEXT PRIMARY KEY, reply_text TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS scheduled_broadcast (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, message TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS user_notes (user_id INTEGER, note TEXT, timestamp TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS group_data (chat_id INTEGER PRIMARY KEY, title TEXT, joined_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS referrals (user_id INTEGER PRIMARY KEY, referred_by INTEGER, count INTEGER DEFAULT 0, joined_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS giveaway (id INTEGER PRIMARY KEY AUTOINCREMENT, prize TEXT, end_time TEXT, active INTEGER DEFAULT 1)')
    cursor.execute('CREATE TABLE IF NOT EXISTS giveaway_entries (giveaway_id INTEGER, user_id INTEGER, PRIMARY KEY(giveaway_id, user_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS quiz (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT, chat_id INTEGER, active INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS daily_report (last_sent TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS user_join_date (user_id INTEGER PRIMARY KEY, joined_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS bookmarks (user_id INTEGER, file_key TEXT, added_at TEXT, PRIMARY KEY(user_id, file_key))')
    cursor.execute('CREATE TABLE IF NOT EXISTS file_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, request_text TEXT, status TEXT DEFAULT "pending", requested_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subscribers (user_id INTEGER, category TEXT, PRIMARY KEY(user_id, category))')
    cursor.execute('CREATE TABLE IF NOT EXISTS coins (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS file_categories (file_key TEXT PRIMARY KEY, category TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, remind_at TEXT, message TEXT, sent INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()
    
    # Ban DB
    conn = sqlite3.connect(BANNED_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY, reason TEXT)')
    conn.commit()
    conn.close()

def add_admin(user_id, permissions="all"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO admins (user_id, permissions) VALUES (?, ?)', (user_id, permissions))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM admins')
    rows = [row[0] for row in cursor.fetchall()]
    conn.close()
    return rows

def is_admin(user_id):
    if user_id == MAIN_OWNER:
        return True
    return user_id in get_admins()

def add_banned(user_id, reason):
    conn = sqlite3.connect(BANNED_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO banned (user_id, reason) VALUES (?, ?)', (user_id, reason))
    conn.commit()
    conn.close()

def remove_banned(user_id):
    conn = sqlite3.connect(BANNED_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM banned WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect(BANNED_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM banned WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def add_warning(user_id, reason):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT warning_count FROM warnings WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    if row:
        new_count = row[0] + 1
        cursor.execute('UPDATE warnings SET warning_count=?, reason=? WHERE user_id=?', (new_count, reason, user_id))
    else:
        new_count = 1
        cursor.execute('INSERT INTO warnings (user_id, warning_count, reason) VALUES (?, ?, ?)', (user_id, new_count, reason))
    conn.commit()
    conn.close()
    return new_count

def get_warnings(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT warning_count, reason FROM warnings WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row if row else (0, "")

def reset_warnings(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM warnings WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def log_activity(user_id, command):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_activity (user_id, command, timestamp) VALUES (?, ?, ?)', 
                   (user_id, command, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_filter(keyword, reply):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO filters (keyword, reply_text) VALUES (?, ?)', (keyword.lower(), reply))
    conn.commit()
    conn.close()

def remove_filter(keyword):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM filters WHERE keyword=?', (keyword.lower(),))
    conn.commit()
    conn.close()

def get_filters():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT keyword, reply_text FROM filters')
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_user_note(user_id, note):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_notes (user_id, note, timestamp) VALUES (?, ?, ?)', 
                   (user_id, note, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_notes(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT note, timestamp FROM user_notes WHERE user_id=? ORDER BY timestamp DESC', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_scheduled_broadcast(broadcast_time, message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO scheduled_broadcast (time, message) VALUES (?, ?)', (broadcast_time, message))
    conn.commit()
    conn_id = cursor.lastrowid
    conn.close()
    return conn_id

def get_scheduled_broadcasts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, time, message FROM scheduled_broadcast')
    rows = cursor.fetchall()
    conn.close()
    return rows

def remove_scheduled_broadcast(bid):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM scheduled_broadcast WHERE id=?', (bid,))
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def add_group(chat_id, title):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO group_data (chat_id, title, joined_at) VALUES (?, ?, ?)', 
                   (chat_id, title, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_groups():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, title, joined_at FROM group_data')
    rows = cursor.fetchall()
    conn.close()
    return rows

def remove_group(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM group_data WHERE chat_id=?', (chat_id,))
    conn.commit()
    conn.close()

# Existing functions from original bot
def save_file_to_db(key, file_id, f_type, caption):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO files (key, file_id, type, caption, downloads) VALUES (?, ?, ?, ?, 0)', 
                   (key, file_id, f_type, caption))
    conn.commit()
    conn.close()

def get_file_from_db(key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, type, caption, downloads FROM files WHERE key=?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row

def increment_downloads(key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE files SET downloads = downloads + 1 WHERE key=?', (key,))
    conn.commit()
    conn.close()

def get_all_files():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT key, type, caption, downloads FROM files')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_file_from_db(key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM files WHERE key=?', (key,))
    conn.commit()
    conn.close()

def add_extra(username, button_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO extra_menu (username, button_name) VALUES (?, ?)', (username, button_name))
    conn.commit()
    conn.close()

def remove_extra(username):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM extra_menu WHERE username=?', (username,))
    conn.commit()
    conn.close()

def get_extra_list():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT username, button_name FROM extra_menu')
    rows = cursor.fetchall()
    conn.close()
    return rows

def set_fixed_channels(channel, group):
    global FIXED_CH, FIXED_GR
    FIXED_CH = channel
    FIXED_GR = group
    set_setting("fixed_ch", channel)
    set_setting("fixed_gr", group)

# Initialize DB
init_db()

# Load saved fixed channels
saved_ch = get_setting("fixed_ch")
saved_gr = get_setting("fixed_gr")
if saved_ch:
    FIXED_CH = saved_ch
if saved_gr:
    FIXED_GR = saved_gr

# --- USER LOGGING ---
all_chats = set()
if os.path.exists(CHATS_FILE):
    with open(CHATS_FILE, "r") as f:
        for line in f:
            if line.strip():
                try: all_chats.add(int(line.strip()))
                except: continue

def log_chat(message):
    chat_id = message.chat.id
    if chat_id not in all_chats:
        all_chats.add(chat_id)
        with open(CHATS_FILE, "a") as f:
            f.write(f"{chat_id}\n")

# --- BAN CHECK DECORATOR ---
def ban_check(func):
    def wrapper(message):
        if is_banned(message.from_user.id):
            bot.reply_to(message, "🚫 **You are banned from using this bot!**", parse_mode="Markdown")
            return
        return func(message)
    return wrapper

# --- START COMMAND ---
@bot.message_handler(commands=['start'])
@ban_check
def start(message):
    log_chat(message)
    chat_id = message.chat.id
    text_parts = message.text.split()
    user_id = message.from_user.id

    if len(text_parts) > 1:
        param = text_parts[1]

        # Handle referral link
        if param.startswith("ref_"):
            try:
                referrer_id = int(param.replace("ref_", ""))
                if referrer_id != user_id:
                    init_referral(user_id, referred_by=referrer_id)
                    bot.send_message(chat_id, "👋 **Welcome!** You joined via a referral link!", parse_mode="Markdown")
                    try:
                        add_coins(referrer_id, 10)
                        bot.send_message(referrer_id, f"🎉 Someone joined using your referral link!\n🪙 +10 coins পেয়েছো!\nTotal referrals: {get_referral_count(referrer_id)}")
                    except:
                        pass
            except:
                pass
            if is_admin(chat_id):
                show_admin_panel(message)
            else:
                bot.send_message(chat_id, "👋 **Welcome!**\n\nI am a File Store Bot. Use /help to see commands.", parse_mode="Markdown")
            return

        file_key = param
        f_data = get_file_from_db(file_key)
        
        if f_data:
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FIXED_CH}"))
            markup.add(types.InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{FIXED_GR}"))
            
            extras = get_extra_list()
            for username, btn_name in extras:
                markup.add(types.InlineKeyboardButton(f"{btn_name}", url=f"https://t.me/{username}"))
            
            markup.add(types.InlineKeyboardButton("✅ Verify & Get File", callback_data=f"check_{file_key}"))
            
            join_msg = f"📋 **Please join all channels to access the file:**\n\n1️⃣ Join {FIXED_CH}\n2️⃣ Join {FIXED_GR}\n"
            for _, btn_name in extras:
                join_msg += f"• {btn_name}\n"
            join_msg += "\n⚠️ **You must join ALL channels to get access.**"
            
            bot.send_message(chat_id, join_msg, reply_markup=markup, parse_mode="Markdown")
            return

    # Track new user referral with no referrer
    init_referral(user_id)

    if is_admin(chat_id):
        show_admin_panel(message)
    else:
        welcome_text = (
            "📁 *Welcome to File Store Bot!*\n\n"
            f"👋 Hello {message.from_user.first_name}!\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔹 /browse — Browse files\n"
            "🔹 /request — Request a file\n"
            "🔹 /subscribe — Get new file alerts\n"
            "🔹 /coins — Your coin balance\n"
            "🔹 /refer — Referral link\n"
            "🔹 /ai — Ask AI anything\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ Use a valid file link to get files.\n\n"
            "Enjoy! 🚀"
        )
        bot.send_message(chat_id, welcome_text, parse_mode="Markdown")

def show_admin_panel(message):
    panel1 = (
        "🛡️ ADMIN PANEL — Part 1\n\n"
        "📁 FILE MANAGEMENT:\n"
        "/setfile — Upload file\n"
        "/files — List all files\n"
        "/delfile [key] — Delete file\n"
        "/fileinfo [key] — File details\n"
        "/topfiles — Most downloaded\n"
        "/searchfile [query] — Search\n"
        "/setcategory [key] [cat] — Set category\n"
        "/browse — Browse by category\n"
        "/notify [key] — Alert subscribers\n"
        "/link [key] — Get deeplink\n\n"
        "👑 ADMIN MANAGEMENT:\n"
        "/addadmin [id] — Add admin\n"
        "/removeadmin [id] — Remove admin\n"
        "/admins — List admins\n\n"
        "🔗 CHANNELS:\n"
        "/add [name] [@user] — Add button\n"
        "/remove [@user] — Remove button\n"
        "/setfixed [ch] [gr] — Set fixed channels\n"
        "/channels — List channels\n\n"
        "📢 BROADCAST:\n"
        "/broadcast [msg] — Send to all\n"
        "/broadcastfwd — Forward message\n"
        "/schedule [HH:MM] [msg] — Schedule\n"
        "/testbroadcast [msg] — Test"
    )

    panel2 = (
        "🛡️ ADMIN PANEL — Part 2\n\n"
        "🚫 BAN & WARN:\n"
        "/ban [id] [reason] — Ban user\n"
        "/unban [id] — Unban\n"
        "/warn [id] — Warn user\n"
        "/warnings [id] — Check warns\n\n"
        "🛡️ MODERATION:\n"
        "/setantispam [on/off]\n"
        "/setantilink [on/off]\n"
        "/setantiforward [on/off]\n"
        "/setcaptcha [on/off]\n"
        "/maintenance [on/off]\n\n"
        "🎁 ENGAGEMENT:\n"
        "/giveaway [mins] [prize]\n"
        "/quiz [question] | [answer]\n"
        "/topreferrals — Top referrers\n"
        "/addcoins [id] [amount]\n"
        "/topcoins — Coin leaderboard\n\n"
        "📊 STATS & REPORTS:\n"
        "/stats — Bot stats\n"
        "/growth — 7 day growth\n"
        "/retention — User retention\n"
        "/downloadreport [key]\n"
        "/popular — Top files\n\n"
        "🔐 SECURITY:\n"
        "/backup — Backup DB\n"
        "/restore — Restore DB\n"
        "/cleanup — Clean old data\n"
        "/optimize — Optimize DB\n\n"
        "🤖 AI FEATURES:\n"
        "/ai [question] — Ask ChatGPT\n"
        "/caption [topic] — AI caption\n"
        "/shortlink [url] — Short link\n\n"
        "👤 USER FEATURES:\n"
        "/coins /topcoins /addcoins\n"
        "/requests — Pending file requests\n"
        "/donate — Donation button"
    )

    bot.send_message(message.chat.id, panel1)
    bot.send_message(message.chat.id, panel2)

# --- FILE MANAGEMENT COMMANDS ---
@bot.message_handler(commands=['setfile'])
def set_file_init(message):
    if not is_admin(message.chat.id):
        return
    msg = bot.send_message(message.chat.id, "📁 Please send the file (Video/Document/Photo) or just type some Text.")
    bot.register_next_step_handler(msg, process_content)

def process_content(message):
    file_id = None
    f_type = None

    if message.document:
        file_id, f_type = message.document.file_id, 'document'
    elif message.video:
        file_id, f_type = message.video.file_id, 'video'
    elif message.photo:
        file_id, f_type = message.photo[-1].file_id, 'photo'
    elif message.text:
        file_id, f_type = message.text, 'text'

    if file_id:
        if f_type != 'text':
            msg = bot.send_message(message.chat.id, "📝 Send the caption/name for this file.")
            bot.register_next_step_handler(msg, finalize_data, file_id, f_type)
        else:
            finalize_data(message, file_id, f_type)
    else:
        bot.send_message(message.chat.id, "❌ No file or text found. Try again.")

def finalize_data(message, file_id, f_type):
    caption = message.text if f_type != 'text' else ""
    key = f"file_{int(time.time())}"
    save_file_to_db(key, file_id, f_type, caption)
    bot_user = bot.get_me().username
    bot.send_message(message.chat.id, f"✅ **Link Created!**\n\n`https://t.me/{bot_user}?start={key}`\n\n**Key:** `{key}`", parse_mode="Markdown")

@bot.message_handler(commands=['files'])
def list_files(message):
    if not is_admin(message.chat.id):
        return
    files = get_all_files()
    if not files:
        bot.reply_to(message, "📂 No files found in database.")
        return
    
    msg = "📁 **File List:**\n\n"
    for key, f_type, caption, downloads in files[:20]:  # Show first 20
        msg += f"🔹 **Key:** `{key}`\n   Type: {f_type} | Downloads: {downloads}\n   Caption: {caption[:30] if caption else 'None'}...\n\n"
    
    if len(files) > 20:
        msg += f"\nAnd {len(files)-20} more files. Use /searchfile to find specific files."
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['delfile'])
def delete_file(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/delfile [key]`", parse_mode="Markdown")
        return
    
    key = parts[1]
    file_data = get_file_from_db(key)
    if file_data:
        delete_file_from_db(key)
        bot.reply_to(message, f"✅ File with key `{key}` has been deleted.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ No file found with key `{key}`.", parse_mode="Markdown")

@bot.message_handler(commands=['fileinfo'])
def file_info(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/fileinfo [key]`", parse_mode="Markdown")
        return
    
    key = parts[1]
    file_data = get_file_from_db(key)
    if file_data:
        f_id, f_type, caption, downloads = file_data
        info = f"📄 **File Info:**\n\n🔑 **Key:** `{key}`\n📁 **Type:** {f_type}\n📥 **Downloads:** {downloads}\n📝 **Caption:** {caption if caption else 'No caption'}\n🆔 **File ID:** `{f_id[:50]}...`"
        bot.send_message(message.chat.id, info, parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ No file found with key `{key}`.", parse_mode="Markdown")

@bot.message_handler(commands=['topfiles'])
def top_files(message):
    if not is_admin(message.chat.id):
        return
    files = get_all_files()
    if not files:
        bot.reply_to(message, "📂 No files found.")
        return
    
    sorted_files = sorted(files, key=lambda x: x[3], reverse=True)[:10]
    msg = "🏆 **Top 10 Most Downloaded Files:**\n\n"
    for i, (key, f_type, caption, downloads) in enumerate(sorted_files, 1):
        msg += f"{i}. `{key}` - {downloads} downloads\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['searchfile'])
def search_file(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/searchfile [query]`", parse_mode="Markdown")
        return
    
    query = parts[1].lower()
    files = get_all_files()
    results = [f for f in files if query in f[2].lower() or query in f[0].lower()]
    
    if not results:
        bot.reply_to(message, f"❌ No files found matching '{query}'.")
        return
    
    msg = f"🔍 **Search Results for '{query}':**\n\n"
    for key, f_type, caption, downloads in results[:10]:
        msg += f"🔹 `{key}` - {f_type} ({downloads} downloads)\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- ADMIN MANAGEMENT ---
@bot.message_handler(commands=['addadmin'])
def add_admin_cmd(message):
    if message.chat.id != MAIN_OWNER:
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/addadmin [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        add_admin(user_id)
        bot.reply_to(message, f"✅ User `{user_id}` added as admin.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_cmd(message):
    if message.chat.id != MAIN_OWNER:
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/removeadmin [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        remove_admin(user_id)
        bot.reply_to(message, f"✅ Admin `{user_id}` removed.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['admins'])
def list_admins(message):
    if not is_admin(message.chat.id):
        return
    admins = get_admins()
    msg = "👑 **Admin List:**\n\n"
    msg += f"👤 **Owner:** `{MAIN_OWNER}`\n\n"
    if admins:
        msg += "**Admins:**\n"
        for admin in admins:
            msg += f"🔹 `{admin}`\n"
    else:
        msg += "No additional admins."
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['setadminperm'])
def set_admin_perm(message):
    if message.chat.id != MAIN_OWNER:
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "❌ Usage: `/setadminperm [user_id] [perm]`\nPerms: all, files, broadcast, users", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        perm = parts[2]
        # Store permission in DB (simplified)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO admins (user_id, permissions) VALUES (?, ?)', (user_id, perm))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Admin `{user_id}` permission set to `{perm}`.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid input.")

@bot.message_handler(commands=['adminlog'])
def admin_log(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/adminlog [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT command, timestamp FROM user_activity WHERE user_id=? ORDER BY timestamp DESC LIMIT 20', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            bot.reply_to(message, f"No activity found for `{user_id}`.", parse_mode="Markdown")
            return
        
        msg = f"📋 **Activity Log for `{user_id}`:**\n\n"
        for cmd, ts in rows:
            msg += f"🔹 {cmd} - {ts[:16]}\n"
        
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

# --- VERIFICATION CHANNELS ---
@bot.message_handler(commands=['add'])
def add_menu_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) >= 3:
        username = parts[-1].replace("@", "").strip()
        button_name = " ".join(parts[1:-1])
        add_extra(username, button_name)
        bot.reply_to(message, f"✅ @{username} added with button name: '{button_name}'")
    else:
        bot.reply_to(message, "❌ Usage: `/add [Button Name] [@username]`", parse_mode="Markdown")

@bot.message_handler(commands=['remove'])
def remove_menu_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) > 1:
        username = parts[1].replace("@", "").strip()
        remove_extra(username)
        bot.reply_to(message, f"🗑️ @{username} has been removed.")
    else:
        bot.reply_to(message, "❌ Usage: `/remove [@username]`", parse_mode="Markdown")

@bot.message_handler(commands=['channels'])
def list_channels(message):
    if not is_admin(message.chat.id):
        return
    extras = get_extra_list()
    msg = f"🔗 **Verification Channels:**\n\n📢 **Fixed Channel:** @{FIXED_CH}\n👥 **Fixed Group:** @{FIXED_GR}\n\n"
    if extras:
        msg += "**Extra Buttons:**\n"
        for username, btn_name in extras:
            msg += f"🔹 {btn_name} -> @{username}\n"
    else:
        msg += "No extra buttons configured."
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['setfixed'])
def set_fixed(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "❌ Usage: `/setfixed [channel_username] [group_username]`\nExample: `/setfixed mychannel mygroup`", parse_mode="Markdown")
        return
    
    channel = parts[1].replace("@", "").strip()
    group = parts[2].replace("@", "").strip()
    set_fixed_channels(channel, group)
    bot.reply_to(message, f"✅ Fixed channels updated!\n📢 Channel: @{channel}\n👥 Group: @{group}", parse_mode="Markdown")

@bot.message_handler(commands=['checkmembership'])
def check_membership(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/checkmembership [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        all_to_check = [FIXED_CH, FIXED_GR] + [row[0] for row in get_extra_list()]
        results = []
        
        for username in all_to_check:
            try:
                status = bot.get_chat_member(f"@{username}", user_id).status
                joined = status in ['member', 'administrator', 'creator']
                results.append(f"@{username}: {'✅ Joined' if joined else '❌ Not joined'}")
            except:
                results.append(f"@{username}: ⚠️ Error checking")
        
        msg = f"📋 **Membership Status for User `{user_id}`:**\n\n" + "\n".join(results)
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

# --- BROADCAST SYSTEM ---
@bot.message_handler(commands=['broadcast'])
def broadcast_to_all(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Please include a message. Example: `/broadcast Hello everyone`")
        return
    
    broadcast_msg = args[1]
    success_count = 0
    fail_count = 0
    status_msg = bot.reply_to(message, "🚀 Starting Broadcast...")
    
    for chat_id in list(all_chats):
        try:
            bot.send_message(chat_id, broadcast_msg)
            success_count += 1
            time.sleep(0.1)
        except:
            fail_count += 1
    
    bot.edit_message_text(f"✅ **Broadcast Finished!**\n\n📨 Sent: {success_count}\n❌ Failed: {fail_count}", 
                          message.chat.id, status_msg.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['broadcastfwd'])
def broadcast_forward(message):
    if not is_admin(message.chat.id):
        return
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Please reply to a message to forward broadcast.")
        return
    
    success_count = 0
    status_msg = bot.reply_to(message, "🚀 Starting Forward Broadcast...")
    
    for chat_id in list(all_chats):
        try:
            bot.forward_message(chat_id, message.chat.id, message.reply_to_message.message_id)
            success_count += 1
            time.sleep(0.1)
        except:
            continue
    
    bot.edit_message_text(f"✅ **Forward Broadcast Finished!**\n\n📨 Sent: {success_count}", 
                          message.chat.id, status_msg.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['schedule'])
def schedule_broadcast(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/schedule [HH:MM] [message]`\nExample: `/schedule 14:30 Hello everyone`", parse_mode="Markdown")
        return
    
    time_str = args[1]
    msg_text = args[2]
    
    try:
        target_time = datetime.strptime(time_str, "%H:%M").time()
        now = datetime.now()
        scheduled_dt = datetime.combine(now.date(), target_time)
        
        if scheduled_dt < now:
            scheduled_dt += timedelta(days=1)
        
        bid = add_scheduled_broadcast(scheduled_dt.isoformat(), msg_text)
        
        # Start a thread to check schedule
        def check_schedule():
            time.sleep((scheduled_dt - now).total_seconds())
            for chat_id in list(all_chats):
                try:
                    bot.send_message(chat_id, msg_text)
                    time.sleep(0.1)
                except:
                    continue
            remove_scheduled_broadcast(bid)
        
        threading.Thread(target=check_schedule, daemon=True).start()
        
        bot.reply_to(message, f"✅ Broadcast scheduled at {time_str} (ID: {bid})", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid time format. Use HH:MM (24-hour format)")

@bot.message_handler(commands=['cancelbroadcast'])
def cancel_broadcast(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/cancelbroadcast [id]`", parse_mode="Markdown")
        return
    
    try:
        bid = int(parts[1])
        remove_scheduled_broadcast(bid)
        bot.reply_to(message, f"✅ Broadcast ID {bid} cancelled.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

@bot.message_handler(commands=['broadcaststatus'])
def broadcast_status(message):
    if not is_admin(message.chat.id):
        return
    schedules = get_scheduled_broadcasts()
    if not schedules:
        bot.reply_to(message, "📭 No scheduled broadcasts.")
        return
    
    msg = "📅 **Scheduled Broadcasts:**\n\n"
    for bid, btime, bmsg in schedules:
        msg += f"🆔 ID: {bid}\n⏰ Time: {btime[:16]}\n📝 Message: {bmsg[:50]}...\n\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['testbroadcast'])
def test_broadcast(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/testbroadcast [message]`", parse_mode="Markdown")
        return
    
    for admin in [MAIN_OWNER] + get_admins():
        try:
            bot.send_message(admin, f"🧪 **Test Broadcast:**\n\n{args[1]}", parse_mode="Markdown")
        except:
            continue
    
    bot.reply_to(message, "✅ Test broadcast sent to all admins.")

# --- STATISTICS ---
@bot.message_handler(commands=['stats'])
def bot_stats(message):
    if not is_admin(message.chat.id):
        return
    
    files = get_all_files()
    total_files = len(files)
    total_downloads = sum(f[3] for f in files)
    total_users = len(all_chats)
    admins_count = len(get_admins())
    extras_count = len(get_extra_list())
    
    stats_msg = f"""
📊 **BOT STATISTICS**

👥 **Users:** {total_users}
📁 **Files:** {total_files}
📥 **Total Downloads:** {total_downloads}
👑 **Admins:** {admins_count + 1}
🔗 **Channels:** {extras_count + 2}
💾 **Database Size:** {os.path.getsize(DB_FILE) / 1024:.2f} KB

🕐 **Uptime:** {get_uptime()}
"""
    bot.send_message(message.chat.id, stats_msg, parse_mode="Markdown")

@bot.message_handler(commands=['userstats'])
def user_stats(message):
    if not is_admin(message.chat.id):
        return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_activity')
    active_users = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT user_id, COUNT(*) as cmd_count FROM user_activity GROUP BY user_id ORDER BY cmd_count DESC LIMIT 10')
    top_users = cursor.fetchall()
    conn.close()
    
    msg = f"📊 **User Statistics:**\n\n👥 **Total Users:** {len(all_chats)}\n⭐ **Active Users:** {active_users}\n\n**🏆 Top 10 Active Users:**\n"
    
    for i, (uid, count) in enumerate(top_users, 1):
        msg += f"{i}. `{uid}` - {count} commands\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['filestats'])
def file_stats(message):
    if not is_admin(message.chat.id):
        return
    files = get_all_files()
    
    type_counts = {'document': 0, 'video': 0, 'photo': 0, 'text': 0}
    for _, f_type, _, _ in files:
        if f_type in type_counts:
            type_counts[f_type] += 1
    
    msg = f"📁 **File Statistics:**\n\n📄 Total Files: {len(files)}\n\n**By Type:**\n"
    for f_type, count in type_counts.items():
        msg += f"🔹 {f_type}: {count}\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['groupstats'])
def group_stats(message):
    if not is_admin(message.chat.id):
        return
    groups = get_all_groups()
    
    msg = f"💬 **Group Statistics:**\n\n📊 Total Groups: {len(groups)}\n\n**Group List:**\n"
    for chat_id, title, joined_at in groups[:20]:
        msg += f"🔹 {title[:30]} - `{chat_id}`\n"
    
    if len(groups) > 20:
        msg += f"\nAnd {len(groups)-20} more groups."
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['commandstats'])
def command_stats(message):
    if not is_admin(message.chat.id):
        return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT command, COUNT(*) as count FROM user_activity GROUP BY command ORDER BY count DESC LIMIT 15')
    rows = cursor.fetchall()
    conn.close()
    
    msg = "📊 **Command Usage Statistics:**\n\n"
    for cmd, count in rows:
        msg += f"🔹 {cmd}: {count} times\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['hourlystats'])
def hourly_stats(message):
    if not is_admin(message.chat.id):
        return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT strftime("%H", timestamp) as hour, COUNT(*) FROM user_activity GROUP BY hour ORDER BY hour')
    rows = cursor.fetchall()
    conn.close()
    
    msg = "📊 **Hourly Activity:**\n\n"
    for hour, count in rows:
        bar = "█" * (count // 10) if count > 10 else "▏"
        msg += f"{hour}:00 {bar} {count}\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- BAN MANAGEMENT ---
@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/ban [user_id] [reason]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        add_banned(user_id, reason)
        bot.reply_to(message, f"✅ User `{user_id}` banned.\n📝 Reason: {reason}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/unban [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        remove_banned(user_id)
        bot.reply_to(message, f"✅ User `{user_id}` unbanned.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['banned'])
def list_banned(message):
    if not is_admin(message.chat.id):
        return
    
    conn = sqlite3.connect(BANNED_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, reason FROM banned')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "📭 No banned users.")
        return
    
    msg = "🚫 **Banned Users:**\n\n"
    for user_id, reason in rows:
        msg += f"🔹 `{user_id}` - {reason}\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['warn'])
def warn_user(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/warn [user_id] [reason]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "No reason"
        count = add_warning(user_id, reason)
        
        if count >= 5:
            add_banned(user_id, f"Auto-banned after {count} warnings")
            bot.reply_to(message, f"⚠️ User `{user_id}` has been auto-banned after {count} warnings.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"⚠️ User `{user_id}` warned ({count}/5).\nReason: {reason}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['warnings'])
def check_warnings(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/warnings [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        count, reason = get_warnings(user_id)
        bot.reply_to(message, f"⚠️ User `{user_id}` has {count}/5 warnings.\nLast reason: {reason}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['resetwarns'])
def reset_warns(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/resetwarns [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        reset_warnings(user_id)
        bot.reply_to(message, f"✅ Warnings reset for `{user_id}`.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

# --- BOT SETTINGS ---
@bot.message_handler(commands=['settings'])
def view_settings(message):
    if not is_admin(message.chat.id):
        return
    
    welcome_msg = get_setting("welcome_msg", "Welcome to the bot!")
    goodbye_msg = get_setting("goodbye_msg", "Goodbye!")
    rules = get_setting("rules", "No rules set.")
    language = get_setting("language", "en")
    antispam = get_setting("antispam", "off")
    
    msg = f"""
⚙️ **Bot Settings:**

👋 **Welcome:** {welcome_msg[:50]}
👋 **Goodbye:** {goodbye_msg[:50]}
📜 **Rules:** {rules[:50]}...
🌐 **Language:** {language}
🛡️ **Anti-Spam:** {antispam}

📢 **Fixed Channel:** @{FIXED_CH}
👥 **Fixed Group:** @{FIXED_GR}
"""
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['setwelcome'])
def set_welcome(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/setwelcome [message]`", parse_mode="Markdown")
        return
    
    set_setting("welcome_msg", args[1])
    bot.reply_to(message, "✅ Welcome message updated!")

@bot.message_handler(commands=['setgoodbye'])
def set_goodbye(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/setgoodbye [message]`", parse_mode="Markdown")
        return
    
    set_setting("goodbye_msg", args[1])
    bot.reply_to(message, "✅ Goodbye message updated!")

@bot.message_handler(commands=['setrules'])
def set_rules(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/setrules [text]`", parse_mode="Markdown")
        return
    
    set_setting("rules", args[1])
    bot.reply_to(message, "✅ Rules updated!")

@bot.message_handler(commands=['setlang'])
def set_language(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['en', 'bn']:
        bot.reply_to(message, "❌ Usage: `/setlang [en/bn]`", parse_mode="Markdown")
        return
    
    set_setting("language", args[1])
    bot.reply_to(message, f"✅ Language set to {args[1]}")

@bot.message_handler(commands=['setbutton'])
def set_custom_button(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/setbutton [name] [url]`", parse_mode="Markdown")
        return
    
    set_setting("custom_btn_name", args[1])
    set_setting("custom_btn_url", args[2])
    bot.reply_to(message, f"✅ Custom button added: {args[1]}")

@bot.message_handler(commands=['resetall'])
def reset_all_settings(message):
    if message.chat.id != MAIN_OWNER:
        return
    
    confirm_msg = bot.reply_to(message, "⚠️ This will reset ALL settings. Type `yes` to confirm.", parse_mode="Markdown")
    bot.register_next_step_handler(confirm_msg, confirm_reset)

def confirm_reset(message):
    if message.text.lower() == 'yes':
        set_setting("welcome_msg", "")
        set_setting("goodbye_msg", "")
        set_setting("rules", "")
        set_setting("language", "en")
        set_setting("antispam", "off")
        bot.reply_to(message, "✅ All settings reset to default.")
    else:
        bot.reply_to(message, "❌ Reset cancelled.")

# --- AUTO-MODERATION ---
@bot.message_handler(commands=['addfilter'])
def add_filter_cmd(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/addfilter [word] [reply]`", parse_mode="Markdown")
        return
    
    add_filter(args[1], args[2])
    bot.reply_to(message, f"✅ Filter added for '{args[1]}'")

@bot.message_handler(commands=['removefilter'])
def remove_filter_cmd(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/removefilter [word]`", parse_mode="Markdown")
        return
    
    remove_filter(args[1])
    bot.reply_to(message, f"✅ Filter removed for '{args[1]}'")

@bot.message_handler(commands=['filters'])
def list_filters_cmd(message):
    if not is_admin(message.chat.id):
        return
    
    filters = get_filters()
    if not filters:
        bot.reply_to(message, "📭 No filters configured.")
        return
    
    msg = "🔍 **Active Filters:**\n\n"
    for keyword, reply in filters:
        msg += f"🔹 `{keyword}` -> {reply[:30]}...\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['setantispam'])
def set_antispam(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/setantispam [on/off]`", parse_mode="Markdown")
        return
    
    set_setting("antispam", args[1])
    bot.reply_to(message, f"✅ Anti-spam turned {args[1]}")

@bot.message_handler(commands=['setlangfilter'])
def set_lang_filter(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/setlangfilter [on/off]`", parse_mode="Markdown")
        return
    
    set_setting("lang_filter", args[1])
    bot.reply_to(message, f"✅ Language filter turned {args[1]}")

@bot.message_handler(commands=['setwordfilter'])
def set_word_filter(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/setwordfilter [word]`", parse_mode="Markdown")
        return
    
    blocked = get_setting("blocked_words", "")
    if blocked:
        blocked += f",{args[1]}"
    else:
        blocked = args[1]
    set_setting("blocked_words", blocked)
    bot.reply_to(message, f"✅ Word '{args[1]}' added to blocked list")

# --- USER MANAGEMENT ---
@bot.message_handler(commands=['userinfo'])
def user_info(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    user_id = parts[1] if len(parts) > 1 else str(message.reply_to_message.from_user.id) if message.reply_to_message else str(message.from_user.id)
    
    try:
        uid = int(user_id)
        is_banned_status = is_banned(uid)
        warnings_count, _ = get_warnings(uid)
        
        # Get user activity count
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM user_activity WHERE user_id=?', (uid,))
        activity_count = cursor.fetchone()[0]
        conn.close()
        
        msg = f"""
👤 **User Information:**

🆔 **User ID:** `{uid}`
🚫 **Banned:** {'Yes' if is_banned_status else 'No'}
⚠️ **Warnings:** {warnings_count}/5
📊 **Commands Used:** {activity_count}
"""
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['usernote'])
def add_user_note_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ Usage: `/usernote [user_id] [note]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        note = parts[2]
        add_user_note(user_id, note)
        bot.reply_to(message, f"✅ Note added for `{user_id}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['usernotes'])
def get_user_notes_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/usernotes [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        notes = get_user_notes(user_id)
        
        if not notes:
            bot.reply_to(message, f"📭 No notes for `{user_id}`.", parse_mode="Markdown")
            return
        
        msg = f"📝 **Notes for `{user_id}`:**\n\n"
        for note, ts in notes[:10]:
            msg += f"🔹 {note[:50]}... ({ts[:16]})\n"
        
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['activity'])
def user_activity(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/activity [user_id]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT command, timestamp FROM user_activity WHERE user_id=? ORDER BY timestamp DESC LIMIT 20', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            bot.reply_to(message, f"📭 No activity for `{user_id}`.", parse_mode="Markdown")
            return
        
        msg = f"📊 **Recent Activity for `{user_id}`:**\n\n"
        for cmd, ts in rows[:10]:
            msg += f"🔹 {cmd} - {ts[5:16]}\n"
        
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid user ID.")

@bot.message_handler(commands=['exportusers'])
def export_users(message):
    if not is_admin(message.chat.id):
        return
    
    filename = f"users_export_{int(time.time())}.txt"
    with open(filename, "w") as f:
        for chat_id in all_chats:
            f.write(f"{chat_id}\n")
    
    with open(filename, "rb") as f:
        bot.send_document(message.chat.id, f, caption=f"📊 Exported {len(all_chats)} users")
    
    os.remove(filename)

@bot.message_handler(commands=['importusers'])
def import_users(message):
    if not is_admin(message.chat.id):
        return
    if not message.reply_to_message or not message.reply_to_message.document:
        bot.reply_to(message, "❌ Please reply to a text file with user IDs.")
        return
    
    file_info = bot.get_file(message.reply_to_message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    new_users = 0
    for line in downloaded_file.decode().splitlines():
        if line.strip():
            try:
                uid = int(line.strip())
                if uid not in all_chats:
                    all_chats.add(uid)
                    with open(CHATS_FILE, "a") as f:
                        f.write(f"{uid}\n")
                    new_users += 1
            except:
                continue
    
    bot.reply_to(message, f"✅ Imported {new_users} new users.")

# --- GROUP MANAGEMENT ---
@bot.message_handler(commands=['groups'])
def list_groups(message):
    if not is_admin(message.chat.id):
        return
    groups = get_all_groups()
    
    if not groups:
        bot.reply_to(message, "📭 Bot is not in any groups.")
        return
    
    msg = "💬 **Bot Groups:**\n\n"
    for chat_id, title, joined_at in groups:
        msg += f"🔹 {title} - `{chat_id}`\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['leave'])
def leave_group(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/leave [chat_id]`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(parts[1])
        bot.leave_chat(chat_id)
        remove_group(chat_id)
        bot.reply_to(message, f"✅ Left group `{chat_id}`.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Failed to leave group.")

@bot.message_handler(commands=['setgrouptitle'])
def set_group_title(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/setgrouptitle [chat_id] [title]`", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(args[1])
        title = args[2]
        bot.set_chat_title(chat_id, title)
        bot.reply_to(message, f"✅ Group title updated to '{title}'")
    except:
        bot.reply_to(message, "❌ Failed to set title.")

@bot.message_handler(commands=['setgrouppic'])
def set_group_pic(message):
    if not is_admin(message.chat.id):
        return
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "❌ Reply to a photo to set as group picture.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/setgrouppic [chat_id]` (reply to a photo)", parse_mode="Markdown")
        return
    
    try:
        chat_id = int(parts[1])
        file_id = message.reply_to_message.photo[-1].file_id
        bot.set_chat_photo(chat_id, file_id)
        bot.reply_to(message, "✅ Group picture updated.")
    except:
        bot.reply_to(message, "❌ Failed to set picture.")

@bot.message_handler(commands=['promote'])
def promote_user(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/promote [user_id]` (use in group)", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        bot.promote_chat_member(message.chat.id, user_id, can_change_info=True, can_delete_messages=True, 
                                can_invite_users=True, can_restrict_members=True, can_pin_messages=True)
        bot.reply_to(message, f"✅ User `{user_id}` promoted in this group.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Failed to promote user.")

@bot.message_handler(commands=['demote'])
def demote_user(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/demote [user_id]` (use in group)", parse_mode="Markdown")
        return
    
    try:
        user_id = int(parts[1])
        bot.promote_chat_member(message.chat.id, user_id, can_change_info=False, can_delete_messages=False,
                                can_invite_users=False, can_restrict_members=False, can_pin_messages=False)
        bot.reply_to(message, f"✅ User `{user_id}` demoted in this group.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Failed to demote user.")

# --- SECURITY ---
@bot.message_handler(commands=['backup'])
def backup_database(message):
    if not is_admin(message.chat.id):
        return
    
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)
    
    backup_name = f"{BACKUP_FOLDER}/backup_{int(time.time())}.db"
    
    import shutil
    shutil.copy(DB_FILE, backup_name)
    
    with open(backup_name, "rb") as f:
        bot.send_document(message.chat.id, f, caption=f"✅ Database backup created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    os.remove(backup_name)

@bot.message_handler(commands=['restore'])
def restore_database(message):
    if message.chat.id != MAIN_OWNER:
        return
    if not message.reply_to_message or not message.reply_to_message.document:
        bot.reply_to(message, "❌ Reply to a backup file to restore.")
        return
    
    file_info = bot.get_file(message.reply_to_message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    # Backup current before restore
    import shutil
    shutil.copy(DB_FILE, f"{DB_FILE}.old")
    
    with open(DB_FILE, "wb") as f:
        f.write(downloaded_file)
    
    bot.reply_to(message, "✅ Database restored successfully! Old database saved as files_data.db.old")
    init_db()  # Re-initialize to ensure tables exist

@bot.message_handler(commands=['listbackups'])
def list_backups(message):
    if not is_admin(message.chat.id):
        return
    
    if not os.path.exists(BACKUP_FOLDER):
        bot.reply_to(message, "📭 No backups found.")
        return
    
    backups = os.listdir(BACKUP_FOLDER)
    if not backups:
        bot.reply_to(message, "📭 No backups found.")
        return
    
    msg = "💾 **Backup Files:**\n\n"
    for b in backups:
        size = os.path.getsize(f"{BACKUP_FOLDER}/{b}") / 1024
        msg += f"🔹 {b} - {size:.2f} KB\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['cleanup'])
def cleanup_data(message):
    if not is_admin(message.chat.id):
        return
    
    # Delete old activity logs (older than 30 days)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('DELETE FROM user_activity WHERE timestamp < ?', (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    bot.reply_to(message, f"✅ Cleaned up {deleted} old activity records.")

@bot.message_handler(commands=['optimize'])
def optimize_db(message):
    if not is_admin(message.chat.id):
        return
    
    conn = sqlite3.connect(DB_FILE)
    conn.execute("VACUUM")
    conn.execute("ANALYZE")
    conn.close()
    
    bot.reply_to(message, "✅ Database optimized (VACUUM & ANALYZE completed).")

@bot.message_handler(commands=['resetstats'])
def reset_stats(message):
    if message.chat.id != MAIN_OWNER:
        return
    
    confirm_msg = bot.reply_to(message, "⚠️ This will reset ALL statistics. Type `yes` to confirm.", parse_mode="Markdown")
    bot.register_next_step_handler(confirm_msg, confirm_stats_reset)

def confirm_stats_reset(message):
    if message.text.lower() == 'yes':
        conn = sqlite3.connect(DB_FILE)
        conn.execute('DELETE FROM user_activity')
        conn.execute('UPDATE files SET downloads = 0')
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ All statistics reset.")
    else:
        bot.reply_to(message, "❌ Reset cancelled.")

# --- OTHER COMMANDS ---
@bot.message_handler(commands=['id'])
def get_id(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    msg = f"🆔 **Chat ID:** `{chat_id}`\n👤 **Your ID:** `{user_id}`"
    
    if message.reply_to_message:
        msg += f"\n👥 **Replied User ID:** `{message.reply_to_message.from_user.id}`"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['info'])
def bot_info(message):
    bot_user = bot.get_me()
    msg = f"""
🤖 **Bot Information:**

📛 **Name:** {bot_user.first_name}
🔖 **Username:** @{bot_user.username}
🆔 **ID:** `{bot_user.id}`

📊 **Stats:**
👥 **Total Users:** {len(all_chats)}
📁 **Files:** {len(get_all_files())}

👑 **Owner:** @Owner
📅 **Language:** Python (pyTelegramBotAPI)
"""
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['ping'])
def ping(message):
    start = time.time()
    msg = bot.reply_to(message, "🏓 Pong!")
    end = time.time()
    bot.edit_message_text(f"🏓 Pong!\n⏱️ Response time: {round((end - start) * 1000)}ms", 
                          message.chat.id, msg.message_id)

def get_uptime():
    diff = time.time() - START_TIME
    days = int(diff // 86400)
    hours = int((diff % 86400) // 3600)
    minutes = int((diff % 3600) // 60)
    seconds = int(diff % 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    else:
        return f"{minutes}m {seconds}s"

@bot.message_handler(commands=['uptime'])
def uptime(message):
    bot.reply_to(message, f"🕐 **Bot Uptime:** {get_uptime()}", parse_mode="Markdown")

@bot.message_handler(commands=['restart'])
def restart_bot(message):
    if message.chat.id != MAIN_OWNER:
        return
    bot.reply_to(message, "🔄 Restarting bot...")
    os._exit(0)

@bot.message_handler(commands=['shutdown'])
def shutdown_bot(message):
    if message.chat.id != MAIN_OWNER:
        return
    bot.reply_to(message, "🛑 Shutting down bot...")
    os._exit(0)

@bot.message_handler(commands=['log'])
def get_log(message):
    if not is_admin(message.chat.id):
        return
    
    # Send recent activity as log
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, command, timestamp FROM user_activity ORDER BY timestamp DESC LIMIT 30')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "📭 No recent activity.")
        return
    
    log_msg = "📋 **Recent Activity Log:**\n\n"
    for user_id, cmd, ts in rows:
        log_msg += f"🔹 `{user_id}`: {cmd} - {ts[5:16]}\n"
    
    # Split if too long
    if len(log_msg) > 4000:
        bot.send_message(message.chat.id, log_msg[:4000])
        bot.send_message(message.chat.id, log_msg[4000:8000])
    else:
        bot.send_message(message.chat.id, log_msg, parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def help_command(message):
    if is_admin(message.chat.id):
        show_admin_panel(message)
    else:
        help_text = """
🤖 **Available Commands:**

/start - Start the bot
/help - Show this help menu
/id - Get your ID
/info - Bot information
/ping - Check bot status

📁 **To get files:**
Use the link provided by admin.

❓ Need help? Contact bot owner.
"""
        bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# --- VERIFY CALLBACK ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def check_callback(call):
    file_key = call.data.replace("check_", "")
    user_id = call.from_user.id
    
    if is_banned(user_id):
        bot.answer_callback_query(call.id, "🚫 You are banned from using this bot!", show_alert=True)
        return
    
    try:
        extras = [row[0] for row in get_extra_list()]
        all_to_check = [FIXED_CH, FIXED_GR] + extras
        joined = True
        not_joined = []
        
        for username in all_to_check:
            try:
                status = bot.get_chat_member(f"@{username}", user_id).status
                if status not in ['member', 'administrator', 'creator']:
                    joined = False
                    not_joined.append(f"@{username}")
            except:
                not_joined.append(f"@{username} (check failed)")
                joined = False

        if joined:
            f_data = get_file_from_db(file_key)
            if f_data:
                f_id, f_type, f_cap, downloads = f_data
                increment_downloads(file_key)
                
                if f_type == 'document':
                    bot.send_document(user_id, f_id, caption=f_cap)
                elif f_type == 'video':
                    bot.send_video(user_id, f_id, caption=f_cap)
                elif f_type == 'photo':
                    bot.send_photo(user_id, f_id, caption=f_cap)
                elif f_type == 'text':
                    bot.send_message(user_id, f_id)

                # Give coins for downloading
                add_coins(user_id, 2)
                # Log download
                log_activity(user_id, f"download_{file_key}")
                
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.answer_callback_query(call.id, "✅ Here is your file!", show_alert=False)
            else:
                bot.answer_callback_query(call.id, "❌ File not found!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"❌ You haven't joined: {', '.join(not_joined[:3])}", show_alert=True)
    except Exception as e:
        bot.answer_callback_query(call.id, f"⚠️ Error: Make sure bot is admin in all channels.", show_alert=True)

# --- AUTO-MODERATION HANDLER FOR GROUP MESSAGES ---
@bot.message_handler(func=lambda message: True)
def auto_moderate(message):
    if not message.text:
        return

    user_id = message.from_user.id

    # Maintenance mode — block non-admins
    if get_setting("maintenance", "off") == "on" and not is_admin(user_id):
        bot.delete_message(message.chat.id, message.message_id)
        bot.send_message(user_id, "🔧 Bot is under maintenance. Please try again later.")
        return

    # Block banned users
    if is_banned(user_id):
        return

    # Anti-spam check
    if get_setting("antispam", "off") == "on" and not is_admin(user_id):
        if is_muted(user_id):
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return
        if is_spamming(user_id):
            muted_users[user_id] = time.time() + 60  # mute 60 seconds
            try:
                bot.delete_message(message.chat.id, message.message_id)
                bot.send_message(message.chat.id, f"🚫 {message.from_user.first_name} muted for 60 seconds due to spam.")
            except:
                pass
            return

    # Anti-link check (groups only)
    if message.chat.type in ['group', 'supergroup']:
        if get_setting("antilink", "off") == "on" and not is_admin(user_id):
            if contains_link(message.text):
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    bot.send_message(message.chat.id, f"🔗 Links are not allowed here, {message.from_user.first_name}!")
                except:
                    pass
                return

        # Anti-forward check
        if get_setting("antiforward", "off") == "on" and not is_admin(user_id):
            if message.forward_from or message.forward_from_chat:
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    bot.send_message(message.chat.id, f"↩️ Forwarded messages are not allowed here!")
                except:
                    pass
                return

        # Captcha waiting check
        if (message.chat.id, user_id) in captcha_waiting:
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return

    if message.chat.id in active_quiz and not message.text.startswith('/'):
        quiz = active_quiz[message.chat.id]
        if message.text.strip().lower() == quiz["answer"]:
            del active_quiz[message.chat.id]
            add_coins(message.from_user.id, 5)
            bot.reply_to(message, f"🎉 **Correct!** {message.from_user.first_name} got it right!\n✅ Answer: **{quiz['answer']}**\n🪙 +5 coins পেয়েছো!", parse_mode="Markdown")
            return

    # Check for filters
    filters = get_filters()
    for keyword, reply in filters:
        if keyword in message.text.lower():
            bot.reply_to(message, reply)
            break

    # Check blocked words
    blocked_words = get_setting("blocked_words", "")
    if blocked_words:
        for word in blocked_words.split(","):
            if word.strip() and word.strip() in message.text.lower():
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    bot.send_message(message.chat.id, f"🚫 Blocked word detected!")
                except:
                    pass
                break

    # Log activity for non-command messages
    if not message.text.startswith('/'):
        log_activity(message.from_user.id, "message")

# --- NEW CHAT MEMBER HANDLER ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(message):
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            add_group(message.chat.id, message.chat.title)
            bot.send_message(message.chat.id, "🤖 Thanks for adding me! Use /help to see commands.")
        else:
            # Track user join
            init_referral(new_member.id)

            # Captcha system
            if get_setting("captcha", "off") == "on":
                send_captcha(message.chat.id, new_member.id, new_member.first_name)
            else:
                welcome_msg = get_setting("welcome_msg")
                if welcome_msg:
                    bot.send_message(message.chat.id, welcome_msg.format(user=new_member.first_name))

# --- LEFT CHAT MEMBER HANDLER ---
@bot.message_handler(content_types=['left_chat_member'])
def goodbye_member(message):
    if message.left_chat_member.id == bot.get_me().id:
        remove_group(message.chat.id)
    else:
        goodbye_msg = get_setting("goodbye_msg")
        if goodbye_msg:
            bot.send_message(message.chat.id, goodbye_msg)

# ============================================================
# 🛡️ ANTI-LINK / ANTI-FORWARD SYSTEM
# ============================================================

def contains_link(text):
    if not text:
        return False
    url_pattern = re.compile(r'(https?://|t\.me/|@\w+|www\.)', re.IGNORECASE)
    return bool(url_pattern.search(text))

@bot.message_handler(commands=['setantilink'])
def set_antilink(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/setantilink [on/off]`", parse_mode="Markdown")
        return
    set_setting("antilink", args[1])
    bot.reply_to(message, f"🔗 Anti-Link turned {args[1]}")

@bot.message_handler(commands=['setantiforward'])
def set_antiforward(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/setantiforward [on/off]`", parse_mode="Markdown")
        return
    set_setting("antiforward", args[1])
    bot.reply_to(message, f"↩️ Anti-Forward turned {args[1]}")

# ============================================================
# 🔢 CAPTCHA SYSTEM
# ============================================================

def send_captcha(chat_id, user_id, user_name):
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    answer = str(a + b)
    captcha_pending[user_id] = (chat_id, answer)
    captcha_waiting.add((chat_id, user_id))

    markup = types.InlineKeyboardMarkup(row_width=3)
    choices = list({answer, str(random.randint(1,20)), str(random.randint(1,20)), str(random.randint(1,20))})[:4]
    random.shuffle(choices)
    for c in choices:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"captcha_{user_id}_{c}_{answer}"))

    try:
        bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
    except:
        pass

    bot.send_message(chat_id,
        f"🔐 **Captcha Required!**\n\n"
        f"Welcome {user_name}! Solve this to join:\n\n"
        f"**{a} + {b} = ?**\n\n"
        f"⏳ You have 60 seconds.",
        reply_markup=markup, parse_mode="Markdown"
    )

    def auto_kick():
        time.sleep(60)
        if user_id in captcha_pending:
            del captcha_pending[user_id]
            captcha_waiting.discard((chat_id, user_id))
            try:
                bot.ban_chat_member(chat_id, user_id)
                bot.unban_chat_member(chat_id, user_id)
                bot.send_message(chat_id, f"⏰ User {user_name} was removed for not solving captcha.")
            except:
                pass
    threading.Thread(target=auto_kick, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("captcha_"))
def captcha_callback(call):
    parts = call.data.split("_")
    if len(parts) < 4:
        return
    target_uid = int(parts[1])
    chosen = parts[2]
    correct = parts[3]

    if call.from_user.id != target_uid:
        bot.answer_callback_query(call.id, "❌ This captcha is not for you!", show_alert=True)
        return

    if chosen == correct:
        if target_uid in captcha_pending:
            del captcha_pending[target_uid]
        captcha_waiting.discard((call.message.chat.id, target_uid))
        try:
            bot.restrict_chat_member(call.message.chat.id, target_uid,
                can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        except:
            pass
        bot.answer_callback_query(call.id, "✅ Correct! Welcome!", show_alert=True)
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "❌ Wrong answer! Try again.", show_alert=True)

@bot.message_handler(commands=['setcaptcha'])
def set_captcha(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/setcaptcha [on/off]`", parse_mode="Markdown")
        return
    set_setting("captcha", args[1])
    bot.reply_to(message, f"🔐 Captcha turned {args[1]}")

# ============================================================
# 🏆 REFERRAL SYSTEM
# ============================================================

def init_referral(user_id, referred_by=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM referrals WHERE user_id=?', (user_id,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO referrals (user_id, referred_by, count, joined_at) VALUES (?, ?, 0, ?)',
                       (user_id, referred_by, datetime.now().isoformat()))
        if referred_by:
            cursor.execute('UPDATE referrals SET count = count + 1 WHERE user_id=?', (referred_by,))
    conn.commit()
    conn.close()

def get_referral_count(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT count FROM referrals WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

@bot.message_handler(commands=['refer'])
def refer_cmd(message):
    user_id = message.from_user.id
    bot_user = bot.get_me().username
    ref_link = f"https://t.me/{bot_user}?start=ref_{user_id}"
    count = get_referral_count(user_id)
    bot.reply_to(message,
        f"🔗 **Your Referral Link:**\n\n`{ref_link}`\n\n"
        f"👥 **Total Referrals:** {count}\n\n"
        f"Share this link and earn credit when friends join!",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['topreferrals'])
def top_referrals(message):
    if not is_admin(message.chat.id):
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, count FROM referrals ORDER BY count DESC LIMIT 10')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, "📭 No referral data yet.")
        return

    msg = "🏆 **Top Referrers:**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, count) in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} `{uid}` — {count} referrals\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# ============================================================
# 🎁 GIVEAWAY SYSTEM
# ============================================================

@bot.message_handler(commands=['giveaway'])
def start_giveaway(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/giveaway [minutes] [prize]`\nExample: `/giveaway 60 Premium Access`", parse_mode="Markdown")
        return

    try:
        minutes = int(args[1])
        prize = args[2]
        end_time = (datetime.now() + timedelta(minutes=minutes)).isoformat()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO giveaway (prize, end_time, active) VALUES (?, ?, 1)', (prize, end_time))
        gid = cursor.lastrowid
        conn.commit()
        conn.close()

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎉 Join Giveaway!", callback_data=f"giveaway_{gid}"))

        bot.send_message(message.chat.id,
            f"🎁 **GIVEAWAY STARTED!**\n\n"
            f"🏆 Prize: **{prize}**\n"
            f"⏰ Ends in: {minutes} minutes\n"
            f"Click below to enter!",
            reply_markup=markup, parse_mode="Markdown"
        )

        def end_giveaway():
            time.sleep(minutes * 60)
            conn2 = sqlite3.connect(DB_FILE)
            cursor2 = conn2.cursor()
            cursor2.execute('SELECT user_id FROM giveaway_entries WHERE giveaway_id=?', (gid,))
            entries = [row[0] for row in cursor2.fetchall()]
            cursor2.execute('UPDATE giveaway SET active=0 WHERE id=?', (gid,))
            conn2.commit()
            conn2.close()

            if entries:
                winner = random.choice(entries)
                bot.send_message(message.chat.id,
                    f"🎉 **GIVEAWAY ENDED!**\n\n"
                    f"🏆 Prize: **{prize}**\n"
                    f"👑 Winner: `{winner}`\n"
                    f"🎊 Congratulations! Contact admin to claim your prize.",
                    parse_mode="Markdown"
                )
            else:
                bot.send_message(message.chat.id, f"😔 Giveaway for **{prize}** ended with no entries.", parse_mode="Markdown")

        threading.Thread(target=end_giveaway, daemon=True).start()

    except ValueError:
        bot.reply_to(message, "❌ Minutes must be a number.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("giveaway_"))
def giveaway_join(call):
    gid = int(call.data.split("_")[1])
    user_id = call.from_user.id

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT active FROM giveaway WHERE id=?', (gid,))
    row = cursor.fetchone()

    if not row or row[0] == 0:
        bot.answer_callback_query(call.id, "❌ This giveaway has ended!", show_alert=True)
        conn.close()
        return

    try:
        cursor.execute('INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)', (gid, user_id))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ You've entered the giveaway! Good luck! 🍀", show_alert=True)
    except:
        bot.answer_callback_query(call.id, "⚠️ You already joined this giveaway!", show_alert=True)
    conn.close()

# ============================================================
# 📊 DAILY REPORT SYSTEM
# ============================================================

def send_daily_report():
    while True:
        now = datetime.now()
        # Send at 11:59 PM every day
        next_run = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        time.sleep((next_run - now).total_seconds())

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            today = datetime.now().date().isoformat()
            cursor.execute("SELECT COUNT(*) FROM user_activity WHERE timestamp LIKE ?", (f"{today}%",))
            daily_cmds = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE timestamp LIKE ?", (f"{today}%",))
            active_today = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(downloads) FROM files")
            total_dl = cursor.fetchone()[0] or 0
            conn.close()

            report = (
                f"📊 **Daily Report — {today}**\n\n"
                f"👥 Total Users: {len(all_chats)}\n"
                f"✅ Active Today: {active_today}\n"
                f"💬 Commands Used: {daily_cmds}\n"
                f"📥 Total Downloads: {total_dl}\n"
            )
            bot.send_message(MAIN_OWNER, report, parse_mode="Markdown")
        except Exception as e:
            print(f"Daily report error: {e}")

threading.Thread(target=send_daily_report, daemon=True).start()

# ============================================================
# ❓ QUIZ SYSTEM
# ============================================================

active_quiz = {}  # {chat_id: {question, answer, message_id}}

@bot.message_handler(commands=['quiz'])
def quiz_cmd(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/quiz [question] | [answer]`\nExample: `/quiz What is 2+2? | 4`", parse_mode="Markdown")
        return

    combined = " ".join(args[1:])
    if "|" not in combined:
        bot.reply_to(message, "❌ Separate question and answer with `|`\nExample: `/quiz Capital of BD? | Dhaka`", parse_mode="Markdown")
        return

    question, answer = combined.split("|", 1)
    question = question.strip()
    answer = answer.strip().lower()

    active_quiz[message.chat.id] = {"question": question, "answer": answer}

    msg = bot.send_message(message.chat.id,
        f"❓ **QUIZ TIME!**\n\n{question}\n\n✏️ Reply with your answer!",
        parse_mode="Markdown"
    )
    active_quiz[message.chat.id]["message_id"] = msg.message_id

@bot.message_handler(commands=['endquiz'])
def end_quiz(message):
    if not is_admin(message.chat.id):
        return
    if message.chat.id in active_quiz:
        del active_quiz[message.chat.id]
        bot.reply_to(message, "✅ Quiz ended.")
    else:
        bot.reply_to(message, "❌ No active quiz in this chat.")

# ============================================================
# 📈 USER GROWTH / FILE POPULARITY COMMANDS
# ============================================================

@bot.message_handler(commands=['growth'])
def user_growth(message):
    if not is_admin(message.chat.id):
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Count new users per day (last 7 days)
    cursor.execute("""
        SELECT DATE(timestamp) as day, COUNT(DISTINCT user_id) as cnt
        FROM user_activity
        WHERE timestamp >= date('now', '-7 days')
        GROUP BY day ORDER BY day
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, "📭 Not enough data yet.")
        return

    msg = "📈 **User Activity (Last 7 Days):**\n\n"
    for day, cnt in rows:
        bar = "█" * min(cnt, 20)
        msg += f"`{day}` {bar} {cnt}\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['popular'])
def popular_files(message):
    if not is_admin(message.chat.id):
        return
    files = get_all_files()
    if not files:
        bot.reply_to(message, "📭 No files found.")
        return
    sorted_files = sorted(files, key=lambda x: x[3], reverse=True)[:5]
    msg = "🔥 **Most Popular Files:**\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, (key, f_type, caption, downloads) in enumerate(sorted_files):
        bot._user = bot.get_me()
        link = f"https://t.me/{bot.get_me().username}?start={key}"
        msg += f"{medals[i]} `{key}` — {downloads} downloads\n   📝 {caption[:30] if caption else 'No caption'}\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# ============================================================
# 🤖 MAINTENANCE MODE
# ============================================================

@bot.message_handler(commands=['maintenance'])
def maintenance_mode(message):
    if message.chat.id != MAIN_OWNER:
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/maintenance [on/off]`", parse_mode="Markdown")
        return
    set_setting("maintenance", args[1])
    bot.reply_to(message, f"🔧 Maintenance mode turned {args[1]}")

# ============================================================
# 👤 MY STATS (for regular users)
# ============================================================

@bot.message_handler(commands=['mystats'])
def my_stats(message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_activity WHERE user_id=?', (user_id,))
    cmd_count = cursor.fetchone()[0]
    conn.close()

    ref_count = get_referral_count(user_id)
    warn_count, _ = get_warnings(user_id)
    banned = "Yes 🚫" if is_banned(user_id) else "No ✅"

    msg = (
        f"📊 **Your Stats:**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"💬 Commands Used: {cmd_count}\n"
        f"👥 Referrals: {ref_count}\n"
        f"⚠️ Warnings: {warn_count}/5\n"
        f"🚫 Banned: {banned}\n\n"
        f"Use /refer to get your referral link!"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

# ============================================================
# 🔗 DEEPLINK GENERATOR (quick command for admin)
# ============================================================

@bot.message_handler(commands=['link'])
def quick_link(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/link [file_key]`", parse_mode="Markdown")
        return
    key = args[1]
    bot_user = bot.get_me().username
    link = f"https://t.me/{bot_user}?start={key}"
    bot.reply_to(message, f"🔗 **Deeplink:**\n`{link}`", parse_mode="Markdown")

# ============================================================
# ⚡ ANTI-SPAM ENGINE (actual logic)
# ============================================================

def is_spamming(user_id):
    now = time.time()
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t < 5]
    spam_tracker[user_id].append(now)
    return len(spam_tracker[user_id]) > 5  # 5 msgs in 5 sec = spam

def is_muted(user_id):
    if user_id in muted_users:
        if time.time() < muted_users[user_id]:
            return True
        else:
            del muted_users[user_id]
    return False

# ============================================================
# 🤖 CHATGPT AI REPLY
# ============================================================

def ask_openai(prompt):
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        }
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=15)
        result = res.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ AI error: {str(e)}"

@bot.message_handler(commands=['ai'])
def ai_reply(message):
    if is_banned(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/ai [তোমার প্রশ্ন]`\nExample: `/ai Python কি?`", parse_mode="Markdown")
        return
    thinking = bot.reply_to(message, "🤔 চিন্তা করছি...")
    answer = ask_openai(args[1])
    bot.edit_message_text(f"🤖 **AI উত্তর:**\n\n{answer}", message.chat.id, thinking.message_id, parse_mode="Markdown")
    log_activity(message.from_user.id, "/ai")

@bot.message_handler(commands=['caption'])
def ai_caption(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/caption [file নাম বা বিষয়]`", parse_mode="Markdown")
        return
    thinking = bot.reply_to(message, "✍️ Caption তৈরি হচ্ছে...")
    prompt = f"একটি Telegram file store bot এর জন্য এই file এর আকর্ষণীয় বাংলা caption লেখো (২-৩ লাইন): {args[1]}"
    caption = ask_openai(prompt)
    bot.edit_message_text(f"📝 **Generated Caption:**\n\n{caption}", message.chat.id, thinking.message_id, parse_mode="Markdown")

# ============================================================
# 🔗 SHORTLINK SYSTEM (Exe.io)
# ============================================================

def shorten_link(url):
    try:
        api_url = f"https://{EXEIO_DOMAIN}/api?api={EXEIO_API_KEY}&url={url}"
        res = requests.get(api_url, timeout=10)
        data = res.json()
        if data.get("status") == "success":
            return data.get("shortenedUrl", url)
        return url
    except:
        return url

@bot.message_handler(commands=['shortlink'])
def shortlink_cmd(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/shortlink [url]`", parse_mode="Markdown")
        return
    msg = bot.reply_to(message, "🔗 Link ছোট করা হচ্ছে...")
    short = shorten_link(args[1])
    bot.edit_message_text(f"✅ **Shortened Link:**\n`{short}`", message.chat.id, msg.message_id, parse_mode="Markdown")

@bot.message_handler(commands=['setshortlink'])
def set_shortlink(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "❌ Usage: `/setshortlink [on/off]`\n\nYes এ থাকলে file link automatically শোর্ট হবে।", parse_mode="Markdown")
        return
    set_setting("shortlink", args[1])
    bot.reply_to(message, f"🔗 Shortlink system turned {args[1]}")

# ============================================================
# 💰 COIN / POINT SYSTEM
# ============================================================

def get_coins(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM coins WHERE user_id=?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def add_coins(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?',
                   (user_id, amount, amount))
    conn.commit()
    conn.close()

def deduct_coins(user_id, amount):
    current = get_coins(user_id)
    if current < amount:
        return False
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE coins SET balance = balance - ? WHERE user_id=?', (amount, user_id))
    conn.commit()
    conn.close()
    return True

@bot.message_handler(commands=['coins'])
def coins_cmd(message):
    user_id = message.from_user.id
    balance = get_coins(user_id)
    bot.reply_to(message, f"💰 **তোমার Coin Balance:** {balance} 🪙\n\n"
                          f"📥 File download করলে: +2 coins\n"
                          f"👥 Referral করলে: +10 coins\n"
                          f"❓ Quiz জিতলে: +5 coins",
                 parse_mode="Markdown")

@bot.message_handler(commands=['addcoins'])
def add_coins_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "❌ Usage: `/addcoins [user_id] [amount]`", parse_mode="Markdown")
        return
    try:
        uid = int(parts[1])
        amount = int(parts[2])
        add_coins(uid, amount)
        bot.reply_to(message, f"✅ `{uid}` কে {amount} coins দেওয়া হয়েছে।", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid input.")

@bot.message_handler(commands=['topcoins'])
def top_coins(message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, balance FROM coins ORDER BY balance DESC LIMIT 10')
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "📭 কোনো coin data নেই।")
        return
    msg = "🏆 **Top Coin Holders:**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, bal) in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        msg += f"{m} `{uid}` — {bal} 🪙\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# ============================================================
# 📁 FILE CATEGORIES
# ============================================================

def set_file_category(file_key, category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO file_categories (file_key, category) VALUES (?, ?)', (file_key, category.lower()))
    conn.commit()
    conn.close()

def get_file_category(file_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT category FROM file_categories WHERE file_key=?', (file_key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "general"

def get_files_by_category(category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''SELECT f.key, f.type, f.caption, f.downloads
                      FROM files f JOIN file_categories fc ON f.key = fc.file_key
                      WHERE fc.category=?''', (category.lower(),))
    rows = cursor.fetchall()
    conn.close()
    return rows

@bot.message_handler(commands=['setcategory'])
def set_category_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "❌ Usage: `/setcategory [file_key] [category]`\n\nCategories: movie, software, book, music, game, other", parse_mode="Markdown")
        return
    set_file_category(parts[1], parts[2])
    bot.reply_to(message, f"✅ `{parts[1]}` কে **{parts[2]}** category তে রাখা হয়েছে।", parse_mode="Markdown")

@bot.message_handler(commands=['browse'])
def browse_category(message):
    parts = message.text.split()
    if len(parts) < 2:
        markup = types.InlineKeyboardMarkup(row_width=2)
        cats = [("🎬 Movie", "movie"), ("💻 Software", "software"),
                ("📚 Book", "book"), ("🎵 Music", "music"),
                ("🎮 Game", "game"), ("📦 Other", "other")]
        for name, cat in cats:
            markup.add(types.InlineKeyboardButton(name, callback_data=f"browse_{cat}"))
        bot.reply_to(message, "📁 **Category বেছে নাও:**", reply_markup=markup, parse_mode="Markdown")
        return

    category = parts[1].lower()
    files = get_files_by_category(category)
    if not files:
        bot.reply_to(message, f"📭 **{category}** category তে কোনো file নেই।")
        return
    bot_user = bot.get_me().username
    msg = f"📁 **{category.title()} Files:**\n\n"
    for key, f_type, caption, downloads in files[:15]:
        link = f"https://t.me/{bot_user}?start={key}"
        msg += f"🔹 {caption[:30] if caption else key}\n   📥 {downloads} downloads | [Link]({link})\n\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown", disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("browse_"))
def browse_callback(call):
    category = call.data.replace("browse_", "")
    files = get_files_by_category(category)
    bot_user = bot.get_me().username
    if not files:
        bot.answer_callback_query(call.id, f"📭 {category} category তে কোনো file নেই!", show_alert=True)
        return
    msg = f"📁 **{category.title()} Files:**\n\n"
    for key, f_type, caption, downloads in files[:15]:
        link = f"https://t.me/{bot_user}?start={key}"
        msg += f"🔹 {caption[:30] if caption else key}\n   📥 {downloads} | [Link]({link})\n\n"
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", disable_web_page_preview=True)
    bot.answer_callback_query(call.id)

# ============================================================
# 🔖 BOOKMARK SYSTEM
# ============================================================

def add_bookmark(user_id, file_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO bookmarks (user_id, file_key, added_at) VALUES (?, ?, ?)',
                       (user_id, file_key, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def get_bookmarks(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_key, added_at FROM bookmarks WHERE user_id=? ORDER BY added_at DESC', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def remove_bookmark(user_id, file_key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bookmarks WHERE user_id=? AND file_key=?', (user_id, file_key))
    conn.commit()
    conn.close()

@bot.message_handler(commands=['bookmark'])
def bookmark_cmd(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/bookmark [file_key]`", parse_mode="Markdown")
        return
    user_id = message.from_user.id
    key = parts[1]
    if not get_file_from_db(key):
        bot.reply_to(message, "❌ এই key দিয়ে কোনো file পাওয়া যায়নি।")
        return
    if add_bookmark(user_id, key):
        bot.reply_to(message, f"🔖 File bookmark করা হয়েছে!\nদেখতে: /mybookmarks")
    else:
        bot.reply_to(message, "⚠️ এটা আগেই bookmark করা আছে!")

@bot.message_handler(commands=['mybookmarks'])
def my_bookmarks(message):
    user_id = message.from_user.id
    bookmarks = get_bookmarks(user_id)
    if not bookmarks:
        bot.reply_to(message, "📭 তোমার কোনো bookmark নেই।\nFile bookmark করতে: `/bookmark [key]`", parse_mode="Markdown")
        return
    bot_user = bot.get_me().username
    msg = "🔖 **তোমার Bookmarks:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, added_at in bookmarks[:10]:
        f_data = get_file_from_db(key)
        caption = f_data[2] if f_data and f_data[2] else key
        link = f"https://t.me/{bot_user}?start={key}"
        msg += f"🔹 [{caption[:30]}]({link})\n"
        markup.add(types.InlineKeyboardButton(f"❌ Remove: {caption[:20]}", callback_data=f"rmbm_{key}"))
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rmbm_"))
def remove_bookmark_cb(call):
    key = call.data.replace("rmbm_", "")
    remove_bookmark(call.from_user.id, key)
    bot.answer_callback_query(call.id, "✅ Bookmark সরানো হয়েছে!")
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ============================================================
# 📬 FILE REQUEST SYSTEM
# ============================================================

def add_file_request(user_id, request_text):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO file_requests (user_id, request_text, status, requested_at) VALUES (?, ?, "pending", ?)',
                   (user_id, request_text, datetime.now().isoformat()))
    rid = cursor.lastrowid
    conn.commit()
    conn.close()
    return rid

def get_pending_requests():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_id, request_text, requested_at FROM file_requests WHERE status="pending" ORDER BY requested_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_request_status(rid, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE file_requests SET status=? WHERE id=?', (status, rid))
    conn.commit()
    conn.close()

@bot.message_handler(commands=['request'])
def file_request_cmd(message):
    if is_banned(message.from_user.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: `/request [কোন file চাও]`\nExample: `/request Avengers Endgame Movie`", parse_mode="Markdown")
        return
    user_id = message.from_user.id
    rid = add_file_request(user_id, args[1])
    bot.reply_to(message, f"✅ **তোমার request পাঠানো হয়েছে!**\n\n📝 Request: {args[1]}\n🆔 ID: #{rid}\n\nAdmin দেখলে জানাবে!", parse_mode="Markdown")
    # Notify admin
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Done", callback_data=f"req_done_{rid}_{user_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"req_reject_{rid}_{user_id}")
    )
    try:
        bot.send_message(MAIN_OWNER,
            f"📬 **নতুন File Request!**\n\n"
            f"👤 User: `{user_id}`\n"
            f"📝 Request: {args[1]}\n"
            f"🆔 ID: #{rid}",
            reply_markup=markup, parse_mode="Markdown"
        )
    except:
        pass

@bot.message_handler(commands=['requests'])
def list_requests(message):
    if not is_admin(message.chat.id):
        return
    requests_list = get_pending_requests()
    if not requests_list:
        bot.reply_to(message, "📭 কোনো pending request নেই।")
        return
    msg = f"📬 **Pending File Requests ({len(requests_list)}):**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)
    for rid, uid, req_text, req_at in requests_list[:10]:
        msg += f"#{rid} | `{uid}` | {req_text[:40]}\n"
        markup.add(
            types.InlineKeyboardButton(f"✅ #{rid}", callback_data=f"req_done_{rid}_{uid}"),
            types.InlineKeyboardButton(f"❌ #{rid}", callback_data=f"req_reject_{rid}_{uid}")
        )
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("req_"))
def request_callback(call):
    parts = call.data.split("_")
    action = parts[1]
    rid = int(parts[2])
    uid = int(parts[3])

    if action == "done":
        update_request_status(rid, "done")
        bot.answer_callback_query(call.id, "✅ Done করা হয়েছে!")
        try:
            bot.send_message(uid, f"✅ তোমার request #{rid} পূরণ করা হয়েছে! Bot চেক করো।")
        except:
            pass
    elif action == "reject":
        update_request_status(rid, "rejected")
        bot.answer_callback_query(call.id, "❌ Reject করা হয়েছে!")
        try:
            bot.send_message(uid, f"❌ দুঃখিত, তোমার request #{rid} এখন পূরণ করা সম্ভব হচ্ছে না।")
        except:
            pass
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ============================================================
# 🔔 SUBSCRIBER / NEW FILE ALERT
# ============================================================

def subscribe_category(user_id, category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO subscribers (user_id, category) VALUES (?, ?)', (user_id, category))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def unsubscribe_category(user_id, category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscribers WHERE user_id=? AND category=?', (user_id, category))
    conn.commit()
    conn.close()

def get_subscribers(category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM subscribers WHERE category=? OR category="all"', (category,))
    rows = [r[0] for r in cursor.fetchall()]
    conn.close()
    return rows

def notify_subscribers(category, file_key, caption):
    subs = get_subscribers(category)
    bot_user = bot.get_me().username
    link = f"https://t.me/{bot_user}?start={file_key}"
    msg = f"🔔 **নতুন {category.title()} File!**\n\n📝 {caption}\n\n[👉 Download করো]({link})"
    for uid in subs:
        try:
            bot.send_message(uid, msg, parse_mode="Markdown", disable_web_page_preview=True)
            time.sleep(0.1)
        except:
            pass

@bot.message_handler(commands=['subscribe'])
def subscribe_cmd(message):
    if is_banned(message.from_user.id):
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    cats = [("🎬 Movie", "movie"), ("💻 Software", "software"),
            ("📚 Book", "book"), ("🎵 Music", "music"),
            ("🎮 Game", "game"), ("📦 All Files", "all")]
    for name, cat in cats:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"sub_{cat}"))
    bot.reply_to(message, "🔔 **কোন category তে alert চাও?**", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_cmd(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/unsubscribe [category/all]`", parse_mode="Markdown")
        return
    unsubscribe_category(message.from_user.id, parts[1])
    bot.reply_to(message, f"✅ **{parts[1]}** থেকে unsubscribe করা হয়েছে।", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
def subscribe_callback(call):
    category = call.data.replace("sub_", "")
    if subscribe_category(call.from_user.id, category):
        bot.answer_callback_query(call.id, f"✅ {category} তে subscribe করা হয়েছে!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "⚠️ আগেই subscribe করা আছে!", show_alert=True)

# ============================================================
# ⏰ REMINDER SYSTEM
# ============================================================

def add_reminder(user_id, remind_at, message_text):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO reminders (user_id, remind_at, message) VALUES (?, ?, ?)',
                   (user_id, remind_at, message_text))
    rid = cursor.lastrowid
    conn.commit()
    conn.close()
    return rid

def check_reminders():
    while True:
        time.sleep(30)
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('SELECT id, user_id, message FROM reminders WHERE remind_at <= ? AND sent=0', (now,))
            rows = cursor.fetchall()
            for rid, uid, msg in rows:
                try:
                    bot.send_message(uid, f"⏰ **Reminder!**\n\n{msg}", parse_mode="Markdown")
                    cursor.execute('UPDATE reminders SET sent=1 WHERE id=?', (rid,))
                except:
                    pass
            conn.commit()
            conn.close()
        except:
            pass

threading.Thread(target=check_reminders, daemon=True).start()

@bot.message_handler(commands=['remind'])
def remind_cmd(message):
    if is_banned(message.from_user.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "❌ Usage: `/remind [HH:MM] [message]`\nExample: `/remind 18:30 নামাজ পড়তে হবে`", parse_mode="Markdown")
        return
    try:
        time_str = args[1]
        msg_text = args[2]
        target = datetime.strptime(time_str, "%H:%M")
        now = datetime.now()
        remind_dt = now.replace(hour=target.hour, minute=target.minute, second=0)
        if remind_dt < now:
            remind_dt += timedelta(days=1)
        rid = add_reminder(message.from_user.id, remind_dt.isoformat(), msg_text)
        bot.reply_to(message, f"✅ **Reminder set!**\n\n⏰ সময়: {time_str}\n📝 Message: {msg_text}\n🆔 ID: #{rid}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid time format. Use HH:MM (24-hour)")

# ============================================================
# 💳 DONATION / BKASH BUTTON
# ============================================================

@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 bKash এ Donate করো", url=f"https://bkash.com/send-money?number={BKASH_NUMBER}"))
    bot.reply_to(message,
        f"💙 **Donate করুন!**\n\n"
        f"এই bot টি free রাখতে আপনার সাহায্য দরকার।\n\n"
        f"📱 **bKash:** `{BKASH_NUMBER}`\n\n"
        f"যেকোনো পরিমাণ পাঠাতে পারেন। ধন্যবাদ! 🙏",
        reply_markup=markup, parse_mode="Markdown"
    )

# ============================================================
# 📊 DOWNLOAD REPORT (কে কি download করেছে)
# ============================================================

@bot.message_handler(commands=['downloadreport'])
def download_report(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/downloadreport [file_key]`", parse_mode="Markdown")
        return
    key = parts[1]
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, timestamp FROM user_activity WHERE command=? ORDER BY timestamp DESC LIMIT 20',
                   (f"download_{key}",))
    rows = cursor.fetchall()
    conn.close()

    f_data = get_file_from_db(key)
    caption = f_data[2] if f_data else key

    if not rows:
        bot.reply_to(message, f"📭 **{caption}** — কেউ এখনো download করেনি।")
        return

    msg = f"📊 **Download Report: {caption[:30]}**\n\n"
    for uid, ts in rows:
        msg += f"👤 `{uid}` — {ts[:16]}\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# ============================================================
# 📈 RETENTION ANALYTICS
# ============================================================

@bot.message_handler(commands=['retention'])
def retention_cmd(message):
    if not is_admin(message.chat.id):
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Users active in last 7 days
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE timestamp >= ?', (week_ago,))
    active_7 = cursor.fetchone()[0]
    # Users active in last 30 days
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE timestamp >= ?', (month_ago,))
    active_30 = cursor.fetchone()[0]
    # Total users
    total = len(all_chats)
    retention_7 = round((active_7 / total * 100), 1) if total else 0
    retention_30 = round((active_30 / total * 100), 1) if total else 0
    conn.close()

    msg = (
        f"📈 **Retention Analytics:**\n\n"
        f"👥 Total Users: {total}\n\n"
        f"📅 Last 7 days:\n"
        f"   Active: {active_7} ({retention_7}%)\n\n"
        f"📅 Last 30 days:\n"
        f"   Active: {active_30} ({retention_30}%)\n\n"
        f"💡 Retention = কতজন user আবার ফিরে আসছে"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# ============================================================
# 🔍 INLINE MODE
# ============================================================

@bot.inline_handler(func=lambda query: True)
def inline_search(query):
    if not query.query:
        return
    search_term = query.query.lower()
    files = get_all_files()
    results = []
    bot_user = bot.get_me().username

    matched = [f for f in files if search_term in (f[2] or "").lower() or search_term in f[0].lower()][:10]

    for key, f_type, caption, downloads in matched:
        link = f"https://t.me/{bot_user}?start={key}"
        results.append(types.InlineQueryResultArticle(
            id=key,
            title=caption[:50] if caption else key,
            description=f"📥 {downloads} downloads | {f_type}",
            input_message_content=types.InputTextMessageContent(
                message_text=f"📁 **{caption}**\n\n[👉 Download করো]({link})",
                parse_mode="Markdown"
            )
        ))

    if not results:
        results.append(types.InlineQueryResultArticle(
            id="no_result",
            title="❌ কিছু পাওয়া যায়নি",
            description="অন্য keyword দিয়ে চেষ্টা করো",
            input_message_content=types.InputTextMessageContent(message_text="❌ কোনো file পাওয়া যায়নি।")
        ))

    bot.answer_inline_query(query.id, results, cache_time=10)

# ============================================================
# Update finalize_data to notify subscribers & give coins
# ============================================================

def finalize_data(message, file_id, f_type):
    caption = message.text if f_type != 'text' else ""
    key = f"file_{int(time.time())}"
    save_file_to_db(key, file_id, f_type, caption)
    bot_user = bot.get_me().username

    # Shortlink if enabled
    raw_link = f"https://t.me/{bot_user}?start={key}"
    if get_setting("shortlink", "off") == "on":
        final_link = shorten_link(raw_link)
    else:
        final_link = raw_link

    bot.send_message(message.chat.id,
        f"✅ **Link Created!**\n\n`{final_link}`\n\n**Key:** `{key}`\n\n"
        f"📁 Category set করতে: `/setcategory {key} movie`\n"
        f"🔔 Subscribers notify করতে: `/notify {key}`",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['notify'])
def notify_cmd(message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: `/notify [file_key]`", parse_mode="Markdown")
        return
    key = parts[1]
    f_data = get_file_from_db(key)
    if not f_data:
        bot.reply_to(message, "❌ File পাওয়া যায়নি।")
        return
    caption = f_data[2] or key
    category = get_file_category(key)
    msg = bot.reply_to(message, f"📢 Subscribers কে notify করা হচ্ছে...")
    threading.Thread(target=notify_subscribers, args=(category, key, caption), daemon=True).start()
    bot.edit_message_text("✅ Notification পাঠানো হচ্ছে!", message.chat.id, msg.message_id)

# ============================================================
# Update check_callback to give coins on download
# ============================================================

# --- START BOT ---
if __name__ == "__main__":
    print("🤖 Bot Started! Press Ctrl+C to stop.")
    print(f"📊 Bot Username: @{bot.get_me().username}")
    print(f"👑 Owner ID: {MAIN_OWNER}")
    bot.infinity_polling(timeout=10)