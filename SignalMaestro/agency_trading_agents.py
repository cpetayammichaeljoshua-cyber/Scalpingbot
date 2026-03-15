#!/usr/bin/env python3
"""
Agency-Agents Trading Framework
Specialized trading agents based on agency-agents philosophy
Each agent has expertise, personality, and proven workflows
"""

import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentRole(Enum):
    """Specialized trading agent roles"""
    SIGNAL_ANALYST = "signal_analyst"
    RISK_MANAGER = "risk_manager"
    MARKET_OBSERVER = "market_observer"
    POSITION_OPTIMIZER = "position_optimizer"
    EXECUTION_SPECIALIST = "execution_specialist"

@dataclass
class AgentDecision:
    agent_role: AgentRole
    recommendation: str  # BUY, SELL, HOLD, SKIP
    confidence: float  # 0-100
    reasoning: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class SignalAnalystAgent:
    """
    Signal Analysis Specialist
    - Validates incoming trading signals
    - Detects patterns and anomalies
    - Cross-references with technical indicators
    - Expertise: Pattern recognition, signal validation, trend detection
    """
    
    role = AgentRole.SIGNAL_ANALYST
    personality = "Methodical, detail-oriented, pattern-focused"
    expertise = ["Signal validation", "Pattern detection", "Anomaly identification"]
    
    def __init__(self):
        self.validated_signals = []
    
    async def analyze(self, symbol: str, indicators: Dict, signal_data: Dict) -> AgentDecision:
        """Analyze signal validity and quality"""
        await asyncio.sleep(0.01)
        
        reasoning = []
        confidence = 50
        
        # Check indicator alignment
        if indicators.get('ema_fast') and indicators.get('ema_slow'):
            if indicators['ema_fast'] > indicators['ema_slow']:
                reasoning.append("✓ EMA bullish alignment")
                confidence += 15
            else:
                reasoning.append("✗ EMA bearish misalignment")
                confidence -= 10
        
        # Check RSI conditions
        rsi = indicators.get('rsi', 50)
        if 30 < rsi < 70:
            reasoning.append("✓ RSI in neutral zone (good entry)")
            confidence += 10
        elif rsi <= 30:
            reasoning.append("✓ RSI oversold (strong buy signal)")
            confidence += 20
        elif rsi >= 70:
            reasoning.append("✗ RSI overbought (weak signal)")
            confidence -= 15
        
        # Check volume
        if indicators.get('volume_ratio', 1.0) > 1.2:
            reasoning.append("✓ High volume confirms signal")
            confidence += 10
        
        # Determine recommendation
        if confidence > 65:
            recommendation = signal_data.get('direction', 'BUY')
        elif confidence > 50:
            recommendation = "HOLD"
        else:
            recommendation = "SKIP"
        
        return AgentDecision(
            agent_role=self.role,
            recommendation=recommendation,
            confidence=min(100, max(0, confidence)),
            reasoning=reasoning,
            metrics={'rsi': rsi, 'ema_cross': indicators.get('ema_fast', 0) > indicators.get('ema_slow', 0)},
            metadata={'symbol': symbol, 'timestamp': datetime.now().isoformat()}
        )

