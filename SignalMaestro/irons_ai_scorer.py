#!/usr/bin/env python3
"""
IRONS AI Scorer — Comprehensive multi-indicator signal intelligence.
Computes 0-100 signal quality score with full indicator breakdown panels.

Indicators:
  Momentum (9):   RSI, Stochastic, Williams %R, CCI, MFI, ROC, Awesome Osc, TSI, Ultimate Osc
  Trend    (6):   MACD, EMA, ADX, Ichimoku, SuperTrend, Aroon
  Volatility (5): Bollinger, Keltner Ch, ATR, Fibonacci, Pivot
  Volume   (5):   Volume ratio, VWAP, OBV, CMF, A/D Line
"""

from __future__ import annotations
import math
import logging
from typing import List, Dict, Tuple, Optional, Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python indicator helpers (self-contained, no external deps)
# ─────────────────────────────────────────────────────────────────────────────

def _ema_s(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
    return ema

def _ema_series_s(data: List[float], period: int) -> Optional[List[float]]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period
    out = [ema]
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out

def _true_atr_s(closes: List[float], highs: List[float], lows: List[float],
                period: int = 14) -> Optional[float]:
    n = min(len(closes), len(highs), len(lows))
    if n < period + 1:
        if n < 2:
            return None
        trs = [abs(closes[i] - closes[i-1]) for i in range(1, n)]
        return sum(trs) / len(trs) if trs else None
    trs = []
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def _bollinger_s(closes: List[float], period: int = 20):
    if len(closes) < period:
        return None, None, None
    w = closes[-period:]
    mid = sum(w) / period
    sd = (sum((x - mid)**2 for x in w) / period) ** 0.5
    return mid + 2*sd, mid, mid - 2*sd

def _pivot_s(highs: List[float], lows: List[float], closes: List[float]):
    if len(closes) < 22:
        return None
    h = max(highs[-21:-1])
    l = min(lows[-21:-1])
    c = closes[-2]
    p = (h + l + c) / 3.0
    return {"P": p, "R1": 2*p-l, "R2": p+(h-l), "S1": 2*p-h, "S2": p-(h-l)}

def _adx_s(closes: List[float], highs: List[float], lows: List[float], period: int = 14):
    n = min(len(closes), len(highs), len(lows))
    if n < period * 2 + 1:
        return None
    c, h, l = closes[-n:], highs[-n:], lows[-n:]
    pdm, mdm, trs = [], [], []
    for i in range(1, len(c)):
        up = h[i] - h[i-1];  dn = l[i-1] - l[i]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    def _ws(d, p):
        sm = sum(d[:p])
        out = [sm]
        for v in d[p:]:
            sm = sm - sm/p + v
            out.append(sm)
        return out
    at = _ws(trs, period); pd = _ws(pdm, period); md = _ws(mdm, period)
    if not at:
        return None
    dx_vals = []
    for i in range(len(at)):
        if at[i] == 0:
            continue
        pi = 100 * pd[i] / at[i]; mi = 100 * md[i] / at[i]
        denom = pi + mi
        if denom > 0:
            dx_vals.append(abs(pi - mi) / denom * 100)
    if not dx_vals:
        return None
    adx = sum(dx_vals[:period]) / min(period, len(dx_vals))
    for dv in dx_vals[period:]:
        adx = (adx * (period - 1) + dv) / period
    return adx

def _st_dir_s(closes: List[float], highs: List[float], lows: List[float],
              period: int = 10, mult: float = 3.0) -> Optional[int]:
    n = min(len(closes), len(highs), len(lows))
    if n < period + 3:
        return None
    c, h, l = closes[-n:], highs[-n:], lows[-n:]
    atr_vs = []
    for i in range(1, n):
        atr_vs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    if len(atr_vs) < period + 1:
        return None
    atr_sm = sum(atr_vs[:period]) / period
    direction = 1 if c[period] > (h[period]+l[period])/2 - mult*atr_sm else -1
    fu = (h[period]+l[period])/2 + mult*atr_sm
    fl = (h[period]+l[period])/2 - mult*atr_sm
    for i in range(period, n-1):
        atr_sm = (atr_sm*(period-1) + atr_vs[i-1])/period
        hl2 = (h[i]+l[i])/2
        bu = hl2 + mult*atr_sm; bl = hl2 - mult*atr_sm
        nu = min(bu, fu) if c[i] < fu else bu
        nl = max(bl, fl) if c[i] > fl else bl
        if direction == 1 and c[i] < nl:
            direction = -1
        elif direction == -1 and c[i] > nu:
            direction = 1
        fu, fl = nu, nl
    return direction

def _cci_s(closes: List[float], highs: List[float], lows: List[float], period: int = 20):
    n = min(len(closes), len(highs), len(lows))
    if n < period:
        return None
    c, h, l = closes[-period:], highs[-period:], lows[-period:]
    tp = [(h[i]+l[i]+c[i])/3 for i in range(period)]
    ma = sum(tp)/period
    mad = sum(abs(t-ma) for t in tp)/period
    return (tp[-1]-ma)/(0.015*mad) if mad != 0 else 0.0

def _mfi_s(closes: List[float], highs: List[float], lows: List[float],
           volumes: List[float], period: int = 14):
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < period + 1:
        return None
    c, h, l, v = closes[-n:], highs[-n:], lows[-n:], volumes[-n:]
    pos = neg = 0.0
    for i in range(1, period + 1):
        tp_c = (h[i]+l[i]+c[i])/3; tp_p = (h[i-1]+l[i-1]+c[i-1])/3
        mf = tp_c * v[i]
        if tp_c > tp_p:   pos += mf
        elif tp_c < tp_p: neg += mf
    if neg == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + pos/neg))

def _awesome_osc_s(closes: List[float], highs: List[float], lows: List[float],
                    fast: int = 5, slow: int = 34):
    n = min(len(closes), len(highs), len(lows))
    if n < slow:
        return None
    mids = [(highs[i]+lows[i])/2 for i in range(n)]
    return sum(mids[-fast:])/fast - sum(mids[-slow:])/slow

def _tsi_s(closes: List[float], long_p: int = 25, short_p: int = 13):
    if len(closes) < long_p + short_p + 2:
        return None
    mom = [closes[i]-closes[i-1] for i in range(1, len(closes))]
    abm = [abs(m) for m in mom]
    e1m = _ema_series_s(mom, long_p)
    e1a = _ema_series_s(abm, long_p)
    if not e1m or not e1a:
        return None
    e2m = _ema_series_s(e1m, short_p)
    e2a = _ema_series_s(e1a, short_p)
    if not e2m or not e2a or e2a[-1] == 0:
        return None
    return (e2m[-1] / e2a[-1]) * 100.0

