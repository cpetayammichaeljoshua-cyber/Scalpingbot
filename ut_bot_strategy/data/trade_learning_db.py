"""
Trade Learning Database

Comprehensive SQLite database for tracking positions, outcomes, and AI learning data.
Supports async operations for integration with the trading engine.
"""

import os
import json
import logging
import aiosqlite
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeLearningDB:
    """
    Trade Learning Database for tracking positions, outcomes, and AI learning data.
    
    Tables:
    - trades: Store all trade entries and exits
    - ai_learnings: Store AI analysis and recommendations per trade
    - performance_metrics: Store periodic performance summaries
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize Trade Learning Database
        
        Args:
            db_path: Path to SQLite database file. Defaults to ut_bot_strategy/data/trade_learning.db
        """
        if db_path is None:
            db_dir = Path(__file__).parent
            db_path = str(db_dir / "trade_learning.db")
        
        self.db_path = db_path
        self._initialized = False
        logger.info(f"TradeLearningDB initialized with path: {self.db_path}")
    
    async def initialize(self) -> None:
        """Initialize database and create tables if they don't exist"""
        if self._initialized:
            return
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await self._create_trades_table(db)
                await self._create_ai_learnings_table(db)
                await self._create_performance_metrics_table(db)
                await self._create_indexes(db)
                await db.commit()
            
            self._initialized = True
            logger.info("Trade Learning Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def _create_trades_table(self, db: aiosqlite.Connection) -> None:
        """Create the trades table"""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                take_profit_3 REAL,
                leverage INTEGER DEFAULT 1,
                position_size REAL,
                margin_used REAL,
                signal_confidence REAL,
                ai_confidence REAL,
                signal_strength REAL,
                ut_bot_signal TEXT,
                stc_value REAL,
                stc_color TEXT,
                atr_value REAL,
                volatility_score REAL,
                entry_time TIMESTAMP,
                exit_time TIMESTAMP,
                exit_price REAL,
                exit_reason TEXT,
                profit_loss REAL,
                profit_percent REAL,
                outcome TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    async def _create_ai_learnings_table(self, db: aiosqlite.Connection) -> None:
        """Create the ai_learnings table"""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                ai_analysis TEXT,
                ai_recommendations TEXT,
                learning_insights TEXT,
                parameter_adjustments TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trade_id) REFERENCES trades (id)
            )
        """)
    
    async def _create_performance_metrics_table(self, db: aiosqlite.Connection) -> None:
        """Create the performance_metrics table"""
        await db.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                total_trades INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0.0,
                total_profit REAL DEFAULT 0.0,
                average_profit REAL DEFAULT 0.0,
                max_drawdown REAL DEFAULT 0.0,
                best_trade REAL DEFAULT 0.0,
                worst_trade REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    async def _create_indexes(self, db: aiosqlite.Connection) -> None:
        """Create database indexes for better query performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol)",
            "CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades (entry_time)",
            "CREATE INDEX IF NOT EXISTS idx_trades_outcome ON trades (outcome)",
            "CREATE INDEX IF NOT EXISTS idx_ai_learnings_trade_id ON ai_learnings (trade_id)",
            "CREATE INDEX IF NOT EXISTS idx_ai_learnings_timestamp ON ai_learnings (timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_performance_period ON performance_metrics (period_start, period_end)",
        ]
        
        for index_sql in indexes:
            await db.execute(index_sql)
    
    async def record_trade_entry(self, trade_data: Dict[str, Any]) -> int:
        """
        Record a new trade entry
        
        Args:
            trade_data: Dictionary containing trade details
            
        Returns:
            trade_id: The ID of the newly created trade record
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO trades (
                        symbol, direction, entry_price, stop_loss,
                        take_profit_1, take_profit_2, take_profit_3,
                        leverage, position_size, margin_used,
                        signal_confidence, ai_confidence, signal_strength,
                        ut_bot_signal, stc_value, stc_color, atr_value, volatility_score,
                        entry_time, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_data.get('symbol'),
                    trade_data.get('direction'),
                    trade_data.get('entry_price'),
                    trade_data.get('stop_loss'),
                    trade_data.get('take_profit_1'),
                    trade_data.get('take_profit_2'),
                    trade_data.get('take_profit_3'),
                    trade_data.get('leverage', 1),
                    trade_data.get('position_size'),
                    trade_data.get('margin_used'),
                    trade_data.get('signal_confidence'),
                    trade_data.get('ai_confidence'),
                    trade_data.get('signal_strength'),
                    trade_data.get('ut_bot_signal'),
                    trade_data.get('stc_value'),
                    trade_data.get('stc_color'),
                    trade_data.get('atr_value'),
                    trade_data.get('volatility_score'),
                    trade_data.get('entry_time', datetime.now().isoformat()),
                    datetime.now().isoformat()
                ))
                
                trade_id = cursor.lastrowid or 0
                await db.commit()
                
                logger.info(f"Recorded trade entry: ID={trade_id}, Symbol={trade_data.get('symbol')}, Direction={trade_data.get('direction')}")
                return trade_id
                
        except Exception as e:
            logger.error(f"Error recording trade entry: {e}")
            raise
    
    async def record_trade_exit(self, trade_id: int, exit_data: Dict[str, Any]) -> bool:
        """
        Record trade exit details
        
        Args:
            trade_id: ID of the trade to update
            exit_data: Dictionary containing exit details
            
        Returns:
            success: True if update was successful
        """
        await self.initialize()
        
        try:
            exit_price = exit_data.get('exit_price')
            exit_time = exit_data.get('exit_time', datetime.now().isoformat())
            exit_reason = exit_data.get('exit_reason')
            profit_loss = exit_data.get('profit_loss')
            profit_percent = exit_data.get('profit_percent')
            outcome = exit_data.get('outcome')
            
            if outcome is None and profit_loss is not None:
                if profit_loss > 0:
                    outcome = 'win'
                elif profit_loss < 0:
                    outcome = 'loss'
                else:
                    outcome = 'breakeven'
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE trades SET
                        exit_price = ?,
                        exit_time = ?,
                        exit_reason = ?,
                        profit_loss = ?,
                        profit_percent = ?,
                        outcome = ?
                    WHERE id = ?
                """, (
                    exit_price,
                    exit_time,
                    exit_reason,
                    profit_loss,
                    profit_percent,
                    outcome,
                    trade_id
                ))
                
                await db.commit()
                
                logger.info(f"Recorded trade exit: ID={trade_id}, Outcome={outcome}, P/L={profit_loss}")
                return True
                
        except Exception as e:
            logger.error(f"Error recording trade exit: {e}")
            raise
    
    async def get_recent_trades(self, limit: int = 50, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent trades
        
        Args:
            limit: Maximum number of trades to return
            symbol: Optional symbol filter
            
        Returns:
            List of trade dictionaries
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                if symbol:
                    query = """
                        SELECT * FROM trades 
                        WHERE symbol = ?
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    """
                    params = (symbol, limit)
                else:
                    query = """
                        SELECT * FROM trades 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    """
                    params = (limit,)
                
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    trades = [dict(row) for row in rows]
                    
                logger.debug(f"Retrieved {len(trades)} recent trades")
                return trades
                
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []
    
    async def get_trade_statistics(self, period_days: int = 30, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get trade performance statistics for a given period
        
        Args:
            period_days: Number of days to analyze
            symbol: Optional symbol filter
            
        Returns:
            Dictionary containing performance statistics
        """
        await self.initialize()
        
        try:
            cutoff_date = (datetime.now() - timedelta(days=period_days)).isoformat()
            
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                if symbol:
                    base_condition = "WHERE timestamp >= ? AND symbol = ?"
                    params = (cutoff_date, symbol)
                else:
                    base_condition = "WHERE timestamp >= ?"
                    params = (cutoff_date,)
                
                async with db.execute(f"""
                    SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END) as breakeven,
                        COALESCE(SUM(profit_loss), 0) as total_profit,
                        COALESCE(AVG(profit_loss), 0) as average_profit,
                        COALESCE(MAX(profit_loss), 0) as best_trade,
                        COALESCE(MIN(profit_loss), 0) as worst_trade,
                        COALESCE(AVG(profit_percent), 0) as average_profit_percent
                    FROM trades
                    {base_condition}
                """, params) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        stats = dict(row)
                        total = stats['total_trades']
                        wins = stats['wins'] or 0
                        
                        stats['win_rate'] = (wins / total * 100) if total > 0 else 0.0
                        stats['period_days'] = period_days
                        stats['period_start'] = cutoff_date
                        stats['period_end'] = datetime.now().isoformat()
                        
                        stats['max_drawdown'] = await self._calculate_max_drawdown(db, cutoff_date, symbol)
                        
                        return stats
                    
                    return {
                        'total_trades': 0,
                        'wins': 0,
                        'losses': 0,
                        'breakeven': 0,
                        'win_rate': 0.0,
                        'total_profit': 0.0,
                        'average_profit': 0.0,
                        'best_trade': 0.0,
                        'worst_trade': 0.0,
                        'max_drawdown': 0.0,
                        'period_days': period_days
                    }
                    
        except Exception as e:
            logger.error(f"Error getting trade statistics: {e}")
            return {}
    
    async def _calculate_max_drawdown(self, db: aiosqlite.Connection, cutoff_date: str, symbol: Optional[str] = None) -> float:
        """Calculate maximum drawdown for the period"""
        try:
            if symbol:
                query = """
                    SELECT profit_loss FROM trades 
                    WHERE timestamp >= ? AND symbol = ? AND profit_loss IS NOT NULL
                    ORDER BY timestamp
                """
                params = (cutoff_date, symbol)
            else:
                query = """
                    SELECT profit_loss FROM trades 
                    WHERE timestamp >= ? AND profit_loss IS NOT NULL
                    ORDER BY timestamp
                """
                params = (cutoff_date,)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            
            if not rows:
                return 0.0
            
            cumulative = 0.0
            peak = 0.0
            max_drawdown = 0.0
            
            for row in rows:
                pnl = row[0] or 0.0
                cumulative += pnl
                
                if cumulative > peak:
                    peak = cumulative
                
                drawdown = peak - cumulative
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            return max_drawdown
            
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0
    
    async def record_ai_learning(self, trade_id: int, learning_data: Dict[str, Any]) -> int:
        """
        Store AI learning insights for a trade
        
        Args:
            trade_id: ID of the associated trade
            learning_data: Dictionary containing AI analysis and insights
            
        Returns:
            learning_id: The ID of the newly created learning record
        """
        await self.initialize()
        
        try:
            ai_analysis = learning_data.get('ai_analysis')
            if isinstance(ai_analysis, dict):
                ai_analysis = json.dumps(ai_analysis)
            
            ai_recommendations = learning_data.get('ai_recommendations')
            if isinstance(ai_recommendations, (dict, list)):
                ai_recommendations = json.dumps(ai_recommendations)
            
            learning_insights = learning_data.get('learning_insights')
            if isinstance(learning_insights, (dict, list)):
                learning_insights = json.dumps(learning_insights)
            
            parameter_adjustments = learning_data.get('parameter_adjustments')
            if isinstance(parameter_adjustments, dict):
                parameter_adjustments = json.dumps(parameter_adjustments)
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO ai_learnings (
                        trade_id, ai_analysis, ai_recommendations,
                        learning_insights, parameter_adjustments, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    trade_id,
                    ai_analysis,
                    ai_recommendations,
                    learning_insights,
                    parameter_adjustments,
                    datetime.now().isoformat()
                ))
                
                learning_id = cursor.lastrowid or 0
                await db.commit()
                
                logger.info(f"Recorded AI learning: ID={learning_id}, Trade ID={trade_id}")
                return learning_id
                
        except Exception as e:
            logger.error(f"Error recording AI learning: {e}")
            raise
    
    async def get_learning_summary(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get aggregated learning data for AI analysis
        
        Args:
            limit: Maximum number of recent learnings to include
            
        Returns:
            Dictionary containing aggregated learning data
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute("""
                    SELECT 
                        al.id,
                        al.trade_id,
                        al.ai_analysis,
                        al.ai_recommendations,
                        al.learning_insights,
                        al.parameter_adjustments,
                        al.timestamp,
                        t.symbol,
                        t.direction,
                        t.outcome,
                        t.profit_loss,
                        t.profit_percent
                    FROM ai_learnings al
                    LEFT JOIN trades t ON al.trade_id = t.id
                    ORDER BY al.timestamp DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
                
                learnings = []
                for row in rows:
                    learning = dict(row)
                    
                    for field in ['ai_analysis', 'ai_recommendations', 'learning_insights', 'parameter_adjustments']:
                        if learning.get(field):
                            try:
                                learning[field] = json.loads(learning[field])
                            except (json.JSONDecodeError, TypeError):
                                pass
                    
                    learnings.append(learning)
                
                async with db.execute("""
                    SELECT 
                        COUNT(*) as total_learnings,
                        COUNT(DISTINCT trade_id) as trades_with_learnings
                    FROM ai_learnings
                """) as cursor:
                    summary_row = await cursor.fetchone()
                    summary_stats = dict(summary_row) if summary_row else {}
                
                async with db.execute("""
                    SELECT 
                        t.outcome,
                        COUNT(*) as count,
                        AVG(t.profit_percent) as avg_profit_percent
                    FROM ai_learnings al
                    JOIN trades t ON al.trade_id = t.id
                    WHERE t.outcome IS NOT NULL
                    GROUP BY t.outcome
                """) as cursor:
                    outcome_rows = await cursor.fetchall()
                    outcomes = {row[0]: {'count': row[1], 'avg_profit_percent': row[2]} for row in outcome_rows}
                
                return {
                    'learnings': learnings,
                    'total_learnings': summary_stats.get('total_learnings', 0),
                    'trades_with_learnings': summary_stats.get('trades_with_learnings', 0),
                    'outcomes_analysis': outcomes,
                    'generated_at': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting learning summary: {e}")
            return {'learnings': [], 'error': str(e)}
    
    async def save_performance_metrics(self, period_start: str, period_end: str, metrics: Dict[str, Any]) -> int:
        """
        Save performance metrics for a period
        
        Args:
            period_start: Start of the period (ISO format)
            period_end: End of the period (ISO format)
            metrics: Dictionary containing performance metrics
            
        Returns:
            metrics_id: The ID of the saved metrics record
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO performance_metrics (
                        period_start, period_end,
                        total_trades, wins, losses, win_rate,
                        total_profit, average_profit, max_drawdown,
                        best_trade, worst_trade, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    period_start,
                    period_end,
                    metrics.get('total_trades', 0),
                    metrics.get('wins', 0),
                    metrics.get('losses', 0),
                    metrics.get('win_rate', 0.0),
                    metrics.get('total_profit', 0.0),
                    metrics.get('average_profit', 0.0),
                    metrics.get('max_drawdown', 0.0),
                    metrics.get('best_trade', 0.0),
                    metrics.get('worst_trade', 0.0),
                    datetime.now().isoformat()
                ))
                
                metrics_id = cursor.lastrowid or 0
                await db.commit()
                
                logger.info(f"Saved performance metrics: ID={metrics_id}")
                return metrics_id
                
        except Exception as e:
            logger.error(f"Error saving performance metrics: {e}")
            raise
    
    async def get_performance_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Get historical performance metrics
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of performance metric dictionaries
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute("""
                    SELECT * FROM performance_metrics
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"Error getting performance history: {e}")
            return []
    
    async def get_trade_by_id(self, trade_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific trade by ID
        
        Args:
            trade_id: The trade ID
            
        Returns:
            Trade dictionary or None if not found
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute(
                    "SELECT * FROM trades WHERE id = ?", (trade_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
                    
        except Exception as e:
            logger.error(f"Error getting trade {trade_id}: {e}")
            return None
    
    async def get_open_trades(self) -> List[Dict[str, Any]]:
        """
        Get all trades that haven't been closed yet
        
        Returns:
            List of open trade dictionaries
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute("""
                    SELECT * FROM trades 
                    WHERE exit_time IS NULL
                    ORDER BY entry_time DESC
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []
    
    async def get_trades_by_symbol(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get trades for a specific symbol
        
        Args:
            symbol: Trading symbol
            limit: Maximum number of trades to return
            
        Returns:
            List of trade dictionaries
        """
        await self.initialize()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute("""
                    SELECT * FROM trades 
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (symbol, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"Error getting trades for {symbol}: {e}")
            return []
    
    async def health_check(self) -> bool:
        """
        Check database connectivity and health
        
        Returns:
            True if database is healthy
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("SELECT 1")
                return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close database connections (cleanup)"""
        self._initialized = False
        logger.info("TradeLearningDB closed")
