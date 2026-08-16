# -*- coding: utf-8 -*-
"""
Kai រកលុយ — Referral Bot
- ណែនាំមិត្ត 1 នាក់ = $0.20
- ដកលុយអប្បបរមា = $2.50
- តម្រូវឲ្យចូល Channel មុននឹងទទួលបានប្រាក់ណែនាំ (Force-Subscribe)
- អត្តសញ្ញាណ user កំណត់ដោយ Telegram user ID ប៉ុណ្ណោះ (មិនតម្រូវលេខទូរស័ព្ទ)
- Grace-period watchdog: ប្រាក់ណែនាំក្លាយជាស្ថាពរលុះត្រាតែអ្នកត្រូវបានណែនាំនៅតែក្នុង Channel
- មាន Admin Panel ពេញលេញ
Stack: pyTelegramBotAPI + Flask keep-alive + JSON persistence (DATA_DIR) — same pattern
used across Kairozen bots, ready for Render deployment.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime

import telebot
from telebot import types
from flask import Flask

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = set(
    int(x) for x in os.environ.get("ADMIN_IDS", "8266854899").split(",") if x.strip()
)

BOT_DISPLAY_NAME = os.environ.get("BOT_DISPLAY_NAME", "Kai រកលុយ")

REFERRAL_BONUS = float(os.environ.get("REFERRAL_BONUS", "0.20"))
MIN_WITHDRAW = float(os.environ.get("MIN_WITHDRAW", "2.50"))
REFERRAL_GRACE_HOURS = float(os.environ.get("REFERRAL_GRACE_HOURS", "24"))
WATCHDOG_INTERVAL_MINUTES = float(os.environ.get("WATCHDOG_INTERVAL_MINUTES", "60"))

DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
WITHDRAW_FILE = os.path.join(DATA_DIR, "withdrawals.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
REFERRAL_LOG_FILE = os.path.join(DATA_DIR, "referral_log.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("kairozen-referral")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# in-memory conversation state: {user_id: {"step": "...", ...}}
STATE = {}

# ------------------------------------------------------------------
# STORAGE HELPERS
# ------------------------------------------------------------------
_lock = threading.Lock()


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log.exception("Failed loading %s", path)
        return default


def _save(path, data):
    with _lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def load_users():
    return _load(USERS_FILE, {})


def save_users(d):
    _save(USERS_FILE, d)


def load_withdrawals():
    return _load(WITHDRAW_FILE, [])


def save_withdrawals(d):
    _save(WITHDRAW_FILE, d)


def load_settings():
    return _load(SETTINGS_FILE, {"channel": os.environ.get("CHANNEL_USERNAME", "")})


def save_settings(d):
    _save(SETTINGS_FILE, d)


def load_referral_log():
    return _load(REFERRAL_LOG_FILE, [])


def log_referral_event(event):
    logs = load_referral_log()
    event["ts"] = datetime.utcnow().isoformat()
    logs.append(event)
    _save(REFERRAL_LOG_FILE, logs)


def get_user(user_id, username=None, first_name=None):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "id": user_id,
            "username": username or "",
            "first_name": first_name or "",
            "balance": 0.0,
            "referred_by": None,
            "referral_count": 0,
            "joined_channel": False,
            "pending_referrer": None,
            "referral_credited_at": None,
            "referral_verified": False,
            "referral_reverted": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        save_users(users)
    else:
        # keep username fresh
        changed = False
        if username and users[uid].get("username") != username:
            users[uid]["username"] = username
            changed = True
        if first_name and users[uid].get("first_name") != first_name:
            users[uid]["first_name"] = first_name
            changed = True
        if changed:
            save_users(users)
    return users[uid]


def update_user(user_id, **kwargs):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        get_user(user_id)
        users = load_users()
    users[uid].update(kwargs)
    save_users(users)
    return users[uid]


def is_admin(user_id):
    return user_id in ADMIN_IDS


# ------------------------------------------------------------------
# CHANNEL MEMBERSHIP CHECK
# ------------------------------------------------------------------
def get_channel():
    return load_settings().get("channel", "").strip()


def is_member_of_channel(user_id):
    channel = get_channel()
    if not channel:
        # no channel configured -> treat as passed (avoid locking everyone out)
        return True
    try:
        member = bot.get_chat_member(channel, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        log.warning("Membership check failed for %s in %s: %s", user_id, channel, e)
        return False


def join_channel_markup():
    channel = get_channel()
    kb = types.InlineKeyboardMarkup()
    if channel:
        link = channel if channel.startswith("http") else f"https://t.me/{channel.lstrip('@')}"
        kb.add(types.InlineKeyboardButton("📢 ចូល Channel", url=link))
    kb.add(types.InlineKeyboardButton("✅ ខ្ញុំបានចូលរួចហើយ", callback_data="check_join"))
    return kb


# ------------------------------------------------------------------
# MAIN MENU
# ------------------------------------------------------------------
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("💰 សមតុល្យ", "🔗 លីងណែនាំ")
    kb.row("💵 ដកលុយ", "🏆 អ្នកណែនាំកំពូល")
    kb.row("ℹ️ ជំនួយ")
    return kb


def referral_link(user_id):
    me = bot.get_me()
    return f"https://t.me/{me.username}?start=ref{user_id}"


def finalize_referral(user_id):
    """Credit the referrer once the referred user has joined the channel.
    Idempotent & fraud-guarded (self-referral blocked, credited once per user).
    The bonus starts in a grace period — see referral_watchdog() — and is only
    made permanent if the referred user is STILL in the channel after
    REFERRAL_GRACE_HOURS. This stops the "join → get friend paid → leave"
    exploit. Identity is tracked purely by Telegram user ID (no phone
    number required)."""
    user = get_user(user_id)
    if not user.get("joined_channel"):
        return
    if user.get("referred_by") is not None:
        return
    ref_id = user.get("pending_referrer")
    if not ref_id or ref_id == user_id:
        return
    referrer = get_user(ref_id)
    new_balance = round(referrer["balance"] + REFERRAL_BONUS, 2)
    update_user(ref_id, balance=new_balance, referral_count=referrer.get("referral_count", 0) + 1)
    update_user(
        user_id,
        referred_by=ref_id,
        pending_referrer=None,
        referral_credited_at=datetime.utcnow().isoformat(),
        referral_verified=False,
        referral_reverted=False,
    )
    log_referral_event(
        {"type": "credit_pending", "referrer": ref_id, "referred": user_id, "amount": REFERRAL_BONUS}
    )
    try:
        bot.send_message(
            ref_id,
            f"🎉 អ្នកទទួលបានប្រាក់ណែនាំថ្មី <b>${REFERRAL_BONUS:.2f}</b>!\n"
            f"💰 សមតុល្យថ្មី: <b>${new_balance:.2f}</b>\n\n"
            f"⏳ ចំណាំ៖ ប្រាក់នេះនឹងក្លាយជាស្ថាពរបន្ទាប់ពី {int(REFERRAL_GRACE_HOURS)} ម៉ោង "
            "ប្រសិនបើមិត្តភ័ក្តិដែលអ្នកបានណែនាំនៅតែស្ថិតនៅក្នុង Channel។",
        )
    except Exception:
        pass


def referral_watchdog():
    """Background loop: after the grace period, re-checks that each referred
    user is still a channel member. Still there -> confirm bonus permanently.
    Left the channel -> claw back the bonus from the referrer."""
    while True:
        try:
            users = load_users()
            now = datetime.utcnow()
            for uid, u in list(users.items()):
                if u.get("referral_verified") or u.get("referral_reverted"):
                    continue
                credited_at = u.get("referral_credited_at")
                ref_id = u.get("referred_by")
                if not credited_at or not ref_id:
                    continue
                try:
                    elapsed_hours = (now - datetime.fromisoformat(credited_at)).total_seconds() / 3600
                except ValueError:
                    continue
                if elapsed_hours < REFERRAL_GRACE_HOURS:
                    continue

                still_member = is_member_of_channel(int(uid))
                if still_member:
                    update_user(int(uid), referral_verified=True)
                    log_referral_event({"type": "credit_confirmed", "referrer": ref_id, "referred": int(uid)})
                else:
                    referrer = get_user(ref_id)
                    reverted_balance = max(0.0, round(referrer["balance"] - REFERRAL_BONUS, 2))
                    update_user(
                        ref_id,
                        balance=reverted_balance,
                        referral_count=max(0, referrer.get("referral_count", 0) - 1),
                    )
                    update_user(int(uid), referral_verified=True, referral_reverted=True)
                    log_referral_event(
                        {"type": "credit_reverted", "referrer": ref_id, "referred": int(uid), "amount": REFERRAL_BONUS}
                    )
                    try:
                        bot.send_message(
                            ref_id,
                            f"⚠️ ប្រាក់ណែនាំ <b>${REFERRAL_BONUS:.2f}</b> ត្រូវបានដកចេញវិញ ព្រោះមិត្តភ័ក្តិដែលអ្នកបានណែនាំបានចាកចេញពី Channel។\n"
                            f"💰 សមតុល្យថ្មី: <b>${reverted_balance:.2f}</b>",
                        )
                    except Exception:
                        pass
        except Exception:
            log.exception("referral_watchdog iteration failed")
        time.sleep(WATCHDOG_INTERVAL_MINUTES * 60)


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------
@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    user = get_user(user_id, username, first_name)

    # parse referral payload: /start ref123456
    args = message.text.split(maxsplit=1)
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            ref_id = int(args[1][3:])
        except ValueError:
            ref_id = None

    if ref_id and ref_id != user_id and user.get("referred_by") is None and user.get("pending_referrer") is None:
        # only set if this user has never been referred/credited before
        if str(ref_id) in load_users():
            update_user(user_id, pending_referrer=ref_id)
            user = get_user(user_id)

    if not user.get("joined_channel"):
        bot.send_message(
            message.chat.id,
            f"👋 សូមស្វាគមន៍មកកាន់ <b>{BOT_DISPLAY_NAME}</b>! 💸\n"
            "ណែនាំមិត្តភ័ក្តិ ទទួលបានប្រាក់ភ្លាមៗ ងាយៗ ស្រួលៗ!\n\n"
            f"💵 ណែនាំមិត្ត 1 នាក់ = <b>${REFERRAL_BONUS:.2f}</b>\n"
            f"💳 ដកលុយអប្បបរមា = <b>${MIN_WITHDRAW:.2f}</b>\n\n"
            "⚠️ សូមចូលរួម Channel ខាងក្រោមសិន ដើម្បីចាប់ផ្តើមប្រើប្រាស់ ហើយដើម្បីឲ្យអ្នកណែនាំទទួលបានប្រាក់៖",
            reply_markup=join_channel_markup(),
        )
        return

    bot.send_message(
        message.chat.id,
        f"👋 សួស្តី {first_name}! សូមស្វាគមន៍មកកាន់ <b>{BOT_DISPLAY_NAME}</b> 💰\n"
        "សូមប្រើម៉ឺនុយខាងក្រោម៖",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def cb_check_join(call):
    user_id = call.from_user.id
    if is_member_of_channel(user_id):
        update_user(user_id, joined_channel=True)
        finalize_referral(user_id)

        bot.answer_callback_query(call.id, "✅ អ្នកបានចូល Channel រួចហើយ!")
        bot.send_message(
            call.message.chat.id,
            f"✅ ជោគជ័យ! សូមស្វាគមន៍មកកាន់ <b>{BOT_DISPLAY_NAME}</b> សូមប្រើម៉ឺនុយខាងក្រោម៖",
            reply_markup=main_menu(),
        )
    else:
        bot.answer_callback_query(
            call.id, "❌ អ្នកមិនទាន់បានចូល Channel ទេ សូមចូលរួមសិន!", show_alert=True
        )


# ------------------------------------------------------------------
# GATE: block everything else until user has joined the channel
# ------------------------------------------------------------------
def require_joined(message):
    user = get_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    if is_admin(message.from_user.id):
        return True
    if not user.get("joined_channel"):
        bot.send_message(
            message.chat.id,
            "⚠️ សូមចូលរួម Channel មុនសិន៖",
            reply_markup=join_channel_markup(),
        )
        return False
    return True


# ------------------------------------------------------------------
# USER MENU HANDLERS
# ------------------------------------------------------------------
@bot.message_handler(func=lambda m: m.text == "💰 សមតុល្យ")
def handle_balance(message):
    if not require_joined(message):
        return
    user = get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"💰 សមតុល្យបច្ចុប្បន្ន: <b>${user['balance']:.2f}</b>\n"
        f"👥 ចំនួនអ្នកបានណែនាំ: <b>{user.get('referral_count', 0)}</b>",
    )


@bot.message_handler(func=lambda m: m.text == "🔗 លីងណែនាំ")
def handle_ref_link(message):
    if not require_joined(message):
        return
    link = referral_link(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "🔗 លីងណែនាំរបស់អ្នក៖\n"
        f"<code>{link}</code>\n\n"
        f"ចែករំលែកលីងនេះទៅមិត្តភ័ក្តិ! រាល់ការចុះឈ្មោះ + ចូល Channel = <b>${REFERRAL_BONUS:.2f}</b>",
    )


@bot.message_handler(func=lambda m: m.text == "🏆 អ្នកណែនាំកំពូល")
def handle_leaderboard(message):
    if not require_joined(message):
        return
    users = load_users()
    ranked = sorted(users.values(), key=lambda u: u.get("referral_count", 0), reverse=True)[:10]
    if not ranked or ranked[0].get("referral_count", 0) == 0:
        bot.send_message(message.chat.id, "🏆 មិនទាន់មានទិន្នន័យនៅឡើយទេ។")
        return
    lines = ["🏆 <b>អ្នកណែនាំកំពូល 10 នាក់</b>\n"]
    for i, u in enumerate(ranked, 1):
        if u.get("referral_count", 0) == 0:
            continue
        name = u.get("username") and f"@{u['username']}" or (u.get("first_name") or f"ID{u['id']}")
        lines.append(f"{i}. {name} — {u.get('referral_count', 0)} នាក់ (${u['balance']:.2f})")
    bot.send_message(message.chat.id, "\n".join(lines))


@bot.message_handler(func=lambda m: m.text == "ℹ️ ជំនួយ")
def handle_help(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>របៀបប្រើប្រាស់</b>\n\n"
        "1️⃣ ចែករំលែកលីងណែនាំរបស់អ្នក\n"
        "2️⃣ មិត្តភ័ក្តិចុចលីង ចូល Bot ហើយចូល Channel\n"
        f"3️⃣ អ្នកទទួលបាន <b>${REFERRAL_BONUS:.2f}</b> ភ្លាមៗ\n"
        f"4️⃣ នៅពេលសមតុល្យដល់ <b>${MIN_WITHDRAW:.2f}</b> អាចដកបាន\n\n"
        "មានបញ្ហា? ទាក់ទង Admin។",
    )


# ------------------------------------------------------------------
# WITHDRAW FLOW
# ------------------------------------------------------------------
@bot.message_handler(func=lambda m: m.text == "💵 ដកលុយ")
def handle_withdraw(message):
    if not require_joined(message):
        return
    user = get_user(message.from_user.id)
    if user["balance"] < MIN_WITHDRAW:
        bot.send_message(
            message.chat.id,
            f"❌ សមតុល្យរបស់អ្នកមិនទាន់គ្រប់ចំនួនអប្បបរមាទេ។\n"
            f"💰 សមតុល្យ: ${user['balance']:.2f} / ត្រូវការ ${MIN_WITHDRAW:.2f}",
        )
        return
    STATE[message.from_user.id] = {"step": "awaiting_withdraw_info"}
    bot.send_message(
        message.chat.id,
        f"💵 សមតុល្យអាចដកបាន: <b>${user['balance']:.2f}</b>\n\n"
        "សូមផ្ញើ <b>រូបភាព QR Code Bakong</b> របស់អ្នក (screenshot ពី App Bakong)\n"
        "ឬអាចវាយលេខ <b>Bakong / លេខទូរស័ព្ទ</b> ជាអក្សរជំនួសក៏បាន៖",
        reply_markup=types.ReplyKeyboardRemove(),
    )


def notify_admins_withdraw(w):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ អនុម័ត", callback_data=f"wapprove_{w['id']}"),
        types.InlineKeyboardButton("❌ បដិសេធ", callback_data=f"wreject_{w['id']}"),
    )
    caption = (
        "📥 <b>សំណើដកលុយថ្មី</b>\n\n"
        f"👤 User: {w['username'] or w['first_name']} (<code>{w['user_id']}</code>)\n"
        f"💵 ចំនួន: ${w['amount']:.2f}\n"
        f"📱 ព័ត៌មានទទួល: <code>{w.get('info') or '(មិនបានវាយអត្ថបទ សូមមើលរូបភាព QR)'}</code>\n"
        f"🆔 Request ID: <code>{w['id']}</code>"
    )
    photo_id = w.get("photo_id")
    for admin_id in ADMIN_IDS:
        try:
            if photo_id:
                bot.send_photo(admin_id, photo_id, caption=caption, reply_markup=kb)
            else:
                bot.send_message(admin_id, caption, reply_markup=kb)
        except Exception:
            pass


@bot.message_handler(
    func=lambda m: STATE.get(m.from_user.id, {}).get("step") == "awaiting_withdraw_info",
    content_types=["text", "photo"],
)
def handle_withdraw_info(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    amount = user["balance"]

    if amount < MIN_WITHDRAW:
        STATE.pop(user_id, None)
        bot.send_message(message.chat.id, "❌ សមតុល្យមិនគ្រប់ចំនួនទៀតទេ។", reply_markup=main_menu())
        return

    photo_id = None
    info = ""
    if message.content_type == "photo":
        photo_id = message.photo[-1].file_id
        info = (message.caption or "").strip()
    else:
        info = (message.text or "").strip()
        if not info:
            bot.send_message(message.chat.id, "❌ សូមផ្ញើរូបភាព QR ឬវាយលេខ Bakong/ទូរស័ព្ទ។")
            return

    # deduct immediately, refund on rejection
    update_user(user_id, balance=0.0)

    withdrawals = load_withdrawals()
    w = {
        "id": int(time.time() * 1000),
        "user_id": user_id,
        "username": user.get("username", ""),
        "first_name": user.get("first_name", ""),
        "amount": round(amount, 2),
        "info": info,
        "photo_id": photo_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    withdrawals.append(w)
    save_withdrawals(withdrawals)
    STATE.pop(user_id, None)

    bot.send_message(
        message.chat.id,
        f"✅ សំណើដកលុយ <b>${w['amount']:.2f}</b> ត្រូវបានផ្ញើទៅ Admin ។\n"
        "សូមរង់ចាំការអនុម័ត។",
        reply_markup=main_menu(),
    )
    notify_admins_withdraw(w)


@bot.callback_query_handler(func=lambda c: c.data.startswith("wapprove_") or c.data.startswith("wreject_"))
def cb_withdraw_decision(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ អ្នកមិនមែនជា Admin ទេ។", show_alert=True)
        return

    approve = call.data.startswith("wapprove_")
    wid = int(call.data.split("_", 1)[1])
    withdrawals = load_withdrawals()
    w = next((x for x in withdrawals if x["id"] == wid), None)
    if not w or w["status"] != "pending":
        bot.answer_callback_query(call.id, "⚠️ សំណើនេះត្រូវបានដោះស្រាយរួចហើយ។", show_alert=True)
        return

    if approve:
        w["status"] = "approved"
        try:
            bot.send_message(
                w["user_id"],
                f"✅ សំណើដកលុយ <b>${w['amount']:.2f}</b> របស់អ្នកត្រូវបានអនុម័ត និងបានផ្ញើប្រាក់ហើយ!",
            )
        except Exception:
            pass
    else:
        w["status"] = "rejected"
        # refund
        user = get_user(w["user_id"])
        update_user(w["user_id"], balance=round(user["balance"] + w["amount"], 2))
        try:
            bot.send_message(
                w["user_id"],
                f"❌ សំណើដកលុយ <b>${w['amount']:.2f}</b> របស់អ្នកត្រូវបានបដិសេធ។ ប្រាក់ត្រូវបានប្រគល់ត្រលប់ទៅសមតុល្យវិញ។",
            )
        except Exception:
            pass

    save_withdrawals(withdrawals)
    bot.edit_message_text(
        call.message.text + f"\n\n{'✅ អនុម័តរួច' if approve else '❌ បដិសេធរួច'} ដោយ Admin",
        call.message.chat.id,
        call.message.message_id,
    )
    bot.answer_callback_query(call.id, "✅ រួចរាល់")


# ------------------------------------------------------------------
# ADMIN PANEL
# ------------------------------------------------------------------
def admin_menu():
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📊 ស្ថិតិទូទៅ", callback_data="a_stats"))
    kb.row(types.InlineKeyboardButton("📋 សំណើដកលុយកំពុងរង់ចាំ", callback_data="a_pending"))
    kb.row(types.InlineKeyboardButton("📢 ផ្សព្វផ្សាយសារ", callback_data="a_broadcast"))
    kb.row(types.InlineKeyboardButton("⚙️ កំណត់ Channel", callback_data="a_setchannel"))
    kb.row(types.InlineKeyboardButton("💳 កែសមតុល្យ User", callback_data="a_addbalance"))
    kb.row(types.InlineKeyboardButton("↩️ ណែនាំដែលត្រូវបានដកវិញ", callback_data="a_flagged"))
    return kb


@bot.message_handler(commands=["admin"])
def handle_admin(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, f"🛠️ <b>{BOT_DISPLAY_NAME} — Admin Panel</b>", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("a_"))
def cb_admin_menu(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ គ្មានសិទ្ធិ", show_alert=True)
        return
    action = call.data

    if action == "a_stats":
        users = load_users()
        withdrawals = load_withdrawals()
        total_users = len(users)
        joined = sum(1 for u in users.values() if u.get("joined_channel"))
        pending_grace = sum(
            1 for u in users.values()
            if u.get("referred_by") and not u.get("referral_verified") and not u.get("referral_reverted")
        )
        reverted = sum(1 for u in users.values() if u.get("referral_reverted"))
        total_balance = sum(u.get("balance", 0.0) for u in users.values())
        total_paid = sum(w["amount"] for w in withdrawals if w["status"] == "approved")
        pending_count = sum(1 for w in withdrawals if w["status"] == "pending")
        bot.send_message(
            call.message.chat.id,
            "📊 <b>ស្ថិតិទូទៅ</b>\n\n"
            f"👥 សរុប Users: {total_users}\n"
            f"✅ បានចូល Channel: {joined}\n"
            f"⏳ ណែនាំកំពុងរង់ចាំផ្ទៀងផ្ទាត់ ({int(REFERRAL_GRACE_HOURS)}ម៉ោង): {pending_grace}\n"
            f"↩️ ប្រាក់ណែនាំត្រូវបានដកវិញ (ចាកចេញ Channel): {reverted}\n"
            f"💰 សមតុល្យសរុប (មិនទាន់ដក): ${total_balance:.2f}\n"
            f"💸 បានបង់ចេញសរុប: ${total_paid:.2f}\n"
            f"📋 សំណើកំពុងរង់ចាំ: {pending_count}",
        )

    elif action == "a_pending":
        withdrawals = [w for w in load_withdrawals() if w["status"] == "pending"]
        if not withdrawals:
            bot.send_message(call.message.chat.id, "📋 គ្មានសំណើដកលុយកំពុងរង់ចាំទេ។")
        else:
            for w in withdrawals:
                kb = types.InlineKeyboardMarkup()
                kb.row(
                    types.InlineKeyboardButton("✅ អនុម័ត", callback_data=f"wapprove_{w['id']}"),
                    types.InlineKeyboardButton("❌ បដិសេធ", callback_data=f"wreject_{w['id']}"),
                )
                caption = (
                    f"👤 {w['username'] or w['first_name']} (<code>{w['user_id']}</code>)\n"
                    f"💵 ${w['amount']:.2f}\n"
                    f"📱 <code>{w.get('info') or '(មើលរូបភាព QR ខាងលើ)'}</code>\n"
                    f"🆔 <code>{w['id']}</code>"
                )
                if w.get("photo_id"):
                    bot.send_photo(call.message.chat.id, w["photo_id"], caption=caption, reply_markup=kb)
                else:
                    bot.send_message(call.message.chat.id, caption, reply_markup=kb)

    elif action == "a_broadcast":
        STATE[call.from_user.id] = {"step": "awaiting_broadcast"}
        bot.send_message(call.message.chat.id, "📢 សូមផ្ញើសារដែលអ្នកចង់ផ្សព្វផ្សាយទៅ Users ទាំងអស់៖")

    elif action == "a_setchannel":
        STATE[call.from_user.id] = {"step": "awaiting_channel"}
        bot.send_message(
            call.message.chat.id,
            "⚙️ សូមផ្ញើ Channel username (ឧ. @kairozen_channel) ឬ Channel ID។\n"
            "⚠️ ត្រូវប្រាកដថា Bot ជា Admin នៅក្នុង Channel នោះ។",
        )

    elif action == "a_addbalance":
        STATE[call.from_user.id] = {"step": "awaiting_addbalance"}
        bot.send_message(
            call.message.chat.id,
            "💳 សូមផ្ញើតាមទម្រង់៖ <code>user_id ចំនួនទឹកប្រាក់</code>\n"
            "ឧទាហរណ៍៖ <code>8266854899 1.50</code> (អាចដាក់ចំនួនអវិជ្ជមានដើម្បីកាត់)",
        )

    elif action == "a_flagged":
        users = load_users()
        reverted = [u for u in users.values() if u.get("referral_reverted")]
        if not reverted:
            bot.send_message(call.message.chat.id, "↩️ គ្មានប្រាក់ណែនាំដែលត្រូវបានដកវិញទេ។")
        else:
            lines = ["↩️ <b>ណែនាំដែលត្រូវបានដកវិញ (ចាកចេញ Channel មុនផុត Grace Period)</b>\n"]
            for u in reverted:
                name = u.get("username") and f"@{u['username']}" or (u.get("first_name") or "")
                lines.append(f"• {name} — ID: <code>{u['id']}</code> — Referrer: <code>{u.get('referred_by')}</code>")
            bot.send_message(call.message.chat.id, "\n".join(lines))

    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: STATE.get(m.from_user.id, {}).get("step") == "awaiting_broadcast")
def handle_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    STATE.pop(message.from_user.id, None)
    users = load_users()
    sent, failed = 0, 0
    for uid in users:
        try:
            bot.copy_message(int(uid), message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
    bot.send_message(message.chat.id, f"📢 ផ្សព្វផ្សាយចប់! ជោគជ័យ: {sent} | បរាជ័យ: {failed}")


@bot.message_handler(func=lambda m: STATE.get(m.from_user.id, {}).get("step") == "awaiting_channel")
def handle_setchannel(message):
    if not is_admin(message.from_user.id):
        return
    STATE.pop(message.from_user.id, None)
    channel = message.text.strip()
    settings = load_settings()
    settings["channel"] = channel
    save_settings(settings)
    bot.send_message(message.chat.id, f"✅ Channel ត្រូវបានកំណត់ជា: <code>{channel}</code>")


@bot.message_handler(func=lambda m: STATE.get(m.from_user.id, {}).get("step") == "awaiting_addbalance")
def handle_addbalance(message):
    if not is_admin(message.from_user.id):
        return
    STATE.pop(message.from_user.id, None)
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ ទម្រង់មិនត្រឹមត្រូវ។ ឧទាហរណ៍៖ 8266854899 1.50")
        return
    try:
        target_id = int(parts[0])
        amount = float(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, "❌ ទម្រង់មិនត្រឹមត្រូវ។")
        return
    user = get_user(target_id)
    new_balance = max(0.0, round(user["balance"] + amount, 2))
    update_user(target_id, balance=new_balance)
    bot.send_message(message.chat.id, f"✅ សមតុល្យរបស់ {target_id} ឥឡូវនេះ: ${new_balance:.2f}")
    try:
        bot.send_message(target_id, f"💳 សមតុល្យរបស់អ្នកត្រូវបានកែសម្រួល។ សមតុល្យថ្មី: ${new_balance:.2f}")
    except Exception:
        pass


# ------------------------------------------------------------------
# FLASK KEEP-ALIVE (Render)
# ------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def home():
    return f"{BOT_DISPLAY_NAME} bot is running."


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=referral_watchdog, daemon=True).start()
    log.info("Bot starting... admins=%s", ADMIN_IDS)

    # If another instance (local Termux, an old Render deploy, etc.) is still
    # polling with the same BOT_TOKEN, Telegram returns 409 Conflict and
    # infinity_polling would exit. Instead of crash-looping, back off and retry —
    # this self-heals once the other instance stops.
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error("Polling crashed: %s — retrying in 15s", e)
            time.sleep(15)
