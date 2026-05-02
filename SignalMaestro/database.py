"""
Database management for trading bot
Handles storage of trades, signals, users, and portfolio data using SQLite
"""

import sqlite3
import aiosqlite
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from config import Config

class Database:
    """SQLite database manager for trading bot data"""
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.db_path = self.config.DATABASE_PATH
        
    async def initialize(self):
        """Initialize database tables"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Create users table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        is_admin BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        settings TEXT DEFAULT '{}'
                    )
                """)
                
                # Create signals table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        signal_data TEXT,
                        parsed_signal TEXT,
                        validation_result TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                """)
                
                # Create trades table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id INTEGER,
                        user_id INTEGER,
                        symbol TEXT,
                        side TEXT,
                        amount REAL,
                        price REAL,
                        order_id TEXT,
                        status TEXT,
                        pnl REAL DEFAULT 0,
                        fee REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        executed_at TIMESTAMP,
                        closed_at TIMESTAMP,
                        trade_data TEXT,
                        FOREIGN KEY (signal_id) REFERENCES signals (id),
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                """)
                
                # Create portfolio snapshots table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        total_value REAL,
                        balance_data TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                """)
                
                # Create cornix_logs table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS cornix_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id INTEGER,
                        payload TEXT,
                        response TEXT,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (signal_id) REFERENCES signals (id)
                    )
                """)
                
                # Create system_logs table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS system_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT,
                        message TEXT,
                        module TEXT,
                        user_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for better performance
                await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_user_id ON signals (user_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals (created_at)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades (user_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades (created_at)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_user_id ON portfolio_snapshots (user_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs (created_at)")
                
                await db.commit()
                
            self.logger.info("Database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def close(self):
        """Close database connections"""
        # SQLite connections are closed automatically with aiosqlite context manager
        pass
    
    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("SELECT 1")
                return True
        except Exception as e:
            self.logger.warning(f"Database health check failed: {e}")
            return False
    
    # User Management
    async def save_user(self, user_id: int, username: str, first_name: str = "", last_name: str = ""):
        """Save or update user information"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name, last_active)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, username, first_name, last_name))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error saving user {user_id}: {e}")
            raise
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        user = dict(row)
                        user['settings'] = json.loads(user.get('settings', '{}'))
                        return user
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    async def update_user_settings(self, user_id: int, settings: Dict[str, Any]):
        """Update user settings"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE users SET settings = ?, last_active = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                """, (json.dumps(settings), user_id))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error updating user settings for {user_id}: {e}")
            raise
    
    # Signal Management
    async def save_signal(self, user_id: int, signal_data: str, parsed_signal: Dict[str, Any], 
                         validation_result: Dict[str, Any]) -> int:
        """Save trading signal"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO signals (user_id, signal_data, parsed_signal, validation_result)
                    VALUES (?, ?, ?, ?)
                """, (user_id, signal_data, json.dumps(parsed_signal), json.dumps(validation_result)))
                
                signal_id = cursor.lastrowid
                await db.commit()
                return signal_id
                
        except Exception as e:
            self.logger.error(f"Error saving signal: {e}")
            raise
    
    async def update_signal_status(self, signal_id: int, status: str):
        """Update signal processing status"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE signals SET status = ?, processed_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (status, signal_id))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error updating signal status: {e}")
            raise
    
    async def get_signals(self, user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signals"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                if user_id:
                    query = """
                        SELECT * FROM signals WHERE user_id = ? 
                        ORDER BY created_at DESC LIMIT ?
                    """
                    params = (user_id, limit)
                else:
                    query = "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?"
                    params = (limit,)
                
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    signals = []
                    for row in rows:
                        signal = dict(row)
                        signal['parsed_signal'] = json.loads(signal.get('parsed_signal', '{}'))
                        signal['validation_result'] = json.loads(signal.get('validation_result', '{}'))
                        signals.append(signal)
                    return signals
                    
        except Exception as e:
            self.logger.error(f"Error getting signals: {e}")
            return []
    
    # Trade Management
    async def save_trade(self, signal_id: int, user_id: int, trade_data: Dict[str, Any]) -> int:
        """Save trade execution result"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO trades (signal_id, user_id, symbol, side, amount, price, 
                                      order_id, status, fee, trade_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_id,
                    user_id,
                    trade_data.get('symbol', ''),
                    trade_data.get('side', ''),
                    trade_data.get('amount', 0),
                    trade_data.get('price', 0),
                    trade_data.get('order_id', ''),
                    trade_data.get('status', 'pending'),
                    trade_data.get('fee', {}).get('cost', 0),
                    json.dumps(trade_data)
                ))
                
                trade_id = cursor.lastrowid
                await db.commit()
                return trade_id
                
        except Exception as e:
            self.logger.error(f"Error saving trade: {e}")
            raise
    
    async def update_trade(self, trade_id: int, updates: Dict[str, Any]):
        """Update trade information"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                set_clauses = []
                params = []
                
                for key, value in updates.items():
                    if key in ['status', 'pnl', 'executed_at', 'closed_at']:
                        set_clauses.append(f"{key} = ?")
                        params.append(value)
                
                if set_clauses:
                    query = f"UPDATE trades SET {', '.join(set_clauses)} WHERE id = ?"
                    params.append(trade_id)
                    await db.execute(query, params)
                    await db.commit()
                    
        except Exception as e:
            self.logger.error(f"Error updating trade {trade_id}: {e}")
            raise
    
    async def get_trades(self, user_id: Optional[int] = None, symbol: Optional[str] = None, 
                        limit: int = 50) -> List[Dict[str, Any]]:
        """Get trading history"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                query = "SELECT * FROM trades WHERE 1=1"
                params = []
                
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                
                if symbol:
                    query += " AND symbol = ?"
                    params.append(symbol)
                
                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    trades = []
                    for row in rows:
                        trade = dict(row)
                        trade['trade_data'] = json.loads(trade.get('trade_data', '{}'))
                        trades.append(trade)
                    return trades
                    
        except Exception as e:
            self.logger.error(f"Error getting trades: {e}")
            return []
    
    async def get_open_trades(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get open trades"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                query = "SELECT * FROM trades WHERE status IN ('open', 'pending')"
                params = []
                
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                
                query += " ORDER BY created_at DESC"
                
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    trades = []
                    for row in rows:
                        trade = dict(row)
                        trade['trade_data'] = json.loads(trade.get('trade_data', '{}'))
                        trades.append(trade)
                    return trades
                    
        except Exception as e:
            self.logger.error(f"Error getting open trades: {e}")
            return []
    
    # Portfolio Management
    async def update_portfolio_snapshot(self, balance_data: Dict[str, Any], user_id: int = 1):
        """Save portfolio snapshot"""
        try:
            total_value = sum(
                data.get('total', 0) for data in balance_data.values()
                if isinstance(data, dict)
            )
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO portfolio_snapshots (user_id, total_value, balance_data)
                    VALUES (?, ?, ?)
                """, (user_id, total_value, json.dumps(balance_data)))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error updating portfolio snapshot: {e}")
            raise
    
    async def get_portfolio_history(self, user_id: int = 1, days: int = 30) -> List[Dict[str, Any]]:
        """Get portfolio history"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM portfolio_snapshots 
                    WHERE user_id = ? AND created_at >= ?
                    ORDER BY created_at DESC
                """, (user_id, cutoff_date.isoformat())) as cursor:
                    rows = await cursor.fetchall()
                    snapshots = []
                    for row in rows:
                        snapshot = dict(row)
                        snapshot['balance_data'] = json.loads(snapshot.get('balance_data', '{}'))
                        snapshots.append(snapshot)
                    return snapshots
                    
        except Exception as e:
            self.logger.error(f"Error getting portfolio history: {e}")
            return []
    
    # Cornix Integration Logs
    async def save_cornix_log(self, signal_id: int, payload: Dict[str, Any], 
                             response: Dict[str, Any], status: str):
        """Save Cornix integration log"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO cornix_logs (signal_id, payload, response, status)
                    VALUES (?, ?, ?, ?)
                """, (signal_id, json.dumps(payload), json.dumps(response), status))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error saving Cornix log: {e}")
            raise
    
    # System Logs
    async def save_system_log(self, level: str, message: str, module: str, user_id: Optional[int] = None):
        """Save system log entry"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO system_logs (level, message, module, user_id)
                    VALUES (?, ?, ?, ?)
                """, (level, message, module, user_id))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error saving system log: {e}")
    
    # Analytics and Statistics
    async def get_trading_stats(self, user_id: Optional[int] = None, days: int = 30) -> Dict[str, Any]:
        """Get trading statistics"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with aiosqlite.connect(self.db_path) as db:
                query = """
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                        SUM(pnl) as total_pnl,
                        AVG(pnl) as avg_pnl,
                        MAX(pnl) as max_win,
                        MIN(pnl) as max_loss,
                        SUM(fee) as total_fees
                    FROM trades 
                    WHERE created_at >= ?
                """
                params = [cutoff_date.isoformat()]
                
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                
                async with db.execute(query, params) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        total_trades = row[0] or 0
                        winning_trades = row[1] or 0
                        
                        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                        
                        return {
                            'total_trades': total_trades,
                            'winning_trades': winning_trades,
                            'losing_trades': row[2] or 0,
                            'win_rate': round(win_rate, 2),
                            'total_pnl': row[4] or 0,
                            'avg_pnl': row[5] or 0,
                            'max_win': row[6] or 0,
                            'max_loss': row[7] or 0,
                            'total_fees': row[8] or 0
                        }
                    
                return {}
                
        except Exception as e:
            self.logger.error(f"Error getting trading stats: {e}")
            return {}
    
    async def cleanup_old_data(self, cutoff_timestamp: float):
        """Clean up old data from database"""
        try:
            cutoff_date = datetime.fromtimestamp(cutoff_timestamp)
            
            async with aiosqlite.connect(self.db_path) as db:
                # Clean old system logs
                await db.execute(
                    "DELETE FROM system_logs WHERE created_at < ?",
                    (cutoff_date.isoformat(),)
                )
                
                # Clean old portfolio snapshots (keep daily snapshots)
                await db.execute("""
                    DELETE FROM portfolio_snapshots 
                    WHERE created_at < ? AND id NOT IN (
                        SELECT MIN(id) FROM portfolio_snapshots 
                        WHERE created_at < ?
                        GROUP BY DATE(created_at)
                    )
                """, (cutoff_date.isoformat(), cutoff_date.isoformat()))
                
                # Clean old Cornix logs
                await db.execute(
                    "DELETE FROM cornix_logs WHERE created_at < ?",
                    (cutoff_date.isoformat(),)
                )
                
                await db.commit()
                
            self.logger.info(f"Cleaned up data older than {cutoff_date}")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old data: {e}")
            raise
#!/usr/bin/env python3
"""
Database Module for Trading Bot
"""

import asyncio
import logging
import sqlite3
from typing import Dict, Any, List, Optional

class Database:
    """Database interface for trading bot"""
    
    def __init__(self, db_path: str = "trading_bot.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        
    async def initialize(self):
        """Initialize database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    signal_strength REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("Database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Database initialization error: {e}")
    
    async def test_connection(self) -> bool:
        """Test database connection"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            return True
        except:
            return False
    
    async def insert_trade(self, trade_data: Dict[str, Any]) -> Optional[int]:
        """Insert new trade record"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades (symbol, direction, entry_price, stop_loss, 
                                  take_profit_1, take_profit_2, take_profit_3, signal_strength)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data['symbol'],
                trade_data['direction'],
                trade_data['entry_price'],
                trade_data['stop_loss'],
                trade_data.get('take_profit_1'),
                trade_data.get('take_profit_2'),
                trade_data.get('take_profit_3'),
                trade_data.get('signal_strength')
            ))
            
            trade_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return trade_id
            
        except Exception as e:
            self.logger.error(f"Error inserting trade: {e}")
            return None
            
    def save_signal_data(self, data: Dict[str, Any]) -> Optional[int]:
        """Save signal data to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO signals (signal_data, parsed_signal, status)
                VALUES (?, ?, ?)
            ''', (
                json.dumps(data),
                json.dumps(data.get('parsed_signal', {})),
                data.get('status', 'processed')
            ))
            
            signal_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return signal_id
            
        except Exception as e:
            self.logger.error(f"Error saving signal data: {e}")
            return None
