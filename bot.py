# ===========================
# PART 1 — IMPORTS & CONFIG
# ===========================

import os
import asyncio
import logging
import datetime
from datetime import timedelta, datetime

from dotenv import load_dotenv
load_dotenv()

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Message
)
from pyrogram.errors import FloodWait, MessageNotModified

from pymongo import MongoClient
from bson.objectid import ObjectId

# ---------------------------
# LOGGING SETUP
# ---------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("VideoBot")

# ---------------------------
# PLACEHOLDERS (TUM BAAD ME BHAROGE)
# ---------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://username:password@cluster.mongodb.net/mydb?retryWrites=true&w=majority"
)

DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID", "-1001234567890"))   # tumhara storage channel
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "-1009876543210"))     # owner log group

START_IMAGE = os.getenv(
    "START_IMAGE",
    "https://telegra.ph/file/your_start_image.jpg"
)

PAYMENT_QR = os.getenv(
    "PAYMENT_QR",
    "https://telegra.ph/file/your_qr_image.jpg"
)

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

DEFAULT_DAILY_LIMIT = 5        # free users
DONATION_DAILY_LIMIT = 40      # paid users
DONATION_AMOUNT = 3            # ₹3
REMINDER_DAYS = 5              # last 5 days reminder start

# ---------------------------
# INIT BOT
# ---------------------------

app = Client(
    "VideoLimitBot",
    bot_token=BOT_TOKEN
)

# ---------------------------
# CONNECT MONGODB
# ---------------------------

mongo = MongoClient(MONGO_URI)
db = mongo["videobot"]

users_col = db["users"]
content_col = db["content"]
payments_col = db["payments"]
codes_col = db["codes"]
banned_col = db["banned"]
bonus_col = db["daily_bonus"]

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------

def now_ist():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def today_str():
    return now_ist().strftime("%Y-%m-%d")

async def is_banned(user_id: int) -> bool:
    return banned_col.find_one({"user_id": user_id}) is not None

async def ensure_user_exists(user_id: int, username: str | None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "username": username,
            "daily_limit": DEFAULT_DAILY_LIMIT,
            "used_today": 0,
            "premium": False,
            "premium_until": None,
            "joined_at": now_ist(),
            "last_active": now_ist()
        })
# ===========================
# PART 2 — START + MENU UI
# ===========================

# -------- MAIN MENU KEYBOARD --------

def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Increase Daily Limit", callback_data="increase_limit")],

            [
                InlineKeyboardButton("👤 Profile", callback_data="profile"),
                InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")
            ],

            [
                InlineKeyboardButton("📦 Backup Group", url="https://t.me/your_backup_group"),
                InlineKeyboardButton("📢 Updates", url="https://t.me/your_updates_channel")
            ],

            [InlineKeyboardButton("▶️ Next Video", callback_data="next_video")]
        ]
    )


# -------- BACK BUTTON --------

def back_to_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_menu")]]
    )


# -------- START COMMAND --------

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):

    user_id = message.from_user.id
    username = message.from_user.username

    # ensure user in DB
    await ensure_user_exists(user_id, username)

    # log to admin group
    try:
        await app.send_photo(
            LOG_GROUP_ID,
            photo=START_IMAGE,
            caption=f"""
🆕 **New User Started Bot**

👤 User: @{username}
🆔 User ID: `{user_id}`
🟢 Status: Active
📅 Joined: {now_ist().strftime("%Y-%m-%d %H:%M:%S")}
"""
        )
    except Exception as e:
        logger.error(f"Log group error: {e}")

    # send welcome + menu
    await app.send_photo(
        chat_id=user_id,
        photo=START_IMAGE,
        caption="""
👋 **Welcome to Video Limit Bot!**

Use the menu below to:
• Watch videos  
• Claim daily bonus  
• Increase your limit  
• Check your profile  
""",
        reply_markup=main_menu()
    )


# -------- CALLBACK HANDLER (MENU ROUTER) --------