def _aroon_s(highs: List[float], lows: List[float], period: int = 25):
    n = min(len(highs), len(lows))
    if n < period + 1:
        return None
    h = highs[-(period+1):]; l = lows[-(period+1):]
    hi_idx = max(range(period+1), key=lambda i: h[i])
    lo_idx = min(range(period+1), key=lambda i: l[i])
    bsh = period - hi_idx; bsl = period - lo_idx
    return ((period-bsh)/period*100, (period-bsl)/period*100)

def _ad_line_s(closes: List[float], highs: List[float], lows: List[float],
               volumes: List[float]):
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < 5:
        return None
    c, h, l, v = closes[-n:], highs[-n:], lows[-n:], volumes[-n:]
    ad = 0.0; vals = []
    for i in range(n):
        r = h[i]-l[i]
        clv = ((c[i]-l[i])-(h[i]-c[i]))/r if r > 0 else 0.0
        ad += clv * v[i]; vals.append(ad)
    return vals[-1] - vals[-5] if len(vals) >= 5 else 0.0

def _vwap_s(closes: List[float], highs: List[float], lows: List[float],
            volumes: List[float], period: int = 20):
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < period:
        return None
    c, h, l, v = closes[-period:], highs[-period:], lows[-period:], volumes[-period:]
    tpv = sum((h[i]+l[i]+c[i])/3*v[i] for i in range(period))
    vs = sum(v)
    return tpv/vs if vs > 0 else None

def _ultimate_osc_s(closes: List[float], highs: List[float], lows: List[float]):
    n = min(len(closes), len(highs), len(lows))
    if n < 29:
        return None
    c, h, l = closes[-n:], highs[-n:], lows[-n:]
    def _bp_tr(i):
        pc = c[i-1]
        return c[i]-min(l[i],pc), max(h[i],pc)-min(l[i],pc)
    def _ps(period, idx):
        bs = ts = 0.0
        for j in range(idx-period+1, idx+1):
            if j < 1: continue
            b, t = _bp_tr(j); bs += b; ts += t
        return bs, ts
    idx = n-1
    b7, t7   = _ps(7, idx)
    b14, t14 = _ps(14, idx)
    b28, t28 = _ps(28, idx)
    if t7 == 0 or t14 == 0 or t28 == 0:
        return None
    return ((b7/t7)*4 + (b14/t14)*2 + b28/t28) / 7.0 * 100.0

def _roc_s(closes: List[float], period: int = 12):
    if len(closes) < period + 1:
        return None
    prev = closes[-(period+1)]
    return (closes[-1]-prev)/prev*100 if prev != 0 else None

def _fib_prox_s(closes: List[float], highs: List[float], lows: List[float], lb: int = 50):
    n = min(len(closes), len(highs), len(lows))
    lb = min(lb, n)
    if lb < 10:
        return None
    hmax = max(highs[-lb:]); lmin = min(lows[-lb:])
    rng = hmax - lmin
    if rng == 0:
        return None
    cur = closes[-1]
    levels = {"0%": lmin, "23.6%": lmin+0.236*rng, "38.2%": lmin+0.382*rng,
              "50%": lmin+0.5*rng, "61.8%": lmin+0.618*rng, "78.6%": lmin+0.786*rng, "100%": hmax}
    best_name = "50%"; best_d = float('inf')
    for nm, lv in levels.items():
        d = abs(cur-lv)
        if d < best_d:
            best_d = d; best_name = nm
    prox = best_d/cur*100 if cur > 0 else 99
    return prox, best_name

def _detect_patterns(closes: List[float], highs: List[float], lows: List[float],
                     lb: int = 50) -> List[Tuple[str, str]]:
    """Detect chart patterns. Returns list of (name, direction)."""
    out = []
    n = min(len(closes), len(highs), len(lows), lb)
    if n < 15:
        return out
    c, h, l = closes[-n:], highs[-n:], lows[-n:]
    m = len(c)
    # swing points (3-bar)
    sh = [(i, h[i]) for i in range(2, m-2)
          if h[i] >= h[i-1] and h[i] >= h[i+1] and h[i] >= h[i-2] and h[i] >= h[i+2]]
    sl = [(i, l[i]) for i in range(2, m-2)
          if l[i] <= l[i-1] and l[i] <= l[i+1] and l[i] <= l[i-2] and l[i] <= l[i+2]]
    # Double Top
    if len(sh) >= 2:
        h1, h2 = sh[-2][1], sh[-1][1]
        if sh[-1][0] > sh[-2][0]+3 and abs(h1-h2)/max(h1,h2) < 0.025:
            out.append(("Double Top", "bear"))
    # Double Bottom
    if len(sl) >= 2:
        l1, l2 = sl[-2][1], sl[-1][1]
        if sl[-1][0] > sl[-2][0]+3 and abs(l1-l2)/max(l1,l2,1e-9) < 0.025:
            out.append(("Double Bottom", "bull"))
    # Head & Shoulders
    if len(sh) >= 3:
        lft, hd, rgt = sh[-3][1], sh[-2][1], sh[-1][1]
        if hd > lft and hd > rgt and abs(lft-rgt)/hd < 0.04:
            out.append(("H&S Top", "bear"))
    # Inverse H&S
    if len(sl) >= 3:
        lft, hd, rgt = sl[-3][1], sl[-2][1], sl[-1][1]
        if hd < lft and hd < rgt and abs(lft-rgt)/max(lft,1e-9) < 0.05:
            out.append(("Inv H&S", "bull"))
    # Ascending Triangle
    if len(sh) >= 2 and len(sl) >= 2:
        if abs(sh[-1][1]-sh[-2][1])/max(sh[-1][1],1e-9) < 0.015 and sl[-1][1] > sl[-2][1]:
            out.append(("Ascending Triangle", "bull"))
    # Descending Triangle
    if len(sh) >= 2 and len(sl) >= 2:
        if abs(sl[-1][1]-sl[-2][1])/max(sl[-1][1],1e-9) < 0.015 and sh[-1][1] < sh[-2][1]:
            out.append(("Descending Triangle", "bear"))
    return out

# ─────────────────────────────────────────────────────────────────────────────
# IRONS AI Scorer
# ─────────────────────────────────────────────────────────────────────────────

