
#!/usr/bin/env python3
"""
Machine Learning Trade Analyzer
Learns from losses and analyzes past trades to improve scalping performance
"""

import os
import numpy as np
import pandas as pd
import json
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import sqlite3
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
import warnings
warnings.filterwarnings('ignore')

class MLTradeAnalyzer:
    """Machine Learning analyzer for trade performance improvement"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.model_dir = Path("SignalMaestro/ml_models")
        self.model_dir.mkdir(exist_ok=True)
        
        # Models for different aspects
        self.loss_prediction_model = None
        self.signal_strength_model = None
        self.entry_timing_model = None
        self.scaler = StandardScaler()
        
        # Persistent encoders
        self.direction_encoder = LabelEncoder()
        self.cvd_encoder = LabelEncoder()
        self.macd_encoder = LabelEncoder()
        self.feature_names = None
        
        # Trade database
        self.db_path = "SignalMaestro/trade_learning.db"
        self._initialize_database()
        
        # Learning parameters
        self.min_trades_for_learning = 10
        self.feature_importance_threshold = 0.01
        
        # Model performance tracking
        self.model_performance = {
            'loss_prediction_accuracy': 0.0,
            'signal_strength_accuracy': 0.0,
            'entry_timing_accuracy': 0.0,
            'last_training_time': None,
            'trades_analyzed': 0
        }
        
        # Try to load existing models if available
        try:
            self._load_models()
        except Exception as e:
            self.logger.info(f"No pre-trained models found: {e}")
        
        self.logger.info("🧠 ML Trade Analyzer initialized")
    
    def load_models(self):
        """Public method to load trained models from disk"""
        try:
            self._load_models()
            self.logger.info("✅ ML models loaded successfully")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not load ML models: {e}")
    
    def _initialize_database(self):
        """Initialize SQLite database for trade storage"""
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
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    signal_strength REAL,
                    leverage INTEGER,
                    position_size REAL,
                    trade_result TEXT,
                    profit_loss REAL,
                    duration_minutes REAL,
                    entry_time TIMESTAMP,
                    exit_time TIMESTAMP,
                    market_conditions TEXT,
                    indicators_data TEXT,
                    cvd_trend TEXT,
                    volatility REAL,
                    volume_ratio REAL,
                    ema_alignment BOOLEAN,
                    rsi_value REAL,
                    macd_signal TEXT,
                    lessons_learned TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create learning insights table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight_type TEXT NOT NULL,
                    pattern_description TEXT,
                    success_rate REAL,
                    recommendation TEXT,
                    confidence_score REAL,
                    trades_analyzed INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("📊 Trade learning database initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
    
    async def record_trade(self, trade_data: Dict[str, Any]):
        """Record a trade for machine learning analysis"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades (
                    symbol, direction, entry_price, exit_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3, signal_strength,
                    leverage, position_size, trade_result, profit_loss,
                    duration_minutes, entry_time, exit_time, market_conditions,
                    indicators_data, cvd_trend, volatility, volume_ratio,
                    ema_alignment, rsi_value, macd_signal, lessons_learned
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data.get('symbol'),
                trade_data.get('direction'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                trade_data.get('stop_loss'),
                trade_data.get('take_profit_1'),
                trade_data.get('take_profit_2'),
                trade_data.get('take_profit_3'),
                trade_data.get('signal_strength'),
                trade_data.get('leverage'),
                trade_data.get('position_size'),
                trade_data.get('trade_result'),
                trade_data.get('profit_loss'),
                trade_data.get('duration_minutes'),
                trade_data.get('entry_time'),
                trade_data.get('exit_time'),
                json.dumps(trade_data.get('market_conditions', {})),
                json.dumps(trade_data.get('indicators_data', {})),
                trade_data.get('cvd_trend'),
                trade_data.get('volatility'),
                trade_data.get('volume_ratio'),
                trade_data.get('ema_alignment'),
                trade_data.get('rsi_value'),
                trade_data.get('macd_signal'),
                trade_data.get('lessons_learned')
            ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"📝 Trade recorded for ML analysis: {trade_data.get('symbol')} {trade_data.get('trade_result')}")
            
            # Trigger learning if we have enough data
            if self._get_trade_count() >= self.min_trades_for_learning:
                await self.analyze_and_learn()
                
        except Exception as e:
            self.logger.error(f"Error recording trade: {e}")
    
    def _get_trade_count(self) -> int:
        """Get total number of recorded trades"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM trades")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            self.logger.error(f"Error getting trade count: {e}")
            return 0
    
    async def analyze_and_learn(self, include_telegram_data: bool = True):
        """Main learning function that analyzes trades and updates models"""
        try:
            self.logger.info("🧠 Starting ML analysis and learning process...")
            
            # Get trade data from database
            trades_df = self._get_trades_dataframe()
            
            # Integrate Telegram channel data if available
            if include_telegram_data:
                telegram_data = await self._get_telegram_training_data()
                if len(telegram_data) > 0:
                    telegram_df = pd.DataFrame(telegram_data)
                    trades_df = pd.concat([trades_df, telegram_df], ignore_index=True)
                    self.logger.info(f"📨 Integrated {len(telegram_data)} Telegram trades")
            
            if len(trades_df) < self.min_trades_for_learning:
                self.logger.warning(f"Not enough trades for learning: {len(trades_df)}")
                return
            
            # 1. Learn from losses
            loss_insights = await self._analyze_losses(trades_df)
            
            # 2. Analyze successful patterns
            success_patterns = await self._analyze_successful_patterns(trades_df)
            
            # 3. Train prediction models
            await self._train_prediction_models(trades_df)
            
            # 4. Generate trading insights
            insights = await self._generate_trading_insights(trades_df)
            
            # 5. Update model performance metrics
            self._update_performance_metrics(trades_df)
            
            # 6. Store insights
            await self._store_insights(loss_insights + success_patterns + insights)
            
            self.logger.info(f"✅ ML analysis complete. Analyzed {len(trades_df)} trades")
            
        except Exception as e:
            self.logger.error(f"Error in ML analysis: {e}")
    
    async def _get_telegram_training_data(self) -> List[Dict[str, Any]]:
        """Get training data from Telegram scanner"""
        try:
            try:
                # Import here to avoid circular imports
                from telegram_trade_scanner import TelegramTradeScanner
                
                # Initialize scanner (you'll need to configure these)
                bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                channel_username = os.getenv('TELEGRAM_CHANNEL', '@SignalTactics')
            except ImportError:
                self.logger.warning("Telegram scanner not available")
                return []
            
            if not bot_token:
                self.logger.warning("No Telegram bot token configured")
                return []
            
            scanner = TelegramTradeScanner(bot_token, channel_username)
            
            # Get training data from scanner
            training_data = await scanner.get_training_data()
            
            # Convert to format compatible with ML analyzer
            formatted_data = []
            for trade in training_data:
                formatted_trade = {
                    'symbol': trade['symbol'],
                    'direction': trade['direction'],
                    'entry_price': trade['entry_price'],
                    'exit_price': trade['entry_price'] * (1 + trade['profit_loss']/100) if trade['profit_loss'] else trade['entry_price'],
                    'stop_loss': trade['stop_loss'],
                    'take_profit_1': trade['tp1'],
                    'take_profit_2': trade['tp2'],
                    'take_profit_3': trade['tp3'],
                    'signal_strength': trade.get('signal_strength', 85),
                    'leverage': trade.get('leverage', 10),
                    'position_size': 100,  # Default position size
                    'trade_result': 'PROFIT' if trade['outcome'] == 'profit' else 'LOSS',
                    'profit_loss': trade['profit_loss'],
                    'duration_minutes': trade['duration_minutes'],
                    'entry_time': trade['timestamp'],
                    'exit_time': trade['timestamp'],  # Simplified
                    'market_conditions': {
                        'source': 'telegram_channel',
                        'tp1_hit': trade['tp1_hit'],
                        'tp2_hit': trade['tp2_hit'],
                        'tp3_hit': trade['tp3_hit'],
                        'sl_hit': trade['sl_hit']
                    },
                    'indicators_data': {},
                    'cvd_trend': 'neutral',
                    'volatility': 0.02,
                    'volume_ratio': 1.0,
                    'ema_alignment': True,
                    'rsi_value': 50.0,
                    'macd_signal': 'neutral',
                    'lessons_learned': f"Telegram channel trade: {trade['outcome']}"
                }
                formatted_data.append(formatted_trade)
            
            return formatted_data
            
        except Exception as e:
            self.logger.error(f"Error getting Telegram training data: {e}")
            return []
    
    def _get_trades_dataframe(self) -> pd.DataFrame:
        """Get trades data as pandas DataFrame"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = "SELECT * FROM trades ORDER BY created_at DESC LIMIT 1000"
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            # Parse JSON fields
            if 'market_conditions' in df.columns:
                df['market_conditions'] = df['market_conditions'].apply(
                    lambda x: json.loads(x) if x else {}
                )
            if 'indicators_data' in df.columns:
                df['indicators_data'] = df['indicators_data'].apply(
                    lambda x: json.loads(x) if x else {}
                )
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error getting trades DataFrame: {e}")
            return pd.DataFrame()
    
    async def _analyze_losses(self, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Analyze losing trades to identify patterns and lessons"""
        try:
            loss_insights = []
            
            # Filter losing trades
            losing_trades = trades_df[trades_df['trade_result'].isin(['LOSS', 'STOP_LOSS'])]
            
            if len(losing_trades) == 0:
                return []
            
            # Analyze loss patterns by symbol
            symbol_losses = losing_trades.groupby('symbol').agg({
                'profit_loss': ['count', 'mean'],
                'signal_strength': 'mean',
                'volatility': 'mean'
            }).round(2)
            
            for symbol in symbol_losses.index:
                loss_count = symbol_losses.loc[symbol, ('profit_loss', 'count')]
                avg_loss = symbol_losses.loc[symbol, ('profit_loss', 'mean')]
                avg_signal_strength = symbol_losses.loc[symbol, ('signal_strength', 'mean')]
                
                if loss_count >= 3:  # Pattern detection threshold
                    insight = {
                        'type': 'loss_pattern',
                        'symbol': symbol,
                        'pattern': f"High loss frequency on {symbol}",
                        'recommendation': f"Reduce position size or avoid {symbol} temporarily",
                        'confidence': min(loss_count / 10 * 100, 95),
                        'data': {
                            'loss_count': loss_count,
                            'avg_loss': avg_loss,
                            'avg_signal_strength': avg_signal_strength
                        }
                    }
                    loss_insights.append(insight)
            
            # Analyze loss patterns by market conditions
            condition_losses = {}
            for _, trade in losing_trades.iterrows():
                conditions = trade.get('market_conditions', {})
                if isinstance(conditions, dict):
                    for condition, value in conditions.items():
                        if condition not in condition_losses:
                            condition_losses[condition] = []
                        condition_losses[condition].append(value)
            
            # Analyze signal strength vs losses
            if len(losing_trades) >= 5:
                low_strength_losses = losing_trades[losing_trades['signal_strength'] < 85]
                if len(low_strength_losses) > len(losing_trades) * 0.6:
                    insight = {
                        'type': 'signal_strength_lesson',
                        'pattern': "Majority of losses from signals < 85% strength",
                        'recommendation': "Increase minimum signal strength to 90%",
                        'confidence': 85,
                        'data': {
                            'low_strength_loss_ratio': len(low_strength_losses) / len(losing_trades),
                            'avg_loss_signal_strength': losing_trades['signal_strength'].mean()
                        }
                    }
                    loss_insights.append(insight)
            
            # CVD divergence analysis
            cvd_losses = losing_trades[losing_trades['cvd_trend'].notnull()]
            if len(cvd_losses) >= 3:
                bearish_cvd_losses = cvd_losses[cvd_losses['cvd_trend'] == 'bearish']
                if len(bearish_cvd_losses) > len(cvd_losses) * 0.7:
                    insight = {
                        'type': 'cvd_lesson',
                        'pattern': "High loss rate during bearish CVD trend",
                        'recommendation': "Avoid long positions during bearish CVD",
                        'confidence': 80,
                        'data': {
                            'bearish_cvd_loss_ratio': len(bearish_cvd_losses) / len(cvd_losses)
                        }
                    }
                    loss_insights.append(insight)
            
            return loss_insights
            
        except Exception as e:
            self.logger.error(f"Error analyzing losses: {e}")
            return []
    
    async def _analyze_successful_patterns(self, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Analyze successful trades to identify winning patterns"""
        try:
            success_insights = []
            
            # Filter successful trades
            winning_trades = trades_df[trades_df['trade_result'].isin(['PROFIT', 'TP1', 'TP2', 'TP3'])]
            
            if len(winning_trades) == 0:
                return []
            
            # Analyze winning patterns by signal strength
            high_strength_wins = winning_trades[winning_trades['signal_strength'] >= 90]
            if len(high_strength_wins) > 0:
                win_rate = len(high_strength_wins) / len(winning_trades)
                if win_rate > 0.7:
                    insight = {
                        'type': 'success_pattern',
                        'pattern': "High win rate with signal strength >= 90%",
                        'recommendation': "Prioritize signals with 90%+ strength",
                        'confidence': min(win_rate * 100, 95),
                        'data': {
                            'high_strength_win_rate': win_rate,
                            'avg_profit': high_strength_wins['profit_loss'].mean()
                        }
                    }
                    success_insights.append(insight)
            
            # Analyze by leverage patterns
            leverage_analysis = winning_trades.groupby('leverage').agg({
                'profit_loss': ['count', 'mean', 'std']
            }).round(2)
            
            best_leverage = None
            best_performance = 0
            
            for leverage in leverage_analysis.index:
                count = leverage_analysis.loc[leverage, ('profit_loss', 'count')]
                avg_profit = leverage_analysis.loc[leverage, ('profit_loss', 'mean')]
                
                if count >= 3 and avg_profit > best_performance:
                    best_performance = avg_profit
                    best_leverage = leverage
            
            if best_leverage:
                insight = {
                    'type': 'leverage_optimization',
                    'pattern': f"Best performance with {best_leverage}x leverage",
                    'recommendation': f"Consider using {best_leverage}x leverage more frequently",
                    'confidence': 75,
                    'data': {
                        'optimal_leverage': best_leverage,
                        'avg_profit': best_performance
                    }
                }
                success_insights.append(insight)
            
            # Analyze timeframe patterns
            duration_wins = winning_trades[winning_trades['duration_minutes'].notnull()]
            if len(duration_wins) >= 5:
                quick_wins = duration_wins[duration_wins['duration_minutes'] <= 30]
                if len(quick_wins) > len(duration_wins) * 0.6:
                    insight = {
                        'type': 'timing_pattern',
                        'pattern': "Majority of wins occur within 30 minutes",
                        'recommendation': "Focus on quick scalping entries/exits",
                        'confidence': 80,
                        'data': {
                            'quick_win_ratio': len(quick_wins) / len(duration_wins),
                            'avg_quick_profit': quick_wins['profit_loss'].mean()
                        }
                    }
                    success_insights.append(insight)
            
            return success_insights
            
        except Exception as e:
            self.logger.error(f"Error analyzing successful patterns: {e}")
            return []
    
    async def _train_prediction_models(self, trades_df: pd.DataFrame):
        """Train ML models for trade prediction"""
        try:
            if len(trades_df) < 20:
                self.logger.warning("Not enough data for model training")
                return
            
            # Prepare features with encoder fitting
            features = self._prepare_features(trades_df, fit_encoders=True)
            
            if features is None or len(features) == 0:
                return
            
            # Train loss prediction model
            await self._train_loss_prediction_model(features, trades_df)
            
            # Train signal strength optimization model
            await self._train_signal_strength_model(features, trades_df)
            
            # Train entry timing model
            await self._train_entry_timing_model(features, trades_df)
            
            # Save models and encoders
            self._save_models()
            
            self.logger.info("🤖 ML models trained and saved")
            
        except Exception as e:
            self.logger.error(f"Error training prediction models: {e}")
    
    def _prepare_features(self, trades_df: pd.DataFrame, fit_encoders: bool = False) -> Optional[pd.DataFrame]:
        """Prepare features for ML models with persistent encoders"""
        try:
            # Define consistent feature columns
            feature_columns = [
                'signal_strength', 'leverage', 'volatility', 'volume_ratio', 'rsi_value',
                'direction_encoded', 'cvd_trend_encoded', 'macd_signal_encoded', 
                'ema_alignment', 'hour', 'day_of_week'
            ]
            
            features = pd.DataFrame()
            
            # Basic features with safe defaults
            features['signal_strength'] = trades_df['signal_strength'].fillna(85)
            features['leverage'] = trades_df['leverage'].fillna(35)
            features['volatility'] = trades_df['volatility'].fillna(0.02)
            features['volume_ratio'] = trades_df['volume_ratio'].fillna(1.0)
            features['rsi_value'] = trades_df['rsi_value'].fillna(50)
            
            # Encode categorical features with persistent encoders
            try:
                direction_values = trades_df['direction'].fillna('BUY').astype(str)
                cvd_values = trades_df['cvd_trend'].fillna('neutral').astype(str)
                macd_values = trades_df['macd_signal'].fillna('neutral').astype(str)
                
                if fit_encoders:
                    # Fit encoders during training
                    features['direction_encoded'] = self.direction_encoder.fit_transform(direction_values)
                    features['cvd_trend_encoded'] = self.cvd_encoder.fit_transform(cvd_values)
                    features['macd_signal_encoded'] = self.macd_encoder.fit_transform(macd_values)
                else:
                    # Use existing encoders for prediction
                    features['direction_encoded'] = self._safe_transform(self.direction_encoder, pd.Series(direction_values), 1)
                    features['cvd_trend_encoded'] = self._safe_transform(self.cvd_encoder, pd.Series(cvd_values), 0)
                    features['macd_signal_encoded'] = self._safe_transform(self.macd_encoder, pd.Series(macd_values), 0)
                    
            except Exception as e:
                self.logger.warning(f"Label encoding error: {e}")
                features['direction_encoded'] = 1
                features['cvd_trend_encoded'] = 0
                features['macd_signal_encoded'] = 0
                
            features['ema_alignment'] = trades_df['ema_alignment'].fillna(False).astype(int)
            
            # Time-based features with safer extraction
            try:
                if 'entry_time' in trades_df.columns:
                    entry_times = pd.to_datetime(trades_df['entry_time'], errors='coerce')
                    features['hour'] = entry_times.dt.hour.fillna(datetime.now().hour)
                    features['day_of_week'] = entry_times.dt.dayofweek.fillna(datetime.now().weekday())
                else:
                    features['hour'] = datetime.now().hour
                    features['day_of_week'] = datetime.now().weekday()
            except Exception as e:
                self.logger.warning(f"Time feature extraction error: {e}")
                features['hour'] = datetime.now().hour
                features['day_of_week'] = datetime.now().weekday()
            
            # Ensure consistent column order
            features = features[feature_columns]
            
            # Remove rows with too many NaN values
            features = features.fillna(0)
            
            # Store feature names for consistent usage
            self.feature_names = feature_columns
            
            return features
            
        except Exception as e:
            self.logger.error(f"Error preparing features: {e}")
            return None
    
    def _safe_transform(self, encoder: LabelEncoder, values: pd.Series, default_value: int) -> pd.Series:
        """Safely transform values with fallback for unknown categories"""
        try:
            # Handle unknown categories by using default or first known category
            transformed = []
            for value in values:
                try:
                    if hasattr(encoder, 'classes_') and value in encoder.classes_:
                        transformed.append(encoder.transform([value])[0])
                    else:
                        transformed.append(default_value)
                except:
                    transformed.append(default_value)
            return pd.Series(transformed, index=values.index)
        except Exception:
            return pd.Series([default_value] * len(values), index=values.index)
    
    async def _train_loss_prediction_model(self, features: pd.DataFrame, trades_df: pd.DataFrame):
        """Train model to predict likely losses"""
        try:
            # Create binary target (1 = loss, 0 = profit)
            target = (trades_df['trade_result'].isin(['LOSS', 'STOP_LOSS'])).astype(int)
            
            # Align features and target
            common_indices = features.index.intersection(target.index)
            X = features.loc[common_indices]
            y = target.loc[common_indices]
            
            if len(X) < 10:
                return
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
            
            # Scale features for consistency (tree models don't strictly need it)
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            self.loss_prediction_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
            self.loss_prediction_model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred = self.loss_prediction_model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            self.model_performance['loss_prediction_accuracy'] = accuracy
            self.logger.info(f"🎯 Loss prediction model accuracy: {accuracy:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error training loss prediction model: {e}")
    
    async def _train_signal_strength_model(self, features: pd.DataFrame, trades_df: pd.DataFrame):
        """Train model to optimize signal strength thresholds"""
        try:
            # Create target based on profitability
            target = trades_df['profit_loss'].fillna(0)
            
            # Align features and target
            common_indices = features.index.intersection(target.index)
            X = features.loc[common_indices]
            y = target.loc[common_indices]
            
            if len(X) < 10:
                return
            
            # Convert to classification problem (profitable vs not)
            y_binary = (y > 0).astype(int)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y_binary, test_size=0.3, random_state=42)
            
            # Scale features for gradient boosting
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            self.signal_strength_model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                random_state=42
            )
            self.signal_strength_model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred = self.signal_strength_model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            self.model_performance['signal_strength_accuracy'] = accuracy
            self.logger.info(f"📊 Signal strength model accuracy: {accuracy:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error training signal strength model: {e}")
    
    async def _train_entry_timing_model(self, features: pd.DataFrame, trades_df: pd.DataFrame):
        """Train model for optimal entry timing"""
        try:
            # Create target based on quick profits
            duration = trades_df['duration_minutes'].fillna(60)
            profit = trades_df['profit_loss'].fillna(0)
            
            # Good timing = profitable within 30 minutes
            target = ((duration <= 30) & (profit > 0)).astype(int)
            
            # Align features and target
            common_indices = features.index.intersection(target.index)
            X = features.loc[common_indices]
            y = target.loc[common_indices]
            
            if len(X) < 10 or y.sum() < 3:  # Need at least 3 positive examples
                return
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
            
            # Scale features for timing model
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            self.entry_timing_model = RandomForestClassifier(
                n_estimators=50,
                max_depth=8,
                random_state=42
            )
            self.entry_timing_model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred = self.entry_timing_model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            self.model_performance['entry_timing_accuracy'] = accuracy
            self.logger.info(f"⏰ Entry timing model accuracy: {accuracy:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error training entry timing model: {e}")
    
    async def _generate_trading_insights_advanced(self, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate advanced trading insights from data analysis"""
        try:
            insights = []
            
            if len(trades_df) < 5:
                return insights
                
            # Time-based performance analysis
            trades_df['hour'] = pd.to_datetime(trades_df['entry_time'], errors='coerce').dt.hour
            hourly_performance = trades_df.groupby('hour').agg({
                'profit_loss': ['mean', 'count'],
                'trade_result': lambda x: (x.isin(['PROFIT', 'TP1', 'TP2', 'TP3'])).mean()
            }).round(3)
            
            # Find best performing hours
            if len(hourly_performance) > 0:
                best_hours = hourly_performance[hourly_performance[('profit_loss', 'count')] >= 2]
                if len(best_hours) > 0:
                    profit_means = best_hours[('profit_loss', 'mean')]
                    top_hour_idx = profit_means.idxmax() if len(profit_means) > 0 else 0
                    if len(profit_means) > 0 and hourly_performance.loc[top_hour_idx, ('profit_loss', 'mean')] > 0:
                        insights.append({
                            'type': 'time_optimization',
                            'pattern': f'Best performance at hour {top_hour_idx}:00 UTC',
                            'recommendation': f'Focus trading around {int(top_hour_idx)}:00-{int(top_hour_idx)+1}:00 UTC',
                            'confidence': 75,
                            'data': {
                                'hour': top_hour_idx,
                                'avg_profit': float(hourly_performance.loc[top_hour_idx, ('profit_loss', 'mean')]),
                                'trade_count': int(hourly_performance.loc[top_hour_idx, ('profit_loss', 'count')])
                            }
                        })
            
            # Volume ratio insights
            volume_trades = trades_df[trades_df['volume_ratio'].notnull()]
            if len(volume_trades) >= 10:
                high_volume_trades = volume_trades[volume_trades['volume_ratio'] > 1.5]
                if len(high_volume_trades) > 0:
                    hv_win_rate = len(high_volume_trades[high_volume_trades['profit_loss'] > 0]) / len(high_volume_trades)
                    if hv_win_rate > 0.7:
                        insights.append({
                            'type': 'volume_insight',
                            'pattern': 'High volume ratio correlates with success',
                            'recommendation': 'Prioritize trades with volume ratio > 1.5x',
                            'confidence': 80,
                            'data': {
                                'high_volume_win_rate': float(hv_win_rate),
                                'sample_size': len(high_volume_trades)
                            }
                        })
            
            return insights
            
        except Exception as e:
            self.logger.error(f"Error generating trading insights: {e}")
            return []
    
    def _load_models_legacy(self):
        """Load trained models from disk"""
        try:
            model_files = {
                'loss_prediction_model.pkl': 'loss_prediction_model',
                'signal_strength_model.pkl': 'signal_strength_model', 
                'entry_timing_model.pkl': 'entry_timing_model',
                # Skip scaler.pkl as it's no longer used
            }
            
            for filename, attr_name in model_files.items():
                filepath = self.model_dir / filename
                if filepath.exists() and attr_name != 'scaler':
                    with open(filepath, 'rb') as f:
                        setattr(self, attr_name, pickle.load(f))
            
            # Load performance metrics
            metrics_file = self.model_dir / 'performance_metrics.json'
            if metrics_file.exists():
                with open(metrics_file, 'r') as f:
                    self.model_performance.update(json.load(f))
            
            self.logger.info("🤖 ML models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading models: {e}")
    
    async def _generate_trading_insights(self, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate actionable trading insights"""
        try:
            insights = []
            
            # Overall performance analysis
            total_trades = len(trades_df)
            winning_trades = len(trades_df[trades_df['profit_loss'] > 0])
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            if win_rate < 0.6:
                insights.append({
                    'type': 'performance_warning',
                    'pattern': f"Win rate below 60% ({win_rate:.1%})",
                    'recommendation': "Review signal criteria and risk management",
                    'confidence': 90,
                    'data': {'current_win_rate': win_rate}
                })
            
            # Best performing symbols
            if total_trades >= 10:
                symbol_performance = trades_df.groupby('symbol')['profit_loss'].agg(['count', 'mean', 'sum'])
                symbol_performance = symbol_performance[symbol_performance['count'] >= 3]
                
                if len(symbol_performance) > 0:
                    best_symbol = symbol_performance['mean'].idxmax()
                    best_performance = symbol_performance.loc[best_symbol, 'mean']
                    
                    insights.append({
                        'type': 'symbol_recommendation',
                        'pattern': f"Best performing symbol: {best_symbol}",
                        'recommendation': f"Consider increasing allocation to {best_symbol}",
                        'confidence': 75,
                        'data': {
                            'symbol': best_symbol,
                            'avg_profit': best_performance,
                            'trade_count': symbol_performance.loc[best_symbol, 'count']
                        }
                    })
            
            return insights
            
        except Exception as e:
            self.logger.error(f"Error generating trading insights: {e}")
            return []
    
    def _update_performance_metrics(self, trades_df: pd.DataFrame):
        """Update model performance tracking"""
        try:
            self.model_performance['last_training_time'] = datetime.now().isoformat()
            self.model_performance['trades_analyzed'] = len(trades_df)
            
        except Exception as e:
            self.logger.error(f"Error updating performance metrics: {e}")
    
    async def _store_insights(self, insights: List[Dict[str, Any]]):
        """Store insights in database"""
        try:
            if not insights:
                return
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for insight in insights:
                cursor.execute('''
                    INSERT INTO learning_insights (
                        insight_type, pattern_description, success_rate,
                        recommendation, confidence_score, trades_analyzed
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    insight.get('type'),
                    insight.get('pattern'),
                    insight.get('data', {}).get('win_rate', 0),
                    insight.get('recommendation'),
                    insight.get('confidence', 0),
                    self.model_performance['trades_analyzed']
                ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"💡 Stored {len(insights)} new insights")
            
        except Exception as e:
            self.logger.error(f"Error storing insights: {e}")
    
    def predict_trade_outcome(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict trade outcome using trained models"""
        try:
            if not hasattr(self, 'loss_prediction_model') or not self.loss_prediction_model:
                return {'prediction': 'unknown', 'confidence': 5.0, 'fallback_mode': True}
            
            # Prepare features
            features_df = self._prepare_signal_features(signal_data)
            if features_df is None or len(features_df) == 0:
                return {'prediction': 'unknown', 'confidence': 5.0, 'fallback_mode': True}
            
            # Use simple scaling if no scaler available
            features_scaled = features_df.values if not hasattr(self, 'feature_scaler') or self.feature_scaler is None else self.feature_scaler.transform(features_df)
            
            # Predict loss probability
            loss_prob = self.loss_prediction_model.predict_proba(features_scaled)[0][1]
            
            # Predict signal strength optimization
            strength_pred = 0
            if self.signal_strength_model:
                strength_pred = self.signal_strength_model.predict_proba(features_scaled)[0][1]
            
            # Predict entry timing
            timing_pred = 0
            if self.entry_timing_model:
                timing_pred = self.entry_timing_model.predict_proba(features_scaled)[0][1]
            
            # Combine predictions
            overall_score = (1 - loss_prob) * 0.5 + strength_pred * 0.3 + timing_pred * 0.2
            
            prediction = 'favorable' if overall_score > 0.6 else 'unfavorable' if overall_score < 0.4 else 'neutral'
            
            return {
                'prediction': prediction,
                'confidence': overall_score * 100,
                'loss_probability': loss_prob * 100,
                'strength_score': strength_pred * 100,
                'timing_score': timing_pred * 100,
                'recommendation': self._get_prediction_recommendation(overall_score, loss_prob)
            }
            
        except Exception as e:
            self.logger.error(f"Error predicting trade outcome: {e}")
            return {'prediction': 'unknown', 'confidence': 0, 'error': str(e)}
    
    def _prepare_signal_features(self, signal_data: Dict[str, Any]) -> Optional[pd.DataFrame]:
        """Prepare features from signal data for prediction"""
        try:
            # Create DataFrame with consistent structure
            feature_data = {
                'signal_strength': [signal_data.get('signal_strength', 85)],
                'leverage': [signal_data.get('optimal_leverage', 35)],
                'volatility': [signal_data.get('volatility', 0.02)],
                'volume_ratio': [signal_data.get('volume_ratio', 1.0)],
                'rsi_value': [signal_data.get('rsi', 50)],
                'direction_encoded': [1 if signal_data.get('direction') == 'BUY' else 0],
                'cvd_trend_encoded': [1 if signal_data.get('cvd_trend') == 'bullish' else 0],
                'macd_signal_encoded': [1 if signal_data.get('macd_bullish', False) else 0],
                'ema_alignment': [1 if signal_data.get('ema_bullish', False) else 0],
                'hour': [datetime.now().hour],
                'day_of_week': [datetime.now().weekday()]
            }
            
            features_df = pd.DataFrame(feature_data)
            
            # Ensure consistent column order
            if hasattr(self, 'feature_names'):
                features_df = features_df[self.feature_names]
            
            return features_df
            
        except Exception as e:
            self.logger.error(f"Error preparing signal features: {e}")
            return None
    
    def _get_prediction_recommendation(self, overall_score: float, loss_prob: float) -> str:
        """Get trading recommendation based on predictions"""
        if loss_prob > 0.7:
            return "HIGH RISK - Consider skipping this trade"
        elif overall_score > 0.75:
            return "EXCELLENT - High probability trade"
        elif overall_score > 0.6:
            return "GOOD - Favorable conditions"
        elif overall_score > 0.4:
            return "NEUTRAL - Exercise caution"
        else:
            return "POOR - Unfavorable conditions"
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """Get summary of learning progress and insights"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get trade statistics
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM trades")
            total_trades = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM trades WHERE profit_loss > 0")
            winning_trades = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM learning_insights")
            total_insights = cursor.fetchone()[0]
            
            # Get recent insights
            cursor.execute("SELECT * FROM learning_insights ORDER BY created_at DESC LIMIT 5")
            recent_insights = cursor.fetchall()
            
            conn.close()
            
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            return {
                'total_trades_analyzed': total_trades,
                'win_rate': win_rate,
                'total_insights_generated': total_insights,
                'model_performance': self.model_performance,
                'recent_insights': [
                    {
                        'type': insight[1],
                        'pattern': insight[2],
                        'recommendation': insight[4],
                        'confidence': insight[5]
                    }
                    for insight in recent_insights
                ],
                'learning_status': 'active' if total_trades >= self.min_trades_for_learning else 'collecting_data'
            }
            
        except Exception as e:
            self.logger.error(f"Error getting learning summary: {e}")
            return {'error': str(e)}
    
    def get_trade_recommendations(self, symbol: str) -> Dict[str, Any]:
        """Get specific recommendations for a symbol based on historical performance"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = "SELECT * FROM trades WHERE symbol = ? ORDER BY created_at DESC LIMIT 20"
            df = pd.read_sql_query(query, conn, params=[symbol])
            conn.close()
            
            if len(df) == 0:
                return {'recommendation': 'No historical data available'}
            
            # Analyze symbol-specific patterns
            win_rate = len(df[df['profit_loss'] > 0]) / len(df)
            avg_profit = df['profit_loss'].mean()
            if 'leverage' in df.columns and len(df) > 0:
                leverage_performance = df.groupby('leverage')['profit_loss'].mean()
                best_leverage = leverage_performance.idxmax() if len(leverage_performance) > 0 else 10
            else:
                best_leverage = 10
            avg_duration = df['duration_minutes'].mean()
            
            recommendation = "NEUTRAL"
            if win_rate > 0.7 and avg_profit > 0:
                recommendation = "FAVORABLE"
            elif win_rate < 0.4 or avg_profit < 0:
                recommendation = "AVOID"
            
            return {
                'symbol': symbol,
                'recommendation': recommendation,
                'historical_win_rate': win_rate,
                'avg_profit_loss': avg_profit,
                'optimal_leverage': best_leverage,
                'avg_trade_duration': avg_duration,
                'trade_count': len(df)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting trade recommendations for {symbol}: {e}")
            return {'error': str(e)}
    
    def predict_trade_outcome(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict trade outcome using trained ML models"""
        try:
            if not self.loss_prediction_model and not self.signal_strength_model:
                # Fallback to signal strength based prediction
                signal_strength = trade_data.get('signal_strength', 50)
                return {
                    'confidence': max(5.0, min(95.0, signal_strength * 0.8)),
                    'prediction': 'profitable' if signal_strength > 75 else 'uncertain',
                    'loss_probability': max(0.05, (100 - signal_strength) / 100),
                    'source': 'fallback'
                }
            
            # Prepare feature data for prediction
            feature_data = pd.DataFrame([{
                'signal_strength': trade_data.get('signal_strength', 85),
                'leverage': trade_data.get('leverage', 35),
                'volatility': trade_data.get('volatility', 0.02),
                'volume_ratio': trade_data.get('volume_ratio', 1.0),
                'rsi_value': trade_data.get('rsi_value', 50),
                'direction': trade_data.get('direction', 'BUY'),
                'cvd_trend': trade_data.get('cvd_trend', 'neutral'),
                'macd_signal': trade_data.get('macd_signal', 'neutral'),
                'ema_alignment': trade_data.get('ema_alignment', True),
                'entry_time': trade_data.get('entry_time', datetime.now())
            }])
            
            # Prepare features using the same pipeline as training
            features = self._prepare_features(feature_data, fit_encoders=False)
            
            if features is None or len(features) == 0:
                return {'confidence': 50.0, 'prediction': 'uncertain', 'source': 'error'}
            
            predictions = {}
            
            # Loss prediction
            if self.loss_prediction_model:
                scaler = StandardScaler()
                # For single prediction, we need to transform but can't fit
                # This is a limitation - ideally we'd save the scaler used during training
                X_scaled = features.values.reshape(1, -1)
                loss_prob = self.loss_prediction_model.predict_proba(X_scaled)[0]
                predictions['loss_probability'] = float(loss_prob[1]) if len(loss_prob) > 1 else 0.5
            else:
                predictions['loss_probability'] = 0.5
            
            # Signal strength prediction
            if self.signal_strength_model:
                X_scaled = features.values.reshape(1, -1)
                signal_pred = self.signal_strength_model.predict_proba(X_scaled)[0]
                predictions['signal_confidence'] = float(signal_pred[1]) if len(signal_pred) > 1 else 0.5
            else:
                predictions['signal_confidence'] = 0.5
            
            # Combine predictions into overall confidence
            loss_factor = 1 - predictions['loss_probability']
            signal_factor = predictions['signal_confidence']
            base_signal_strength = trade_data.get('signal_strength', 85) / 100
            
            # Weighted combination
            ml_confidence = (loss_factor * 0.4 + signal_factor * 0.4 + base_signal_strength * 0.2) * 100
            
            # Apply bounds
            ml_confidence = max(5.0, min(95.0, ml_confidence))
            
            return {
                'confidence': ml_confidence,
                'prediction': 'profitable' if ml_confidence > 65 else 'uncertain',
                'loss_probability': predictions['loss_probability'],
                'signal_confidence': predictions.get('signal_confidence', 0.5),
                'source': 'ml_models'
            }
            
        except Exception as e:
            self.logger.error(f"Error in ML prediction: {e}")
            # Fallback to signal strength
            signal_strength = trade_data.get('signal_strength', 50)
            return {
                'confidence': max(10.0, min(90.0, signal_strength * 0.8)),
                'prediction': 'uncertain',
                'source': 'error_fallback',
                'error': str(e)
            }

    def get_ml_confidence(self, symbol: str, trade_data: Dict[str, Any]) -> float:
        """Get ML confidence score for a specific trade"""
        try:
            if not self.loss_prediction_model:
                # Fallback to signal strength based confidence
                signal_strength = trade_data.get('signal_strength', 50)
                return max(5.0, min(95.0, signal_strength * 0.8))
            
            # Get ML prediction
            prediction = self.predict_trade_outcome(trade_data) if hasattr(self, 'predict_trade_outcome') else {'confidence': 50}
            base_confidence = prediction.get('confidence', 50)
            
            # Adjust based on symbol's historical performance
            symbol_adjustment = self._get_symbol_confidence_adjustment(symbol)
            
            # Apply adjustment
            ml_confidence = base_confidence * symbol_adjustment
            
            # Keep within reasonable bounds (5-95%)
            return max(5.0, min(95.0, ml_confidence))
            
        except Exception as e:
            self.logger.error(f"Error calculating ML confidence: {e}")
            return 50.0
    
    def _get_symbol_confidence_adjustment(self, symbol: str) -> float:
        """Get confidence adjustment based on symbol's historical performance"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = '''
                SELECT 
                    AVG(CASE WHEN profit_loss > 0 THEN 1.0 ELSE 0.0 END) as win_rate,
                    COUNT(*) as trade_count
                FROM trades 
                WHERE symbol = ? AND created_at >= datetime('now', '-30 days')
            '''
            result = conn.execute(query, (symbol,)).fetchone()
            conn.close()
            
            if result and result[1] >= 3:  # At least 3 trades for statistical significance
                win_rate = result[0]
                trade_count = result[1]
                
                # Confidence adjustment based on win rate and sample size
                confidence_factor = min(trade_count / 10, 1.0)  # More trades = more confidence
                
                if win_rate >= 0.75:
                    return 1.0 + (0.2 * confidence_factor)  # Boost up to 20%
                elif win_rate >= 0.6:
                    return 1.0 + (0.1 * confidence_factor)  # Boost up to 10%
                elif win_rate <= 0.3:
                    return 1.0 - (0.3 * confidence_factor)  # Reduce up to 30%
                elif win_rate <= 0.45:
                    return 1.0 - (0.15 * confidence_factor)  # Reduce up to 15%
                else:
                    return 1.0  # Neutral adjustment
            else:
                return 1.0  # No historical data, neutral adjustment
                
        except Exception as e:
            self.logger.error(f"Error getting symbol confidence adjustment: {e}")
            return 1.0
    
    def should_trade_symbol(self, symbol: str, current_conditions: Dict[str, Any]) -> bool:
        """Determine if we should trade a specific symbol based on ML analysis"""
        try:
            # Get symbol recommendations
            recommendations = self.get_trade_recommendations(symbol)
            
            if recommendations.get('recommendation') == 'AVOID':
                self.logger.info(f"🚫 ML recommends avoiding {symbol}")
                return False
            
            # Check ML confidence
            ml_confidence = self.get_ml_confidence(symbol, current_conditions)
            
            # Minimum confidence threshold
            min_confidence = 60.0
            
            if ml_confidence < min_confidence:
                self.logger.debug(f"📉 {symbol} ML confidence {ml_confidence:.1f}% below threshold {min_confidence}%")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error determining if should trade {symbol}: {e}")
            return True  # Default to allowing trade if error occurs
    
    def get_optimal_position_size(self, symbol: str, trade_data: Dict[str, Any]) -> float:
        """Get ML-optimized position size multiplier"""
        try:
            ml_confidence = self.get_ml_confidence(symbol, trade_data)
            
            # Scale position size based on confidence
            if ml_confidence >= 85:
                return 1.2  # Increase position by 20%
            elif ml_confidence >= 75:
                return 1.1  # Increase position by 10%
            elif ml_confidence >= 65:
                return 1.0  # Normal position
            elif ml_confidence >= 50:
                return 0.8  # Reduce position by 20%
            else:
                return 0.6  # Reduce position by 40%
                
        except Exception as e:
            self.logger.error(f"Error calculating optimal position size: {e}")
            return 1.0
    
    def _save_models(self):
        """Save trained models and encoders to disk"""
        try:
            # Save models
            if self.loss_prediction_model:
                with open(self.model_dir / 'loss_prediction_model.pkl', 'wb') as f:
                    pickle.dump(self.loss_prediction_model, f)
                    
            if self.signal_strength_model:
                with open(self.model_dir / 'signal_strength_model.pkl', 'wb') as f:
                    pickle.dump(self.signal_strength_model, f)
                    
            if self.entry_timing_model:
                with open(self.model_dir / 'entry_timing_model.pkl', 'wb') as f:
                    pickle.dump(self.entry_timing_model, f)
            
            # Save encoders
            encoders = {
                'direction_encoder': self.direction_encoder,
                'cvd_encoder': self.cvd_encoder,
                'macd_encoder': self.macd_encoder,
                'feature_names': self.feature_names
            }
            with open(self.model_dir / 'encoders.pkl', 'wb') as f:
                pickle.dump(encoders, f)
            
            # Save performance metrics
            with open(self.model_dir / 'performance_metrics.json', 'w') as f:
                json.dump(self.model_performance, f)
                
            self.logger.info("💾 Models and encoders saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving models: {e}")
    
    def _load_models(self):
        """Load trained models and encoders from disk"""
        try:
            # Load models
            loss_model_path = self.model_dir / 'loss_prediction_model.pkl'
            if loss_model_path.exists():
                with open(loss_model_path, 'rb') as f:
                    self.loss_prediction_model = pickle.load(f)
                    
            signal_model_path = self.model_dir / 'signal_strength_model.pkl'
            if signal_model_path.exists():
                with open(signal_model_path, 'rb') as f:
                    self.signal_strength_model = pickle.load(f)
                    
            timing_model_path = self.model_dir / 'entry_timing_model.pkl'
            if timing_model_path.exists():
                with open(timing_model_path, 'rb') as f:
                    self.entry_timing_model = pickle.load(f)
            
            # Load encoders
            encoders_path = self.model_dir / 'encoders.pkl'
            if encoders_path.exists():
                with open(encoders_path, 'rb') as f:
                    encoders = pickle.load(f)
                    self.direction_encoder = encoders.get('direction_encoder', LabelEncoder())
                    self.cvd_encoder = encoders.get('cvd_encoder', LabelEncoder())
                    self.macd_encoder = encoders.get('macd_encoder', LabelEncoder())
                    self.feature_names = encoders.get('feature_names')
            
            # Load performance metrics
            metrics_path = self.model_dir / 'performance_metrics.json'
            if metrics_path.exists():
                with open(metrics_path, 'r') as f:
                    self.model_performance.update(json.load(f))
                    
            models_loaded = sum([
                self.loss_prediction_model is not None,
                self.signal_strength_model is not None,
                self.entry_timing_model is not None
            ])
            
            if models_loaded > 0:
                self.logger.info(f"🧠 Loaded {models_loaded} ML models successfully")
            else:
                self.logger.info("No pre-trained models found")
                
        except Exception as e:
            self.logger.error(f"Error loading models: {e}")
            # Initialize fresh encoders if loading fails
            self.direction_encoder = LabelEncoder()
            self.cvd_encoder = LabelEncoder()
            self.macd_encoder = LabelEncoder()

    def get_model_status(self) -> Dict[str, Any]:
        """Get current status of all ML models"""
        return {
            'models_available': {
                'loss_prediction': self.loss_prediction_model is not None,
                'signal_strength': self.signal_strength_model is not None,
                'entry_timing': self.entry_timing_model is not None,
                'scaler': self.scaler is not None
            },
            'performance_metrics': self.model_performance,
            'features_defined': hasattr(self, 'feature_names'),
            'total_trades_analyzed': self.model_performance.get('trades_analyzed', 0),
            'last_training': self.model_performance.get('last_training_time', 'Never'),
            'learning_ready': self._get_trade_count() >= self.min_trades_for_learning
        }
