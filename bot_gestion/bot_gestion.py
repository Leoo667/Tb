#!/usr/bin/env python3
# BOT #2: CLIENT MANAGEMENT & SIGNAL DISTRIBUTION
# Receives 5 signals every hour from BOT #1 and distributes to active clients

import os
import time
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
import requests
from flask import Flask, request, jsonify

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_BOT2")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

CLIENTS_FILE = "clients.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================================
# CLIENT MANAGEMENT
# ============================================================

def load_clients():
    try:
        with open(CLIENTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_clients(clients):
    with open(CLIENTS_FILE, 'w') as f:
        json.dump(clients, f, indent=2)

def add_client(chat_id, name, days=30):
    clients = load_clients()
    expiry = time.time() + (days * 86400)
    clients[str(chat_id)] = {
        "name": name,
        "expiry": expiry,
        "expiry_date": datetime.fromtimestamp(expiry).strftime('%Y-%m-%d'),
        "status": "active",
        "joined_at": datetime.now().isoformat()
    }
    save_clients(clients)
    logger.info(f"✅ New client: {name} ({chat_id}) - expires {clients[str(chat_id)]['expiry_date']}")
    return True

def remove_client(chat_id):
    clients = load_clients()
    if str(chat_id) in clients:
        del clients[str(chat_id)]
        save_clients(clients)
        logger.info(f"❌ Client removed: {chat_id}")
        return True
    return False

def is_active(chat_id):
    clients = load_clients()
    client = clients.get(str(chat_id))
    if not client:
        return False
    return time.time() < client.get('expiry', 0)

def get_active_clients():
    clients = load_clients()
    return [int(cid) for cid, c in clients.items() if time.time() < c.get('expiry', 0)]

def get_remaining_days(chat_id):
    clients = load_clients()
    client = clients.get(str(chat_id))
    if not client:
        return 0
    remaining = (client['expiry'] - time.time()) / 86400
    return max(0, int(remaining))

def get_clients_stats():
    clients = load_clients()
    total = len(clients)
    active = len(get_active_clients())
    return {
        'total': total,
        'active': active,
        'expired': total - active,
        'revenue': active * 15
    }

# ============================================================
# TELEGRAM FUNCTIONS
# ============================================================

def send_message(chat_id, text):
    """Send message via Telegram Bot API"""
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token not defined!")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
        if r.status_code == 200:
            logger.info(f"✅ Message sent to {chat_id}")
            return True
        else:
            logger.error(f"❌ Telegram error: {r.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return False

# ============================================================
# SIGNAL FORMATTING - BEAUTIFUL LAYOUT
# ============================================================

def format_signal_message(signal_data):
    """Format signal message with beautiful layout"""
    
    symbol = signal_data.get('symbol', 'Unknown')
    signal_type = signal_data.get('signal', 'Unknown')
    entry_price = signal_data.get('price', 0)
    rsi = signal_data.get('rsi', 50)
    confidence = signal_data.get('confidence', 0)
    best_strategy = signal_data.get('best_strategy', '')
    desc = signal_data.get('desc', '')
    details = signal_data.get('details', [])
    
    # Determine volatility and price format based on pair
    if symbol == "XAU/USD":
        volatility = 0.008
        price_str = f"${entry_price:,.2f}"
    elif symbol in ["GBP/USD", "EUR/USD", "JPY/USD"]:
        volatility = 0.005
        price_str = f"{entry_price:.4f}"
    else:
        volatility = 0.02
        price_str = f"${entry_price:,.0f}"
    
    # Signal type configuration
    if signal_type == "BUY":
        emoji = "🟢"
        action = "STRONG BUY"
        sl = entry_price * (1 - volatility)
        tp = entry_price * (1 + volatility * 2.5)
        sl_change = f"-{volatility*100:.1f}%"
        tp_change = f"+{volatility*2.5*100:.1f}%"
        advice = "🚀 STRONG SIGNAL - All indicators confirm"
    elif signal_type == "SELL":
        emoji = "🔴"
        action = "STRONG SELL"
        sl = entry_price * (1 + volatility)
        tp = entry_price * (1 - volatility * 2.5)
        sl_change = f"+{volatility*100:.1f}%"
        tp_change = f"-{volatility*2.5*100:.1f}%"
        advice = "⚠️ STRONG SIGNAL - All indicators confirm"
    elif signal_type == "WATCH_BUY":
        emoji = "🟡"
        action = "WATCH BUY"
        sl = entry_price * (1 - volatility * 0.7)
        tp = entry_price * (1 + volatility * 1.5)
        sl_change = f"-{volatility*0.7*100:.1f}%"
        tp_change = f"+{volatility*1.5*100:.1f}%"
        advice = "👀 Weak buy signal - Wait for confirmation"
    elif signal_type == "WATCH_SELL":
        emoji = "🟡"
        action = "WATCH SELL"
        sl = entry_price * (1 + volatility * 0.7)
        tp = entry_price * (1 - volatility * 1.5)
        sl_change = f"+{volatility*0.7*100:.1f}%"
        tp_change = f"-{volatility*1.5*100:.1f}%"
        advice = "👀 Weak sell signal - Wait for confirmation"
    elif signal_type == "NEUTRAL":
        emoji = "⚪"
        action = "NEUTRAL"
        sl = entry_price * (1 - volatility * 0.3)
        tp = entry_price * (1 + volatility * 0.5)
        sl_change = f"-{volatility*0.3*100:.1f}%"
        tp_change = f"+{volatility*0.5*100:.1f}%"
        advice = "📊 Market ranging - No clear direction. Wait for breakout."
    elif signal_type == "NO_DATA":
        emoji = "⚠️"
        action = "NO DATA"
        sl = entry_price
        tp = entry_price
        sl_change = "0%"
        tp_change = "0%"
        advice = "⚠️ Unable to analyze market data. Check connection."
    else:
        emoji = "⚪"
        action = signal_type
        sl = entry_price
        tp = entry_price
        sl_change = "0%"
        tp_change = "0%"
        advice = ""
    
    # Format SL/TP based on pair
    if symbol in ["GBP/USD", "EUR/USD", "JPY/USD"]:
        sl_str = f"{sl:.4f}"
        tp_str = f"{tp:.4f}"
    else:
        sl_str = f"${sl:,.2f}"
        tp_str = f"${tp:,.2f}"
    
    # Confidence bar
    bar_length = confidence // 10
    bar = "█" * bar_length + "░" * (10 - bar_length)
    
    # Strategies text
    if details:
        strategies_text = "\n".join(details[:3])
    else:
        strategies_text = "None"
    
    # Current time
    current_time = datetime.now().strftime('%I:%M %p')
    
    # Build the beautiful message
    message = f"""
{emoji} *{action}* - {symbol}

💰 *Current Price:* {price_str}
📊 *RSI:* {rsi:.1f}
🎯 *Confidence:* {confidence}% {bar}

🏆 *Best Strategy:* {best_strategy}
📝 *Details:* {desc}

📊 *Signals Detected:*
{strategies_text}

🚪 *Entry:* {price_str}
🛑 *Stop-Loss:* {sl_str} ({sl_change})
🎯 *Take-Profit:* {tp_str} ({tp_change})

⏱️ *Analysis:* 5m timeframe | Signal every hour
🕐 *Time:* {current_time}

💡 {advice}
"""
    return message

# ============================================================
# API ENDPOINTS (Receives signals from BOT #1)
# ============================================================

@app.route('/receive_signal', methods=['POST'])
def receive_signal():
    """Receive signal from BOT #1 and distribute to active clients"""
    data = request.json
    signal_type = data.get('signal', 'Unknown')
    symbol = data.get('symbol', 'Unknown')
    
    logger.info(f"📡 Signal received: {signal_type} - {symbol}")
    
    active_clients = get_active_clients()
    
    if not active_clients:
        logger.info("⚠️ No active clients")
        return jsonify({"ok": True, "message": "No active clients", "sent": 0}), 200
    
    # Format the beautiful message
    message = format_signal_message(data)
    
    # Send to all active clients
    sent = 0
    for client_id in active_clients:
        if send_message(client_id, message):
            sent += 1
        time.sleep(0.1)  # Rate limit protection
    
    logger.info(f"✅ Signal distributed to {sent} clients")
    
    return jsonify({"ok": True, "sent": sent, "total_clients": len(active_clients)}), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "alive",
        "active_clients": len(get_active_clients()),
        "total_clients": len(load_clients()),
        "token_configured": TELEGRAM_TOKEN is not None
    }), 200