class IRONSScorer:
    """
    Computes a comprehensive 0-100 signal score with full indicator breakdown.
    Weights: Momentum 25%, Trend 30%, Volatility 20%, Volume 25%.
    """

    @staticmethod
    def _ind(score: int, note: str) -> Tuple[int, str]:
        return (max(0, min(100, score)), note)

    @classmethod
    def score(
        cls,
        closes:   List[float],
        highs:    List[float],
        lows:     List[float],
        volumes:  List[float],
        action:   str,
        atr:      float,
        rsi:      float,
        macd_line: Optional[float],
        macd_sig:  Optional[float],
        swarm_consensus: float,
        confidence: float,
        vol_ratio: float,
        regime: str,
        htf_1h: str = "NEUTRAL",
        htf_4h: str = "NEUTRAL",
    ) -> Dict[str, Any]:
        """
        Returns dict:
          score         int 0-100
          risk_label    str
          categories    dict {momentum, trend, volatility, volume} → avg score
          indicators    dict name → (score, note)
          patterns      list of (name, direction)
          mtf           dict {4H, 1H, 15M}
          squeeze_on    bool
        """
        n = len(closes)
        cur = closes[-1] if n > 0 else 1.0
        is_long = action == "BUY"
        ind: Dict[str, Tuple[int, str]] = {}

        # ── MOMENTUM ──────────────────────────────────────────────────────────

        # RSI
        if is_long:
            if rsi < 30:   rs, rn = 90, f"RSI {rsi:.1f} oversold — bullish zone"
            elif rsi < 45: rs, rn = 72, f"RSI {rsi:.1f} low — growth potential"
            elif rsi < 60: rs, rn = 55, f"RSI {rsi:.1f} neutral"
            elif rsi < 70: rs, rn = 35, f"RSI {rsi:.1f} elevated"
            else:          rs, rn = 15, f"RSI {rsi:.1f} overbought — risky LONG"
        else:
            if rsi > 70:   rs, rn = 90, f"RSI {rsi:.1f} overbought — bearish zone"
            elif rsi > 55: rs, rn = 72, f"RSI {rsi:.1f} elevated — bearish pressure"
            elif rsi > 40: rs, rn = 55, f"RSI {rsi:.1f} neutral"
            elif rsi > 30: rs, rn = 35, f"RSI {rsi:.1f} low"
            else:          rs, rn = 15, f"RSI {rsi:.1f} oversold — risky SHORT"
        ind["RSI(14)"] = cls._ind(rs, rn)

        # Stochastic (uses actual H/L)
        stoch_score = 50; stoch_note = "Stoch —"
        if n >= 14 and len(highs) >= 14 and len(lows) >= 14:
            hh = max(highs[-14:]); ll = min(lows[-14:])
            if hh != ll:
                k = (cur - ll) / (hh - ll) * 100
                stoch_note = f"Stoch K={k:.1f}"
                if is_long:
                    if k < 20:   stoch_score = 88
                    elif k < 40: stoch_score = 68
                    elif k < 60: stoch_score = 50
                    elif k < 80: stoch_score = 32
                    else:        stoch_score = 15
                else:
                    if k > 80:   stoch_score = 88
                    elif k > 60: stoch_score = 68
                    elif k > 40: stoch_score = 50
                    elif k > 20: stoch_score = 32
                    else:        stoch_score = 15
        ind["Stochastic"] = cls._ind(stoch_score, stoch_note)

        # Williams %R (with H/L)
        wr_score = 50; wr_note = "%R —"
        if n >= 14 and len(highs) >= 14 and len(lows) >= 14:
            hh = max(highs[-14:]); ll = min(lows[-14:])
            if hh != ll:
                wr = (hh - cur) / (hh - ll) * -100
                wr_note = f"%R={wr:.1f}"
                if is_long:
                    if wr < -80:   wr_score, wr_note = 88, f"%R={wr:.1f} oversold"
                    elif wr < -50: wr_score, wr_note = 65, f"%R={wr:.1f} low"
                    elif wr < -20: wr_score, wr_note = 45, f"%R={wr:.1f} neutral"
                    else:          wr_score, wr_note = 18, f"%R={wr:.1f} overbought"
                else:
                    if wr > -20:   wr_score, wr_note = 88, f"%R={wr:.1f} overbought"
                    elif wr > -50: wr_score, wr_note = 65, f"%R={wr:.1f} high"
                    elif wr > -80: wr_score, wr_note = 45, f"%R={wr:.1f} neutral"
                    else:          wr_score, wr_note = 18, f"%R={wr:.1f} oversold"
        ind["Williams %R"] = cls._ind(wr_score, wr_note)

        # CCI(20)
        cci_val = _cci_s(closes, highs, lows, 20)
        if cci_val is not None:
            if is_long:
                if cci_val < -100:  cs, cn = 82, f"CCI={cci_val:.1f} oversold"
                elif cci_val < 0:   cs, cn = 62, f"CCI={cci_val:.1f} below zero"
                elif cci_val < 100: cs, cn = 45, f"CCI={cci_val:.1f} neutral"
                else:               cs, cn = 18, f"CCI={cci_val:.1f} overbought"
            else:
                if cci_val > 100:   cs, cn = 82, f"CCI={cci_val:.1f} overbought"
                elif cci_val > 0:   cs, cn = 62, f"CCI={cci_val:.1f} above zero"
                elif cci_val > -100:cs, cn = 45, f"CCI={cci_val:.1f} neutral"
                else:               cs, cn = 18, f"CCI={cci_val:.1f} oversold"
        else:
            cs, cn = 50, "CCI — insufficient data"
        ind["CCI(20)"] = cls._ind(cs, cn)

        # MFI(14)
        mfi_val = _mfi_s(closes, highs, lows, volumes, 14)
        if mfi_val is not None:
            if is_long:
                if mfi_val < 20:   ms, mn = 85, f"MFI={mfi_val:.1f} low — growth potential"
                elif mfi_val < 40: ms, mn = 70, f"MFI={mfi_val:.1f} healthy inflow"
                elif mfi_val < 60: ms, mn = 52, f"MFI={mfi_val:.1f} neutral"
                elif mfi_val < 80: ms, mn = 35, f"MFI={mfi_val:.1f} elevated"
                else:              ms, mn = 15, f"MFI={mfi_val:.1f} overbought"
            else:
                if mfi_val > 80:   ms, mn = 85, f"MFI={mfi_val:.1f} overbought — bearish"
                elif mfi_val > 60: ms, mn = 70, f"MFI={mfi_val:.1f} high — outflow likely"
                elif mfi_val > 40: ms, mn = 52, f"MFI={mfi_val:.1f} neutral"
                elif mfi_val > 20: ms, mn = 35, f"MFI={mfi_val:.1f} low"
                else:              ms, mn = 15, f"MFI={mfi_val:.1f} oversold — risky SHORT"
        else:
            ms, mn = 50, "MFI — insufficient data"
        ind["MFI(14)"] = cls._ind(ms, mn)

        # ROC(12)
        roc_val = _roc_s(closes, 12)
        if roc_val is not None:
            if is_long:
                if roc_val > 5:    ros, ron = 90, f"ROC={roc_val:.2f}% strong momentum"
                elif roc_val > 1:  ros, ron = 78, f"ROC={roc_val:.2f}% positive"
                elif roc_val > 0:  ros, ron = 58, f"ROC={roc_val:.2f}% mild positive"
                elif roc_val > -2: ros, ron = 35, f"ROC={roc_val:.2f}% mild negative"
                else:              ros, ron = 18, f"ROC={roc_val:.2f}% negative"
            else:
                if roc_val < -5:   ros, ron = 90, f"ROC={roc_val:.2f}% strong bearish"
                elif roc_val < -1: ros, ron = 78, f"ROC={roc_val:.2f}% bearish"
                elif roc_val < 0:  ros, ron = 58, f"ROC={roc_val:.2f}% mild bearish"
                elif roc_val < 2:  ros, ron = 35, f"ROC={roc_val:.2f}% mild bullish"
                else:              ros, ron = 18, f"ROC={roc_val:.2f}% positive vs SHORT"
        else:
            ros, ron = 50, "ROC — insufficient data"
        ind["ROC(12)"] = cls._ind(ros, ron)

        # Awesome Oscillator
        ao_val = _awesome_osc_s(closes, highs, lows)
        if ao_val is not None:
            pos = ao_val > 0
            if is_long:
                aos, aon = (80, f"AO={ao_val:.5g} positive — bullish") if pos else (28, f"AO={ao_val:.5g} negative")
            else:
                aos, aon = (80, f"AO={ao_val:.5g} negative — bearish") if not pos else (28, f"AO={ao_val:.5g} positive vs SHORT")
        else:
            aos, aon = 50, "AO — insufficient data"
        ind["Awesome Osc"] = cls._ind(aos, aon)

        # TSI
        tsi_val = _tsi_s(closes)
        if tsi_val is not None:
            if is_long:
                if tsi_val > 25:    ts2, tn = 82, f"TSI={tsi_val:.1f} strong bullish"
                elif tsi_val > 0:   ts2, tn = 65, f"TSI={tsi_val:.1f} positive"
                elif tsi_val > -25: ts2, tn = 38, f"TSI={tsi_val:.1f} weak"
                else:               ts2, tn = 18, f"TSI={tsi_val:.1f} bearish"
            else:
                if tsi_val < -25:   ts2, tn = 82, f"TSI={tsi_val:.1f} strong bearish"
                elif tsi_val < 0:   ts2, tn = 65, f"TSI={tsi_val:.1f} negative"
                elif tsi_val < 25:  ts2, tn = 38, f"TSI={tsi_val:.1f} weak"
                else:               ts2, tn = 18, f"TSI={tsi_val:.1f} bullish vs SHORT"
        else:
            ts2, tn = 50, "TSI — insufficient data"
        ind["TSI"] = cls._ind(ts2, tn)

        # Ultimate Oscillator
        uo_val = _ultimate_osc_s(closes, highs, lows)
        if uo_val is not None:
            if is_long:
                if uo_val < 30:   uos, uon = 82, f"UO={uo_val:.1f} oversold"
                elif uo_val < 50: uos, uon = 62, f"UO={uo_val:.1f} below midline"
                elif uo_val < 70: uos, uon = 42, f"UO={uo_val:.1f} above midline"
                else:             uos, uon = 22, f"UO={uo_val:.1f} overbought"
            else:
                if uo_val > 70:   uos, uon = 82, f"UO={uo_val:.1f} overbought"
                elif uo_val > 50: uos, uon = 62, f"UO={uo_val:.1f} above midline"
                elif uo_val > 30: uos, uon = 42, f"UO={uo_val:.1f} below midline"
                else:             uos, uon = 22, f"UO={uo_val:.1f} oversold vs SHORT"
        else:
            uos, uon = 50, "UO — insufficient data"
        ind["Ultimate Osc"] = cls._ind(uos, uon)

        # ── TREND ─────────────────────────────────────────────────────────────

        # MACD
        # v8.1 BUG FIX: the old "weakening" conditions `hist > -abs(hist)*0.3` and
        # `hist < abs(hist)*0.3` are always False for opposite-sign hist values
        # (simplifies to `1 < 0.3` after dividing by hist), making the 42-pt
        # "weakening" tier completely unreachable.  Fixed to use the signal line
        # magnitude as the reference (hist slightly adverse relative to macd_sig).
        if macd_line is not None and macd_sig is not None:
            hist = macd_line - macd_sig
            _sig_ref = abs(macd_sig) if macd_sig else abs(macd_line) or 1e-9
            if is_long:
                if hist > 0 and macd_line > 0:   mads, madn = 88, f"MACD hist={hist:.5g} bullish crossover"
                elif hist > 0:                    mads, madn = 72, f"MACD hist={hist:.5g} bullish momentum"
                elif hist > -_sig_ref * 0.5:      mads, madn = 42, f"MACD hist={hist:.5g} weakening"
                else:                             mads, madn = 18, f"MACD hist={hist:.5g} bearish"
            else:
                if hist < 0 and macd_line < 0:   mads, madn = 88, f"MACD hist={hist:.5g} bearish crossover"
                elif hist < 0:                    mads, madn = 72, f"MACD hist={hist:.5g} bearish momentum"
                elif hist < _sig_ref * 0.5:       mads, madn = 42, f"MACD hist={hist:.5g} weakening"
                else:                             mads, madn = 18, f"MACD hist={hist:.5g} bullish"
        else:
            mads, madn = 50, "MACD — insufficient data"
        ind["MACD(12,26,9)"] = cls._ind(mads, madn)

        # EMA alignment (9, 21, 200)
        ema9  = _ema_s(closes, 9)
        ema21 = _ema_s(closes, 21)
        ema200 = _ema_s(closes, 200) if n >= 200 else None
        if ema9 and ema21:
            bull = ema9 > ema21
            above_200 = (cur > ema200) if ema200 else None
            if above_200 is not None:
                if is_long:
                    if bull and above_200:         es, en = 92, f"EMA9>{ema9:.5g} > EMA21={ema21:.5g} | above EMA200"
                    elif bull:                     es, en = 68, f"EMA9>{ema9:.5g} > EMA21={ema21:.5g} | below EMA200"
                    elif above_200:                es, en = 42, f"EMA9 < EMA21 | above EMA200"
                    else:                          es, en = 18, f"EMA9 < EMA21 | below EMA200"
                else:
                    if not bull and not above_200: es, en = 92, f"EMA9 < EMA21 | below EMA200"
                    elif not bull:                 es, en = 68, f"EMA9 < EMA21 | above EMA200"
                    elif not above_200:            es, en = 42, f"EMA9 > EMA21 | below EMA200"
                    else:                          es, en = 18, f"EMA9 > EMA21 | above EMA200"
            else:
                if is_long:
                    es, en = (72, f"EMA9={ema9:.5g} > EMA21={ema21:.5g} bull stack") if bull else (28, f"EMA9 < EMA21 bearish")
                else:
                    es, en = (72, f"EMA9 < EMA21 bearish stack") if not bull else (28, f"EMA9 > EMA21 bullish")
        else:
            es, en = 50, "EMA — insufficient data"
        ind["EMA"] = cls._ind(es, en)

        # ADX(14)
        adx_val = _adx_s(closes, highs, lows, 14)
        if adx_val is not None:
            if adx_val > 40:    ads, adn = 82, f"ADX={adx_val:.1f} strong trend"
            elif adx_val > 25:  ads, adn = 65, f"ADX={adx_val:.1f} moderate trend"
            elif adx_val > 20:  ads, adn = 50, f"ADX={adx_val:.1f} developing"
            else:               ads, adn = 32, f"ADX={adx_val:.1f} weak (ranging)"
        else:
            ads, adn = 50, "ADX — insufficient data"
        ind["ADX(14)"] = cls._ind(ads, adn)

        # Ichimoku Cloud
        ich_score = 50; ich_note = "Ichimoku — checking"
        if n >= 52 and len(highs) >= 52:
            try:
                h52, l52 = highs[-52:], lows[-52:]
                ten = (max(h52[-9:]) + min(l52[-9:])) / 2
                kij = (max(h52[-26:]) + min(l52[-26:])) / 2
                sa  = (ten + kij) / 2
                sb  = (max(h52[-52:]) + min(l52[-52:])) / 2
                ct = max(sa, sb); cb = min(sa, sb)
                tk_bull = ten > kij
                above = cur > ct; below = cur < cb
                if is_long:
                    if above and tk_bull:        ich_score, ich_note = 92, "Price above cloud + bullish TK"
                    elif above:                  ich_score, ich_note = 68, "Price above cloud"
                    elif not below:              ich_score, ich_note = 40, "Price in cloud"
                    else:                        ich_score, ich_note = 15, "Price below cloud — bearish"
                else:
                    if below and not tk_bull:    ich_score, ich_note = 92, "Price below cloud + bearish TK"
                    elif below:                  ich_score, ich_note = 68, "Price below cloud"
                    elif not above:              ich_score, ich_note = 40, "Price in cloud"
                    else:                        ich_score, ich_note = 15, "Price above cloud — bullish"
            except Exception:
                pass
        ind["Ichimoku"] = cls._ind(ich_score, ich_note)

        # SuperTrend
        st_dir = _st_dir_s(closes, highs, lows)
        if st_dir is not None:
            aligned = (is_long and st_dir == 1) or (not is_long and st_dir == -1)
            if aligned: sts, stn = 82, f"SuperTrend {'bullish' if is_long else 'bearish'} — confirms signal"
            else:       sts, stn = 22, f"SuperTrend opposes {'LONG' if is_long else 'SHORT'}"
        else:
            sts, stn = 50, "SuperTrend — insufficient data"
        ind["SuperTrend"] = cls._ind(sts, stn)

        # Aroon(25)
        aroon = _aroon_s(highs, lows, 25)
        if aroon is not None:
            au, ad2 = aroon
            if is_long:
                if au > 80 and ad2 < 20:   ars, arn = 88, f"Aroon Up={au:.0f} Down={ad2:.0f} — strong bullish"
                elif au > ad2:             ars, arn = 65, f"Aroon Up={au:.0f} > Down={ad2:.0f}"
                elif au == ad2:            ars, arn = 50, f"Aroon balanced"
                else:                      ars, arn = 28, f"Aroon Up={au:.0f} < Down={ad2:.0f} bearish"
            else:
                if ad2 > 80 and au < 20:   ars, arn = 88, f"Aroon Down={ad2:.0f} Up={au:.0f} — strong bearish"
                elif ad2 > au:             ars, arn = 65, f"Aroon Down={ad2:.0f} > Up={au:.0f}"
                elif au == ad2:            ars, arn = 50, f"Aroon balanced"
                else:                      ars, arn = 28, f"Aroon Down < Up bullish"
        else:
            ars, arn = 50, "Aroon — insufficient data"
        ind["Aroon(25)"] = cls._ind(ars, arn)

        # ── VOLATILITY ────────────────────────────────────────────────────────

        # Bollinger Bands
        bb_score = 50; bb_note = "BB — insufficient data"
        if n >= 20:
            bbu, bbm, bbl = _bollinger_s(closes, 20)
            if bbu is not None and (bbu - bbl) > 0:
                pos = (cur - bbl) / (bbu - bbl)
                bb_note = f"Price pos={pos:.1%} in BB"
                if is_long:
                    if pos < 0.20:   bb_score = 82
                    elif pos < 0.40: bb_score = 65
                    elif pos < 0.60: bb_score = 50
                    elif pos < 0.80: bb_score = 32
                    else:            bb_score = 15
                else:
                    if pos > 0.80:   bb_score = 82
                    elif pos > 0.60: bb_score = 65
                    elif pos > 0.40: bb_score = 50
                    elif pos > 0.20: bb_score = 32
                    else:            bb_score = 15
                tag = " above upper BB" if cur > bbu else (" below lower BB" if cur < bbl else "")
                bb_note += tag
        ind["Bollinger"] = cls._ind(bb_score, bb_note)

        # Keltner Channel
        kc_score = 50; kc_note = "KC — insufficient data"
        if n >= 25 and len(highs) >= 25:
            kc_mid = _ema_s(closes, 20)
            atr10 = _true_atr_s(closes, highs, lows, 10) or atr
            if kc_mid and atr10 > 0:
                kcu = kc_mid + 2*atr10; kcl = kc_mid - 2*atr10
                if is_long:
                    if cur < kcl:   kc_score, kc_note = 78, "Price below lower KC — oversold"
                    elif cur < kc_mid: kc_score, kc_note = 62, "Price in lower KC half"
                    elif cur < kcu: kc_score, kc_note = 42, "Price in upper KC half"
                    else:           kc_score, kc_note = 22, "Price above upper KC"
                else:
                    if cur > kcu:   kc_score, kc_note = 78, "Price above upper KC — overbought"
                    elif cur > kc_mid: kc_score, kc_note = 62, "Price in upper KC half"
                    elif cur > kcl: kc_score, kc_note = 42, "Price in lower KC half"
                    else:           kc_score, kc_note = 22, "Price below lower KC"
        ind["Keltner Ch"] = cls._ind(kc_score, kc_note)

        # ATR quality
        if atr > 0 and cur > 0:
            atr_pct = atr / cur * 100
            if atr_pct < 0.5:    atrs, atrn = 80, f"ATR={atr_pct:.2f}% tight — good precision"
            elif atr_pct < 1.0:  atrs, atrn = 68, f"ATR={atr_pct:.2f}% normal"
            elif atr_pct < 2.0:  atrs, atrn = 52, f"ATR={atr_pct:.2f}% moderate"
            elif atr_pct < 3.0:  atrs, atrn = 35, f"ATR={atr_pct:.2f}% elevated volatility"
            else:                atrs, atrn = 18, f"ATR={atr_pct:.2f}% very high volatility"
        else:
            atrs, atrn = 50, "ATR — N/A"
        ind["ATR"] = cls._ind(atrs, atrn)

        # Fibonacci
        fib = _fib_prox_s(closes, highs, lows, 50)
        if fib is not None:
            prox, lvl = fib
            if prox < 0.5:    fibs, fibn = 92, f"Entry near Fib {lvl} ({prox:.2f}% away)"
            elif prox < 1.5:  fibs, fibn = 72, f"Near Fib {lvl} ({prox:.2f}%)"
            elif prox < 3.0:  fibs, fibn = 50, f"Fib {lvl} nearby ({prox:.2f}%)"
            else:             fibs, fibn = 32, f"Away from Fib levels ({prox:.2f}%)"
        else:
            fibs, fibn = 50, "Fibonacci — insufficient data"
        ind["Fibonacci"] = cls._ind(fibs, fibn)

        # Pivot
        piv = _pivot_s(highs, lows, closes)
        if piv:
            p, r1, s1 = piv["P"], piv["R1"], piv["S1"]
            if is_long:
                if cur < p:    pivs, pivn = 68, f"Price below Pivot={p:.5g} — bounce zone"
                elif cur < r1: pivs, pivn = 50, f"Between Pivot={p:.5g} and R1={r1:.5g}"
                else:          pivs, pivn = 30, f"Above R1={r1:.5g} — resistance"
            else:
                if cur > p:    pivs, pivn = 68, f"Price above Pivot={p:.5g} — reversal zone"
                elif cur > s1: pivs, pivn = 50, f"Between S1={s1:.5g} and Pivot={p:.5g}"
                else:          pivs, pivn = 30, f"Below S1={s1:.5g} — support"
        else:
            pivs, pivn = 50, "Pivot — insufficient data"
        ind["Pivot"] = cls._ind(pivs, pivn)

        # ── VOLUME ────────────────────────────────────────────────────────────

        # Volume ratio
        if vol_ratio > 2.5:   vols, voln = 90, f"Volume {vol_ratio:.1f}x — surge"
        elif vol_ratio > 1.5: vols, voln = 72, f"Volume {vol_ratio:.1f}x — above avg"
        elif vol_ratio > 1.0: vols, voln = 55, f"Volume {vol_ratio:.1f}x — average"
        elif vol_ratio > 0.7: vols, voln = 38, f"Volume {vol_ratio:.1f}x — low"
        else:                 vols, voln = 18, f"Volume {vol_ratio:.1f}x — very low"
        ind["Volume"] = cls._ind(vols, voln)

        # VWAP
        vwap = _vwap_s(closes, highs, lows, volumes, min(20, n))
        if vwap is not None:
            above_vwap = cur > vwap
            if is_long:
                vs2, vn2 = (80, f"Price above VWAP={vwap:.5g}") if above_vwap else (28, f"Price below VWAP={vwap:.5g}")
            else:
                vs2, vn2 = (80, f"Price below VWAP={vwap:.5g}") if not above_vwap else (28, f"Price above VWAP={vwap:.5g}")
        else:
            vs2, vn2 = 50, "VWAP — N/A"
        ind["VWAP"] = cls._ind(vs2, vn2)

        # OBV trend
        if n >= 10 and len(volumes) >= 10:
            obv = 0.0; obv_prev5 = 0.0
            for i in range(1, n):
                if closes[i] > closes[i-1]:    obv += volumes[i]
                elif closes[i] < closes[i-1]:  obv -= volumes[i]
                if i == n - 5:
                    obv_prev5 = obv
            rising = obv > obv_prev5
            if is_long:
                os2, on2 = (80, "OBV rising — buying pressure") if rising else (25, "OBV falling — selling pressure")
            else:
                os2, on2 = (80, "OBV falling — selling pressure") if not rising else (25, "OBV rising — buying pressure")
        else:
            os2, on2 = 50, "OBV — insufficient data"
        ind["OBV"] = cls._ind(os2, on2)

        # CMF(14)
        if n >= 15 and len(highs) >= 15:
            cmf_mfv = cmf_vs = 0.0
            for i in range(-14, 0):
                hl = highs[i] - lows[i]
                mfm = ((closes[i]-lows[i])-(highs[i]-closes[i]))/hl if hl > 0 else 0.0
                cmf_mfv += mfm * volumes[i]; cmf_vs += abs(volumes[i])
            cmf_val = cmf_mfv / cmf_vs if cmf_vs > 0 else 0.0
            if is_long:
                if cmf_val > 0.2:    cmfs, cmfn = 82, f"CMF={cmf_val:.3f} strong inflow"
                elif cmf_val > 0.05: cmfs, cmfn = 65, f"CMF={cmf_val:.3f} positive"
                elif cmf_val > -0.05:cmfs, cmfn = 50, f"CMF={cmf_val:.3f} neutral"
                else:                cmfs, cmfn = 28, f"CMF={cmf_val:.3f} outflow"
            else:
                if cmf_val < -0.2:   cmfs, cmfn = 82, f"CMF={cmf_val:.3f} strong outflow"
                elif cmf_val < -0.05:cmfs, cmfn = 65, f"CMF={cmf_val:.3f} negative"
                elif cmf_val < 0.05: cmfs, cmfn = 50, f"CMF={cmf_val:.3f} neutral"
                else:                cmfs, cmfn = 28, f"CMF={cmf_val:.3f} inflow vs SHORT"
        else:
            cmfs, cmfn = 50, "CMF — insufficient data"
        ind["CMF(14)"] = cls._ind(cmfs, cmfn)

        # A/D Line slope
        ad_slope = _ad_line_s(closes, highs, lows, volumes)
        if ad_slope is not None:
            if is_long:
                ads2, adn2 = (80, "A/D rising — accumulation") if ad_slope > 0 else (25, "A/D falling — distribution")
            else:
                ads2, adn2 = (80, "A/D falling — distribution") if ad_slope < 0 else (25, "A/D rising — accumulation vs SHORT")
        else:
            ads2, adn2 = 50, "A/D — insufficient data"
        ind["A/D Line"] = cls._ind(ads2, adn2)

        # ── SQUEEZE DETECTION ────────────────────────────────────────────────
        squeeze_on = False
        if n >= 25 and len(highs) >= 25:
            try:
                bbu2, _, bbl2 = _bollinger_s(closes, 20)
                kc_m = _ema_s(closes, 20)
                atr_kc = _true_atr_s(closes, highs, lows, 10) or atr
                if all(v is not None for v in [bbu2, bbl2, kc_m]) and atr_kc > 0:
                    kcu2 = kc_m + 1.5 * atr_kc; kcl2 = kc_m - 1.5 * atr_kc
                    squeeze_on = (bbu2 < kcu2) and (bbl2 > kcl2)
            except Exception:
                pass

        # ── COMPUTE FINAL SCORE ───────────────────────────────────────────────
        mom_keys = ["RSI(14)", "Stochastic", "Williams %R", "CCI(20)", "MFI(14)",
                    "ROC(12)", "Awesome Osc", "TSI", "Ultimate Osc"]
        trd_keys = ["MACD(12,26,9)", "EMA", "ADX(14)", "Ichimoku", "SuperTrend", "Aroon(25)"]
        vol_keys = ["Bollinger", "Keltner Ch", "ATR", "Fibonacci", "Pivot"]
        vum_keys = ["Volume", "VWAP", "OBV", "CMF(14)", "A/D Line"]

        mom_avg = sum(ind[k][0] for k in mom_keys) / len(mom_keys)
        trd_avg = sum(ind[k][0] for k in trd_keys) / len(trd_keys)
        vol_avg = sum(ind[k][0] for k in vol_keys) / len(vol_keys)
        vum_avg = sum(ind[k][0] for k in vum_keys) / len(vum_keys)

        # v11.1: trend weight raised 0.30→0.32, momentum lowered 0.25→0.23, volume raised 0.25→0.26,
        # volatility lowered 0.20→0.19.  Rationale: in trending crypto futures markets, trend
        # indicators (MACD, EMA, ADX, Ichimoku, SuperTrend, Aroon) are the strongest WR
        # discriminators; momentum oscillators fire frequently on pullbacks and add noise.
        # Volume flow (VWAP, OBV, CMF) is the second-best predictor for crypto directional moves.
        raw = mom_avg * 0.23 + trd_avg * 0.32 + vol_avg * 0.19 + vum_avg * 0.26
        # v8.1: 3-factor blend — raw technical indicators + swarm consensus + agent confidence
        # Rationale: unanimous swarm + high confidence are orthogonal quality signals.
        # swarm_pct cap raised 95→100 to distinguish 95% from 100% consensus.
        swarm_pct = min(swarm_consensus * 100, 100.0)
        conf_pct  = min(float(confidence or 0), 95.0)
        final = int(raw * 0.60 + swarm_pct * 0.25 + conf_pct * 0.15)
        final = max(10, min(97, final))

        # Risk label
        if final >= 75:   risk = "STRONG — high confidence"
        elif final >= 60: risk = "MODERATE — good confirmations"
        elif final >= 45: risk = "FAIR — limited confirmations"
        else:             risk = "RISKY — weak confirmations"

        # Patterns
        patterns = _detect_patterns(closes, highs, lows, 50)

        # MTF summary
        mtf = {"4H": htf_4h, "1H": htf_1h, "15M": action}

        return {
            "score": final,
            "risk_label": risk,
            "indicators": ind,
            "categories": {
                "momentum":   round(mom_avg),
                "trend":      round(trd_avg),
                "volatility": round(vol_avg),
                "volume":     round(vum_avg),
            },
            "squeeze_on": squeeze_on,
            "patterns": patterns,
            "mtf": mtf,
        }


