#!/usr/bin/env python3
"""
NeuralSignalTrainer — Self-learning signal quality filter for MiroFish Swarm.

Architecture  : 50-feature input → Dense(128, ReLU) → Dense(64, ReLU)
                → Dense(32, ReLU) → Dense(1, Sigmoid)
Optimizer     : Adam with L2 regularisation + dropout (training only)
Loss          : Focal BCE with dynamic class-weighting (adapts to actual W/L ratio)
Persistence   : Weights saved as JSON — survives bot restarts with full warm-start
Training data : Labeled trades from TradeMemory (TP1/TP2/TP3 = win, SL = loss)
Output        : win_probability ∈ [0, 1] for any SwarmSignal

Architecture v3 (50-feature, 4-layer) — Option B "Temporal Awareness" upgrade:
  • Expanded 42 → 50 features: 8 sequential lag price-return features (last 8 bars)
    give the MLP short-term temporal/momentum context without needing an LSTM.
    Each lag is bounded via tanh(return * 100) so the feature stays in [-1, +1]
    regardless of regime. Lag 1 = most recent completed bar return, lag 8 = oldest.
  • Backwards compatible: trades missing `price_returns` get zero-padded lags so
    legacy training data still trains cleanly; old saved weights with input_dim=42
    are detected by _load_weights() and re-initialised cleanly (no crash).
  • Wider hidden layers (64/32/16 → 128/64/32) preserved for greater model capacity
  • Existing 42 features capture: RSI-direction alignment, BB-direction alignment,
    confidence×consensus interaction, quadratic R:R, log volume, cubic consensus,
    sub-day cycle harmonics, and RSI trap risk alignment

Self-Learning Philosophy:
  • Class weight adapts dynamically to actual win/loss ratio so the network
    always penalises the minority class proportionally (was hardcoded 2×).
  • Focal loss down-weights easy samples and forces the network to study hard
    cases — trades that looked good but failed (the most dangerous patterns).
  • After each training cycle, a LossPatternAnalyzer scans feature space for
    "danger zones" — feature ranges consistently associated with losses.
  • Predictions for signals that fall inside danger zones receive an additional
    confidence penalty, further reducing false positives.
  • MC-Dropout (20 stochastic passes) provides calibrated uncertainty so the
    gate can be adjusted by prediction confidence, not just probability alone.
  • Optimal decision threshold is computed from validation data (Youden's J)
    rather than being hardcoded at 0.5 / 0.40 / 0.70.
  • Feature z-score normalisation is fit on training data and applied to all
    predictions, preventing large-magnitude features (e.g. RSI) from dominating
    the gradient signal.

When fewer than MIN_TRAIN_SAMPLES labeled trades exist, predict() returns 0.5
(pass-through — normal confidence gate handles quality control).
"""

import json
import math
import os
import random
import time
import logging
from typing import List, Dict, Optional, Tuple, Any

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    import torch as _torch
    import torch.nn as _nn
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

try:
    from .bitnet_optimizer import BitNetInferenceOptimizer, create_bitnet_optimizer
    _HAS_BITNET = True
except ImportError:
    try:
        from bitnet_optimizer import BitNetInferenceOptimizer, create_bitnet_optimizer
        _HAS_BITNET = True
    except ImportError:
        _HAS_BITNET = False

WEIGHTS_PATH       = os.path.join(os.path.dirname(__file__), "nn_weights.json")
TORCH_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "torch_transformer_weights.pt")

# Transformer tokenisation: reshape 55 features → 11 tokens × 5 dims (55 = 11 × 5)
_TORCH_N_TOKENS  = 11
_TORCH_TOKEN_DIM = 5   # INPUT_DIM // _TORCH_N_TOKENS
_TORCH_D_MODEL   = 32  # compact hidden dim for fast CPU training

MIN_TRAIN_SAMPLES = 15   # v5.4: 20→15 — activates NN sooner; with 17 labeled trades (W=5/L=12)
                         # the NN was stuck in 0.5 pass-through mode. 15 allows activation
                         # so the 50-feature MLP starts filtering signals immediately.
LAG_FEATURE_COUNT   = 8  # v3 (Option B): 8 sequential price-return lags for temporal awareness
OFI_FEATURE_COUNT   = 1  # v4 (OFI): real-time order-flow imbalance from WS depth5 stream
PC_FEATURE_COUNT    = 1  # v5 (PriceConsensus): 7-model ensemble direction tilt
HURST_FEATURE_COUNT = 1  # v6 (HurstRegime): R/S-derived trending vs mean-reverting classifier
EWMA_VOL_FEATURE_COUNT = 1  # v7 (EWMA-Vol): RiskMetrics λ=0.94 vol expansion/contraction signal
SKEW_FEATURE_COUNT = 1  # v8 (RealSkew): Neuberger 2012 model-free realized skewness — third moment
INPUT_DIM          = 55  # v8 (B+OFI+PC+HRS+EWMA+RSK): 42+8+1+1+1+1+1 = 55