@app.route('/stats', methods=['GET'])
def api_stats():
    """API endpoint for statistics"""
    stats = get_clients_stats()
    return jsonify(stats), 200

# ============================================================
# ADMIN COMMAND PROCESSOR (Polling)
# ============================================================

def check_messages():
    """Poll Telegram for admin commands"""
    last_update_id = 0
    
    print("👑 Admin bot ready - waiting for messages on Telegram...")
    print("💡 Commands: /addclient, /listclients, /stats, /broadcast, /info, /test")
    
    while True:
        try:
            if not TELEGRAM_TOKEN:
                time.sleep(5)
                continue
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            response = requests.get(url, params={"offset": last_update_id + 1, "timeout": 20}, timeout=25)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        last_update_id = update.get("update_id", last_update_id)
                        message = update.get("message", {})
                        chat_id = message.get("chat", {}).get("id")
                        text = message.get("text", "")
                        
                        # Only admin can use commands
                        if chat_id != ADMIN_CHAT_ID:
                            logger.warning(f"⛔ Unauthorized command from {chat_id}")
                            continue
                        
                        logger.info(f"📩 Admin command: {text}")
                        
                        # ========== COMMANDS ==========
                        if text == "/start":
                            send_message(chat_id, """
👑 *ADMIN PANEL - BOT #2*

📋 *Available Commands:*

🔹 `/addclient ID NAME DAYS`
   Example: `/addclient 7481692608 VEGAS 30`

🔹 `/removeclient ID`
   Example: `/removeclient 7481692608`

🔹 `/listclients`
   - Show all clients with remaining days

🔹 `/stats`
   - Show subscription statistics and revenue

🔹 `/broadcast MESSAGE`
   - Send message to all active clients

🔹 `/info ID`
   - Show detailed client information

🔹 `/test`
   - Test if bot is working

💡 *Signal Format:*
• 5 signals every hour (1 per pair)
• Pairs: GBP/USD, EUR/USD, JPY/USD, XAU/USD, BTC/USD
• Subscription: $15/month
""")
                        
                        elif text.startswith("/addclient"):
                            parts = text.split()
                            if len(parts) >= 3:
                                try:
                                    client_id = int(parts[1])
                                    name = parts[2]
                                    days = int(parts[3]) if len(parts) > 3 else 30
                                    add_client(client_id, name, days)
                                    send_message(chat_id, f"✅ Client {name} ({client_id}) added for {days} days")
                                    
                                    # Welcome message to client
                                    welcome_msg = f"""🎉 *Welcome {name}!*

✅ Your subscription is active for {days} days

💰 *Price:* $15/month (30 days)
🔄 *Renewal:* Contact @Admin

📊 *What you get:*
• **5 signals every hour** (1 per pair)
• Pairs: GBP/USD, EUR/USD, JPY/USD, XAU/USD, BTC/USD
• 5 expert strategies combined
• Stop-Loss & Take-Profit levels

Signals will arrive here automatically every hour!"""
                                    send_message(client_id, welcome_msg)
                                except Exception as e:
                                    send_message(chat_id, f"❌ Error: {str(e)}")
                            else:
                                send_message(chat_id, "❌ Usage: /addclient ID NAME DAYS\nExample: /addclient 7481692608 VEGAS 30")
                        
                        elif text.startswith("/removeclient"):
                            parts = text.split()
                            if len(parts) >= 2:
                                try:
                                    client_id = int(parts[1])
                                    client_info = load_clients().get(str(client_id), {})
                                    name = client_info.get('name', 'Client')
                                    remove_client(client_id)
                                    send_message(chat_id, f"✅ Client {name} ({client_id}) removed")
                                    send_message(client_id, "❌ Your subscription has been cancelled. Contact @Admin for more information.")
                                except Exception as e:
                                    send_message(chat_id, f"❌ Error: {str(e)}")
                            else:
                                send_message(chat_id, "❌ Usage: /removeclient ID")
                        
                        elif text == "/listclients":
                            clients = load_clients()
                            if not clients:
                                send_message(chat_id, "📋 No clients yet")
                            else:
                                msg = "📋 *CLIENT LIST:*\n\n"
                                for client_id, client in clients.items():
                                    days_left = get_remaining_days(int(client_id))
                                    status = "✅ ACTIVE" if days_left > 0 else "❌ EXPIRED"
                                    expiry = client.get('expiry_date', 'N/A')
                                    msg += f"*{client['name']}*\n"
                                    msg += f"   ID: `{client_id}`\n"
                                    msg += f"   Status: {status} | {days_left} days left\n"
                                    msg += f"   Expires: {expiry}\n\n"
                                send_message(chat_id, msg)
                        
                        elif text == "/stats":
                            stats = get_clients_stats()
                            msg = f"""
📊 *SUBSCRIPTION STATISTICS*

👥 Total clients: {stats['total']}
✅ Active clients: {stats['active']}
❌ Expired clients: {stats['expired']}

💰 *Monthly revenue:* ${stats['revenue']}
💎 *Subscription price:* $15/month

📈 *Signals per hour:* 5 (1 per pair)
🕐 *Pairs:* GBP, EUR, JPY, XAU, BTC

📅 *Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
                            send_message(chat_id, msg)
                        
                        elif text.startswith("/broadcast"):
                            parts = text.split(" ", 1)
                            if len(parts) > 1:
                                broadcast_msg = parts[1]
                                active_clients = get_active_clients()
                                sent = 0
                                for client_id in active_clients:
                                    if send_message(client_id, f"📢 *ADMIN ANNOUNCEMENT*\n\n{broadcast_msg}"):
                                        sent += 1
                                    time.sleep(0.1)
                                send_message(chat_id, f"✅ Message sent to {sent} clients")
                            else:
                                send_message(chat_id, "❌ Usage: /broadcast MESSAGE")
                        
                        elif text.startswith("/info"):
                            parts = text.split()
                            if len(parts) >= 2:
                                try:
                                    client_id = int(parts[1])
                                    clients = load_clients()
                                    client = clients.get(str(client_id))
                                    if client:
                                        days_left = get_remaining_days(client_id)
                                        status = "✅ ACTIVE" if days_left > 0 else "❌ EXPIRED"
                                        msg = f"""
