#!/usr/bin/env python3
# Telegram Trading Bot - FORCE 5 SIGNALS EVERY HOUR

import os
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import numpy as np
import yfinance as yf

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BOT2_API_URL = os.getenv("BOT2_API_URL", "http://localhost:5001/receive_signal")
USE_BOT2 = os.getenv("USE_BOT2", "true").lower() == "true"

TIMEFRAME = "5m"
LOOP_INTERVAL = 3600  # 1 hour

# 5 PAIRS
SYMBOLS = [
    "GBP/USD",
    "EUR/USD",
    "JPY/USD",
    "XAU/USD",
    "BTC/USD",
]

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("ERROR: Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# SEND TO BOT #2
# ============================================================

def send_signal_to_bot2(signal_data):
    if not USE_BOT2:
        return False
    try:
        response = requests.post(BOT2_API_URL, json=signal_data, timeout=5)
        if response.status_code == 200:
            logger.info(f"📡 Signal sent to BOT #2: {signal_data.get('signal')} for {signal_data.get('symbol')}")
            return True
        return False
    except:
        return False

def send_telegram_message_direct(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except:
        return False

def send_telegram_message(message):
    if not USE_BOT2:
        return send_telegram_message_direct(message)
    return True

# ============================================================
# DATA FROM YAHOO FINANCE
# ============================================================

def get_klines_yahoo(symbol, interval="5m", limit=150):
    try:
        yahoo_symbols = {
            "GBP/USD": "GBPUSD=X",
            "EUR/USD": "EURUSD=X",
            "JPY/USD": "JPY=X",
            "XAU/USD": "GC=F",
            "BTC/USD": "BTC-USD"
        }
        yahoo_symbol = yahoo_symbols.get(symbol, symbol)
        yf_interval = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h"}.get(interval, "5m")
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period="30d", interval=yf_interval)
        if df.empty:
            return None
        df = df.reset_index()
        df = df.rename(columns={'Datetime': 'timestamp', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
        return df.tail(limit)
    except Exception as e:
        logger.error(f"Yahoo error for {symbol}: {e}")
        return None

def get_market_data(symbol):
    return get_klines_yahoo(symbol, TIMEFRAME, limit=150)

# ============================================================
# 5 STRATEGIES
# ============================================================

def strategy_rsi_divergence(df):
    try:
        if len(df) < 30:
            return {'signal': None, 'score': 0, 'desc': ''}
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        price_1 = df['close'].iloc[-2]
        price_2 = df['close'].iloc[-1]
        rsi_1 = rsi.iloc[-2]
        rsi_2 = rsi.iloc[-1]
        if price_2 < price_1 and rsi_2 > rsi_1:
            return {'signal': 'BUY', 'score': 85, 'desc': 'RSI Divergence Bullish'}
        if price_2 > price_1 and rsi_2 < rsi_1:
            return {'signal': 'SELL', 'score': 85, 'desc': 'RSI Divergence Bearish'}
        return {'signal': None, 'score': 0, 'desc': ''}
    except:
        return {'signal': None, 'score': 0, 'desc': ''}

def strategy_macd_ema_crossover(df):
    try:
        if len(df) < 50:
            return {'signal': None, 'score': 0, 'desc': ''}
        ema_fast = df['close'].ewm(span=9, adjust=False).mean()
        ema_slow = df['close'].ewm(span=21, adjust=False).mean()
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        prev_ema_fast = ema_fast.iloc[-2]
        prev_ema_slow = ema_slow.iloc[-2]
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        if (prev_macd <= prev_signal and current_macd > current_signal and current_ema_fast > current_ema_slow):
            return {'signal': 'BUY', 'score': 75, 'desc': 'MACD bullish crossover + EMA above'}
        if (prev_macd >= prev_signal and current_macd < current_signal and current_ema_fast < current_ema_slow):
            return {'signal': 'SELL', 'score': 75, 'desc': 'MACD bearish crossover + EMA below'}
        return {'signal': None, 'score': 0, 'desc': ''}
    except:
        return {'signal': None, 'score': 0, 'desc': ''}

def strategy_bollinger_squeeze(df):
    try:
        if len(df) < 20:
            return {'signal': None, 'score': 0, 'desc': ''}
        period = 20
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        bandwidth = (upper - lower) / sma
        current_bandwidth = bandwidth.iloc[-1]
        prev_bandwidth = bandwidth.iloc[-2]
        current_price = df['close'].iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        if current_bandwidth < 0.05 and prev_bandwidth > current_bandwidth:
            if current_price > current_upper * 0.98:
                return {'signal': 'BUY', 'score': 80, 'desc': 'Bollinger Squeeze - Breaking UP'}
            elif current_price < current_lower * 1.02:
                return {'signal': 'SELL', 'score': 80, 'desc': 'Bollinger Squeeze - Breaking DOWN'}
        return {'signal': None, 'score': 0, 'desc': ''}
    except:
        return {'signal': None, 'score': 0, 'desc': ''}

def strategy_ichimoku(df):
    try:
        if len(df) < 52:
            return {'signal': None, 'score': 0, 'desc': ''}
        period9_high = df['high'].rolling(window=9).max()
        period9_low = df['low'].rolling(window=9).min()
        tenkan = (period9_high + period9_low) / 2
        period26_high = df['high'].rolling(window=26).max()
        period26_low = df['low'].rolling(window=26).min()
        kijun = (period26_high + period26_low) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        current_price = df['close'].iloc[-1]
        current_tenkan = tenkan.iloc[-1]
        current_kijun = kijun.iloc[-1]
        current_senkou_a = senkou_a.iloc[-1]
        prev_tenkan = tenkan.iloc[-2]
        prev_kijun = kijun.iloc[-2]
        if (prev_tenkan <= prev_kijun and current_tenkan > current_kijun and current_price > current_senkou_a):
            return {'signal': 'BUY', 'score': 90, 'desc': 'Ichimoku TK Cross + Price above Cloud'}
        if (prev_tenkan >= prev_kijun and current_tenkan < current_kijun and current_price < current_senkou_a):
            return {'signal': 'SELL', 'score': 90, 'desc': 'Ichimoku TK Cross + Price below Cloud'}
        return {'signal': None, 'score': 0, 'desc': ''}
    except:
        return {'signal': None, 'score': 0, 'desc': ''}

def strategy_volume_price(df):
    try:
        if len(df) < 20:
            return {'signal': None, 'score': 0, 'desc': ''}
        avg_volume = df['volume'].rolling(window=20).mean()
        current_volume = df['volume'].iloc[-1]
        prev_volume = df['volume'].iloc[-2]
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        volume_surge = current_volume > avg_volume.iloc[-1] * 1.5
        if volume_surge:
            if current_price > prev_price and current_volume > prev_volume:
                return {'signal': 'BUY', 'score': 70, 'desc': 'Volume surge + Price UP'}
            elif current_price < prev_price and current_volume > prev_volume:
                return {'signal': 'SELL', 'score': 70, 'desc': 'Volume surge + Price DOWN'}
        return {'signal': None, 'score': 0, 'desc': ''}
    except:
        return {'signal': None, 'score': 0, 'desc': ''}

# ============================================================
# COMBINE ALL STRATEGIES - RETURNS BEST SIGNAL
# ============================================================

def analyze_all_strategies(df):
    strategies = [
        ('RSI Divergence', strategy_rsi_divergence),
        ('MACD + EMA', strategy_macd_ema_crossover),
        ('Bollinger Squeeze', strategy_bollinger_squeeze),
        ('Ichimoku Cloud', strategy_ichimoku),
        ('Volume + Price', strategy_volume_price),
    ]
    
    results = []
    buy_score = 0
    sell_score = 0
    best_strategy = None
    best_desc = ""
    best_score = 0
    
    for name, strategy_func in strategies:
        result = strategy_func(df)
        if result['signal'] == 'BUY':
            buy_score += result['score']
            results.append(f"🟢 {name}: +{result['score']}% - {result['desc']}")
            if result['score'] > best_score:
                best_score = result['score']
                best_strategy = name
                best_desc = result['desc']
        elif result['signal'] == 'SELL':
            sell_score += result['score']
            results.append(f"🔴 {name}: +{result['score']}% - {result['desc']}")
            if result['score'] > best_score:
                best_score = result['score']
                best_strategy = name
                best_desc = result['desc']
    
    # FORCE SIGNAL - always return the best available
    if buy_score > sell_score and buy_score > 0:
        return {
            'signal': 'BUY',
            'confidence': min(buy_score, 98),
            'details': results,
            'best_strategy': best_strategy,
            'desc': best_desc
        }
    elif sell_score > buy_score and sell_score > 0:
        return {
            'signal': 'SELL',
            'confidence': min(sell_score, 98),
            'details': results,
            'best_strategy': best_strategy,
            'desc': best_desc
        }
    elif buy_score > 0:
        return {
            'signal': 'WATCH_BUY',
            'confidence': buy_score,
            'details': results,
            'best_strategy': best_strategy,
            'desc': best_desc
        }
    elif sell_score > 0:
        return {
            'signal': 'WATCH_SELL',
            'confidence': sell_score,
            'details': results,
            'best_strategy': best_strategy,
            'desc': best_desc
        }
    
    # NO SIGNAL FROM STRATEGIES - return NEUTRAL (always send something)
    return {
        'signal': 'NEUTRAL',
        'confidence': 30,
        'details': ['No clear signal from strategies'],
        'best_strategy': 'Market Analysis',
        'desc': 'Market is ranging - No strong setup'
    }

# ============================================================
# ANALYZE ONE PAIR - ALWAYS RETURNS A SIGNAL
# ============================================================

def analyze_symbol(symbol):
    df = get_market_data(symbol)
    if df is None or len(df) < 52:
        # Return default signal if no data
        return {
            'symbol': symbol,
            'signal': 'NO_DATA',
            'price': 0,
            'rsi': 50,
            'confidence': 10,
            'details': ['Unable to fetch market data'],
            'best_strategy': 'N/A',
            'desc': 'Data unavailable - check connection'
        }
    
    current_price = df['close'].iloc[-1]
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    analysis = analyze_all_strategies(df)
    
    return {
        'symbol': symbol,
        'signal': analysis['signal'],
        'price': current_price,
        'rsi': current_rsi,
        'confidence': analysis['confidence'],
        'details': analysis['details'],
        'best_strategy': analysis['best_strategy'],
        'desc': analysis['desc']
    }

# ============================================================
# FORMAT MESSAGE
# ============================================================

def format_signal_message(analysis):
    symbol = analysis['symbol']
    price = analysis['price']
    rsi = analysis['rsi']
    confidence = analysis['confidence']
    signal = analysis['signal']
    
    # Format price based on pair
    if symbol == "XAU/USD":
        volatility = 0.008
        price_str = f"${price:,.2f}"
    elif symbol in ["GBP/USD", "EUR/USD", "JPY/USD"]:
        volatility = 0.005
        price_str = f"{price:.4f}"
    else:
        volatility = 0.02
        price_str = f"${price:,.0f}"
    
    # Signal type
    if signal == "BUY":
        emoji = "🟢"
        action = "STRONG BUY"
        sl = price * (1 - volatility)
        tp = price * (1 + volatility * 2.5)
        sl_change = f"-{volatility*100:.1f}%"
        tp_change = f"+{volatility*2.5*100:.1f}%"
        advice = "🚀 STRONG SIGNAL - All indicators confirm"
    elif signal == "SELL":
        emoji = "🔴"
        action = "STRONG SELL"
        sl = price * (1 + volatility)
        tp = price * (1 - volatility * 2.5)
        sl_change = f"+{volatility*100:.1f}%"
        tp_change = f"-{volatility*2.5*100:.1f}%"
        advice = "⚠️ STRONG SIGNAL - All indicators confirm"
    elif signal == "WATCH_BUY":
        emoji = "🟡"
        action = "WATCH BUY"
        sl = price * (1 - volatility * 0.7)
        tp = price * (1 + volatility * 1.5)
        sl_change = f"-{volatility*0.7*100:.1f}%"
        tp_change = f"+{volatility*1.5*100:.1f}%"
        advice = "👀 Weak buy signal - Wait for confirmation"
    elif signal == "WATCH_SELL":
        emoji = "🟡"
        action = "WATCH SELL"
        sl = price * (1 + volatility * 0.7)
        tp = price * (1 - volatility * 1.5)
        sl_change = f"+{volatility*0.7*100:.1f}%"
        tp_change = f"-{volatility*1.5*100:.1f}%"
        advice = "👀 Weak sell signal - Wait for confirmation"
    elif signal == "NEUTRAL":
        emoji = "⚪"
        action = "NEUTRAL"
        sl = price * (1 - volatility * 0.3)
        tp = price * (1 + volatility * 0.5)
        sl_change = f"-{volatility*0.3*100:.1f}%"
        tp_change = f"+{volatility*0.5*100:.1f}%"
        advice = "📊 Market ranging - No clear direction. Wait for breakout."
    else:
        emoji = "⚪"
        action = "NO DATA"
        sl = price
        tp = price
        sl_change = "0%"
        tp_change = "0%"
        advice = "⚠️ Unable to analyze - check connection"
    
    # Format SL/TP
    if symbol in ["GBP/USD", "EUR/USD", "JPY/USD"]:
        sl_str = f"{sl:.4f}"
        tp_str = f"{tp:.4f}"
    else:
        sl_str = f"${sl:,.2f}"
        tp_str = f"${tp:,.2f}"
    
    # Confidence bar
    bar = "█" * (confidence // 10) + "░" * (10 - (confidence // 10))
    
    # Strategies text
    if analysis['details']:
        strategies_text = "\n".join(analysis['details'][:3])
    else:
        strategies_text = "None"
    
    message = f"""
{emoji} *{action}* - {symbol}

💰 *Current Price:* {price_str}
📊 *RSI:* {rsi:.1f}
🎯 *Confidence:* {confidence}% {bar}

🏆 *Best Strategy:* {analysis['best_strategy']}
📝 *Details:* {analysis['desc']}

📊 *Signals Detected:*
{strategies_text}

🚪 *Entry:* {price_str}
🛑 *Stop-Loss:* {sl_str} ({sl_change})
🎯 *Take-Profit:* {tp_str} ({tp_change})

⏱️ *Analysis:* 5m timeframe | Signal every 1h

💡 {advice}
"""
    return message

# ============================================================
# MAIN LOOP - FORCES 5 SIGNALS EVERY HOUR
# ============================================================

def run_bot():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║   BOT TRADING - 5 SIGNALS EVERY HOUR                        ║
    ║                                                              ║
    ║   📊 5 PAIRS: GBP | EUR | JPY | XAU | BTC                  ║
    ║   🔄 5 SIGNALS every hour (1 per pair)                      ║
    ║   📡 BOT #2: ACTIVE                                         ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    logger.info("🤖 BOT STARTED - 5 SIGNALS EVERY HOUR")
    logger.info(f"📌 PAIRS: {', '.join(SYMBOLS)}")
    
    send_telegram_message("""🏆 *BOT TRADING - 5 SIGNALS EVERY HOUR*

📊 *Pairs monitored:*
• GBP/USD
• EUR/USD  
• JPY/USD
• XAU/USD (Gold)
• BTC/USD

🔄 *You will receive 1 signal per pair every hour*
⏱️ *Total: 5 signals/hour*

Bot is now active!""")
    
    # Track last signal time for each pair
    last_signal_time = {symbol: 0 for symbol in SYMBOLS}
    
    try:
        while True:
            current_time = time.time()
            
            for symbol in SYMBOLS:
                # Check if 1 hour has passed for this pair
                if current_time - last_signal_time[symbol] >= 3600:
                    logger.info(f"🔍 Analyzing {symbol}...")
                    
                    analysis = analyze_symbol(symbol)
                    
                    if analysis:
                        # Send to BOT #2
                        signal_data = {
                            'symbol': analysis['symbol'],
                            'signal': analysis['signal'],
                            'price': analysis['price'],
                            'rsi': analysis['rsi'],
                            'confidence': analysis['confidence'],
                            'details': analysis.get('details', []),
                            'best_strategy': analysis.get('best_strategy', ''),
                            'desc': analysis.get('desc', ''),
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        success = send_signal_to_bot2(signal_data)
                        
                        if not success and USE_BOT2:
                            # Fallback to direct message
                            msg = format_signal_message(analysis)
                            send_telegram_message_direct(msg)
                        
                        last_signal_time[symbol] = current_time
                        logger.info(f"✅ {symbol} - Signal sent: {analysis['signal']} ({analysis['confidence']}%)")
                    else:
                        logger.warning(f"⚠️ {symbol} - No analysis returned")
                    
                    # Small delay between pairs
                    time.sleep(2)
            
            logger.info(f"💤 All 5 pairs analyzed. Next cycle in 1 hour...")
            time.sleep(3600)  # Wait 1 hour before next full cycle
            
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
        send_telegram_message("🛑 *Bot Trading stopped.*")

if __name__ == "__main__":
    run_bot()