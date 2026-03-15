#!/usr/bin/env python3
"""
Advanced AI Orchestrator - Unified AI Decision Making System
Coordinates all AI models and makes unified trading decisions
Integrates sentiment analysis, market prediction, and existing ML systems
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
import traceback
from collections import deque, defaultdict
import math
import sys

# Import AI capability checker
try:
    from .ai_capability_checker import (
        AICapabilityChecker, get_capability_checker, check_ai_capabilities,
        enforce_smart_ai_requirements, CapabilityLevel
    )
    CAPABILITY_CHECKER_AVAILABLE = True
except ImportError:
    CAPABILITY_CHECKER_AVAILABLE = False

# Import smart fallbacks
try:
    from .ai_smart_fallbacks import (
        SmartSentimentAnalyzer, SmartMarketPredictor,
        get_smart_sentiment_fallback, get_smart_market_fallback,
        SmartSentimentResult, SmartPredictionResult
    )
    SMART_FALLBACKS_AVAILABLE = True
except ImportError:
    SMART_FALLBACKS_AVAILABLE = False

# Import AI components
try:
    from .ai_sentiment_analyzer import AISentimentAnalyzer, get_sentiment_analyzer, MarketSentimentSummary
    SENTIMENT_ANALYZER_AVAILABLE = True
except ImportError:
    SENTIMENT_ANALYZER_AVAILABLE = False

try:
    from .ai_market_predictor import AIMarketPredictor, get_market_predictor, MarketPrediction
    MARKET_PREDICTOR_AVAILABLE = True
except ImportError:
    MARKET_PREDICTOR_AVAILABLE = False

# Statistical and ML imports
try:
    from sklearn.ensemble import VotingClassifier, VotingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, mean_squared_error
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

@dataclass
class AISignal:
    """Comprehensive AI trading signal"""
    symbol: str
    timeframe: str
    signal_type: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0.0 to 1.0
    strength: float   # 0.0 to 100.0
    
    # Price targets
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    
    # AI components
    sentiment_score: float
    prediction_confidence: float
    ml_confidence: float
    
    # Risk assessment
    risk_level: str  # "LOW", "MODERATE", "HIGH", "EXTREME"
    position_size_multiplier: float
    leverage_recommendation: int
    
    # Technical factors
    trend_direction: str
    momentum_strength: float
    volatility_forecast: float
    pattern_detected: str
    
    # Market context
    market_regime: str
    news_impact: float
    correlation_factor: float
    
    # Execution parameters
    urgency: str  # "LOW", "NORMAL", "HIGH", "IMMEDIATE"
    hold_duration_estimate: int  # minutes
    expected_return: float
    
    # Metadata
    timestamp: datetime
    model_versions: Dict[str, str]
    reasoning: str

@dataclass
class AIDecisionContext:
    """Context for AI decision making"""
    market_conditions: Dict[str, Any]
    portfolio_state: Dict[str, Any]
    risk_parameters: Dict[str, Any]
    recent_performance: Dict[str, Any]
    external_factors: Dict[str, Any]

class AIOrchestrator:
    """
    Advanced AI Orchestrator for unified trading decisions
    Coordinates sentiment analysis, market prediction, and ML systems
    """

    def __init__(self, enforce_requirements: bool = True):
        self.logger = logging.getLogger(__name__)
        
        # Perform comprehensive capability check
        self.system_capability = None
        self.capability_checker = None
        
        if CAPABILITY_CHECKER_AVAILABLE:
            try:
                self.capability_checker = get_capability_checker()
                self.system_capability = self.capability_checker.check_system_capabilities()
                
                # Enforce smart analysis requirements if requested
                if enforce_requirements:
                    if not self.capability_checker.enforce_smart_analysis_requirements(self.system_capability):
                        error_msg = (
                            "❌ CRITICAL: AI Orchestrator cannot start - Smart analysis requirements not met!\n"
                            "The system requires genuine AI-powered analysis capabilities.\n"
                            "Please install required dependencies and try again."
                        )
                        self.logger.critical(error_msg)
                        raise RuntimeError(error_msg)
                
                self.degraded_mode_info = self.capability_checker.get_degraded_mode_info(self.system_capability)
                
            except Exception as e:
                if enforce_requirements:
                    raise
                self.logger.warning(f"⚠️ Capability check failed: {e}")
        else:
            self.logger.warning("⚠️ Capability checker not available - running without validation")
        
        # Initialize AI components based on capability assessment
        self.sentiment_analyzer = None
        self.market_predictor = None
        
        # Initialize sentiment analyzer
        if SENTIMENT_ANALYZER_AVAILABLE and self._is_component_available('sentiment_analysis'):
            try:
                self.sentiment_analyzer = get_sentiment_analyzer()
                self.logger.info("✅ Sentiment Analyzer initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ Sentiment Analyzer initialization failed: {e}")
                if enforce_requirements and self._is_component_critical('sentiment_analysis'):
                    raise RuntimeError(f"Critical sentiment analysis component failed: {e}")
        elif self._has_fallback('sentiment_analysis'):
            self.logger.info("🔄 Sentiment Analyzer running in fallback mode")
        else:
            self.logger.error("❌ Sentiment Analyzer unavailable")
            if enforce_requirements:
                raise RuntimeError("Critical sentiment analysis component unavailable")
        
        # Initialize market predictor
        if MARKET_PREDICTOR_AVAILABLE and self._is_component_available('market_prediction'):
            try:
                self.market_predictor = get_market_predictor()
                self.logger.info("✅ Market Predictor initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ Market Predictor initialization failed: {e}")
                if enforce_requirements and self._is_component_critical('market_prediction'):
                    raise RuntimeError(f"Critical market prediction component failed: {e}")
        elif self._has_fallback('market_prediction'):
            self.logger.info("🔄 Market Predictor running in fallback mode")
        else:
            self.logger.error("❌ Market Predictor unavailable")
            if enforce_requirements:
                raise RuntimeError("Critical market prediction component unavailable")
        
        # Database for storing AI decisions
        self.db_path = "SignalMaestro/ai_orchestrator.db"
        self._initialize_database()
        
        # Decision tracking
        self.decision_history = deque(maxlen=1000)
        self.performance_metrics = {
            'total_signals': 0,
            'successful_signals': 0,
            'accuracy': 0.0,
            'avg_return': 0.0,
            'avg_confidence': 0.0,
            'risk_adjusted_return': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'last_updated': None
        }
        
        # Adjust model weights based on capability level
        self.model_weights = self._calculate_adaptive_weights()
        
        # Decision thresholds
        self.decision_thresholds = {
            'min_confidence': 0.65,
            'high_confidence': 0.80,
            'sentiment_threshold': 0.3,
            'prediction_threshold': 0.7,
            'consensus_requirement': 0.75
        }
        
        # Risk management parameters
        self.risk_parameters = {
            'max_position_risk': 0.05,  # 5% max risk per position
            'max_portfolio_risk': 0.20, # 20% max portfolio risk
            'correlation_limit': 0.70,  # Max correlation between positions
            'volatility_multiplier': 1.0,
            'news_impact_multiplier': 1.0
        }
        
        # Market regime detection
        self.market_regimes = {
            'bull_market': {'sentiment_min': 0.3, 'trend_min': 0.6, 'volatility_max': 0.03},
            'bear_market': {'sentiment_max': -0.3, 'trend_max': -0.6, 'volatility_max': 0.05},
            'sideways': {'sentiment_range': [-0.3, 0.3], 'trend_range': [-0.3, 0.3]},
            'high_volatility': {'volatility_min': 0.05},
            'low_volatility': {'volatility_max': 0.02}
        }
        
        # Reinforcement learning concepts
        self.rl_state_space = {
            'market_sentiment': 0.0,
            'trend_strength': 0.0,
            'volatility': 0.0,
            'momentum': 0.0,
            'volume': 0.0,
            'news_impact': 0.0,
            'portfolio_pnl': 0.0,
            'risk_exposure': 0.0
        }
        
        self.action_space = {
            'BUY': {'weight': 1.0, 'success_rate': 0.0, 'avg_return': 0.0},
            'SELL': {'weight': 1.0, 'success_rate': 0.0, 'avg_return': 0.0},
            'HOLD': {'weight': 1.0, 'success_rate': 0.0, 'avg_return': 0.0}
        }
        
        # Load historical performance
        self._load_performance_metrics()
        
        # Log initialization summary
        self._log_initialization_summary()
        
        self.logger.info("🎼 AI Orchestrator initialized successfully")

    def _initialize_database(self):
        """Initialize AI orchestrator database"""
        try:
            Path("SignalMaestro").mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # AI signals table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    strength REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL NOT NULL,
                    take_profit_2 REAL NOT NULL,
                    take_profit_3 REAL NOT NULL,
                    sentiment_score REAL NOT NULL,
                    prediction_confidence REAL NOT NULL,
                    ml_confidence REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    position_size_multiplier REAL NOT NULL,
                    leverage_recommendation INTEGER NOT NULL,
                    trend_direction TEXT NOT NULL,
                    momentum_strength REAL NOT NULL,
                    volatility_forecast REAL NOT NULL,
                    pattern_detected TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    news_impact REAL NOT NULL,
                    urgency TEXT NOT NULL,
                    hold_duration_estimate INTEGER NOT NULL,
                    expected_return REAL NOT NULL,
                    reasoning TEXT NOT NULL,
                    actual_return REAL,
                    signal_accuracy REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
            ''')

            # AI performance table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_signals INTEGER NOT NULL,
                    successful_signals INTEGER NOT NULL,
                    accuracy REAL NOT NULL,
                    avg_return REAL NOT NULL,
                    avg_confidence REAL NOT NULL,
                    risk_adjusted_return REAL NOT NULL,
                    sharpe_ratio REAL NOT NULL,
                    max_drawdown REAL NOT NULL,
                    win_rate REAL NOT NULL,
                    model_weights TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Market regime table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_regimes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    regime_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    duration_minutes INTEGER,
                    characteristics TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                )
            ''')

            conn.commit()
            conn.close()
            self.logger.info("📊 AI Orchestrator database initialized")

        except Exception as e:
            self.logger.error(f"❌ Database initialization failed: {e}")

    async def generate_ai_signal(self, symbol: str, market_data: pd.DataFrame, 
                                current_ml_analysis: Optional[Dict[str, Any]] = None,
                                timeframe: str = "1m") -> Optional[AISignal]:
        """
        Generate comprehensive AI trading signal by orchestrating all AI components
        
        Args:
            symbol: Trading symbol
            market_data: Historical market data
            current_ml_analysis: Existing ML analysis from ultimate_trading_bot
            timeframe: Trading timeframe
            
        Returns:
            AISignal with comprehensive trading recommendation
        """
        try:
            self.logger.info(f"🎼 Generating AI signal for {symbol}")
            
            # Gather AI components data
            sentiment_data = await self._get_sentiment_analysis(symbol)
            prediction_data = await self._get_market_prediction(symbol, market_data, timeframe)
            market_regime = self._detect_market_regime(market_data, sentiment_data)
            
            # Combine with existing ML analysis
            if current_ml_analysis is None:
                current_ml_analysis = self._create_fallback_ml_analysis()
            
            # Create decision context
            context = self._create_decision_context(
                market_data, sentiment_data, prediction_data, current_ml_analysis
            )
            
            # Generate unified signal
            ai_signal = await self._orchestrate_decision(
                symbol, timeframe, market_data, sentiment_data, 
                prediction_data, current_ml_analysis, context
            )
            
            if ai_signal:
                # Store signal
                await self._store_ai_signal(ai_signal)
                
                # Update tracking
                self.decision_history.append(ai_signal)
                self.performance_metrics['total_signals'] += 1
                
                # Adaptive learning
                await self._update_model_weights(ai_signal, context)
                
                self.logger.info(f"✅ AI signal generated: {ai_signal.signal_type} ({ai_signal.confidence:.2f} confidence)")
                
            return ai_signal
            
        except Exception as e:
            self.logger.error(f"❌ AI signal generation failed: {e}")
            return None

    async def _get_sentiment_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get sentiment analysis data"""
        try:
            if self.sentiment_analyzer is None:
                return await self._create_smart_fallback_sentiment(symbol)
            
            # Get general market sentiment
            market_sentiment = await self.sentiment_analyzer.analyze_market_sentiment()
            
            # Get symbol-specific sentiment
            symbol_sentiment = self.sentiment_analyzer.get_symbol_sentiment(symbol)
            
            # Get overall insights
            insights = self.sentiment_analyzer.get_sentiment_insights()
            
            return {
                'overall_sentiment': market_sentiment.overall_sentiment,
                'confidence': market_sentiment.confidence,
                'symbol_sentiment': symbol_sentiment.get('current_sentiment', 0.0),
                'symbol_trend': symbol_sentiment.get('trend', 'neutral'),
                'market_bias': insights.get('market_bias', 'neutral'),
                'fear_greed_index': market_sentiment.fear_greed_index,
                'risk_level': market_sentiment.market_risk_level,
                'news_volume': market_sentiment.news_volume,
                'trending_themes': market_sentiment.trending_themes,
                'signal_recommendation': insights.get('signal_recommendation', 'hold')
            }
            
        except Exception as e:
            self.logger.error(f"❌ Sentiment analysis failed: {e}")
            return await self._create_smart_fallback_sentiment(symbol)

    async def _get_market_prediction(self, symbol: str, market_data: pd.DataFrame, 
                                   timeframe: str) -> Optional[Dict[str, Any]]:
        """Get market prediction data"""
        try:
            if self.market_predictor is None:
                return await self._create_smart_fallback_prediction(symbol, market_data, timeframe)
            
            # Get short-term prediction (15 minutes)
            short_prediction = await self.market_predictor.predict_market_movement(
                symbol, market_data, timeframe, horizon=15
            )
            
            # Get medium-term prediction (60 minutes)
            medium_prediction = await self.market_predictor.predict_market_movement(
                symbol, market_data, timeframe, horizon=60
            )
            
            # Get prediction insights
            insights = self.market_predictor.get_prediction_insights()
            
            return {
                'short_term_direction': short_prediction.price_direction,
                'short_term_confidence': short_prediction.confidence,
                'short_term_price': short_prediction.predicted_price,
                'medium_term_direction': medium_prediction.price_direction,
                'medium_term_confidence': medium_prediction.confidence,
                'medium_term_price': medium_prediction.predicted_price,
                'volatility_forecast': short_prediction.volatility_prediction,
                'trend_strength': short_prediction.trend_strength,
                'momentum_score': short_prediction.momentum_score,
                'pattern_detected': short_prediction.pattern_detected,
                'support_levels': short_prediction.support_levels,
                'resistance_levels': short_prediction.resistance_levels,
                'risk_assessment': short_prediction.risk_assessment,
                'model_performance': insights.get('model_performance', {}),
                'recommendations': insights.get('recommendations', [])
            }
            
        except Exception as e:
            self.logger.error(f"❌ Market prediction failed: {e}")
            return await self._create_smart_fallback_prediction(symbol, market_data, timeframe)

    def _detect_market_regime(self, market_data: pd.DataFrame, 
                            sentiment_data: Optional[Dict[str, Any]]) -> str:
        """Detect current market regime"""
        try:
            if len(market_data) < 50:
                return "insufficient_data"
            
            # Calculate market metrics
            returns = market_data['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(1440)  # Annualized volatility
            trend = (market_data['close'].iloc[-1] - market_data['close'].iloc[-50]) / market_data['close'].iloc[-50]
            
            sentiment_score = sentiment_data.get('overall_sentiment', 0.0) if sentiment_data else 0.0
            
            # Check regime conditions
            if (sentiment_score > 0.3 and trend > 0.1 and volatility < 0.03):
                return "bull_market"
            elif (sentiment_score < -0.3 and trend < -0.1 and volatility < 0.05):
                return "bear_market"
            elif (volatility > 0.05):
                return "high_volatility"
            elif (volatility < 0.02):
                return "low_volatility"
            elif (abs(trend) < 0.05 and abs(sentiment_score) < 0.3):
                return "sideways"
            else:
                return "transitional"
                
        except Exception as e:
            self.logger.error(f"❌ Market regime detection failed: {e}")
            return "unknown"

    def _create_decision_context(self, market_data: pd.DataFrame, 
                               sentiment_data: Optional[Dict[str, Any]],
                               prediction_data: Optional[Dict[str, Any]],
                               ml_analysis: Dict[str, Any]) -> AIDecisionContext:
        """Create comprehensive decision context"""
        try:
            current_price = float(market_data['close'].iloc[-1])
            
            # Market conditions
            market_conditions = {
                'current_price': current_price,
                'volatility': prediction_data.get('volatility_forecast', 0.02) if prediction_data else 0.02,
                'trend_strength': prediction_data.get('trend_strength', 0.0) if prediction_data else 0.0,
                'volume_trend': self._calculate_volume_trend(market_data),
                'support_resistance_ratio': self._calculate_sr_ratio(prediction_data) if prediction_data else 0.0,
                'market_regime': self._detect_market_regime(market_data, sentiment_data)
            }
            
            # Portfolio state (simplified - would integrate with actual portfolio)
            portfolio_state = {
                'current_exposure': 0.0,
                'available_capital': 1.0,
                'open_positions': 0,
                'correlation_risk': 0.0
            }
            
            # Risk parameters
            risk_parameters = {
                'market_risk': sentiment_data.get('risk_level', 'MODERATE') if sentiment_data else 'MODERATE',
                'volatility_risk': 'HIGH' if market_conditions['volatility'] > 0.04 else 'MODERATE',
                'news_risk': 'HIGH' if (sentiment_data and sentiment_data.get('news_volume', 0) > 20) else 'LOW',
                'correlation_risk': 'LOW'
            }
            
            # Recent performance
            recent_performance = {
                'recent_accuracy': self.performance_metrics.get('accuracy', 0.0),
                'recent_returns': self.performance_metrics.get('avg_return', 0.0),
                'confidence_level': self.performance_metrics.get('avg_confidence', 0.0)
            }
            
            # External factors
            external_factors = {
                'sentiment_momentum': sentiment_data.get('overall_sentiment', 0.0) if sentiment_data else 0.0,
                'news_impact': min(1.0, sentiment_data.get('news_volume', 0) / 50.0) if sentiment_data else 0.0,
                'time_of_day': datetime.now().hour,
                'day_of_week': datetime.now().weekday()
            }
            
            return AIDecisionContext(
                market_conditions=market_conditions,
                portfolio_state=portfolio_state,
                risk_parameters=risk_parameters,
                recent_performance=recent_performance,
                external_factors=external_factors
            )
            
        except Exception as e:
            self.logger.error(f"❌ Decision context creation failed: {e}")
            return self._create_fallback_context()

    async def _orchestrate_decision(self, symbol: str, timeframe: str, 
                                  market_data: pd.DataFrame,
                                  sentiment_data: Optional[Dict[str, Any]],
                                  prediction_data: Optional[Dict[str, Any]],
                                  ml_analysis: Dict[str, Any],
                                  context: AIDecisionContext) -> Optional[AISignal]:
        """Orchestrate final trading decision using all AI components"""
        try:
            # Extract current price and basic info
            current_price = float(market_data['close'].iloc[-1])
            
            # Calculate component scores (handle None values)
            sentiment_score = self._calculate_sentiment_score(sentiment_data or {})
            prediction_score = self._calculate_prediction_score(prediction_data or {})
            ml_score = self._calculate_ml_score(ml_analysis)
            technical_score = self._calculate_technical_score(market_data)
            
            # Apply weights
            weighted_score = (
                sentiment_score * self.model_weights['sentiment_weight'] +
                prediction_score * self.model_weights['prediction_weight'] +
                ml_score * self.model_weights['ml_existing_weight'] +
                technical_score * self.model_weights['technical_weight']
            )
            
            # Determine signal type
            signal_type = "HOLD"
            if weighted_score > self.decision_thresholds['high_confidence']:
                signal_type = "BUY"
            elif weighted_score < -self.decision_thresholds['high_confidence']:
                signal_type = "SELL"
            elif abs(weighted_score) > self.decision_thresholds['min_confidence']:
                signal_type = "BUY" if weighted_score > 0 else "SELL"
            
            # Calculate confidence
            confidence = min(1.0, abs(weighted_score))
            
            # Check consensus requirement
            component_agreement = self._check_component_consensus(
                sentiment_score, prediction_score, ml_score, technical_score
            )
            
            if component_agreement < self.decision_thresholds['consensus_requirement']:
                signal_type = "HOLD"
                confidence *= 0.5  # Reduce confidence for low consensus
            
            # Skip low confidence signals
            if confidence < self.decision_thresholds['min_confidence'] and signal_type != "HOLD":
                return None
            
            # Calculate price targets using multiple methods
            price_targets = self._calculate_price_targets(
                current_price, signal_type, prediction_data or {}, context
            )
            
            # Calculate risk level
            risk_level = self._calculate_risk_level(context, confidence)
            
            # Determine position sizing and leverage
            position_multiplier, leverage = self._calculate_position_parameters(
                confidence, risk_level, context
            )
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                sentiment_score, prediction_score, ml_score, technical_score,
                component_agreement, context
            )
            
            # Create AI signal
            ai_signal = AISignal(
                symbol=symbol,
                timeframe=timeframe,
                signal_type=signal_type,
                confidence=confidence,
                strength=abs(weighted_score) * 100,
                
                entry_price=current_price,
                stop_loss=price_targets['stop_loss'],
                take_profit_1=price_targets['tp1'],
                take_profit_2=price_targets['tp2'],
                take_profit_3=price_targets['tp3'],
                
                sentiment_score=sentiment_score,
                prediction_confidence=prediction_score,
                ml_confidence=ml_score,
                
                risk_level=risk_level,
                position_size_multiplier=position_multiplier,
                leverage_recommendation=leverage,
                
                trend_direction=(prediction_data or {}).get('short_term_direction', 'sideways'),
                momentum_strength=(prediction_data or {}).get('momentum_score', 0.0),
                volatility_forecast=(prediction_data or {}).get('volatility_forecast', 0.02),
                pattern_detected=(prediction_data or {}).get('pattern_detected', 'none'),
                
                market_regime=context.market_conditions['market_regime'],
                news_impact=context.external_factors['news_impact'],
                correlation_factor=0.0,  # Would be calculated with actual portfolio
                
                urgency=self._determine_urgency(confidence, signal_type, context),
                hold_duration_estimate=self._estimate_hold_duration(prediction_data or {}, context),
                expected_return=self._calculate_expected_return(signal_type, confidence, context),
                
                timestamp=datetime.now(),
                model_versions={
                    'sentiment_analyzer': '1.0',
                    'market_predictor': '1.0',
                    'orchestrator': '1.0'
                },
                reasoning=reasoning
            )
            
            return ai_signal
            
        except Exception as e:
            self.logger.error(f"❌ Decision orchestration failed: {e}")
            return None

    def _calculate_sentiment_score(self, sentiment_data: Dict[str, Any]) -> float:
        """Calculate normalized sentiment score"""
        try:
            overall_sentiment = sentiment_data.get('overall_sentiment', 0.0)
            confidence = sentiment_data.get('confidence', 0.0)
            symbol_sentiment = sentiment_data.get('symbol_sentiment', 0.0)
            
            # Combine different sentiment signals
            weighted_sentiment = (
                overall_sentiment * 0.4 +
                symbol_sentiment * 0.6
            )
            
            # Apply confidence weighting
            final_score = weighted_sentiment * confidence
            
            return max(-1.0, min(1.0, final_score))
            
        except Exception:
            return 0.0

    def _calculate_prediction_score(self, prediction_data: Dict[str, Any]) -> float:
        """Calculate normalized prediction score"""
        try:
            short_direction = prediction_data.get('short_term_direction', 'sideways')
            short_confidence = prediction_data.get('short_term_confidence', 0.0)
            medium_direction = prediction_data.get('medium_term_direction', 'sideways')
            medium_confidence = prediction_data.get('medium_term_confidence', 0.0)
            
            # Convert directions to scores
            direction_map = {'up': 1.0, 'down': -1.0, 'sideways': 0.0}
            
            short_score = direction_map.get(short_direction, 0.0) * short_confidence
            medium_score = direction_map.get(medium_direction, 0.0) * medium_confidence
            
            # Weight short-term more heavily
            final_score = short_score * 0.7 + medium_score * 0.3
            
            return max(-1.0, min(1.0, final_score))
            
        except Exception:
            return 0.0

    def _calculate_ml_score(self, ml_analysis: Dict[str, Any]) -> float:
        """Calculate normalized ML score from existing system"""
        try:
            ml_confidence = ml_analysis.get('ml_confidence', 0.0)
            ml_prediction = ml_analysis.get('ml_prediction', 'neutral')
            
            # Convert ML prediction to score
            if ml_prediction in ['highly_favorable', 'favorable']:
                base_score = 0.8 if ml_prediction == 'highly_favorable' else 0.5
            elif ml_prediction in ['unfavorable', 'highly_unfavorable']:
                base_score = -0.5 if ml_prediction == 'unfavorable' else -0.8
            else:
                base_score = 0.0
            
            # Apply confidence
            final_score = base_score * (ml_confidence / 100.0)
            
            return max(-1.0, min(1.0, final_score))
            
        except Exception:
            return 0.0

    def _calculate_technical_score(self, market_data: pd.DataFrame) -> float:
        """Calculate technical analysis score"""
        try:
            if len(market_data) < 20:
                return 0.0
            
            # Use pandas operations to avoid numpy type issues
            close_series = market_data['close']
            
            # Calculate simple technical indicators
            sma_20 = close_series.tail(20).mean()
            current_price = float(close_series.iloc[-1])
            
            # Price relative to moving average
            price_ma_ratio = (current_price - sma_20) / sma_20
            
            # Recent momentum
            momentum = (current_price - float(close_series.iloc[-5])) / float(close_series.iloc[-5])
            
            # Volume trend (if available)
            volume_score = 0.0
            if 'volume' in market_data.columns:
                recent_volume = market_data['volume'].tail(5).mean()
                avg_volume = market_data['volume'].tail(20).mean()
                if avg_volume != 0:
                    volume_score = (recent_volume - avg_volume) / avg_volume
            
            # Combine scores
            technical_score = (
                price_ma_ratio * 0.4 +
                momentum * 0.4 +
                volume_score * 0.2
            )
            
            return max(-1.0, min(1.0, technical_score))
            
        except Exception:
            return 0.0

    def _check_component_consensus(self, sentiment_score: float, prediction_score: float, 
                                 ml_score: float, technical_score: float) -> float:
        """Check consensus between different AI components"""
        try:
            scores = [sentiment_score, prediction_score, ml_score, technical_score]
            
            # Count agreements
            positive_count = sum(1 for s in scores if s > 0.1)
            negative_count = sum(1 for s in scores if s < -0.1)
            neutral_count = sum(1 for s in scores if abs(s) <= 0.1)
            
            total_components = len(scores)
            
            # Calculate consensus based on agreement
            if positive_count >= 3:
                consensus = positive_count / total_components
            elif negative_count >= 3:
                consensus = negative_count / total_components
            else:
                # Mixed signals - low consensus
                consensus = max(positive_count, negative_count) / total_components
            
            return consensus
            
        except Exception:
            return 0.0

    def _calculate_price_targets(self, current_price: float, signal_type: str,
                               prediction_data: Dict[str, Any],
                               context: AIDecisionContext) -> Dict[str, float]:
        """Calculate price targets based on AI analysis"""
        try:
            volatility = prediction_data.get('volatility_forecast', 0.02)
            support_levels = prediction_data.get('support_levels', [])
            resistance_levels = prediction_data.get('resistance_levels', [])
            
            if signal_type == "BUY":
                # Stop loss below support or using volatility
                if support_levels:
                    stop_loss = min(support_levels) * 0.995  # 0.5% below support
                else:
                    stop_loss = current_price * (1 - volatility * 2)
                
                # Take profits above resistance or using volatility
                if resistance_levels:
                    tp1 = resistance_levels[0] if len(resistance_levels) > 0 else current_price * 1.01
                    tp2 = resistance_levels[1] if len(resistance_levels) > 1 else current_price * 1.02
                    tp3 = resistance_levels[2] if len(resistance_levels) > 2 else current_price * 1.03
                else:
                    tp1 = current_price * (1 + volatility * 1.5)
                    tp2 = current_price * (1 + volatility * 2.5)
                    tp3 = current_price * (1 + volatility * 4.0)
                    
            elif signal_type == "SELL":
                # Stop loss above resistance or using volatility
                if resistance_levels:
                    stop_loss = max(resistance_levels) * 1.005  # 0.5% above resistance
                else:
                    stop_loss = current_price * (1 + volatility * 2)
                
                # Take profits below support or using volatility
                if support_levels:
                    tp1 = support_levels[0] if len(support_levels) > 0 else current_price * 0.99
                    tp2 = support_levels[1] if len(support_levels) > 1 else current_price * 0.98
                    tp3 = support_levels[2] if len(support_levels) > 2 else current_price * 0.97
                else:
                    tp1 = current_price * (1 - volatility * 1.5)
                    tp2 = current_price * (1 - volatility * 2.5)
                    tp3 = current_price * (1 - volatility * 4.0)
                    
            else:  # HOLD
                stop_loss = current_price
                tp1 = current_price
                tp2 = current_price
                tp3 = current_price
            
            return {
                'stop_loss': stop_loss,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3
            }
            
        except Exception as e:
            self.logger.error(f"❌ Price target calculation failed: {e}")
            return {
                'stop_loss': current_price,
                'tp1': current_price,
                'tp2': current_price,
                'tp3': current_price
            }

    def _calculate_risk_level(self, context: AIDecisionContext, confidence: float) -> str:
        """Calculate overall risk level"""
        try:
            market_risk = context.risk_parameters.get('market_risk', 'MODERATE')
            volatility_risk = context.risk_parameters.get('volatility_risk', 'MODERATE')
            news_risk = context.risk_parameters.get('news_risk', 'LOW')
            
            # Risk scoring
            risk_scores = {
                'LOW': 1,
                'MODERATE': 2,
                'HIGH': 3,
                'EXTREME': 4
            }
            
            total_risk = (
                risk_scores.get(market_risk, 2) +
                risk_scores.get(volatility_risk, 2) +
                risk_scores.get(news_risk, 1)
            )
            
            # Adjust based on confidence
            if confidence < 0.5:
                total_risk += 1
            elif confidence > 0.8:
                total_risk -= 1
            
            # Map back to risk levels
            if total_risk <= 3:
                return "LOW"
            elif total_risk <= 5:
                return "MODERATE"
            elif total_risk <= 7:
                return "HIGH"
            else:
                return "EXTREME"
                
        except Exception:
            return "MODERATE"

    def _calculate_position_parameters(self, confidence: float, risk_level: str,
                                     context: AIDecisionContext) -> Tuple[float, int]:
        """Calculate position size multiplier and leverage recommendation"""
        try:
            # Base position size based on confidence
            base_multiplier = confidence
            
            # Risk adjustments
            risk_multipliers = {
                'LOW': 1.2,
                'MODERATE': 1.0,
                'HIGH': 0.7,
                'EXTREME': 0.4
            }
            
            position_multiplier = base_multiplier * risk_multipliers.get(risk_level, 1.0)
            position_multiplier = max(0.1, min(2.0, position_multiplier))  # Cap between 0.1x and 2.0x
            
            # Leverage based on volatility and risk
            volatility = context.market_conditions.get('volatility', 0.02)
            
            if volatility < 0.01:
                base_leverage = 50
            elif volatility < 0.02:
                base_leverage = 30
            elif volatility < 0.04:
                base_leverage = 20
            else:
                base_leverage = 10
            
            # Risk adjustments for leverage
            if risk_level == 'HIGH':
                base_leverage = int(base_leverage * 0.7)
            elif risk_level == 'EXTREME':
                base_leverage = int(base_leverage * 0.5)
            elif risk_level == 'LOW':
                base_leverage = int(base_leverage * 1.2)
            
            leverage = max(5, min(75, base_leverage))  # Cap between 5x and 75x
            
            return position_multiplier, leverage
            
        except Exception:
            return 1.0, 20

    def _determine_urgency(self, confidence: float, signal_type: str, 
                         context: AIDecisionContext) -> str:
        """Determine signal urgency"""
        try:
            if signal_type == "HOLD":
                return "LOW"
            
            # High confidence signals are more urgent
            if confidence > 0.9:
                return "IMMEDIATE"
            elif confidence > 0.8:
                return "HIGH"
            elif confidence > 0.6:
                return "NORMAL"
            else:
                return "LOW"
                
        except Exception:
            return "NORMAL"

    def _estimate_hold_duration(self, prediction_data: Dict[str, Any], 
                              context: AIDecisionContext) -> int:
        """Estimate hold duration in minutes"""
        try:
            volatility = prediction_data.get('volatility_forecast', 0.02)
            pattern = prediction_data.get('pattern_detected', 'none')
            
            # Base duration based on volatility
            if volatility > 0.05:
                base_duration = 15  # High volatility - quick moves
            elif volatility > 0.03:
                base_duration = 30  # Medium volatility
            else:
                base_duration = 60  # Low volatility - longer moves
            
            # Pattern adjustments
            pattern_adjustments = {
                'breakout': 0.5,      # Quick moves
                'flag': 1.5,          # Continuation patterns take time
                'triangle': 2.0,      # Longer consolidation
                'double_top': 1.2,
                'double_bottom': 1.2,
                'head_shoulders': 2.0
            }
            
            multiplier = pattern_adjustments.get(pattern, 1.0)
            estimated_duration = int(base_duration * multiplier)
            
            return max(5, min(240, estimated_duration))  # Between 5 minutes and 4 hours
            
        except Exception:
            return 30

    def _calculate_expected_return(self, signal_type: str, confidence: float,
                                 context: AIDecisionContext) -> float:
        """Calculate expected return for the signal"""
        try:
            if signal_type == "HOLD":
                return 0.0
            
            # Base expected return based on confidence and volatility
            volatility = context.market_conditions.get('volatility', 0.02)
            base_return = volatility * confidence * 2  # Conservative estimate
            
            # Market regime adjustments
            regime = context.market_conditions.get('market_regime', 'unknown')
            regime_multipliers = {
                'bull_market': 1.3,
                'bear_market': 1.1,  # Short opportunities
                'high_volatility': 1.5,
                'low_volatility': 0.8,
                'sideways': 0.6
            }
            
            multiplier = regime_multipliers.get(regime, 1.0)
            expected_return = base_return * multiplier
            
            return max(0.001, min(0.1, expected_return))  # Between 0.1% and 10%
            
        except Exception:
            return 0.01

    def _generate_reasoning(self, sentiment_score: float, prediction_score: float,
                          ml_score: float, technical_score: float,
                          consensus: float, context: AIDecisionContext) -> str:
        """Generate human-readable reasoning for the signal"""
        try:
            reasons = []
            
            # Component analysis
            if abs(sentiment_score) > 0.3:
                direction = "positive" if sentiment_score > 0 else "negative"
                reasons.append(f"Market sentiment is {direction} ({sentiment_score:.2f})")
            
            if abs(prediction_score) > 0.3:
                direction = "bullish" if prediction_score > 0 else "bearish"
                reasons.append(f"AI prediction model is {direction} ({prediction_score:.2f})")
            
            if abs(ml_score) > 0.3:
                direction = "favorable" if ml_score > 0 else "unfavorable"
                reasons.append(f"Existing ML system shows {direction} conditions ({ml_score:.2f})")
            
            if abs(technical_score) > 0.3:
                direction = "bullish" if technical_score > 0 else "bearish"
                reasons.append(f"Technical indicators are {direction} ({technical_score:.2f})")
            
            # Consensus analysis
            if consensus > 0.75:
                reasons.append(f"High consensus between AI components ({consensus:.2f})")
            elif consensus < 0.5:
                reasons.append(f"Low consensus between AI components ({consensus:.2f})")
            
            # Market regime
            regime = context.market_conditions.get('market_regime', 'unknown')
            if regime != 'unknown':
                reasons.append(f"Market regime: {regime}")
            
            # Risk factors
            risk_level = context.risk_parameters.get('market_risk', 'MODERATE')
            if risk_level in ['HIGH', 'EXTREME']:
                reasons.append(f"Elevated market risk: {risk_level}")
            
            return "; ".join(reasons) if reasons else "Standard analysis applied"
            
        except Exception:
            return "AI analysis completed"

    async def _update_model_weights(self, signal: AISignal, context: AIDecisionContext):
        """Update model weights based on performance (reinforcement learning concept)"""
        try:
            # This would be implemented with actual performance feedback
            # For now, we'll do basic adaptive adjustments
            
            # Adjust weights based on recent performance
            if self.performance_metrics['accuracy'] > 0.7:
                # Good performance - maintain current weights
                pass
            elif self.performance_metrics['accuracy'] < 0.5:
                # Poor performance - adjust weights
                # Reduce weight of worst performing component
                component_scores = {
                    'sentiment': abs(signal.sentiment_score),
                    'prediction': abs(signal.prediction_confidence),
                    'ml': abs(signal.ml_confidence)
                }
                
                worst_component = min(component_scores.items(), key=lambda x: x[1])[0]
                
                if worst_component == 'sentiment':
                    self.model_weights['sentiment_weight'] *= 0.95
                elif worst_component == 'prediction':
                    self.model_weights['prediction_weight'] *= 0.95
                elif worst_component == 'ml':
                    self.model_weights['ml_existing_weight'] *= 0.95
                
                # Normalize weights
                total_weight = sum(self.model_weights.values())
                for key in self.model_weights:
                    self.model_weights[key] /= total_weight
            
        except Exception as e:
            self.logger.error(f"❌ Model weight update failed: {e}")

    async def _store_ai_signal(self, signal: AISignal):
        """Store AI signal in database"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO ai_signals (
                    symbol, timeframe, signal_type, confidence, strength,
                    entry_price, stop_loss, take_profit_1, take_profit_2, take_profit_3,
                    sentiment_score, prediction_confidence, ml_confidence,
                    risk_level, position_size_multiplier, leverage_recommendation,
                    trend_direction, momentum_strength, volatility_forecast, pattern_detected,
                    market_regime, news_impact, urgency, hold_duration_estimate,
                    expected_return, reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal.symbol, signal.timeframe, signal.signal_type, signal.confidence, signal.strength,
                signal.entry_price, signal.stop_loss, signal.take_profit_1, signal.take_profit_2, signal.take_profit_3,
                signal.sentiment_score, signal.prediction_confidence, signal.ml_confidence,
                signal.risk_level, signal.position_size_multiplier, signal.leverage_recommendation,
                signal.trend_direction, signal.momentum_strength, signal.volatility_forecast, signal.pattern_detected,
                signal.market_regime, signal.news_impact, signal.urgency, signal.hold_duration_estimate,
                signal.expected_return, signal.reasoning
            ))
            
            conn.commit()
            
        except Exception as e:
            self.logger.error(f"❌ AI signal storage failed: {e}")
        finally:
            if conn:
                conn.close()

    def get_orchestrator_insights(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator insights"""
        try:
            recent_signals = list(self.decision_history)[-10:] if self.decision_history else []
            
            if not recent_signals:
                return {'status': 'no_signals', 'insights': {}}
            
            # Calculate insights
            signal_types = [s.signal_type for s in recent_signals]
            avg_confidence = sum(s.confidence for s in recent_signals) / len(recent_signals)
            
            # Component performance
            avg_sentiment = sum(abs(s.sentiment_score) for s in recent_signals) / len(recent_signals)
            avg_prediction = sum(abs(s.prediction_confidence) for s in recent_signals) / len(recent_signals)
            avg_ml = sum(abs(s.ml_confidence) for s in recent_signals) / len(recent_signals)
            
            return {
                'status': 'active',
                'total_signals': len(self.decision_history),
                'recent_signals': len(recent_signals),
                'signal_distribution': {t: signal_types.count(t) for t in set(signal_types)},
                'avg_confidence': avg_confidence,
                'component_performance': {
                    'sentiment_strength': avg_sentiment,
                    'prediction_strength': avg_prediction,
                    'ml_strength': avg_ml
                },
                'model_weights': self.model_weights.copy(),
                'performance_metrics': self.performance_metrics.copy(),
                'last_signal': recent_signals[-1].timestamp.isoformat() if recent_signals else None
            }
            
        except Exception as e:
            self.logger.error(f"❌ Orchestrator insights failed: {e}")
            return {'status': 'error', 'insights': {}}

    async def _create_smart_fallback_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Create intelligent sentiment fallback using advanced local algorithms"""
        try:
            if not SMART_FALLBACKS_AVAILABLE:
                return self._create_basic_fallback_sentiment()
            
            # Use smart sentiment analyzer with synthetic market news analysis
            smart_analyzer = get_smart_sentiment_fallback()
            
            # Create sample market context for analysis
            market_context_samples = [
                f"{symbol} market analysis shows mixed signals with moderate volatility",
                f"Trading volume for {symbol} remains steady with neutral market sentiment",
                f"Technical indicators for {symbol} suggest consolidation phase",
                f"Market participants showing cautious optimism for {symbol} outlook",
                f"Recent {symbol} price action indicates sideways movement with support holding"
            ]
            
            # Analyze multiple context samples for robust sentiment
            sentiment_results = []
            for context in market_context_samples:
                result = smart_analyzer.analyze_text_sentiment(context, symbol)
                sentiment_results.append(result)
            
            # Aggregate results
            if sentiment_results:
                avg_sentiment = sum(r.sentiment_score for r in sentiment_results) / len(sentiment_results)
                avg_confidence = sum(r.confidence for r in sentiment_results) / len(sentiment_results)
                
                # Extract common themes
                all_themes = []
                for r in sentiment_results:
                    all_themes.extend(r.key_themes)
                
                # Get most common themes
                theme_counts = {}
                for theme in all_themes:
                    theme_counts[theme] = theme_counts.get(theme, 0) + 1
                
                trending_themes = [theme for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
                
                # Calculate market metrics
                fear_greed_index = max(0, min(100, (avg_sentiment + 1.0) * 50))
                
                # Determine risk level
                if avg_sentiment < -0.5:
                    risk_level = "HIGH"
                elif avg_sentiment < -0.2:
                    risk_level = "ELEVATED"
                elif avg_sentiment > 0.5:
                    risk_level = "LOW"
                else:
                    risk_level = "MODERATE"
                
                # Generate signal recommendation
                if avg_confidence > 0.6:
                    if avg_sentiment > 0.3:
                        signal_recommendation = "buy"
                    elif avg_sentiment < -0.3:
                        signal_recommendation = "sell"
                    else:
                        signal_recommendation = "hold"
                else:
                    signal_recommendation = "hold"
                
                return {
                    'overall_sentiment': avg_sentiment,
                    'confidence': avg_confidence,
                    'symbol_sentiment': avg_sentiment,
                    'symbol_trend': 'improving' if avg_sentiment > 0.1 else 'declining' if avg_sentiment < -0.1 else 'neutral',
                    'market_bias': 'bullish' if avg_sentiment > 0.2 else 'bearish' if avg_sentiment < -0.2 else 'neutral',
                    'fear_greed_index': fear_greed_index,
                    'risk_level': risk_level,
                    'news_volume': len(sentiment_results),
                    'trending_themes': trending_themes,
                    'signal_recommendation': signal_recommendation
                }
            
        except Exception as e:
            self.logger.error(f"❌ Smart sentiment fallback failed: {e}")
        
        # Final fallback to basic sentiment
        return self._create_basic_fallback_sentiment()
    
    async def _create_smart_fallback_prediction(self, symbol: str, market_data: pd.DataFrame, timeframe: str) -> Dict[str, Any]:
        """Create intelligent prediction fallback using advanced statistical methods"""
        try:
            if not SMART_FALLBACKS_AVAILABLE or market_data.empty:
                return self._create_basic_fallback_prediction()
            
            # Use smart market predictor
            smart_predictor = get_smart_market_fallback()
            
            # Get short-term prediction (15 minutes)
            short_prediction = smart_predictor.predict_market_movement(market_data, 15)
            
            # Get medium-term prediction (60 minutes) 
            medium_prediction = smart_predictor.predict_market_movement(market_data, 60)
            
            # Convert smart prediction results to orchestrator format
            return {
                'short_term_direction': short_prediction.direction,
                'short_term_confidence': short_prediction.confidence,
                'short_term_price': short_prediction.predicted_price,
                'medium_term_direction': medium_prediction.direction,
                'medium_term_confidence': medium_prediction.confidence,
                'medium_term_price': medium_prediction.predicted_price,
                'volatility_forecast': short_prediction.volatility_forecast,
                'trend_strength': short_prediction.trend_strength,
                'momentum_score': short_prediction.momentum_score,
                'pattern_detected': short_prediction.pattern_detected,
                'support_levels': short_prediction.support_levels,
                'resistance_levels': short_prediction.resistance_levels,
                'risk_assessment': (short_prediction.volatility_forecast + (1 - short_prediction.confidence)) / 2,
                'model_performance': {'model': 'smart_statistical_fallback', 'accuracy': short_prediction.confidence},
                'recommendations': [short_prediction.reasoning]
            }
            
        except Exception as e:
            self.logger.error(f"❌ Smart prediction fallback failed: {e}")
        
        # Final fallback to basic prediction
        return self._create_basic_fallback_prediction()

    def _create_basic_fallback_sentiment(self) -> Dict[str, Any]:
        """Create basic fallback sentiment data (final fallback)"""
        return {
            'overall_sentiment': 0.0,
            'confidence': 0.0,
            'symbol_sentiment': 0.0,
            'symbol_trend': 'neutral',
            'market_bias': 'neutral',
            'fear_greed_index': 50.0,
            'risk_level': 'MODERATE',
            'news_volume': 0,
            'trending_themes': [],
            'signal_recommendation': 'hold'
        }

    def _create_basic_fallback_prediction(self) -> Dict[str, Any]:
        """Create basic fallback prediction data (final fallback)"""
        return {
            'short_term_direction': 'sideways',
            'short_term_confidence': 0.0,
            'short_term_price': 0.0,
            'medium_term_direction': 'sideways',
            'medium_term_confidence': 0.0,
            'medium_term_price': 0.0,
            'volatility_forecast': 0.02,
            'trend_strength': 0.0,
            'momentum_score': 0.0,
            'pattern_detected': 'none',
            'support_levels': [],
            'resistance_levels': [],
            'risk_assessment': 0.5,
            'model_performance': {},
            'recommendations': []
        }

    def _create_fallback_ml_analysis(self) -> Dict[str, Any]:
        """Create fallback ML analysis"""
        return {
            'ml_confidence': 0.0,
            'ml_prediction': 'neutral',
            'model_accuracy': 0.0,
            'trades_learned_from': 0
        }

    def _create_fallback_context(self) -> AIDecisionContext:
        """Create fallback decision context"""
        return AIDecisionContext(
            market_conditions={
                'current_price': 0.0,
                'volatility': 0.02,
                'trend_strength': 0.0,
                'volume_trend': 0.0,
                'support_resistance_ratio': 0.0,
                'market_regime': 'unknown'
            },
            portfolio_state={
                'current_exposure': 0.0,
                'available_capital': 1.0,
                'open_positions': 0,
                'correlation_risk': 0.0
            },
            risk_parameters={
                'market_risk': 'MODERATE',
                'volatility_risk': 'MODERATE',
                'news_risk': 'LOW',
                'correlation_risk': 'LOW'
            },
            recent_performance={
                'recent_accuracy': 0.0,
                'recent_returns': 0.0,
                'confidence_level': 0.0
            },
            external_factors={
                'sentiment_momentum': 0.0,
                'news_impact': 0.0,
                'time_of_day': 12,
                'day_of_week': 1
            }
        )

    def _calculate_volume_trend(self, market_data: pd.DataFrame) -> float:
        """Calculate volume trend"""
        try:
            if 'volume' not in market_data.columns or len(market_data) < 20:
                return 0.0
            
            # Use pandas operations directly to avoid type confusion
            recent_volume = market_data['volume'].tail(5).mean()
            avg_volume = market_data['volume'].tail(20).mean()
            
            # Handle NaN values from empty/invalid calculations using .iloc to get scalar values
            recent_volume = float(recent_volume) if not pd.isna(recent_volume) else 0.0
            avg_volume = float(avg_volume) if not pd.isna(avg_volume) else 1.0
            
            return (recent_volume - avg_volume) / avg_volume
            
        except Exception:
            return 0.0

    def _calculate_sr_ratio(self, prediction_data: Dict[str, Any]) -> float:
        """Calculate support/resistance ratio"""
        try:
            support_levels = prediction_data.get('support_levels', [])
            resistance_levels = prediction_data.get('resistance_levels', [])
            
            if not support_levels and not resistance_levels:
                return 0.0
            
            support_count = len(support_levels)
            resistance_count = len(resistance_levels)
            
            if support_count + resistance_count == 0:
                return 0.0
            
            return (support_count - resistance_count) / (support_count + resistance_count)
            
        except Exception:
            return 0.0

    def _load_performance_metrics(self):
        """Load historical performance metrics"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM ai_performance ORDER BY created_at DESC LIMIT 1
            ''')
            
            result = cursor.fetchone()
            if result:
                # Update performance metrics with latest data
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, result))
                
                for key in self.performance_metrics:
                    if key in data:
                        self.performance_metrics[key] = data[key]
            
        except Exception as e:
            self.logger.debug(f"Performance metrics loading failed: {e}")
        finally:
            if conn:
                conn.close()
    
    def _is_component_available(self, component_name: str) -> bool:
        """Check if a component is available based on capability assessment"""
        if not self.system_capability:
            return True  # If no capability check, assume available
        
        component_result = self.system_capability.components.get(component_name)
        return component_result is not None and component_result.available
    
    def _is_component_critical(self, component_name: str) -> bool:
        """Check if a component is critical for smart analysis"""
        if not self.capability_checker:
            return True  # If no capability checker, assume all are critical
        
        return component_name in self.capability_checker.critical_components
    
    def _has_fallback(self, component_name: str) -> bool:
        """Check if a component has intelligent fallback available"""
        if not self.system_capability:
            return False
        
        component_result = self.system_capability.components.get(component_name)
        return component_result is not None and component_result.fallback_available
    
    def _calculate_adaptive_weights(self) -> Dict[str, float]:
        """Calculate model weights based on component availability"""
        base_weights = {
            'sentiment_weight': 0.25,
            'prediction_weight': 0.35,
            'ml_existing_weight': 0.25,
            'technical_weight': 0.15
        }
        
        if not self.system_capability:
            return base_weights
        
        # Adjust weights based on component availability and intelligence
        adjusted_weights = base_weights.copy()
        
        # Sentiment analysis adjustment
        sentiment_result = self.system_capability.components.get('sentiment_analysis')
        if sentiment_result:
            if not sentiment_result.available and sentiment_result.fallback_available:
                # Reduce sentiment weight if using fallback
                adjusted_weights['sentiment_weight'] *= 0.7
            elif not sentiment_result.available:
                # Remove sentiment weight if unavailable
                adjusted_weights['sentiment_weight'] = 0.0
        
        # Market prediction adjustment
        prediction_result = self.system_capability.components.get('market_prediction')
        if prediction_result:
            if not prediction_result.available and prediction_result.fallback_available:
                # Reduce prediction weight if using fallback
                adjusted_weights['prediction_weight'] *= 0.7
            elif not prediction_result.available:
                # Remove prediction weight if unavailable
                adjusted_weights['prediction_weight'] = 0.0
        
        # Normalize weights to sum to 1.0
        total_weight = sum(adjusted_weights.values())
        if total_weight > 0:
            for key in adjusted_weights:
                adjusted_weights[key] /= total_weight
        else:
            # Fallback to equal weights if all components failed
            adjusted_weights = {key: 1.0 / len(base_weights) for key in base_weights}
        
        return adjusted_weights
    
    def _log_initialization_summary(self):
        """Log comprehensive initialization summary"""
        try:
            if not self.system_capability:
                self.logger.info("🎼 AI Orchestrator initialized without capability assessment")
                return
            
            # Log system status
            level_emoji = {
                CapabilityLevel.FULL: "🟢",
                CapabilityLevel.DEGRADED: "🟡", 
                CapabilityLevel.FAILED: "🔴"
            }
            
            emoji = level_emoji.get(self.system_capability.level, "❓")
            self.logger.info(f"{emoji} System Status: {self.system_capability.level.value.upper()}")
            self.logger.info(f"🧠 Intelligence Score: {self.system_capability.intelligence_score:.2f}")
            self.logger.info(f"✨ Smart Analysis: {'ENABLED' if self.system_capability.can_provide_smart_analysis else 'DISABLED'}")
            
            # Log component statuses
            for component, result in self.system_capability.components.items():
                if result.available:
                    self.logger.info(f"✅ {component}: Active (intelligence: {result.intelligence_score:.2f})")
                elif result.fallback_available:
                    self.logger.info(f"🔄 {component}: Fallback mode (intelligence: {result.intelligence_score:.2f})")
                else:
                    self.logger.warning(f"❌ {component}: Unavailable")
            
            # Log model weights
            self.logger.info("⚖️ Adaptive Model Weights:")
            for component, weight in self.model_weights.items():
                self.logger.info(f"   {component}: {weight:.2f}")
            
            # Log any critical issues
            if self.system_capability.issues:
                self.logger.warning("⚠️ System Issues Detected:")
                for issue in self.system_capability.issues[:3]:  # Limit to first 3
                    self.logger.warning(f"   • {issue}")
                    
        except Exception as e:
            self.logger.error(f"❌ Initialization summary logging failed: {e}")


# Global instance for easy access
_ai_orchestrator = None

def get_ai_orchestrator() -> AIOrchestrator:
    """Get global AI orchestrator instance"""
    global _ai_orchestrator
    if _ai_orchestrator is None:
        _ai_orchestrator = AIOrchestrator()
    return _ai_orchestrator


# Example usage for testing
async def main():
    """Test the AI orchestrator"""
    orchestrator = get_ai_orchestrator()
    
    # Create sample market data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1min')
    sample_data = pd.DataFrame({
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)
    
    # Test signal generation
    print("🎼 Testing AI orchestrator...")
    ai_signal = await orchestrator.generate_ai_signal("BTCUSDT", sample_data)
    
    if ai_signal:
        print(f"Signal: {ai_signal.signal_type} ({ai_signal.confidence:.2f} confidence)")
        print(f"Reasoning: {ai_signal.reasoning}")
        print(f"Risk Level: {ai_signal.risk_level}")
    else:
        print("No signal generated")
    
    # Test insights
    insights = orchestrator.get_orchestrator_insights()
    print(f"Orchestrator Status: {insights['status']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())