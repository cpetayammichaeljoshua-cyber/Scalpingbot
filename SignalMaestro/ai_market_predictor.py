#!/usr/bin/env python3
"""
Advanced AI Market Predictor - Transformer-Based Time Series Prediction
Uses transformer architectures for advanced time series prediction and pattern recognition
Integrates with the Ultimate Trading Bot for enhanced market forecasting
"""

import asyncio
import logging
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import sqlite3
from pathlib import Path
import pickle
import traceback
from collections import deque, defaultdict
import math

# Deep Learning and Transformer imports
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    optim = None  # type: ignore
    DataLoader = None  # type: ignore
    Dataset = object  # type: ignore

    # Stub classes so module-level class definitions (TimeSeriesTransformer etc.)
    # that reference torch.Tensor / nn.Module / nn.Linear don't raise NameError
    # or AttributeError at import time when PyTorch is absent.
    # None of these stubs are ever instantiated — all torch code paths are
    # guarded by `if TORCH_AVAILABLE:` before use.
    class _TorchStub:
        Tensor = object
        FloatTensor = object
        class cuda:
            @staticmethod
            def is_available(): return False
        @staticmethod
        def zeros(*a, **kw): return None
        @staticmethod
        def arange(*a, **kw): return None
        @staticmethod
        def exp(*a, **kw): return None
        @staticmethod
        def sin(*a, **kw): return None
        @staticmethod
        def cos(*a, **kw): return None
        @staticmethod
        def sigmoid(*a, **kw): return None
        @staticmethod
        def softmax(*a, **kw): return None
        @staticmethod
        def no_grad(): return __import__('contextlib').nullcontext()
        @staticmethod
        def load(*a, **kw): return {}
        @staticmethod
        def save(*a, **kw): pass
        device = object

    class _NNStub:
        Module           = object
        Linear           = object
        TransformerEncoderLayer = object
        TransformerEncoder      = object
        Dropout          = object
        LayerNorm        = object
        MSELoss          = object
        BCELoss          = object
        CrossEntropyLoss = object
        @staticmethod
        def Parameter(*a, **kw): return None
        @staticmethod
        def Sigmoid(*a, **kw): return None
        @staticmethod
        def ReLU(*a, **kw): return None

    torch = _TorchStub()  # type: ignore
    nn = _NNStub()  # type: ignore

try:
    from transformers import AutoModel, AutoTokenizer, AutoConfig
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

# Scientific computing
try:
    from sklearn.preprocessing import StandardScaler, MinMaxScaler
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

@dataclass
class MarketPrediction:
    """Market prediction result structure"""
    symbol: str
    timeframe: str
    prediction_horizon: int  # Minutes into the future
    predicted_price: float
    confidence: float
    price_direction: str  # "up", "down", "sideways"
    volatility_prediction: float
    support_levels: List[float]
    resistance_levels: List[float]
    trend_strength: float
    momentum_score: float
    pattern_detected: str
    risk_assessment: float
    timestamp: datetime
    model_used: str

@dataclass
class PredictionPerformance:
    """Prediction performance metrics"""
    accuracy: float
    mse: float
    mae: float
    r2_score: float
    direction_accuracy: float
    predictions_made: int
    successful_predictions: int
    avg_confidence: float
    model_version: str

class TimeSeriesTransformer(nn.Module):
    """Custom Transformer model for time series prediction"""
    
    def __init__(self, input_dim: int, hidden_dim: int = 256, num_layers: int = 4, 
                 num_heads: int = 8, dropout: float = 0.1, sequence_length: int = 60):
        super(TimeSeriesTransformer, self).__init__()
        
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.sequence_length = sequence_length
        
        # Input projection
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        
        # Positional encoding
        self.positional_encoding = self._create_positional_encoding(sequence_length, hidden_dim)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            activation='gelu',
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output layers
        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(hidden_dim)
        
        # Multi-head output for different predictions
        self.price_head = nn.Linear(hidden_dim, 1)
        self.volatility_head = nn.Linear(hidden_dim, 1)
        self.direction_head = nn.Linear(hidden_dim, 3)  # up, down, sideways
        self.confidence_head = nn.Linear(hidden_dim, 1)
        
    def _create_positional_encoding(self, seq_length: int, hidden_dim: int) -> torch.Tensor:
        """Create positional encoding for transformer"""
        pe = torch.zeros(seq_length, hidden_dim)
        position = torch.arange(0, seq_length, dtype=torch.float).unsqueeze(1)
        
        div_term = torch.exp(torch.arange(0, hidden_dim, 2).float() * 
                           (-math.log(10000.0) / hidden_dim))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        return pe.unsqueeze(0)
    
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """Forward pass of the transformer"""
        batch_size, seq_len, _ = x.shape
        
        # Input projection
        x = self.input_projection(x)
        
        # Add positional encoding
        if seq_len <= self.positional_encoding.size(1):
            x = x + self.positional_encoding[:, :seq_len, :].to(x.device)
        
        # Transformer encoding
        transformer_output = self.transformer_encoder(x)
        
        # Use the last time step for predictions
        last_hidden = transformer_output[:, -1, :]
        last_hidden = self.layer_norm(self.dropout(last_hidden))
        
        # Multi-head predictions
        price_pred = self.price_head(last_hidden)
        volatility_pred = torch.sigmoid(self.volatility_head(last_hidden))
        direction_pred = torch.softmax(self.direction_head(last_hidden), dim=-1)
        confidence_pred = torch.sigmoid(self.confidence_head(last_hidden))
        
        return {
            'price': price_pred,
            'volatility': volatility_pred,
            'direction': direction_pred,
            'confidence': confidence_pred
        }

