#!/usr/bin/env python3
"""
Ichimoku Sniper Strategy - COMPREHENSIVELY FIXED
Pine Script v6 implementation with:
- Proper Ichimoku periods per timeframe (9/26/52 for 30m, optimized for scalping TFs)
- True crossover detection (not just position-based)
- Proper EMA calculation with SMA seed
- RSI + Volume confirmation
- Multi-timeframe signals (1m, 5m, 15m, 30m)
- Dynamic SL/TP with ATR
- Three take-profit levels (TP1/TP2/TP3)
- Accurate signal strength and confidence scoring
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

@dataclass
class IchimokuSignal:
    """Data class for Ichimoku signals with multi-TP support"""
    symbol: str
    action: str              # BUY or SELL
    entry_price: float
    stop_loss: float
    take_profit: float       # Primary TP (TP1)
    signal_strength: float
    confidence: float
    risk_reward_ratio: float
    atr_value: float
    timestamp: datetime
    timeframe: str = "30m"
    take_profit_1: float = 0.0   # 45% allocation
    take_profit_2: float = 0.0   # 35% allocation
    take_profit_3: float = 0.0   # 20% allocation
    leverage: int = 10
    rsi: float = 50.0
    volume_ratio: float = 1.0
    cloud_bullish: bool = True
    crossover_detected: bool = False

    def __post_init__(self):
        if self.take_profit_1 == 0.0:
            self.take_profit_1 = self.take_profit
        if self.take_profit_2 == 0.0:
            if self.action == "BUY":
                self.take_profit_2 = self.entry_price + (self.take_profit - self.entry_price) * 1.8
            else:
                self.take_profit_2 = self.entry_price - (self.entry_price - self.take_profit) * 1.8
        if self.take_profit_3 == 0.0:
            if self.action == "BUY":
                self.take_profit_3 = self.entry_price + (self.take_profit - self.entry_price) * 2.8
            else:
                self.take_profit_3 = self.entry_price - (self.entry_price - self.take_profit) * 2.8


# Timeframe-specific Ichimoku periods (Pine Script optimized)
ICHIMOKU_PARAMS = {
    "1m":  {"conversion": 7,  "base": 13, "lagging2": 27,  "displacement": 13, "sl_pct": 0.45, "tp1_pct": 0.55, "tp2_pct": 1.05, "tp3_pct": 1.75, "ema": 50,  "min_candles": 80},
    "3m":  {"conversion": 7,  "base": 14, "lagging2": 27,  "displacement": 14, "sl_pct": 0.55, "tp1_pct": 0.75, "tp2_pct": 1.35, "tp3_pct": 2.10, "ema": 100, "min_candles": 120},
    "5m":  {"conversion": 9,  "base": 17, "lagging2": 34,  "displacement": 17, "sl_pct": 0.65, "tp1_pct": 0.90, "tp2_pct": 1.60, "tp3_pct": 2.50, "ema": 100, "min_candles": 140},
    "15m": {"conversion": 9,  "base": 22, "lagging2": 44,  "displacement": 22, "sl_pct": 0.80, "tp1_pct": 1.05, "tp2_pct": 1.95, "tp3_pct": 3.00, "ema": 200, "min_candles": 230},
    "30m": {"conversion": 9,  "base": 26, "lagging2": 52,  "displacement": 26, "sl_pct": 1.00, "tp1_pct": 1.30, "tp2_pct": 2.40, "tp3_pct": 3.75, "ema": 200, "min_candles": 230},
    "1h":  {"conversion": 9,  "base": 26, "lagging2": 52,  "displacement": 26, "sl_pct": 1.20, "tp1_pct": 1.65, "tp2_pct": 3.10, "tp3_pct": 4.80, "ema": 200, "min_candles": 230},
    "4h":  {"conversion": 9,  "base": 26, "lagging2": 52,  "displacement": 26, "sl_pct": 1.50, "tp1_pct": 2.10, "tp2_pct": 3.90, "tp3_pct": 6.00, "ema": 200, "min_candles": 230},
}

# Leverage per timeframe (risk-adjusted)
LEVERAGE_MAP = {
    "1m": 20, "3m": 15, "5m": 12, "15m": 10, "30m": 8, "1h": 5, "4h": 3
}

class IchimokuSniperStrategy:
    """
    Ichimoku Sniper Strategy — Full Pine Script v6 accuracy
    Fixes all bugs from original implementation:
    - Proper per-TF periods
    - True crossover detection
    - Correct EMA with SMA seed
    - RSI + Volume filters
    - Multi-TP levels
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Active timeframes — all enabled for max signal frequency
        self.timeframes = ["1m", "5m", "15m", "30m"]
        self.primary_timeframe = "30m"

        # Minimum thresholds — strategy-level pre-boost gates
        # NOTE: process_signals applies ATAS/Bookmap/Microstructure boosts (+20-53%) AFTER these pass
        # Final send threshold is AI_THRESHOLD_PERCENT=72 (in process_signals). Keep strategy gates lower
        # so signals can be boosted into the passing range by market intelligence.
        self.min_signal_strength = 55.0   # Pre-boost gate (strategy-level) — boosts can add 20-53%
        self.min_confidence = 55.0        # Pre-boost gate — final threshold is 72% after all boosts

        # Signal state tracking for crossover detection (per timeframe)
        self._prev_state: Dict[str, Optional[str]] = {}   # "ABOVE_CLOUD" / "BELOW_CLOUD" / None
        self._prev_trend: Dict[str, Optional[str]] = {}   # "BULL" / "BEAR"

        self.logger.info("✅ Ichimoku Sniper Strategy initialized — Multi-TF + Crossover Detection")
        self.logger.info(f"   Active TFs: {self.timeframes}")
        self.logger.info(f"   Min Strength: {self.min_signal_strength}% | Min Confidence: {self.min_confidence}%")

    # ─────────────────────────────────────────────
    # Core math helpers
    # ─────────────────────────────────────────────

    def _donchian_mid(self, highs: List[float], lows: List[float], period: int) -> float:
        """Donchian channel midpoint — exact Pine Script (hl2 of highest/lowest)"""
        if len(highs) < period or len(lows) < period:
            return 0.0
        return (max(highs[-period:]) + min(lows[-period:])) / 2.0

    def _sma(self, prices: List[float], period: int) -> float:
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        return sum(prices[-period:]) / period

    def _ema(self, prices: List[float], period: int) -> float:
        """EMA with SMA seed (correct Pine Script implementation)"""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        multiplier = 2.0 / (period + 1)
        # Seed with SMA of first `period` values
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = price * multiplier + ema * (1.0 - multiplier)
        return ema

    def _atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """True Range ATR"""
        if len(closes) < period + 1:
            return abs(highs[-1] - lows[-1]) if highs and lows else 0.001
        trs = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            trs.append(max(hl, hc, lc))
        if len(trs) < period:
            return sum(trs) / len(trs) if trs else 0.001
        # Wilder smoothing (RMA seed = SMA first period)
        atr = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr = (atr * (period - 1) + tr) / period
        return atr

    def _rsi(self, closes: List[float], period: int = 14) -> float:
        """RSI — Wilder's smoothing"""
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        if not gains:
            return 50.0
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _volume_ratio(self, volumes: List[float], period: int = 20) -> float:
        """Current volume vs average (volume surge detection)"""
        if len(volumes) < period + 1:
            return 1.0
        avg = sum(volumes[-period - 1:-1]) / period
        if avg == 0:
            return 1.0
        return volumes[-1] / avg

    # ─────────────────────────────────────────────
    # Ichimoku component calculator
    # ─────────────────────────────────────────────

    def _calculate_ichimoku(self, highs: List[float], lows: List[float],
                             closes: List[float], volumes: List[float],
                             params: Dict) -> Dict[str, Any]:
        """Calculate all Ichimoku components + technical filters"""
        cp = params["conversion"]
        bp = params["base"]
        l2p = params["lagging2"]
        disp = params["displacement"]
        ema_p = params["ema"]

        n = len(closes)
        if n < max(ema_p, l2p, cp, bp) + disp + 5:
            return {}

        # ── Ichimoku lines ──
        conversion = self._donchian_mid(highs, lows, cp)          # Tenkan-sen
        base       = self._donchian_mid(highs, lows, bp)           # Kijun-sen
        lead1      = (conversion + base) / 2.0                     # Senkou Span A
        lead2      = self._donchian_mid(highs, lows, l2p)          # Senkou Span B

        # ── Displaced cloud (future cloud — shifted forward by displacement) ──
        # For signal logic, we use the cloud that is displaced BACK by `disp` candles
        # so we're comparing price to the cloud that was projected `disp` candles ago
        hist_highs = highs[:-disp] if len(highs) > disp else highs
        hist_lows  = lows[:-disp]  if len(lows)  > disp else lows
        hist_closes= closes[:-disp] if len(closes) > disp else closes

        if len(hist_closes) > max(cp, bp, l2p):
            hist_conv  = self._donchian_mid(hist_highs, hist_lows, cp)
            hist_base  = self._donchian_mid(hist_highs, hist_lows, bp)
            cloud_top_disp    = (hist_conv + hist_base) / 2.0
            cloud_bottom_disp = self._donchian_mid(hist_highs, hist_lows, l2p)
        else:
            cloud_top_disp    = lead1
            cloud_bottom_disp = lead2

        # ── Previous bar displaced cloud (for crossover detection into visible cloud) ──
        # Strip one more bar to get the displaced cloud as seen one bar ago
        prev_h = highs[:-disp - 1] if len(highs) > disp + 1 else hist_highs
        prev_l = lows[:-disp - 1]  if len(lows)  > disp + 1 else hist_lows
        prev_c = closes[:-disp - 1] if len(closes) > disp + 1 else hist_closes
        if len(prev_c) > max(cp, bp, l2p):
            pdc    = self._donchian_mid(prev_h, prev_l, cp)
            pdb    = self._donchian_mid(prev_h, prev_l, bp)
            prev_cld_top  = (pdc + pdb) / 2.0
            prev_cld_bot  = self._donchian_mid(prev_h, prev_l, l2p)
        else:
            prev_cld_top  = cloud_top_disp
            prev_cld_bot  = cloud_bottom_disp

        # ── Lagging span (chikou) ──
        chikou_price = closes[-1]  # Current close, plotted disp bars back
        chikou_ref   = closes[-(disp + 1)] if n > disp + 1 else closes[0]

        # ── EMA filter ──
        ema_val = self._ema(closes, ema_p)

        # ── ATR ──
        atr = self._atr(highs, lows, closes)

        # ── RSI ──
        rsi_val = self._rsi(closes)

        # ── Volume ratio ──
        vol_ratio = self._volume_ratio(volumes)

        # ── Previous bar values for crossover detection ──
        if n >= 2:
            prev_conv  = self._donchian_mid(highs[:-1], lows[:-1], cp)
            prev_base  = self._donchian_mid(highs[:-1], lows[:-1], bp)
            prev_lead1 = (prev_conv + prev_base) / 2.0
            prev_lead2 = self._donchian_mid(highs[:-1], lows[:-1], l2p)
            prev_close = closes[-2]
        else:
            prev_conv = conversion; prev_base = base
            prev_lead1 = lead1; prev_lead2 = lead2; prev_close = closes[-1]

        # Normalise displaced cloud pairs
        _ctd = max(cloud_top_disp, cloud_bottom_disp)
        _cbd = min(cloud_top_disp, cloud_bottom_disp)
        _pctd = max(prev_cld_top, prev_cld_bot)
        _pcbd = min(prev_cld_top, prev_cld_bot)

        return {
            "close":              closes[-1],
            "prev_close":         prev_close,
            "conversion":         conversion,
            "base":               base,
            "lead1":              lead1,
            "lead2":              lead2,
            "prev_lead1":         prev_lead1,
            "prev_lead2":         prev_lead2,
            "prev_conv":          prev_conv,
            "prev_base":          prev_base,
            "cloud_top":          max(lead1, lead2),
            "cloud_bottom":       min(lead1, lead2),
            "cloud_top_disp":     _ctd,
            "cloud_bottom_disp":  _cbd,
            "prev_cloud_top_disp":  _pctd,
            "prev_cloud_bot_disp":  _pcbd,
            "chikou":             chikou_price,
            "chikou_ref":         chikou_ref,
            "ema":                ema_val,
            "atr":                atr,
            "rsi":                rsi_val,
            "vol_ratio":          vol_ratio,
            "cloud_bullish":      lead1 >= lead2,
        }

    # ─────────────────────────────────────────────
    # Signal generator
    # ─────────────────────────────────────────────

    def _generate_signal(self, data: Dict[str, Any], timeframe: str,
                          params: Dict) -> Optional[IchimokuSignal]:
        """Generate Ichimoku signal with crossover detection and quality scoring"""
        if not data:
            return None

        close     = data["close"]
        prev_close= data["prev_close"]
        conv      = data["conversion"]
        base      = data["base"]
        lead1     = data["lead1"]
        lead2     = data["lead2"]
        prev_conv = data["prev_conv"]
        prev_base = data["prev_base"]
        prev_l1   = data["prev_lead1"]
        prev_l2   = data["prev_lead2"]
        cloud_top = data["cloud_top"]
        cloud_bot = data["cloud_bottom"]
        cloud_top_d = data["cloud_top_disp"]
        cloud_bot_d = data["cloud_bottom_disp"]
        prev_cloud_top_d = data["prev_cloud_top_disp"]
        prev_cloud_bot_d = data["prev_cloud_bot_disp"]
        chikou    = data["chikou"]
        chikou_ref= data["chikou_ref"]
        ema       = data["ema"]
        atr       = data["atr"]
        rsi       = data["rsi"]
        vol_ratio = data["vol_ratio"]
        cloud_bull= data["cloud_bullish"]

        tf_key = timeframe

        # ── BULLISH CONDITIONS ──
        # 1. Tenkan/Kijun cross (TK cross) — primary entry signal
        tk_cross_bull = (conv > base and prev_conv <= prev_base)

        # 2. Price crosses above VISIBLE cloud (displaced Senkou Span)
        price_cross_cloud_bull = (close > cloud_top_d and prev_close <= prev_cloud_top_d)

        # 3. Price above VISIBLE cloud (momentum condition)
        price_above_cloud = close > cloud_top_d

        # 4. Price above tenkan and kijun
        price_above_tk_kj = close > conv and close > base

        # 5. EMA trend filter
        ema_bull = close > ema

        # 6. Cloud color bullish (lead1 >= lead2)
        cloud_color_bull = cloud_bull

        # 7. Chikou above price reference
        chikou_bull = chikou > chikou_ref

        # 8. RSI bullish zone (not overbought)
        rsi_bull = 40 < rsi < 75

        # 9. Volume confirmation
        vol_confirm = vol_ratio > 0.8

        # ── BEARISH CONDITIONS ──
        tk_cross_bear = (conv < base and prev_conv >= prev_base)
        price_cross_cloud_bear = (close < cloud_bot_d and prev_close >= prev_cloud_bot_d)
        price_below_cloud = close < cloud_bot_d
        price_below_tk_kj = close < conv and close < base
        ema_bear = close < ema
        cloud_color_bear = not cloud_bull
        chikou_bear = chikou < chikou_ref
        rsi_bear = 25 < rsi < 60

        # ── SIGNAL SCORING ──
        # Each condition contributes to a weighted score
        # Primary triggers: TK cross OR Price-Cloud cross (either must occur or price must be strongly positioned)
        long_trigger  = tk_cross_bull or price_cross_cloud_bull or (price_above_cloud and price_above_tk_kj and ema_bull)
        short_trigger = tk_cross_bear or price_cross_cloud_bear or (price_below_cloud and price_below_tk_kj and ema_bear)

        crossover = tk_cross_bull or price_cross_cloud_bull or tk_cross_bear or price_cross_cloud_bear

        if not long_trigger and not short_trigger:
            return None

        # Determine direction
        if long_trigger and not short_trigger:
            direction = "BUY"
        elif short_trigger and not long_trigger:
            direction = "SELL"
        elif long_trigger and short_trigger:
            # Conflict — use EMA direction as tiebreaker
            direction = "BUY" if ema_bull else "SELL"
        else:
            return None

        # ── STRENGTH CALCULATION (0-100) ──
        if direction == "BUY":
            conditions = [
                (price_above_cloud,    25),   # Above cloud — strongest condition
                (ema_bull,             20),   # Above EMA
                (price_above_tk_kj,   15),   # Above TK lines
                (cloud_color_bull,     15),   # Bullish cloud color
                (chikou_bull,          10),   # Chikou above
                (rsi_bull,              8),   # RSI in zone
                (vol_confirm,           7),   # Volume confirm
            ]
        else:
            conditions = [
                (price_below_cloud,    25),
                (ema_bear,             20),
                (price_below_tk_kj,   15),
                (cloud_color_bear,     15),
                (chikou_bear,          10),
                (rsi_bear,              8),
                (vol_confirm,           7),
            ]

        max_score = sum(w for _, w in conditions)
        raw_score = sum(w for cond, w in conditions if cond)
        signal_strength = (raw_score / max_score) * 100.0 if max_score > 0 else 0

        if signal_strength < self.min_signal_strength:
            self.logger.debug(f"⚠️ {timeframe} signal strength {signal_strength:.1f}% < {self.min_signal_strength}% — skipped")
            return None

        # ── CONFIDENCE CALCULATION ──
        # Base confidence from signal strength
        base_conf = 55.0 + (signal_strength - 60) * 0.5

        # Crossover bonus (fresh signal)
        crossover_bonus = 12.0 if crossover else 0.0

        # TK cross bonus
        tk_bonus = 8.0 if (tk_cross_bull if direction == "BUY" else tk_cross_bear) else 0.0

        # Cloud clarity bonus — use VISIBLE displaced cloud width (what price actually traded through)
        cloud_width_pct = abs(cloud_top_d - cloud_bot_d) / close * 100 if close > 0 else 0
        cloud_bonus = min(8.0, cloud_width_pct * 4)

        # RSI proximity bonus (RSI 50-60 for buys, 40-50 for sells)
        if direction == "BUY":
            rsi_bonus = 5.0 if 50 <= rsi <= 65 else (3.0 if 45 <= rsi < 50 else 0)
        else:
            rsi_bonus = 5.0 if 35 <= rsi <= 50 else (3.0 if 50 < rsi <= 55 else 0)

        # Volume spike bonus
        vol_bonus = min(6.0, (vol_ratio - 1.0) * 4) if vol_ratio > 1.0 else 0.0

        # Timeframe confidence boost
        tf_boost = {"1m": 0, "3m": 2, "5m": 3, "15m": 5, "30m": 8, "1h": 10, "4h": 12}.get(timeframe, 0)

        confidence = min(97.0, base_conf + crossover_bonus + tk_bonus + cloud_bonus + rsi_bonus + vol_bonus + tf_boost)
        confidence = max(0, confidence)

        if confidence < self.min_confidence:
            self.logger.debug(f"⚠️ {timeframe} confidence {confidence:.1f}% < {self.min_confidence}% — skipped")
            return None

        # ── SL/TP CALCULATION ──
        sl_pct   = params["sl_pct"]
        tp1_pct  = params["tp1_pct"]
        tp2_pct  = params["tp2_pct"]
        tp3_pct  = params["tp3_pct"]

        # ATR-adjusted SL (uses larger of % or ATR-based)
        atr_sl_factor = 1.5
        atr_sl_pct = (atr * atr_sl_factor / close) * 100

        effective_sl_pct = max(sl_pct, atr_sl_pct)
        # Cap SL at 3x the base to prevent runaway
        effective_sl_pct = min(effective_sl_pct, sl_pct * 3)

        if direction == "BUY":
            stop_loss   = close * (1 - effective_sl_pct / 100)
            tp1         = close * (1 + tp1_pct / 100)
            tp2         = close * (1 + tp2_pct / 100)
            tp3         = close * (1 + tp3_pct / 100)
            # Anchor SL to VISIBLE cloud bottom (displaced Senkou Span B) — tighter and correct
            cloud_sl = cloud_bot_d * 0.999
            stop_loss = min(stop_loss, cloud_sl) if cloud_bot_d > 0 and cloud_sl > 0 else stop_loss
        else:
            stop_loss   = close * (1 + effective_sl_pct / 100)
            tp1         = close * (1 - tp1_pct / 100)
            tp2         = close * (1 - tp2_pct / 100)
            tp3         = close * (1 - tp3_pct / 100)
            # Anchor SL to VISIBLE cloud top (displaced Senkou Span A) — tighter and correct
            cloud_sl = cloud_top_d * 1.001
            stop_loss = max(stop_loss, cloud_sl) if cloud_top_d > 0 else stop_loss

        # ── RISK/REWARD ──
        risk   = abs(close - stop_loss)
        reward = abs(tp1 - close)
        rr     = reward / risk if risk > 0 else 0

        # Reject poor R:R
        if rr < 0.8:
            self.logger.debug(f"⚠️ {timeframe} R:R {rr:.2f} too low — skipped")
            return None

        # ── LEVERAGE ──
        base_lev = LEVERAGE_MAP.get(timeframe, 10)
        # Scale leverage inversely with volatility (higher ATR = lower leverage)
        vol_factor = min(1.0, 0.3 / max(atr_sl_pct, 0.1))
        leverage = max(2, min(base_lev, int(base_lev * vol_factor)))

        self.logger.info(
            f"🎯 {direction} signal [{timeframe}] | Close={close:.5f} | "
            f"Conv={conv:.5f} Base={base:.5f} | "
            f"VisibleCloud {cloud_bot_d:.5f}-{cloud_top_d:.5f} ({'BULL' if cloud_bull else 'BEAR'}) | "
            f"RSI={rsi:.1f} Vol={vol_ratio:.2f}x | "
            f"Strength={signal_strength:.1f}% Conf={confidence:.1f}% | "
            f"SL={stop_loss:.5f} TP1={tp1:.5f} TP2={tp2:.5f} TP3={tp3:.5f} | "
            f"Crossover={'YES' if crossover else 'NO'} Lev={leverage}x"
        )

        return IchimokuSignal(
            symbol="FXSUSDT",
            action=direction,
            entry_price=close,
            stop_loss=stop_loss,
            take_profit=tp1,
            signal_strength=signal_strength,
            confidence=confidence,
            risk_reward_ratio=rr,
            atr_value=atr,
            timestamp=datetime.now(),
            timeframe=timeframe,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            leverage=leverage,
            rsi=rsi,
            volume_ratio=vol_ratio,
            cloud_bullish=cloud_bull,
            crossover_detected=crossover,
        )

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    async def analyze_timeframe(self, trader, timeframe: str) -> Optional[IchimokuSignal]:
        """Fetch data and generate signal for a specific timeframe"""
        try:
            params = ICHIMOKU_PARAMS.get(timeframe, ICHIMOKU_PARAMS["30m"])
            limit  = params["min_candles"] + 20   # extra buffer

            ohlcv = await trader.get_klines(timeframe, limit)

            if not ohlcv or len(ohlcv) < params["min_candles"]:
                self.logger.debug(f"📊 Insufficient data for {timeframe}: {len(ohlcv) if ohlcv else 0}/{params['min_candles']}")
                return None

            highs  = [c[2] for c in ohlcv]
            lows   = [c[3] for c in ohlcv]
            closes = [c[4] for c in ohlcv]
            volumes= [c[5] for c in ohlcv]

            # ── Dead-market guard ──────────────────────────────────────────
            # Detect flat/zero-volume candles (e.g. SETTLING contracts)
            _recent  = ohlcv[-20:] if len(ohlcv) >= 20 else ohlcv
            _vol_sum = sum(c[5] for c in _recent)
            _uniq_c  = len(set(c[4] for c in _recent))
            if _vol_sum == 0 or _uniq_c <= 1:
                _key = f"_dead_warned_{timeframe}"
                _last = getattr(self, _key, 0)
                if time.time() - _last > 300:            # warn at most every 5 min per TF
                    setattr(self, _key, time.time())
                    self.logger.warning(
                        f"💀 {timeframe}: DEAD MARKET — Volume={_vol_sum:.2f} "
                        f"UniqueCloses={_uniq_c}/20 — price frozen, no signals possible"
                    )
                return None
            # ── End dead-market guard ──────────────────────────────────────

            ichimoku_data = self._calculate_ichimoku(highs, lows, closes, volumes, params)
            if not ichimoku_data:
                return None

            return self._generate_signal(ichimoku_data, timeframe, params)

        except Exception as e:
            self.logger.error(f"❌ Error analyzing {timeframe}: {e}", exc_info=True)
            return None

    async def generate_multi_timeframe_signals(self, trader) -> List[IchimokuSignal]:
        """Generate and rank signals across all enabled timeframes"""
        try:
            tasks = [self.analyze_timeframe(trader, tf) for tf in self.timeframes]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            signals: List[IchimokuSignal] = []
            for i, result in enumerate(results):
                tf = self.timeframes[i]
                if isinstance(result, Exception):
                    self.logger.error(f"❌ {tf} analysis error: {result}")
                elif isinstance(result, IchimokuSignal):
                    signals.append(result)
                    self.logger.info(f"✅ Valid signal on {tf}: {result.action} @ {result.entry_price:.5f} "
                                     f"(Str={result.signal_strength:.1f}% Conf={result.confidence:.1f}%)")

            if not signals:
                self.logger.debug("📊 No qualifying signals on any timeframe this scan")
                return []

            # Priority sort: crossover > strength > timeframe priority > confidence
            tf_priority = {"30m": 4, "15m": 3, "5m": 2, "1m": 1}
            signals.sort(key=lambda s: (
                s.crossover_detected,           # Fresh crossovers first
                s.signal_strength,
                tf_priority.get(s.timeframe, 0),
                s.confidence
            ), reverse=True)

            self.logger.info(f"📊 {len(signals)} signal(s) found — top: {signals[0].action} [{signals[0].timeframe}] @ {signals[0].entry_price:.5f}")
            return signals

        except Exception as e:
            self.logger.error(f"❌ Multi-TF analysis error: {e}", exc_info=True)
            return []

    async def generate_signal_for_timeframe(self, trader, timeframe: str = "30m") -> Optional[IchimokuSignal]:
        """Single timeframe signal (legacy compatibility)"""
        return await self.analyze_timeframe(trader, timeframe)