class RiskManagerAgent:
    """
    Risk Management Specialist
    - Calculates position size based on account risk
    - Determines stop loss and take profit levels
    - Monitors exposure and drawdown
    - Expertise: Position sizing, risk assessment, portfolio protection
    """
    
    role = AgentRole.RISK_MANAGER
    personality = "Conservative, protective, calculation-focused"
    expertise = ["Position sizing", "Risk assessment", "Stop loss optimization"]
    
    def __init__(self, account_size: float = 1000.0, risk_per_trade: float = 2.0):
        self.account_size = account_size
        self.risk_per_trade = risk_per_trade
        self.active_positions = []
    
    async def calculate_position(self, entry: float, direction: str, atr: float) -> AgentDecision:
        """Calculate optimal position size and risk parameters"""
        await asyncio.sleep(0.01)
        
        reasoning = []
        
        # Calculate risk amount
        risk_amount = self.account_size * (self.risk_per_trade / 100)
        reasoning.append(f"Risk amount: ${risk_amount:.2f} ({self.risk_per_trade}% of account)")
        
        # Calculate stop loss based on ATR
        atr_risk = atr * 1.5
        if direction.upper() == 'BUY':
            stop_loss = entry - atr_risk
            reasoning.append(f"Stop loss {atr_risk*100/entry:.2f}% below entry")
        else:
            stop_loss = entry + atr_risk
            reasoning.append(f"Stop loss {atr_risk*100/entry:.2f}% above entry")
        
        # Calculate position size
        if atr_risk > 0:
            position_size = risk_amount / atr_risk
            reasoning.append(f"Position size: {position_size:.4f} units")
        else:
            position_size = self.account_size * 0.01
            reasoning.append("Using default 1% position size")
        
        # Check portfolio exposure
        total_exposure = sum(p.get('size', 0) for p in self.active_positions) + position_size
        max_exposure = self.account_size * 0.1  # Max 10%
        
        if total_exposure > max_exposure:
            recommendation = "SKIP"
            reasoning.append(f"⚠ Exposure limit would be exceeded")
            confidence = 30
        else:
            recommendation = "APPROVE"
            confidence = 85
            reasoning.append(f"✓ Risk parameters approved")
        
        return AgentDecision(
            agent_role=self.role,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            metrics={
                'position_size': position_size,
                'stop_loss': stop_loss,
                'risk_amount': risk_amount,
                'total_exposure': total_exposure
            }
        )

class MarketObserverAgent:
    """
    Market Conditions Specialist
    - Analyzes overall market health
    - Detects market regimes (trending, ranging, volatile)
    - Provides macro-level context
    - Expertise: Market analysis, regime detection, volatility assessment
    """
    
    role = AgentRole.MARKET_OBSERVER
    personality = "Strategic, big-picture thinker, context-aware"
    expertise = ["Market analysis", "Regime detection", "Trend strength"]
    
    async def assess_market(self, indicators: Dict) -> AgentDecision:
        """Assess overall market conditions"""
        await asyncio.sleep(0.01)
        
        reasoning = []
        confidence = 50
        
        # Assess volatility
        atr_pct = indicators.get('atr_percent', 1.0)
        if atr_pct < 1.0:
            reasoning.append("✓ Low volatility - good for scalping")
            confidence += 15
        elif atr_pct > 3.0:
            reasoning.append("⚠ High volatility - reduce size")
            confidence -= 10
        else:
            reasoning.append("✓ Normal volatility - optimal conditions")
            confidence += 10
        
        # Assess trend strength
        trend_strength = indicators.get('trend_strength', 0.5)
        if trend_strength > 0.7:
            reasoning.append("✓ Strong trend identified")
            confidence += 15
        elif trend_strength < 0.3:
            reasoning.append("✗ Weak trend - risk of whipsaw")
            confidence -= 15
        
        # Assess volume
        volume_ratio = indicators.get('volume_ratio', 1.0)
        if volume_ratio > 1.3:
            reasoning.append("✓ High volume - healthy market")
            confidence += 10
        
        recommendation = "FAVORABLE" if confidence > 60 else "CAUTION" if confidence > 40 else "UNFAVORABLE"
        
        return AgentDecision(
            agent_role=self.role,
            recommendation=recommendation,
            confidence=min(100, max(0, confidence)),
            reasoning=reasoning,
            metrics={
                'volatility': atr_pct,
                'trend_strength': trend_strength,
                'volume_ratio': volume_ratio
            }
        )

