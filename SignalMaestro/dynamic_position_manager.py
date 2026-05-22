
#!/usr/bin/env python3
"""
Dynamic Position Manager for BTCUSDT Perpetual Futures (Binance USDM)
Handles auto leverage and dynamic stop loss/take profit using ATR
Implements 1:2+ risk/reward ratio with position sizing for BTC volatility
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import hmac
import hashlib

try:
    from SignalMaestro.btcusdt_trader import BTCUSDTTrader as _Trader
except ImportError:
    try:
        from btcusdt_trader import BTCUSDTTrader as _Trader
    except ImportError:
        _Trader = object

@dataclass
class PositionConfig:
    """Position configuration with dynamic parameters"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    atr_value: float
    leverage: int
    position_size: float
    risk_amount: float
    expected_return: float

class DynamicPositionManager:
    """Manages dynamic position sizing, leverage, and SL/TP for BTCUSDT Perpetual with advanced market adaptation"""

    def __init__(self, trader):
        self.logger = logging.getLogger(__name__)
        self.trader = trader
        
        # Advanced risk management parameters
        self.max_risk_per_trade = 0.02  # 2% of account
        self.min_leverage = 2
        self.max_leverage = 20
        self.base_risk_reward_ratio = 2.0  # Base 1:2 RR, will be dynamic
        
        # Multi-timeframe ATR parameters for precision
        self.atr_configs = {
            '1m': {'period': 14, 'weight': 0.15},
            '5m': {'period': 14, 'weight': 0.25},
            '15m': {'period': 14, 'weight': 0.35},
            '30m': {'period': 14, 'weight': 0.25}
        }
        
        # Dynamic ATR multipliers based on market regime
        self.regime_multipliers = {
            'trending_bull': {'sl': 1.8, 'tp': 4.5, 'rr': 2.5},
            'trending_bear': {'sl': 1.8, 'tp': 4.5, 'rr': 2.5},
            'ranging': {'sl': 1.2, 'tp': 2.4, 'rr': 2.0},
            'volatile': {'sl': 2.2, 'tp': 3.5, 'rr': 1.6},
            'breakout': {'sl': 2.5, 'tp': 6.0, 'rr': 2.4},
            'consolidation': {'sl': 1.0, 'tp': 2.0, 'rr': 2.0}
        }
        
        # Advanced volatility-based leverage scaling with market regime consideration
        self.volatility_leverage_map = {
            0.00001: {'base': 20, 'trending': 18, 'ranging': 15, 'volatile': 8},
            0.00005: {'base': 15, 'trending': 15, 'ranging': 12, 'volatile': 6},
            0.0001: {'base': 10, 'trending': 12, 'ranging': 10, 'volatile': 5},
            0.0002: {'base': 5, 'trending': 7, 'ranging': 6, 'volatile': 3},
            0.0005: {'base': 2, 'trending': 3, 'ranging': 3, 'volatile': 2}
        }
        
        # Market regime detection thresholds
        self.regime_thresholds = {
            'adx_trending': 25,
            'atr_volatile': 0.0002,
            'bb_squeeze': 0.015,
            'rsi_oversold': 30,
            'rsi_overbought': 70
        }
        
        # Trailing stop configuration
        self.trailing_config = {
            'enabled': True,
            'activation_profit': 1.5,  # Activate after 1.5% profit
            'trail_distance': 0.8,  # Trail at 0.8x ATR
            'step_size': 0.3  # Move in 0.3% increments
        }
        
        self.logger.info("⚙️ Advanced Dynamic Position Manager initialized with market regime adaptation")
    
    async def calculate_multi_timeframe_atr(self, symbol: str) -> Dict[str, float]:
        """Calculate weighted ATR across multiple timeframes for precision"""
        try:
            atr_values = {}
            weighted_atr = 0.0
            
            for timeframe, config in self.atr_configs.items():
                klines = await self.trader.get_klines(timeframe, config['period'] + 20)
                if not klines:
                    continue
                
                # Calculate ATR
                high = [float(k[2]) for k in klines]
                low = [float(k[3]) for k in klines]
                close = [float(k[4]) for k in klines]
                
                tr_list = []
                for i in range(1, len(high)):
                    tr = max(
                        high[i] - low[i],
                        abs(high[i] - close[i-1]),
                        abs(low[i] - close[i-1])
                    )
                    tr_list.append(tr)
                
                atr = sum(tr_list[-config['period']:]) / config['period']
                atr_values[timeframe] = atr
                weighted_atr += atr * config['weight']
            
            return {
                'weighted_atr': weighted_atr,
                'individual_atrs': atr_values,
                'atr_trend': 'increasing' if len(atr_values) > 1 and list(atr_values.values())[-1] > list(atr_values.values())[0] else 'decreasing'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating multi-timeframe ATR: {e}")
            return {'weighted_atr': 0.0001, 'individual_atrs': {}, 'atr_trend': 'stable'}
    
    async def detect_market_regime(self, symbol: str) -> str:
        """Detect current market regime for adaptive strategy"""
        try:
            # Get 30m data for regime detection
            klines = await self.trader.get_klines('30m', 50)
            if not klines:
                return 'ranging'
            
            close = [float(k[4]) for k in klines]
            high = [float(k[2]) for k in klines]
            low = [float(k[3]) for k in klines]
            
            # Calculate ADX for trend strength
            tr_list = []
            plus_dm = []
            minus_dm = []
            
            for i in range(1, len(high)):
                tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
                tr_list.append(tr)
                
                up_move = high[i] - high[i-1]
                down_move = low[i-1] - low[i]
                
                plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
                minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
            
            atr = sum(tr_list[-14:]) / 14
            plus_di = (sum(plus_dm[-14:]) / 14) / atr * 100 if atr > 0 else 0
            minus_di = (sum(minus_dm[-14:]) / 14) / atr * 100 if atr > 0 else 0
            adx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
            
            # Calculate Bollinger Bands width for volatility
            sma_20 = sum(close[-20:]) / 20
            std_20 = (sum([(x - sma_20) ** 2 for x in close[-20:]]) / 20) ** 0.5
            bb_width = (std_20 * 2) / sma_20
            
            # Calculate RSI
            gains = []
            losses = []
            for i in range(1, len(close)):
                change = close[i] - close[i-1]
                gains.append(change if change > 0 else 0)
                losses.append(-change if change < 0 else 0)
            
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))
            
            # Determine regime
            if adx > self.regime_thresholds['adx_trending']:
                if close[-1] > close[-20]:
                    return 'trending_bull'
                else:
                    return 'trending_bear'
            elif atr > self.regime_thresholds['atr_volatile']:
                return 'volatile'
            elif bb_width < self.regime_thresholds['bb_squeeze']:
                # Check for breakout potential
                if abs(close[-1] - sma_20) / sma_20 > 0.005:
                    return 'breakout'
                return 'consolidation'
            else:
                return 'ranging'
                
        except Exception as e:
            self.logger.error(f"Error detecting market regime: {e}")
            return 'ranging'

    async def calculate_dynamic_sl_tp(self, symbol: str, direction: str, entry_price: float, 
                                     atr_data: Dict[str, float], market_regime: str) -> Dict[str, Any]:
        """Calculate dynamic stop loss and take profit based on market conditions"""
        try:
            weighted_atr = atr_data.get('weighted_atr', 0.0001)
            
            # Get regime-specific multipliers
            multipliers = self.regime_multipliers.get(market_regime, self.regime_multipliers['ranging'])
            
            sl_distance = weighted_atr * multipliers['sl']
            tp_distance = weighted_atr * multipliers['tp']
            
            if direction.upper() in ['BUY', 'LONG']:
                stop_loss = entry_price - sl_distance
                take_profit_1 = entry_price + (tp_distance * 0.4)  # 40% of TP distance
                take_profit_2 = entry_price + (tp_distance * 0.7)  # 70% of TP distance
                take_profit_3 = entry_price + tp_distance  # Full TP distance
            else:  # SHORT/SELL
                stop_loss = entry_price + sl_distance
                take_profit_1 = entry_price - (tp_distance * 0.4)
                take_profit_2 = entry_price - (tp_distance * 0.7)
                take_profit_3 = entry_price - tp_distance
            
            # Calculate actual risk-reward ratio
            risk = abs(entry_price - stop_loss)
            reward = abs(entry_price - take_profit_3)
            actual_rr = reward / risk if risk > 0 else multipliers['rr']
            
            # Trailing stop configuration
            trailing_stop = None
            if self.trailing_config['enabled']:
                activation_price = entry_price + (entry_price * self.trailing_config['activation_profit'] / 100) if direction.upper() in ['BUY', 'LONG'] else entry_price - (entry_price * self.trailing_config['activation_profit'] / 100)
                trail_distance = weighted_atr * self.trailing_config['trail_distance']
                
                trailing_stop = {
                    'activation_price': activation_price,
                    'trail_distance': trail_distance,
                    'active': False
                }
            
            sl_tp_config = {
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'take_profit_3': take_profit_3,
                'tp1_close_percent': 33.0,
                'tp2_close_percent': 33.0,
                'tp3_close_percent': 34.0,
                'risk_reward_ratio': actual_rr,
                'atr_used': weighted_atr,
                'sl_multiplier': multipliers['sl'],
                'tp_multiplier': multipliers['tp'],
                'market_regime': market_regime,
                'trailing_stop': trailing_stop
            }
            
            self.logger.info(f"📊 Dynamic SL/TP: Entry {entry_price:.6f}, SL {stop_loss:.6f}, TP1 {take_profit_1:.6f}, TP2 {take_profit_2:.6f}, TP3 {take_profit_3:.6f}")
            self.logger.info(f"📈 Risk-Reward: 1:{actual_rr:.2f} | Regime: {market_regime}")
            
            return sl_tp_config
            
        except Exception as e:
            self.logger.error(f"Error calculating dynamic SL/TP: {e}")
            # Fallback to conservative values
            sl_distance = entry_price * 0.015
            tp_distance = entry_price * 0.03
            
            return {
                'stop_loss': entry_price - sl_distance if direction.upper() in ['BUY', 'LONG'] else entry_price + sl_distance,
                'take_profit_1': entry_price + tp_distance * 0.4 if direction.upper() in ['BUY', 'LONG'] else entry_price - tp_distance * 0.4,
                'take_profit_2': entry_price + tp_distance * 0.7 if direction.upper() in ['BUY', 'LONG'] else entry_price - tp_distance * 0.7,
                'take_profit_3': entry_price + tp_distance if direction.upper() in ['BUY', 'LONG'] else entry_price - tp_distance,
                'risk_reward_ratio': 2.0,
                'market_regime': 'unknown'
            }
    
    async def update_trailing_stop(self, position: Dict[str, Any], current_price: float) -> Optional[float]:
        """Update trailing stop based on current price movement"""
        try:
            if not position.get('trailing_stop') or not position['trailing_stop'].get('activation_price'):
                return None
            
            trailing_config = position['trailing_stop']
            direction = position.get('direction', 'LONG')
            
            # Check if trailing stop should be activated
            if not trailing_config.get('active'):
                if direction.upper() in ['BUY', 'LONG']:
                    if current_price >= trailing_config['activation_price']:
                        trailing_config['active'] = True
                        self.logger.info(f"✅ Trailing stop activated at {current_price:.6f}")
                else:
                    if current_price <= trailing_config['activation_price']:
                        trailing_config['active'] = True
                        self.logger.info(f"✅ Trailing stop activated at {current_price:.6f}")
            
            # Update trailing stop if active
            if trailing_config.get('active'):
                trail_distance = trailing_config['trail_distance']
                current_sl = position.get('stop_loss')
                
                if direction.upper() in ['BUY', 'LONG']:
                    new_sl = current_price - trail_distance
                    if new_sl > current_sl:
                        self.logger.info(f"📈 Trailing SL updated: {current_sl:.6f} → {new_sl:.6f}")
                        return new_sl
                else:
                    new_sl = current_price + trail_distance
                    if new_sl < current_sl:
                        self.logger.info(f"📉 Trailing SL updated: {current_sl:.6f} → {new_sl:.6f}")
                        return new_sl
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error updating trailing stop: {e}")
            return None
    
    async def create_comprehensive_position_config(self, symbol: str, direction: str, 
                                                   entry_price: float, account_balance: float) -> PositionConfig:
        """Create comprehensive position configuration with all dynamic parameters"""
        try:
            # Get multi-timeframe ATR
            atr_data = await self.calculate_multi_timeframe_atr(symbol)
            
            # Detect market regime
            market_regime = await self.detect_market_regime(symbol)
            
            # Calculate optimal leverage
            leverage = await self.calculate_optimal_leverage(symbol, atr_data, market_regime, account_balance)
            
            # Calculate dynamic SL/TP
            sl_tp_config = await self.calculate_dynamic_sl_tp(symbol, direction, entry_price, atr_data, market_regime)
            
            # Calculate position size based on risk
            risk_amount = account_balance * self.max_risk_per_trade
            sl_distance = abs(entry_price - sl_tp_config['stop_loss'])
            position_size = (risk_amount / sl_distance) if sl_distance > 0 else 0
            
            # Expected return calculation
            tp_distance = abs(entry_price - sl_tp_config['take_profit_3'])
            expected_return = position_size * tp_distance
            
            position_config = PositionConfig(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=sl_tp_config['stop_loss'],
                take_profit=sl_tp_config['take_profit_3'],
                atr_value=atr_data['weighted_atr'],
                leverage=leverage,
                position_size=position_size,
                risk_amount=risk_amount,
                expected_return=expected_return
            )
            
            self.logger.info(f"✅ Comprehensive Position Config Created:")
            self.logger.info(f"   Symbol: {symbol} | Direction: {direction}")
            self.logger.info(f"   Entry: {entry_price:.6f} | Leverage: {leverage}x")
            self.logger.info(f"   SL: {sl_tp_config['stop_loss']:.6f} | TP: {sl_tp_config['take_profit_3']:.6f}")
            self.logger.info(f"   Position Size: {position_size:.4f} | Risk: ${risk_amount:.2f}")
            self.logger.info(f"   Expected Return: ${expected_return:.2f} | RR: 1:{sl_tp_config['risk_reward_ratio']:.2f}")
            self.logger.info(f"   Market Regime: {market_regime} | ATR: {atr_data['weighted_atr']:.6f}")
            
            return position_config
            
        except Exception as e:
            self.logger.error(f"Error creating position config: {e}")
            raise

            return 'ranging'
    
    async def calculate_optimal_leverage(self, symbol: str, atr_data: Dict[str, float], market_regime: str, account_balance: float) -> int:
        """Calculate optimal leverage based on ATR volatility and market regime"""
        try:
            atr_value = atr_data.get('weighted_atr', 0.0001)
            
            if atr_value <= 0:
                return self.min_leverage
            
            # Find base leverage from volatility
            base_leverage = self.min_leverage
            
            for atr_threshold, leverage_map in sorted(self.volatility_leverage_map.items()):
                if atr_value >= atr_threshold:
                    # Adjust leverage based on market regime
                    regime_type = 'trending' if 'trending' in market_regime else 'ranging' if market_regime == 'ranging' else 'volatile'
                    base_leverage = leverage_map.get(regime_type, leverage_map['base'])
                    break
            
            # Additional adjustment for ATR trend
            if atr_data.get('atr_trend') == 'increasing':
                base_leverage = max(self.min_leverage, int(base_leverage * 0.85))
            
            # Ensure within limits
            optimal_leverage = max(self.min_leverage, min(base_leverage, self.max_leverage))
            
            self.logger.info(f"🎯 Optimal leverage: {optimal_leverage}x (Regime: {market_regime}, ATR: {atr_value:.6f})")
            return optimal_leverage
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal leverage: {e}")
            return self.min_leverage
    
    async def calculate_position_size(self, entry_price: float, stop_loss: float, 
                                    leverage: int, account_balance: float) -> Tuple[float, float]:
        """Calculate position size based on risk management"""
        try:
            # Calculate risk amount (2% of account)
            risk_amount = account_balance * self.max_risk_per_trade
            
            # Calculate stop loss distance
            sl_distance = abs(entry_price - stop_loss)
            
            if sl_distance <= 0:
                return 0.0, 0.0
            
            # Calculate position size considering leverage
            # Risk = Position Size * Price * SL Distance / Leverage
            # Position Size = Risk * Leverage / (Price * SL Distance)
            position_size = (risk_amount * leverage) / (entry_price * sl_distance)
            
            # Calculate notional value
            notional_value = position_size * entry_price
            
            self.logger.info(f"💰 Risk: ${risk_amount:.2f} | Position: {position_size:.6f} | Notional: ${notional_value:.2f}")
            
            return position_size, notional_value
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0.0, 0.0
    
    async def set_leverage(self, leverage: int) -> bool:
        """Set leverage for BTCUSDT Perpetual Futures trading"""
        try:
            if hasattr(self.trader, 'change_leverage'):
                return await self.trader.change_leverage(self.trader.symbol, leverage)
            self.logger.warning("Trader does not support change_leverage — skipping")
            return False
        except Exception as e:
            self.logger.error(f"Error setting leverage: {e}")
            return False
    
    async def place_market_order(self, direction: str, quantity: float) -> Optional[Dict[str, Any]]:
        """Place market order for BTCUSDT Perpetual Futures"""
        try:
            endpoint = "/fapi/v1/order"
            timestamp = int(time.time() * 1000)
            
            side = "BUY" if direction.upper() == "BUY" else "SELL"
            
            params = {
                'symbol': self.trader.symbol,
                'side': side,
                'type': 'MARKET',
                'quantity': f"{quantity:.6f}",
                'timestamp': timestamp
            }
            
            # Create signed query string using trader's _sign method
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = self.trader._sign(query_string)

            url = f"{self.trader.base_url}{endpoint}"

            headers = {
                'X-MBX-APIKEY': self.trader.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            data = f"{query_string}&signature={signature}"

            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"✅ Market order placed: {side} {quantity:.6f} {self.trader.symbol}")
                        return result
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Failed to place order: {response.status} - {error_text}")
                        return None

        except Exception as e:
            self.logger.error(f"Error placing market order: {e}")
            return None
    
    async def place_stop_order(self, direction: str, quantity: float, stop_price: float) -> Optional[Dict[str, Any]]:
        """Place stop loss order"""
        try:
            endpoint = "/fapi/v1/order"
            timestamp = int(time.time() * 1000)
            
            # For stop loss, we need opposite direction
            side = "SELL" if direction.upper() == "BUY" else "BUY"
            
            params = {
                'symbol': self.trader.symbol,
                'side': side,
                'type': 'STOP_MARKET',
                'quantity': f"{quantity:.6f}",
                'stopPrice': f"{stop_price:.5f}",
                'timeInForce': 'GTC',
                'timestamp': timestamp
            }
            
            # Create signed query string using trader's _sign method
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = self.trader._sign(query_string)

            url = f"{self.trader.base_url}{endpoint}"

            headers = {
                'X-MBX-APIKEY': self.trader.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            data = f"{query_string}&signature={signature}"

            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"🛡️ Stop loss placed: {stop_price:.5f}")
                        return result
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Failed to place stop order: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"Error placing stop order: {e}")
            return None
    
    async def place_limit_order(self, direction: str, quantity: float, limit_price: float) -> Optional[Dict[str, Any]]:
        """Place take profit limit order"""
        try:
            endpoint = "/fapi/v1/order"
            timestamp = int(time.time() * 1000)
            
            # For take profit, we need opposite direction
            side = "SELL" if direction.upper() == "BUY" else "BUY"
            
            params = {
                'symbol': self.trader.symbol,
                'side': side,
                'type': 'LIMIT',
                'quantity': f"{quantity:.6f}",
                'price': f"{limit_price:.5f}",
                'timeInForce': 'GTC',
                'timestamp': timestamp
            }
            
            # Create signed query string using trader's _sign method
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = self.trader._sign(query_string)

            url = f"{self.trader.base_url}{endpoint}"

            headers = {
                'X-MBX-APIKEY': self.trader.api_key,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            data = f"{query_string}&signature={signature}"

            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"🎯 Take profit placed: {limit_price:.5f}")
                        return result
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Failed to place limit order: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"Error placing limit order: {e}")
            return None
    
    async def execute_position(self, signal_data: Dict[str, Any]) -> Optional[PositionConfig]:
        """Execute complete position with dynamic parameters"""
        try:
            # Extract signal data
            direction = signal_data['action']
            entry_price = signal_data['entry_price']
            stop_loss = signal_data['stop_loss']
            take_profit = signal_data['take_profit']
            atr_value = signal_data['atr_value']
            
            # Get account balance
            account_info = await self.trader.get_account_balance()
            if not account_info:
                self.logger.error("❌ Failed to get account balance")
                return None
            
            balance = account_info['available_balance']
            if balance <= 0:
                self.logger.error("❌ Insufficient account balance")
                return None
            
            # Calculate optimal leverage
            optimal_leverage = await self.calculate_optimal_leverage(atr_value, balance)
            
            # Set leverage
            if not await self.set_leverage(optimal_leverage):
                self.logger.error("❌ Failed to set leverage")
                return None
            
            # Calculate position size
            position_size, notional_value = await self.calculate_position_size(
                entry_price, stop_loss, optimal_leverage, balance
            )
            
            if position_size <= 0:
                self.logger.error("❌ Invalid position size calculated")
                return None
            
            # Place market order
            market_order = await self.place_market_order(direction, position_size)
            if not market_order:
                self.logger.error("❌ Failed to place market order")
                return None
            
            # Place stop loss
            stop_order = await self.place_stop_order(direction, position_size, stop_loss)
            if not stop_order:
                self.logger.warning("⚠️ Failed to place stop loss order")
            
            # Place take profit
            tp_order = await self.place_limit_order(direction, position_size, take_profit)
            if not tp_order:
                self.logger.warning("⚠️ Failed to place take profit order")
            
            # Create position config
            risk_amount = balance * self.max_risk_per_trade
            sl_distance = abs(entry_price - stop_loss)
            tp_distance = abs(take_profit - entry_price)
            expected_return = (tp_distance / sl_distance) * risk_amount
            
            position_config = PositionConfig(
                symbol=self.trader.symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                atr_value=atr_value,
                leverage=optimal_leverage,
                position_size=position_size,
                risk_amount=risk_amount,
                expected_return=expected_return
            )
            
            self.logger.info(f"✅ Position executed: {direction} {position_size:.6f} @ {entry_price:.5f}")
            self.logger.info(f"   Leverage: {optimal_leverage}x | Risk: ${risk_amount:.2f} | Expected: ${expected_return:.2f}")
            
            return position_config
            
        except Exception as e:
            self.logger.error(f"Error executing position: {e}")
            return None