def format_irons_panel(
    signal_symbol: str,
    signal_action: str,
    signal_leverage: int,
    signal_entry: float,
    signal_sl: float,
    signal_tp1: float,
    signal_tp2: float,
    signal_tp3: float,
    signal_tp4: float,
    signal_rr: float,
    signal_tf: str,
    signal_session: str,
    irons: Dict[str, Any],
    swarm_consensus: float,
    confidence: float,
    agent_votes: Dict[str, str],
    pm_line: str = "",
    ai_narrative: str = "",
) -> str:
    """
    Build the IRONS AI-style formatted Telegram message (Cornix-compatible).
    Stays under 4096 characters. Cornix parses the structured block; analytics
    are appended below as supplementary info for human traders.
    """
    direction = "LONG" if signal_action == "BUY" else "SHORT"
    d_emoji = "🟢" if signal_action == "BUY" else "🔴"

    def _fmt(p: float) -> str:
        if p >= 1000:    return f"{p:.2f}"
        elif p >= 10:    return f"{p:.4f}"
        elif p >= 0.1:   return f"{p:.5f}"
        elif p >= 0.01:  return f"{p:.6f}"
        else:            return f"{p:.8f}"

    def _pct(ref, val, buy):
        if ref <= 0: return 0.0
        return (val - ref) / ref * 100 if buy else (ref - val) / ref * 100

    is_buy = signal_action == "BUY"
    sl_pct  = _pct(signal_entry, signal_sl,  not is_buy)
    tp1_pct = _pct(signal_entry, signal_tp1, is_buy)
    tp2_pct = _pct(signal_entry, signal_tp2, is_buy)
    tp3_pct = _pct(signal_entry, signal_tp3, is_buy)
    tp4_pct = _pct(signal_entry, signal_tp4, is_buy)

    score      = irons.get("score", 50)
    risk_label = irons.get("risk_label", "")
    ind        = irons.get("indicators", {})
    cats       = irons.get("categories", {})
    patterns   = irons.get("patterns", [])
    mtf        = irons.get("mtf", {})
    squeeze    = irons.get("squeeze_on", False)

    # Score emoji
    if score >= 75:    score_emoji = "✅"
    elif score >= 55:  score_emoji = "⚠️"
    else:              score_emoji = "🔴"

    # Direction arrow (▲ LONG, ▼ SHORT)
    dir_arrow = "▲" if is_buy else "▼"

    # Indicator emoji helper
    def _ie(s: int) -> str:
        if s >= 65: return "✅"
        elif s >= 42: return "⚪"
        else: return "🔴"

    regime = "RANGING"
    if swarm_consensus >= 0.80: regime = "BULL" if is_buy else "BEAR"
    elif swarm_consensus >= 0.65: regime = "TRENDING"

    # ── Cornix-compatible block (strictly parsed by Cornix bot) ──
    tf_up = (signal_tf or "15m").upper()
    sym_tag = f"#{signal_symbol}"
    sess_short = signal_session[:2].upper() if signal_session else "XX"

    cornix_block = (
        f"{d_emoji} {sym_tag} {direction}\n"
        f"Exchange: Binance Futures\n"
        f"Leverage: Cross {signal_leverage}x\n"
        f"\n"
        f"Entry Targets:\n"
        f"1) {_fmt(signal_entry)}\n"
        f"\n"
        f"Take-Profit Targets:\n"
        f"1) {_fmt(signal_tp1)}\n"
        f"2) {_fmt(signal_tp2)}\n"
        f"3) {_fmt(signal_tp3)}\n"
        f"4) {_fmt(signal_tp4)}\n"
        f"\n"
        f"Stop Targets:\n"
        f"1) {_fmt(signal_sl)}\n"
    )

    # ── IRONS AI Score header ──
    score_block = (
        f"\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"🤖 IRONS AI | Score: {score}/100\n"
        f"{score_emoji} {risk_label}\n"
        f"🔎 {signal_symbol} {direction} {dir_arrow} | {signal_leverage}x | {regime}\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
    )

    # ── Price levels summary ──
    levels_block = (
        f"📍 Entry: {_fmt(signal_entry)} → 🛑 SL: {_fmt(signal_sl)} (-{sl_pct:.1f}%)\n"
        f"🎯 TP: +{tp1_pct:.1f}% · +{tp2_pct:.1f}% · +{tp3_pct:.1f}% · +{tp4_pct:.1f}%\n"
        f"⚖️ R:R 1:{signal_rr:.1f} | {tf_up} | {sess_short}\n"
    )

    # ── Indicator panel (compact) ──
    def _row(name: str) -> str:
        if name not in ind:
            return ""
        sc, note = ind[name]
        return f"{_ie(sc)} {sc}% {name} — {note}\n"

    panel_mom = (
        f"─ Momentum [{cats.get('momentum',50)}%]\n"
        + _row("RSI(14)")
        + _row("Stochastic")
        + _row("Williams %R")
        + _row("CCI(20)")
        + _row("MFI(14)")
        + _row("ROC(12)")
        + _row("Awesome Osc")
        + _row("TSI")
        + _row("Ultimate Osc")
    )

    panel_trend = (
        f"─ Trend [{cats.get('trend',50)}%]\n"
        + _row("MACD(12,26,9)")
        + _row("EMA")
        + _row("ADX(14)")
        + _row("Ichimoku")
        + _row("SuperTrend")
        + _row("Aroon(25)")
    )

    panel_vol = (
        f"─ Volatility [{cats.get('volatility',50)}%]\n"
        + _row("Bollinger")
        + _row("Keltner Ch")
        + _row("ATR")
        + _row("Fibonacci")
        + _row("Pivot")
    )

    panel_vum = (
        f"─ Volume [{cats.get('volume',50)}%]\n"
        + _row("Volume")
        + _row("VWAP")
        + _row("OBV")
        + _row("CMF(14)")
        + _row("A/D Line")
    )

    indicators_block = (
        f"┌─ Indicators [{score}/100] ───────\n"
        f"│ {panel_mom}"
        f"│ {panel_trend}"
        f"│ {panel_vol}"
        f"│ {panel_vum}"
        f"└─────────────────────────────\n"
    )

    # ── MTF block ──
    def _mtf_arrow(sig):
        if sig in ("BUY", "LONG"): return "⬆️ BULL"
        elif sig in ("SELL", "SHORT"): return "⬇️ BEAR"
        else: return "➡️ NEUTRAL"
    mtf_block = (
        f"📊 MTF: 4H {_mtf_arrow(mtf.get('4H','NEUTRAL'))} · "
        f"1H {_mtf_arrow(mtf.get('1H','NEUTRAL'))} · "
        f"15M {_mtf_arrow(mtf.get('15M', signal_action))}\n"
    )

    # ── Squeeze ──
    squeeze_line = "🔥 TTM Squeeze FIRING — breakout imminent\n" if squeeze else ""

    # ── Chart patterns ──
    pat_line = ""
    if patterns:
        pat_strs = []
        for name, direction_p in patterns[:3]:
            arrow = "📈" if direction_p == "bull" else "📉"
            pat_strs.append(f"{arrow} {name}")
        pat_line = "🔷 Patterns: " + " · ".join(pat_strs) + "\n"

    # ── Consensus traders panel (agent votes) ──
    short_names = {
        "TrendAgent": "Trend", "MomentumAgent": "Momentum", "VolumeAgent": "Volume",
        "VolatilityAgent": "Volatility", "OrderFlowAgent": "OrderFlow",
        "SentimentAgent": "Sentiment", "FundingFlowAgent": "FundingFlow",
        "PivotSRAgent": "PivotSR", "FLOOPAgent": "FLOOP", "AIOrchestrationAgent": "AI",
    }
    vote_sym = {"BUY": "✅", "SELL": "🔴", "NEUTRAL": "⚪"}
    consensus_pct = swarm_consensus * 100
    votes_rows = " ".join(
        f"{vote_sym.get(v,'⚪')}{short_names.get(n, n[:4])}"
        for n, v in list((agent_votes or {}).items())[:8]
    )
    consensus_block = (
        f"🐟 Swarm: {consensus_pct:.0f}% consensus · {confidence:.0f}% conf\n"
        f"{votes_rows}\n"
    )

    # ── PM line ──
    pm_section = f"{pm_line}\n" if pm_line else ""

    # ── Footer ──
    footer = "📡 @ichimokutradingsignal | MiroFish Swarm × IRONS AI"

    # ── Assemble full message ──
    full = (
        cornix_block
        + score_block
        + levels_block
        + indicators_block
        + mtf_block
        + squeeze_line
        + pat_line
        + consensus_block
        + pm_section
        + footer
    )

    # Telegram 4096 char hard limit — truncate indicators block if too long
    if len(full) > 4000:
        # Compact indicators to just category scores
        compact_ind = (
            f"📊 Indicators: Momentum {cats.get('momentum',50)}% · "
            f"Trend {cats.get('trend',50)}% · "
            f"Volatility {cats.get('volatility',50)}% · "
            f"Volume {cats.get('volume',50)}%\n"
        )
        full = (
            cornix_block
            + score_block
            + levels_block
            + compact_ind
            + mtf_block
            + squeeze_line
            + pat_line
            + consensus_block
            + pm_section
            + footer
        )

    return full