class PositionOptimizerAgent:
    """
    Position Optimization Specialist
    - Optimizes existing positions
    - Manages take profit levels
    - Trails stops and adapts to market
    - Expertise: Trade optimization, profit taking, dynamic management
    """
    
    role = AgentRole.POSITION_OPTIMIZER
    personality = "Adaptive, profit-focused, dynamic"
    expertise = ["Position optimization", "Take profit management", "Stop loss trailing"]
    
    async def optimize_position(self, trade_info: Dict, current_price: float) -> AgentDecision:
        """Optimize existing position"""
        await asyncio.sleep(0.01)
        
        reasoning = []
        entry = trade_info.get('entry_price', 0)
        direction = trade_info.get('direction', 'BUY')
        
        if direction == 'BUY':
            pnl_pct = ((current_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - current_price) / entry) * 100
        
        reasoning.append(f"Current P&L: {pnl_pct:.2f}%")
        
        # Check profit target achievement
        tp_levels = trade_info.get('tp_levels', [])
        if pnl_pct > 3.0:
            recommendation = "TAKE_PARTIAL"
            reasoning.append("✓ Target 1.5-2% achieved - take partial profit")
        elif pnl_pct > 5.0:
            recommendation = "TAKE_HALF"
            reasoning.append("✓ Target 3-4% achieved - take 50%")
        elif pnl_pct < -1.0:
            recommendation = "TIGHTEN_STOP"
            reasoning.append("⚠ In drawdown - tighten stop loss")
        else:
            recommendation = "HOLD"
            reasoning.append("Hold current position")
        
        confidence = 80
        
        return AgentDecision(
            agent_role=self.role,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            metrics={'pnl_percent': pnl_pct}
        )

class ExecutionSpecialistAgent:
    """
    Execution Specialist
    - Handles order execution details
    - Manages order timing and slippage
    - Executes with optimal parameters
    - Expertise: Order execution, slippage management, timing
    """
    
    role = AgentRole.EXECUTION_SPECIALIST
    personality = "Precise, timing-focused, execution-oriented"
    expertise = ["Order execution", "Timing optimization", "Slippage management"]
    
    async def prepare_execution(self, signal: Dict, market_data: Dict) -> AgentDecision:
        """Prepare optimal execution parameters"""
        await asyncio.sleep(0.01)
        
        reasoning = []
        confidence = 80
        
        # Check market conditions
        spread = market_data.get('spread', 0.001)
        if spread < 0.001:
            reasoning.append("✓ Tight spread - optimal execution window")
            confidence += 10
        else:
            reasoning.append(f"⚠ Spread {spread*100:.4f}% - may affect entry")
        
        # Check order book depth
        bid_volume = market_data.get('bid_volume', 0)
        ask_volume = market_data.get('ask_volume', 0)
        
        if bid_volume > 10 and ask_volume > 10:
            reasoning.append("✓ Good order book depth")
            confidence += 10
        else:
            reasoning.append("✗ Shallow order book - execution risk")
            confidence -= 10
        
        # Recommend execution strategy
        if confidence > 80:
            recommendation = "EXECUTE_MARKET"
            reasoning.append("Execute at market price")
        else:
            recommendation = "EXECUTE_LIMIT"
            reasoning.append("Use limit order to manage slippage")
        
        return AgentDecision(
            agent_role=self.role,
            recommendation=recommendation,
            confidence=min(100, max(0, confidence)),
            reasoning=reasoning,
            metrics={'spread': spread, 'bid_volume': bid_volume, 'ask_volume': ask_volume}
        )

