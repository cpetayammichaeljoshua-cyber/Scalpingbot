
#!/usr/bin/env python3
"""
Telegram Trade Scanner
Scans past trades from Telegram channel, analyzes responses, and feeds data to ML training
"""

import asyncio
import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import sqlite3
from telegram import Bot
from telegram.error import TelegramError

@dataclass
class TradeResponse:
    """Trade response data from Telegram channel"""
    message_id: int
    signal_text: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    timestamp: datetime
    responses: List[str]
    outcome: str  # 'profit', 'loss', 'partial', 'pending'
    profit_percentage: float
    duration_minutes: int

class TelegramTradeScanner:
    """Scans Telegram channel for trade signals and outcomes"""
    
    def __init__(self, bot_token: str, channel_username: str):
        self.bot_token = bot_token
        self.channel_username = channel_username
        self.bot = Bot(token=bot_token)
        self.logger = logging.getLogger(__name__)
        
        # Database for storing scanned trades
        self.db_path = "telegram_trade_scanner.db"
        self._initialize_database()
        
        # Pattern matching for signals and responses
        self.signal_patterns = {
            'symbol': r'#?(\w+USDT?)\s+(LONG|SHORT|BUY|SELL)',
            'entry': r'Entry:\s*(\d+\.?\d*)',
            'stop_loss': r'(?:SL|Stop\s*Loss):\s*(\d+\.?\d*)',
            'tp1': r'TP1?:\s*(\d+\.?\d*)',
            'tp2': r'TP2:\s*(\d+\.?\d*)',
            'tp3': r'TP3:\s*(\d+\.?\d*)',
            'leverage': r'(?:Leverage|LEV):\s*(\d+)x?',
        }
        
        # Response patterns for outcomes
        self.outcome_patterns = {
            'tp1_hit': r'TP1?\s+(?:HIT|REACHED|✅)',
            'tp2_hit': r'TP2\s+(?:HIT|REACHED|✅)',
            'tp3_hit': r'TP3\s+(?:HIT|REACHED|✅)',
            'sl_hit': r'(?:SL|Stop\s*Loss)\s+(?:HIT|REACHED|❌)',
            'profit': r'(?:PROFIT|WIN|✅).*?([+-]?\d+\.?\d*)%?',
            'loss': r'(?:LOSS|LOSE|❌).*?([+-]?\d+\.?\d*)%?',
            'closed': r'(?:CLOSED|FULL\s+CLOSE|EXIT)',
        }
    
    def _initialize_database(self):
        """Initialize database for storing scanned trades"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scanned_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL,
                    stop_loss REAL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    leverage INTEGER,
                    signal_timestamp TIMESTAMP,
                    outcome TEXT,
                    profit_percentage REAL,
                    duration_minutes INTEGER,
                    tp1_hit BOOLEAN DEFAULT 0,
                    tp2_hit BOOLEAN DEFAULT 0,
                    tp3_hit BOOLEAN DEFAULT 0,
                    sl_hit BOOLEAN DEFAULT 0,
                    responses_json TEXT,
                    signal_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER,
                    update_type TEXT,
                    update_text TEXT,
                    update_timestamp TIMESTAMP,
                    FOREIGN KEY (trade_id) REFERENCES scanned_trades (id)
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("📊 Telegram trade scanner database initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing scanner database: {e}")
    
    async def scan_channel_history(self, days_back: int = 7) -> List[TradeResponse]:
        """Scan Telegram channel for trade signals and responses"""
        try:
            self.logger.info(f"🔍 Scanning {self.channel_username} for last {days_back} days")
            
            # Get channel messages
            messages = await self._get_channel_messages(days_back)
            
            # Parse signals and responses
            trade_responses = []
            signals = {}
            
            for message in messages:
                # Check if message is a signal
                signal = self._parse_signal_message(message)
                if signal:
                    signals[signal['message_id']] = signal
                    continue
                
                # Check if message is a response/update to existing signal
                update = self._parse_update_message(message, signals)
                if update:
                    # Apply update to corresponding signal
                    signal_id = update.get('signal_id')
                    if signal_id in signals:
                        signals[signal_id].setdefault('updates', []).append(update)
            
            # Convert signals to TradeResponse objects
            for signal_id, signal_data in signals.items():
                trade_response = self._create_trade_response(signal_data)
                if trade_response:
                    trade_responses.append(trade_response)
            
            self.logger.info(f"📈 Found {len(trade_responses)} trade signals with responses")
            return trade_responses
            
        except Exception as e:
            self.logger.error(f"Error scanning channel history: {e}")
            return []
    
    async def _get_channel_messages(self, days_back: int) -> List[Dict]:
        """Get messages from Telegram channel"""
        try:
            messages = []
            offset_date = datetime.now() - timedelta(days=days_back)
            
            # This is a simplified approach - in production you'd need to handle pagination
            # and use proper Telegram API methods to get channel history
            
            # For now, we'll simulate getting recent messages
            # In real implementation, you'd use telegram.Bot.get_chat_history() or similar
            
            # Placeholder for actual implementation
            chat = await self.bot.get_chat(self.channel_username)
            
            # Note: Telegram Bot API has limitations for reading channel history
            # You might need to use Telegram Client API (pyrogram/telethon) for full history access
            
            return messages
            
        except TelegramError as e:
            self.logger.error(f"Telegram API error: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error getting channel messages: {e}")
            return []
    
    def _parse_signal_message(self, message: Dict) -> Optional[Dict]:
        """Parse a message to extract trading signal"""
        try:
            text = message.get('text', '')
            if not text:
                return None
            
            # Check if this looks like a trading signal
            symbol_match = re.search(self.signal_patterns['symbol'], text, re.IGNORECASE)
            if not symbol_match:
                return None
            
            symbol = symbol_match.group(1).upper()
            direction = symbol_match.group(2).upper()
            
            # Extract price levels
            entry_match = re.search(self.signal_patterns['entry'], text, re.IGNORECASE)
            sl_match = re.search(self.signal_patterns['stop_loss'], text, re.IGNORECASE)
            tp1_match = re.search(self.signal_patterns['tp1'], text, re.IGNORECASE)
            tp2_match = re.search(self.signal_patterns['tp2'], text, re.IGNORECASE)
            tp3_match = re.search(self.signal_patterns['tp3'], text, re.IGNORECASE)
            leverage_match = re.search(self.signal_patterns['leverage'], text, re.IGNORECASE)
            
            if not all([entry_match, sl_match, tp1_match]):
                return None  # Minimum required fields
            
            signal = {
                'message_id': message.get('message_id'),
                'symbol': symbol,
                'direction': direction,
                'entry_price': float(entry_match.group(1)),
                'stop_loss': float(sl_match.group(1)),
                'tp1': float(tp1_match.group(1)) if tp1_match else None,
                'tp2': float(tp2_match.group(1)) if tp2_match else None,
                'tp3': float(tp3_match.group(1)) if tp3_match else None,
                'leverage': int(leverage_match.group(1)) if leverage_match else 10,
                'timestamp': datetime.fromtimestamp(message.get('date', 0)),
                'text': text
            }
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error parsing signal message: {e}")
            return None
    
    def _parse_update_message(self, message: Dict, signals: Dict) -> Optional[Dict]:
        """Parse a message to extract trade updates/outcomes"""
        try:
            text = message.get('text', '')
            if not text:
                return None
            
            # Find which signal this update belongs to
            signal_id = self._find_related_signal(text, signals, message.get('date', 0))
            if not signal_id:
                return None
            
            update = {
                'signal_id': signal_id,
                'message_id': message.get('message_id'),
                'text': text,
                'timestamp': datetime.fromtimestamp(message.get('date', 0)),
                'type': 'update'
            }
            
            # Check for specific outcomes
            if re.search(self.outcome_patterns['tp1_hit'], text, re.IGNORECASE):
                update['type'] = 'tp1_hit'
            elif re.search(self.outcome_patterns['tp2_hit'], text, re.IGNORECASE):
                update['type'] = 'tp2_hit'
            elif re.search(self.outcome_patterns['tp3_hit'], text, re.IGNORECASE):
                update['type'] = 'tp3_hit'
            elif re.search(self.outcome_patterns['sl_hit'], text, re.IGNORECASE):
                update['type'] = 'sl_hit'
            elif re.search(self.outcome_patterns['closed'], text, re.IGNORECASE):
                update['type'] = 'closed'
            
            # Extract profit/loss percentage
            profit_match = re.search(self.outcome_patterns['profit'], text, re.IGNORECASE)
            loss_match = re.search(self.outcome_patterns['loss'], text, re.IGNORECASE)
            
            if profit_match:
                update['profit_percentage'] = float(profit_match.group(1))
            elif loss_match:
                update['profit_percentage'] = -float(loss_match.group(1))
            
            return update
            
        except Exception as e:
            self.logger.error(f"Error parsing update message: {e}")
            return None
    
    def _find_related_signal(self, text: str, signals: Dict, message_date: int) -> Optional[int]:
        """Find which signal an update message belongs to"""
        try:
            # Look for symbol mentions in the update text
            for signal_id, signal in signals.items():
                symbol = signal['symbol']
                
                # Check if symbol is mentioned in the update
                if symbol.replace('USDT', '') in text.upper() or symbol in text.upper():
                    # Check if update is within reasonable time frame (e.g., 24 hours)
                    signal_time = signal['timestamp'].timestamp()
                    if 0 <= message_date - signal_time <= 86400:  # 24 hours
                        return signal_id
            
            return None
            
        except Exception as e:
            return None
    
    def _create_trade_response(self, signal_data: Dict) -> Optional[TradeResponse]:
        """Create TradeResponse object from signal and updates"""
        try:
            updates = signal_data.get('updates', [])
            
            # Determine final outcome
            outcome = 'pending'
            profit_percentage = 0.0
            tp1_hit = False
            tp2_hit = False
            tp3_hit = False
            sl_hit = False
            
            for update in updates:
                if update['type'] == 'tp1_hit':
                    tp1_hit = True
                elif update['type'] == 'tp2_hit':
                    tp2_hit = True
                elif update['type'] == 'tp3_hit':
                    tp3_hit = True
                    outcome = 'profit'
                elif update['type'] == 'sl_hit':
                    sl_hit = True
                    outcome = 'loss'
                elif update['type'] == 'closed':
                    if tp1_hit or tp2_hit or tp3_hit:
                        outcome = 'profit'
                    else:
                        outcome = 'loss'
                
                # Update profit percentage if available
                if 'profit_percentage' in update:
                    profit_percentage = update['profit_percentage']
            
            # Calculate duration
            start_time = signal_data['timestamp']
            end_time = max([u['timestamp'] for u in updates]) if updates else start_time
            duration_minutes = int((end_time - start_time).total_seconds() / 60)
            
            trade_response = TradeResponse(
                message_id=signal_data['message_id'],
                signal_text=signal_data['text'],
                symbol=signal_data['symbol'],
                direction=signal_data['direction'],
                entry_price=signal_data['entry_price'],
                stop_loss=signal_data['stop_loss'],
                tp1=signal_data['tp1'],
                tp2=signal_data['tp2'],
                tp3=signal_data['tp3'],
                timestamp=signal_data['timestamp'],
                responses=[u['text'] for u in updates],
                outcome=outcome,
                profit_percentage=profit_percentage,
                duration_minutes=duration_minutes
            )
            
            return trade_response
            
        except Exception as e:
            self.logger.error(f"Error creating trade response: {e}")
            return None
    
    async def store_scanned_trades(self, trade_responses: List[TradeResponse]):
        """Store scanned trades in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for trade in trade_responses:
                cursor.execute('''
                    INSERT OR REPLACE INTO scanned_trades (
                        message_id, symbol, direction, entry_price, stop_loss,
                        tp1, tp2, tp3, signal_timestamp, outcome,
                        profit_percentage, duration_minutes,
                        tp1_hit, tp2_hit, tp3_hit, sl_hit,
                        responses_json, signal_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade.message_id,
                    trade.symbol,
                    trade.direction,
                    trade.entry_price,
                    trade.stop_loss,
                    trade.tp1,
                    trade.tp2,
                    trade.tp3,
                    trade.timestamp.isoformat(),
                    trade.outcome,
                    trade.profit_percentage,
                    trade.duration_minutes,
                    'tp1' in str(trade.responses).lower(),
                    'tp2' in str(trade.responses).lower(),
                    'tp3' in str(trade.responses).lower(),
                    'sl' in str(trade.responses).lower() or 'stop' in str(trade.responses).lower(),
                    json.dumps(trade.responses),
                    trade.signal_text
                ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"💾 Stored {len(trade_responses)} scanned trades")
            
        except Exception as e:
            self.logger.error(f"Error storing scanned trades: {e}")
    
    async def get_training_data(self) -> List[Dict[str, Any]]:
        """Get formatted training data for ML model"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM scanned_trades 
                WHERE outcome IN ('profit', 'loss')
                ORDER BY signal_timestamp DESC
            ''')
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            training_data = []
            for row in rows:
                trade_dict = dict(zip(columns, row))
                
                # Convert to ML training format
                training_sample = {
                    'symbol': trade_dict['symbol'],
                    'direction': trade_dict['direction'],
                    'entry_price': trade_dict['entry_price'],
                    'stop_loss': trade_dict['stop_loss'],
                    'tp1': trade_dict['tp1'],
                    'tp2': trade_dict['tp2'],
                    'tp3': trade_dict['tp3'],
                    'leverage': 10,  # Default if not available
                    'signal_strength': 85,  # Default signal strength
                    'outcome': trade_dict['outcome'],
                    'profit_loss': trade_dict['profit_percentage'],
                    'duration_minutes': trade_dict['duration_minutes'],
                    'tp1_hit': trade_dict['tp1_hit'],
                    'tp2_hit': trade_dict['tp2_hit'],
                    'tp3_hit': trade_dict['tp3_hit'],
                    'sl_hit': trade_dict['sl_hit'],
                    'timestamp': trade_dict['signal_timestamp']
                }
                
                training_data.append(training_sample)
            
            conn.close()
            
            self.logger.info(f"📚 Retrieved {len(training_data)} training samples")
            return training_data
            
        except Exception as e:
            self.logger.error(f"Error getting training data: {e}")
            return []