@app.on_callback_query()
async def menu_router(client, callback):

    data = callback.data
    user_id = callback.from_user.id

    if await is_banned(user_id):
        await callback.answer("🚫 You are banned.", show_alert=True)
        return

    # ---- BACK TO MENU ----
    if data == "back_menu":
        await callback.message.edit_reply_markup(main_menu())
        return

    # ---- INCREASE LIMIT PAGE ----
    if data == "increase_limit":
        text = f"""
💎 **Increase Daily Limit**

Donate only ₹{DONATION_AMOUNT} to get:
• {DONATION_DAILY_LIMIT} videos per day  
• Valid for 1 full month  

If interested, click **Donate** below.
"""

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("💸 Donate", callback_data="donate"),
                    InlineKeyboardButton("⬅️ Back", callback_data="back_menu")
                ]
            ]
        )

        await callback.message.edit_text(text, reply_markup=kb)
        return

    # ---- DONATE PAGE ----
    if data == "donate":
        text = """
📲 **Payment Instructions**

1) Scan QR and pay  
2) Click **Submit Payment**  
3) Send payment screenshot  
4) Wait for approval  
"""

        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📤 Submit Payment", callback_data="submit_payment")],
                [InlineKeyboardButton("⬅️ Back", callback_data="back_menu")]
            ]
        )

        await callback.message.edit_media(
            media=PAYMENT_QR,
            caption=text,
            reply_markup=kb
        )
        return

    # ---- PROFILE ----
    if data == "profile":
        u = users_col.find_one({"user_id": user_id})

        premium = "Yes ✅" if u.get("premium") else "No ❌"
        expiry = u.get("premium_until") or "Not applicable"

        text = f"""
👤 **Your Profile**

🆔 User ID: `{user_id}`
📊 Daily Limit: {u.get('daily_limit')}
🎯 Used Today: {u.get('used_today')}
💎 Premium: {premium}
📅 Premium Until: {expiry}
"""

        await callback.message.edit_text(text, reply_markup=back_to_menu())
        return

    # ---- DAILY BONUS BUTTON ----
    if data == "daily_bonus":
        today = today_str()

        if bonus_col.find_one({"user_id": user_id, "date": today}):
            await callback.answer("✅ Bonus already claimed today!", show_alert=True)
        else:
            bonus_col.insert_one({"user_id": user_id, "date": today})
            users_col.update_one(
                {"user_id": user_id},
                {"$set": {"used_today": 0}}
            )
            await callback.answer("🎁 Daily bonus claimed! You can use Next.", show_alert=True)

        await callback.message.edit_reply_markup(main_menu())
        return
# ===========================
# PART 3 — NEXT VIDEO LOGIC
# ===========================

async def pick_next_content():
    """
    MongoDB se ek unused content pick karega.
    Tum baad me isko random / category wise change kar sakte ho.
    """
    doc = content_col.find_one({"valid": True})

    if not doc:
        return None

    return {
        "channel_id": doc["channel_id"],
        "message_id": doc["message_id"]
    }


async def has_claimed_bonus_today(user_id: int) -> bool:
    today = today_str()
    return bonus_col.find_one({"user_id": user_id, "date": today}) is not None


@app.on_callback_query(filters.regex("^next_video$"))
async def next_video_handler(client, callback):
    user_id = callback.from_user.id

    # --- Ban check ---
    if await is_banned(user_id):
        await callback.answer("🚫 You are banned from using this bot.", show_alert=True)
        return

    user = users_col.find_one({"user_id": user_id})

    # --- Daily bonus check ---
    if not await has_claimed_bonus_today(user_id):
        await callback.answer(
            "🎁 First start and claim your Daily Bonus, then press Next!",
            show_alert=True
        )
        return

    # --- Limit check ---
    used = user.get("used_today", 0)
    limit = user.get("daily_limit", DEFAULT_DAILY_LIMIT)

    if used >= limit:
        await callback.answer(
            "❌ Your daily limit is finished.\nCome back tomorrow or donate to increase limit.",
            show_alert=True
        )
        return

    # --- Pick content from DB channel ---
    content = await pick_next_content()

    if not content:
        await callback.answer("⚠️ No more videos available right now.", show_alert=True)
        return

    try:
        # --- Send via copyMessage (clean, no forward tag) ---
        sent_msg = await app.copy_message(
            chat_id=user_id,
            from_chat_id=content["channel_id"],
            message_id=content["message_id"],
            caption=(
                "💡 If you want to watch again, forward to Saved Messages.\n"
                "🗑️ This message will auto delete in 60 seconds."
            )
        )

        # --- Increase used count ---
        users_col.update_one(
            {"user_id": user_id},
            {"$inc": {"used_today": 1}}
        )

        # --- Auto delete after 60 seconds ---
        async def auto_delete_task(msg: Message):
            await asyncio.sleep(60)
            try:
                await msg.delete()
            except Exception as e:
                logger.warning(f"Auto delete failed: {e}")

        asyncio.create_task(auto_delete_task(sent_msg))

        await callback.answer("▶️ Video sent!", show_alert=False)

    except Exception as e:
        logger.error(f"copyMessage error: {e}")
        await callback.answer("❌ Failed to send video. Try again later.", show_alert=True)