📋 *CLIENT INFORMATION*

👤 *Name:* {client['name']}
🆔 *Chat ID:* {client_id}
📅 *Joined:* {client.get('joined_at', 'N/A')[:10]}
📅 *Expires:* {client.get('expiry_date', 'N/A')}
⏳ *Days left:* {days_left} days
📊 *Status:* {status}

💡 *They receive 5 signals every hour*
"""
                                        send_message(chat_id, msg)
                                    else:
                                        send_message(chat_id, f"❌ Client {client_id} does not exist")
                                except Exception as e:
                                    send_message(chat_id, f"❌ Error: {str(e)}")
                            else:
                                send_message(chat_id, "❌ Usage: /info ID")
                        
                        elif text == "/test":
                            send_message(chat_id, """✅ *Admin bot is working!*

📡 BOT #2 Status:
• API: Running on port 5001
• Active clients: """ + str(len(get_active_clients())) + f"""
• Total clients: {len(load_clients())}
• Token configured: YES

🔄 Ready to receive signals from BOT #1
💡 5 signals will be distributed every hour
""")
                        
                        else:
                            send_message(chat_id, "❓ Command not recognized. Type /start for available commands.")
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Admin loop error: {e}")
            time.sleep(5)

# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import threading
    
    # Verify configuration
    if not TELEGRAM_TOKEN:
        print("❌ ERROR: TELEGRAM_TOKEN_BOT2 not defined in .env file")
        print("Create .env file with:")
        print("TELEGRAM_TOKEN_BOT2=your_token_here")
        print("ADMIN_CHAT_ID=your_chat_id_here")
        exit(1)
    
    if ADMIN_CHAT_ID == 0:
        print("⚠️ WARNING: ADMIN_CHAT_ID not set. Admin commands disabled.")
    
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║   BOT #2: CLIENT MANAGEMENT & SIGNAL DISTRIBUTION           ║
    ║   ===============================================           ║
    ║                                                              ║
    ║   ✅ API Server: http://localhost:5001                      ║
    ║   ✅ Admin Bot: Active (waiting for commands)               ║
    ║   ✅ Signal Format: Beautiful layout with Entry/SL/TP       ║
    ║                                                              ║
    ║   📊 Subscription: $15/month                                ║
    ║   📈 Signals: 5 signals every hour (1 per pair)            ║
    ║   📌 Pairs: GBP, EUR, JPY, XAU, BTC                        ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    print(f"🤖 Admin Bot Token: {TELEGRAM_TOKEN[:20]}...")
    print(f"👑 Admin Chat ID: {ADMIN_CHAT_ID}")
    print("")
    print("💡 Commands you can send to this bot on Telegram:")
    print("   /addclient 123456789 NAME 30")
    print("   /listclients")
    print("   /stats")
    print("   /test")
    print("")
    
    # Start Flask API in background thread
    def run_api():
        app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
    
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    print("✅ API Server started on port 5001")
    
    # Start admin command processor (main thread)
    check_messages()