class AgencyTradingAgents:
    """
    Agency Trading System - Coordinates 5 specialized agents
    Each agent has expertise, personality, and proven workflows
    """
    
    def __init__(self, account_size: float = 1000.0):
        self.signal_analyst = SignalAnalystAgent()
        self.risk_manager = RiskManagerAgent(account_size=account_size)
        self.market_observer = MarketObserverAgent()
        self.position_optimizer = PositionOptimizerAgent()
        self.execution_specialist = ExecutionSpecialistAgent()
        
        self.decision_history = []
        self.max_history = 200
    
    async def analyze_signal_with_agents(self, symbol: str, signal: Dict, 
                                         indicators: Dict, market_data: Dict) -> Dict:
        """
        Execute all agents in parallel, collect recommendations
        Returns consensus decision with full reasoning
        """
        
        # Run all agents concurrently
        tasks = [
            self.signal_analyst.analyze(symbol, indicators, signal),
            self.market_observer.assess_market(indicators),
            self.risk_manager.calculate_position(
                signal.get('entry_price', market_data.get('current_price', 0)),
                signal.get('direction', 'BUY'),
                market_data.get('atr', 0)
            ),
            self.execution_specialist.prepare_execution(signal, market_data)
        ]
        
        decisions = await asyncio.gather(*tasks)
        
        # Calculate consensus
        consensus = self._calculate_consensus(decisions)
        
        # Build complete analysis
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'agent_decisions': {d.agent_role.value: {
                'recommendation': d.recommendation,
                'confidence': d.confidence,
                'reasoning': d.reasoning,
                'metrics': d.metrics
            } for d in decisions},
            'consensus': consensus,
            'final_recommendation': self._get_final_recommendation(consensus),
            'confidence_score': int(consensus.get('average_confidence', 0))
        }
        
        # Store history
        self.decision_history.append(analysis)
        if len(self.decision_history) > self.max_history:
            self.decision_history.pop(0)
        
        return analysis
    
    def _calculate_consensus(self, decisions: List[AgentDecision]) -> Dict:
        """Calculate consensus from agent decisions"""
        
        recommendations = [d.recommendation for d in decisions]
        confidences = [d.confidence for d in decisions]
        
        # Count recommendations
        rec_count = {}
        for rec in recommendations:
            rec_count[rec] = rec_count.get(rec, 0) + 1
        
        # Get most common recommendation
        top_rec = max(rec_count.items(), key=lambda x: x[1])[0] if rec_count else "HOLD"
        
        return {
            'top_recommendation': top_rec,
            'recommendation_count': rec_count,
            'average_confidence': sum(confidences) / len(confidences) if confidences else 0,
            'agent_count': len(decisions),
            'agreement_level': rec_count.get(top_rec, 0) / len(decisions) if decisions else 0
        }
    
    def _get_final_recommendation(self, consensus: Dict) -> str:
        """Get final trading recommendation based on consensus"""
        
        top_rec = consensus.get('top_recommendation', 'HOLD')
        agreement = consensus.get('agreement_level', 0)
        avg_conf = consensus.get('average_confidence', 0)
        
        # Require strong consensus for execution
        if agreement >= 0.75 and avg_conf >= 70:
            return top_rec
        elif top_rec in ['BUY', 'SELL'] and agreement >= 0.5 and avg_conf >= 55:
            return top_rec
        else:
            return "HOLD"
    
    async def monitor_position(self, symbol: str, trade_info: Dict, 
                              current_price: float) -> Dict:
        """Monitor existing position with optimizer agent"""
        
        decision = await self.position_optimizer.optimize_position(trade_info, current_price)
        
        return {
            'symbol': symbol,
            'agent': decision.agent_role.value,
            'recommendation': decision.recommendation,
            'confidence': decision.confidence,
            'reasoning': decision.reasoning,
            'timestamp': datetime.now().isoformat()
        }
    
    def print_agent_roster(self):
        """Print info about all agents"""
        print("\n" + "="*70)
        print("AGENCY TRADING AGENTS - SPECIALIZED TRADING TEAM")
        print("="*70)
        
        agents = [
            ("🎯 Signal Analyst", self.signal_analyst.personality, self.signal_analyst.expertise),
            ("📊 Risk Manager", self.risk_manager.personality, self.risk_manager.expertise),
            ("🔍 Market Observer", self.market_observer.personality, self.market_observer.expertise),
            ("⚡ Position Optimizer", self.position_optimizer.personality, self.position_optimizer.expertise),
            ("🚀 Execution Specialist", self.execution_specialist.personality, self.execution_specialist.expertise)
        ]
        
        for name, personality, expertise in agents:
            print(f"\n{name}")
            print(f"  Personality: {personality}")
            print(f"  Expertise: {', '.join(expertise)}")
        
        print("\n" + "="*70 + "\n")
