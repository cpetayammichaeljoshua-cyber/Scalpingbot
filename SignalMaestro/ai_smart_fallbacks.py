#!/usr/bin/env python3
"""
AI Smart Fallbacks - Intelligent Local Analysis Models
Provides genuine AI-powered analysis without external dependencies
Uses advanced local algorithms for sentiment analysis and market prediction
"""

import logging
import re
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict, Counter
import json
from pathlib import Path

# Try to import advanced libraries, fall back to basic ones
try:
    from scipy import stats, signal
    from scipy.optimize import minimize
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

@dataclass
class SmartSentimentResult:
    """Smart sentiment analysis result using local algorithms"""
    sentiment_score: float  # -1.0 to 1.0
    confidence: float      # 0.0 to 1.0
    market_impact: float   # 0.0 to 1.0
    key_themes: List[str]
    relevance_score: float
    reasoning: str

@dataclass
class SmartPredictionResult:
    """Smart market prediction result using statistical models"""
    predicted_price: float
    confidence: float
    direction: str  # "up", "down", "sideways"
    volatility_forecast: float
    support_levels: List[float]
    resistance_levels: List[float]
    trend_strength: float
    momentum_score: float
    pattern_detected: str
    reasoning: str

class SmartSentimentAnalyzer:
    """
    Advanced rule-based sentiment analyzer with linguistic intelligence
    Uses sophisticated NLP techniques without external dependencies
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Advanced sentiment lexicons
        self.sentiment_lexicon = self._build_comprehensive_lexicon()
        self.crypto_specific_terms = self._build_crypto_lexicon()
        self.market_context_patterns = self._build_market_patterns()
        
        # Linguistic rules and patterns
        self.negation_patterns = [
            r'not\s+', r"n't\s+", r'no\s+', r'never\s+', r'nothing\s+',
            r'neither\s+', r'nobody\s+', r'nowhere\s+', r'hardly\s+', r'scarcely\s+'
        ]
        
        self.intensifier_patterns = {
            'very': 1.5, 'extremely': 2.0, 'incredibly': 2.0, 'amazingly': 1.8,
            'absolutely': 1.8, 'completely': 1.7, 'totally': 1.7, 'highly': 1.6,
            'significantly': 1.6, 'substantially': 1.5, 'considerably': 1.4,
            'quite': 1.3, 'rather': 1.2, 'somewhat': 1.1, 'slightly': 0.8,
            'barely': 0.6, 'hardly': 0.5, 'scarcely': 0.5
        }
        
        # Market-specific sentiment modifiers
        self.market_modifiers = {
            'bullish': 1.3, 'bearish': -1.3, 'volatile': -0.5, 'stable': 0.3,
            'optimistic': 1.2, 'pessimistic': -1.2, 'confident': 1.1, 'uncertain': -0.8,
            'positive': 1.0, 'negative': -1.0, 'neutral': 0.0
        }
        
        # Context-aware sentiment weights
        self.context_weights = {
            'price': 1.4, 'volume': 1.2, 'adoption': 1.3, 'regulation': 1.5,
            'technology': 1.2, 'partnership': 1.1, 'development': 1.1, 'security': 1.3
        }
        
    def analyze_text_sentiment(self, text: str, symbol: Optional[str] = None) -> SmartSentimentResult:
        """
        Perform intelligent sentiment analysis using advanced local algorithms
        """
        if not text or not text.strip():
            return self._create_neutral_result("Empty text provided")
        
        try:
            # Preprocess text
            processed_text = self._preprocess_text(text)
            
            # Extract linguistic features
            features = self._extract_linguistic_features(processed_text)
            
            # Calculate base sentiment
            base_sentiment = self._calculate_base_sentiment(processed_text, features)
            
            # Apply contextual modifiers
            context_sentiment = self._apply_contextual_modifiers(base_sentiment, processed_text, symbol)
            
            # Calculate market impact
            market_impact = self._calculate_market_impact(processed_text, context_sentiment)
            
            # Extract key themes
            key_themes = self._extract_key_themes(processed_text)
            
            # Calculate relevance to crypto/trading
            relevance_score = self._calculate_relevance(processed_text, key_themes)
            
            # Calculate confidence based on multiple factors
            confidence = self._calculate_sentiment_confidence(features, context_sentiment, relevance_score)
            
            # Generate reasoning
            reasoning = self._generate_sentiment_reasoning(context_sentiment, key_themes, features)
            
            # Ensure sentiment is within bounds
            final_sentiment = max(-1.0, min(1.0, context_sentiment))
            
            return SmartSentimentResult(
                sentiment_score=final_sentiment,
                confidence=confidence,
                market_impact=market_impact,
                key_themes=key_themes,
                relevance_score=relevance_score,
                reasoning=reasoning
            )
            
        except Exception as e:
            self.logger.error(f"❌ Smart sentiment analysis failed: {e}")
            return self._create_neutral_result(f"Analysis error: {str(e)}")
    
    def _build_comprehensive_lexicon(self) -> Dict[str, float]:
        """Build comprehensive sentiment lexicon with market-relevant terms"""
        lexicon = {
            # Extremely positive
            'excellent': 2.0, 'outstanding': 2.0, 'amazing': 1.8, 'incredible': 1.8,
            'phenomenal': 1.8, 'spectacular': 1.8, 'exceptional': 1.7, 'brilliant': 1.7,
            
            # Very positive
            'great': 1.5, 'fantastic': 1.5, 'wonderful': 1.4, 'impressive': 1.4,
            'strong': 1.3, 'solid': 1.2, 'good': 1.1, 'positive': 1.0,
            
            # Moderately positive
            'decent': 0.8, 'okay': 0.5, 'fair': 0.4, 'acceptable': 0.6,
            
            # Neutral
            'neutral': 0.0, 'average': 0.0, 'normal': 0.0, 'standard': 0.0,
            
            # Moderately negative
            'poor': -0.8, 'weak': -1.0, 'bad': -1.1, 'disappointing': -1.2,
            
            # Very negative
            'terrible': -1.5, 'horrible': -1.6, 'awful': -1.6, 'devastating': -1.7,
            'disastrous': -1.8, 'catastrophic': -2.0, 'abysmal': -2.0,
            
            # Market-specific terms
            'bullish': 1.4, 'bearish': -1.4, 'rally': 1.3, 'surge': 1.5,
            'pump': 1.2, 'dump': -1.4, 'crash': -1.8, 'correction': -0.8,
            'consolidation': 0.2, 'breakout': 1.3, 'breakdown': -1.3,
            'support': 0.8, 'resistance': -0.3, 'momentum': 1.1,
            'volatile': -0.5, 'stable': 0.6, 'liquid': 0.4, 'adoption': 1.2,
            'partnership': 1.1, 'innovation': 1.3, 'development': 1.0,
            'upgrade': 1.2, 'fork': -0.3, 'hack': -1.8, 'regulation': -0.8,
            'ban': -1.6, 'approval': 1.4, 'listing': 1.3, 'delisting': -1.5,
            'whale': -0.4, 'retail': 0.2, 'institutional': 1.0, 'etf': 1.2,
            'halving': 0.8, 'mining': 0.3, 'staking': 0.6, 'yield': 0.8,
            'defi': 0.9, 'nft': 0.5, 'metaverse': 0.7, 'web3': 0.8,
        }
        return lexicon
    
    def _build_crypto_lexicon(self) -> Dict[str, float]:
        """Build cryptocurrency-specific sentiment terms"""
        return {
            'hodl': 1.0, 'diamond_hands': 1.5, 'paper_hands': -1.2,
            'moon': 1.8, 'lambo': 1.6, 'rekt': -1.8, 'fud': -1.4,
            'fomo': 0.3, 'btfd': 1.2, 'ath': 1.5, 'atl': -1.5,
            'bull_run': 1.6, 'bear_market': -1.4, 'alt_season': 1.3,
            'accumulation': 1.1, 'distribution': -0.8, 'capitulation': -1.7,
            'hopium': 0.5, 'copium': -0.8, 'rugpull': -2.0, 'scam': -1.9,
            'legit': 1.2, 'solid_project': 1.4, 'vaporware': -1.6,
            'shill': -0.7, 'research': 0.8, 'fundamentals': 1.0,
            'technicals': 0.6, 'on_chain': 0.7, 'metrics': 0.5
        }
    
    def _build_market_patterns(self) -> List[Dict[str, Any]]:
        """Build market context patterns for better analysis"""
        return [
            {
                'pattern': r'price\s+(up|rising|increasing|surging|pumping)',
                'sentiment': 1.3, 'confidence': 0.8, 'context': 'price_movement'
            },
            {
                'pattern': r'price\s+(down|falling|declining|dumping|crashing)',
                'sentiment': -1.3, 'confidence': 0.8, 'context': 'price_movement'
            },
            {
                'pattern': r'volume\s+(high|increasing|surging)',
                'sentiment': 1.1, 'confidence': 0.7, 'context': 'volume'
            },
            {
                'pattern': r'volume\s+(low|decreasing|declining)',
                'sentiment': -0.6, 'confidence': 0.6, 'context': 'volume'
            },
            {
                'pattern': r'(new\s+)?(partnership|collaboration|integration)',
                'sentiment': 1.2, 'confidence': 0.9, 'context': 'partnerships'
            },
            {
                'pattern': r'(regulatory|regulation|ban|banned|illegal)',
                'sentiment': -1.1, 'confidence': 0.9, 'context': 'regulation'
            },
            {
                'pattern': r'(hack|hacked|exploit|vulnerability|breach)',
                'sentiment': -1.7, 'confidence': 0.95, 'context': 'security'
            },
            {
                'pattern': r'(adoption|mainstream|institutional|etf|approved)',
                'sentiment': 1.4, 'confidence': 0.9, 'context': 'adoption'
            }
        ]
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for better analysis"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove URLs
        text = re.sub(r'http[s]?://\S+', '', text)
        
        # Replace common crypto shorthand
        replacements = {
            'btc': 'bitcoin', 'eth': 'ethereum', 'btfd': 'buy the dip',
            'hodl': 'hold', 'fud': 'fear uncertainty doubt',
            'fomo': 'fear of missing out', 'ath': 'all time high',
            'atl': 'all time low', 'mcap': 'market cap'
        }
        
        for short, full in replacements.items():
            text = re.sub(r'\b' + short + r'\b', full, text)
        
        return text
    
    def _extract_linguistic_features(self, text: str) -> Dict[str, Any]:
        """Extract linguistic features from text"""
        features = {
            'word_count': len(text.split()),
            'sentence_count': len([s for s in text.split('.') if s.strip()]),
            'exclamation_count': text.count('!'),
            'question_count': text.count('?'),
            'caps_ratio': sum(1 for c in text if c.isupper()) / len(text) if text else 0,
            'negation_count': sum(1 for pattern in self.negation_patterns if re.search(pattern, text)),
            'intensifier_count': sum(1 for word in self.intensifier_patterns if word in text),
            'crypto_term_count': sum(1 for term in self.crypto_specific_terms if term.replace('_', ' ') in text),
            'market_term_count': sum(1 for term in self.market_modifiers if term in text)
        }
        
        # Calculate emotional intensity
        features['emotional_intensity'] = (
            features['exclamation_count'] * 0.3 +
            features['caps_ratio'] * 0.4 +
            features['intensifier_count'] * 0.3
        )
        
        return features
    
    def _calculate_base_sentiment(self, text: str, features: Dict[str, Any]) -> float:
        """Calculate base sentiment using lexicon and patterns"""
        words = text.split()
        sentiment_sum = 0.0
        sentiment_count = 0
        
        # Process each word
        for i, word in enumerate(words):
            # Check if word is in lexicon
            word_sentiment = 0.0
            
            if word in self.sentiment_lexicon:
                word_sentiment = self.sentiment_lexicon[word]
            elif word in self.crypto_specific_terms:
                word_sentiment = self.crypto_specific_terms[word]
            elif word in self.market_modifiers:
                word_sentiment = self.market_modifiers[word]
            
            if word_sentiment != 0.0:
                # Apply intensifiers
                intensifier_multiplier = 1.0
                if i > 0 and words[i-1] in self.intensifier_patterns:
                    intensifier_multiplier = self.intensifier_patterns[words[i-1]]
                
                # Apply negation
                negation_window = words[max(0, i-3):i]
                is_negated = any(re.search(pattern.strip(), ' '.join(negation_window)) 
                               for pattern in self.negation_patterns)
                
                if is_negated:
                    word_sentiment *= -0.8  # Invert and reduce intensity
                
                final_sentiment = word_sentiment * intensifier_multiplier
                sentiment_sum += final_sentiment
                sentiment_count += 1
        
        # Apply pattern-based sentiment
        for pattern_info in self.market_context_patterns:
            if re.search(pattern_info['pattern'], text):
                pattern_weight = pattern_info['confidence']
                sentiment_sum += pattern_info['sentiment'] * pattern_weight
                sentiment_count += 1
        
        # Calculate average sentiment
        if sentiment_count > 0:
            base_sentiment = sentiment_sum / sentiment_count
        else:
            base_sentiment = 0.0
        
        # Apply emotional intensity modifier
        intensity_modifier = 1.0 + (features['emotional_intensity'] * 0.2)
        return base_sentiment * intensity_modifier
    
    def _apply_contextual_modifiers(self, base_sentiment: float, text: str, symbol: Optional[str]) -> float:
        """Apply contextual modifiers based on market context"""
        modified_sentiment = base_sentiment
        
        # Symbol-specific modifiers
        if symbol and symbol.lower() in text:
            modified_sentiment *= 1.2  # Boost relevance for symbol-specific content
        
        # Context-based modifiers
        for context, weight in self.context_weights.items():
            if context.replace('_', ' ') in text:
                if base_sentiment > 0:
                    modified_sentiment *= weight
                else:
                    modified_sentiment *= (2.0 - weight)  # Inverse for negative sentiment
        
        return modified_sentiment
    
    def _calculate_market_impact(self, text: str, sentiment: float) -> float:
        """Calculate potential market impact of the sentiment"""
        impact_factors = {
            'regulation': 0.9, 'ban': 0.95, 'etf': 0.85, 'institutional': 0.8,
            'partnership': 0.7, 'hack': 0.9, 'listing': 0.75, 'delisting': 0.8,
            'upgrade': 0.6, 'fork': 0.7, 'halving': 0.8, 'adoption': 0.75
        }
        
        base_impact = abs(sentiment) * 0.5  # Base impact from sentiment strength
        
        # Add impact from specific terms
        for term, impact_boost in impact_factors.items():
            if term in text:
                base_impact = max(base_impact, impact_boost)
        
        return min(1.0, base_impact)
    
    def _extract_key_themes(self, text: str) -> List[str]:
        """Extract key themes from text using pattern matching"""
        themes = []
        
        theme_patterns = {
            'price_action': [r'price\s+(up|down|rising|falling)', r'(pump|dump|surge|crash)'],
            'volume': [r'volume\s+(high|low|increasing)', r'trading\s+volume'],
            'partnerships': [r'partnership', r'collaboration', r'integration'],
            'regulation': [r'regulat', r'ban', r'legal', r'compliance'],
            'technology': [r'upgrade', r'development', r'innovation', r'protocol'],
            'adoption': [r'adoption', r'mainstream', r'institutional', r'etf'],
            'market_sentiment': [r'bullish', r'bearish', r'optimistic', r'pessimistic'],
            'security': [r'hack', r'security', r'vulnerability', r'breach'],
            'fundamentals': [r'fundamental', r'utility', r'use\s+case', r'project']
        }
        
        for theme, patterns in theme_patterns.items():
            if any(re.search(pattern, text) for pattern in patterns):
                themes.append(theme)
        
        return themes[:5]  # Return top 5 themes
    
    def _calculate_relevance(self, text: str, themes: List[str]) -> float:
        """Calculate relevance to crypto/trading"""
        crypto_indicators = [
            'bitcoin', 'ethereum', 'crypto', 'blockchain', 'defi', 'nft',
            'trading', 'price', 'market', 'volume', 'bullish', 'bearish',
            'hodl', 'fomo', 'fud', 'moon', 'lambo', 'whale', 'pump', 'dump'
        ]
        
        relevance_score = 0.0
        total_words = len(text.split())
        
        if total_words == 0:
            return 0.0
        
        # Check for crypto-specific terms
        crypto_count = sum(1 for term in crypto_indicators if term in text)
        relevance_score += (crypto_count / total_words) * 2.0
        
        # Boost for relevant themes
        theme_boost = len(themes) * 0.15
        relevance_score += theme_boost
        
        # Pattern-based relevance
        trading_patterns = [
            r'(buy|sell|trade|invest)', r'(bull|bear)\s+market',
            r'(support|resistance)\s+level', r'technical\s+analysis'
        ]
        
        pattern_count = sum(1 for pattern in trading_patterns if re.search(pattern, text))
        relevance_score += pattern_count * 0.2
        
        return min(1.0, relevance_score)
    
    def _calculate_sentiment_confidence(self, features: Dict[str, Any], 
                                      sentiment: float, relevance: float) -> float:
        """Calculate confidence in sentiment analysis"""
        confidence = 0.5  # Base confidence
        
        # Boost confidence based on features
        if features['word_count'] >= 10:
            confidence += 0.1
        if features['crypto_term_count'] > 0:
            confidence += 0.15
        if features['market_term_count'] > 0:
            confidence += 0.1
        if relevance > 0.5:
            confidence += 0.15
        if abs(sentiment) > 0.5:
            confidence += 0.1
        
        # Reduce confidence for uncertainty indicators
        if features['question_count'] > features['sentence_count'] * 0.5:
            confidence -= 0.1
        if features['negation_count'] > 2:
            confidence -= 0.05
        
        return max(0.1, min(1.0, confidence))
    
    def _generate_sentiment_reasoning(self, sentiment: float, themes: List[str], 
                                    features: Dict[str, Any]) -> str:
        """Generate human-readable reasoning for sentiment"""
        reasoning_parts = []
        
        # Sentiment strength
        if abs(sentiment) > 0.7:
            strength = "strong"
        elif abs(sentiment) > 0.4:
            strength = "moderate"
        else:
            strength = "weak"
        
        direction = "positive" if sentiment > 0 else "negative" if sentiment < 0 else "neutral"
        reasoning_parts.append(f"{strength} {direction} sentiment detected")
        
        # Key themes
        if themes:
            reasoning_parts.append(f"key themes: {', '.join(themes[:3])}")
        
        # Notable features
        if features['crypto_term_count'] > 0:
            reasoning_parts.append(f"{features['crypto_term_count']} crypto-specific terms")
        
        if features['emotional_intensity'] > 0.3:
            reasoning_parts.append("high emotional intensity")
        
        return "; ".join(reasoning_parts)
    
    def _create_neutral_result(self, reason: str) -> SmartSentimentResult:
        """Create neutral sentiment result"""
        return SmartSentimentResult(
            sentiment_score=0.0,
            confidence=0.1,
            market_impact=0.0,
            key_themes=[],
            relevance_score=0.0,
            reasoning=reason
        )


class SmartMarketPredictor:
    """
    Advanced statistical market predictor using local algorithms
    Provides intelligent predictions without external dependencies
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Technical analysis parameters
        self.ta_params = {
            'sma_periods': [5, 10, 20, 50],
            'ema_periods': [12, 26, 50],
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'bb_period': 20,
            'bb_std': 2
        }
        
        # Pattern recognition parameters
        self.pattern_params = {
            'lookback_periods': 50,
            'min_pattern_length': 5,
            'similarity_threshold': 0.8,
            'trend_strength_threshold': 0.6
        }
    
    def predict_market_movement(self, market_data: pd.DataFrame, 
                              horizon_minutes: int = 15) -> SmartPredictionResult:
        """
        Predict market movement using advanced statistical methods
        """
        try:
            if len(market_data) < 50:
                return self._create_insufficient_data_result("Insufficient historical data")
            
            # Calculate technical indicators
            indicators = self._calculate_technical_indicators(market_data)
            
            # Detect patterns
            patterns = self._detect_chart_patterns(market_data)
            primary_pattern = max(patterns.items(), key=lambda x: x[1]) if patterns else ("none", 0.0)
            
            # Calculate statistical predictions
            price_prediction = self._predict_price_statistically(market_data, indicators, horizon_minutes)
            
            # Determine trend and momentum
            trend_analysis = self._analyze_trend_momentum(market_data, indicators)
            
            # Calculate support and resistance
            support_resistance = self._calculate_smart_support_resistance(market_data)
            
            # Assess volatility
            volatility_forecast = self._forecast_volatility(market_data)
            
            # Calculate prediction confidence
            confidence = self._calculate_prediction_confidence(
                market_data, indicators, patterns, trend_analysis
            )
            
            # Determine price direction
            current_price = float(market_data['close'].iloc[-1])
            price_change = (price_prediction - current_price) / current_price
            
            if price_change > 0.002:  # 0.2% threshold
                direction = "up"
            elif price_change < -0.002:
                direction = "down"
            else:
                direction = "sideways"
            
            # Generate reasoning
            reasoning = self._generate_prediction_reasoning(
                direction, primary_pattern[0], trend_analysis, confidence
            )
            
            return SmartPredictionResult(
                predicted_price=price_prediction,
                confidence=confidence,
                direction=direction,
                volatility_forecast=volatility_forecast,
                support_levels=support_resistance['support'],
                resistance_levels=support_resistance['resistance'],
                trend_strength=trend_analysis['strength'],
                momentum_score=trend_analysis['momentum'],
                pattern_detected=primary_pattern[0],
                reasoning=reasoning
            )
            
        except Exception as e:
            self.logger.error(f"❌ Smart market prediction failed: {e}")
            return self._create_error_result(f"Prediction error: {str(e)}")
    
    def _calculate_technical_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive technical indicators"""
        indicators = {}
        
        try:
            # Simple Moving Averages
            for period in self.ta_params['sma_periods']:
                if len(df) >= period:
                    indicators[f'sma_{period}'] = df['close'].rolling(period).mean()
            
            # Exponential Moving Averages
            for period in self.ta_params['ema_periods']:
                if len(df) >= period:
                    indicators[f'ema_{period}'] = df['close'].ewm(span=period).mean()
            
            # RSI
            if len(df) >= self.ta_params['rsi_period']:
                indicators['rsi'] = self._calculate_rsi(df['close'], self.ta_params['rsi_period'])
            
            # MACD
            if len(df) >= self.ta_params['macd_slow']:
                macd_line, signal_line = self._calculate_macd(
                    df['close'], 
                    self.ta_params['macd_fast'],
                    self.ta_params['macd_slow'],
                    self.ta_params['macd_signal']
                )
                indicators['macd'] = macd_line
                indicators['macd_signal'] = signal_line
                indicators['macd_histogram'] = macd_line - signal_line
            
            # Bollinger Bands
            if len(df) >= self.ta_params['bb_period']:
                bb_middle = df['close'].rolling(self.ta_params['bb_period']).mean()
                bb_std = df['close'].rolling(self.ta_params['bb_period']).std()
                indicators['bb_upper'] = bb_middle + (bb_std * self.ta_params['bb_std'])
                indicators['bb_lower'] = bb_middle - (bb_std * self.ta_params['bb_std'])
                indicators['bb_middle'] = bb_middle
                indicators['bb_position'] = (df['close'] - indicators['bb_lower']) / (indicators['bb_upper'] - indicators['bb_lower'])
            
            # Volume indicators
            if 'volume' in df.columns:
                indicators['volume_sma'] = df['volume'].rolling(20).mean()
                indicators['volume_ratio'] = df['volume'] / indicators['volume_sma']
                indicators['price_volume'] = df['close'] * df['volume']
            
            # Volatility indicators
            indicators['returns'] = df['close'].pct_change()
            indicators['volatility'] = indicators['returns'].rolling(20).std()
            indicators['atr'] = self._calculate_atr(df)
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"❌ Technical indicators calculation failed: {e}")
            return {}
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices: pd.Series, fast: int = 12, 
                       slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series]:
        """Calculate MACD line and signal line"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        return macd_line, signal_line
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        atr = pd.Series(true_range).rolling(period).mean()
        return atr
    
    def _detect_chart_patterns(self, df: pd.DataFrame) -> Dict[str, float]:
        """Detect chart patterns using statistical methods"""
        patterns = {}
        
        if len(df) < self.pattern_params['lookback_periods']:
            return patterns
        
        try:
            # Use recent data for pattern detection
            recent_data = df.tail(self.pattern_params['lookback_periods'])
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values
            
            # Double top/bottom detection
            patterns['double_top'] = self._detect_double_top(highs, closes)
            patterns['double_bottom'] = self._detect_double_bottom(lows, closes)
            
            # Triangle patterns
            patterns['ascending_triangle'] = self._detect_ascending_triangle(highs, lows)
            patterns['descending_triangle'] = self._detect_descending_triangle(highs, lows)
            
            # Support/Resistance breakout
            patterns['breakout'] = self._detect_breakout(closes, highs, lows)
            
            # Trend channel
            patterns['channel'] = self._detect_channel(highs, lows, closes)
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"❌ Pattern detection failed: {e}")
            return {}
    
    def _detect_double_top(self, highs: np.ndarray, closes: np.ndarray) -> float:
        """Detect double top pattern"""
        if len(highs) < 20:
            return 0.0
        
        # Find local maxima
        if SCIPY_AVAILABLE:
            peaks, _ = signal.find_peaks(highs, distance=5, prominence=np.std(highs) * 0.5)
        else:
            # Simple peak detection fallback
            peaks = []
            for i in range(2, len(highs) - 2):
                if (highs[i] > highs[i-1] and highs[i] > highs[i+1] and
                    highs[i] > highs[i-2] and highs[i] > highs[i+2]):
                    peaks.append(i)
        
        if len(peaks) < 2:
            return 0.0
        
        # Check for double top characteristics
        for i in range(len(peaks) - 1):
            peak1_idx, peak2_idx = peaks[i], peaks[i + 1]
            peak1_price, peak2_price = highs[peak1_idx], highs[peak2_idx]
            
            # Peaks should be similar height
            height_similarity = 1 - abs(peak1_price - peak2_price) / max(peak1_price, peak2_price)
            
            if height_similarity > 0.95:  # 95% similar
                # Check if current price is below peaks
                current_price = closes[-1]
                if current_price < min(peak1_price, peak2_price) * 0.98:
                    return height_similarity
        
        return 0.0
    
    def _detect_double_bottom(self, lows: np.ndarray, closes: np.ndarray) -> float:
        """Detect double bottom pattern"""
        if len(lows) < 20:
            return 0.0
        
        # Find local minima
        inverted_lows = -lows
        if SCIPY_AVAILABLE:
            troughs, _ = signal.find_peaks(inverted_lows, distance=5, prominence=np.std(inverted_lows) * 0.5)
        else:
            # Simple trough detection fallback
            troughs = []
            for i in range(2, len(lows) - 2):
                if (lows[i] < lows[i-1] and lows[i] < lows[i+1] and
                    lows[i] < lows[i-2] and lows[i] < lows[i+2]):
                    troughs.append(i)
        
        if len(troughs) < 2:
            return 0.0
        
        # Check for double bottom characteristics
        for i in range(len(troughs) - 1):
            trough1_idx, trough2_idx = troughs[i], troughs[i + 1]
            trough1_price, trough2_price = lows[trough1_idx], lows[trough2_idx]
            
            # Troughs should be similar depth
            depth_similarity = 1 - abs(trough1_price - trough2_price) / max(trough1_price, trough2_price)
            
            if depth_similarity > 0.95:  # 95% similar
                # Check if current price is above troughs
                current_price = closes[-1]
                if current_price > max(trough1_price, trough2_price) * 1.02:
                    return depth_similarity
        
        return 0.0
    
    def _detect_ascending_triangle(self, highs: np.ndarray, lows: np.ndarray) -> float:
        """Detect ascending triangle pattern"""
        if len(highs) < 15:
            return 0.0
        
        try:
            recent_highs = highs[-15:]
            recent_lows = lows[-15:]
            
            # Check if highs are relatively flat (resistance)
            high_trend = np.polyfit(range(len(recent_highs)), recent_highs, 1)[0]
            high_flatness = 1 - abs(high_trend) / np.mean(recent_highs) * 100
            
            # Check if lows are ascending (support)
            low_trend = np.polyfit(range(len(recent_lows)), recent_lows, 1)[0]
            low_ascending = max(0, low_trend / np.mean(recent_lows) * 100)
            
            if high_flatness > 0.7 and low_ascending > 0.5:
                return (high_flatness + low_ascending) / 2
            
        except Exception:
            pass
        
        return 0.0
    
    def _detect_descending_triangle(self, highs: np.ndarray, lows: np.ndarray) -> float:
        """Detect descending triangle pattern"""
        if len(lows) < 15:
            return 0.0
        
        try:
            recent_highs = highs[-15:]
            recent_lows = lows[-15:]
            
            # Check if lows are relatively flat (support)
            low_trend = np.polyfit(range(len(recent_lows)), recent_lows, 1)[0]
            low_flatness = 1 - abs(low_trend) / np.mean(recent_lows) * 100
            
            # Check if highs are descending (resistance)
            high_trend = np.polyfit(range(len(recent_highs)), recent_highs, 1)[0]
            high_descending = max(0, -high_trend / np.mean(recent_highs) * 100)
            
            if low_flatness > 0.7 and high_descending > 0.5:
                return (low_flatness + high_descending) / 2
            
        except Exception:
            pass
        
        return 0.0
    
    def _detect_breakout(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
        """Detect breakout pattern"""
        if len(closes) < 20:
            return 0.0
        
        try:
            # Define recent consolidation period
            consolidation_period = 10
            recent_closes = closes[-consolidation_period:]
            recent_highs = highs[-consolidation_period:]
            recent_lows = lows[-consolidation_period:]
            
            # Check for consolidation (low volatility)
            consolidation_range = (np.max(recent_highs) - np.min(recent_lows)) / np.mean(recent_closes)
            
            if consolidation_range < 0.05:  # Less than 5% range indicates consolidation
                # Check for recent breakout
                current_price = closes[-1]
                resistance = np.max(recent_highs[:-1])  # Exclude current period
                support = np.min(recent_lows[:-1])
                
                # Upward breakout
                if current_price > resistance * 1.01:
                    return 0.8
                
                # Downward breakout
                if current_price < support * 0.99:
                    return 0.8
            
        except Exception:
            pass
        
        return 0.0
    
    def _detect_channel(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> float:
        """Detect channel/trend pattern"""
        if len(closes) < 30:
            return 0.0
        
        try:
            # Use last 30 periods for channel detection
            period = 30
            recent_highs = highs[-period:]
            recent_lows = lows[-period:]
            x_values = np.array(range(period))
            
            # Fit trend lines to highs and lows
            high_trend = np.polyfit(x_values, recent_highs, 1)
            low_trend = np.polyfit(x_values, recent_lows, 1)
            
            # Calculate trend line values
            high_line = np.polyval(high_trend, x_values)
            low_line = np.polyval(low_trend, x_values)
            
            # Check if trends are parallel (similar slopes)
            slope_similarity = 1 - abs(high_trend[0] - low_trend[0]) / max(abs(high_trend[0]), abs(low_trend[0]), 0.001)
            
            # Check how well price respects the channel
            high_respect = np.mean(recent_highs <= high_line * 1.02)  # Allow 2% tolerance
            low_respect = np.mean(recent_lows >= low_line * 0.98)
            
            channel_strength = (slope_similarity + high_respect + low_respect) / 3
            
            if channel_strength > 0.6:
                return channel_strength
            
        except Exception:
            pass
        
        return 0.0
    
    def _predict_price_statistically(self, df: pd.DataFrame, 
                                   indicators: Dict[str, Any], 
                                   horizon: int) -> float:
        """Predict price using statistical methods"""
        current_price = float(df['close'].iloc[-1])
        
        try:
            # Multiple prediction methods
            predictions = []
            weights = []
            
            # Method 1: Moving average convergence
            if 'ema_12' in indicators and 'ema_26' in indicators:
                ema12_current = float(indicators['ema_12'].iloc[-1])
                ema26_current = float(indicators['ema_26'].iloc[-1])
                ma_signal = (ema12_current - ema26_current) / current_price
                ma_prediction = current_price * (1 + ma_signal * 0.1)  # Conservative multiplier
                predictions.append(ma_prediction)
                weights.append(0.3)
            
            # Method 2: RSI mean reversion
            if 'rsi' in indicators:
                rsi_current = float(indicators['rsi'].iloc[-1])
                if rsi_current > 70:  # Overbought
                    rsi_prediction = current_price * 0.98
                elif rsi_current < 30:  # Oversold
                    rsi_prediction = current_price * 1.02
                else:
                    rsi_prediction = current_price
                predictions.append(rsi_prediction)
                weights.append(0.2)
            
            # Method 3: Bollinger Band position
            if 'bb_position' in indicators:
                bb_pos = float(indicators['bb_position'].iloc[-1])
                if bb_pos > 0.8:  # Near upper band
                    bb_prediction = current_price * 0.99
                elif bb_pos < 0.2:  # Near lower band
                    bb_prediction = current_price * 1.01
                else:
                    bb_prediction = current_price
                predictions.append(bb_prediction)
                weights.append(0.25)
            
            # Method 4: Volatility-adjusted random walk
            if 'volatility' in indicators:
                volatility = float(indicators['volatility'].iloc[-1])
                vol_prediction = current_price + np.random.normal(0, volatility * current_price * 0.1)
                predictions.append(vol_prediction)
                weights.append(0.15)
            
            # Method 5: Linear trend extrapolation
            if len(df) >= 10:
                recent_prices = df['close'].tail(10).values
                x_vals = np.array(range(10))
                trend_coeff = np.polyfit(x_vals, recent_prices, 1)
                trend_prediction = np.polyval(trend_coeff, 10 + horizon/60)  # Convert minutes to periods
                predictions.append(trend_prediction)
                weights.append(0.1)
            
            # Weighted average of predictions
            if predictions and weights:
                total_weight = sum(weights)
                weighted_prediction = sum(p * w for p, w in zip(predictions, weights)) / total_weight
                return weighted_prediction
            
        except Exception as e:
            self.logger.error(f"❌ Statistical prediction failed: {e}")
        
        return current_price  # Fallback to current price
    
    def _analyze_trend_momentum(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, float]:
        """Analyze trend strength and momentum"""
        try:
            trend_signals = []
            momentum_signals = []
            
            # EMA trend analysis
            if 'ema_12' in indicators and 'ema_26' in indicators:
                ema12 = indicators['ema_12'].iloc[-1]
                ema26 = indicators['ema_26'].iloc[-1]
                ema_trend = (ema12 - ema26) / ema26
                trend_signals.append(ema_trend)
            
            # Price vs SMA analysis
            if 'sma_20' in indicators:
                current_price = df['close'].iloc[-1]
                sma20 = indicators['sma_20'].iloc[-1]
                price_trend = (current_price - sma20) / sma20
                trend_signals.append(price_trend)
            
            # MACD momentum
            if 'macd' in indicators and 'macd_signal' in indicators:
                macd_current = indicators['macd'].iloc[-1]
                signal_current = indicators['macd_signal'].iloc[-1]
                macd_momentum = (macd_current - signal_current) / abs(signal_current) if signal_current != 0 else 0
                momentum_signals.append(macd_momentum)
            
            # RSI momentum
            if 'rsi' in indicators:
                rsi = indicators['rsi'].iloc[-5:]  # Last 5 values
                rsi_momentum = (rsi.iloc[-1] - rsi.iloc[0]) / 5  # Rate of change
                momentum_signals.append(rsi_momentum / 10)  # Scale down
            
            # Volume-price momentum
            if 'volume_ratio' in indicators:
                vol_ratio = indicators['volume_ratio'].iloc[-1]
                price_change = df['close'].pct_change().iloc[-1]
                vol_momentum = vol_ratio * price_change
                momentum_signals.append(vol_momentum)
            
            # Calculate averages
            trend_strength = np.mean(trend_signals) if trend_signals else 0.0
            momentum_score = np.mean(momentum_signals) if momentum_signals else 0.0
            
            # Normalize to [-1, 1]
            trend_strength = max(-1, min(1, trend_strength))
            momentum_score = max(-1, min(1, momentum_score))
            
            return {
                'strength': abs(trend_strength),  # 0 to 1
                'direction': 1 if trend_strength > 0 else -1,
                'momentum': momentum_score
            }
            
        except Exception as e:
            self.logger.error(f"❌ Trend/momentum analysis failed: {e}")
            return {'strength': 0.0, 'direction': 0, 'momentum': 0.0}
    
    def _calculate_smart_support_resistance(self, df: pd.DataFrame) -> Dict[str, List[float]]:
        """Calculate intelligent support and resistance levels"""
        try:
            if len(df) < 50:
                return {'support': [], 'resistance': []}
            
            # Use recent data for S/R calculation
            recent_data = df.tail(100)  # Last 100 periods
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values
            
            # Find significant levels using multiple methods
            support_levels = []
            resistance_levels = []
            
            # Method 1: Historical pivot points
            for i in range(10, len(highs) - 10):
                # Resistance: local high that's higher than surrounding points
                if (highs[i] == max(highs[i-10:i+10]) and 
                    highs[i] > np.mean(highs[i-10:i+10]) * 1.02):
                    resistance_levels.append(highs[i])
                
                # Support: local low that's lower than surrounding points
                if (lows[i] == min(lows[i-10:i+10]) and 
                    lows[i] < np.mean(lows[i-10:i+10]) * 0.98):
                    support_levels.append(lows[i])
            
            # Method 2: Fibonacci retracements
            if len(recent_data) >= 50:
                period_high = np.max(highs)
                period_low = np.min(lows)
                diff = period_high - period_low
                
                fib_levels = [
                    period_high - diff * 0.236,  # 23.6% retracement
                    period_high - diff * 0.382,  # 38.2% retracement
                    period_high - diff * 0.5,    # 50% retracement
                    period_high - diff * 0.618,  # 61.8% retracement
                ]
                
                current_price = closes[-1]
                for level in fib_levels:
                    if level < current_price:
                        support_levels.append(level)
                    else:
                        resistance_levels.append(level)
            
            # Method 3: Round number levels
            current_price = closes[-1]
            price_magnitude = 10 ** (len(str(int(current_price))) - 1)
            
            for multiplier in [0.5, 1, 1.5, 2, 2.5]:
                round_level = round(current_price / (price_magnitude * multiplier)) * (price_magnitude * multiplier)
                if abs(round_level - current_price) / current_price < 0.1:  # Within 10%
                    if round_level > current_price:
                        resistance_levels.append(round_level)
                    elif round_level < current_price:
                        support_levels.append(round_level)
            
            # Filter and sort levels
            current_price = closes[-1]
            
            # Remove levels too close to current price (less than 0.5% away)
            min_distance = current_price * 0.005
            support_levels = [s for s in support_levels if current_price - s > min_distance]
            resistance_levels = [r for r in resistance_levels if r - current_price > min_distance]
            
            # Sort and limit to most significant levels
            support_levels = sorted(list(set(support_levels)), reverse=True)[:3]
            resistance_levels = sorted(list(set(resistance_levels)))[:3]
            
            return {
                'support': support_levels,
                'resistance': resistance_levels
            }
            
        except Exception as e:
            self.logger.error(f"❌ Support/resistance calculation failed: {e}")
            return {'support': [], 'resistance': []}
    
    def _forecast_volatility(self, df: pd.DataFrame) -> float:
        """Forecast volatility using statistical methods"""
        try:
            if len(df) < 20:
                return 0.02  # Default 2% volatility
            
            # Calculate returns
            returns = df['close'].pct_change().dropna()
            
            # Method 1: Historical volatility
            hist_vol = returns.tail(20).std()
            
            # Method 2: Exponentially weighted volatility
            ewm_vol = returns.ewm(span=20).std().iloc[-1]
            
            # Method 3: High-low volatility
            if len(df) >= 10:
                high_low_vol = ((df['high'] / df['low']).tail(10).apply(np.log)).std()
            else:
                high_low_vol = hist_vol
            
            # Combine methods
            combined_vol = (hist_vol * 0.4 + ewm_vol * 0.4 + high_low_vol * 0.2)
            
            # Annualize and ensure reasonable bounds
            daily_vol = combined_vol * np.sqrt(1440)  # Assuming 1-minute data
            return max(0.01, min(1.0, daily_vol))
            
        except Exception as e:
            self.logger.error(f"❌ Volatility forecast failed: {e}")
            return 0.02
    
    def _calculate_prediction_confidence(self, df: pd.DataFrame, 
                                       indicators: Dict[str, Any],
                                       patterns: Dict[str, float],
                                       trend_analysis: Dict[str, float]) -> float:
        """Calculate confidence in the prediction"""
        confidence_factors = []
        
        try:
            # Factor 1: Data quality
            data_quality = min(1.0, len(df) / 100)  # More data = higher confidence
            confidence_factors.append(data_quality * 0.15)
            
            # Factor 2: Trend consistency
            trend_strength = trend_analysis.get('strength', 0)
            confidence_factors.append(trend_strength * 0.25)
            
            # Factor 3: Pattern strength
            max_pattern_score = max(patterns.values()) if patterns else 0
            confidence_factors.append(max_pattern_score * 0.2)
            
            # Factor 4: Technical indicator agreement
            agreement_score = 0.0
            agreement_count = 0
            
            if 'rsi' in indicators:
                rsi = indicators['rsi'].iloc[-1]
                if 30 <= rsi <= 70:  # RSI in normal range
                    agreement_score += 0.8
                agreement_count += 1
            
            if 'macd' in indicators and 'macd_signal' in indicators:
                macd = indicators['macd'].iloc[-1]
                signal = indicators['macd_signal'].iloc[-1]
                if abs(macd - signal) / abs(signal) < 0.1:  # MACD near signal
                    agreement_score += 0.7
                agreement_count += 1
            
            if agreement_count > 0:
                confidence_factors.append((agreement_score / agreement_count) * 0.2)
            
            # Factor 5: Volatility stability
            if 'volatility' in indicators:
                vol_stability = 1 - min(1.0, indicators['volatility'].iloc[-1] / 0.05)
                confidence_factors.append(vol_stability * 0.2)
            
            # Calculate final confidence
            base_confidence = 0.3  # Base confidence level
            additional_confidence = sum(confidence_factors)
            
            final_confidence = min(1.0, base_confidence + additional_confidence)
            return max(0.1, final_confidence)
            
        except Exception as e:
            self.logger.error(f"❌ Confidence calculation failed: {e}")
            return 0.5  # Default moderate confidence
    
    def _generate_prediction_reasoning(self, direction: str, pattern: str, 
                                     trend_analysis: Dict[str, float], confidence: float) -> str:
        """Generate human-readable reasoning for prediction"""
        reasoning_parts = []
        
        # Direction and confidence
        conf_level = "high" if confidence > 0.7 else "moderate" if confidence > 0.4 else "low"
        reasoning_parts.append(f"{conf_level} confidence {direction} prediction")
        
        # Pattern information
        if pattern != "none":
            reasoning_parts.append(f"{pattern} pattern detected")
        
        # Trend information
        trend_strength = trend_analysis.get('strength', 0)
        if trend_strength > 0.6:
            trend_dir = "upward" if trend_analysis.get('direction', 0) > 0 else "downward"
            reasoning_parts.append(f"strong {trend_dir} trend")
        elif trend_strength > 0.3:
            reasoning_parts.append("moderate trend strength")
        else:
            reasoning_parts.append("weak trend")
        
        # Momentum information
        momentum = trend_analysis.get('momentum', 0)
        if abs(momentum) > 0.5:
            mom_dir = "positive" if momentum > 0 else "negative"
            reasoning_parts.append(f"{mom_dir} momentum")
        
        return "; ".join(reasoning_parts)
    
    def _create_insufficient_data_result(self, reason: str) -> SmartPredictionResult:
        """Create result for insufficient data"""
        return SmartPredictionResult(
            predicted_price=0.0,
            confidence=0.1,
            direction="sideways",
            volatility_forecast=0.02,
            support_levels=[],
            resistance_levels=[],
            trend_strength=0.0,
            momentum_score=0.0,
            pattern_detected="none",
            reasoning=reason
        )
    
    def _create_error_result(self, reason: str) -> SmartPredictionResult:
        """Create error result"""
        return SmartPredictionResult(
            predicted_price=0.0,
            confidence=0.0,
            direction="sideways",
            volatility_forecast=0.02,
            support_levels=[],
            resistance_levels=[],
            trend_strength=0.0,
            momentum_score=0.0,
            pattern_detected="error",
            reasoning=reason
        )


# Factory functions for creating smart fallback instances
def create_smart_sentiment_analyzer() -> SmartSentimentAnalyzer:
    """Create smart sentiment analyzer instance"""
    return SmartSentimentAnalyzer()

def create_smart_market_predictor() -> SmartMarketPredictor:
    """Create smart market predictor instance"""
    return SmartMarketPredictor()

# Global instances for fallback components
_smart_sentiment_analyzer = None
_smart_market_predictor = None

def get_smart_sentiment_fallback() -> SmartSentimentAnalyzer:
    """Get global smart sentiment fallback instance"""
    global _smart_sentiment_analyzer
    if _smart_sentiment_analyzer is None:
        _smart_sentiment_analyzer = SmartSentimentAnalyzer()
    return _smart_sentiment_analyzer

def get_smart_market_fallback() -> SmartMarketPredictor:
    """Get global smart market predictor fallback instance"""
    global _smart_market_predictor
    if _smart_market_predictor is None:
        _smart_market_predictor = SmartMarketPredictor()
    return _smart_market_predictor