# -------- OPTIONAL: RESET DAILY LIMIT AT MIDNIGHT (IST) --------
async def reset_daily_usage():
    while True:
        now = now_ist()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5)

        sleep_seconds = (tomorrow - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        users_col.update_many({}, {"$set": {"used_today": 0}})
        logger.info("Daily limits reset for all users.")


asyncio.create_task(reset_daily_usage())
# ===========================
# PART 4 — PAYMENT SYSTEM
# ===========================

# ---------- STEP 1: USER CLICKS "SUBMIT PAYMENT" ----------

@app.on_callback_query(filters.regex("^submit_payment$"))
async def ask_screenshot(client, callback):
    await callback.message.edit_text(
        "📤 **Send your payment screenshot now.**\n\n"
        "After sending, wait for owner approval.",
        reply_markup=back_to_menu()
    )
    await callback.answer("Send screenshot in chat.", show_alert=False)


# ---------- STEP 2: CAPTURE SCREENSHOT ----------

@app.on_message(filters.photo)
async def receive_payment_ss(client, message: Message):

    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"

    # Save payment in DB (pending)
    pay_doc = {
        "user_id": user_id,
        "username": username,
        "photo_file_id": message.photo.file_id,
        "status": "pending",
        "submitted_at": now_ist()
    }
    payments_col.insert_one(pay_doc)

    # Send to log group with approve/decline buttons
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_{user_id}"
                ),
                InlineKeyboardButton(
                    "❌ Decline",
                    callback_data=f"decline_{user_id}"
                )
            ]
        ]
    )

    try:
        await app.send_photo(
            LOG_GROUP_ID,
            photo=message.photo.file_id,
            caption=f"""
💰 **New Payment Submitted**

👤 User: @{username}
🆔 User ID: `{user_id}`
💵 Amount: ₹{DONATION_AMOUNT}
📅 Time: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}
""",
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Log group error: {e}")

    await message.reply(
        "✅ Payment submitted! Please wait for owner approval."
    )


# ---------- STEP 3: OWNER APPROVES PAYMENT ----------

@app.on_callback_query(filters.regex("^approve_"))
async def approve_payment(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Only owner can approve.", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])

    # Update user premium status
    premium_until = now_ist() + timedelta(days=30)

    users_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "premium": True,
                "premium_until": premium_until,
                "daily_limit": DONATION_DAILY_LIMIT,
                "used_today": 0
            }
        }
    )

    payments_col.update_one(
        {"user_id": user_id, "status": "pending"},
        {"$set": {"status": "approved", "approved_at": now_ist()}}
    )

    # Notify user
    try:
        await app.send_message(
            user_id,
            f"""
🎉 **Congratulations!**

Your daily limit is now:
• {DONATION_DAILY_LIMIT} videos per day  
• Valid until: {premium_until.strftime('%Y-%m-%d')}

Enjoy! ▶️ Press **Next Video** anytime.
"""
        )
    except Exception as e:
        logger.error(f"Notify error: {e}")

    await callback.message.edit_caption(
        callback.message.caption + "\n\n🟢 **APPROVED BY OWNER**"
    )
    await callback.answer("Payment approved.")


# ---------- STEP 4: OWNER DECLINES PAYMENT ----------

@app.on_callback_query(filters.regex("^decline_"))
async def decline_payment(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Only owner can decline.", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])

    payments_col.update_one(
        {"user_id": user_id, "status": "pending"},
        {"$set": {"status": "declined", "declined_at": now_ist()}}
    )

    try:
        await app.send_message(
            user_id,
            "❌ **Payment declined.**\n"
            "If this is a mistake, please try again."
        )
    except Exception as e:
        logger.error(f"Notify error: {e}")

    await callback.message.edit_caption(
        callback.message.caption + "\n\n🔴 **DECLINED BY OWNER**"
    )
    await callback.answer("Payment declined.")


# ---------- AUTO REMINDER FOR EXPIRY (LAST 5 DAYS) ----------

async def premium_reminder_loop():
    while True:
        await asyncio.sleep(6 * 60 * 60)  # every 6 hours

        users = users_col.find({"premium": True})

        for u in users:
            user_id = u["user_id"]
            expiry = u.get("premium_until")

            if not expiry:
                continue

            days_left = (expiry - now_ist()).days

            if 0 <= days_left <= REMINDER_DAYS:
                try:
                    kb = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("💸 Donate Now", callback_data="increase_limit")]]
                    )

                    await app.send_message(
                        user_id,
                        f"""
⚠️ **Premium expiring soon!**

Your daily limit ends on: {expiry.strftime('%Y-%m-%d')}

Donate ₹{DONATION_AMOUNT} to extend for another month.
""",
                        reply_markup=kb
                    )
                except Exception as e:
                    logger.warning(f"Reminder failed for {user_id}: {e}")

asyncio.create_task(premium_reminder_loop())
# ==================================================
# PART 5 — ADMIN COMMANDS + CODES + BAN + BROADCAST
# ==================================================