class MarketDataset(Dataset):
    """Custom dataset for market data"""
    
    def __init__(self, data: np.ndarray, targets: np.ndarray, sequence_length: int = 60):
        self.data = data
        self.targets = targets
        self.sequence_length = sequence_length
        
    def __len__(self):
        return len(self.data) - self.sequence_length + 1
    
    def __getitem__(self, idx):
        x = self.data[idx:idx + self.sequence_length]
        y = self.targets[idx + self.sequence_length - 1]
        
        return torch.FloatTensor(x), torch.FloatTensor(y)

class AIMarketPredictor:
    """
    Advanced AI Market Predictor using transformer architectures
    Provides sophisticated time series prediction and pattern recognition
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Model configuration
        self.sequence_length = 60  # Look back 60 time steps
        self.input_features = 20   # Number of technical indicators
        self.hidden_dim = 256
        self.num_layers = 4
        self.num_heads = 8
        self.dropout = 0.1
        
        # Initialize models
        self.model = None
        self.scaler = None
        self.target_scaler = None
        # FIX: guard torch.device() call — without this, the _TorchStub.device=object
        # causes `object('cpu')` → TypeError: object() takes no arguments
        if TORCH_AVAILABLE:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = 'cpu'   # plain string fallback when torch absent

        if TORCH_AVAILABLE:
            self._initialize_model()
        
        # Database for storing predictions and performance
        self.db_path = "SignalMaestro/market_predictions.db"
        self._initialize_database()
        
        # Performance tracking
        self.prediction_history = deque(maxlen=1000)
        self.model_performance = {
            'accuracy': 0.0,
            'mse': 0.0,
            'mae': 0.0,
            'r2_score': 0.0,
            'direction_accuracy': 0.0,
            'predictions_made': 0,
            'successful_predictions': 0,
            'last_training': None,
            'model_version': 1.0
        }
        
        # Pattern recognition
        self.pattern_library = {
            'double_top': {'score_threshold': 0.85, 'lookback': 100},
            'double_bottom': {'score_threshold': 0.85, 'lookback': 100},
            'head_shoulders': {'score_threshold': 0.80, 'lookback': 150},
            'triangle': {'score_threshold': 0.75, 'lookback': 80},
            'flag': {'score_threshold': 0.70, 'lookback': 50},
            'breakout': {'score_threshold': 0.80, 'lookback': 30}
        }
        
        # Prediction cache
        self.prediction_cache = {}
        self.cache_ttl = 60  # 1 minute cache
        
        # Load existing models
        self._load_models()
        
        self.logger.info("🧠 AI Market Predictor initialized with transformer architecture")

    def _initialize_model(self):
        """Initialize the transformer model"""
        try:
            if not TORCH_AVAILABLE:
                self.logger.warning("⚠️ PyTorch not available, using fallback prediction")
                return
            
            self.model = TimeSeriesTransformer(
                input_dim=self.input_features,
                hidden_dim=self.hidden_dim,
                num_layers=self.num_layers,
                num_heads=self.num_heads,
                dropout=self.dropout,
                sequence_length=self.sequence_length
            ).to(self.device)
            
            self.optimizer = optim.AdamW(self.model.parameters(), lr=0.001, weight_decay=0.01)
            self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                self.optimizer, mode='min', factor=0.5, patience=10
            )
            
            if SKLEARN_AVAILABLE:
                self.scaler = StandardScaler()
                self.target_scaler = MinMaxScaler()
            
            self.logger.info("✅ Transformer model initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Model initialization failed: {e}")

    def _initialize_database(self):
        """Initialize prediction database"""
        try:
            Path("SignalMaestro").mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Market predictions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    prediction_horizon INTEGER NOT NULL,
                    predicted_price REAL NOT NULL,
                    actual_price REAL,
                    confidence REAL NOT NULL,
                    price_direction TEXT NOT NULL,
                    volatility_prediction REAL NOT NULL,
                    support_levels TEXT NOT NULL,
                    resistance_levels TEXT NOT NULL,
                    trend_strength REAL NOT NULL,
                    momentum_score REAL NOT NULL,
                    pattern_detected TEXT NOT NULL,
                    risk_assessment REAL NOT NULL,
                    model_used TEXT NOT NULL,
                    prediction_accuracy REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    validated_at TIMESTAMP
                )
            ''')

            # Model performance table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_version REAL NOT NULL,
                    accuracy REAL NOT NULL,
                    mse REAL NOT NULL,
                    mae REAL NOT NULL,
                    r2_score REAL NOT NULL,
                    direction_accuracy REAL NOT NULL,
                    predictions_made INTEGER NOT NULL,
                    successful_predictions INTEGER NOT NULL,
                    training_data_points INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Pattern detection table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pattern_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    pattern_type TEXT NOT NULL,
                    pattern_score REAL NOT NULL,
                    prediction_impact REAL NOT NULL,
                    timeframe TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()
            conn.close()
            self.logger.info("📊 Market prediction database initialized")

        except Exception as e:
            self.logger.error(f"❌ Database initialization failed: {e}")

    async def predict_market_movement(self, symbol: str, market_data: pd.DataFrame, 
                                    timeframe: str = "1m", horizon: int = 15) -> MarketPrediction:
        """
        Predict market movement using transformer model
        
        Args:
            symbol: Trading symbol
            market_data: Historical OHLCV data
            timeframe: Timeframe for prediction
            horizon: Prediction horizon in minutes
            
        Returns:
            MarketPrediction with comprehensive forecast
        """
        try:
            cache_key = f"{symbol}_{timeframe}_{horizon}_{datetime.now().minute}"
            if cache_key in self.prediction_cache:
                cache_time, prediction = self.prediction_cache[cache_key]
                if (datetime.now() - cache_time).seconds < self.cache_ttl:
                    return prediction
            
            self.logger.info(f"🔮 Predicting market movement for {symbol} ({timeframe}, {horizon}min)")
            
            # Prepare features
            features = self._prepare_features(market_data)
            if features is None or len(features) < self.sequence_length:
                return self._create_fallback_prediction(symbol, timeframe, horizon)
            
            # Make prediction with transformer model
            prediction_data = await self._make_transformer_prediction(features, symbol)
            
            # Detect patterns
            patterns = self._detect_patterns(market_data)
            primary_pattern = max(patterns.items(), key=lambda x: x[1]) if patterns else ("none", 0.0)
            
            # Calculate support and resistance levels
            support_resistance = self._calculate_support_resistance(market_data)
            
            # Create prediction object
            current_price = float(market_data['close'].iloc[-1])
            predicted_price = prediction_data.get('price', current_price)
            
            # Determine price direction
            price_change = (predicted_price - current_price) / current_price
            if price_change > 0.002:  # 0.2% threshold
                direction = "up"
            elif price_change < -0.002:
                direction = "down"
            else:
                direction = "sideways"
            
            prediction = MarketPrediction(
                symbol=symbol,
                timeframe=timeframe,
                prediction_horizon=horizon,
                predicted_price=predicted_price,
                confidence=prediction_data.get('confidence', 0.5),
                price_direction=direction,
                volatility_prediction=prediction_data.get('volatility', 0.02),
                support_levels=support_resistance['support'],
                resistance_levels=support_resistance['resistance'],
                trend_strength=prediction_data.get('trend_strength', 0.5),
                momentum_score=prediction_data.get('momentum', 0.5),
                pattern_detected=primary_pattern[0],
                risk_assessment=prediction_data.get('risk', 0.5),
                timestamp=datetime.now(),
                model_used="transformer_v1"
            )
            
            # Cache prediction
            self.prediction_cache[cache_key] = (datetime.now(), prediction)
            
            # Store in database
            await self._store_prediction(prediction)
            
            # Update performance tracking
            self.prediction_history.append(prediction)
            self.model_performance['predictions_made'] += 1
            
            self.logger.info(f"✅ Prediction completed: {direction} ({prediction.confidence:.2f} confidence)")
            return prediction
            
        except Exception as e:
            self.logger.error(f"❌ Market prediction failed: {e}")
            return self._create_fallback_prediction(symbol, timeframe, horizon)

    def _prepare_features(self, market_data: pd.DataFrame) -> Optional[np.ndarray]:
        """Prepare features for the transformer model"""
        try:
            if len(market_data) < self.sequence_length:
                return None
            
            # Calculate technical indicators
            df = market_data.copy()
            
            # Price features
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
            df['price_ma_20'] = df['close'].rolling(20).mean()
            df['price_ma_50'] = df['close'].rolling(50).mean()
            
            # Volatility features
            df['volatility'] = df['returns'].rolling(20).std()
            df['high_low_ratio'] = (df['high'] - df['low']) / df['close']
            
            # Volume features
            df['volume_ma'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            # Momentum indicators
            df['rsi'] = self._calculate_rsi(df['close'])
            df['macd'], df['macd_signal'] = self._calculate_macd(df['close'])
            df['stoch_k'], df['stoch_d'] = self._calculate_stochastic(df)
            
            # Trend indicators
            df['ema_12'] = df['close'].ewm(span=12).mean()
            df['ema_26'] = df['close'].ewm(span=26).mean()
            df['ema_diff'] = df['ema_12'] - df['ema_26']
            
            # Support/Resistance
            df['resistance'] = df['high'].rolling(20).max()
            df['support'] = df['low'].rolling(20).min()
            df['price_position'] = (df['close'] - df['support']) / (df['resistance'] - df['support'])
            
            # Time features
            df['hour'] = pd.to_datetime(df.index).hour if hasattr(df.index, 'hour') else 12
            df['day_of_week'] = pd.to_datetime(df.index).dayofweek if hasattr(df.index, 'dayofweek') else 1
            
            # Select features for model
            feature_columns = [
                'returns', 'log_returns', 'volatility', 'high_low_ratio',
                'volume_ratio', 'rsi', 'macd', 'macd_signal', 'stoch_k', 'stoch_d',
                'ema_diff', 'price_position', 'hour', 'day_of_week'
            ]
            
            # Add price normalization features
            df['price_norm'] = (df['close'] - df['close'].rolling(50).mean()) / df['close'].rolling(50).std()
            df['volume_norm'] = (df['volume'] - df['volume'].rolling(50).mean()) / df['volume'].rolling(50).std()
            
            feature_columns.extend(['price_norm', 'volume_norm'])
            
            # Pad to required number of features
            while len(feature_columns) < self.input_features:
                feature_columns.append(f'padding_{len(feature_columns)}')
                df[f'padding_{len(feature_columns)-1}'] = 0.0
            
            # Select final features
            features = df[feature_columns[:self.input_features]].fillna(0).values
            
            # Normalize features
            if self.scaler is not None and SKLEARN_AVAILABLE:
                if not hasattr(self.scaler, 'mean_'):
                    self.scaler.fit(features)
                features = self.scaler.transform(features)
            
            return features
            
        except Exception as e:
            self.logger.error(f"❌ Feature preparation failed: {e}")
            return None

    async def _make_transformer_prediction(self, features: np.ndarray, symbol: str) -> Dict[str, float]:
        """Make prediction using transformer model"""
        try:
            if self.model is None or not TORCH_AVAILABLE:
                return self._fallback_prediction_data()
            
            # Prepare input
            if len(features) >= self.sequence_length:
                input_sequence = features[-self.sequence_length:]
            else:
                # Pad if necessary
                padding = np.zeros((self.sequence_length - len(features), self.input_features))
                input_sequence = np.vstack([padding, features])
            
            input_tensor = torch.FloatTensor(input_sequence).unsqueeze(0).to(self.device)
            
            # Make prediction
            self.model.eval()
            with torch.no_grad():
                predictions = self.model(input_tensor)
            
            # Extract predictions
            price_pred = predictions['price'].cpu().numpy()[0, 0]
            volatility_pred = predictions['volatility'].cpu().numpy()[0, 0]
            direction_probs = predictions['direction'].cpu().numpy()[0]
            confidence_pred = predictions['confidence'].cpu().numpy()[0, 0]
            
            # Calculate derived metrics
            trend_strength = max(direction_probs) - min(direction_probs)
            momentum = direction_probs[0] - direction_probs[1]  # up - down
            risk = 1.0 - confidence_pred
            
            return {
                'price': float(price_pred),
                'volatility': float(volatility_pred),
                'confidence': float(confidence_pred),
                'trend_strength': float(trend_strength),
                'momentum': float(momentum),
                'risk': float(risk)
            }
            
        except Exception as e:
            self.logger.error(f"❌ Transformer prediction failed: {e}")
            return self._fallback_prediction_data()

    def _detect_patterns(self, market_data: pd.DataFrame) -> Dict[str, float]:
        """Detect chart patterns using technical analysis"""
        try:
            patterns = {}
            
            if len(market_data) < 50:
                return patterns
            
            highs = market_data['high'].values
            lows = market_data['low'].values
            closes = market_data['close'].values
            
            # Double top pattern
            patterns['double_top'] = self._detect_double_top(highs, closes)
            
            # Double bottom pattern
            patterns['double_bottom'] = self._detect_double_bottom(lows, closes)
            
            # Head and shoulders
            patterns['head_shoulders'] = self._detect_head_shoulders(highs, closes)
            
            # Triangle patterns
            patterns['triangle'] = self._detect_triangle(highs, lows)
            
            # Flag pattern
            patterns['flag'] = self._detect_flag(closes)
            
            # Breakout pattern
            patterns['breakout'] = self._detect_breakout(closes, highs, lows)
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"❌ Pattern detection failed: {e}")
            return {}

    def _detect_double_top(self, highs: np.ndarray, closes: np.ndarray) -> float:
        """Detect double top pattern"""
        try:
            if len(highs) < 50:
                return 0.0
            
            # Find peaks
            peaks = []
            for i in range(1, len(highs) - 1):
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    peaks.append((i, highs[i]))
            
            if len(peaks) < 2:
                return 0.0
            
            # Check for double top pattern
            peaks.sort(key=lambda x: x[1], reverse=True)
            top1, top2 = peaks[0], peaks[1]
            
            # Similarity of peaks (within 2%)
            peak_similarity = 1.0 - abs(top1[1] - top2[1]) / max(top1[1], top2[1])
            if peak_similarity < 0.98:
                return 0.0
            
            # Time separation (should be significant)
            time_separation = abs(top1[0] - top2[0])
            if time_separation < 10:
                return 0.0
            
            # Check for lower high after second peak
            if top2[0] < len(closes) - 5:
                recent_high = max(highs[top2[0]:])
                if recent_high > top2[1] * 1.01:
                    return 0.0
            
            return min(0.9, peak_similarity * 0.8 + 0.1)
            
        except Exception:
            return 0.0

    def _detect_double_bottom(self, lows: np.ndarray, closes: np.ndarray) -> float:
        """Detect double bottom pattern"""
        try:
            if len(lows) < 50:
                return 0.0
            
            # Find troughs
            troughs = []
            for i in range(1, len(lows) - 1):
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    troughs.append((i, lows[i]))
            
            if len(troughs) < 2:
                return 0.0
            
            # Check for double bottom pattern
            troughs.sort(key=lambda x: x[1])
            bottom1, bottom2 = troughs[0], troughs[1]
            
            # Similarity of troughs (within 2%)
            trough_similarity = 1.0 - abs(bottom1[1] - bottom2[1]) / max(bottom1[1], bottom2[1])
            if trough_similarity < 0.98:
                return 0.0
            
            # Time separation
            time_separation = abs(bottom1[0] - bottom2[0])
            if time_separation < 10:
                return 0.0
            
            # Check for higher low after second trough
            if bottom2[0] < len(closes) - 5:
                recent_low = min(lows[bottom2[0]:])
                if recent_low < bottom2[1] * 0.99:
                    return 0.0
            
            return min(0.9, trough_similarity * 0.8 + 0.1)
            
        except Exception:
            return 0.0

    def _detect_head_shoulders(self, highs: np.ndarray, closes: np.ndarray) -> float:
        """Detect head and shoulders pattern"""
        try:
            if len(highs) < 100:
                return 0.0
            
            # Find significant peaks
            peaks = []
            for i in range(5, len(highs) - 5):
                if all(highs[i] > highs[i-j] for j in range(1, 6)) and \
                   all(highs[i] > highs[i+j] for j in range(1, 6)):
                    peaks.append((i, highs[i]))
            
            if len(peaks) < 3:
                return 0.0
            
            # Sort by time
            peaks.sort(key=lambda x: x[0])
            
            # Check for head and shoulders formation
            for i in range(len(peaks) - 2):
                left_shoulder = peaks[i]
                head = peaks[i + 1]
                right_shoulder = peaks[i + 2]
                
                # Head should be higher than shoulders
                if head[1] <= max(left_shoulder[1], right_shoulder[1]):
                    continue
                
                # Shoulders should be similar height
                shoulder_similarity = 1.0 - abs(left_shoulder[1] - right_shoulder[1]) / max(left_shoulder[1], right_shoulder[1])
                if shoulder_similarity < 0.95:
                    continue
                
                # Head should be significantly higher
                head_prominence = (head[1] - max(left_shoulder[1], right_shoulder[1])) / head[1]
                if head_prominence < 0.05:
                    continue
                
                return min(0.9, shoulder_similarity * 0.6 + head_prominence * 10 * 0.3 + 0.1)
            
            return 0.0
            
        except Exception:
            return 0.0

    def _detect_triangle(self, highs: np.ndarray, lows: np.ndarray) -> float:
        """Detect triangle pattern"""
        try:
            if len(highs) < 30:
                return 0.0
            
            recent_highs = highs[-30:]
            recent_lows = lows[-30:]
            
            # Calculate trend lines
            x = np.arange(len(recent_highs))
            
            # Fit lines to highs and lows
            high_slope = np.polyfit(x, recent_highs, 1)[0]
            low_slope = np.polyfit(x, recent_lows, 1)[0]
            
            # Triangle patterns:
            # Ascending: flat resistance, rising support
            # Descending: falling resistance, flat support
            # Symmetrical: falling resistance, rising support
            
            convergence = abs(high_slope - low_slope)
            
            if convergence > 0.001:  # Lines are converging
                if abs(high_slope) < 0.0005 and low_slope > 0.0005:
                    return 0.8  # Ascending triangle
                elif abs(low_slope) < 0.0005 and high_slope < -0.0005:
                    return 0.8  # Descending triangle
                elif high_slope < -0.0005 and low_slope > 0.0005:
                    return 0.75  # Symmetrical triangle
            
            return 0.0
            
        except Exception:
            return 0.0

    def _detect_flag(self, closes: np.ndarray) -> float:
        """Detect flag pattern"""
        try:
            if len(closes) < 30:
                return 0.0
            
            # Look for strong move followed by consolidation
            recent_closes = closes[-30:]
            
            # Check for strong initial move
            initial_move = (recent_closes[10] - recent_closes[0]) / recent_closes[0]
            if abs(initial_move) < 0.05:  # Less than 5% move
                return 0.0
            
            # Check for consolidation after move
            consolidation_period = recent_closes[10:]
            volatility = np.std(consolidation_period) / np.mean(consolidation_period)
            
            if volatility < 0.02:  # Low volatility consolidation
                return 0.7
            
            return 0.0
            
        except Exception:
            return 0.0

    def _detect_breakout(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
        """Detect breakout pattern"""
        try:
            if len(closes) < 20:
                return 0.0
            
            recent_closes = closes[-20:]
            recent_highs = highs[-20:]
            recent_lows = lows[-20:]
            
            # Calculate recent range
            recent_high = max(recent_highs[:-1])  # Exclude current candle
            recent_low = min(recent_lows[:-1])
            current_price = closes[-1]
            
            # Check for breakout
            range_size = (recent_high - recent_low) / recent_low
            
            if current_price > recent_high * 1.002:  # Upward breakout
                return min(0.9, 0.5 + range_size * 5)
            elif current_price < recent_low * 0.998:  # Downward breakout
                return min(0.9, 0.5 + range_size * 5)
            
            return 0.0
            
        except Exception:
            return 0.0

    def _calculate_support_resistance(self, market_data: pd.DataFrame) -> Dict[str, List[float]]:
        """Calculate support and resistance levels"""
        try:
            highs = market_data['high'].values
            lows = market_data['low'].values
            closes = market_data['close'].values
            
            support_levels = []
            resistance_levels = []
            
            # Find pivot points
            lookback = 10
            for i in range(lookback, len(highs) - lookback):
                # Resistance levels (pivot highs)
                if all(highs[i] >= highs[i-j] for j in range(1, lookback+1)) and \
                   all(highs[i] >= highs[i+j] for j in range(1, lookback+1)):
                    resistance_levels.append(highs[i])
                
                # Support levels (pivot lows)
                if all(lows[i] <= lows[i-j] for j in range(1, lookback+1)) and \
                   all(lows[i] <= lows[i+j] for j in range(1, lookback+1)):
                    support_levels.append(lows[i])
            
            # Filter and sort levels
            current_price = closes[-1]
            
            # Keep only relevant levels (within reasonable range)
            price_range = current_price * 0.1  # 10% range
            
            support_levels = [s for s in support_levels if current_price - price_range <= s <= current_price]
            resistance_levels = [r for r in resistance_levels if current_price <= r <= current_price + price_range]
            
            # Sort and limit
            support_levels = sorted(set(support_levels), reverse=True)[:3]
            resistance_levels = sorted(set(resistance_levels))[:3]
            
            return {
                'support': support_levels,
                'resistance': resistance_levels
            }
            
        except Exception as e:
            self.logger.error(f"❌ Support/resistance calculation failed: {e}")
            return {'support': [], 'resistance': []}

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))
        except Exception:
            return pd.Series([50] * len(prices), index=prices.index)

    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series]:
        """Calculate MACD indicator"""
        try:
            ema_fast = prices.ewm(span=fast).mean()
            ema_slow = prices.ewm(span=slow).mean()
            macd = ema_fast - ema_slow
            signal_line = macd.ewm(span=signal).mean()
            return macd, signal_line
        except Exception:
            return pd.Series([0] * len(prices), index=prices.index), pd.Series([0] * len(prices), index=prices.index)

    def _calculate_stochastic(self, data: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """Calculate Stochastic oscillator"""
        try:
            low_min = data['low'].rolling(window=k_period).min()
            high_max = data['high'].rolling(window=k_period).max()
            k_percent = 100 * ((data['close'] - low_min) / (high_max - low_min))
            d_percent = k_percent.rolling(window=d_period).mean()
            return k_percent, d_percent
        except Exception:
            return pd.Series([50] * len(data), index=data.index), pd.Series([50] * len(data), index=data.index)

    async def train_model(self, training_data: pd.DataFrame) -> bool:
        """Train the transformer model with new data"""
        try:
            if not TORCH_AVAILABLE or self.model is None:
                self.logger.warning("⚠️ Training skipped - PyTorch not available")
                return False
            
            self.logger.info("🎓 Starting model training...")
            
            # Prepare training data
            features = self._prepare_features(training_data)
            if features is None or len(features) < self.sequence_length + 50:
                self.logger.warning("⚠️ Insufficient training data")
                return False
            
            # Prepare targets (next price)
            targets = training_data['close'].values[1:]  # Next close price
            features = features[:-1]  # Align with targets
            
            # Create dataset
            if SKLEARN_AVAILABLE:
                X_train, X_val, y_train, y_val = train_test_split(
                    features, targets, test_size=0.2, shuffle=False
                )
            else:
                split_idx = int(len(features) * 0.8)
                X_train, X_val = features[:split_idx], features[split_idx:]
                y_train, y_val = targets[:split_idx], targets[split_idx:]
            
            # Create data loaders
            train_dataset = MarketDataset(X_train, y_train, self.sequence_length)
            val_dataset = MarketDataset(X_val, y_val, self.sequence_length)
            
            train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)
            
            # Training loop
            self.model.train()
            best_val_loss = float('inf')
            patience_counter = 0
            max_patience = 15
            
            criterion = nn.MSELoss()
            
            for epoch in range(100):  # Max epochs
                train_loss = 0.0
                for batch_x, batch_y in train_loader:
                    batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                    
                    self.optimizer.zero_grad()
                    predictions = self.model(batch_x)
                    loss = criterion(predictions['price'].squeeze(), batch_y)
                    loss.backward()
                    self.optimizer.step()
                    
                    train_loss += loss.item()
                
                # Validation
                val_loss = 0.0
                self.model.eval()
                with torch.no_grad():
                    for batch_x, batch_y in val_loader:
                        batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                        predictions = self.model(batch_x)
                        loss = criterion(predictions['price'].squeeze(), batch_y)
                        val_loss += loss.item()
                
                self.model.train()
                
                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    # Save best model
                    self._save_models()
                else:
                    patience_counter += 1
                    if patience_counter >= max_patience:
                        break
                
                self.scheduler.step(val_loss)
                
                if epoch % 10 == 0:
                    self.logger.info(f"Epoch {epoch}: Train Loss {train_loss:.6f}, Val Loss {val_loss:.6f}")
            
            self.model_performance['last_training'] = datetime.now()
            self.model_performance['model_version'] += 0.1
            
            self.logger.info("✅ Model training completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Model training failed: {e}")
            return False

    def _save_models(self):
        """Save trained models to disk"""
        try:
            model_dir = Path("SignalMaestro/ai_models")
            model_dir.mkdir(parents=True, exist_ok=True)
            
            if self.model is not None and TORCH_AVAILABLE:
                torch.save(self.model.state_dict(), model_dir / "transformer_model.pth")
            
            if self.scaler is not None:
                with open(model_dir / "feature_scaler.pkl", 'wb') as f:
                    pickle.dump(self.scaler, f)
            
            if self.target_scaler is not None:
                with open(model_dir / "target_scaler.pkl", 'wb') as f:
                    pickle.dump(self.target_scaler, f)
            
            # Save performance metrics
            with open(model_dir / "model_performance.json", 'w') as f:
                json.dump(self.model_performance, f, indent=2, default=str)
            
            self.logger.info("💾 Models saved successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Model saving failed: {e}")

    def _load_models(self):
        """Load trained models from disk"""
        try:
            model_dir = Path("SignalMaestro/ai_models")
            if not model_dir.exists():
                self.logger.info("📁 No saved models found")
                return
            
            # Load transformer model
            model_path = model_dir / "transformer_model.pth"
            if model_path.exists() and self.model is not None and TORCH_AVAILABLE:
                self.model.load_state_dict(torch.load(model_path, map_location=self.device))
                self.logger.info("🤖 Transformer model loaded")
            
            # Load scalers
            scaler_path = model_dir / "feature_scaler.pkl"
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                self.logger.info("📊 Feature scaler loaded")
            
            target_scaler_path = model_dir / "target_scaler.pkl"
            if target_scaler_path.exists():
                with open(target_scaler_path, 'rb') as f:
                    self.target_scaler = pickle.load(f)
                self.logger.info("🎯 Target scaler loaded")
            
            # Load performance metrics
            performance_path = model_dir / "model_performance.json"
            if performance_path.exists():
                with open(performance_path, 'r') as f:
                    self.model_performance.update(json.load(f))
                self.logger.info("📈 Performance metrics loaded")
            
        except Exception as e:
            self.logger.error(f"❌ Model loading failed: {e}")

    async def _store_prediction(self, prediction: MarketPrediction):
        """Store prediction in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO market_predictions (
                    symbol, timeframe, prediction_horizon, predicted_price, confidence,
                    price_direction, volatility_prediction, support_levels, resistance_levels,
                    trend_strength, momentum_score, pattern_detected, risk_assessment, model_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                prediction.symbol, prediction.timeframe, prediction.prediction_horizon,
                prediction.predicted_price, prediction.confidence, prediction.price_direction,
                prediction.volatility_prediction, json.dumps(prediction.support_levels),
                json.dumps(prediction.resistance_levels), prediction.trend_strength,
                prediction.momentum_score, prediction.pattern_detected,
                prediction.risk_assessment, prediction.model_used
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"❌ Prediction storage failed: {e}")

    def _create_fallback_prediction(self, symbol: str, timeframe: str, horizon: int) -> MarketPrediction:
        """Create fallback prediction when model fails"""
        return MarketPrediction(
            symbol=symbol,
            timeframe=timeframe,
            prediction_horizon=horizon,
            predicted_price=0.0,
            confidence=0.0,
            price_direction="sideways",
            volatility_prediction=0.02,
            support_levels=[],
            resistance_levels=[],
            trend_strength=0.0,
            momentum_score=0.0,
            pattern_detected="none",
            risk_assessment=0.5,
            timestamp=datetime.now(),
            model_used="fallback"
        )

    def _fallback_prediction_data(self) -> Dict[str, float]:
        """Fallback prediction data"""
        return {
            'price': 0.0,
            'volatility': 0.02,
            'confidence': 0.0,
            'trend_strength': 0.0,
            'momentum': 0.0,
            'risk': 0.5
        }

    def get_prediction_insights(self) -> Dict[str, Any]:
        """Get comprehensive prediction insights"""
        try:
            if not self.prediction_history:
                return {'status': 'no_predictions', 'recommendations': []}
            
            recent_predictions = list(self.prediction_history)[-10:]
            
            # Calculate metrics
            avg_confidence = sum(p.confidence for p in recent_predictions) / len(recent_predictions)
            
            # Direction distribution
            directions = [p.price_direction for p in recent_predictions]
            direction_counts = {d: directions.count(d) for d in set(directions)}
            
            # Pattern frequency
            patterns = [p.pattern_detected for p in recent_predictions if p.pattern_detected != "none"]
            pattern_counts = {p: patterns.count(p) for p in set(patterns)}
            
            # Risk assessment
            avg_risk = sum(p.risk_assessment for p in recent_predictions) / len(recent_predictions)
            
            return {
                'status': 'active',
                'predictions_made': len(self.prediction_history),
                'avg_confidence': avg_confidence,
                'direction_distribution': direction_counts,
                'pattern_frequency': pattern_counts,
                'avg_risk_level': avg_risk,
                'model_performance': self.model_performance,
                'last_prediction': recent_predictions[-1].timestamp.isoformat(),
                'recommendations': self._generate_recommendations(recent_predictions)
            }
            
        except Exception as e:
            self.logger.error(f"❌ Prediction insights failed: {e}")
            return {'status': 'error', 'recommendations': []}

    def _generate_recommendations(self, predictions: List[MarketPrediction]) -> List[str]:
        """Generate trading recommendations based on predictions"""
        recommendations = []
        
        if not predictions:
            return recommendations
        
        latest = predictions[-1]
        
        # Confidence-based recommendations
        if latest.confidence > 0.8:
            recommendations.append(f"High confidence {latest.price_direction} signal")
        elif latest.confidence < 0.3:
            recommendations.append("Low confidence - consider waiting")
        
        # Pattern-based recommendations
        if latest.pattern_detected in ['double_bottom', 'head_shoulders']:
            recommendations.append("Bullish reversal pattern detected")
        elif latest.pattern_detected in ['double_top']:
            recommendations.append("Bearish reversal pattern detected")
        elif latest.pattern_detected == 'breakout':
            recommendations.append("Breakout pattern - momentum trade opportunity")
        
        # Risk-based recommendations
        if latest.risk_assessment > 0.7:
            recommendations.append("High risk environment - reduce position size")
        elif latest.risk_assessment < 0.3:
            recommendations.append("Low risk environment - standard position sizing")
        
        return recommendations


# Global instance for easy access
_market_predictor = None

def get_market_predictor() -> AIMarketPredictor:
    """Get global market predictor instance"""
    global _market_predictor
    if _market_predictor is None:
        _market_predictor = AIMarketPredictor()
    return _market_predictor


# Example usage for testing
async def main():
    """Test the market predictor"""
    predictor = get_market_predictor()
    
    # Create sample data for testing
    dates = pd.date_range(start='2024-01-01', periods=1000, freq='1min')
    sample_data = pd.DataFrame({
        'open': np.random.randn(1000).cumsum() + 100,
        'high': np.random.randn(1000).cumsum() + 102,
        'low': np.random.randn(1000).cumsum() + 98,
        'close': np.random.randn(1000).cumsum() + 100,
        'volume': np.random.randint(1000, 10000, 1000)
    }, index=dates)
    
    # Test prediction
    print("🔮 Testing market prediction...")
    prediction = await predictor.predict_market_movement("BTCUSDT", sample_data)
    print(f"Prediction: {prediction.price_direction} ({prediction.confidence:.2f} confidence)")
    print(f"Pattern: {prediction.pattern_detected}")
    
    # Test insights
    insights = predictor.get_prediction_insights()
    print(f"Insights: {insights['status']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())