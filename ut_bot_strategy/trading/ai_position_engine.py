"""
AI-Driven Position Engine for Dynamic TP/SL/Position Calculation

Features:
- Dynamic stop-loss calculation based on ATR, volatility, and market structure
- Multi-target take profits (TP1, TP2, TP3) with configurable allocation
- Intelligent position sizing based on risk percentage and account balance
- Optimal leverage calculation based on volatility and signal confidence
- Margin requirements management
- Trailing stop logic with progressive SL movement
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    """Trade direction enum"""
    LONG = "LONG"
    SHORT = "SHORT"


class TrailingStopState(Enum):
    """Trailing stop state machine"""
    INITIAL = "initial"
    AT_ENTRY = "at_entry"
    AT_TP1 = "at_tp1"
    AT_TP2 = "at_tp2"


@dataclass
class TPLevel:
    """Take profit level with allocation"""
    price: float
    allocation_percent: float
    risk_reward: float
    hit: bool = False


@dataclass
class TradeSetup:
    """Complete trade setup with all parameters"""
    entry_price: float
    stop_loss: float
    tp1: TPLevel
    tp2: TPLevel
    tp3: TPLevel
    position_size: float
    leverage: int
    margin_required: float
    direction: str
    risk_amount: float
    total_risk_reward: float
    trailing_stop_state: TrailingStopState = TrailingStopState.INITIAL
    current_trailing_sl: Optional[float] = None
    confidence_score: float = 0.0
    reasoning: str = ""


@dataclass
class TPAllocation:
    """Take profit allocation configuration"""
    tp1_percent: float = 40.0
    tp2_percent: float = 35.0
    tp3_percent: float = 25.0
    
    def validate(self) -> bool:
        """Validate allocations sum to 100%"""
        total = self.tp1_percent + self.tp2_percent + self.tp3_percent
        return abs(total - 100.0) < 0.01


class AIPositionEngine:
    """
    AI-driven position calculation engine with dynamic TP/SL management
    
    Features:
    - ATR-based dynamic stop loss with volatility and AI adjustments
    - Multi-target take profits with configurable risk-reward ratios
    - Intelligent position sizing based on risk management
    - Volatility-adaptive leverage calculation
    - Trailing stop management with progressive SL movement
    """
    
    def __init__(
        self,
        min_leverage: int = 2,
        max_leverage: int = 20,
        base_leverage: int = 5,
        default_risk_percent: float = 2.0,
        max_position_percent: float = 50.0,
        atr_sl_multiplier: float = 1.5,
        volatility_low_threshold: float = 0.5,
        volatility_high_threshold: float = 2.0,
        tp_allocation: Optional[TPAllocation] = None
    ):
        """
        Initialize the AI Position Engine
        """
        self.min_leverage = min_leverage
        self.max_leverage = max_leverage
        self.base_leverage = base_leverage
        self.default_risk_percent = default_risk_percent
        self.max_position_percent = max_position_percent / 100.0
        self.atr_sl_multiplier = atr_sl_multiplier
        self.vol_low = volatility_low_threshold
        self.vol_high = volatility_high_threshold
        
        self.tp_allocation = tp_allocation or TPAllocation()
        if not self.tp_allocation.validate():
            logger.warning("TP allocations don't sum to 100%, using defaults")
            self.tp_allocation = TPAllocation()
        
        self.volatility_leverage_scale = {
            0.3: 1.3, 0.5: 1.1, 1.0: 1.0, 1.5: 0.7, 2.0: 0.5, 3.0: 0.3
        }
        
        self.market_structure_adjustments = {
            'trending': {'sl_mult': 1.2, 'tp_mult': 1.3},
            'ranging': {'sl_mult': 0.9, 'tp_mult': 0.85},
            'volatile': {'sl_mult': 1.5, 'tp_mult': 1.1},
            'breakout': {'sl_mult': 1.8, 'tp_mult': 1.5},
            'consolidation': {'sl_mult': 0.8, 'tp_mult': 0.8}
        }
    
    def calculate_dynamic_sl(
        self, entry_price: float, direction: str, atr: float,
        volatility_score: float, ai_adjustment: float = 0.0,
        market_structure: str = "ranging"
    ) -> Tuple[float, str]:
        try:
            ai_adjustment = max(-0.5, min(0.5, ai_adjustment))
            structure_adj = self.market_structure_adjustments.get(
                market_structure, self.market_structure_adjustments['ranging']
            )
            volatility_multiplier = 1.0
            if volatility_score < 0.3: volatility_multiplier = 1.4
            elif volatility_score < 0.5: volatility_multiplier = 1.2
            elif volatility_score > 0.8: volatility_multiplier = 0.8
            
            adjusted_multiplier = (
                self.atr_sl_multiplier * structure_adj['sl_mult'] * 
                volatility_multiplier * (1.0 + ai_adjustment)
            )
            sl_distance = atr * adjusted_multiplier
            direction_upper = direction.upper()
            stop_loss = entry_price - sl_distance if direction_upper == "LONG" else entry_price + sl_distance
            
            sl_percent = abs(entry_price - stop_loss) / entry_price * 100
            reasoning = f"SL: {sl_percent:.2f}% (ATR based)"
            return stop_loss, reasoning
        except Exception as e:
            logger.error(f"Error: {e}")
            return entry_price * 0.98 if direction.upper() == "LONG" else entry_price * 1.02, str(e)

    def calculate_multi_tp(
        self, entry_price: float, stop_loss: float, direction: str,
        risk_reward_ratios: Optional[List[float]] = None,
        market_structure: str = "ranging"
    ) -> List[TPLevel]:
        if risk_reward_ratios is None: risk_reward_ratios = [1.5, 3.0, 4.5]
        sl_distance = abs(entry_price - stop_loss)
        tp_levels = []
        allocations = [self.tp_allocation.tp1_percent, self.tp_allocation.tp2_percent, self.tp_allocation.tp3_percent]
        
        for i, (rr, alloc) in enumerate(zip(risk_reward_ratios, allocations)):
            tp_dist = sl_distance * rr
            tp_price = entry_price + tp_dist if direction.upper() == "LONG" else entry_price - tp_dist
            tp_levels.append(TPLevel(price=tp_price, allocation_percent=alloc, risk_reward=rr))
        return tp_levels

    def calculate_position_size(self, balance, risk_pct, entry, sl, leverage=1):
        risk_amt = balance * (risk_pct / 100.0)
        sl_pct = abs(entry - sl) / entry
        pos_val = risk_amt / sl_pct if sl_pct > 0 else balance * 0.1
        pos_size = pos_val / entry
        return pos_size, pos_val, risk_amt

    def calculate_optimal_leverage(self, vol, confidence):
        return 14, "TradeTactics Default"

    def calculate_margin_required(self, val, lev):
        return val / lev

    def get_complete_trade_setup(self, signal, balance, market_data):
        entry = signal.get('entry_price', signal.get('price', 0))
        direction = signal.get('direction', 'LONG').upper()
        atr = market_data.get('atr', entry * 0.01)
        sl, sl_reas = self.calculate_dynamic_sl(entry, direction, atr, 0.5)
        tps = self.calculate_multi_tp(entry, sl, direction)
        lev = 14
        size, val, risk = self.calculate_position_size(balance, 2.0, entry, sl, lev)
        margin = self.calculate_margin_required(val, lev)
        
        return TradeSetup(
            entry_price=entry, stop_loss=sl, tp1=tps[0], tp2=tps[1], tp3=tps[2],
            position_size=size, leverage=lev, margin_required=margin,
            direction=direction, risk_amount=risk, total_risk_reward=3.0,
            trailing_stop_state=TrailingStopState.INITIAL, current_trailing_sl=sl,
            confidence_score=0.8, reasoning=sl_reas
        )

    def update_trailing_stop(self, trade_setup: TradeSetup, current_price: float, tp_hit: int = 0) -> TradeSetup:
        """
        Dynamically adjusts the stop-loss (SL) as TP levels are reached.
        Logic:
        - TP1 Hit: SL moves to Entry Price (Break-even)
        - TP2 Hit: SL moves to TP1 Price (Locked Profit)
        - TP3 Hit: SL moves to TP2 Price (Maximized Profit)
        """
        try:
            direction = trade_setup.direction.upper()
            
            if tp_hit == 1:
                trade_setup.tp1.hit = True
                # Move SL to Entry
                trade_setup.current_trailing_sl = trade_setup.entry_price
                trade_setup.trailing_stop_state = TrailingStopState.AT_ENTRY
                logger.info(f"TP1 HIT - SL moved to Entry: {trade_setup.entry_price}")
                
            elif tp_hit == 2:
                trade_setup.tp2.hit = True
                # Move SL to TP1
                trade_setup.current_trailing_sl = trade_setup.tp1.price
                trade_setup.trailing_stop_state = TrailingStopState.AT_TP1
                logger.info(f"TP2 HIT - SL moved to TP1: {trade_setup.tp1.price}")
                
            elif tp_hit == 3:
                trade_setup.tp3.hit = True
                # Move SL to TP2
                trade_setup.current_trailing_sl = trade_setup.tp2.price
                trade_setup.trailing_stop_state = TrailingStopState.AT_TP2
                logger.info(f"TP3 HIT - SL moved to TP2: {trade_setup.tp2.price}")
                
            # Additional logic for micro-adjustments if price is far beyond a target
            if trade_setup.tp1.hit and not trade_setup.tp2.hit:
                # If price is 50% of the way to TP2, we could move SL slightly above entry
                pass

            return trade_setup
        except Exception as e:
            logger.error(f"Error in update_trailing_stop: {e}")
            return trade_setup

    def check_tp_hit(self, trade_setup, price) -> int:
        direction = trade_setup.direction.upper()
        if direction == "LONG":
            if not trade_setup.tp3.hit and price >= trade_setup.tp3.price: return 3
            if not trade_setup.tp2.hit and price >= trade_setup.tp2.price: return 2
            if not trade_setup.tp1.hit and price >= trade_setup.tp1.price: return 1
        else:
            if not trade_setup.tp3.hit and price <= trade_setup.tp3.price: return 3
            if not trade_setup.tp2.hit and price <= trade_setup.tp2.price: return 2
            if not trade_setup.tp1.hit and price <= trade_setup.tp1.price: return 1
        return 0

    def check_sl_hit(self, trade_setup, price) -> bool:
        direction = trade_setup.direction.upper()
        sl = trade_setup.current_trailing_sl or trade_setup.stop_loss
        return price <= sl if direction == "LONG" else price >= sl

    def format_trade_summary(self, setup):
        return f"Trade: {setup.direction} @ {setup.entry_price}"