# ---------- OWNER ONLY FILTER ----------
def is_owner(_, __, message):
    return message.from_user and message.from_user.id == OWNER_ID

owner_filter = filters.create(is_owner)

# -----------------------------
# /setdailylimit {userid} {n}
# -----------------------------
@app.on_message(filters.command("setdailylimit") & owner_filter)
async def set_daily_limit(client, message):
    try:
        _, uid, limit = message.text.split()
        uid = int(uid)
        limit = int(limit)

        users_col.update_one(
            {"user_id": uid},
            {"$set": {"daily_limit": limit}}
        )

        await message.reply(f"✅ Daily limit of `{uid}` set to **{limit}**")
    except Exception as e:
        await message.reply(
            "Usage: /setdailylimit <userid> <number>\n"
            f"Error: {e}"
        )

# -----------------------------
# /rmdailylimit {userid}
# -----------------------------
@app.on_message(filters.command("rmdailylimit") & owner_filter)
async def remove_daily_limit(client, message):
    try:
        _, uid = message.text.split()
        uid = int(uid)

        users_col.update_one(
            {"user_id": uid},
            {"$set": {"daily_limit": DEFAULT_DAILY_LIMIT, "premium": False}}
        )

        await message.reply(f"✅ Premium removed for `{uid}`")
    except Exception as e:
        await message.reply("Usage: /rmdailylimit <userid>")

# -----------------------------
# /gencode {videos} {days}
# -----------------------------
@app.on_message(filters.command("gencode") & owner_filter)
async def gen_code(client, message):
    try:
        _, videos, days = message.text.split()
        videos = int(videos)
        days = int(days)

        code = f"VC-{videos}-{days}-{int(datetime.utcnow().timestamp())}"

        codes_col.insert_one({
            "code": code,
            "videos": videos,
            "days": days,
            "used": False,
            "created_at": now_ist()
        })

        await message.reply(
            f"🎟️ **Redeem Code Generated**\n\n"
            f"`{code}`\n\n"
            f"Videos/day: {videos}\nDays: {days}"
        )
    except Exception as e:
        await message.reply("Usage: /gencode <videos> <days>")

# -----------------------------
# /redeem {code}
# -----------------------------
@app.on_message(filters.command("redeem"))
async def redeem_code(client, message):
    try:
        _, code = message.text.split()

        c = codes_col.find_one({"code": code, "used": False})
        if not c:
            await message.reply("❌ Invalid or already used code.")
            return

        expiry = now_ist() + timedelta(days=c["days"])

        users_col.update_one(
            {"user_id": message.from_user.id},
            {
                "$set": {
                    "premium": True,
                    "premium_until": expiry,
                    "daily_limit": c["videos"],
                    "used_today": 0
                }
            }
        )

        codes_col.update_one({"code": code}, {"$set": {"used": True}})

        await message.reply(
            f"🎉 Code redeemed!\n"
            f"Limit: {c['videos']} videos/day\n"
            f"Valid till: {expiry.strftime('%Y-%m-%d')}"
        )
    except Exception as e:
        await message.reply("Usage: /redeem <CODE>")

# -----------------------------
# /ban {userid}
# -----------------------------
@app.on_message(filters.command("ban") & owner_filter)
async def ban_user(client, message):
    try:
        _, uid = message.text.split()
        uid = int(uid)

        banned_col.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid}},
            upsert=True
        )

        await message.reply(f"🚫 User `{uid}` banned from bot.")
    except Exception:
        await message.reply("Usage: /ban <userid>")

# -----------------------------
# /unban {userid}
# -----------------------------
@app.on_message(filters.command("unban") & owner_filter)
async def unban_user(client, message):
    try:
        _, uid = message.text.split()
        uid = int(uid)

        banned_col.delete_one({"user_id": uid})

        await message.reply(f"✅ User `{uid}` unbanned.")
    except Exception:
        await message.reply("Usage: /unban <userid>")

# ==================================================
# SIMPLE BROADCAST (BOT USERS ONLY)
# ==================================================
# (Tumhari broadcast.py ka simplified, bot-friendly version)
# 1

@app.on_message(filters.command("broadcast") & owner_filter)
async def broadcast_all(client, message):
    if not message.reply_to_message:
        await message.reply("Reply to a message with /broadcast")
        return

    sent = 0
    failed = 0

    users = users_col.find({})
    for u in users:
        uid = u["user_id"]
        try:
            await message.reply_to_message.copy(uid)
            sent += 1
            await asyncio.sleep(0.2)
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
        except Exception:
            failed += 1

    await message.reply(f"📢 Broadcast done.\nSent: {sent} | Failed: {failed}")

# ==================================================
# START BOT
# ==================================================

if __name__ == "__main__":
    logger.info("Bot is starting...")
    app.run()
