#!/usr/bin/env python3
"""
ML-Based Agent Signal Analyzer with Parallel Processing
Integrates machine learning and multi-agent decision making for signal validation
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from enum import Enum
import json
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SignalAgentType(Enum):
    """Types of trading agents"""
    TECHNICAL_AGENT = "technical"
    MOMENTUM_AGENT = "momentum"
    VOLATILITY_AGENT = "volatility"
    VOLUME_AGENT = "volume"
    SENTIMENT_AGENT = "sentiment"

@dataclass
class AgentDecision:
    """Decision from a single trading agent"""
    agent_type: SignalAgentType
    confidence: float  # 0-1
    signal_direction: str  # 'BUY', 'SELL', 'NEUTRAL'
    reasoning: str
    indicators_used: List[str] = field(default_factory=list)
    score: float = 0.0

@dataclass
class EnhancedSignal:
    """Enhanced signal with ML predictions and multi-agent consensus"""
    symbol: str
    direction: str
    entry_price: float
    confidence_score: float  # 0-100
    agent_votes: Dict[str, float]
    ml_prediction: float  # 0-1, probability of success
    dynamic_sl: float
    dynamic_tp1: float
    dynamic_tp2: float
    dynamic_tp3: float
    risk_score: float  # 0-100, lower is better
    timestamp: datetime
    reasoning: str

class MLTradeModel:
    """Simple ML model for trade prediction based on historical data"""
    
    def __init__(self):
        self.model_data = defaultdict(list)
        self.min_samples = 20
        
    def add_trade_result(self, symbol: str, indicators: Dict, result: float):
        """Add training data (result: 1 for win, 0 for loss)"""
        self.model_data[symbol].append({'indicators': indicators, 'result': result})
    
    def predict_win_probability(self, symbol: str, indicators: Dict) -> float:
        """Predict probability of winning trade based on indicators"""
        if symbol not in self.model_data or len(self.model_data[symbol]) < self.min_samples:
            return 0.5  # Default confidence
        
        trades = self.model_data[symbol]
        
        # Simple pattern matching: find similar indicator combinations
        similarities = []
        for trade in trades:
            similarity = self._calculate_similarity(indicators, trade['indicators'])
            weighted_result = trade['result'] * (similarity / 100)
            similarities.append(weighted_result)
        
        if not similarities:
            return 0.5
        
        avg_win_rate = np.mean(similarities)
        return min(1.0, max(0.0, avg_win_rate))
    
    @staticmethod
    def _calculate_similarity(ind1: Dict, ind2: Dict) -> float:
        """Calculate similarity between two indicator sets (0-100)"""
        if not ind1 or not ind2:
            return 50
        
        common_keys = set(ind1.keys()) & set(ind2.keys())
        if not common_keys:
            return 50
        
        differences = []
        for key in common_keys:
            if isinstance(ind1[key], (int, float)) and isinstance(ind2[key], (int, float)):
                if ind1[key] != 0:
                    diff = abs(ind1[key] - ind2[key]) / max(abs(ind1[key]), 0.01)
                    differences.append(diff)
        
        if not differences:
            return 50
        
        avg_diff = np.mean(differences)
        similarity = max(0, 100 - (avg_diff * 100))
        return similarity

class MultiAgentSignalAnalyzer:
    """Multi-agent system for signal analysis with parallel processing"""
    
    def __init__(self):
        self.ml_model = MLTradeModel()
        self.agent_weights = {
            SignalAgentType.TECHNICAL_AGENT: 0.25,
            SignalAgentType.MOMENTUM_AGENT: 0.20,
            SignalAgentType.VOLATILITY_AGENT: 0.20,
            SignalAgentType.VOLUME_AGENT: 0.15,
            SignalAgentType.SENTIMENT_AGENT: 0.20
        }
        self.decision_history = defaultdict(list)
        self.max_history = 100
        
    async def analyze_signal_parallel(self, symbol: str, indicators: Dict[str, Any], 
                                     current_price: float, atr: float) -> Optional[EnhancedSignal]:
        """
        Analyze signal using parallel agent processing
        Combines multiple agent decisions with ML prediction
        """
        try:
            # Run all agents in parallel
            tasks = [
                self._technical_agent(symbol, indicators),
                self._momentum_agent(symbol, indicators),
                self._volatility_agent(symbol, indicators, atr),
                self._volume_agent(symbol, indicators),
                self._sentiment_agent(symbol, indicators)
            ]
            
            agent_decisions = await asyncio.gather(*tasks, return_exceptions=True)
            agent_decisions = [d for d in agent_decisions if isinstance(d, AgentDecision)]
            
            if not agent_decisions:
                return None
            
            # Calculate consensus
            signal_direction, confidence = self._calculate_consensus(agent_decisions)
            
            if confidence < 0.55:  # Minimum confidence threshold
                return None
            
            # Get ML prediction
            ml_probability = self.ml_model.predict_win_probability(symbol, indicators)
            
            # Calculate dynamic SL and TP
            dynamic_sl, tp1, tp2, tp3 = self._calculate_dynamic_sl_tp(
                current_price, atr, signal_direction, ml_probability, indicators
            )
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(indicators, signal_direction, atr)
            
            # Build reasoning
            reasoning = self._build_reasoning(agent_decisions, ml_probability)
            
            # Create agent votes dict
            agent_votes = {d.agent_type.value: d.score for d in agent_decisions}
            
            signal = EnhancedSignal(
                symbol=symbol,
                direction=signal_direction,
                entry_price=current_price,
                confidence_score=int(confidence * 100),
                agent_votes=agent_votes,
                ml_prediction=ml_probability,
                dynamic_sl=dynamic_sl,
                dynamic_tp1=tp1,
                dynamic_tp2=tp2,
                dynamic_tp3=tp3,
                risk_score=int(risk_score),
                timestamp=datetime.now(),
                reasoning=reasoning
            )
            
            # Store decision history
            self.decision_history[symbol].append({
                'timestamp': signal.timestamp,
                'direction': signal.direction,
                'confidence': signal.confidence_score,
                'ml_prob': ml_probability
            })
            
            if len(self.decision_history[symbol]) > self.max_history:
                self.decision_history[symbol].pop(0)
            
            return signal
            
        except Exception as e:
            logger.error(f"Error analyzing signal for {symbol}: {e}")
            return None
    
    async def _technical_agent(self, symbol: str, indicators: Dict) -> AgentDecision:
        """Technical analysis agent"""
        await asyncio.sleep(0.01)  # Simulate processing
        
        score = 0
        signals = []
        
        # EMA crossover
        if indicators.get('ema_fast') and indicators.get('ema_slow'):
            if indicators['ema_fast'] > indicators['ema_slow']:
                score += 25
                signals.append('ema_bullish')
            else:
                score -= 25
                signals.append('ema_bearish')
        
        # RSI
        if indicators.get('rsi'):
            rsi = indicators['rsi']
            if 30 < rsi < 70:
                score += 15
                signals.append('rsi_neutral')
            elif rsi <= 30:
                score += 20
                signals.append('rsi_oversold')
            elif rsi >= 70:
                score -= 20
                signals.append('rsi_overbought')
        
        # Bollinger Bands
        if indicators.get('bb_upper') and indicators.get('bb_lower'):
            price = indicators.get('current_price', 0)
            if price > indicators['bb_upper']:
                score -= 15
                signals.append('bb_overbought')
            elif price < indicators['bb_lower']:
                score += 15
                signals.append('bb_oversold')
        
        direction = 'BUY' if score > 0 else 'SELL' if score < 0 else 'NEUTRAL'
        confidence = min(1.0, abs(score) / 100)
        
        return AgentDecision(
            agent_type=SignalAgentType.TECHNICAL_AGENT,
            confidence=confidence,
            signal_direction=direction,
            reasoning=f"Technical signals: {', '.join(signals)}",
            indicators_used=signals,
            score=score
        )
    
    async def _momentum_agent(self, symbol: str, indicators: Dict) -> AgentDecision:
        """Momentum agent"""
        await asyncio.sleep(0.01)
        
        score = 0
        signals = []
        
        # MACD
        if indicators.get('macd') and indicators.get('macd_signal'):
            if indicators['macd'] > indicators['macd_signal']:
                score += 20
                signals.append('macd_bullish')
            else:
                score -= 20
                signals.append('macd_bearish')
        
        # Price momentum (rate of change)
        if indicators.get('price_change_pct'):
            change = indicators['price_change_pct']
            if change > 0.5:
                score += 15
                signals.append('positive_momentum')
            elif change < -0.5:
                score -= 15
                signals.append('negative_momentum')
        
        direction = 'BUY' if score > 0 else 'SELL' if score < 0 else 'NEUTRAL'
        confidence = min(1.0, abs(score) / 100)
        
        return AgentDecision(
            agent_type=SignalAgentType.MOMENTUM_AGENT,
            confidence=confidence,
            signal_direction=direction,
            reasoning=f"Momentum signals: {', '.join(signals)}",
            indicators_used=signals,
            score=score
        )
    
    async def _volatility_agent(self, symbol: str, indicators: Dict, atr: float) -> AgentDecision:
        """Volatility assessment agent"""
        await asyncio.sleep(0.01)
        
        score = 0
        signals = []
        
        # ATR-based volatility
        if atr > 0:
            atr_pct = indicators.get('atr_percent', 0)
            if atr_pct < 1.0:
                score += 10
                signals.append('low_volatility')
            elif atr_pct > 3.0:
                score -= 15
                signals.append('high_volatility')
            else:
                score += 5
                signals.append('optimal_volatility')
        
        # Bollinger Bands width
        if indicators.get('bb_width'):
            if indicators['bb_width'] < 2:
                score -= 5
                signals.append('tight_bands')
            else:
                score += 10
                signals.append('wide_bands')
        
        direction = 'BUY' if score > 0 else 'SELL' if score < 0 else 'NEUTRAL'
        confidence = min(1.0, abs(score) / 100)
        
        return AgentDecision(
            agent_type=SignalAgentType.VOLATILITY_AGENT,
            confidence=confidence,
            signal_direction=direction,
            reasoning=f"Volatility signals: {', '.join(signals)}",
            indicators_used=signals,
            score=score
        )
    
    async def _volume_agent(self, symbol: str, indicators: Dict) -> AgentDecision:
        """Volume analysis agent"""
        await asyncio.sleep(0.01)
        
        score = 0
        signals = []
        
        # Volume analysis
        if indicators.get('volume_ratio'):
            vol_ratio = indicators['volume_ratio']
            if vol_ratio > 1.2:
                score += 20
                signals.append('high_volume')
            elif vol_ratio < 0.8:
                score -= 10
                signals.append('low_volume')
            else:
                score += 5
                signals.append('normal_volume')
        
        # Volume trend
        if indicators.get('volume_trend') == 'increasing':
            score += 10
            signals.append('volume_increasing')
        elif indicators.get('volume_trend') == 'decreasing':
            score -= 10
            signals.append('volume_decreasing')
        
        direction = 'BUY' if score > 0 else 'SELL' if score < 0 else 'NEUTRAL'
        confidence = min(1.0, abs(score) / 100)
        
        return AgentDecision(
            agent_type=SignalAgentType.VOLUME_AGENT,
            confidence=confidence,
            signal_direction=direction,
            reasoning=f"Volume signals: {', '.join(signals)}",
            indicators_used=signals,
            score=score
        )
    
    async def _sentiment_agent(self, symbol: str, indicators: Dict) -> AgentDecision:
        """Market sentiment agent"""
        await asyncio.sleep(0.01)
        
        score = 0
        signals = []
        
        # Price position
        if indicators.get('price_position'):
            position = indicators['price_position']
            if position > 0.7:
                score += 10
                signals.append('price_near_high')
            elif position < 0.3:
                score += 15
                signals.append('price_near_low')
            else:
                score += 5
                signals.append('price_midpoint')
        
        # Trend direction
        if indicators.get('trend_direction') == 'up':
            score += 15
            signals.append('uptrend')
        elif indicators.get('trend_direction') == 'down':
            score -= 15
            signals.append('downtrend')
        
        direction = 'BUY' if score > 0 else 'SELL' if score < 0 else 'NEUTRAL'
        confidence = min(1.0, abs(score) / 100)
        
        return AgentDecision(
            agent_type=SignalAgentType.SENTIMENT_AGENT,
            confidence=confidence,
            signal_direction=direction,
            reasoning=f"Sentiment signals: {', '.join(signals)}",
            indicators_used=signals,
            score=score
        )
    
    def _calculate_consensus(self, decisions: List[AgentDecision]) -> Tuple[str, float]:
        """Calculate consensus from all agent decisions"""
        weighted_score = 0
        total_weight = 0
        
        for decision in decisions:
            weight = self.agent_weights.get(decision.agent_type, 0.2)
            
            direction_value = 1.0 if decision.signal_direction == 'BUY' else -1.0 if decision.signal_direction == 'SELL' else 0
            weighted_score += direction_value * decision.confidence * weight
            total_weight += weight
        
        if total_weight > 0:
            consensus_score = weighted_score / total_weight
        else:
            consensus_score = 0
        
        direction = 'BUY' if consensus_score > 0.1 else 'SELL' if consensus_score < -0.1 else 'NEUTRAL'
        confidence = min(1.0, abs(consensus_score))
        
        return direction, confidence
    
    def _calculate_dynamic_sl_tp(self, entry: float, atr: float, direction: str,
                                 ml_prob: float, indicators: Dict) -> Tuple[float, float, float, float]:
        """Calculate dynamic stop loss and take profit levels based on risk"""
        
        # Adjust multipliers based on ML confidence
        ml_factor = 0.8 + (ml_prob * 0.4)  # 0.8 to 1.2
        
        # Base risk is 1-2 ATR depending on volatility
        volatility_factor = indicators.get('atr_percent', 1.0)
        if volatility_factor > 2.0:
            risk_distance = atr * 1.5 * ml_factor
        else:
            risk_distance = atr * 1.0 * ml_factor
        
        if direction == 'BUY':
            sl = entry - risk_distance
            tp1 = entry + (risk_distance * 1.0)
            tp2 = entry + (risk_distance * 2.0)
            tp3 = entry + (risk_distance * 3.0)
        else:
            sl = entry + risk_distance
            tp1 = entry - (risk_distance * 1.0)
            tp2 = entry - (risk_distance * 2.0)
            tp3 = entry - (risk_distance * 3.0)
        
        return sl, tp1, tp2, tp3
    
    def _calculate_risk_score(self, indicators: Dict, direction: str, atr: float) -> float:
        """Calculate risk score 0-100 (lower is better)"""
        risk = 30  # Base risk
        
        # ATR-based volatility risk
        volatility = indicators.get('atr_percent', 1.0)
        risk += (volatility - 1.0) * 20
        
        # RSI extreme risk
        rsi = indicators.get('rsi', 50)
        if rsi > 80 or rsi < 20:
            risk += 15
        
        # Trend strength
        if indicators.get('trend_strength', 0.5) < 0.3:
            risk += 20
        
        return min(100, max(0, risk))
    
    def _build_reasoning(self, decisions: List[AgentDecision], ml_prob: float) -> str:
        """Build human-readable reasoning for the signal"""
        high_confidence_agents = [d.agent_type.value for d in decisions if d.confidence > 0.7]
        reasoning = f"Multi-agent consensus with {len(high_confidence_agents)} strong agents. "
        reasoning += f"ML confidence: {int(ml_prob*100)}%. "
        reasoning += f"Key signals: {', '.join(high_confidence_agents)}"
        return reasoning

    def record_trade_result(self, symbol: str, indicators: Dict, won: bool):
        """Record trade result for ML learning"""
        self.ml_model.add_trade_result(symbol, indicators, 1.0 if won else 0.0)
