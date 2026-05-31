#!/usr/bin/env python3
"""
Dynamic Leverage Management System for Binance Futures USDM Trading

This module implements a sophisticated volatility-based leverage adjustment system that:
- Calculates real-time volatility using ATR and price movement analysis
- Implements dynamic leverage scaling (2x-10x based on volatility)
- Provides safe leverage management that prevents over-leveraging in volatile markets
- Maximizes profits in stable conditions while maintaining strict risk management

Key Features:
- Multi-timeframe volatility analysis
- Adaptive leverage scaling based on market conditions
- Risk-adjusted position sizing
- Comprehensive logging and monitoring
- Integration with existing trading systems
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import sqlite3
import json
from decimal import Decimal, ROUND_DOWN

@dataclass
class VolatilityProfile:
    """Volatility profile for a trading symbol"""
    symbol: str
    atr_14: float
    atr_percentage: float
    price_volatility: float
    volume_volatility: float
    hourly_volatility: float
    daily_volatility: float
    volatility_score: float
    recommended_leverage: int
    max_safe_leverage: int
    risk_level: str
    last_updated: datetime

@dataclass
class LeverageAdjustment:
    """Leverage adjustment record"""
    symbol: str
    old_leverage: int
    new_leverage: int
    volatility_score: float
    reason: str
    timestamp: datetime
    position_size_impact: float

class DynamicLeverageManager:
    """Dynamic leverage management system for futures trading"""
    
    def __init__(self, database_path: str = "leverage_management.db"):
        self.logger = logging.getLogger(__name__)
        self.database_path = database_path
        
        # Leverage configuration
        self.leverage_config = {
            'min_leverage': 2,
            'max_leverage': 10,
            'default_leverage': 5,
            'conservative_max': 6,  # For high volatility periods
            'aggressive_max': 10,   # For low volatility periods
        }
        
        # Volatility thresholds for leverage scaling
        self.volatility_thresholds = {
            'very_low': 0.5,    # Volatility score < 0.5 = Very stable
            'low': 1.0,         # Volatility score < 1.0 = Stable
            'medium': 2.0,      # Volatility score < 2.0 = Moderate
            'high': 3.5,        # Volatility score < 3.5 = High
            'very_high': 5.0    # Volatility score >= 5.0 = Extreme
        }
        
        # Leverage mapping based on volatility
        self.leverage_mapping = {
            'very_low': {'min': 8, 'max': 10, 'default': 9},
            'low': {'min': 6, 'max': 8, 'default': 7},
            'medium': {'min': 4, 'max': 6, 'default': 5},
            'high': {'min': 3, 'max': 4, 'default': 3},
            'very_high': {'min': 2, 'max': 3, 'default': 2}
        }
        
        # Risk management parameters
        self.risk_params = {
            'max_portfolio_leverage': 5.0,  # Average leverage across all positions
            'volatility_lookback_periods': 100,
            'min_data_points': 50,
            'leverage_change_cooldown': 300,  # 5 minutes between adjustments
            'emergency_volatility_threshold': 8.0  # Emergency leverage reduction
        }
        
        # In-memory cache for volatility profiles
        self.volatility_cache = {}
        self.last_leverage_adjustment = {}
        
        # Initialize database
        self._init_database()
        
        self.logger.info("🎯 Dynamic Leverage Manager initialized with adaptive volatility-based scaling")
    
    def _init_database(self):
        """Initialize SQLite database for leverage management tracking"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Volatility profiles table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS volatility_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        atr_14 REAL,
                        atr_percentage REAL,
                        price_volatility REAL,
                        volume_volatility REAL,
                        hourly_volatility REAL,
                        daily_volatility REAL,
                        volatility_score REAL,
                        recommended_leverage INTEGER,
                        max_safe_leverage INTEGER,
                        risk_level TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, timestamp)
                    )
                ''')
                
                # Leverage adjustments table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS leverage_adjustments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        old_leverage INTEGER,
                        new_leverage INTEGER,
                        volatility_score REAL,
                        reason TEXT,
                        position_size_impact REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Leverage history table for tracking performance
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS leverage_performance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        leverage INTEGER,
                        entry_price REAL,
                        exit_price REAL,
                        profit_loss REAL,
                        profit_percentage REAL,
                        volatility_at_entry REAL,
                        hold_duration INTEGER,  -- in minutes
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                conn.commit()
                self.logger.info("📊 Leverage management database initialized successfully")
                
        except Exception as e:
            self.logger.error(f"❌ Error initializing leverage database: {e}")
            raise
    
    async def calculate_volatility_profile(self, symbol: str, ohlcv_data: Dict[str, List]) -> Optional[VolatilityProfile]:
        """
        Calculate comprehensive volatility profile for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            ohlcv_data: Multi-timeframe OHLCV data
            
        Returns:
            VolatilityProfile object with all volatility metrics
        """
        try:
            # Prepare dataframes for different timeframes
            timeframes = ['5m', '15m', '1h', '4h', '1d']
            df_data = {}
            
            for tf in timeframes:
                if tf in ohlcv_data and len(ohlcv_data[tf]) >= self.risk_params['min_data_points']:
                    df_data[tf] = self._prepare_dataframe(ohlcv_data[tf])
            
            if len(df_data) < 3:
                self.logger.warning(f"⚠️ Insufficient data for {symbol} volatility analysis")
                return None
            
            # Use 1-hour data as primary timeframe for volatility calculation
            primary_df = df_data.get('1h') or df_data.get('15m') or list(df_data.values())[0]
            
            # Calculate ATR (Average True Range)
            atr_14, atr_percentage = await self._calculate_atr(primary_df)
            
            # Calculate price volatility (standard deviation of returns)
            price_volatility = await self._calculate_price_volatility(primary_df)
            
            # Calculate volume volatility
            volume_volatility = await self._calculate_volume_volatility(primary_df)
            
            # Calculate hourly volatility using shorter timeframe
            hourly_volatility = 0.0
            if '15m' in df_data:
                hourly_volatility = await self._calculate_short_term_volatility(df_data['15m'])
            
            # Calculate daily volatility using longer timeframe
            daily_volatility = 0.0
            if '4h' in df_data:
                daily_volatility = await self._calculate_daily_volatility(df_data['4h'])
            elif '1h' in df_data:
                daily_volatility = await self._calculate_daily_volatility(df_data['1h'])
            
            # Calculate composite volatility score
            volatility_score = await self._calculate_volatility_score(
                atr_percentage, price_volatility, volume_volatility, 
                hourly_volatility, daily_volatility
            )
            
            # Determine risk level
            risk_level = self._determine_risk_level(volatility_score)
            
            # Calculate recommended leverage
            recommended_leverage, max_safe_leverage = self._calculate_recommended_leverage(
                volatility_score, risk_level
            )
            
            profile = VolatilityProfile(
                symbol=symbol,
                atr_14=atr_14,
                atr_percentage=atr_percentage,
                price_volatility=price_volatility,
                volume_volatility=volume_volatility,
                hourly_volatility=hourly_volatility,
                daily_volatility=daily_volatility,
                volatility_score=volatility_score,
                recommended_leverage=recommended_leverage,
                max_safe_leverage=max_safe_leverage,
                risk_level=risk_level,
                last_updated=datetime.now()
            )
            
            # Cache the profile
            self.volatility_cache[symbol] = profile
            
            # Store in database
            await self._store_volatility_profile(profile)
            
            self.logger.info(f"📈 {symbol}: Volatility Score: {volatility_score:.2f}, "
                           f"Risk: {risk_level}, Recommended Leverage: {recommended_leverage}x")
            
            return profile
            
        except Exception as e:
            self.logger.error(f"❌ Error calculating volatility profile for {symbol}: {e}")
            return None
    
    def _prepare_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Convert OHLCV data to pandas DataFrame"""
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.dropna()
    
    async def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Tuple[float, float]:
        """Calculate Average True Range and ATR percentage"""
        try:
            if len(df) < period + 1:
                return 0.0, 0.0
            
            # Calculate True Range
            high_low = df['high'] - df['low']
            high_close_prev = np.abs(df['high'] - df['close'].shift(1))
            low_close_prev = np.abs(df['low'] - df['close'].shift(1))
            
            true_range = np.maximum(high_low, np.maximum(high_close_prev, low_close_prev))
            
            # Calculate ATR using Simple Moving Average
            atr = true_range.rolling(window=period).mean()
            current_atr = float(atr.iloc[-1])
            current_price = float(df['close'].iloc[-1])
            
            # Calculate ATR as percentage of current price
            atr_percentage = (current_atr / current_price) * 100
            
            return current_atr, atr_percentage
            
        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")
            return 0.0, 0.0
    
    async def _calculate_price_volatility(self, df: pd.DataFrame, period: int = 20) -> float:
        """Calculate price volatility using standard deviation of returns"""
        try:
            if len(df) < period:
                return 0.0
            
            # Calculate returns
            returns = df['close'].pct_change().dropna()
            
            # Calculate rolling volatility (annualized)
            volatility = returns.rolling(window=period).std() * np.sqrt(365 * 24)  # For hourly data
            
            return float(volatility.iloc[-1] * 100)  # Convert to percentage
            
        except Exception as e:
            self.logger.error(f"Error calculating price volatility: {e}")
            return 0.0
    
    async def _calculate_volume_volatility(self, df: pd.DataFrame, period: int = 20) -> float:
        """Calculate volume volatility"""
        try:
            if len(df) < period:
                return 0.0
            
            # Calculate volume changes
            volume_changes = df['volume'].pct_change().dropna()
            
            # Calculate rolling standard deviation
            volume_volatility = volume_changes.rolling(window=period).std()
            
            return float(volume_volatility.iloc[-1] * 100)  # Convert to percentage
            
        except Exception as e:
            self.logger.error(f"Error calculating volume volatility: {e}")
            return 0.0
    
    async def _calculate_short_term_volatility(self, df: pd.DataFrame) -> float:
        """Calculate short-term volatility using 15-minute data"""
        try:
            if len(df) < 24:  # Need at least 6 hours of 15m data
                return 0.0
            
            # Calculate 6-hour rolling volatility
            returns = df['close'].pct_change().dropna()
            short_vol = returns.rolling(window=24).std() * np.sqrt(96)  # Annualized for 15m data
            
            return float(short_vol.iloc[-1] * 100)
            
        except Exception as e:
            self.logger.error(f"Error calculating short-term volatility: {e}")
            return 0.0
    
    async def _calculate_daily_volatility(self, df: pd.DataFrame) -> float:
        """Calculate daily volatility using longer timeframe data"""
        try:
            if len(df) < 24:
                return 0.0
            
            # Calculate 24-hour rolling volatility
            returns = df['close'].pct_change().dropna()
            
            # Adjust for timeframe
            if len(df) > 168:  # If we have more than a week of data
                periods_per_day = 6 if 'close' in df.columns else 24  # 4h or 1h data
                daily_vol = returns.rolling(window=periods_per_day).std() * np.sqrt(365)
            else:
                daily_vol = returns.std() * np.sqrt(365)
            
            return float(daily_vol.iloc[-1] * 100) if hasattr(daily_vol, 'iloc') else float(daily_vol * 100)
            
        except Exception as e:
            self.logger.error(f"Error calculating daily volatility: {e}")
            return 0.0
    
    async def _calculate_volatility_score(self, atr_percentage: float, price_volatility: float,
                                        volume_volatility: float, hourly_volatility: float,
                                        daily_volatility: float) -> float:
        """
        Calculate composite volatility score
        
        The score combines multiple volatility measures with different weights:
        - ATR percentage: 30% (immediate volatility)
        - Price volatility: 25% (recent price movements)
        - Hourly volatility: 20% (short-term trends)
        - Daily volatility: 15% (medium-term trends)
        - Volume volatility: 10% (market participation)
        """
        try:
            # Normalize each component (these are rough normalization factors based on crypto markets)
            normalized_atr = min(atr_percentage / 2.0, 5.0)  # Cap at 5
            normalized_price = min(price_volatility / 50.0, 5.0)  # Cap at 5
            normalized_volume = min(volume_volatility / 100.0, 3.0)  # Cap at 3
            normalized_hourly = min(hourly_volatility / 80.0, 4.0)  # Cap at 4
            normalized_daily = min(daily_volatility / 60.0, 4.0)  # Cap at 4
            
            # Weighted composite score
            volatility_score = (
                normalized_atr * 0.30 +
                normalized_price * 0.25 +
                normalized_hourly * 0.20 +
                normalized_daily * 0.15 +
                normalized_volume * 0.10
            )
            
            return round(volatility_score, 2)
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility score: {e}")
            return 2.0  # Default medium volatility
    
    def _determine_risk_level(self, volatility_score: float) -> str:
        """Determine risk level based on volatility score"""
        if volatility_score < self.volatility_thresholds['very_low']:
            return 'very_low'
        elif volatility_score < self.volatility_thresholds['low']:
            return 'low'
        elif volatility_score < self.volatility_thresholds['medium']:
            return 'medium'
        elif volatility_score < self.volatility_thresholds['high']:
            return 'high'
        else:
            return 'very_high'
    
    def _calculate_recommended_leverage(self, volatility_score: float, risk_level: str) -> Tuple[int, int]:
        """Calculate recommended and maximum safe leverage"""
        try:
            # Get leverage range for this risk level
            leverage_range = self.leverage_mapping.get(risk_level, self.leverage_mapping['medium'])
            
            # Calculate recommended leverage within the range
            # Lower volatility = higher leverage (up to max)
            # Higher volatility = lower leverage (down to min)
            min_lev = leverage_range['min']
            max_lev = leverage_range['max']
            default_lev = leverage_range['default']
            
            # Fine-tune based on exact volatility score
            if risk_level == 'very_low':
                # Very stable - can use high leverage
                recommended = max_lev if volatility_score < 0.3 else max(min_lev, max_lev - 1)
            elif risk_level == 'low':
                # Stable - moderate to high leverage
                recommended = default_lev if volatility_score < 0.8 else min_lev
            elif risk_level == 'medium':
                # Moderate volatility - balanced approach
                recommended = default_lev
            elif risk_level == 'high':
                # High volatility - conservative leverage
                recommended = min_lev if volatility_score > 3.0 else max(min_lev, default_lev - 1)
            else:  # very_high
                # Extreme volatility - minimum leverage
                recommended = min_lev
            
            # Emergency volatility check
            if volatility_score >= self.risk_params['emergency_volatility_threshold']:
                recommended = self.leverage_config['min_leverage']
                max_safe = self.leverage_config['min_leverage']
            else:
                max_safe = max_lev
            
            # Ensure values are within global limits
            recommended = max(self.leverage_config['min_leverage'], 
                            min(recommended, self.leverage_config['max_leverage']))
            max_safe = max(self.leverage_config['min_leverage'], 
                          min(max_safe, self.leverage_config['max_leverage']))
            
            return recommended, max_safe
            
        except Exception as e:
            self.logger.error(f"Error calculating recommended leverage: {e}")
            return self.leverage_config['default_leverage'], self.leverage_config['default_leverage']
    
    async def adjust_leverage_for_symbol(self, symbol: str, current_leverage: int, 
                                       ohlcv_data: Dict[str, List]) -> Optional[LeverageAdjustment]:
        """
        Adjust leverage for a specific symbol based on current volatility
        
        Args:
            symbol: Trading symbol
            current_leverage: Current leverage setting
            ohlcv_data: Market data for volatility calculation
            
        Returns:
            LeverageAdjustment object if leverage should be changed
        """
        try:
            # Check cooldown period
            if symbol in self.last_leverage_adjustment:
                last_adjustment = self.last_leverage_adjustment[symbol]
                time_since_last = (datetime.now() - last_adjustment).total_seconds()
                if time_since_last < self.risk_params['leverage_change_cooldown']:
                    self.logger.debug(f"🕐 {symbol}: Leverage adjustment cooldown active "
                                    f"({int(self.risk_params['leverage_change_cooldown'] - time_since_last)}s remaining)")
                    return None
            
            # Calculate current volatility profile
            volatility_profile = await self.calculate_volatility_profile(symbol, ohlcv_data)
            if not volatility_profile:
                return None
            
            recommended_leverage = volatility_profile.recommended_leverage
            
            # Check if adjustment is needed
            if current_leverage == recommended_leverage:
                self.logger.debug(f"✅ {symbol}: Leverage {current_leverage}x is optimal for current volatility")
                return None
            
            # Determine adjustment reason
            if volatility_profile.volatility_score >= self.risk_params['emergency_volatility_threshold']:
                reason = f"Emergency volatility reduction (score: {volatility_profile.volatility_score:.2f})"
            elif current_leverage > recommended_leverage:
                reason = f"Reducing leverage due to increased volatility ({volatility_profile.risk_level})"
            else:
                reason = f"Increasing leverage due to decreased volatility ({volatility_profile.risk_level})"
            
            # Calculate position size impact
            position_size_impact = (recommended_leverage / current_leverage) - 1
            
            # Create adjustment record
            adjustment = LeverageAdjustment(
                symbol=symbol,
                old_leverage=current_leverage,
                new_leverage=recommended_leverage,
                volatility_score=volatility_profile.volatility_score,
                reason=reason,
                timestamp=datetime.now(),
                position_size_impact=position_size_impact
            )
            
            # Update last adjustment time
            self.last_leverage_adjustment[symbol] = datetime.now()
            
            # Store in database
            await self._store_leverage_adjustment(adjustment)
            
            self.logger.info(f"⚡ {symbol}: Leverage adjustment {current_leverage}x → {recommended_leverage}x "
                           f"(Volatility: {volatility_profile.volatility_score:.2f}, Risk: {volatility_profile.risk_level})")
            
            return adjustment
            
        except Exception as e:
            self.logger.error(f"❌ Error adjusting leverage for {symbol}: {e}")
            return None
    
    async def get_optimal_leverage_for_trade(self, symbol: str, trade_direction: str, 
                                           trade_size_usdt: float, ohlcv_data: Dict[str, List]) -> Dict[str, Any]:
        """
        Get optimal leverage for a specific trade considering volatility and risk management
        
        Args:
            symbol: Trading symbol
            trade_direction: 'LONG' or 'SHORT'
            trade_size_usdt: Trade size in USDT
            ohlcv_data: Market data
            
        Returns:
            Dictionary with leverage recommendation and risk analysis
        """
        try:
            # Get volatility profile
            volatility_profile = await self.calculate_volatility_profile(symbol, ohlcv_data)
            if not volatility_profile:
                return {
                    'recommended_leverage': self.leverage_config['default_leverage'],
                    'max_leverage': self.leverage_config['max_leverage'],
                    'auto_leverage': self.leverage_config['default_leverage'],
                    'margin_type': 'CROSS',
                    'cross_margin_enabled': True,
                    'leverage_mode': 'AUTO',
                    'risk_analysis': 'Insufficient data for volatility analysis',
                    'confidence': 'low'
                }
            
            base_leverage = volatility_profile.recommended_leverage
            max_leverage = volatility_profile.max_safe_leverage
            
            # Adjust for trade size (larger trades = lower leverage)
            size_adjustment = 1.0
            if trade_size_usdt > 100:  # For trades larger than $100
                size_adjustment = max(0.8, 1 - (trade_size_usdt - 100) / 1000)
            
            # Adjust for trade direction and current volatility
            direction_adjustment = 1.0
            if trade_direction == 'SHORT' and volatility_profile.volatility_score > 2.0:
                # Be more conservative with shorts in volatile markets
                direction_adjustment = 0.9
            
            # Calculate final leverage
            adjusted_leverage = int(base_leverage * size_adjustment * direction_adjustment)
            adjusted_leverage = max(self.leverage_config['min_leverage'], 
                                  min(adjusted_leverage, max_leverage))
            
            # Auto leverage calculation (dynamic based on market conditions)
            auto_leverage = self._calculate_auto_leverage(volatility_profile, trade_size_usdt, trade_direction)
            
            # Cross margin settings
            cross_margin_enabled = True
            margin_type = 'CROSS'  # Always use cross margin for better risk distribution
            
            # Risk analysis
            risk_factors = []
            if volatility_profile.volatility_score > 3.0:
                risk_factors.append("High volatility detected")
            if trade_size_usdt > 200:
                risk_factors.append("Large position size")
            if volatility_profile.hourly_volatility > 60:
                risk_factors.append("High short-term volatility")
            
            confidence = 'high'
            if len(risk_factors) > 2:
                confidence = 'low'
            elif len(risk_factors) > 0:
                confidence = 'medium'
            
            return {
                'recommended_leverage': adjusted_leverage,
                'max_leverage': max_leverage,
                'auto_leverage': auto_leverage,
                'margin_type': margin_type,
                'cross_margin_enabled': cross_margin_enabled,
                'leverage_mode': 'AUTO',
                'volatility_score': volatility_profile.volatility_score,
                'risk_level': volatility_profile.risk_level,
                'risk_factors': risk_factors,
                'risk_analysis': f"Volatility: {volatility_profile.risk_level}, Score: {volatility_profile.volatility_score:.2f}",
                'confidence': confidence,
                'atr_percentage': volatility_profile.atr_percentage,
                'size_adjustment': size_adjustment,
                'direction_adjustment': direction_adjustment,
                'margin_settings': {
                    'type': margin_type,
                    'cross_enabled': cross_margin_enabled,
                    'isolated_enabled': False,
                    'auto_add_margin': True,
                    'maintenance_margin_ratio': self._calculate_maintenance_margin_ratio(adjusted_leverage)
                }
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error getting optimal leverage for {symbol}: {e}")
            return {
                'recommended_leverage': self.leverage_config['default_leverage'],
                'max_leverage': self.leverage_config['max_leverage'],
                'risk_analysis': f'Error in analysis: {e}',
                'confidence': 'low'
            }
    
    async def monitor_portfolio_leverage(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Monitor overall portfolio leverage and risk
        
        Args:
            positions: List of open positions with leverage info
            
        Returns:
            Portfolio risk analysis and recommendations
        """
        try:
            if not positions:
                return {
                    'portfolio_leverage': 0.0,
                    'risk_level': 'none',
                    'recommendations': ['No open positions'],
                    'total_exposure': 0.0
                }
            
            total_notional_value = 0.0
            total_margin_used = 0.0
            weighted_volatility = 0.0
            
            high_risk_positions = []
            
            for position in positions:
                symbol = position.get('symbol', '')
                size = position.get('size', 0.0)
                leverage = position.get('leverage', 1)
                mark_price = position.get('markPrice', 0.0)
                
                notional_value = size * mark_price
                margin_used = notional_value / leverage if leverage > 0 else notional_value
                
                total_notional_value += notional_value
                total_margin_used += margin_used
                
                # Get volatility for this symbol if available
                if symbol in self.volatility_cache:
                    vol_profile = self.volatility_cache[symbol]
                    weighted_volatility += vol_profile.volatility_score * (notional_value / total_notional_value if total_notional_value > 0 else 0)
                    
                    if vol_profile.risk_level in ['high', 'very_high'] and leverage > 4:
                        high_risk_positions.append({
                            'symbol': symbol,
                            'leverage': leverage,
                            'volatility': vol_profile.volatility_score,
                            'risk_level': vol_profile.risk_level
                        })
            
            # Calculate portfolio leverage
            portfolio_leverage = total_notional_value / total_margin_used if total_margin_used > 0 else 0.0
            
            # Determine portfolio risk level
            portfolio_risk = 'low'
            if portfolio_leverage > self.risk_params['max_portfolio_leverage']:
                portfolio_risk = 'high'
            elif portfolio_leverage > self.risk_params['max_portfolio_leverage'] * 0.7:
                portfolio_risk = 'medium'
            
            # Generate recommendations
            recommendations = []
            if portfolio_leverage > self.risk_params['max_portfolio_leverage']:
                recommendations.append(f"Portfolio leverage ({portfolio_leverage:.1f}x) exceeds recommended maximum ({self.risk_params['max_portfolio_leverage']}x)")
            
            if high_risk_positions:
                recommendations.append(f"High volatility positions with excessive leverage detected: {len(high_risk_positions)} positions")
            
            if weighted_volatility > 3.0:
                recommendations.append("High portfolio volatility - consider reducing overall leverage")
            
            if not recommendations:
                recommendations.append("Portfolio leverage within acceptable limits")
            
            return {
                'portfolio_leverage': round(portfolio_leverage, 2),
                'risk_level': portfolio_risk,
                'recommendations': recommendations,
                'total_exposure': round(total_notional_value, 2),
                'total_margin': round(total_margin_used, 2),
                'weighted_volatility': round(weighted_volatility, 2),
                'high_risk_positions': high_risk_positions,
                'position_count': len(positions)
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error monitoring portfolio leverage: {e}")
            return {
                'portfolio_leverage': 0.0,
                'risk_level': 'unknown',
                'recommendations': [f'Error in portfolio analysis: {e}'],
                'total_exposure': 0.0
            }
    
    async def _store_volatility_profile(self, profile: VolatilityProfile):
        """Store volatility profile in database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO volatility_profiles 
                    (symbol, atr_14, atr_percentage, price_volatility, volume_volatility,
                     hourly_volatility, daily_volatility, volatility_score, 
                     recommended_leverage, max_safe_leverage, risk_level, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    profile.symbol, profile.atr_14, profile.atr_percentage,
                    profile.price_volatility, profile.volume_volatility,
                    profile.hourly_volatility, profile.daily_volatility,
                    profile.volatility_score, profile.recommended_leverage,
                    profile.max_safe_leverage, profile.risk_level,
                    profile.last_updated
                ))
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error storing volatility profile: {e}")
    
    async def _store_leverage_adjustment(self, adjustment: LeverageAdjustment):
        """Store leverage adjustment in database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO leverage_adjustments 
                    (symbol, old_leverage, new_leverage, volatility_score, 
                     reason, position_size_impact, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    adjustment.symbol, adjustment.old_leverage, adjustment.new_leverage,
                    adjustment.volatility_score, adjustment.reason,
                    adjustment.position_size_impact, adjustment.timestamp
                ))
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error storing leverage adjustment: {e}")
    
    async def get_leverage_statistics(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get leverage management statistics"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Base query
                base_query = "SELECT * FROM leverage_adjustments"
                params = []
                
                if symbol:
                    base_query += " WHERE symbol = ?"
                    params.append(symbol)
                
                base_query += " ORDER BY timestamp DESC LIMIT 100"
                
                cursor.execute(base_query, params)
                adjustments = cursor.fetchall()
                
                if not adjustments:
                    return {'message': 'No leverage adjustments found'}
                
                # Calculate statistics
                total_adjustments = len(adjustments)
                increases = sum(1 for adj in adjustments if adj[3] > adj[2])  # new_leverage > old_leverage
                decreases = total_adjustments - increases
                
                recent_adjustments = [adj for adj in adjustments if 
                                    (datetime.now() - datetime.fromisoformat(adj[7])).days <= 7]
                
                return {
                    'total_adjustments': total_adjustments,
                    'leverage_increases': increases,
                    'leverage_decreases': decreases,
                    'recent_adjustments': len(recent_adjustments),
                    'adjustment_ratio': round(decreases / total_adjustments * 100, 1) if total_adjustments > 0 else 0,
                    'symbols_monitored': len(set(adj[1] for adj in adjustments)),
                    'last_adjustment': adjustments[0][7] if adjustments else None
                }
                
        except Exception as e:
            self.logger.error(f"Error getting leverage statistics: {e}")
            return {'error': str(e)}
    
    def update_leverage_config(self, new_config: Dict[str, Any]):
        """Update leverage configuration"""
        try:
            for key, value in new_config.items():
                if key in self.leverage_config:
                    old_value = self.leverage_config[key]
                    self.leverage_config[key] = value
                    self.logger.info(f"🔧 Updated leverage config: {key} {old_value} → {value}")
            
            self.logger.info("✅ Leverage configuration updated successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error updating leverage config: {e}")
    
    def _calculate_auto_leverage(self, volatility_profile, trade_size_usdt: float, trade_direction: str) -> int:
        """Calculate automatic leverage based on dynamic market conditions"""
        try:
            # Base auto leverage from volatility
            volatility_score = volatility_profile.volatility_score
            
            if volatility_score < 0.5:
                auto_leverage = 15  # Very stable market
            elif volatility_score < 1.0:
                auto_leverage = 12  # Stable market
            elif volatility_score < 2.0:
                auto_leverage = 8   # Moderate volatility
            elif volatility_score < 3.5:
                auto_leverage = 5   # High volatility
            else:
                auto_leverage = 3   # Extreme volatility
            
            # Adjust for trade size
            if trade_size_usdt > 500:
                auto_leverage = max(2, int(auto_leverage * 0.7))
            elif trade_size_usdt > 1000:
                auto_leverage = max(2, int(auto_leverage * 0.5))
            
            # Adjust for direction (shorts typically get lower leverage in volatile conditions)
            if trade_direction == 'SHORT' and volatility_score > 2.0:
                auto_leverage = max(2, int(auto_leverage * 0.8))
            
            # Ensure within bounds
            return max(self.leverage_config['min_leverage'], 
                      min(auto_leverage, self.leverage_config['max_leverage']))
            
        except Exception as e:
            self.logger.error(f"Error calculating auto leverage: {e}")
            return self.leverage_config['default_leverage']
    
    def _calculate_maintenance_margin_ratio(self, leverage: int) -> float:
        """Calculate maintenance margin ratio based on leverage"""
        try:
            # Higher leverage = higher maintenance margin ratio
            if leverage >= 20:
                return 0.10  # 10%
            elif leverage >= 15:
                return 0.075  # 7.5%
            elif leverage >= 10:
                return 0.05   # 5%
            elif leverage >= 5:
                return 0.025  # 2.5%
            else:
                return 0.01   # 1%
                
        except Exception:
            return 0.05  # Default 5%

    def get_current_config(self) -> Dict[str, Any]:
        """Get current leverage configuration"""
        return {
            'leverage_config': self.leverage_config.copy(),
            'volatility_thresholds': self.volatility_thresholds.copy(),
            'leverage_mapping': self.leverage_mapping.copy(),
            'risk_params': self.risk_params.copy()
        }