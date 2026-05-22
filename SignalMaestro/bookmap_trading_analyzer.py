#!/usr/bin/env python3
"""
Bookmap Trading Analyzer
Advanced order flow analysis using Binance order book (DOM)
Analyzes liquidity heatmaps, volume profiles, and institutional activity
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio

class LiquidityLevel(Enum):
    EXTREME_CLUSTER = "EXTREME_CLUSTER"
    MAJOR_SUPPORT = "MAJOR_SUPPORT"
    MINOR_SUPPORT = "MINOR_SUPPORT"
    NEUTRAL_ZONE = "NEUTRAL_ZONE"
    MINOR_RESISTANCE = "MINOR_RESISTANCE"
    MAJOR_RESISTANCE = "MAJOR_RESISTANCE"
    EXTREME_RESISTANCE = "EXTREME_RESISTANCE"

class OrderFlowDirection(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"

@dataclass
class BookmapSignal:
    """Bookmap trading signal"""
    timestamp: str
    price_level: float
    liquidity_level: LiquidityLevel
    order_flow_direction: OrderFlowDirection
    aggressive_buy_ratio: float
    aggressive_sell_ratio: float
    volume_imbalance: float
    heatmap_intensity: float
    institutional_activity: float
    dom_structure_signal: str
    confidence: float
    strength: float

class BookmapTradingAnalyzer:
    """Advanced order flow analysis using Bookmap methodology"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.dom_cache = {}
        self.price_levels_cache = {}
        self.liquidity_clusters = []
    
    async def analyze_order_book(self, symbol: str, depth: Dict[str, Any]) -> BookmapSignal:
        """Analyze order book using Bookmap methodology"""
        try:
            if not depth or 'bids' not in depth or 'asks' not in depth:
                return self._create_neutral_signal()
            
            bids = np.array(depth.get('bids', [])[:20], dtype=float)
            asks = np.array(depth.get('asks', [])[:20], dtype=float)
            
            if len(bids) == 0 or len(asks) == 0:
                return self._create_neutral_signal()
            
            # Extract prices and volumes
            bid_prices = bids[:, 0]
            bid_volumes = bids[:, 1]
            ask_prices = asks[:, 0]
            ask_volumes = asks[:, 1]
            
            # Calculate DOM metrics
            spread = float(ask_prices[0] - bid_prices[0])
            mid_price = float((bid_prices[0] + ask_prices[0]) / 2)
            
            # Volume analysis
            total_bid_volume = float(np.sum(bid_volumes))
            total_ask_volume = float(np.sum(ask_volumes))
            volume_ratio = total_bid_volume / (total_ask_volume + 0.001)
            
            # Aggressive order detection (level 1)
            aggressive_buy = bid_volumes[0]
            aggressive_sell = ask_volumes[0]
            aggressive_ratio = aggressive_buy / (aggressive_sell + 0.001)
            
            # Liquidity clustering
            liquidity_levels = self._detect_liquidity_clusters(bid_prices, bid_volumes, ask_prices, ask_volumes, mid_price)
            
            # DOM structure signal
            dom_signal = self._analyze_dom_structure(bid_volumes, ask_volumes, bid_prices, ask_prices)
            
            # Order flow imbalance
            imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume + 0.001)
            
            # Heatmap intensity (volume concentration)
            top_3_bid = float(np.sum(bid_volumes[:3]))
            top_3_ask = float(np.sum(ask_volumes[:3]))
            heatmap = (top_3_bid + top_3_ask) / (total_bid_volume + total_ask_volume + 0.001)
            
            # Institutional activity detection
            institutional = self._detect_institutional_activity(bid_volumes, ask_volumes, bid_prices, ask_prices, mid_price)
            
            # Direction and strength
            direction = self._determine_order_flow_direction(volume_ratio, imbalance, dom_signal)
            confidence = min(abs(imbalance) + heatmap * 0.5, 1.0)
            strength = min(abs(volume_ratio - 1.0) * 50 + institutional * 30, 100.0)
            
            # Current liquidity level
            current_level = self._get_liquidity_level_for_price(mid_price, liquidity_levels)
            
            return BookmapSignal(
                timestamp=pd.Timestamp.now().isoformat(),
                price_level=mid_price,
                liquidity_level=current_level,
                order_flow_direction=direction,
                aggressive_buy_ratio=float(aggressive_buy / (aggressive_buy + aggressive_sell + 0.001)),
                aggressive_sell_ratio=float(aggressive_sell / (aggressive_buy + aggressive_sell + 0.001)),
                volume_imbalance=float(imbalance),
                heatmap_intensity=float(heatmap),
                institutional_activity=float(institutional),
                dom_structure_signal=dom_signal,
                confidence=float(confidence),
                strength=float(strength)
            )
        except Exception as e:
            self.logger.debug(f"Order book analysis error: {e}")
            return self._create_neutral_signal()
    
    async def analyze_volume_profile(self, ohlcv_data: List) -> Dict[str, Any]:
        """Analyze volume profile for price levels"""
        try:
            if not ohlcv_data or len(ohlcv_data) == 0:
                return {'error': 'No data'}
            
            # Convert to DataFrame
            if isinstance(ohlcv_data[0], (list, tuple)):
                col_count = len(ohlcv_data[0])
                if col_count == 6:
                    df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df = df.drop('timestamp', axis=1)
                else:
                    df = pd.DataFrame(ohlcv_data, columns=['open', 'high', 'low', 'close', 'volume'])
            else:
                df = ohlcv_data
            
            if 'volume' not in df.columns or 'close' not in df.columns:
                return {'error': 'Invalid data'}
            
            # Calculate volume-weighted price levels
            vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()
            
            # High volume levels
            df['high_volume'] = df['volume'] > df['volume'].quantile(0.75)
            high_vol_prices = df[df['high_volume']]['close'].values
            
            # Volume clusters
            clusters = self._identify_volume_clusters(df)
            
            return {
                'vwap': float(vwap),
                'high_volume_prices': [float(p) for p in high_vol_prices[-10:]],
                'volume_clusters': clusters,
                'avg_volume': float(df['volume'].mean()),
                'volume_trend': 'INCREASING' if df['volume'].iloc[-1] > df['volume'].mean() else 'NORMAL'
            }
        except Exception as e:
            self.logger.debug(f"Volume profile error: {e}")
            return {'error': str(e)}
    
    async def detect_institutional_orders(self, order_book: Dict, price_history: List) -> Dict[str, Any]:
        """Detect institutional block orders and accumulation"""
        try:
            bids = np.array(order_book.get('bids', [])[:30], dtype=float)
            asks = np.array(order_book.get('asks', [])[:30], dtype=float)
            
            if len(bids) == 0 or len(asks) == 0:
                return {'institutional_signal': 'NEUTRAL', 'confidence': 0}
            
            bid_volumes = bids[:, 1]
            ask_volumes = asks[:, 1]
            
            # Large orders detection
            large_bid_threshold = np.percentile(bid_volumes, 90)
            large_ask_threshold = np.percentile(ask_volumes, 90)
            
            large_bids = np.sum(bid_volumes[bid_volumes > large_bid_threshold])
            large_asks = np.sum(ask_volumes[ask_volumes > large_ask_threshold])
            
            # Accumulation pattern
            acc_ratio = large_bids / (large_asks + 0.001)
            
            if acc_ratio > 1.5:
                signal = 'ACCUMULATION_BUY'
                conf = min(acc_ratio / 3, 1.0)
            elif acc_ratio < 0.67:
                signal = 'DISTRIBUTION_SELL'
                conf = min((1 / acc_ratio) / 3, 1.0)
            else:
                signal = 'NEUTRAL'
                conf = 0.5
            
            return {
                'institutional_signal': signal,
                'accumulation_ratio': float(acc_ratio),
                'large_buy_volume': float(large_bids),
                'large_sell_volume': float(large_asks),
                'confidence': float(conf)
            }
        except Exception as e:
            self.logger.debug(f"Institutional detection error: {e}")
            return {'institutional_signal': 'NEUTRAL', 'confidence': 0}
    
    def _detect_liquidity_clusters(self, bid_prices, bid_volumes, ask_prices, ask_volumes, mid_price):
        """Detect liquidity concentration zones"""
        clusters = []
        
        # Find major volume zones
        bid_strength = np.sum(bid_volumes[:3]) / (np.sum(bid_volumes) + 0.001)
        ask_strength = np.sum(ask_volumes[:3]) / (np.sum(ask_volumes) + 0.001)
        
        if bid_strength > 0.6:
            clusters.append({'zone': 'BID', 'level': float(bid_prices[0]), 'strength': bid_strength})
        if ask_strength > 0.6:
            clusters.append({'zone': 'ASK', 'level': float(ask_prices[0]), 'strength': ask_strength})
        
        return clusters
    
    def _analyze_dom_structure(self, bid_vols, ask_vols, bid_prices, ask_prices):
        """Analyze depth of market structure"""
        bid_profile = bid_vols / (np.sum(bid_vols) + 0.001)
        ask_profile = ask_vols / (np.sum(ask_vols) + 0.001)
        
        bid_concentration = bid_profile[0]
        ask_concentration = ask_profile[0]
        
        if bid_concentration > ask_concentration + 0.15:
            return "BUY_PRESSURE"
        elif ask_concentration > bid_concentration + 0.15:
            return "SELL_PRESSURE"
        else:
            return "BALANCED"
    
    def _detect_institutional_activity(self, bid_vols, ask_vols, bid_prices, ask_prices, mid_price):
        """Score institutional order presence"""
        # Large orders at extremes
        large_bid = np.max(bid_vols) / (np.mean(bid_vols) + 0.001)
        large_ask = np.max(ask_vols) / (np.mean(ask_vols) + 0.001)
        
        activity = (large_bid + large_ask) / 4  # Normalize to 0-1
        return min(activity, 1.0)
    
    def _determine_order_flow_direction(self, volume_ratio, imbalance, dom_signal):
        """Determine overall order flow direction"""
        score = (volume_ratio - 1.0) * 0.5 + imbalance * 0.5
        
        if score > 0.3:
            return OrderFlowDirection.STRONG_BUY if score > 0.6 else OrderFlowDirection.BUY
        elif score < -0.3:
            return OrderFlowDirection.STRONG_SELL if score < -0.6 else OrderFlowDirection.SELL
        else:
            return OrderFlowDirection.NEUTRAL
    
    def _get_liquidity_level_for_price(self, price, clusters):
        """Determine liquidity level for current price"""
        if not clusters:
            return LiquidityLevel.NEUTRAL_ZONE
        
        cluster_nearby = [c for c in clusters if abs(c['level'] - price) / price < 0.01]
        if cluster_nearby:
            return LiquidityLevel.MAJOR_SUPPORT if any(c['zone'] == 'BID' for c in cluster_nearby) else LiquidityLevel.MAJOR_RESISTANCE
        
        return LiquidityLevel.NEUTRAL_ZONE
    
    def _identify_volume_clusters(self, df):
        """Identify volume concentration clusters"""
        clusters = []
        vol_mean = df['volume'].mean()
        vol_std = df['volume'].std()
        
        high_vol_periods = df[df['volume'] > vol_mean + vol_std]
        if len(high_vol_periods) > 0:
            for idx, row in high_vol_periods.iterrows():
                clusters.append({
                    'price': float(row['close']),
                    'volume': float(row['volume']),
                    'strength': float(row['volume'] / (vol_mean + vol_std))
                })
        
        return clusters[:5]  # Top 5 clusters
    
    def _create_neutral_signal(self) -> BookmapSignal:
        """Create neutral/default signal"""
        return BookmapSignal(
            timestamp=pd.Timestamp.now().isoformat(),
            price_level=0.0,
            liquidity_level=LiquidityLevel.NEUTRAL_ZONE,
            order_flow_direction=OrderFlowDirection.NEUTRAL,
            aggressive_buy_ratio=0.5,
            aggressive_sell_ratio=0.5,
            volume_imbalance=0.0,
            heatmap_intensity=0.0,
            institutional_activity=0.0,
            dom_structure_signal="NEUTRAL",
            confidence=0.0,
            strength=0.0
        )

# Global instance
bookmap_analyzer = BookmapTradingAnalyzer()