# Agent order — all 10 votes used as features (FLOOPAgent added in v5.0 — INPUT_DIM 41→42)
# IMPORTANT: Adding FLOOPAgent here changes W1 shape from (41,128) to (42,128).
# _load_weights() detects the shape mismatch and re-initialises cleanly (no crash).
AGENT_ORDER = [
    "TrendAgent", "MomentumAgent", "VolumeAgent",
    "VolatilityAgent", "OrderFlowAgent", "SentimentAgent",
    "FundingFlowAgent", "PivotSRAgent", "FLOOPAgent", "AIOrchestrationAgent",
]
_SESSION = {"ASIAN": 0.0, "EU": 0.33, "US": 1.0, "TRANSITION": 0.17}
_VOTE    = {"BUY": 1.0, "SELL": -1.0, "NEUTRAL": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: safe float conversion for legacy SQLite BLOB fields
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(value, default: float = 0.0) -> float:
    """
    Convert `value` to float, handling legacy SQLite REAL columns that were
    accidentally stored as raw binary blobs (struct-packed IEEE 754 float32).

    SQLite's Python driver returns bytes when a REAL column contains a raw
    blob (e.g. from an older code version using struct.pack).  Attempting
    `float(b'\\x0c\\x19\\xb8B')` raises ValueError; we unpack it instead.

    Falls back to `default` on any conversion error.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, bytes):
        import struct
        # 4-byte IEEE 754 little-endian float32 (SQLite REAL stored as BLOB)
        if len(value) == 4:
            try:
                return float(struct.unpack('<f', value)[0])
            except Exception:
                pass
        # 8-byte IEEE 754 little-endian float64
        if len(value) == 8:
            try:
                return float(struct.unpack('<d', value)[0])
            except Exception:
                pass
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering  (52 features — v5: Option B lags + OFI + PriceConsensus)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_lag_returns(trade: Dict, n: int = LAG_FEATURE_COUNT) -> List[float]:
    """
    Pull the last `n` completed-bar log-style price returns from the trade dict.

    Accepts (in priority order):
      • trade["price_returns"]        — list/tuple of floats (raw fractional returns)
      • trade["price_returns_json"]   — JSON-encoded list of floats
      • trade["closes"] or ["close_prices"] — list of closes (returns derived)

    Returns a length-`n` list, lag 1 = most recent, padded with 0.0 when missing.
    Each value is squashed via tanh(r * 100) so it lives in [-1, +1] regardless
    of asset volatility — keeps the gradient well-conditioned alongside the
    other normalised features.
    """
    raw: List[float] = []
    pr = trade.get("price_returns")
    if isinstance(pr, (list, tuple)) and pr:
        raw = [float(x) for x in pr if x is not None]
    else:
        prj = trade.get("price_returns_json")
        if isinstance(prj, str) and prj:
            try:
                parsed = json.loads(prj)
                if isinstance(parsed, list):
                    raw = [float(x) for x in parsed if x is not None]
            except Exception:
                raw = []
        if not raw:
            closes = trade.get("closes") or trade.get("close_prices")
            if isinstance(closes, (list, tuple)) and len(closes) >= 2:
                cs = [float(c) for c in closes if c is not None and float(c) > 0]
                # Derive (n+1) closes → n returns; lag 1 = most recent
                tail = cs[-(n + 1):]
                if len(tail) >= 2:
                    raw = [
                        (tail[i] - tail[i - 1]) / tail[i - 1]
                        for i in range(1, len(tail))
                    ]
    # `raw` is oldest→newest; reverse so lag 1 is the most recent
    raw_recent_first = list(reversed(raw))[:n]
    # Pad with zeros if fewer than n returns are available
    while len(raw_recent_first) < n:
        raw_recent_first.append(0.0)
    # Bounded squash: a 1% bar = tanh(1.0) ≈ 0.76, a 0.1% bar ≈ 0.10
    return [math.tanh(r * 100.0) for r in raw_recent_first]


def _extract_price_consensus(trade: Dict) -> float:
    """
    Pull the 7-model Price Consensus tilt from the trade dict.

    Consensus ∈ [-1, +1] is produced by SignalMaestro/price_consensus_predictor
    fusing EMA crossover, OLS slope, z-score mean-reversion, Donchian position,
    VWAP deviation, Holt double-exp smoothing forecast, and ATR-normalised
    momentum.  Returns 0.0 when missing (legacy training rows, producer not
    yet wired) so the slot is benign during cold-start.
    """
    raw = trade.get("price_consensus")
    if raw is None:
        # Compatible alternates the producer might emit
        raw = trade.get("price_consensus_score", trade.get("pc_consensus", 0.0))
    try:
        v = float(raw or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if v >  1.0: v =  1.0
    if v < -1.0: v = -1.0
    return v


def _extract_realized_skew(trade: Dict) -> float:
    """
    Pull the realized-skewness regime signal from the trade dict.

    Signal ∈ [-1, +1] from Neuberger 2012 model-free RS via tanh(RS/2):
        > 0  → SQUEEZE-RISK regime (upside fat tails — favour LONG, fade SHORT)
        ≈ 0  → symmetric returns   (no directional skew premium)
        < 0  → CRASH-RISK regime   (downside fat tails — favour SHORT, fade LONG)

    Computed by SignalMaestro/price_consensus_predictor.realized_skew_signal()
    on a 30-bar return window inside a 50-bar close window.  Producer stamps
    trade['realized_skew'] right before NN inference; returns 0.0 (neutral)
    when missing so the slot is benign during cold-start (existing 1000
    historical training rows have no skew field) and lights up on every
    fresh producer signal.
    """
    raw = trade.get("realized_skew")
    if raw is None:
        raw = trade.get("skew_signal", trade.get("rs_signal", 0.0))
    try:
        v = float(raw or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if v >  1.0: v =  1.0
    if v < -1.0: v = -1.0
    return v


def _extract_ewma_vol(trade: Dict) -> float:
    """
    Pull the EWMA-vol regime signal from the trade dict.

    Signal ∈ [-1, +1] from RiskMetrics λ=0.94 EWMA conditional vol forecast:
        > 0  → vol EXPANSION   (forecast vol > realized — caution, widen SL)
        ≈ 0  → balanced regime (forecast ≈ realized)
        < 0  → vol CONTRACTION (forecast vol < realized — compression / pre-breakout)

    Computed by SignalMaestro/price_consensus_predictor.ewma_vol_signal()
    on a 50-bar close window.  Producer stamps trade['ewma_vol_signal']
    right before NN inference; returns 0.0 (neutral) when missing so the
    slot is benign during cold-start (existing 1000 historical training
    rows have no ewma field) and lights up on every fresh producer signal.
    """
    raw = trade.get("ewma_vol_signal")
    if raw is None:
        raw = trade.get("ewma_vol", trade.get("vol_regime", 0.0))
    try:
        v = float(raw or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if v >  1.0: v =  1.0
    if v < -1.0: v = -1.0
    return v


def _extract_hurst(trade: Dict) -> float:
    """
    Pull the Hurst-regime signal from the trade dict.

    Signal ∈ [-1, +1] derived from the Hurst exponent H via 2·(H − 0.5):
        +1.0  →  H = 1.0   strongly trending / persistent
        +0.4  →  H = 0.7   trending (momentum & breakout favored)
         0.0  →  H = 0.5   random walk (no regime edge)
        -0.4  →  H = 0.3   mean-reverting (fade & reversion favored)
        -1.0  →  H = 0.0   strongly anti-persistent

    Computed by SignalMaestro/price_consensus_predictor.hurst_regime_signal()
    on a 50-bar close window via Rescaled-Range (R/S) analysis at lags
    {4, 8, 12, 16, 24}.  Returns 0.0 (random-walk neutral) when missing so
    the slot is benign during cold-start training (existing 1000 historical
    rows have no hurst field) and lights up on every fresh producer signal.
    """
    raw = trade.get("hurst_signal")
    if raw is None:
        raw = trade.get("hurst", trade.get("hurst_regime", 0.0))
    try:
        v = float(raw or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if v >  1.0: v =  1.0
    if v < -1.0: v = -1.0
    return v


def _extract_ofi(trade: Dict) -> float:
    """
    Pull the real-time Order-Flow Imbalance from the trade dict.

    OFI = (bid_vol − ask_vol) / (bid_vol + ask_vol)  ∈ [-1, +1]

    Computed every 100 ms by Unity Engine's WS depth5 task and stored as
    `depth_imbalance` in `_ws_state[symbol]`.  The producer (fxsusdt bot)
    snapshots that value into the signal record under key 'ofi' before
    invoking the NN.  Returns 0.0 when missing or stale (legacy training
    rows, WS not yet connected) so the slot is benign during cold-start
    and lights up the moment live OB pressure becomes available.

    OFI is one of the most documented short-term price predictors in the
    HFT literature (Cont, Kukanov, Stoikov 2014) — a positive imbalance
    means resting liquidity is biased toward the bid, which historically
    leads price up over the next few hundred milliseconds.
    """
    raw = trade.get("ofi")
    if raw is None:
        raw = trade.get("depth_imbalance", 0.0)
    try:
        v = float(raw or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    # Clamp defensively — WS already produces [-1, +1] but stale/garbled
    # snapshots could overflow; min/max keeps weights well-conditioned.
    if v >  1.0: v =  1.0
    if v < -1.0: v = -1.0
    return v


def build_features(trade: Dict) -> "np.ndarray":
    """
    55-feature normalised vector from a trade record dict (v8 — full quant feature set).

    v3 change: 8 sequential lag price-return features appended (43-50) to give
    the MLP short-term temporal/momentum context without an LSTM. INPUT_DIM 42→50.

    v4 change: 1 real-time order-flow imbalance feature appended (51) — derived
    from Binance @depth5@100ms WS stream — institutional-grade microstructure
    alpha. INPUT_DIM 50→51.

    v5 change: 7-predictor price consensus feature appended (52). INPUT_DIM 51→52.
    v6 change: Hurst fractal regime signal appended (53). INPUT_DIM 52→53.
    v7 change: EWMA-Vol regime signal appended (54). INPUT_DIM 53→54.
    v8 change: Realized-Skewness signal appended (55). INPUT_DIM 54→55.
    v10.4 BUG FIX: docstring now matches implementation (was falsely documented as 51).

    Features 1-12:  scalar signal quality indicators
    Features 13-16: time / leverage encoding
    Features 17-26: all 10 agent votes [-1, 0, +1]   ← +1 for FLOOPAgent
    Features 27-28: derived consensus metrics (agreement fraction, purity)
    Features 29-30: RSI regime flags (overbought / oversold binary)
    Features 31-32: Bollinger Band extreme zone flags (upper / lower extreme)
    Features 33-42: v2 non-linear interaction & regime terms
      33 — RSI strength aligned to direction  (punishes counter-RSI signals)
      34 — BB position aligned to direction   (punishes counter-BB signals)
      35 — confidence × consensus product     (joint quality gate interaction)
      36 — R:R quadratic scaling              (super-linear reward for high R:R)
      37 — participation rate squared         (super-linear reward for quorum)
      38 — consensus cubed                    (strongly amplifies near-unanimous)
      39 — log-normalised volume ratio        (handles vol spikes non-linearly)
      40 — ATR ratio quadratic                (super-linear for high volatility)
      41 — sub-day cosine cycle               (captures intra-session 6h rhythm)
      42 — RSI trap risk aligned to direction (warns of exhaustion in direction)
    Features 43-50: v3 sequential lag price returns  (Option B — temporal awareness)
      43 — lag 1  return (most recent completed bar), tanh(r*100) ∈ [-1, +1]
      44 — lag 2  return
      45 — lag 3  return
      46 — lag 4  return
      47 — lag 5  return
      48 — lag 6  return
      49 — lag 7  return
      50 — lag 8  return  (oldest of the 8-bar window)
    """
    if not _HAS_NUMPY:
        raise ImportError("numpy required for neural signal trainer")

    votes = json.loads(trade.get("agent_votes_json", "{}"))
    # All 10 agent votes (FLOOPAgent added in v5.0 — auto-generated from AGENT_ORDER)
    agent_feats = [_VOTE.get(votes.get(a, "NEUTRAL"), 0.0) for a in AGENT_ORDER]

    direction = 1.0 if trade.get("action", "BUY") == "BUY" else -1.0
    session   = _SESSION.get((trade.get("session") or "US").upper(), 1.0)

    rsi        = _safe_float(trade.get("rsi"),              50.0)
    hour       = _safe_float(trade.get("hour_of_day"),     12.0)
    leverage   = _safe_float(trade.get("leverage"),        10.0)
    bb_pos     = _safe_float(trade.get("bb_position"),      0.5)
    confidence = _safe_float(trade.get("confidence"),      70.0) / 100.0
    consensus  = _safe_float(trade.get("swarm_consensus"), 0.75)
    vol_ratio  = _safe_float(trade.get("volume_ratio"),     1.0)
    rr         = _safe_float(trade.get("risk_reward_ratio"), 1.5)
    atr_ratio  = _safe_float(trade.get("atr_ratio"),       0.003)
    part_rate  = _safe_float(trade.get("participation_rate"), 0.700)

    # Derived consensus metrics
    all_votes = [votes.get(a, "NEUTRAL") for a in AGENT_ORDER]
    n_buy    = sum(1 for v in all_votes if v == "BUY")
    n_sell   = sum(1 for v in all_votes if v == "SELL")
    n_total  = len(AGENT_ORDER)
    # Fraction of agents that agree with the signal direction
    if direction > 0:
        agreement_frac = n_buy / n_total
    else:
        agreement_frac = n_sell / n_total
    # Consensus purity: how dominant is the winning side (0=split, 1=unanimous)
    dominant = max(n_buy, n_sell)
    consensus_purity = dominant / n_total

    # RSI regime binary flags — critical for identifying OB/OS exhaustion traps
    rsi_overbought = 1.0 if rsi > 70.0 else 0.0   # signal fired into OB territory
    rsi_oversold   = 1.0 if rsi < 30.0 else 0.0   # signal fired into OS territory

    # Bollinger Band extreme zone flags — price near the bands = mean-reversion risk
    bb_upper_extreme = 1.0 if bb_pos > 0.85 else 0.0  # price near or above upper BB
    bb_lower_extreme = 1.0 if bb_pos < 0.15 else 0.0  # price near or below lower BB

    # ── v2 Non-linear interaction & regime features (31-40) ──────────────────

    # F31: RSI momentum aligned with signal direction [-1, +1]
    # Positive when RSI bias matches trade direction (good), negative when counter-trend
    rsi_aligned = (rsi - 50.0) / 50.0 * direction

    # F32: BB position bias aligned with signal direction [-0.5, +0.5]
    # BUY: prefer bb_pos < 0.5 (room to run up); SELL: prefer bb_pos > 0.5
    bb_aligned = (0.5 - bb_pos) * direction

    # F33: confidence × consensus joint interaction [0, 1]
    # Captures the compound quality gate: both must be high for a great trade
    conf_x_consensus = confidence * consensus

    # F34: R:R quadratic scaling [0, 1]
    # Disproportionately rewards high R:R trades (e.g. 3:1 >> 2:1)
    rr_quadratic = min(rr / 5.0, 1.0) ** 2

    # F35: Participation rate squared [0, 1]
    # Disproportionately rewards near-unanimous quorum
    part_sq = part_rate ** 2

    # F36: Consensus cubed [0, 1]
    # Strongly amplifies near-unanimous consensus (0.9^3=0.73, 0.72^3=0.37)
    consensus_cubed = consensus ** 3

    # F37: Log-normalised volume ratio [0, 1]
    # Handles volume spikes gracefully (log compression prevents dominance)
    vol_log = min(math.log1p(max(vol_ratio, 0)) / 2.5, 1.0)

    # F38: ATR ratio quadratic [0, 1]
    # Higher volatility gets disproportionately higher weight (risk amplifier)
    atr_quad = min(atr_ratio / 0.015, 1.0) ** 2

    # F39: Sub-day cosine cycle (6h rhythm) — captures intra-session phase
    # Different from the 24h cos (F16) — picks up Asian/EU/US session sub-periods
    hour_cos2 = math.cos(4.0 * math.pi * hour / 24.0)

    # F40: RSI exhaustion trap risk aligned to trade direction [0, 1]
    # BUY into overbought (RSI>65) or SELL into oversold (RSI<35) = trap risk = 1
    # BUY into oversold (RSI<35) or SELL into overbought (RSI>65) = momentum aligned = 0
    if direction > 0:
        rsi_trap = 1.0 if rsi > 65.0 else (0.0 if rsi < 45.0 else (rsi - 45.0) / 20.0)
    else:
        rsi_trap = 1.0 if rsi < 35.0 else (0.0 if rsi > 55.0 else (55.0 - rsi) / 20.0)

    f = [
        # ── Signal quality (1-12) ─────────────────────────────────────────────
        confidence,                                                       # 1
        consensus,                                                        # 2
        _safe_float(trade.get("signal_strength", 65.0), 65.0) / 100.0,   # 3
        part_rate,                                                        # 4
        (rsi - 50.0) / 50.0,                                             # 5  rsi bias [-1,+1]
        min(vol_ratio / 3.0, 1.0),                                       # 6
        min(rr / 5.0, 1.0),                                              # 7
        min(atr_ratio / 0.01, 1.0),                                      # 8
        bb_pos,                                                           # 9
        direction,                                                        # 10 BUY=+1 SELL=-1
        session,                                                          # 11 session [0,1]
        consensus ** 2,                                                   # 12 consensus² (amplify high values)

        # ── Time / leverage encoding (13-16) ─────────────────────────────────
        leverage / 30.0,                                                  # 13 leverage normalised
        (rsi - 50.0) ** 2 / 2500.0,                                      # 14 rsi extremity [0,1]
        math.sin(2.0 * math.pi * hour / 24.0),                           # 15 hour_sin
        math.cos(2.0 * math.pi * hour / 24.0),                           # 16 hour_cos
    ] + agent_feats + [                                                   # 17-26 all 10 agent votes (FLOOPAgent added)

        # ── Derived consensus metrics (27-28) ────────────────────────────────
        agreement_frac,                                                   # 27 direction agreement [0,1]
        consensus_purity,                                                 # 28 dominant-side purity [0,1]

        # ── RSI regime flags (29-30) ─────────────────────────────────────────
        rsi_overbought,                                                   # 29 1 if RSI>70 (OB trap risk)
        rsi_oversold,                                                     # 30 1 if RSI<30 (OS trap risk)

        # ── Bollinger Band extreme zone flags (31-32) ────────────────────────
        bb_upper_extreme,                                                 # 31 1 if price near upper BB
        bb_lower_extreme,                                                 # 32 1 if price near lower BB

        # ── v2 Non-linear interaction & regime features (33-42) ──────────────
        rsi_aligned,                                                      # 33 RSI aligned to direction
        bb_aligned,                                                       # 34 BB pos aligned to direction
        conf_x_consensus,                                                 # 35 confidence × consensus
        rr_quadratic,                                                     # 36 R:R quadratic
        part_sq,                                                          # 37 participation squared
        consensus_cubed,                                                  # 38 consensus cubed
        vol_log,                                                          # 39 log vol ratio
        atr_quad,                                                         # 40 ATR quadratic
        hour_cos2,                                                        # 41 sub-day cosine (6h)
        rsi_trap,                                                         # 42 RSI trap risk aligned
    ]

    # ── v3 Sequential lag price returns (43-50) — Option B temporal awareness ─
    # 8 most-recent completed-bar returns squashed via tanh(r*100) ∈ [-1, +1].
    # When `price_returns` / `closes` aren't on the trade record (e.g. legacy
    # training rows), the helper returns zeros so the slot is benign during
    # training but lights up the moment upstream code starts populating it.
    f.extend(_extract_lag_returns(trade, LAG_FEATURE_COUNT))             # 43-50

    # ── v4 Real-time Order-Flow Imbalance (51) — institutional microstructure ─
    # OFI ∈ [-1, +1] from Binance @depth5@100ms WS stream.  Captures resting
    # liquidity asymmetry that historically leads price by 100-500 ms.  Producer
    # snapshots WS state into signal['ofi'] right before NN inference so the
    # 20-pass MC-Dropout sees the freshest microstructure pressure available.
    f.append(_extract_ofi(trade))                                        # 51

    # ── v5 Multi-model Price Consensus (52) — 7-predictor ensemble ──────────
    # Equal-weighted average of EMA crossover + OLS slope + z-score mean
    # reversion + Donchian position + VWAP dev + Holt double-exp forecast +
    # ATR-normalised momentum.  Produced by price_consensus_predictor module.
    # ∈ [-1, +1] (negative = bearish, positive = bullish).  Producer computes
    # from raw klines and stamps trade['price_consensus'] before NN inference.
    f.append(_extract_price_consensus(trade))                            # 52

    # ── v6 Hurst-Regime Signal (53) — fractal market state classifier ───────
    # Rescaled-Range (R/S) Hurst exponent H ∈ [0,1] mapped to a [-1,+1] tilt:
    #   H > 0.55 (sig > +0.10) → trending (NN can up-weight momentum cues)
    #   H ≈ 0.50 (sig ≈   0.0) → random walk (no regime edge)
    #   H < 0.45 (sig < -0.10) → mean-reverting (NN can up-weight reversion)
    # The MLP learns regime-conditional win-prob: e.g. "trust EMA crossover
    # signals more when feature 53 > 0".  Produced by price_consensus_predictor
    # .hurst_regime_signal() and stamped into trade['hurst_signal'] by producer.
    f.append(_extract_hurst(trade))                                      # 53

    # ── v7 EWMA-Vol Regime Signal (54) — RiskMetrics 1994 (λ = 0.94) ─────────
    # Conditional volatility forecast: σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}
    # Mapped to [-1, +1] via tanh(σ_ewma / σ_realized − 1):
    #   > 0  → vol EXPANSION   (caution: regime change, widen SL, smaller size)
    #   ≈ 0  → balanced regime (forecast ≈ realized)
    #   < 0  → vol CONTRACTION (compression / pre-breakout setup forming)
    # The institutional second-moment companion to the Hurst (first-moment
    # persistence) classifier — together they form the complete fractal-vol
    # regime picture every elite quant desk uses for risk-adjusted execution.
    f.append(_extract_ewma_vol(trade))                                   # 54

    # ── v8 Realized-Skewness Signal (55) — third-moment regime classifier ──
    # Neuberger 2012 model-free RS = √n · Σr³ / (Σr²)^1.5 mapped to [-1, +1]:
    #   sig > +0.10 → SQUEEZE-RISK regime (upside fat tails, fade SHORTs)
    #   sig ≈   0.0 → symmetric returns   (no directional skew premium)
    #   sig < -0.10 → CRASH-RISK regime   (downside fat tails, fade LONGs)
    # This is the institutional third-moment companion to Hurst (1st-moment
    # persistence, feat 53) and EWMA-Vol (2nd-moment persistence, feat 54).
    # Crypto futures shows the strongest documented RS premium in any asset
    # class (Bakshi-Kapadia-Madan 2003, Kozhan-Neuberger-Schneider 2013).
    # Producer computes via realized_skew_from_klines() and stamps
    # trade['realized_skew']; the MLP learns asymmetric direction-conditional
    # win-prob (e.g. "trust BUYs more when RS > 0").
    f.append(_extract_realized_skew(trade))                              # 55

    arr = np.array(f, dtype=np.float32)
    if arr.shape[0] != INPUT_DIM:
        raise ValueError(f"Feature shape {arr.shape[0]} ≠ {INPUT_DIM}")
    return arr


def build_label(trade: Dict) -> float:
    """
    Binary label: 1.0 = win, 0.0 = loss, -1.0 = skip (neutral / ambiguous).

    TP1/TP2/TP3  → always WIN  (price reached take-profit — unambiguous)
    SL           → always LOSS (stop-loss hit — unambiguous)
    EXPIRED      → ONLY labeled when pnl is meaningful:
                   pnl ≥ +0.5%  → WIN  (expired but clearly profitable)
                   pnl ≤ −0.5%  → LOSS (expired with significant drawdown)
                   −0.5% < pnl < +0.5% → SKIP (-1.0): too noisy to learn from.
                     Previously these were labeled 0.0 (loss), injecting 48
                     near-zero P&L trades as confirmed losses and inflating the
                     loss rate from ~52% to 80% — corrupting class weights and
                     causing the NN to predict low win probability for everything.
    """
    outcome = (trade.get("outcome") or "EXPIRED").upper()
    if outcome in ("TP1", "TP2", "TP3"):
        return 1.0
    if outcome == "SL":
        return 0.0
    # EXPIRED: require a meaningful P&L to generate a reliable label
    pnl = _safe_float(trade.get("pnl_pct"), 0.0)
    if pnl >= 0.5:
        return 1.0
    if pnl <= -0.5:
        return 0.0
    return -1.0  # neutral EXPIRED — caller must skip (do NOT train on this)


# ─────────────────────────────────────────────────────────────────────────────
# Loss Pattern Analyzer — identifies feature zones correlated with losses
# ─────────────────────────────────────────────────────────────────────────────

class LossPatternAnalyzer:
    """
    After training, analyses the feature distribution of winning vs losing trades
    to identify "danger zones" — feature ranges strongly associated with losses.

    Called once per training cycle.  Stores the danger zone boundaries so that
    predict_with_loss_penalty() can apply an additional penalty to signals that
    match known losing patterns.
    """

    def __init__(self):
        # danger_zones[feature_idx] = (low, high, loss_rate) for zones with high loss rate
        self.danger_zones: List[Tuple[int, float, float, float]] = []
        self.feature_importance: List[float] = [1.0] * INPUT_DIM
        self.win_means: Optional["np.ndarray"]  = None
        self.loss_means: Optional["np.ndarray"] = None
        self.is_fitted = False
        # Base loss rate from training data — stored so danger_penalty uses a relative
        # threshold rather than the hardcoded 0.65 that caused negative penalties when
        # the base rate was below 65% (e.g. zones with loss_rate 0.63 gave penalty < 0).
        self._base_loss_rate: float = 0.50

    # Maximum number of danger zones kept in memory.
    # With 50 features × 8 bins = 400 candidate zones; cap prevents the
    # danger-zone penalty from covering ALL of feature space when the
    # base loss rate is already high (e.g. 55% → every bin exceeds 65%).
    MAX_DANGER_ZONES = 12

    def fit(self, X: "np.ndarray", y: "np.ndarray"):
        """
        Compute per-feature loss patterns from training data.

        X: (N, INPUT_DIM) feature matrix
        y: (N,) binary labels (1=win, 0=loss)

        FIXED: danger zones are now computed RELATIVE to the base loss rate.
        A zone is only marked dangerous if its loss_rate exceeds the dataset-
        wide loss_rate by at least DANGER_MARGIN (15pp).  Previously the
        threshold was an absolute 65%, so when the base rate was 80% (due to
        mislabeled neutral EXPIRED trades) EVERY bin exceeded the threshold
        and all 56 zones were marked dangerous — blocking every signal.

        After filtering neutral EXPIRED trades the base rate is ~48%, so the
        effective threshold becomes ~63% — much more selective.

        Only the top MAX_DANGER_ZONES zones (sorted by delta above base rate)
        are kept to ensure the penalty covers the most dangerous feature regions
        without blanketing the entire feature space.
        """
        if not _HAS_NUMPY or len(X) < 10:
            return
        try:
            wins   = X[y == 1]
            losses = X[y == 0]

            if len(wins) == 0 or len(losses) == 0:
                return

            win_mean  = np.mean(wins,   axis=0)
            loss_mean = np.mean(losses, axis=0)
            win_std   = np.std(wins,    axis=0) + 1e-8
            loss_std  = np.std(losses,  axis=0) + 1e-8

            self.win_means  = win_mean
            self.loss_means = loss_mean

            # Feature importance: abs difference in means normalised by std
            self.feature_importance = list(
                abs(win_mean - loss_mean) / ((win_std + loss_std) / 2)
            )

            # Base loss rate for this training batch
            base_loss_rate = float(1.0 - y.mean())
            self._base_loss_rate = base_loss_rate  # stored for use in danger_penalty()

            # Danger zones: zones where loss_rate meaningfully exceeds base rate.
            # Threshold = base_rate + 15pp (e.g. 48% base → 63% threshold).
            # This is relative, so it stays meaningful regardless of class imbalance.
            DANGER_MARGIN = 0.15
            zone_threshold = min(base_loss_rate + DANGER_MARGIN, 0.85)

            candidate_zones = []
            n_bins = 8  # fewer bins → larger zones → fewer false positives
            for fi in range(INPUT_DIM):
                col   = X[:, fi]
                col_y = y
                edges = np.percentile(col, np.linspace(0, 100, n_bins + 1))
                for bi in range(n_bins):
                    lo, hi = edges[bi], edges[bi + 1]
                    mask = (col >= lo) & (col <= hi)
                    n_in = int(mask.sum())
                    if n_in < 5:  # need at least 5 samples for reliable rate
                        continue
                    loss_rate = float(1.0 - col_y[mask].mean())
                    delta = loss_rate - base_loss_rate
                    if loss_rate > zone_threshold:
                        candidate_zones.append(
                            (fi, float(lo), float(hi), float(loss_rate), delta)
                        )

            # Keep only the top MAX_DANGER_ZONES by delta above base rate
            candidate_zones.sort(key=lambda z: z[4], reverse=True)
            self.danger_zones = [
                (fi, lo, hi, lr)
                for fi, lo, hi, lr, _ in candidate_zones[:self.MAX_DANGER_ZONES]
            ]

            self.is_fitted = True
        except Exception:
            pass

    def danger_penalty(self, x: "np.ndarray") -> float:
        """
        Return a penalty [0, 0.15] to subtract from win_probability for signals
        that fall inside known danger zones.  Higher = more dangerous pattern.

        BUG FIX: Previously used hardcoded 0.65 as the penalty base. After the
        relative threshold fix in fit() (base_rate + 15pp), zones with loss_rate
        between base_rate+15pp and 0.65 produced NEGATIVE penalties, boosting
        the confidence of bad signals instead of penalising them.

        Fix: use self._base_loss_rate as the reference so penalty is always
        proportional to how much the zone exceeds the base rate (always ≥ 0).
        Penalty = (loss_rate - base_rate) × importance × scaling_factor
        Capped at 0.15 to prevent over-rejection.
        """
        if not self.is_fitted or not self.danger_zones:
            return 0.0
        try:
            penalty = 0.0
            base_lr = max(self._base_loss_rate, 0.30)
            _zones_hit = 0
            for fi, lo, hi, loss_rate in self.danger_zones:
                if lo <= x[fi] <= hi:
                    excess = loss_rate - base_lr
                    if excess <= 0:
                        continue
                    imp = min(self.feature_importance[fi], 3.0) / 3.0
                    _zone_pen = min(excess * imp * 0.4, 0.06)
                    penalty += _zone_pen
                    _zones_hit += 1
                    if _zones_hit >= 4:
                        break
            # Cap raised from 0.10 → 0.15 to match the documented range [0, 0.15].
            return min(max(penalty, 0.0), 0.15)
        except Exception:
            return 0.0

    def update_incremental(self, x: "np.ndarray", label: float):
        """Incrementally update danger zone loss rates with a single new sample."""
        if not self.is_fitted or not self.danger_zones:
            return
        try:
            updated = []
            for fi, lo, hi, loss_rate in self.danger_zones:
                if lo <= x[fi] <= hi:
                    alpha = 0.05
                    is_loss = 1.0 if label == 0.0 else 0.0
                    loss_rate = loss_rate * (1.0 - alpha) + is_loss * alpha
                updated.append((fi, lo, hi, loss_rate))
            self.danger_zones = updated
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# PyTorch Transformer Predictor  (v11.0 — attention-based ensemble complement)
# ─────────────────────────────────────────────────────────────────────────────

if _HAS_TORCH:
    class _TransformerSignalModule(_nn.Module):
        """
        CLS-token Transformer encoder over tokenized 55-feature input.

        Reshape:  (B, 55) → (B, 11, 5) tokens
        Project:  each token (5-dim) → d_model via learnable linear
        CLS:      prepend learnable CLS token → (B, 12, d_model)
        Positional: add learned positional embeddings
        Encode:   2-layer pre-norm TransformerEncoder (4-head, GELU, dropout=0.10)
        Head:     CLS output → LayerNorm → Linear(16) → GELU → Dropout → Linear(1) → Sigmoid
        Output:   win_probability ∈ [0, 1]

        Token groupings (semantic):
          tokens 0-3  : signal quality (confidence, consensus, strength, participation, RSI-bias, vol, R:R, ATR)
          tokens 4-7  : regime flags (BB, direction, session, consensus², leverage, extremity)
          tokens 8-9  : agent votes (agents 1-5 and 6-10)
          token  10   : derived / non-linear / lag features
        """

        def __init__(self, d_model: int = _TORCH_D_MODEL, nhead: int = 4,
                     num_layers: int = 2, dropout: float = 0.10):
            super().__init__()
            self.input_proj = _nn.Linear(_TORCH_TOKEN_DIM, d_model, bias=True)
            self.cls_token  = _nn.Parameter(_torch.zeros(1, 1, d_model))
            self.pos_embed  = _nn.Parameter(_torch.zeros(1, _TORCH_N_TOKENS + 1, d_model))
            enc_layer = _nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=d_model * 4,
                dropout=dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,     # pre-LN (more stable on small datasets)
            )
            self.encoder = _nn.TransformerEncoder(enc_layer, num_layers=num_layers)
            self.head = _nn.Sequential(
                _nn.LayerNorm(d_model),
                _nn.Linear(d_model, 16),
                _nn.GELU(),
                _nn.Dropout(dropout),
                _nn.Linear(16, 1),
            )
            # Weight initialisation
            _nn.init.trunc_normal_(self.cls_token, std=0.02)
            _nn.init.trunc_normal_(self.pos_embed, std=0.02)

        def forward(self, x: "_torch.Tensor") -> "_torch.Tensor":
            B = x.size(0)
            tokens  = x.view(B, _TORCH_N_TOKENS, _TORCH_TOKEN_DIM)   # (B, 11, 5)
            tokens  = self.input_proj(tokens)                          # (B, 11, d_model)
            cls     = self.cls_token.expand(B, -1, -1)                # (B, 1,  d_model)
            tokens  = _torch.cat([cls, tokens], dim=1)                 # (B, 12, d_model)
            tokens  = tokens + self.pos_embed                         # learned position
            out     = self.encoder(tokens)                            # (B, 12, d_model)
            cls_out = out[:, 0, :]                                    # (B, d_model)
            return _torch.sigmoid(self.head(cls_out)).squeeze(-1)     # (B,)


class TorchTransformerPredictor:
    """
    Trains and serves the PyTorch Transformer complement to NeuralSignalTrainer.

    When PyTorch ≥ 2.0 is available:
      • fit(X_norm, y) trains on the same normalised data as the numpy MLP.
      • predict(x_norm) returns win_probability ∈ [0, 1] or 0.5 when untrained.
      • Weights are persisted to torch_transformer_weights.pt (atomic rename).
      • Ensemble blend in predict_signal_with_uncertainty():
            final = 0.60 × mlp_prob + 0.40 × transformer_prob
        giving the MLP majority vote while letting attention capture
        cross-feature interactions (e.g. high consensus AND trending Hurst
        AND positive OFI) that explicit feature products cannot express.

    Graceful degradation:
      • When PyTorch is absent, all methods are no-ops / 0.5 passthrough.
      • If training fails (OOM, shape mismatch), trained=False — MLP continues.
    """

    # Ensemble blend weights (MLP : Transformer)
    _MLP_WEIGHT   = 0.60
    _TORCH_WEIGHT = 0.40

    def __init__(self):
        self.trained = False
        self._model  = None
        self._logger = logging.getLogger(__name__)
        if _HAS_TORCH:
            try:
                self._model = _TransformerSignalModule()
                self._load()
            except Exception as e:
                self._logger.debug(f"TorchTransformer init: {e}")

    # ── Train ────────────────────────────────────────────────────────────────

    def fit(self, X_norm: "np.ndarray", y: "np.ndarray",
            epochs: int = 100, batch_size: int = 32, lr: float = 3e-4) -> bool:
        """
        Train on normalised (N, 55) feature matrix + binary labels (0/1).
        Uses same 80/20 train/val split as numpy MLP (15% val).
        Returns True on success.
        """
        if not _HAS_TORCH or self._model is None:
            return False
        if not _HAS_NUMPY or len(X_norm) < 20:
            return False
        try:
            _torch.manual_seed(42)  # v15.3 Bug V FIX: deterministic randperm in training loop
            device = _torch.device("cpu")
            self._model.to(device)

            n_val = max(4, int(len(X_norm) * 0.15))
            X_tr, X_va = X_norm[:-n_val], X_norm[-n_val:]
            y_tr, y_va = y[:-n_val].flatten(), y[-n_val:].flatten()

            Xtr = _torch.tensor(X_tr, dtype=_torch.float32)
            ytr = _torch.tensor(y_tr, dtype=_torch.float32)
            Xva = _torch.tensor(X_va, dtype=_torch.float32)
            yva = _torch.tensor(y_va, dtype=_torch.float32)

            def focal_bce(pred: "_torch.Tensor", tgt: "_torch.Tensor",
                          gamma: float = 2.0) -> "_torch.Tensor":
                eps = 1e-7
                p   = pred.clamp(eps, 1.0 - eps)
                pt  = _torch.where(tgt == 1, p, 1.0 - p)
                return (-((1.0 - pt) ** gamma) * pt.log()).mean()

            opt = _torch.optim.AdamW(
                self._model.parameters(), lr=lr, weight_decay=1e-4
            )
            sched = _torch.optim.lr_scheduler.CosineAnnealingLR(
                opt, T_max=epochs, eta_min=1e-5
            )
            best_val  = float("inf")
            best_sd   = {k: v.clone() for k, v in self._model.state_dict().items()}
            no_imp    = 0
            n_epochs_run = 0

            for epoch in range(epochs):
                self._model.train()
                perm = _torch.randperm(len(Xtr))
                for s in range(0, len(Xtr), batch_size):
                    idx  = perm[s: s + batch_size]
                    loss = focal_bce(self._model(Xtr[idx]), ytr[idx])
                    opt.zero_grad()
                    loss.backward()
                    _nn.utils.clip_grad_norm_(self._model.parameters(), 1.0)
                    opt.step()
                sched.step()
                n_epochs_run = epoch + 1

                self._model.eval()
                with _torch.no_grad():
                    vl = focal_bce(self._model(Xva), yva).item()

                if vl < best_val - 1e-5:
                    best_val = vl
                    best_sd  = {k: v.clone() for k, v in self._model.state_dict().items()}
                    no_imp   = 0
                else:
                    no_imp += 1
                    if no_imp >= 18:
                        break

            self._model.load_state_dict(best_sd)
            self.trained = True
            self._save()
            self._logger.info(
                f"🔮 PyTorch Transformer trained | n={len(X_norm)} "
                f"val_loss={best_val:.4f} epochs={n_epochs_run}"
            )
            return True
        except Exception as e:
            self._logger.warning(f"TorchTransformer.fit failed (MLP unaffected): {e}")
            return False

    # ── Predict ──────────────────────────────────────────────────────────────

    def predict(self, x_norm: "np.ndarray") -> float:
        """Return win_probability ∈ [0, 1]. Returns 0.5 when untrained."""
        if not self.trained or self._model is None or not _HAS_TORCH:
            return 0.5
        try:
            self._model.eval()
            with _torch.no_grad():
                xt = _torch.tensor(
                    x_norm.reshape(1, -1).astype("float32"), dtype=_torch.float32
                )
                return float(self._model(xt).item())
        except Exception:
            return 0.5

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        if not _HAS_TORCH or self._model is None:
            return
        try:
            tmp = TORCH_WEIGHTS_PATH + ".tmp"
            _torch.save(self._model.state_dict(), tmp)
            os.replace(tmp, TORCH_WEIGHTS_PATH)
        except Exception as e:
            self._logger.debug(f"TorchTransformer save failed: {e}")

    def _load(self) -> None:
        if not _HAS_TORCH or not os.path.exists(TORCH_WEIGHTS_PATH):
            return
        try:
            sd = _torch.load(
                TORCH_WEIGHTS_PATH, map_location="cpu", weights_only=True
            )
            self._model.load_state_dict(sd)
            self.trained = True
            self._logger.info("🔮 PyTorch Transformer weights loaded from disk")
        except Exception as e:
            self._logger.debug(f"TorchTransformer load (cold start — training fresh): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# NeuralSignalTrainer
# ─────────────────────────────────────────────────────────────────────────────

class NeuralSignalTrainer:
    """
    Three-hidden-layer MLP (v2 wider) trained with mini-batch Adam + focal BCE loss.

    Forward:  X(N,50) → Z1=X·W1+b1 → A1=ReLU(Z1) → [dropout]
                      → Z2=A1·W2+b2 → A2=ReLU(Z2) → [dropout]
                      → Z3=A2·W3+b3 → A3=ReLU(Z3)
                      → Z4=A3·W4+b4 → out=σ(Z4)  (N,1)

    Architecture v3 (Option B): 50→128→64→32→1
      • 50 input features = 42 base + 8 sequential lag price returns (temporal)
      • Wider hidden layers: 128/64/32 (v1: 64/32/16) for greater capacity
      • Same 4 parameters groups (W1/b1 through W4/b4)

    Loss: Class-weighted Focal BCE (dynamic class weight based on W/L ratio)
      L = -α * (1-p_t)^γ * log(p_t)
    where α = n_wins/n_losses (adaptive), γ = 2.0 (focusing parameter)

    Key capabilities:
      1. Cosine LR schedule uses _base_lr (not self.lr) — no corruption after epoch 1.
      2. Feature z-score normalisation (fit on training data, applied to predictions).
      3. Optimal decision threshold computed from validation set via Youden's J.
      4. MC-Dropout uncertainty (N=20 stochastic passes) for calibrated confidence.
      5. Dynamic class weight adapts to actual W/L ratio each training run (1.0–5.0).
      6. LossPatternAnalyzer identifies feature danger zones after each training cycle.

    Saves weights to JSON on every successful training run so a bot restart
    continues from the last learned state.
    """

    # MC-Dropout inference passes for uncertainty estimation
    # v9.7: raised 20 → 50.  Mathematically equivalent to ensembling 50 stochastic
    # subnetworks (Gal & Ghahramani 2016 — Dropout as Bayesian Approximation).
    # Variance of the mean estimate scales as 1/√n, so 20→50 tightens the σ
    # estimate by √(50/20) ≈ 1.58×.  This reduces false-positive uncertainty
    # rejects ("σ > 0.18 → unc-override penalty") and stabilises G4 win_prob,
    # at the cost of ~2.5× per-signal predict time (still <30 ms; full Unity
    # cycle is ~0.8 s — negligible overhead).  No retrain required; uses the
    # already-trained MLP weights with more dropout samples.
    _MC_PASSES = 50
    # Dropout rate used for MC-Dropout at inference time (matches training)
    _MC_DROPOUT = 0.20

    def __init__(self, lr: float = 0.001, l2: float = 1e-4,
                 focal_gamma: float = 2.0,
                 class_weight_loss: float = 2.0):
        self.logger  = logging.getLogger(__name__)
        # FIX 1: store _base_lr separately so _cosine_lr never reads the
        # already-decayed self.lr — the bug that broke the schedule after epoch 1.
        self._base_lr = lr
        self.lr       = lr
        self.l2      = l2
        self.focal_gamma = focal_gamma
        # class_weight_loss is a default / floor; train() overrides it dynamically
        self._default_class_weight_loss = class_weight_loss
        self.class_weight_loss = class_weight_loss
        # Dual per-class weights: _w_win applied to y=1, _w_loss to y=0.
        # Both default to 1.0; train() recalculates them from actual data.
        self._w_win:  float = 1.0
        self._w_loss: float = class_weight_loss

        # Adam hyper-parameters
        self._b1     = 0.9
        self._b2     = 0.999
        self._eps    = 1e-8
        self._t      = 0

        # Training state
        self.trained           = False
        self.n_samples_trained = 0
        self.last_train_time   = 0.0
        self.last_accuracy     = 0.0
        self.last_val_loss     = float("inf")
        self.last_win_rate     = 0.0    # fraction of training data that was wins
        self.last_loss_rate    = 0.0    # fraction of training data that was losses

        # FIX 5: Optimal threshold (Youden's J from validation data).
        # reject_threshold: signals below this are hard-rejected or heavily penalized.
        # boost_threshold:  signals above this get a confidence boost.
        # FIXED: Was 0.08 (near-zero), allowing 5% win_prob signals to slip through.
        # Raised to 0.38 floor — rejects signals below the 38% win-probability target
        # needed to achieve positive EV at the configured 1.55:1 R:R ratio
        # (breakeven = 1/(1+1.55) = ~39.2%; floor set at 0.38 for slight tolerance).
        self._opt_threshold    = 0.50   # default; overwritten after each training run
        self._reject_threshold = 0.38   # floor: reject below 38% win prob (raised from 0.35)
        self._boost_threshold  = 0.70   # upper bound (only boost above this)

        # Direction-aware calibration offsets.
        # Corrects for BUY-biased training data: the model tends to underestimate
        # SELL signal win probability when trained on more BUY than SELL samples.
        # offset = mean(actual_label) - mean(predicted_prob) per direction.
        # Applied additively in predict_signal*() so SELL predictions are shifted
        # to match the observed win rate for that direction.
        self._buy_prob_offset:  float = 0.0
        self._sell_prob_offset: float = 0.0

        # FIX 4: Feature normalisation statistics (fit on training data).
        self._feat_mean: Optional["np.ndarray"] = None
        self._feat_std:  Optional["np.ndarray"] = None
        self._feat_fitted = False

        # Loss pattern analyzer
        self.loss_analyzer = LossPatternAnalyzer()

        # Last MC-Dropout uncertainty σ — written by predict_signal_with_uncertainty
        # and predict_from_dict; read by the engine's G4_UNC_SOFT bypass.
        # Explicit __init__ value prevents AttributeError on first getattr read
        # before any prediction has been made.
        self._last_uncertainty: float = 0.0

        # v11.0: PyTorch Transformer ensemble complement
        # Loaded/initialised after numpy MLP so it doesn't block cold-start
        self._torch_predictor: Optional["TorchTransformerPredictor"] = (
            TorchTransformerPredictor() if _HAS_TORCH else None
        )
        if self._torch_predictor is not None and self._torch_predictor.trained:
            self.logger.info("🔮 PyTorch Transformer predictor active (ensemble mode)")
        elif _HAS_TORCH:
            self.logger.debug("🔮 PyTorch Transformer predictor ready — will train after first NN cycle")

        # BitNet-inspired ternary inference optimizer (optional acceleration layer)
        # Loads after weights are available; provides fast ternary inference + MC-Dropout
        # Reference: https://github.com/microsoft/BitNet
        self._bitnet: Optional["BitNetInferenceOptimizer"] = None
        if _HAS_BITNET:
            try:
                self._bitnet = create_bitnet_optimizer(input_dim=INPUT_DIM)
            except Exception:
                self._bitnet = None

        if not _HAS_NUMPY:
            self.logger.warning("⚠️  numpy not found — NeuralSignalTrainer disabled")
            return

        self._xavier_init()
        self._load_weights()

        # Post-load: sync BitNet optimizer with restored float weights
        if self._bitnet is not None and self.trained:
            try:
                loaded = self._bitnet.load_from_trainer(self)
                if loaded:
                    stats = self._bitnet.get_stats()
                    self.logger.info(
                        f"🔢 BitNet optimizer synced | "
                        f"avg_sparsity={sum(stats['sparsity'].values())/len(stats['sparsity']):.0%} "
                        f"| quantization=ternary_absmean"
                    )
            except Exception as e:
                self.logger.debug(f"BitNet post-load sync failed: {e}")

    # ── Weight initialisation ─────────────────────────────────────────────

    def _xavier_init(self):
        rng = np.random.default_rng(42)

        def _w(fan_in, fan_out):
            # He initialisation for ReLU activations (fan_in only) — better than
            # Xavier for deep ReLU networks as it accounts for the dead-neuron effect
            s = np.sqrt(2.0 / fan_in)
            return rng.normal(0, s, (fan_in, fan_out)).astype(np.float32)

        # v3 architecture (Option B): 50 → 128 → 64 → 32 → 1  (42 base + 8 lag returns)
        self.W1 = _w(INPUT_DIM, 128); self.b1 = np.zeros((1, 128), np.float32)
        self.W2 = _w(128, 64);        self.b2 = np.zeros((1, 64),  np.float32)
        self.W3 = _w(64, 32);         self.b3 = np.zeros((1, 32),  np.float32)
        self.W4 = _w(32, 1);          self.b4 = np.zeros((1, 1),   np.float32)

        # Adam first and second moment vectors
        self._m = [np.zeros_like(p) for p in self._params()]
        self._v = [np.zeros_like(p) for p in self._params()]

        # Reset Adam step counter when reinitialising weights
        self._t = 0

    def _params(self):
        return [self.W1, self.b1, self.W2, self.b2, self.W3, self.b3, self.W4, self.b4]

    # ── Activations ──────────────────────────────────────────────────────

    @staticmethod
    def _relu(x):    return np.maximum(0, x)
    @staticmethod
    def _relu_d(x):  return (x > 0).astype(np.float32)
    @staticmethod
    def _sigmoid(x): return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))

    # ── Feature normalisation ─────────────────────────────────────────────

    def _fit_normaliser(self, X: "np.ndarray"):
        """Fit z-score normaliser on training data X (N, INPUT_DIM)."""
        self._feat_mean  = X.mean(axis=0)
        self._feat_std   = X.std(axis=0) + 1e-8   # avoid divide-by-zero
        self._feat_fitted = True

    @staticmethod
    def _utc_hour(ts) -> int:
        """Extract UTC hour from a timestamp, converting from any timezone."""
        if ts is None:
            return 12
        try:
            if hasattr(ts, 'utcoffset') and ts.utcoffset() is not None:
                from datetime import timezone
                ts = ts.astimezone(timezone.utc)
            return ts.hour
        except Exception:
            return 12

    def _normalise(self, X: "np.ndarray") -> "np.ndarray":
        """Apply z-score normalisation.  Returns X unchanged if not yet fitted."""
        if not self._feat_fitted or self._feat_mean is None:
            return X
        return (X - self._feat_mean) / self._feat_std

    # ── Forward pass ─────────────────────────────────────────────────────

    def _forward(self, X: "np.ndarray", training: bool = False, dropout: float = 0.20):
        Z1 = X @ self.W1 + self.b1
        A1 = self._relu(Z1)
        mask1 = None
        if training and dropout > 0:
            mask1 = (np.random.rand(*A1.shape) > dropout).astype(np.float32) / (1.0 - dropout)
            A1 = A1 * mask1

        Z2 = A1 @ self.W2 + self.b2
        A2 = self._relu(Z2)
        mask2 = None
        if training and dropout > 0:
            mask2 = (np.random.rand(*A2.shape) > dropout).astype(np.float32) / (1.0 - dropout)
            A2 = A2 * mask2

        Z3 = A2 @ self.W3 + self.b3
        A3 = self._relu(Z3)

        Z4 = A3 @ self.W4 + self.b4
        A4 = self._sigmoid(Z4)

        return Z1, A1, mask1, Z2, A2, mask2, Z3, A3, Z4, A4

    # ── Focal BCE loss ────────────────────────────────────────────────────

    def _focal_bce_loss(self, y_true: "np.ndarray", y_pred: "np.ndarray") -> "np.ndarray":
        """
        Focal Binary Cross-Entropy loss with dual per-class dynamic weighting.

        For each sample:
          • If y_true == 1 (win):  weight = _w_win,  p_t = y_pred,       focal = (1-p_t)^γ
          • If y_true == 0 (loss): weight = _w_loss, p_t = 1 - y_pred,   focal = (1-p_t)^γ

        Loss = -weight * focal * log(p_t + ε)

        Dual weights ensure the MINORITY class always gets proportionally higher weight:
          • wins dominant  (wins  > losses): _w_loss = n_wins/n_losses  > 1, _w_win  = 1
          • losses dominant(losses > wins ): _w_win  = n_losses/n_wins  > 1, _w_loss = 1
        Previously only the loss class (y=0) was weighted, meaning when losses dominated
        the minority class (wins) had NO extra penalty — now both cases are handled.
        """
        _eps = 1e-7
        γ = self.focal_gamma

        p = np.clip(y_pred, _eps, 1.0 - _eps)

        # p_t: probability of correct class
        p_t     = np.where(y_true == 1, p, 1.0 - p)
        # Apply dual per-class weights (set by train() each run)
        weight  = np.where(y_true == 1, self._w_win, self._w_loss)
        focal_w = (1.0 - p_t) ** γ

        loss = -weight * focal_w * np.log(p_t)
        return loss  # shape (N, 1)

    # ── Optimal threshold computation ─────────────────────────────────────

    def _compute_optimal_threshold(self, X_val: "np.ndarray",
                                   y_val: "np.ndarray") -> float:
        """
        Compute optimal binary classification threshold on validation data.

        v9.5 fix — replaced Youden's J (J = TPR + TNR - 1) with the
        **G-mean** statistic G = sqrt(TPR * TNR).  Youden's J is additively
        symmetric and was selecting low thresholds (≈0.375) that gave 98%
        TPR / 42% TNR — a multiplicatively unbalanced classifier.  G-mean
        is the geometric mean of per-class recall and is the standard
        threshold-selection metric for imbalanced classification (Kubat &
        Matwin 1997).  It penalises any class whose recall collapses, so
        the model is forced to learn losses as well as it learns wins.

        Additional preference: among all thresholds whose G-mean is within
        0.5% of the maximum, pick the one with the highest min(TPR, TNR)
        AND loss_acc (TNR) ≥ 0.50.  This guarantees the model genuinely
        learns losing trades — the symptom that triggered this fix.

        Returns threshold in [0.30, 0.70] clamped for safety.  Falls back
        to 0.50 on any error.  Validation sets with <10 samples return 0.50
        because the metric is statistically unreliable on tiny samples.
        """
        try:
            if len(y_val) < 10:
                return 0.50
            _, _, _, _, _, _, _, _, _, A4v = self._forward(X_val, training=False)
            probs = A4v.flatten()
            y_flat = y_val.flatten()

            scan = []
            for t in np.arange(0.30, 0.71, 0.02):
                preds = (probs >= t).astype(int)
                tp = int(np.sum((preds == 1) & (y_flat == 1)))
                tn = int(np.sum((preds == 0) & (y_flat == 0)))
                fp = int(np.sum((preds == 1) & (y_flat == 0)))
                fn = int(np.sum((preds == 0) & (y_flat == 1)))
                tpr = tp / max(tp + fn, 1)
                tnr = tn / max(tn + fp, 1)
                g_mean = float(math.sqrt(max(tpr, 0.0) * max(tnr, 0.0)))
                scan.append((float(t), tpr, tnr, g_mean))

            if not scan:
                return 0.50

            best_g = max(row[3] for row in scan)
            # Tier-1 candidates: within 0.5% of the best G-mean AND loss_acc≥0.50
            tier1 = [r for r in scan if r[3] >= best_g - 0.005 and r[2] >= 0.50]
            # Tier-2 fallback: within 1.5% of best G-mean (loss_acc constraint relaxed)
            tier2 = [r for r in scan if r[3] >= best_g - 0.015]

            pool = tier1 if tier1 else (tier2 if tier2 else scan)
            # Choose the threshold maximising min(TPR, TNR) — most balanced classifier
            pool.sort(key=lambda r: (min(r[1], r[2]), r[3]), reverse=True)
            best_thresh = pool[0][0]

            # Derived reject / boost thresholds around optimal threshold.
            #
            # Formula: max(0.38, best_thresh * 0.62) with 0.38 hard floor.
            # The 0.38 floor reflects the EV-breakeven win rate at 1.55:1 R:R:
            #   breakeven = 1/(1+1.55) ≈ 39.2% — floor at 0.38 gives slight tolerance.
            #   thresh=0.525 → max(0.38, 0.326) = 0.38
            #   thresh=0.600 → max(0.38, 0.372) = 0.38
            #   thresh=0.700 → max(0.38, 0.434) = 0.43
            # Raised from 0.35 to 0.38 to enforce positive-EV selection discipline.
            self._reject_threshold = max(0.38, best_thresh * 0.62)
            self._boost_threshold  = min(0.85, best_thresh + 0.15)
            return best_thresh
        except Exception:
            return 0.50

    # ── MC-Dropout prediction ─────────────────────────────────────────────

    def predict_mc(self, X: "np.ndarray",
                   n_passes: int = _MC_PASSES,
                   dropout: float = _MC_DROPOUT) -> Tuple["np.ndarray", "np.ndarray"]:
        """
        Monte-Carlo Dropout inference: run N stochastic forward passes and
        return (mean_probs, std_probs) across passes.

        The standard deviation measures epistemic uncertainty — high std means
        the network is unsure regardless of the mean probability.
        """
        if not _HAS_NUMPY or not self.trained:
            n = len(X)
            return (np.full(n, 0.5, dtype=np.float32),
                    np.full(n, 0.0, dtype=np.float32))
        samples = []
        for _ in range(n_passes):
            _, _, _, _, _, _, _, _, _, A4 = self._forward(X, training=True, dropout=dropout)
            samples.append(A4.flatten())
        stacked = np.stack(samples, axis=0)   # (n_passes, N)
        return stacked.mean(axis=0), stacked.std(axis=0)

    # ── Prediction ───────────────────────────────────────────────────────

    def predict_batch(self, X: "np.ndarray") -> "np.ndarray":
        """Win probability for each row in X. Returns 0.5 array if untrained."""
        if not _HAS_NUMPY or not self.trained:
            return np.full(len(X), 0.5, dtype=np.float32)
        X_norm = self._normalise(X)
        _, _, _, _, _, _, _, _, _, A4 = self._forward(X_norm, training=False)
        return A4.flatten()

    def predict_signal(self, signal, bb_position: float = 0.5) -> float:
        """
        Win probability for a single SwarmSignal, with optional loss-pattern penalty.
        Returns 0.5 (neutral) if untrained or on any error.
        """
        if not _HAS_NUMPY or not self.trained:
            return 0.5
        try:
            atr_ratio = (
                signal.atr_value / signal.entry_price
                if (getattr(signal, "atr_value", None) and signal.entry_price)
                else 0.003
            )
            rec = {
                "action":             signal.action,
                "confidence":         signal.confidence,
                "swarm_consensus":    signal.swarm_consensus,
                "signal_strength":    signal.signal_strength,
                "participation_rate": getattr(signal, "participation_rate", 0.700),
                "rsi":                signal.rsi,
                "volume_ratio":       signal.volume_ratio,
                "risk_reward_ratio":  signal.risk_reward_ratio,
                "atr_ratio":          atr_ratio,
                "bb_position":        bb_position,
                "hour_of_day":        self._utc_hour(signal.timestamp),
                "session":            getattr(signal, "market_session", "US"),
                "agent_votes_json":   json.dumps(signal.agent_votes or {}),
                "leverage":           getattr(signal, "leverage", 10),
            }
            X_raw = build_features(rec).reshape(1, -1)
            base_prob = float(self.predict_batch(X_raw)[0])
            X_norm = self._normalise(X_raw)

            _dir_offset = (
                self._sell_prob_offset if rec.get("action") == "SELL"
                else self._buy_prob_offset
            )
            base_prob = float(np.clip(base_prob + _dir_offset, 0.05, 1.0))

            if self.loss_analyzer.is_fitted:
                penalty = self.loss_analyzer.danger_penalty(X_norm[0])
                # Raised scaling 0.35 → 0.60: danger zone penalty was being cut by 65%,
                # rendering the loss-pattern analysis nearly ineffective.
                penalty *= 0.60
                base_prob = max(0.05, base_prob - penalty)

            # v11.0: blend with PyTorch Transformer when trained (60% MLP / 40% Transformer)
            if (self._torch_predictor is not None and self._torch_predictor.trained):
                torch_prob = self._torch_predictor.predict(X_norm[0])
                base_prob  = (TorchTransformerPredictor._MLP_WEIGHT * base_prob
                              + TorchTransformerPredictor._TORCH_WEIGHT * torch_prob)
                base_prob  = float(np.clip(base_prob, 0.05, 1.0))

            return base_prob
        except Exception as e:
            self.logger.debug(f"predict_signal error: {e}")
            return 0.5

    def predict_from_dict(self, signal_data: Dict, bb_position: float = 0.5) -> float:
        """
        Win probability computed directly from a signal_data dict.  (v16.1 FIX)

        Resolves the silent type mismatch that caused the engine's Gate-4 fallback
        to call ``predict(dict)`` — a method that expects ``np.ndarray`` — which
        always raised an exception, was silently caught, and returned 0.5.  Gate 4
        was therefore entirely non-functional for every signal that did not carry a
        pre-computed ``nn_win_prob_precomputed`` value (i.e. all of them).

        v16.2: Upgraded from predict_signal (single forward pass) to
        predict_signal_with_uncertainty (50-pass MC-Dropout).  This activates the
        uncertainty estimate and writes self._last_uncertainty so the engine's
        G4_UNC_SOFT bypass logic at Gate 4 actually fires.  Previously
        _last_uncertainty was always 0.0 (never updated by the predict_signal path),
        so the uncertainty-aware soft-bypass was also a dead letter.

        Also passes microstructure enrichment fields (ofi, price_consensus,
        hurst_signal, ewma_vol_signal, realized_skew) from the signal dict when
        present, giving the model the full 55-feature input it was trained on.

        Args:
            signal_data : dict with standard Unity Engine signal keys.
            bb_position : Bollinger Band position [0, 1] (default 0.5 = neutral).

        Returns:
            mean win_probability ∈ [0.05, 1.0] from the MC-Dropout ensemble.
            Returns 0.5 on any error (self._last_uncertainty reset to 0.0).
        """
        if not _HAS_NUMPY or not self.trained:
            return 0.5
        try:
            import types as _types
            action = (signal_data.get("action") or
                      signal_data.get("direction") or "BUY")
            entry  = float(signal_data.get("entry") or
                           signal_data.get("entry_price") or 1.0)
            atr    = float(signal_data.get("atr_value") or
                           signal_data.get("atr") or 0.0)
            sig = _types.SimpleNamespace(
                action            = action.upper(),
                confidence        = float(signal_data.get("confidence") or
                                          signal_data.get("ai_confidence") or 70.0),
                swarm_consensus   = float(signal_data.get("swarm_consensus") or 0.75),
                signal_strength   = float(signal_data.get("signal_strength") or 50.0),
                participation_rate= float(signal_data.get("participation_rate") or 0.70),
                rsi               = float(signal_data.get("rsi") or 50.0),
                volume_ratio      = float(signal_data.get("volume_ratio") or 1.0),
                risk_reward_ratio = float(signal_data.get("risk_reward_ratio") or
                                          signal_data.get("rr_ratio") or 1.85),
                atr_value         = atr,
                entry_price       = entry,
                timestamp         = float(signal_data.get("timestamp") or
                                          __import__("time").time()),
                market_session    = (signal_data.get("session") or
                                     signal_data.get("market_session") or "US"),
                agent_votes       = json.loads(
                                        signal_data.get("agent_votes_json") or "{}"
                                    ),
                leverage          = int(signal_data.get("leverage") or 10),
            )
            # v16.2: Use MC-Dropout (50 passes) so _last_uncertainty is populated
            # and the engine's G4_UNC_SOFT bypass has real σ data to act on.
            # Also pass microstructure features when available in signal_data.
            mean_p, std_p = self.predict_signal_with_uncertainty(
                sig,
                bb_position    = bb_position,
                ofi            = float(signal_data.get("ofi")             or 0.0),
                price_consensus= float(signal_data.get("price_consensus") or 0.0),
                hurst_signal   = float(signal_data.get("hurst_signal")    or 0.0),
                ewma_vol_signal= float(signal_data.get("ewma_vol_signal") or 0.0),
                realized_skew  = float(signal_data.get("realized_skew")   or 0.0),
            )
            # _last_uncertainty is already written inside predict_signal_with_uncertainty,
            # but we mirror it here for clarity and to ensure it's always current.
            self._last_uncertainty = float(std_p)
            return float(mean_p)
        except Exception as e:
            self.logger.debug(f"predict_from_dict error: {e}")
            self._last_uncertainty = 0.0
            return 0.5

    def predict_batch_mc_from_dicts(
        self,
        records: List[Dict],
        bb_positions: Optional[List[float]] = None,
        n_mc: int = 20,
    ) -> Tuple["np.ndarray", "np.ndarray"]:
        """
        Batch MC-Dropout inference over N signal dicts simultaneously. [v18.16]

        Replaces N individual predict_from_dict() calls (each doing n_mc=50
        forward passes on a (1,55) matrix) with n_mc forward passes on an
        (N,55) matrix — reducing total FLOPS from N×50 to just n_mc=20 passes
        for the entire batch, regardless of batch size.

        For a 50-symbol scan cycle with N=50 and n_mc=50 (default per-symbol),
        this is 50×50=2500 forward passes → 20 forward passes of size 50:
        a 125× FLOP reduction with identical mean and tighter σ estimates.

        Features:
          • z-score normalises the full N×55 matrix in one vectorised call
          • n_mc stochastic forward passes on the full batch via predict_mc()
          • Direction-aware calibration offsets applied per row
          • LossPatternAnalyzer danger zone penalties applied per row
          • PyTorch Transformer blending applied across the full batch

        Args:
            records      : list of N signal dicts (standard Unity Engine format)
            bb_positions : optional per-record bb_position overrides (len=N)
            n_mc         : Monte-Carlo Dropout passes (default 20 for batch mode)

        Returns:
            mean_probs : np.ndarray shape (N,) — calibrated win-probability
            std_probs  : np.ndarray shape (N,) — epistemic uncertainty per row
        """
        N = len(records)
        _fallback_mean = np.full(N, 0.5, dtype=np.float32)
        _fallback_std  = np.zeros(N, dtype=np.float32)
        if N == 0:
            return _fallback_mean[:0], _fallback_std[:0]
        if not _HAS_NUMPY or not self.trained or not self._feat_fitted:
            return _fallback_mean, _fallback_std
        try:
            if bb_positions is None:
                bb_positions = [0.5] * N

            # Build N×55 feature matrix from signal dicts
            X_raw = np.stack([build_features(r) for r in records], axis=0)  # (N,55)
            X_norm = self._normalise(X_raw)                                   # (N,55)

            # n_mc stochastic passes on the FULL batch (not N individual passes)
            mean_p, std_p = self.predict_mc(X_norm, n_passes=n_mc)
            mean_p = mean_p.astype(np.float32).copy()
            std_p  = std_p.astype(np.float32).copy()

            # Per-row direction calibration + danger zone penalty
            for i, r in enumerate(records):
                _dir = (r.get("action") or r.get("direction") or "BUY").upper()
                _off = self._sell_prob_offset if _dir == "SELL" else self._buy_prob_offset
                mean_p[i] = float(np.clip(float(mean_p[i]) + _off, 0.05, 1.0))
                if self.loss_analyzer and self.loss_analyzer.is_fitted:
                    pen = self.loss_analyzer.danger_penalty(X_norm[i]) * 0.60
                    mean_p[i] = max(0.05, float(mean_p[i]) - pen)

            # PyTorch Transformer blending across the full batch
            if self._torch_predictor is not None and self._torch_predictor.trained:
                torch_probs = np.array(
                    [self._torch_predictor.predict(X_norm[i]) for i in range(N)],
                    dtype=np.float32,
                )
                mean_p = (TorchTransformerPredictor._MLP_WEIGHT * mean_p
                          + TorchTransformerPredictor._TORCH_WEIGHT * torch_probs)
                mean_p = np.clip(mean_p, 0.05, 1.0).astype(np.float32)

            return mean_p, std_p
        except Exception as e:
            self.logger.debug(f"predict_batch_mc_from_dicts error: {e}")
            return _fallback_mean, _fallback_std

    def predict_signal_with_uncertainty(self, signal, bb_position: float = 0.5,
                                        n_passes: int = _MC_PASSES,
                                        ofi: float = 0.0,
                                        price_consensus: float = 0.0,
                                        hurst_signal: float = 0.0,
                                        ewma_vol_signal: float = 0.0,
                                        realized_skew: float = 0.0,
                                        ) -> Tuple[float, float]:
        """
        MC-Dropout prediction for a single signal.
        Returns (mean_win_prob, uncertainty_std).

        High uncertainty (std > 0.15) means the model is unsure — useful for
        the caller to decide whether to apply a stricter threshold.
        """
        if not _HAS_NUMPY or not self.trained:
            return 0.5, 0.0
        try:
            atr_ratio = (
                signal.atr_value / signal.entry_price
                if (getattr(signal, "atr_value", None) and signal.entry_price)
                else 0.003
            )
            rec = {
                "action":             signal.action,
                "confidence":         signal.confidence,
                "swarm_consensus":    signal.swarm_consensus,
                "signal_strength":    signal.signal_strength,
                "participation_rate": getattr(signal, "participation_rate", 0.700),
                "rsi":                signal.rsi,
                "volume_ratio":       signal.volume_ratio,
                "risk_reward_ratio":  signal.risk_reward_ratio,
                "atr_ratio":          atr_ratio,
                "bb_position":        bb_position,
                "hour_of_day":        self._utc_hour(signal.timestamp),
                "session":            getattr(signal, "market_session", "US"),
                "agent_votes_json":   json.dumps(signal.agent_votes or {}),
                "leverage":           getattr(signal, "leverage", 10),
                "ofi":                ofi,                              # v4: real-time WS depth imbalance
                "price_consensus":    price_consensus,                  # v5: 7-model ensemble tilt
                "hurst_signal":       hurst_signal,                     # v6: Hurst-regime classifier
                "ewma_vol_signal":    ewma_vol_signal,                  # v7: RiskMetrics EWMA vol regime
                "realized_skew":      realized_skew,                    # v8: Neuberger 2012 realized skewness
            }
            X_raw  = build_features(rec).reshape(1, -1)
            X_norm = self._normalise(X_raw)
            mean_arr, std_arr = self.predict_mc(X_norm, n_passes=n_passes)
            mean_p = float(mean_arr[0])
            std_p  = float(std_arr[0])

            _dir_offset = (
                self._sell_prob_offset if rec.get("action") == "SELL"
                else self._buy_prob_offset
            )
            mean_p = float(np.clip(mean_p + _dir_offset, 0.05, 1.0))

            if self.loss_analyzer.is_fitted:
                penalty = self.loss_analyzer.danger_penalty(X_norm[0])
                # Raised scaling 0.35 → 0.60 (matches predict_signal fix).
                penalty *= 0.60
                mean_p = max(0.05, mean_p - penalty)

            # v11.0: blend MC-Dropout MLP with PyTorch Transformer (60%/40%)
            # The transformer's deterministic output is kept separate from the
            # uncertainty estimate — std_p remains the MLP's MC-Dropout σ.
            if (self._torch_predictor is not None and self._torch_predictor.trained):
                torch_prob = self._torch_predictor.predict(X_norm[0])
                mean_p = (TorchTransformerPredictor._MLP_WEIGHT * mean_p
                          + TorchTransformerPredictor._TORCH_WEIGHT * torch_prob)
                mean_p = float(np.clip(mean_p, 0.05, 1.0))

            # v10.5 FIX: persist σ so start_unity_engine G4-FIX-B can read it
            self._last_uncertainty = float(std_p)
            return mean_p, std_p
        except Exception as e:
            self.logger.debug(f"predict_signal_with_uncertainty error: {e}")
            self._last_uncertainty = 0.0
            return 0.5, 0.0

    # ── Adam update ───────────────────────────────────────────────────────

    def _adam_step(self, grads: list):
        """In-place Adam parameter update."""
        self._t += 1
        params = self._params()
        for i, (p, g) in enumerate(zip(params, grads)):
            self._m[i] = self._b1 * self._m[i] + (1.0 - self._b1) * g
            self._v[i] = self._b2 * self._v[i] + (1.0 - self._b2) * (g ** 2)
            m_hat = self._m[i] / (1.0 - self._b1 ** self._t)
            v_hat = self._v[i] / (1.0 - self._b2 ** self._t)
            p -= self.lr * m_hat / (np.sqrt(v_hat) + self._eps)

    def _cosine_lr(self, epoch: int, max_epochs: int, lr_min: float = 1e-5) -> float:
        """
        Cosine learning rate schedule.

        FIX 1: uses self._base_lr (set once in __init__) as the starting rate.
        Previous version used self.lr, which was already overwritten by the
        schedule result from the PREVIOUS epoch — breaking the schedule after
        epoch 1 (self.lr was always lr_min after the first cosine step).
        """
        return lr_min + 0.5 * (self._base_lr - lr_min) * (
            1.0 + math.cos(math.pi * epoch / max_epochs)
        )

    # ── Training ─────────────────────────────────────────────────────────

    def train(
        self,
        trades: List[Dict],
        epochs: int = 400,
        batch_size: int = 32,
        patience: int = 30,
        dropout: float = 0.20,
        warm_restart: bool = False,
    ) -> Dict:
        """
        Full training run on labeled trades with focal loss + dynamic class weighting.

        Splits 85/15 train/val, uses early stopping on validation focal-BCE loss.
        After training, runs LossPatternAnalyzer to identify danger zones.
        Computes optimal decision threshold from validation data (G-mean statistic).
        """
        if not _HAS_NUMPY:
            return {"status": "disabled", "reason": "numpy not available"}

        if len(trades) < MIN_TRAIN_SAMPLES:
            return {"status": "skipped", "reason": f"only {len(trades)} samples (need {MIN_TRAIN_SAMPLES})"}

        t0 = time.time()
        try:
            # ── Filter out neutral EXPIRED trades (label == -1.0) ───────────
            # These have pnl in the range -0.5%..+0.5% and are too noisy to
            # train on.  Including them inflated the apparent loss rate from
            # ~52% to 80%, causing the model to predict "LOSS" for everything.
            # Also track trade action (BUY/SELL) for direction calibration.
            filtered_triples = [
                (build_features(t), build_label(t), t.get("action", "BUY"))
                for t in trades
            ]
            filtered_triples = [(x, y, a) for x, y, a in filtered_triples if y >= 0.0]
            if len(filtered_triples) < MIN_TRAIN_SAMPLES:
                return {
                    "status": "skipped",
                    "reason": (
                        f"only {len(filtered_triples)} trainable samples after "
                        f"filtering neutral EXPIRED (need {MIN_TRAIN_SAMPLES})"
                    )
                }

            X_all = np.array([x for x, _, _ in filtered_triples], dtype=np.float32)
            y_all = np.array([y for _, y, _ in filtered_triples], dtype=np.float32).reshape(-1, 1)
            _train_actions = [a for _, _, a in filtered_triples]  # for direction calibration

            wins   = int(np.sum(y_all == 1))
            losses = int(np.sum(y_all == 0))

            # FIXED: Dual per-class dynamic weighting — always weights the MINORITY
            # class proportionally, regardless of which class is dominant.
            #
            # Previous bug: only the loss class (y=0) ever received a weight > 1.0.
            # When losses dominated (losses > wins), wins/losses < 1 was clipped to 1.0
            # → minority class (wins) received NO extra penalty, causing the model to
            # predict "loss" for everything.
            #
            # Fix: compute inverse-frequency weights for BOTH classes:
            #   wins dominant  (wins > losses):  _w_loss = wins/losses  > 1, _w_win  = 1
            #   losses dominant(losses > wins):  _w_win  = losses/wins  > 1, _w_loss = 1
            # v7.2: cap lowered 5.0→2.0.  Focal loss (γ=2.0) already down-weights easy
            # samples; a hard cap of 2x prevents extreme win-weighting (e.g. 2.69x at
            # WR=27%) from causing the model to over-predict "win" on borderline signals.
            # v9.4: cap raised 2.0→3.0.  At observed live WR ≈ 24-27% the loss class
            # accounts for ~73% of samples, so the win-minority needs ~2.7x weighting
            # to receive parity gradient.  The previous 2.0 cap clipped that to ~74%
            # of required weight, biasing the model to under-predict wins (the live
            # symptom: NN absolute-rejects firing on 12-21% win_prob for nearly every
            # BUY).  Combined with the calibrated absolute floor in fxsusdt_telegram_bot
            # this restores proper minority-class learning without breaking focal loss.
            _MAX_CLASS_WEIGHT = 3.0
            if wins > 0 and losses > 0:
                ratio = float(wins) / float(losses)
                if ratio >= 1.0:
                    # Wins dominant — penalise the loss minority
                    self._w_win  = 1.0
                    self._w_loss = float(np.clip(ratio, 1.0, _MAX_CLASS_WEIGHT))
                else:
                    # Losses dominant — penalise the win minority
                    self._w_win  = float(np.clip(1.0 / ratio, 1.0, _MAX_CLASS_WEIGHT))
                    self._w_loss = 1.0
                self.class_weight_loss = max(self._w_win, self._w_loss)
            else:
                self._w_win  = 1.0
                self._w_loss = self._default_class_weight_loss
                self.class_weight_loss = self._default_class_weight_loss
            self.logger.info(
                f"🔢 Dual class weights: w_win={self._w_win:.2f}x w_loss={self._w_loss:.2f}x "
                f"(W={wins} L={losses})"
            )

            # v15.3 Bug V FIX: Set deterministic seeds before every train() call.
            # Without seeds, np.random.permutation() and torch.randperm() use
            # a different RNG state each run, causing train/val splits and batch
            # orderings to differ → 20% accuracy swings (91%→71%) between
            # consecutive retrains on the SAME 939-sample dataset.
            # Seed 42 is arbitrary but fixed — ensures reproducible splits and
            # weight init so accuracy reflects DATA quality, not RNG luck.
            random.seed(42)
            np.random.seed(42)
            if _HAS_TORCH:
                _torch.manual_seed(42)
            self.logger.info(
                "🔧 [v15.3 Bug V] Deterministic RNG seeds set "
                "(random/numpy/torch seed=42) — fixes 20% accuracy swings "
                "between consecutive retrains on same dataset"
            )

            n   = len(X_all)
            idx = np.random.permutation(n)
            split = max(10, int(n * 0.85))
            X_tr_raw, y_tr = X_all[idx[:split]],  y_all[idx[:split]]
            X_va_raw, y_va = X_all[idx[split:]],   y_all[idx[split:]]

            # FIX 4: Fit z-score normaliser on TRAINING data only to prevent
            # validation/test data leakage into the normalisation statistics.
            self._fit_normaliser(X_tr_raw)
            X_tr = self._normalise(X_tr_raw)
            X_va = self._normalise(X_va_raw)

            # ── v9.5 fix: Minority-class oversampling on the TRAIN split ──
            # Class weighting alone is mathematically insufficient when the
            # minority class is severely under-represented (live data shows
            # 27% wins, 73% losses).  Each minibatch (size 32) typically
            # contains only ~8 minority samples — gradient noise dominates
            # signal, so the model converges to predicting the majority class
            # and applying weights only to a noisy gradient.
            #
            # Solution: physically replicate minority-class samples (with
            # mild Gaussian feature jitter to act as a poor-man's SMOTE) so
            # the train-set has roughly balanced class counts.  This gives
            # every minibatch a healthy mix of both classes, restores stable
            # gradient direction, and lets focal loss + class weights focus
            # on hardness rather than rarity.
            #
            # NB:  Validation set (X_va, y_va) is NEVER oversampled.  All
            # accuracy / loss / threshold metrics are still computed against
            # the true label distribution — no metric inflation.
            try:
                y_tr_flat = y_tr.flatten().astype(int)
                pos_mask  = y_tr_flat == 1
                neg_mask  = y_tr_flat == 0
                n_pos     = int(pos_mask.sum())
                n_neg     = int(neg_mask.sum())
                if n_pos >= 4 and n_neg >= 4 and abs(n_pos - n_neg) >= 4:
                    minority_mask = pos_mask if n_pos < n_neg else neg_mask
                    deficit = abs(n_pos - n_neg)
                    minority_X = X_tr[minority_mask]
                    minority_y = y_tr[minority_mask]
                    rng = np.random.default_rng(42)  # v15.3 Bug V FIX: fixed seed (was time-based → non-deterministic oversampling)
                    sampled_idx = rng.integers(0, len(minority_X), size=deficit)
                    extra_X = minority_X[sampled_idx]
                    extra_y = minority_y[sampled_idx]
                    # Mild Gaussian feature jitter (σ=0.05 on z-scored space) to
                    # avoid memorising the exact minority points and improve
                    # generalisation.
                    jitter = rng.normal(0.0, 0.03, size=extra_X.shape).astype(np.float32)
                    extra_X = (extra_X + jitter).astype(np.float32)
                    X_tr = np.concatenate([X_tr, extra_X], axis=0)
                    y_tr = np.concatenate([y_tr, extra_y], axis=0)
                    self.logger.info(
                        f"⚖️  Minority oversampling: replicated "
                        f"{deficit} samples (class={'WIN' if n_pos<n_neg else 'LOSS'}) "
                        f"with σ=0.03 jitter — train pos/neg now ≈ "
                        f"{int((y_tr.flatten()==1).sum())}/"
                        f"{int((y_tr.flatten()==0).sum())}"
                    )
            except Exception as _osamp_err:
                self.logger.debug(f"Oversampling skipped: {_osamp_err}")
            # Normalise full dataset for final accuracy + loss-pattern fitting
            X_all_norm = self._normalise(X_all)

            if not (warm_restart and self.trained):
                self._xavier_init()
                # Reset base LR on cold restart so cosine schedule starts fresh.
                # Use max() to guarantee _base_lr is at least 1e-3 even when
                # self.lr has drifted to the cosine annealing floor (≈1e-5 + ε),
                # which would satisfy self.lr > 1e-5 but yield a near-zero base LR
                # and a flat cosine schedule on the next cycle.
                self._base_lr = max(self.lr, 1e-3)

            best_val   = float("inf")
            best_wts   = [p.copy() for p in self._params()]
            no_improve = 0
            history    = []

            for epoch in range(epochs):
                # FIX 1: Cosine LR uses _base_lr, not the already-decayed self.lr
                self.lr = self._cosine_lr(epoch, epochs, lr_min=1e-5)

                perm = np.random.permutation(len(X_tr))
                X_sh, y_sh = X_tr[perm], y_tr[perm]

                for s in range(0, len(X_sh), batch_size):
                    Xb = X_sh[s: s + batch_size]
                    yb = y_sh[s: s + batch_size]
                    m  = len(Xb)

                    Z1, A1, mask1, Z2, A2, mask2, Z3, A3, Z4, A4 = self._forward(
                        Xb, training=True, dropout=dropout
                    )

                    # ── Focal BCE gradient w.r.t. logits Z4 ──────────────────
                    # Uses dual per-class weights (_w_win / _w_loss) to ensure
                    # the minority class always gets proportionally higher gradient.
                    _eps = 1e-7
                    γ    = self.focal_gamma

                    p    = np.clip(A4, _eps, 1.0 - _eps)
                    p_t  = np.where(yb == 1, p, 1.0 - p)
                    wt   = np.where(yb == 1, self._w_win, self._w_loss)
                    focal_w = (1.0 - p_t) ** γ  # precomputed — reused below to avoid redundant pow

                    # d(focal_BCE)/d(A4): chain rule through focal weight
                    d_pt_dp = np.where(yb == 1, 1.0, -1.0)
                    grad_p = wt * (
                        γ * (1.0 - p_t) ** (γ - 1) * np.log(p_t + _eps)
                        - focal_w / (p_t + _eps)          # BUG FIX: was re-computing (1-p_t)^γ inline
                    ) * d_pt_dp
                    # Through sigmoid: dA4/dZ4 = A4*(1-A4)
                    dZ4 = grad_p * A4 * (1.0 - A4) / m

                    # NOTE: dZ4 is already divided by m (batch average).
                    # All subsequent gradient tensors (dA3/dZ3/dA2/dZ2/dA1/dZ1)
                    # inherit that /m factor through backpropagation.
                    # Therefore:
                    #   dW = (prev_activation.T @ dZ)   ← no extra /m (already /m)
                    #   db = dZ.sum(axis=0)              ← sum (not mean) since dZ is already /m
                    # Previous code had dW/m (extra division → effective lr was lr/m²)
                    # and db=mean(dZ) (another /m → lr/m²). Both are now corrected.
                    dW4 = (A3.T @ dZ4) + self.l2 * self.W4
                    db4 = dZ4.sum(axis=0, keepdims=True)

                    dA3 = dZ4 @ self.W4.T
                    dZ3 = dA3 * self._relu_d(Z3)
                    dW3 = (A2.T @ dZ3) + self.l2 * self.W3
                    db3 = dZ3.sum(axis=0, keepdims=True)

                    dA2 = dZ3 @ self.W3.T
                    if mask2 is not None:
                        dA2 = dA2 * mask2
                    dZ2 = dA2 * self._relu_d(Z2)
                    dW2 = (A1.T @ dZ2) + self.l2 * self.W2
                    db2 = dZ2.sum(axis=0, keepdims=True)

                    dA1 = dZ2 @ self.W2.T
                    if mask1 is not None:
                        dA1 = dA1 * mask1
                    dZ1 = dA1 * self._relu_d(Z1)
                    dW1 = (Xb.T @ dZ1) + self.l2 * self.W1
                    db1 = dZ1.sum(axis=0, keepdims=True)

                    self._adam_step([dW1, db1, dW2, db2, dW3, db3, dW4, db4])

                # ── Validation loss (no dropout) ──
                _, _, _, _, _, _, _, _, _, A4v = self._forward(X_va, training=False)
                val_focal = self._focal_bce_loss(y_va, A4v)
                val_loss  = float(np.mean(val_focal))
                history.append(val_loss)

                if val_loss < best_val - 1e-5:
                    best_val   = val_loss
                    best_wts   = [p.copy() for p in self._params()]
                    no_improve = 0
                else:
                    no_improve += 1
                    if no_improve >= patience:
                        break

            # Restore best weights
            self.W1, self.b1, self.W2, self.b2, self.W3, self.b3, self.W4, self.b4 = best_wts

            # FIX 5: Compute optimal decision threshold from validation data.
            # v15.3 Bug Q FIX: Apply EMA smoothing (α=0.35) to prevent the
            # threshold from swinging ±6-8pp between retrains due to random
            # validation-split variance.  Without smoothing the threshold
            # oscillated 0.460→0.520→0.540 every 2h, alternately over-blocking
            # and over-relaxing the NN gate.
            # EMA: new_smoothed = 0.35 × new_raw + 0.65 × prev_smoothed
            # At first retrain (_opt_threshold==0.50 default) the first raw
            # value is adopted at ~65% weight — converges to data in ~3 retrains.
            _raw_thresh = self._compute_optimal_threshold(X_va, y_va)
            _EMA_ALPHA  = 0.35
            _prev_thresh = float(getattr(self, "_opt_threshold", 0.50))
            if _prev_thresh == 0.50:
                # First retrain — accept raw value directly (no prior to blend)
                _smoothed_thresh = _raw_thresh
            else:
                _smoothed_thresh = round(
                    _EMA_ALPHA * _raw_thresh + (1.0 - _EMA_ALPHA) * _prev_thresh, 3
                )
            self._opt_threshold = _smoothed_thresh
            # _reject_threshold was set by _compute_optimal_threshold from _raw_thresh;
            # re-derive it from the smoothed threshold to stay consistent.
            self._reject_threshold = max(0.38, _smoothed_thresh * 0.62)
            self._boost_threshold  = min(0.85, _smoothed_thresh + 0.15)
            self.logger.info(
                f"🎯 [v15.3 Bug Q] Optimal NN threshold: {_smoothed_thresh:.3f} "
                f"(raw={_raw_thresh:.3f} prev={_prev_thresh:.3f} α=0.35 EMA) "
                f"(reject<{self._reject_threshold:.3f} boost>{self._boost_threshold:.3f})"
            )

            # Full-dataset accuracy at optimal threshold
            _, _, _, _, _, _, _, _, _, A4_all = self._forward(X_all_norm, training=False)
            preds  = (A4_all.flatten() >= self._opt_threshold).astype(int)
            y_flat = y_all.flatten().astype(int)
            acc    = float(np.mean(preds == y_flat))

            # ── Direction-aware calibration: correct for BUY/SELL data imbalance ──
            # When training data is BUY-biased, the NN underestimates SELL win
            # probability because fewer SELL examples guided the gradient.
            # Calibration offset = mean(actual_label) - mean(predicted_prob) per
            # direction — applied additively at inference to de-bias SELL signals.
            #
            # v15.3 Bug X FIX: compute calibration on VALIDATION data only.
            # OLD bug: calibration used FULL training-set predictions (A4_all).
            # Because the model overfits its training set, training-set probs are
            # artificially high (≈0.75-0.85) even for true losses, so
            #   raw_offset = mean(actuals) - mean(probs_train) ≈ 0.35 - 0.78 = -0.43
            # but the -0.07 cap only corrected 7 of those 43 points → live NN
            # remained 36-percentage-points overconfident → signals that look like
            # 0.70 win prob actually win only 35% of the time.
            # FIX: use X_va / y_va (never seen during training) so probs reflect
            # what the model predicts on truly unseen data, matching live inference.
            # Also raised cap 0.07 → 0.15 so larger miscalibrations can be applied.
            try:
                _val_idx      = idx[split:]     # original-data indices of val samples
                _buy_mask_val = np.array(
                    [_train_actions[int(i)] == "BUY" for i in _val_idx], dtype=bool
                )
                _sel_mask_val = ~_buy_mask_val
                _, _, _, _, _, _, _, _, _, _A4_val = self._forward(X_va, training=False)
                _probs_val   = _A4_val.flatten()
                _actuals_val = y_va.flatten()
                _raw_buy = (
                    float(np.mean(_actuals_val[_buy_mask_val]) - np.mean(_probs_val[_buy_mask_val]))
                    if _buy_mask_val.any() else 0.0
                )
                _raw_sell = (
                    float(np.mean(_actuals_val[_sel_mask_val]) - np.mean(_probs_val[_sel_mask_val]))
                    if _sel_mask_val.any() else 0.0
                )
                _MAX_DIR_OFFSET = 0.15   # v15.3 Bug X: raised from 0.07 (was capping true miscalibration)
                self._buy_prob_offset  = float(np.clip(_raw_buy,  -_MAX_DIR_OFFSET, _MAX_DIR_OFFSET))
                self._sell_prob_offset = float(np.clip(_raw_sell, -_MAX_DIR_OFFSET, _MAX_DIR_OFFSET))
                if abs(self._sell_prob_offset) > 0.005 or abs(self._buy_prob_offset) > 0.005:
                    self.logger.info(
                        f"🎯 [v15.3 Bug X] Direction calibration (val-set, cap=±0.15): "
                        f"BUY raw={_raw_buy:+.3f} → {self._buy_prob_offset:+.3f} "
                        f"SELL raw={_raw_sell:+.3f} → {self._sell_prob_offset:+.3f} "
                        f"(val BUY={int(_buy_mask_val.sum())} SELL={int(_sel_mask_val.sum())})"
                    )
            except Exception:
                self._buy_prob_offset  = 0.0
                self._sell_prob_offset = 0.0

            # Per-class accuracy (crucial for loss-prevention)
            win_acc  = float(np.mean(preds[y_flat == 1] == 1)) if wins  > 0 else 0.0
            loss_acc = float(np.mean(preds[y_flat == 0] == 0)) if losses > 0 else 0.0

            # ── Quality gate: only activate NN if it has learned BOTH classes ──
            # win_acc < 35% means the model predicts "LOSS" for nearly all wins
            # — it hasn't learned the winning pattern and would block every signal.
            # loss_acc < 35% means it predicts "WIN" for nearly all losses — no filter.
            # Both must be reasonable for the model to add value over the raw
            # confidence gate.  A minimum of 8 wins + 8 losses is also required
            # to ensure both classes are represented in training.
            # Raised win_acc gate 0.35 → 0.40: a model that only identifies 35% of
            # wins adds minimal filtering value above the raw confidence gate.
            quality_ok = (
                win_acc  >= 0.40
                and loss_acc >= 0.40
                and wins  >= 8
                and losses >= 8
            )
            self.trained           = quality_ok
            self.n_samples_trained = len(filtered_triples)  # after neutral filter
            self.last_train_time   = time.time()
            self.last_accuracy     = acc
            self.last_val_loss     = best_val
            self.last_win_rate     = wins  / n if n > 0 else 0.0
            self.last_loss_rate    = losses / n if n > 0 else 0.0
            if not quality_ok:
                self.logger.warning(
                    f"⚠️  NN quality gate FAILED — model disabled until quality improves: "
                    f"win_acc={win_acc:.1%} loss_acc={loss_acc:.1%} "
                    f"(need both ≥40%, wins={wins} losses={losses} need both ≥8)"
                )

            # ── Train loss-pattern analyzer on normalised dataset ──────────
            try:
                self.loss_analyzer.fit(X_all_norm, y_flat)
                n_danger = len(self.loss_analyzer.danger_zones)
                # Top-3 most important features for losses
                fi_sorted = sorted(enumerate(self.loss_analyzer.feature_importance),
                                   key=lambda x: x[1], reverse=True)[:3]
                fi_str = " ".join(f"F{i+1}={v:.2f}" for i, v in fi_sorted)
                self.logger.info(
                    f"🔍 Loss patterns: {n_danger} danger zones | "
                    f"top loss-predictors: {fi_str}"
                )
            except Exception as lpa_err:
                self.logger.debug(f"Loss pattern analysis failed: {lpa_err}")

            self._save_weights()

            # v11.0: Train PyTorch Transformer ensemble (non-blocking; MLP results unaffected)
            if _HAS_TORCH and self.trained and self._torch_predictor is not None:
                try:
                    self._torch_predictor.fit(X_all_norm, y_all)
                except Exception as _te:
                    self.logger.debug(f"Transformer training skipped: {_te}")

            # Sync BitNet optimizer with updated float weights after training
            if self._bitnet is not None and self.trained:
                try:
                    self._bitnet.load_from_trainer(self)
                    self.logger.debug("🔢 BitNet optimizer re-synced after training")
                except Exception:
                    pass

            elapsed = time.time() - t0
            self.logger.info(
                f"🧠 NN trained: {len(trades)} samples | {elapsed:.1f}s | "
                f"acc={acc:.1%} | win_acc={win_acc:.1%} | loss_acc={loss_acc:.1%} | "
                f"W/L={wins}/{losses} | class_w={self.class_weight_loss:.2f} | "
                f"best_val={best_val:.4f} | epochs={len(history)} | "
                f"thresh={self._opt_threshold:.3f}"
            )
            return {
                "status":           "trained",
                "samples":          len(trades),
                "accuracy":         acc,
                "win_acc":          win_acc,
                "loss_acc":         loss_acc,
                "val_loss":         best_val,
                "wins":             wins,
                "losses":           losses,
                "epochs_run":       len(history),
                "elapsed_s":        round(elapsed, 2),
                "danger_zones":     len(self.loss_analyzer.danger_zones),
                "class_weight":     self.class_weight_loss,
                "opt_threshold":    self._opt_threshold,
            }

        except Exception as e:
            self.logger.error(f"Training error: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    # ── Persistence ────────────────────────────────────────────────────────

    def _save_weights(self):
        """
        Atomically persist NN weights + training state to JSON.

        FIXED: Previously wrote directly to WEIGHTS_PATH, which left a truncated
        file if the process was interrupted mid-write (Python's json.dump does
        NOT guarantee atomic writes).  Truncated JSON caused JSONDecodeError on
        the next restart, leaving the bot permanently untrained until manually
        fixed.

        Fix: write to a temp file in the same directory then os.replace() which
        is atomic on all POSIX systems (rename is atomic).
        """
        if not _HAS_NUMPY:
            return
        try:
            # BUG FIX: danger_zones tuples and feature_importance contain NumPy
            # float32 values (from ndarray bin-edge slicing and abs-diff operations).
            # json.dump raises TypeError on numpy scalar types.  Explicitly convert
            # every value to Python-native float/int before serialising.
            data = {
                "W1": self.W1.tolist(), "b1": self.b1.tolist(),
                "W2": self.W2.tolist(), "b2": self.b2.tolist(),
                "W3": self.W3.tolist(), "b3": self.b3.tolist(),
                "W4": self.W4.tolist(), "b4": self.b4.tolist(),
                "n_samples_trained":   int(self.n_samples_trained),
                "last_train_time":     float(self.last_train_time),
                "last_accuracy":       float(self.last_accuracy),
                "last_val_loss":       float(self.last_val_loss),
                "last_win_rate":       float(self.last_win_rate),
                "last_loss_rate":      float(self.last_loss_rate),
                "_t":                  int(self._t),
                "_base_lr":            float(self._base_lr),
                "trained":             bool(self.trained),
                "class_weight_loss":   float(self.class_weight_loss),
                "_w_win":              float(self._w_win),
                "_w_loss":             float(self._w_loss),
                "_opt_threshold":      float(self._opt_threshold),
                "_reject_threshold":   float(self._reject_threshold),
                "_boost_threshold":    float(self._boost_threshold),
                "_buy_prob_offset":    float(self._buy_prob_offset),
                "_sell_prob_offset":   float(self._sell_prob_offset),
                "_feat_mean":  self._feat_mean.tolist()  if self._feat_mean  is not None else None,
                "_feat_std":   self._feat_std.tolist()   if self._feat_std   is not None else None,
                "_feat_fitted": bool(self._feat_fitted),
                # danger_zones: (feature_idx, lo, hi, loss_rate) — lo/hi are np.float32
                "danger_zones": [
                    [int(fi), float(lo), float(hi), float(lr)]
                    for fi, lo, hi, lr in self.loss_analyzer.danger_zones
                ],
                # feature_importance is a list of np.float32 from ndarray operations
                "feature_importance": [float(x) for x in self.loss_analyzer.feature_importance],
                "win_means":  self.loss_analyzer.win_means.tolist()  if self.loss_analyzer.win_means  is not None else None,
                "loss_means": self.loss_analyzer.loss_means.tolist() if self.loss_analyzer.loss_means is not None else None,
                "lpa_base_loss_rate": float(self.loss_analyzer._base_loss_rate),
                "input_dim": INPUT_DIM,  # stored to detect architecture upgrades on load
            }
            # Atomic write: dump to temp file, then rename (POSIX atomic)
            tmp_path = WEIGHTS_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f)
            os.replace(tmp_path, WEIGHTS_PATH)
            self.logger.debug(f"💾 NN weights saved → {WEIGHTS_PATH}")
        except Exception as e:
            self.logger.warning(f"Weight save failed: {e}")

    def _load_weights(self):
        if not _HAS_NUMPY or not os.path.exists(WEIGHTS_PATH):
            return
        try:
            with open(WEIGHTS_PATH) as f:
                d = json.load(f)

            # Early exit if saved weights used a different INPUT_DIM (architecture upgrade)
            saved_input_dim = d.get("input_dim")
            if saved_input_dim is not None and int(saved_input_dim) != INPUT_DIM:
                self.logger.info(
                    f"ℹ️  NN architecture upgraded (input_dim {saved_input_dim}→{INPUT_DIM}) — "
                    f"discarding old weights, starting fresh"
                )
                return

            w1 = np.array(d["W1"], dtype=np.float32)
            b1 = np.array(d["b1"], dtype=np.float32)
            w2 = np.array(d["W2"], dtype=np.float32)
            b2 = np.array(d["b2"], dtype=np.float32)
            w3 = np.array(d["W3"], dtype=np.float32)
            b3 = np.array(d["b3"], dtype=np.float32)
            w4 = np.array(d.get("W4", []), dtype=np.float32)
            b4 = np.array(d.get("b4", []), dtype=np.float32)

            expected = {
                "W1": (INPUT_DIM, 128), "b1": (1, 128),
                "W2": (128, 64),        "b2": (1, 64),
                "W3": (64, 32),         "b3": (1, 32),
                "W4": (32, 1),          "b4": (1, 1),
            }
            actual = {
                "W1": w1.shape, "b1": b1.shape,
                "W2": w2.shape, "b2": b2.shape,
                "W3": w3.shape, "b3": b3.shape,
                "W4": w4.shape, "b4": b4.shape,
            }
            mismatches = [k for k, exp in expected.items() if actual[k] != exp]
            if mismatches:
                self.logger.info(
                    f"ℹ️  NN weights shape mismatch (architecture upgraded) — "
                    f"starting fresh: {mismatches}"
                )
                return

            self.W1 = w1; self.b1 = b1
            self.W2 = w2; self.b2 = b2
            self.W3 = w3; self.b3 = b3
            self.W4 = w4; self.b4 = b4
            self.n_samples_trained = int(d.get("n_samples_trained", 0))
            self.last_train_time   = float(d.get("last_train_time",  0))
            self.last_accuracy     = float(d.get("last_accuracy",    0))
            self.last_val_loss     = float(d.get("last_val_loss",   99))
            self.last_win_rate     = float(d.get("last_win_rate",    0))
            self.last_loss_rate    = float(d.get("last_loss_rate",   0))
            self._t                = int(d.get("_t", 0))

            # FIX 1: Restore base LR so cosine schedule works correctly on reload
            self._base_lr = float(d.get("_base_lr", self._base_lr))

            # Restore dynamic class weight + dual per-class weights
            # v9.5: cap raised 2.0 → 3.0 to match the current train() ceiling
            # (was inconsistent: training allowed 3.0, load clamped to 2.0 → after
            # any restart the restored model used WEAKER class weighting than the
            # freshly-trained one, undoing the loss-learning correction).
            _MAX_CW = 3.0
            self.class_weight_loss = float(d.get("class_weight_loss", self._default_class_weight_loss))
            self._w_win  = float(min(_MAX_CW, d.get("_w_win",  1.0)))
            self._w_loss = float(min(_MAX_CW, d.get("_w_loss", self.class_weight_loss)))

            # FIX 5v2: Restore optimal thresholds.
            # Apply 0.38 floor (raised from 0.35) so old saved weights don't restore
            # a too-permissive reject threshold.  Saved values from older training runs
            # may have been 0.08–0.37 — enforce the current production floor (matches
            # the 0.38 hard floor in _compute_optimal_threshold and __init__).
            self._opt_threshold    = float(d.get("_opt_threshold",    0.50))
            self._reject_threshold = max(0.38, float(d.get("_reject_threshold", 0.38)))
            self._boost_threshold  = float(d.get("_boost_threshold",  0.70))

            # Restore direction-aware calibration offsets
            self._buy_prob_offset  = float(d.get("_buy_prob_offset",  0.0))
            self._sell_prob_offset = float(d.get("_sell_prob_offset", 0.0))

            # FIX 4: Restore normalisation statistics
            if d.get("_feat_mean") is not None:
                self._feat_mean = np.array(d["_feat_mean"], dtype=np.float32)
            if d.get("_feat_std") is not None:
                self._feat_std  = np.array(d["_feat_std"],  dtype=np.float32)
            self._feat_fitted = bool(d.get("_feat_fitted", False))

            # Re-init Adam moments
            self._m = [np.zeros_like(p) for p in self._params()]
            self._v = [np.zeros_like(p) for p in self._params()]

            # Restore loss analyzer
            if d.get("danger_zones"):
                self.loss_analyzer.danger_zones = [
                    tuple(z) for z in d["danger_zones"]
                ]
                self.loss_analyzer.feature_importance = d.get(
                    "feature_importance", [1.0] * INPUT_DIM
                )
                if d.get("win_means"):
                    self.loss_analyzer.win_means  = np.array(d["win_means"],  np.float32)
                if d.get("loss_means"):
                    self.loss_analyzer.loss_means = np.array(d["loss_means"], np.float32)
                # Restore stored base loss rate (avoids negative penalties on reload)
                self.loss_analyzer._base_loss_rate = float(
                    d.get("lpa_base_loss_rate", 0.50)
                )
                self.loss_analyzer.is_fitted = True

            # Restore the quality-gated trained flag.
            # The saved 'trained' key reflects whether the quality gate passed
            # at save time (win_acc ≥ 35% AND loss_acc ≥ 35%).
            # Fall back to n_samples check for older weight files that lack the key.
            saved_trained = d.get("trained")
            if saved_trained is not None:
                self.trained = bool(saved_trained)
            else:
                self.trained = self.n_samples_trained >= MIN_TRAIN_SAMPLES
            if self.trained:
                self.logger.info(
                    f"🧠 NN weights loaded | {self.n_samples_trained} samples | "
                    f"acc={self.last_accuracy:.1%} | win_rate={self.last_win_rate:.1%} | "
                    f"thresh={self._opt_threshold:.3f} | "
                    f"w_win={self._w_win:.2f}x w_loss={self._w_loss:.2f}x | "
                    f"danger_zones={len(self.loss_analyzer.danger_zones)}"
                )
                # Sync BitNet optimizer with freshly restored float weights
                if self._bitnet is not None:
                    try:
                        self._bitnet.load_from_trainer(self)
                    except Exception:
                        pass
            else:
                self.logger.info(
                    f"🧠 NN weights loaded but quality gate not met — "
                    f"acc={self.last_accuracy:.1%} win_rate={self.last_win_rate:.1%} | "
                    f"retraining needed"
                )
        except Exception as e:
            self.logger.warning(f"Weight load failed: {e} — starting fresh")

    def status_summary(self) -> str:
        if not _HAS_NUMPY:
            return "NN: disabled (numpy missing)"
        if not self.trained:
            return f"NN: warming up (need {MIN_TRAIN_SAMPLES} labeled trades)"
        age_h   = (time.time() - self.last_train_time) / 3600
        dz      = len(self.loss_analyzer.danger_zones)
        win_acc = getattr(self, "last_win_rate", 0.0)

        bitnet_str = ""
        if self._bitnet is not None and self._bitnet.is_ready:
            s = self._bitnet.get_stats()
            avg_sp = sum(s["sparsity"].values()) / max(1, len(s["sparsity"]))
            bitnet_str = f" | BitNet=ternary(sparsity={avg_sp:.0%})"

        return (
            f"NN: trained | {self.n_samples_trained} samples | "
            f"acc={self.last_accuracy:.1%} | "
            f"W/L split={win_acc:.1%}/{1.0-win_acc:.1%} | "
            f"w_win={self._w_win:.2f}x w_loss={self._w_loss:.2f}x | "
            f"thresh={self._opt_threshold:.3f} | "
            f"danger_zones={dz} | "
            f"last trained {age_h:.1f}h ago"
            + bitnet_str
        )

    def update_online(self, trade: Dict, n_steps: int = 5,
                      lr_scale: float = 0.1) -> bool:
        """
        Online (incremental) learning from a single resolved trade.

        Runs n_steps of gradient descent on this one sample using a fraction
        (lr_scale) of the base learning rate so it refines the model without
        catastrophically forgetting the previous batch training.

        Only active when the model is already trained (has a valid normaliser).
        Returns True on success, False if skipped or on error.

        This is called immediately after OutcomeTracker resolves each trade,
        providing continuous real-time learning between full batch retrains.
        """
        if not _HAS_NUMPY or not self.trained or not self._feat_fitted:
            return False
        try:
            label = build_label(trade)
            if label < 0.0:
                # Neutral EXPIRED trade — no reliable label, skip online update
                return False
            X_raw = build_features(trade).reshape(1, -1)
            X_norm = self._normalise(X_raw)
            y = np.array([[label]], dtype=np.float32)

            # Use a small fraction of base_lr for online updates to prevent
            # catastrophic forgetting of prior batch-trained knowledge.
            orig_lr = self.lr
            self.lr = self._base_lr * lr_scale

            for _ in range(n_steps):
                Z1, A1, mask1, Z2, A2, mask2, Z3, A3, Z4, A4 = self._forward(
                    X_norm, training=True, dropout=0.10  # light dropout for online
                )

                _eps = 1e-7
                γ = self.focal_gamma
                p = np.clip(A4, _eps, 1.0 - _eps)
                p_t = np.where(y == 1, p, 1.0 - p)
                wt = np.where(y == 1, self._w_win, self._w_loss)
                focal_w = (1.0 - p_t) ** γ  # precomputed — reused below to avoid redundant pow
                d_pt_dp = np.where(y == 1, 1.0, -1.0)
                grad_p = wt * (
                    γ * (1.0 - p_t) ** (γ - 1) * np.log(p_t + _eps)
                    - focal_w / (p_t + _eps)              # BUG FIX: was re-computing (1-p_t)^γ inline
                ) * d_pt_dp
                # m=1 for single sample — no /m needed since dZ4 carries 1/1
                dZ4 = grad_p * A4 * (1.0 - A4)

                dW4 = (A3.T @ dZ4) + self.l2 * self.W4
                db4 = dZ4.sum(axis=0, keepdims=True)

                dA3 = dZ4 @ self.W4.T
                dZ3 = dA3 * self._relu_d(Z3)
                dW3 = (A2.T @ dZ3) + self.l2 * self.W3
                db3 = dZ3.sum(axis=0, keepdims=True)

                dA2 = dZ3 @ self.W3.T
                if mask2 is not None:
                    dA2 = dA2 * mask2
                dZ2 = dA2 * self._relu_d(Z2)
                dW2 = (A1.T @ dZ2) + self.l2 * self.W2
                db2 = dZ2.sum(axis=0, keepdims=True)

                dA1 = dZ2 @ self.W2.T
                if mask1 is not None:
                    dA1 = dA1 * mask1
                dZ1 = dA1 * self._relu_d(Z1)
                dW1 = (X_norm.T @ dZ1) + self.l2 * self.W1
                db1 = dZ1.sum(axis=0, keepdims=True)

                self._adam_step([dW1, db1, dW2, db2, dW3, db3, dW4, db4])

            self.lr = orig_lr

            if self.loss_analyzer and self.loss_analyzer.is_fitted:
                try:
                    self.loss_analyzer.update_incremental(X_norm[0], label)
                except Exception:
                    pass

            outcome_label = "WIN" if label == 1.0 else "LOSS"
            self.logger.debug(
                f"🧠 Online update: {trade.get('symbol','?')} {trade.get('action','?')} "
                f"→ {outcome_label} | {n_steps} steps lr×{lr_scale}"
            )
            return True
        except Exception as e:
            self.logger.debug(f"online_update error: {e}")
            return False
