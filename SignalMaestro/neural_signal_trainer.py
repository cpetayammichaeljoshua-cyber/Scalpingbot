#!/usr/bin/env python3
"""
NeuralSignalTrainer — Self-learning signal quality filter for MiroFish Swarm.

Architecture  : 60-feature input → Dense(128, ReLU) → Dense(64, ReLU)
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

# Transformer tokenisation: reshape 130 features → 26 tokens × 5 dims (130 = 26 × 5) [v87.0: was 25×5=125]
_TORCH_N_TOKENS  = 29
_TORCH_TOKEN_DIM = 5   # INPUT_DIM // _TORCH_N_TOKENS  (v17: 100 = 20×5; v85.0: 125 = 25×5; v87.0: 130 = 26×5; v88.0: 135 = 27×5; v89.0: 140 = 28×5; v90.0: 145 = 29×5)
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
GEX_FEATURE_COUNT  = 5  # v9 (GEX): BTC GEX regime/conf/net/flip-count/proximity — institutional dealer positioning
INPUT_DIM          = 150  # v27 (v91.0): 145 + 5 HMM/VPIN features (hmm_expansion_prob, vpin_pct_norm, hmm_vpin_coherence, hmm_regime_norm, vpin_toxic_norm) = 150

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


def _extract_gex_features(trade: Dict) -> List[float]:
    """
    v9: 5 Deribit GEX regime features (56-60) from BTC GEX snapshot context.
    Returns zeros when gex data is absent (legacy trades, cold-start).  All
    five features are bounded to [-1, +1] or [0, 1] for well-conditioned
    gradient flow.  Stamped onto signal dicts by Unity Engine before NN inference.

    F56 — BTC GEX regime encoded: NEGATIVE=-1  FLIP ZONE=0  POSITIVE=+1
    F57 — BTC GEX confidence [0, 1]   (Deribit confidence score / 100)
    F58 — BTC net GEX log-scaled [-1,+1]  sign×log1p(|net|/1000)/7
           reaches ±1 at ~$7B net GEX (beyond observed extremes)
    F59 — Multi-asset FLIP count [0, 1]  (BTC+ETH+SOL flip count / 3)
           0.0=no FLIP, 0.33=BTC alone, 0.67=2/3, 1.0=all three
    F60 — Spot-to-flip proximity [-1,+1]  (spot−flip)/spot × 20, capped ±1
           >0 = spot above flip level (dealer long gamma)
           <0 = spot below flip level (dealer short gamma)
    """
    try:
        regime = str(trade.get("gex_btc_regime", "") or "").upper()
        if "POSITIVE" in regime:    regime_enc = 1.0
        elif "NEGATIVE" in regime:  regime_enc = -1.0
        else:                        regime_enc = 0.0   # FLIP ZONE or unknown → neutral
        conf    = min(1.0, float(trade.get("gex_btc_conf", 0.0) or 0.0) / 100.0)
        net     = float(trade.get("gex_btc_net", 0.0) or 0.0)
        net_enc = (math.copysign(math.log1p(abs(net) / 1_000.0) / 7.0, net)
                   if net != 0.0 else 0.0)
        net_enc = max(-1.0, min(1.0, net_enc))
        flip_cnt = min(1.0, float(trade.get("gex_flip_count", 0) or 0) / 3.0)
        flip_px  = float(trade.get("gex_btc_flip_price", 0.0) or 0.0)
        entry_px = float(trade.get("entry_price_for_gex", 0.0) or
                         trade.get("entry_price", 0.0) or 0.0)
        if flip_px > 0.0 and entry_px > 0.0:
            prox = max(-1.0, min(1.0, (entry_px - flip_px) / entry_px * 20.0))
        else:
            prox = 0.0
        return [regime_enc, conf, net_enc, flip_cnt, prox]
    except Exception:
        return [0.0, 0.0, 0.0, 0.0, 0.0]


def build_features(trade: Dict) -> "np.ndarray":
    """
    70-feature normalised vector from a trade record dict (v11 — full quant feature set + GEX + microstructure).

    v3 change: 8 sequential lag price-return features appended (43-50) to give
    the MLP short-term temporal/momentum context without an LSTM. INPUT_DIM 42→50.

    v4 change: 1 real-time order-flow imbalance feature appended (51) — derived
    from Binance @depth5@100ms WS stream — institutional-grade microstructure
    alpha. INPUT_DIM 50→51.

    v5 change: 7-predictor price consensus feature appended (52). INPUT_DIM 51→52.
    v6 change: Hurst fractal regime signal appended (53). INPUT_DIM 52→53.
    v7 change: EWMA-Vol regime signal appended (54). INPUT_DIM 53→54.
    v8 change: Realized-Skewness signal appended (55). INPUT_DIM 54→55.
    v9 change: 5 Deribit GEX regime features appended (56-60). INPUT_DIM 55→60.
              Transformer retokenized: 11×5 → 12×5 (12 tokens, 5 dims each = 60).
              Backwards compatible: legacy trades without gex_data → zero padding.
    v10 change: 5 regime-awareness features appended (61-65). INPUT_DIM 60→65.
              Transformer retokenized: 12×5 → 13×5 (13 tokens, 5 dims each = 65).
    v11 change: 5 microstructure features appended (66-70). INPUT_DIM 65→70. [v49.0]
              Transformer retokenized: 13×5 → 14×5 (14 tokens, 5 dims each = 70).
              F66=funding_extreme, F67=ofi_aligned, F68=liq_cascade_dir,
              F69=momentum_aligned, F70=vol_spike_flag.
              Backwards compatible: missing fields → zero padding (benign during training).

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

    # F36: Consensus cubed [0, 1] — v18.79: capped at 0.90 pre-cube
    # Was top loss-predictor (importance=0.19) → overfit signal from tiny consensus
    # differences near 1.0. Cap consensus at 0.90 before cubing to reduce overfit:
    # uncapped: 0.95^3=0.857, 0.90^3=0.729; capped: both map to 0.729 (stable)
    consensus_cubed = min(consensus, 0.90) ** 3

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

    # ── v9 Deribit GEX regime features (56-60) — institutional dealer positioning ─
    # Five macro-structure features derived from Deribit GEX snapshot stamped at
    # signal time by Unity Engine.  Captures the dominant dealer gamma regime
    # (FLIP/POSITIVE/NEGATIVE), confidence strength, log-scaled net GEX (dealer
    # directional positioning magnitude), multi-asset FLIP coordination (0=isolated,
    # 1=all BTC+ETH+SOL simultaneously), and spot-to-gamma-flip proximity.
    # The MLP learns regime-conditional win-prob: e.g. "BUY signals when all three
    # macro assets are in FLIP ZONE have measurably lower WR — penalise accordingly".
    # Backwards compatible: legacy trade records without gex_data → zeros (benign).
    f.extend(_extract_gex_features(trade))                              # 56-60

    # ── v10 Regime-awareness features (61-65) — v43.0 direction + quality context ─
    # Five compact features giving the MLP direct regime-alignment and quality context.
    # All derived from fields already stored in every trade record — backwards compatible.
    # F61: Fear & Greed direction alignment: +1=aligned(SELL in fear/BUY in greed),
    #       -1=opposed(BUY in fear/SELL in greed), 0=neutral F&G zone (30-70).
    # F62: IRONS quality score normalized: irons_score/100 ∈ [0, 1].
    # F63: Fear & Greed normalized: (fg - 50) / 50 ∈ [-1, +1]. Negative=fear, positive=greed.
    # F64: Prime session flag: 1.0 if 15-21h UTC (London/NY overlap), 0.0 otherwise.
    # F65: Volatility crisis flag: +1=extreme fear(fg<25), -1=extreme greed(fg>75), 0=neutral.
    _fg65    = _safe_float(trade.get("fear_greed_index"), 50.0)
    _dir65   = 1.0 if trade.get("action", "BUY") == "BUY" else -1.0
    _irons65 = _safe_float(trade.get("irons_score", trade.get("irons_score_precomputed", 60.0)), 60.0)
    _hour65  = _safe_float(trade.get("hour_of_day"), 12.0)
    # F61 — fg_dir_align
    if (_fg65 < 30.0 and _dir65 < 0) or (_fg65 > 70.0 and _dir65 > 0):
        _fg_dir_align65 = 1.0     # regime-aligned direction
    elif (_fg65 < 30.0 and _dir65 > 0) or (_fg65 > 70.0 and _dir65 < 0):
        _fg_dir_align65 = -1.0    # regime-opposed direction
    else:
        _fg_dir_align65 = 0.0     # neutral F&G zone (30-70)
    f.append(_fg_dir_align65)                                                   # 61 fg_dir_align
    f.append(min(1.0, max(0.0, _irons65 / 100.0)))                             # 62 irons_norm
    f.append(max(-1.0, min(1.0, (_fg65 - 50.0) / 50.0)))                       # 63 fg_norm
    f.append(1.0 if 15 <= int(_hour65) < 21 else 0.0)                          # 64 session_prime
    if _fg65 < 25.0:
        f.append(1.0)                                                           # 65 vol_crisis=extreme_fear
    elif _fg65 > 75.0:
        f.append(-1.0)                                                          # 65 vol_crisis=extreme_greed
    else:
        f.append(0.0)                                                           # 65 vol_crisis=neutral

    # ── v11 Microstructure features (66-70) — v49.0 funding+OFI+liq+momentum+vol ─
    # Five additional microstructure features for the NN to learn live market regime.
    # All derived from fields already stamped into every trade record by the engine.
    # Backwards compatible: missing fields → zero padding (benign during training).
    # F66: Funding rate extreme directional signal
    #       SuperExtreme (|fr|≥0.10%/8h): ±1.0 aligned-to-squeeze direction
    #       Extreme      (|fr|≥0.05%/8h): ±0.5
    #       else: 0.0
    # F67: OFI (order-flow imbalance) aligned to signal direction ∈ [-1, +1]
    # F68: Liquidation cascade direction: SHORT_LIQ=+1 (bullish), LONG_LIQ=-1 (bearish), 0=neutral
    # F69: Aggregate 8-bar momentum aligned to signal direction, tanh-compressed ∈ [-1, +1]
    # F70: Volume spike flag: +1=surge (>1.8×avg), -1=drought (<0.55×avg), 0=normal
    _v11_dir = 1.0 if trade.get("action", "BUY") == "BUY" else -1.0
    # F66 — funding_extreme
    _v11_fr  = _safe_float(trade.get("funding_rate", 0.0), 0.0)
    if abs(_v11_fr) >= 0.0010:
        _v11_f66 = 1.0 if ((_v11_fr > 0 and _v11_dir < 0) or (_v11_fr < 0 and _v11_dir > 0)) else -1.0
    elif abs(_v11_fr) >= 0.0005:
        _v11_f66 = 0.5 if ((_v11_fr > 0 and _v11_dir < 0) or (_v11_fr < 0 and _v11_dir > 0)) else -0.5
    else:
        _v11_f66 = 0.0
    f.append(_v11_f66)                                                          # 66 funding_extreme
    # F67 — ofi_aligned
    _v11_ofi = _safe_float(trade.get("ofi", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v11_ofi * _v11_dir)))                         # 67 ofi_aligned
    # F68 — liq_cascade_dir
    _v11_liqside = str(trade.get("liq_net_side", "") or "").upper()
    if _v11_liqside == "SHORT":
        f.append(1.0)                                                           # 68 short-liq cascade = bullish
    elif _v11_liqside == "LONG":
        f.append(-1.0)                                                          # 68 long-liq cascade = bearish
    else:
        f.append(0.0)                                                           # 68 neutral / unknown
    # F69 — momentum_aligned (aggregate 8-bar return × direction, tanh-compressed)
    _v11_rets = trade.get("price_returns", [])
    if isinstance(_v11_rets, (list, tuple)) and len(_v11_rets) >= 4:
        _v11_mom = sum(float(r) for r in _v11_rets[:8]) * _v11_dir
        f.append(max(-1.0, min(1.0, math.tanh(_v11_mom * 200.0))))             # 69 momentum_aligned
    else:
        f.append(0.0)                                                           # 69 no data → neutral
    # F70 — vol_spike_flag
    _v11_vr = _safe_float(trade.get("volume_ratio", 1.0), 1.0)
    if _v11_vr > 1.8:
        f.append(1.0)                                                           # 70 volume surge
    elif _v11_vr < 0.55:
        f.append(-1.0)                                                          # 70 volume drought
    else:
        f.append(0.0)                                                           # 70 normal volume

    # ── v12 Regime/Crowding features (71-75) — v68.0 ─────────────────────────
    # F71: funding_trend — net direction of 3-reading funding rate delta
    #   +1.0 = funding escalating in UNFAVORABLE direction for signal (crowding warning)
    #   -1.0 = funding trending toward 0 / de-crowding (relief signal)
    #    0.0 = no significant trend or neutral
    _v12_dir = 1.0 if trade.get("action", "BUY") == "BUY" else -1.0
    _v12_fr_trend = _safe_float(trade.get("funding_rate_trend", 0.0), 0.0)
    # fr_trend = net funding delta sign × direction: +1 = bad trend, -1 = favorable trend
    if abs(_v12_fr_trend) > 0.00015:
        _v12_f71 = 1.0 if (_v12_fr_trend > 0 and _v12_dir > 0) or (_v12_fr_trend < 0 and _v12_dir < 0) else -1.0
    else:
        _v12_f71 = 0.0
    f.append(_v12_f71)                                                          # 71 funding_trend

    # F72: btc_atr_spike — BTC ATR relative to 20-bar mean
    #   +1.0 = BTC ATR spike (ATR > 2× mean) → elevated cross-asset vol risk for alts
    #    0.0 = normal ATR environment
    _v12_btc_atr_spike = _safe_float(trade.get("btc_atr_spike", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v12_btc_atr_spike)))                           # 72 btc_atr_spike

    # F73: corr_regime_flag — BTC-ALT rolling correlation regime
    #   +1.0 = high correlation regime (BTC/ALT corr > 0.88) → macro-dominated
    #    0.0 = normal / low correlation
    _v12_corr = _safe_float(trade.get("corr_regime_flag", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v12_corr)))                                    # 73 corr_regime_flag

    # F74: dgrp_vel_norm — normalized DGRP velocity (raw velocity / 10, clipped ±1)
    #   +1.0 = rapidly improving dealer gamma regime (bullish)
    #   -1.0 = rapidly deteriorating dealer gamma regime (bearish)
    _v12_dgrp_vel = _safe_float(trade.get("dgrp_velocity", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v12_dgrp_vel / 10.0)))                        # 74 dgrp_vel_norm

    # F75: vol_compress_flag — ATR at historical low-percentile (pre-breakout compression)
    #   +1.0 = ATR ≤ 25th percentile (compressed, pre-breakout condition)
    #    0.0 = normal or expanding vol
    _v12_vc = _safe_float(trade.get("vol_compress_flag", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v12_vc)))                                      # 75 vol_compress_flag

    # ── v13 Microstructure/Regime features (76-80) — v72.0 ─────────────────────
    # F76: ofi_persistence_score — rolling 3-cycle OFI direction agreement
    #   +1.0 = 3/3 OFI readings aligned with trade direction (strong persistent flow confirm)
    #   -1.0 = 0/3 OFI readings aligned (persistent adverse flow headwind)
    #    0.0 = mixed / insufficient data
    _v13_ofi_persist = _safe_float(trade.get("ofi_persistence_score", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v13_ofi_persist)))                            # 76 ofi_persistence_score

    # F77: regime_coherence_score — HMM + GEX dual-confirm alignment
    #   +1.0 = EXPANSION + GEX bullish both aligned with direction (institutional confirmation)
    #   -1.0 = CONTRACTION + GEX bearish both against direction (institutional headwind)
    #    0.0 = mixed or neutral regime confirmation
    _v13_reg_coh = _safe_float(trade.get("regime_coherence_score", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v13_reg_coh)))                                # 77 regime_coherence_score

    # F78: vol_expansion_flag — recent 7-bar realized vol expanding vs 30-bar baseline
    #   +1.0 = 7-bar realized vol > 1.5× 30-bar baseline (expanding vol regime — noise up)
    #    0.0 = normal or compressing vol (stable microstructure)
    _v13_vol_exp = _safe_float(trade.get("vol_expansion_flag", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v13_vol_exp)))                                 # 78 vol_expansion_flag

    # F79: hmm_expansion_prob_norm — HMM P(EXPANSION) normalized to [-1, +1]
    #   +1.0 = strong EXPANSION regime (P_exp→1.0)
    #   -1.0 = strong CONTRACTION regime (P_exp→0.0)
    #    0.0 = TRANSITION / uncertain (P_exp≈0.5)
    _v13_hmm_p = _safe_float(trade.get("hmm_expansion_prob", 0.5), 0.5)
    f.append(max(-1.0, min(1.0, (_v13_hmm_p - 0.5) * 2.0)))                   # 79 hmm_expansion_prob_norm

    # F80: spread_regime_flag — bid-ask spread elevated above 2× rolling 20-bar median
    #   +1.0 = spread > 2× 20-bar median (high spread / illiquid / execution-cost risk)
    #    0.0 = normal spread environment (execution costs within expected range)
    _v13_spr = _safe_float(trade.get("spread_regime_flag", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v13_spr)))                                     # 80 spread_regime_flag

    # ── v14 Timing/Microstructure features (81-85) — v76.0 ──────────────────
    # F81: avwap_dist_norm — Anchored VWAP extension normalized to [-1, +1]
    #   +1.0 = price strongly extended above VWAP (≥100bps premium; momentum territory)
    #   -1.0 = price strongly extended below VWAP (≥100bps discount; oversold territory)
    #    0.0 = price at or near VWAP anchor (equilibrium / mean-reversion zone)
    #   Source: avwap_dist_bps from _timing_state.avwap_distance_bps() [v76.0]
    _v14_avwap = _safe_float(trade.get("avwap_dist_bps", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v14_avwap / 100.0)))                         # 81 avwap_dist_norm

    # F82: cusum_flag — de Prado symmetric CUSUM event active binary (0/1)
    #   1.0 = CUSUM regime-shift event is live within TTL window (statistical breakout)
    #   0.0 = no active CUSUM event (stable regime, no detected volatility shift)
    #   Source: cusum_active / cusum_flag from _timing_state [v76.0]
    _v14_cusum_raw = trade.get("cusum_flag") or trade.get("cusum_active")
    if _v14_cusum_raw is None:
        _v14_cusum = 0.0
    elif isinstance(_v14_cusum_raw, bool):
        _v14_cusum = 1.0 if _v14_cusum_raw else 0.0
    else:
        _v14_cusum = max(0.0, min(1.0, _safe_float(_v14_cusum_raw, 0.0)))
    f.append(_v14_cusum)                                                        # 82 cusum_flag

    # F83: depth_slip_norm — execution slippage cost pressure normalized to [0, 1]
    #   1.0 = severe execution cost (≥3bps round-trip; wide spread / illiquid market)
    #   0.0 = minimal slippage (tight, liquid market — execution at quoted prices)
    #   Reference: 3bps round-trip (0.003 raw) = 100th percentile / max reference [v76.0]
    _v14_dslip = _safe_float(trade.get("depth_slip_norm", 0.0), 0.0)
    if abs(_v14_dslip) < 1e-9:
        # fallback: compute from raw depth_slip_rt if norm not stamped
        _v14_dslip_raw = _safe_float(trade.get("depth_slip_rt", 0.0), 0.0)
        _v14_dslip = max(0.0, min(1.0, _v14_dslip_raw / 0.003))
    f.append(max(0.0, min(1.0, _v14_dslip)))                                  # 83 depth_slip_norm

    # F84: mark_div_norm — mark-price premium/discount normalized to [-1, +1]
    #   +1.0 = strong premium (mark significantly above index, ≥50bps; funding pressure)
    #   -1.0 = strong discount (mark significantly below index, ≤-50bps; funding relief)
    #    0.0 = mark ≈ index price (fair value; no significant premium or discount)
    #   Source: mark_divergence_bps from MarketStateSnapshot [v76.0]
    _v14_mdiv = _safe_float(trade.get("mark_div_norm", 0.0), 0.0)
    if abs(_v14_mdiv) < 1e-9:
        # fallback: compute from raw mark_divergence_bps if norm not stamped
        _v14_mdiv_raw = _safe_float(trade.get("mark_divergence_bps", 0.0), 0.0)
        _v14_mdiv = max(-1.0, min(1.0, _v14_mdiv_raw / 50.0))
    f.append(max(-1.0, min(1.0, _v14_mdiv)))                                  # 84 mark_div_norm

    # F85: ob_imbalance_norm — orderbook bid/ask pressure centered on 0 [-1, +1]
    #   +1.0 = pure bid-side pressure (ob_imbalance→1.0; strong buying demand)
    #   -1.0 = pure ask-side pressure (ob_imbalance→0.0; strong selling pressure)
    #    0.0 = balanced orderbook (ob_imbalance=0.5; no directional pressure signal)
    #   Source: ob_imbalance from MarketStateSnapshot (bid_vol / total_vol) [v76.0]
    _v14_obimb = _safe_float(trade.get("ob_imbalance_norm", 0.0), 0.0)
    if abs(_v14_obimb) < 1e-9:
        # fallback: compute from raw ob_imbalance if norm not stamped
        _v14_obimb_raw = _safe_float(trade.get("ob_imbalance", 0.5), 0.5)
        _v14_obimb = max(-1.0, min(1.0, (_v14_obimb_raw - 0.5) * 2.0))
    f.append(max(-1.0, min(1.0, _v14_obimb)))                                 # 85 ob_imbalance_norm

    # ── v15 Flow/Microtrend features (86-90) — v77.0 ─────────────────────────
    # F86: ofi_flow_asym_norm — OFI z-score × OB imbalance cross-product [-1, +1]
    #   Cross-product of two orthogonal flow signals: positive = dual buy-side confirm,
    #   negative = dual sell-side confirm, near-zero = divergent/neutral flow.
    #   Source: ofi_flow_asym_norm injected at G4 F86-F90 stamping block [v77.0]
    _v15_f86 = _safe_float(trade.get("ofi_flow_asym_norm", 0.0), 0.0)
    if abs(_v15_f86) < 1e-9:
        # fallback: recompute from raw components if available
        try:
            _v15_ofi_z    = _safe_float(trade.get("ofi_zscore", 0.0), 0.0)
            _v15_obimb_ctr = _safe_float(trade.get("ob_imbalance", 0.5), 0.5) - 0.5
            _v15_f86 = max(-1.0, min(1.0, _v15_ofi_z * _v15_obimb_ctr * 2.0))
        except Exception:
            _v15_f86 = 0.0
    f.append(max(-1.0, min(1.0, _v15_f86)))                                   # 86 ofi_flow_asym_norm

    # F87: microtrend_slope_norm — 10-bar close linear regression slope [-1, +1]
    #   Positive = price trending up over last 10 minutes (buy-side microtrend)
    #   Negative = price trending down (sell-side microtrend)
    #   Source: microtrend_slope_norm injected at G4 F86-F90 stamping block [v77.0]
    _v15_f87 = _safe_float(trade.get("microtrend_slope_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v15_f87)))                                   # 87 microtrend_slope_norm

    # F88: funding_velocity_norm — funding rate delta between last 2 readings [-1, +1]
    #   Positive = funding rate accelerating upward (crowd getting more long)
    #   Negative = funding rate decelerating/going negative (crowd turning short)
    #   Source: funding_velocity_norm injected at G4 F86-F90 stamping block [v77.0]
    _v15_f88 = _safe_float(trade.get("funding_velocity_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v15_f88)))                                   # 88 funding_velocity_norm

    # F89: spread_ratio_norm — bid-ask spread relative to 20-bar median [-1, +1]
    #   Positive = spread elevated above median (illiquid regime, higher slippage risk)
    #   Near-zero = spread at median baseline (normal liquidity)
    #   Source: spread_ratio_norm injected at G4 F86-F90 stamping block [v77.0]
    _v15_f89 = _safe_float(trade.get("spread_ratio_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v15_f89)))                                   # 89 spread_ratio_norm

    # F90: liq_intensity_norm — recent liquidation cascade total notional [0, +1]
    #   Higher values = more recent forced liquidations (elevated cascade risk)
    #   0.0 = no recent liquidations; 1.0 = ≥$500k notional cascaded recently
    #   Source: liq_intensity_norm injected at G4 F86-F90 stamping block [v77.0]
    _v15_f90 = _safe_float(trade.get("liq_intensity_norm", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v15_f90)))                                    # 90 liq_intensity_norm

    # ── v16 Cross-signal coherence features (91-95) — v79.0 ──────────────────
    # F91: ofi_hmm_cross — OFI z-score × HMM regime alignment [-1, +1]
    #   Positive = OFI aligned with HMM expanding/trending regime (dual confirm)
    #   Negative = OFI diverges from HMM regime (conflicting signals)
    #   Source: ofi_hmm_cross injected at G4 F91-F95 stamping block [v79.0]
    _v16_f91 = _safe_float(trade.get("ofi_hmm_cross", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v16_f91)))                                   # 91 ofi_hmm_cross

    # F92: vwap_micro_align — VWAP extension × microtrend slope alignment [-1, +1]
    #   Positive = price above VWAP and microtrend confirms (bullish dual-confirm)
    #   Negative = price below VWAP and microtrend confirms (bearish dual-confirm)
    #   Source: vwap_micro_align injected at G4 F91-F95 stamping block [v79.0]
    _v16_f92 = _safe_float(trade.get("vwap_micro_align", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v16_f92)))                                   # 92 vwap_micro_align

    # F93: funding_ofi_cross — funding rate × OFI flow cross-product [-1, +1]
    #   Positive = funding and OFI both pointing same directional pressure
    #   Negative = funding and OFI divergent (regime conflict signal)
    #   Source: funding_ofi_cross injected at G4 F91-F95 stamping block [v79.0]
    _v16_f93 = _safe_float(trade.get("funding_ofi_cross", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v16_f93)))                                   # 93 funding_ofi_cross

    # F94: regime_3gate_vote — normalized vote count from G8.5C/G8.5R/G8.5U [-1, +1]
    #   +1.0 = all 3 regime gates aligned with trade direction (strong regime conf.)
    #   -1.0 = all 3 gates opposed (strong regime counter-signal)
    #   Source: regime_3gate_vote injected at G4 F91-F95 stamping block [v79.0]
    _v16_f94 = _safe_float(trade.get("regime_3gate_vote", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v16_f94)))                                   # 94 regime_3gate_vote

    # F95: gex_net_norm — net GEX exposure normalized to [-1, +1]
    #   +1.0 = strong positive GEX (dealer hedging creates upward price pressure)
    #   -1.0 = strong negative GEX (dealer hedging creates downward pressure)
    #   Source: gex_net_norm injected at G4 F91-F95 stamping block [v79.0]
    _v16_f95 = _safe_float(trade.get("gex_net_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v16_f95)))                                   # 95 gex_net_norm

    # ── v17 Volume/Pressure/Meta features (96-100) — v80.0 ───────────────────
    # F96: vol_ofi_cross — volume_ratio × OFI direction cross-product [-1, +1]
    #   +1.0 = high-volume surge aligned with OFI direction (institutional confirmation)
    #   -1.0 = high-volume surge opposed to OFI direction (institutional counter-flow)
    #    0.0 = low volume or OFI ambiguous (no regime signal)
    #   Source: vol_ofi_cross injected at G4 F96-F100 stamping block [v80.0]
    _v17_f96 = _safe_float(trade.get("vol_ofi_cross", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v17_f96)))                                   # 96 vol_ofi_cross

    # F97: funding_spread_cross — funding velocity × spread deviation cross [-1, +1]
    #   Positive = funding rising AND spread wide (illiquid + rate-rising = compounded risk)
    #   Negative = funding falling AND spread wide (unusual; relief pattern)
    #    0.0 = normal environment (funding flat or spread neutral)
    #   Source: funding_spread_cross injected at G4 F96-F100 stamping block [v80.0]
    _v17_f97 = _safe_float(trade.get("funding_spread_cross", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v17_f97)))                                   # 97 funding_spread_cross

    # F98: vpr_signal — G8.5L2 VolumePressure-Regime gate result [-1, 0, +1]
    #   +1.0 = G8.5L2 fired aligned (vol surge + OFI confirm direction)
    #   -1.0 = G8.5L2 fired opposed (vol surge + OFI counter direction)
    #    0.0 = G8.5L2 neutral (low volume or OFI ambiguous)
    #   Source: vpr_signal injected at G4 F96-F100 stamping block [v80.0]
    _v17_f98 = _safe_float(trade.get("vpr_signal", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v17_f98)))                                   # 98 vpr_signal

    # F99: spread_liq_score — combined spread pressure + liq_intensity score [-1, +1]
    #   +1.0 = high spread deviation AND high liquidation intensity (execution stress)
    #    0.0 = normal spread and liq environment
    #   -1.0 = very tight spread and no liquidation activity (ideal execution)
    #   Source: spread_liq_score injected at G4 F96-F100 stamping block [v80.0]
    _v17_f99 = _safe_float(trade.get("spread_liq_score", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v17_f99)))                                   # 99 spread_liq_score

    # F100: regime_5gate_meta — normalized 5-gate meta-vote [-1, +1]
    #   Aggregates HMM + OFI + spread + G8.5J + G8.5L2 signals into one meta-regime signal.
    #   +1.0 = all 5 gates aligned bullish/bearish with direction (maximum confluence)
    #   -1.0 = all 5 gates opposed (maximum headwind; strong no-trade signal)
    #    0.0 = mixed/neutral regime (no edge from meta-vote)
    #   Source: regime_5gate_meta injected at G4 F96-F100 stamping block [v80.0]
    _v17_f100 = _safe_float(trade.get("regime_5gate_meta", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v17_f100)))                                  # 100 regime_5gate_meta

    # ── v18 (v81.0) F101-F105: funding/liquidation/meta features ─────────────
    # F101: funding_momentum_norm — funding_rate_trend × direction alignment [-1, +1]
    #   -1.0 = funding trend strongly opposed to direction (crowding risk warning)
    #   +1.0 = funding trend strongly aligned with direction (crowd momentum confirms)
    #    0.0 = neutral/weak funding trend
    #   Source: funding_momentum_norm injected at G4 F101-F105 stamping block [v81.0]
    _v18_f101 = _safe_float(trade.get("funding_momentum_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v18_f101)))                                  # 101 funding_momentum_norm

    # F102: vol_surge_persist — vol_ratio consecutive surge persistence score [-1, +1]
    #   +1.0 = extreme volume surge (vol_ratio >> 1.5x, strong institutional activity)
    #    0.0 = normal volume (vol_ratio near 1.0x baseline)
    #   -1.0 = volume drought (vol_ratio < 1.0x)
    #   Source: vol_surge_persist injected at G4 F101-F105 stamping block [v81.0]
    _v18_f102 = _safe_float(trade.get("vol_surge_persist", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v18_f102)))                                  # 102 vol_surge_persist

    # F103: liq_cascade_intensity — liq_intensity_norm × liq_net_side cross [-1, +1]
    #   +1.0 = strong liquidation cascade aligned with direction (forced exits fuel move)
    #   -1.0 = strong liquidation cascade opposed to direction (forced exits against move)
    #    0.0 = no significant liquidation activity
    #   Source: liq_cascade_intensity injected at G4 F101-F105 stamping block [v81.0]
    _v18_f103 = _safe_float(trade.get("liq_cascade_intensity", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v18_f103)))                                  # 103 liq_cascade_intensity

    # F104: ofi_fund_cross — ofi_z × funding_rate_trend combined regime pressure [-1, +1]
    #   +1.0 = OFI aligned AND funding tail-wind (dual regime confirmation)
    #   -1.0 = OFI opposed AND funding head-wind (dual regime headwind)
    #    0.0 = mixed or neutral signals
    #   Source: ofi_fund_cross injected at G4 F101-F105 stamping block [v81.0]
    _v18_f104 = _safe_float(trade.get("ofi_fund_cross", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v18_f104)))                                  # 104 ofi_fund_cross

    # F105: meta_8gate_vote — 8-gate meta-vote /8 [-1, +1]
    #   Aggregates HMM+OFI+spread+G8.5J+G8.5L2+G8.5N2+liq+funding into one meta signal.
    #   +1.0 = all 8 gates aligned (maximum institutional confluence)
    #   -1.0 = all 8 gates opposed (maximum headwind)
    #    0.0 = mixed/neutral (no directional edge from meta-vote)
    #   Source: meta_8gate_vote injected at G4 F101-F105 stamping block [v81.0]
    _v18_f105 = _safe_float(trade.get("meta_8gate_vote", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v18_f105)))                                  # 105 meta_8gate_vote

    # ── v19 (v82.0) F106-F110: WR/regime/coherence features ─────────────────
    # F106: wr_regime_norm — session WR normalized (50%→0.0, 30%→-0.4, 70%→+0.4)
    #   Source: wr_regime_norm injected at G4 F106-F110 stamping block [v82.0]
    _v19_f106 = _safe_float(trade.get("wr_regime_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v19_f106)))                                  # 106 wr_regime_norm
    # F107: consec_loss_norm — consecutive losses normalized (0→0.0, 5+→-1.0)
    #   Source: consec_loss_norm injected at G4 F106-F110 stamping block [v82.0]
    _v19_f107 = _safe_float(trade.get("consec_loss_norm", 0.0), 0.0)
    f.append(max(-1.0, min(0.0, _v19_f107)))                                  # 107 consec_loss_norm
    # F108: ev_coherence_gate — G8.5O2 WinRateEV coherence gate output (-1/0/+1)
    #   Source: ev_coherence_gate injected at G4 F106-F110 stamping block [v82.0]
    _v19_f108 = _safe_float(trade.get("ev_coherence_gate", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v19_f108)))                                  # 108 ev_coherence_gate
    # F109: sharpe_norm — Sharpe ratio normalized (clip to [-3,+3] → [-1,+1])
    #   Source: sharpe_norm injected at G4 F106-F110 stamping block [v82.0]
    _v19_f109 = _safe_float(trade.get("sharpe_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v19_f109)))                                  # 109 sharpe_norm
    # F110: meta_regime_composite — WR+consec+G8.5O2+Sharpe combined [-1, +1]
    #   Source: meta_regime_composite injected at G4 F106-F110 stamping block [v82.0]
    _v19_f110 = _safe_float(trade.get("meta_regime_composite", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v19_f110)))                                  # 110 meta_regime_composite

    # ── v20 (v83.0) F111-F115: EV/risk crisis features ───────────────────────
    # F111: ev_crisis_norm — session EV normalized (-0.50R→-1.0, 0R→0.0, +0.30R→+0.6)
    #   Source: ev_crisis_norm injected at G4 F111-F115 stamping block [v83.0]
    _v20_f111 = _safe_float(trade.get("ev_crisis_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v20_f111)))                                  # 111 ev_crisis_norm
    # F112: max_dd_norm — MaxDD normalized (0%→0.0, 50%→-1.0, clipped [-1, 0])
    #   Source: max_dd_norm injected at G4 F111-F115 stamping block [v83.0]
    _v20_f112 = _safe_float(trade.get("max_dd_norm", 0.0), 0.0)
    f.append(max(-1.0, min(0.0, _v20_f112)))                                  # 112 max_dd_norm
    # F113: ev_crisis_gate — G8.5P2 EV-crisis gate output (-1=ultra-crisis, 0=neutral)
    #   Source: ev_crisis_gate injected at G4 F111-F115 stamping block [v83.0]
    _v20_f113 = _safe_float(trade.get("ev_crisis_gate", 0.0), 0.0)
    f.append(max(-1.0, min(0.0, _v20_f113)))                                  # 113 ev_crisis_gate
    # F114: kelly_fraction_norm — Kelly fraction normalized (0%→-1.0, 1%→0.0, 2%+→+1.0)
    #   Source: kelly_fraction_norm injected at G4 F111-F115 stamping block [v83.0]
    _v20_f114 = _safe_float(trade.get("kelly_fraction_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v20_f114)))                                  # 114 kelly_fraction_norm
    # F115: risk_composite — EV+MaxDD+EV-gate+Kelly combined meta-feature [-1, +1]
    #   Source: risk_composite injected at G4 F111-F115 stamping block [v83.0]
    _v20_f115 = _safe_float(trade.get("risk_composite", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v20_f115)))                                  # 115 risk_composite

    # ── v21 (v84.0) F116-F120: regime/sentiment composite features ───────────
    # F116: g85q_trendmom — G8.5Q TrendMomentum-Persistence gate output (+1/0/-1)
    #   Source: g85q_trendmom injected at G4 F116-F120 stamping block [v84.0]
    _v21_f116 = _safe_float(trade.get("g85q_trendmom", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v21_f116)))                                  # 116 g85q_trendmom
    # F117: g85r2_regimesent — G8.5R2 RegimeSentiment-Composite gate output (+1/0/-1)
    #   Source: g85r2_regimesent injected at G4 F116-F120 stamping block [v84.0]
    _v21_f117 = _safe_float(trade.get("g85r2_regimesent", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v21_f117)))                                  # 117 g85r2_regimesent
    # F118: vol_persist_composite — VolPressure+FundMom combined meta-signal [-1,+1]
    #   Source: vol_persist_composite injected at G4 F116-F120 stamping block [v84.0]
    _v21_f118 = _safe_float(trade.get("vol_persist_composite", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v21_f118)))                                  # 118 vol_persist_composite
    # F119: ofi_regime_quality — OFI persistence ring majority vote direction [-1,+1]
    #   Source: ofi_regime_quality injected at G4 F116-F120 stamping block [v84.0]
    _v21_f119 = _safe_float(trade.get("ofi_regime_quality", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v21_f119)))                                  # 119 ofi_regime_quality
    # F120: multi_gate_consensus — weighted 5-gate consensus G8.5Q/R2/O2/L2/N2 [-1,+1]
    #   Source: multi_gate_consensus injected at G4 F116-F120 stamping block [v84.0]
    _v21_f120 = _safe_float(trade.get("multi_gate_consensus", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v21_f120)))                                  # 120 multi_gate_consensus

    # ── v22 (v85.0) F121-F125: crisis/regime composite features ────────────
    # F121: wr_crisis_score — Bayesian WR normalized to [-1,+1] around 0.35 baseline
    #   Source: wr_crisis_score injected at G4 F121-F125 stamping block [v85.0]
    _v22_f121 = _safe_float(trade.get("wr_crisis_score", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v22_f121)))                                  # 121 wr_crisis_score
    # F122: fear_greed_regime — F&G index normalized to [-1,+1] (50→0.0, 100→+1.0, 0→-1.0)
    #   Source: fear_greed_regime injected at G4 F121-F125 stamping block [v85.0]
    _v22_f122 = _safe_float(trade.get("fear_greed_regime", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v22_f122)))                                  # 122 fear_greed_regime
    # F123: g85s2_crisis — G8.5S2 WinRate-CrisisRegime gate output (+1/0/-1)
    #   Source: g85s2_crisis injected at G4 F121-F125 stamping block [v85.0]
    _v22_f123 = _safe_float(trade.get("g85s2_crisis", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v22_f123)))                                  # 123 g85s2_crisis
    # F124: g85t2_fearreg — G8.5T2 ExtremeFear-Regime gate output (+1/0/-1)
    #   Source: g85t2_fearreg injected at G4 F121-F125 stamping block [v85.0]
    _v22_f124 = _safe_float(trade.get("g85t2_fearreg", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v22_f124)))                                  # 124 g85t2_fearreg
    # F125: crisis_regime_composite — G8.5S2(1.5x)+G8.5T2(1.0x)+WRscore(0.5x) weighted composite
    #   Source: crisis_regime_composite injected at G4 F121-F125 stamping block [v85.0]
    _v22_f125 = _safe_float(trade.get("crisis_regime_composite", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v22_f125)))                                  # 125 crisis_regime_composite

    # ── v23 (v87.0) F126-F130: VoV-stability and live-flow features ─────────
    # F126: vov_stability — VoV-StabilityRegime gate output (+1=stable, 0=neutral, -1=chaotic)
    #   Source: vov_stability injected at G4 F126-F130 stamping block [v87.0]
    _v23_f126 = _safe_float(trade.get("vov_stability", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v23_f126)))                                  # 126 vov_stability
    # F127: funding_extreme_norm — extreme funding direction signal [-1,+1]
    #   Source: funding_extreme_norm injected at G4 F126-F130 stamping block [v87.0]
    _v23_f127 = _safe_float(trade.get("funding_extreme_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v23_f127)))                                  # 127 funding_extreme_norm
    # F128: oi_velocity_norm — OI change rate direction from mark-price WS [-1,+1]
    #   Source: oi_velocity_norm injected at G4 F126-F130 stamping block [v87.0]
    _v23_f128 = _safe_float(trade.get("oi_velocity_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v23_f128)))                                  # 128 oi_velocity_norm
    # F129: depth_ratio_norm — bid/ask depth asymmetry from live orderbook [-1,+1]
    #   Source: depth_ratio_norm injected at G4 F126-F130 stamping block [v87.0]
    _v23_f129 = _safe_float(trade.get("depth_ratio_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v23_f129)))                                  # 129 depth_ratio_norm
    # F130: liq_net_momentum — net liquidation pressure direction [-1,+1]
    #   Source: liq_net_momentum injected at G4 F126-F130 stamping block [v87.0]
    _v23_f130 = _safe_float(trade.get("liq_net_momentum", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v23_f130)))                                  # 130 liq_net_momentum

    # ── v24 (v88.0) F131-F135: OrderBook Pressure and live-flow features ────────
    # F131: ob_pressure_imbalance — direction-weighted OB depth imbalance gate output [-1,+1]
    #   +1=strong aligned OB pressure, -1=strong opposing OB pressure, 0=neutral
    #   Source: ob_pressure_imbalance injected at G4 F131-F135 stamping block [v88.0]
    _v24_f131 = _safe_float(trade.get("ob_pressure_imbalance", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v24_f131)))                                  # 131 ob_pressure_imbalance
    # F132: ob_bid_dominance — normalized bid depth dominance from WS orderbook [0,1]
    #   1.0=fully bid-dominated, 0.0=fully ask-dominated, 0.5=balanced
    #   Source: ob_bid_dominance injected at G4 F131-F135 stamping block [v88.0]
    _v24_f132 = _safe_float(trade.get("ob_bid_dominance", 0.5), 0.5)
    f.append(max(0.0, min(1.0, _v24_f132)))                                   # 132 ob_bid_dominance
    # F133: ob_ask_dominance — normalized ask depth dominance from WS orderbook [0,1]
    #   1.0=fully ask-dominated (sell pressure), 0.0=no ask dominance
    #   Source: ob_ask_dominance injected at G4 F131-F135 stamping block [v88.0]
    _v24_f133 = _safe_float(trade.get("ob_ask_dominance", 0.5), 0.5)
    f.append(max(0.0, min(1.0, _v24_f133)))                                   # 133 ob_ask_dominance
    # F134: spread_vol_norm — rolling spread volatility (std/mean) normalized to [-1,+1]
    #   +1=low spread vol (stable liquidity), -1=high spread vol (erratic liquidity)
    #   Source: spread_vol_norm injected at G4 F131-F135 stamping block [v88.0]
    _v24_f134 = _safe_float(trade.get("spread_vol_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v24_f134)))                                  # 134 spread_vol_norm
    # F135: trade_flow_intensity — aggressor buy ratio direction from WS aggtrade [-1,+1]
    #   +1=aggressive buyer-dominated, -1=aggressive seller-dominated, 0=balanced
    #   Source: trade_flow_intensity injected at G4 F131-F135 stamping block [v88.0]
    _v24_f135 = _safe_float(trade.get("trade_flow_intensity", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v24_f135)))                                  # 135 trade_flow_intensity
    # ── v25 (v89.0) F136-F140: DrawdownMomentum / risk / regime features ─────
    # F136: dd_sentiment_norm — MaxDD normalized to [-1,0]; 0=no DD, -1=MaxDD at 50%
    #   Source: dd_sentiment_norm injected at G4 F136-F140 stamping block [v89.0]
    _v25_f136 = _safe_float(trade.get("dd_sentiment_norm", 0.0), 0.0)
    f.append(max(-1.0, min(0.0, _v25_f136)))                                  # 136 dd_sentiment_norm
    # F137: sharpe_norm_g — Sharpe ratio normalized [-1,+1]; clamp(Sharpe/5, -1, +1)
    #   +1=strong Sharpe(+5), -1=deep crisis Sharpe(-5), 0=neutral
    #   Source: sharpe_norm_g injected at G4 F136-F140 stamping block [v89.0]
    _v25_f137 = _safe_float(trade.get("sharpe_norm_g", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v25_f137)))                                  # 137 sharpe_norm_g
    # F138: ev_session_norm — session EV/R normalized [-1,+1]; clamp(EV/0.5, -1, +1)
    #   +1=EV≥+0.5R (profitable), -1=EV≤-0.5R (crisis), 0=EV≈0
    #   Source: ev_session_norm injected at G4 F136-F140 stamping block [v89.0]
    _v25_f138 = _safe_float(trade.get("ev_session_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v25_f138)))                                  # 138 ev_session_norm
    # F139: dd_gate_output — G8.5W2 DrawdownMomentum-Sentinel gate output (+1/-1/0)
    #   +1=healthy regime, -1=drawdown warning, 0=neutral/insufficient data
    #   Source: dd_gate_output injected at G4 F136-F140 stamping block [v89.0]
    _v25_f139 = _safe_float(trade.get("dd_gate_output", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v25_f139)))                                  # 139 dd_gate_output
    # F140: kelly_health_norm — Kelly fraction / Kelly cap [0,1]; 1.0=full cap
    #   0.0=at floor (de-sized), 1.0=at cap (full-sized), ~0.5=normal
    #   Source: kelly_health_norm injected at G4 F136-F140 stamping block [v89.0]
    _v25_f140 = _safe_float(trade.get("kelly_health_norm", 0.5), 0.5)
    f.append(max(0.0, min(1.0, _v25_f140)))                                   # 140 kelly_health_norm
    # ── v26 (v90.0) F141-F145: WR-Trajectory features ─────────────────────────
    # F141: rolling_5wr_norm — recent booster-ring WR normalized [-1,+1]
    #   +1=WR=100%, -1=WR=0%, 0=WR=50% breakeven; proxy for recent win momentum
    #   Source: rolling_5wr_norm injected at G4 F141-F145 stamping block [v90.0]
    _v26_f141 = _safe_float(trade.get("rolling_5wr_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v26_f141)))                                  # 141 rolling_5wr_norm
    # F142: rolling_20wr_norm — all-time session WR normalized [-1,+1]
    #   +1=alltime WR=100%, -1=WR=0%, 0=WR=50%; session-level baseline quality
    #   Source: rolling_20wr_norm injected at G4 F141-F145 stamping block [v90.0]
    _v26_f142 = _safe_float(trade.get("rolling_20wr_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v26_f142)))                                  # 142 rolling_20wr_norm
    # F143: wr_trajectory_norm — delta(recent - alltime) WR normalized [-1,+1]
    #   +1=recent WR strongly above alltime (recovering), -1=strongly below (deteriorating)
    #   clamp((recent_wr - alltime_wr) * 5.0, -1, +1); 20pp delta = ±1.0
    #   Source: wr_trajectory_norm injected at G4 F141-F145 stamping block [v90.0]
    _v26_f143 = _safe_float(trade.get("wr_trajectory_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v26_f143)))                                  # 143 wr_trajectory_norm
    # F144: recent_loss_streak_norm — G8.5X2 gate output polarity [−0.5, +0.5]
    #   +0.5=deteriorating trajectory (loss streak proxy), −0.5=recovering, 0.0=neutral
    #   Source: recent_loss_streak_norm injected at G4 F141-F145 stamping block [v90.0]
    _v26_f144 = _safe_float(trade.get("recent_loss_streak_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v26_f144)))                                  # 144 recent_loss_streak_norm
    # F145: recent_win_streak_norm — recent booster-ring WR raw [0,1]
    #   1.0=all recent trades won, 0.0=all lost; win-streak momentum signal
    #   Source: recent_win_streak_norm injected at G4 F141-F145 stamping block [v90.0]
    _v26_f145 = _safe_float(trade.get("recent_win_streak_norm", 0.5), 0.5)
    f.append(max(0.0, min(1.0, _v26_f145)))                                   # 145 recent_win_streak_norm
    # -- v27 (v91.0) F146-F150: HMM-regime / VPIN-flow coherence features --------
    # F146: hmm_expansion_prob_norm -- HMM expansion-state probability [0,1]
    #   1.0 = HMM fully in EXPANSION regime; 0.0 = CONTRACTION; 0.5 = uncertain/TRANSITION
    #   Source: hmm_expansion_prob injected at G4 F146-F150 stamping block [v91.0]
    _v27_f146 = _safe_float(trade.get("hmm_expansion_prob_norm", 0.5), 0.5)
    f.append(max(0.0, min(1.0, _v27_f146)))                                   # 146 hmm_expansion_prob_norm
    # F147: vpin_pct_norm -- VPIN flow toxicity percentile [0,1]
    #   0.0 = ultra-clean flow (institutional accumulation);
    #   1.0 = highly toxic (informed-trader dominated, adverse selection risk)
    #   Source: vpin_pct_norm injected at G4 F146-F150 stamping block [v91.0]
    _v27_f147 = _safe_float(trade.get("vpin_pct_norm", 0.5), 0.5)
    f.append(max(0.0, min(1.0, _v27_f147)))                                   # 147 vpin_pct_norm
    # F148: hmm_vpin_coherence_norm -- joint HMM+VPIN signal normalized [-1,+1]
    #   +1 = EXPANSION + clean VPIN (strong institutional buy-side);
    #   -1 = CONTRACTION + toxic VPIN (institutional distribution);
    #    0 = mixed/neutral regime
    #   Source: hmm_vpin_coherence_norm injected at G4 F146-F150 stamping block [v91.0]
    _v27_f148 = _safe_float(trade.get("hmm_vpin_coherence_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v27_f148)))                                  # 148 hmm_vpin_coherence_norm
    # F149: hmm_regime_norm -- HMM regime encoded [-1,+1]
    #   +1.0 = EXPANSION, -1.0 = CONTRACTION, 0.0 = TRANSITION/UNKNOWN
    #   Source: hmm_regime_norm injected at G4 F146-F150 stamping block [v91.0]
    _v27_f149 = _safe_float(trade.get("hmm_regime_norm", 0.0), 0.0)
    f.append(max(-1.0, min(1.0, _v27_f149)))                                  # 149 hmm_regime_norm
    # F150: vpin_toxic_norm -- binary VPIN toxicity indicator [0,1]
    #   1.0 = flow classified as toxic (pct >= 0.80); 0.0 = clean flow
    #   Source: vpin_toxic_norm injected at G4 F146-F150 stamping block [v91.0]
    _v27_f150 = _safe_float(trade.get("vpin_toxic_norm", 0.0), 0.0)
    f.append(max(0.0, min(1.0, _v27_f150)))                                   # 150 vpin_toxic_norm

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
            # v19.2 FIX: enable_nested_tensor=False prevents PyTorch ≥2.1 internal
            # inplace operations on nested tensors that cause AsStridedBackward0
            # version-mismatch errors during backward() in the training loop.
            self.encoder = _nn.TransformerEncoder(
                enc_layer, num_layers=num_layers, enable_nested_tensor=False
            )
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
            # v19.3 FIX: .contiguous() on the sliced CLS token prevents residual
            # non-contiguous strided-view inplace errors in the head Linear layers.
            cls_out = out[:, 0, :].contiguous()                       # (B, d_model)
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
            epochs: int = 150, batch_size: int = 32, lr: float = 3e-4,   # v19.7: 100→150 — Transformer benefits more from longer training than MLP since attention weights need more gradient steps to converge on sparse 30% WR data; early-stopping (patience→25) prevents overfit
            sample_weight: "Optional[np.ndarray]" = None) -> bool:
        """
        Train on normalised (N, 55) feature matrix + binary labels (0/1).
        Uses same 80/20 train/val split as numpy MLP (15% val).

        v18.92: sample_weight (N,) — per-sample importance weights (e.g. time-decay).
        Weights are normalised so their mean = 1.0 before use. Validation loss is
        always unweighted so the early-stopping metric reflects true data distribution.
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

            # v18.92: Build training sample weights tensor (time-decay or uniform)
            if sample_weight is not None and len(sample_weight) == len(X_norm):
                _sw_tr = sample_weight[:-n_val].astype("float32")
                _sw_tr = _sw_tr / float(_sw_tr.mean() + 1e-8)   # normalise mean=1.0
                sw_tr_t = _torch.tensor(_sw_tr, dtype=_torch.float32)
            else:
                sw_tr_t = None  # uniform weights — fall back to plain mean

            Xtr = _torch.tensor(X_tr, dtype=_torch.float32)
            ytr = _torch.tensor(y_tr, dtype=_torch.float32)
            Xva = _torch.tensor(X_va, dtype=_torch.float32)
            yva = _torch.tensor(y_va, dtype=_torch.float32)

            def focal_bce(pred: "_torch.Tensor", tgt: "_torch.Tensor",
                          sw: "_torch.Tensor | None" = None,
                          gamma: float = 2.0) -> "_torch.Tensor":
                """Focal BCE. If sw given, returns importance-weighted average."""
                eps = 1e-7
                p   = pred.clamp(eps, 1.0 - eps)
                pt  = _torch.where(tgt == 1, p, 1.0 - p)
                loss_per_sample = -((1.0 - pt) ** gamma) * pt.log()
                if sw is not None:
                    # weighted mean: sum(sw * loss) / sum(sw) — preserves gradient scale
                    return (loss_per_sample * sw).sum() / (sw.sum() + 1e-8)
                return loss_per_sample.mean()

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
                    # v19.2 FIX: .contiguous() on indexed tensors eliminates the
                    # AsStridedBackward0 version-mismatch inplace error.
                    # Root cause: Xtr[idx] returns a non-contiguous strided view;
                    # when the optimizer's in-place param update coincides with a
                    # retained grad tensor from the same strides, PyTorch's version
                    # counter fires "expected version N; got N+1".
                    _xb = Xtr[idx].contiguous()
                    _yb = ytr[idx].contiguous()
                    # v18.92: pass per-sample weights for this mini-batch
                    _sw_batch = (
                        sw_tr_t[idx].contiguous() if sw_tr_t is not None else None
                    )
                    # v19.2 FIX: zero_grad(set_to_none=True) BEFORE forward pass.
                    # Calling zero_grad AFTER model() but BEFORE backward() leaves
                    # stale in-place gradient zeroing operations in the autograd
                    # graph that can corrupt the version counter on the strided view.
                    opt.zero_grad(set_to_none=True)
                    loss = focal_bce(self._model(_xb), _yb, sw=_sw_batch)
                    loss.backward()
                    _nn.utils.clip_grad_norm_(self._model.parameters(), 1.0)
                    opt.step()
                sched.step()
                n_epochs_run = epoch + 1

                # Validation always unweighted — reflects true data distribution
                self._model.eval()
                with _torch.no_grad():
                    vl = focal_bce(self._model(Xva), yva, sw=None).item()

                if vl < best_val - 1e-5:
                    best_val = vl
                    best_sd  = {k: v.clone() for k, v in self._model.state_dict().items()}
                    no_imp   = 0
                else:
                    no_imp += 1
                    if no_imp >= 25:   # v19.7: 18→25 — wider patience for attention convergence
                        break

            self._model.load_state_dict(best_sd)
            self.trained = True
            self._save()
            _sw_tag = " time-decay✅" if sw_tr_t is not None else ""
            self._logger.info(
                f"🔮 PyTorch Transformer trained | n={len(X_norm)}{_sw_tag} "
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
                 focal_gamma: float = 2.5,
                 class_weight_loss: float = 2.0):  # v19.6: gamma 2.0→2.5 — at WR=36.3% (minority wins) a higher γ forces the focal loss to penalise easy-to-classify examples (losses) 25% more and focus gradient budget on hard boundary wins; γ=2 was standard for balanced classes; γ=2.5 matches optimal range for 36/64 imbalance per Lin et al. 2017 focal loss paper; combined with _MAX_CLASS_WEIGHT=4.0 this gives the win class ~2× more influence per update
        self.logger  = logging.getLogger(__name__)
        # FIX 1: store _base_lr separately so _cosine_lr never reads the
        # already-decayed self.lr — the bug that broke the schedule after epoch 1.
        self._base_lr = lr
        self.lr       = lr
        self.l2      = l2
        self.focal_gamma = focal_gamma
        # v20.4: Adaptive time-decay steepness — settable externally by the retrain task.
        # Normal regime: 2.0× (oldest=1.00×, newest=2.00×, 30% of samples get 1.5-2.0× weight).
        # Crisis regime (SR<-4 | WR<25%): 4.0× (newest=4.0×, recent 20% dominates 3-4×).
        # Higher steepness helps the NN forget bull-market patterns faster and focus on
        # the current losing regime. Reset to 2.0 in recovery to avoid over-weighting noise.
        self.time_decay_ratio: float = 2.0
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

        # v60.0: HistGradientBoosting ensemble complement (see train() for fitting logic)
        # Provides axis-aligned threshold effects orthogonal to the MLP's smooth boundary.
        # None until first successful quality_ok train cycle; used in predict_signal() blend.
        self._hgbt: Optional[Any] = None
        self._et:   Optional[Any] = None    # v63.0: ExtraTreesClassifier 3rd ensemble
        self._et_weight: float    = 0.15    # v63.0: adaptive weight ∈ [0.10, 0.25]

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
                # v9: GEX regime features — stamped by engine before inference
                "gex_btc_regime":     getattr(signal, "gex_btc_regime",    ""),
                "gex_btc_conf":       getattr(signal, "gex_btc_conf",     0.0),
                "gex_btc_net":        getattr(signal, "gex_btc_net",      0.0),
                "gex_flip_count":     getattr(signal, "gex_flip_count",     0),
                "gex_btc_flip_price": getattr(signal, "gex_btc_flip_price",0.0),
                "entry_price_for_gex":signal.entry_price,
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

            # v64.0: Unified 3-way tree consensus blend.
            # When HistGBT + ExtraTrees are both fitted, compute an accuracy-weighted
            # tree consensus FIRST (prevents double-counting of tree weight when both
            # are available), then blend the consensus against the neural base_prob.
            # Total tree contribution is capped at 40% to preserve neural-net dominance.
            # Fallback: if only one tree is fitted, apply that tree's individual blend.
            # Sequential v60-v63 design (HistGBT first, then ET) could effectively
            # over-weight trees when both fit: e.g. 30%+15%=45% combined but compounded.
            # The unified design is explicit and bounded.
            _hgbt_blend = getattr(self, "_hgbt", None)
            _et_blend   = getattr(self, "_et",   None)
            if _hgbt_blend is not None and _et_blend is not None:
                # Both tree models fitted → unified accuracy-weighted tree consensus
                try:
                    _hg_p    = _hgbt_blend.predict_proba(X_norm)
                    _hg_prob = float(_hg_p[0, 1]) if _hg_p.shape[1] > 1 else float(_hg_p[0, 0])
                    _et_p    = _et_blend.predict_proba(X_norm)
                    _et_prob = float(_et_p[0, 1]) if _et_p.shape[1] > 1 else float(_et_p[0, 0])
                    _hw       = float(getattr(self, "_hgbt_weight", 0.30))   # v61.0 adaptive
                    _ew       = float(getattr(self, "_et_weight",   0.15))   # v63.0 adaptive
                    _tree_sum = _hw + _ew
                    # Weighted average within the tree ensemble
                    _tree_consensus = (
                        (_hw * _hg_prob + _ew * _et_prob) / _tree_sum
                        if _tree_sum > 0.0
                        else (_hg_prob + _et_prob) / 2.0
                    )
                    # Total tree weight capped at 40% to preserve neural dominance
                    _total_tree_w = min(_tree_sum, 0.40)
                    base_prob = float(np.clip(
                        (1.0 - _total_tree_w) * base_prob + _total_tree_w * _tree_consensus,
                        0.05, 1.0
                    ))
                except Exception:
                    pass
            elif _hgbt_blend is not None:
                # Only HistGBT fitted — single-tree blend (original v60-v63 path)
                try:
                    _hg_p    = _hgbt_blend.predict_proba(X_norm)
                    _hg_prob = float(_hg_p[0, 1]) if _hg_p.shape[1] > 1 else float(_hg_p[0, 0])
                    _hw      = float(getattr(self, "_hgbt_weight", 0.30))
                    base_prob = float(np.clip((1.0 - _hw) * base_prob + _hw * _hg_prob, 0.05, 1.0))
                except Exception:
                    pass
            elif _et_blend is not None:
                # Only ExtraTrees fitted (HistGBT not trained yet)
                try:
                    _et_p    = _et_blend.predict_proba(X_norm)
                    _et_prob = float(_et_p[0, 1]) if _et_p.shape[1] > 1 else float(_et_p[0, 0])
                    _ew      = float(getattr(self, "_et_weight", 0.15))
                    base_prob = float(np.clip((1.0 - _ew) * base_prob + _ew * _et_prob, 0.05, 1.0))
                except Exception:
                    pass

            # v65.0: Ensemble Coherence Boost / Penalty ─────────────────────────────────
            # After the unified 3-way tree consensus blend is applied, measure how closely
            # all active model heads agree on the final prediction.  High agreement signals
            # genuine edge and rewards the score; high disagreement signals ambiguity and
            # applies a slight dampener.
            #
            # Rationale (Breiman ensemble bias-variance, Krogh & Vedelsby 1995):
            #   Error of ensemble = average member error − average member ambiguity.
            #   When ambiguity (disagreement) is low and average error is low → the ensemble
            #   is in its ideal state.  When ambiguity is high the ensemble error is bounded
            #   BELOW by the ambiguity → we should discount the confidence of the output.
            #
            # Rule:  collect all available raw model outputs (MLP/Transformer base_prob
            # BEFORE tree blending, HistGBT, ExtraTrees).  Compute the range (max−min).
            #   Range ≤ 0.03 (≡ ±1.5pp):  high consensus → × 1.02  (cap 0.95)
            #   Range ≥ 0.15 (≡ ±7.5pp):  high ambiguity → × 0.99  (floor 0.05)
            #   In between                : no adjustment
            # Non-fatal. Does not change training logic.
            try:
                _ec_models: list = []
                # Neural base (already blended, use as representative)
                _ec_models.append(base_prob)
                if _hgbt_blend is not None:
                    try:
                        _ec_hg_p = _hgbt_blend.predict_proba(X_norm)
                        _ec_models.append(
                            float(_ec_hg_p[0, 1]) if _ec_hg_p.shape[1] > 1 else float(_ec_hg_p[0, 0])
                        )
                    except Exception:
                        pass
                if _et_blend is not None:
                    try:
                        _ec_et_p = _et_blend.predict_proba(X_norm)
                        _ec_models.append(
                            float(_ec_et_p[0, 1]) if _ec_et_p.shape[1] > 1 else float(_ec_et_p[0, 0])
                        )
                    except Exception:
                        pass
                if len(_ec_models) >= 2:
                    _ec_range = max(_ec_models) - min(_ec_models)
                    if _ec_range <= 0.03:
                        base_prob = float(np.clip(base_prob * 1.02, 0.05, 0.95))
                    elif _ec_range >= 0.15:
                        base_prob = float(np.clip(base_prob * 0.99, 0.05, 1.0))
            except Exception:
                pass

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
                # v9: GEX regime features — pass through from signal_data if present
                gex_btc_regime    = str(signal_data.get("gex_btc_regime",    "") or ""),
                gex_btc_conf      = float(signal_data.get("gex_btc_conf",   0.0) or 0.0),
                gex_btc_net       = float(signal_data.get("gex_btc_net",    0.0) or 0.0),
                gex_flip_count    = int(signal_data.get("gex_flip_count",     0) or 0),
                gex_btc_flip_price= float(signal_data.get("gex_btc_flip_price",0.0) or 0.0),
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
                # v9: GEX regime features — stamped by engine before inference
                "gex_btc_regime":     getattr(signal, "gex_btc_regime",    ""),
                "gex_btc_conf":       getattr(signal, "gex_btc_conf",     0.0),
                "gex_btc_net":        getattr(signal, "gex_btc_net",      0.0),
                "gex_flip_count":     getattr(signal, "gex_flip_count",     0),
                "gex_btc_flip_price": getattr(signal, "gex_btc_flip_price",0.0),
                "entry_price_for_gex":signal.entry_price,
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
        epochs: int = 500,      # v19.7: 400→500 — at WR=30% imbalanced data, extra 100 epochs improves minority-class boundary; early-stopping (patience=40) prevents overfit
        batch_size: int = 32,
        patience: int = 40,     # v19.7: 30→40 — wider patience window lets AdamW + cosine LR find better minima before early-stop fires; combined with epochs→500 gives ≥15% longer training in median case
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

            # v18.92: Time-decay sample weights — assumes trades are ordered oldest→newest.
            # Exponential schedule: w_i = exp(ln(R) * i/(n-1)) → oldest=1.00×, newest=R×.
            # v20.4: R (time_decay_ratio) is now settable externally (default 2.0, crisis 4.0).
            # Normal (R=2.0): newest=2.00×, recent 30% contribute ~1.5× more to gradient.
            # Crisis (R=4.0): newest=4.00×, recent 20% contribute 3-4× — NN forgets old regime patterns
            # faster during deep ruin, adapting to the current losing regime in fewer cycles.
            # Normalised so mean=1.0, preserving total gradient magnitude.
            _n_raw = len(filtered_triples)
            _decay_r = float(getattr(self, "time_decay_ratio", 2.0))
            _sw_raw = np.exp(
                np.log(max(1.01, _decay_r)) * np.arange(_n_raw, dtype=np.float32) / max(_n_raw - 1, 1)
            )
            _sw_raw = (_sw_raw / float(_sw_raw.mean())).astype(np.float32)  # mean=1.0

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
            # v67.0: Adaptive _MAX_CLASS_WEIGHT — scales with observed imbalance.
            # At train WR≥40%: cap=4.0 (same as v19.6 — light imbalance, 4× sufficient).
            # At train WR 30-40%: cap=5.0 — moderate imbalance, need 5× to give wins
            #   proportional gradient budget (5× per He & Garcia 2009 institutional standard).
            # At train WR<30%: cap=6.0 — severe imbalance, 1/0.29=3.45× natural weight
            #   would be capped at 4.0 and give insufficient win-class gradient, causing
            #   win_acc=17.8% (nearly all wins misclassified as losses). 6× ensures the
            #   win minority receives enough gradient to learn discriminative patterns.
            _train_wr = wins / (wins + losses) if (wins + losses) > 0 else 0.5
            if _train_wr >= 0.40:
                _MAX_CLASS_WEIGHT = 4.0
            elif _train_wr >= 0.30:
                _MAX_CLASS_WEIGHT = 5.0
            else:
                _MAX_CLASS_WEIGHT = 6.0  # severe imbalance — v67.0 fix for win_acc=17.8%
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
            # v67.0: Adaptive focal gamma — increases with win-minority severity.
            # Default focal_gamma=2.5 was calibrated for ~36% WR (mild imbalance).
            # At WR<35%: gamma 2.5→3.5 — same as the v60.0 extreme-ruin tier but
            #   applied at the training-data level, not just the Sharpe-crisis level.
            # At WR<30%: gamma 3.5→4.5 — at 370W/539L (40.7% WR) the model predicts
            #   only 19.7% of wins correctly; Lin et al. 2017 optimal gamma for 3:7
            #   class ratio is 4-5; γ=4.5 forces the gradient to focus on wins near
            #   the decision boundary (p_t ≈ 0.4-0.5) rather than the easy losses.
            # Stored back to self.focal_gamma so it is consistent across all batches.
            _prev_gamma = self.focal_gamma
            if _train_wr < 0.30:
                self.focal_gamma = 4.5  # v67.0: severe imbalance — force win learning
            elif _train_wr < 0.35:
                self.focal_gamma = 3.5  # v67.0: moderate imbalance — match extreme-ruin
            else:
                self.focal_gamma = 2.5  # restore default at healthy WR
            if abs(self.focal_gamma - _prev_gamma) > 0.01:
                self.logger.info(
                    f"🎯 [v67.0 AdaptGamma] WR={_train_wr:.1%} → focal_gamma "
                    f"{_prev_gamma:.1f}→{self.focal_gamma:.1f} "
                    f"(win-minority learning boost)"
                )
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
            # v60.0: Walk-Forward Validation with Embargo — replaces random 85/15 split
            # for n≥40 trades.  Trades are ordered oldest→newest (time_decay_ratio relies
            # on this ordering).  Temporal ordering prevents look-ahead bias: the
            # validation set always lies in the FUTURE relative to training, matching
            # live deployment reality.  Embargo: drop min(3, train//10) samples at the
            # split boundary to prevent autocorrelation leakage between adjacent trades
            # that share the same market session / microstructure episode.
            # Reference: De Prado (2018) AFML ch.7 — purged/embargoed walk-forward CV.
            # Fallback for n<40: classic 85/15 random split (too few for temporal CV).
            if n >= 30:   # v61.0: threshold 40→30 — walk-forward starts 10 samples earlier
                _oos_n     = max(10, int(n * 0.20))   # 20% out-of-sample holdout
                _train_end = n - _oos_n               # last training index (exclusive)
                _embargo   = min(3, _train_end // 10) # embargo: up to 3 boundary samples
                _va_idx    = list(range(_train_end, n))
                _tr_idx    = list(range(0, _train_end - _embargo))
                X_tr_raw   = X_all[_tr_idx]
                y_tr       = y_all[_tr_idx]
                X_va_raw   = X_all[_va_idx]
                y_va       = y_all[_va_idx]
                sw_tr      = _sw_raw[_tr_idx]
            else:
                idx = np.random.permutation(n)
                split = max(10, int(n * 0.85))
                X_tr_raw, y_tr = X_all[idx[:split]],  y_all[idx[:split]]
                X_va_raw, y_va = X_all[idx[split:]],   y_all[idx[split:]]
                sw_tr = _sw_raw[idx[:split]]
                _va_idx = list(idx[split:].tolist())   # compat: direction calibration uses _va_idx

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
                    # v18.92: propagate time-decay weights to oversampled minority copies
                    _sw_minority = sw_tr[minority_mask]
                    sw_tr = np.concatenate([sw_tr, _sw_minority[sampled_idx]], axis=0)
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
                sw_sh = sw_tr[perm]  # v18.92: shuffle time-decay weights with data

                for s in range(0, len(X_sh), batch_size):
                    Xb = X_sh[s: s + batch_size]
                    yb = y_sh[s: s + batch_size]
                    sw_b = sw_sh[s: s + batch_size].reshape(-1, 1)  # v18.92: per-sample decay
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
                    wt   = np.where(yb == 1, self._w_win, self._w_loss) * sw_b  # v18.92: class×time-decay
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

            # v68.0: CPCV Reliability Signal — Combinatorial Purged Cross-Validation K=3.
            # Upgraded from K=2 → K=3 walk-forward folds for better out-of-sample reliability.
            # Reference: De Prado (2018) AFML ch.12 — simplified time-series-safe variant.
            # When val_acc materially exceeds the CPCV avg (gap > 0.07): the model has
            # overfit to the most recent regime → raise _opt_threshold by up to +2pp.
            # Three temporal folds with purge at each boundary prevent data leakage.
            # K=3 improves overfit detection reliability: single fold K=2 occasionally passes
            # genuinely overfit models when the one held-out fold happens to generalize well
            # by luck; K=3 average is far more robust to this sampling noise.
            # Guard: requires n ≥ 60 (≥20 samples per fold); non-fatal on any error.
            try:
                if n >= 60:
                    _cpcv_accs = []
                    for _sp in [n // 4, n // 2, (3 * n) // 4]:
                        _purge  = min(3, _sp // 10)
                        _tr_i   = list(range(0, _sp - _purge))
                        _te_end = min(_sp + max(8, n // 3), n)
                        _te_i   = list(range(_sp, _te_end))
                        if len(_tr_i) < 12 or len(_te_i) < 8:
                            continue
                        if len(np.unique(y_all[_tr_i].flatten().astype(int))) < 2:
                            continue
                        from sklearn.neural_network import MLPClassifier as _MLPC2
                        _km = _MLPC2(
                            hidden_layer_sizes=(32,), max_iter=150,
                            random_state=_sp, alpha=1.0, learning_rate_init=0.01
                        )
                        try:
                            _km.fit(X_all_norm[_tr_i], y_all[_tr_i].flatten().astype(int))
                            _kp = _km.predict(X_all_norm[_te_i])
                            _cpcv_accs.append(float(np.mean(_kp == y_all[_te_i].flatten().astype(int))))
                        except Exception:
                            pass
                    if len(_cpcv_accs) >= 1:
                        _cpcv_avg = float(np.mean(_cpcv_accs))
                        _cpcv_gap = float(acc - _cpcv_avg)
                        if _cpcv_gap > 0.07 and _cpcv_avg > 0.45:  # v85.0: floor 0.50→0.45 (chronic suppression fix; was 0.47→0.50 in v73.0)
                            # v67.0: gap threshold 0.04→0.07 — at live gap=10% the previous
                            # 4% trigger added +0.030 to _opt_threshold (0.579→0.609), pushing
                            # the G4 gate to a level no 30% WR model can clear (nn_prob=0.35-0.42).
                            # 7% threshold means only genuine overfit (>7pp val vs CPCV gap)
                            # triggers the adjustment; routine 4-6% val-vs-CPCV variation is
                            # benign and should not inflate the threshold.
                            # v70.0: also require _cpcv_avg > 0.47 — at avg=45.4% the CPCV
                            # folds are near-chance level; using a sub-chance signal to push
                            # threshold UP is counterproductive (blocks real signals with noise).
                            # Only fire when CPCV folds show meaningful signal (>47% accuracy).
                            # v85.0: floor lowered 0.50→0.45 — live logs showed avg≈47.2% sitting
                            # just above the old 47% guard but still being excluded by the 50%
                            # boundary, causing chronic CPCV suppression (every retrain skipped
                            # overfit protection). 45% floor allows the guard to fire when CPCV
                            # shows real above-chance signal while still rejecting sub-chance noise.
                            _cpcv_adj  = min(0.02, _cpcv_gap * 0.25)  # v67.0: 0.50→0.30; v73.0: 0.30→0.25 dampen drift
                            _cpcv_old  = self._opt_threshold
                            self._opt_threshold = min(0.75, self._opt_threshold + _cpcv_adj)
                            # re-derive reject/boost thresholds to stay consistent
                            self._reject_threshold = max(0.38, self._opt_threshold * 0.62)
                            self._boost_threshold  = min(0.85, self._opt_threshold + 0.15)
                            self.logger.info(
                                f"🔬 [v68.0 CPCV] K=3 walk-fwd folds={[f'{a:.1%}' for a in _cpcv_accs]} "
                                f"avg={_cpcv_avg:.1%} val={acc:.1%} gap={_cpcv_gap:+.1%} "
                                f"→ thresh {_cpcv_old:.3f}→{self._opt_threshold:.3f} (+{_cpcv_adj:.3f})"
                            )
                        elif _cpcv_gap > 0.07:
                            # v85.0: gap > 7% but CPCV avg ≤ 45% (near-chance) — suppress push
                            # At avg<45% folds are not providing meaningful overfit signal;
                            # applying threshold push from a chance-level CPCV is counterproductive.
                            self.logger.info(
                                f"🔬 [v85.0 CPCV] K=3 walk-fwd: avg={_cpcv_avg:.1%} ≤ 45% chance-floor "
                                f"val={acc:.1%} gap={_cpcv_gap:+.1%} → thresh {self._opt_threshold:.3f} "
                                f"unchanged (sub-chance CPCV suppressed [v70.0])"
                            )
                        else:
                            self.logger.debug(
                                f"🔬 [v68.0 CPCV] K=3 walk-fwd: avg={_cpcv_avg:.1%} "
                                f"val={acc:.1%} gap={_cpcv_gap:+.1%} → thresh unchanged"
                            )
            except Exception:
                pass  # CPCV non-fatal

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
                _val_idx      = _va_idx         # v60.0: WFV uses pre-computed _va_idx (time-ordered or shuffled)
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
                # v19.7: Regime-adaptive direction calibration cap.
                # At WR<35% (loss-heavy regime) both raw offsets hit -0.15 hard cap.
                # With G4 threshold 0.526, capped -0.15 means raw NN output must be
                # ≥0.676 to pass — creates systematic G4 starvation in drawdown regimes.
                # Fix: tighten negative cap to -0.10 when WR<35% so borderline signals
                # with raw NN ~0.62-0.67 still pass after calibration (-0.10→0.52+).
                # Positive cap (overconfident in wins) retained at +0.15 — no starvation risk.
                # Original +0.15 cap restored when WR≥40% (healthy regime — full correction needed).
                _wr_for_cap = wins / max(1, wins + losses)
                if _wr_for_cap < 0.30:
                    _MAX_DIR_OFFSET_NEG = 0.07   # v19.8: deep-crisis (-0.10→-0.07) — at WR<30% G4 starvation is critical; -0.10 cap means raw NN≥0.58 to pass 0.48 gate; -0.07 means raw NN≥0.55 — 3pp more signals enter the live pool; G4 still enforces 0.48 floor + IRONS/Markov/GEX provide quality assurance
                    _MAX_DIR_OFFSET_POS = 0.15   # positive cap unchanged
                elif _wr_for_cap < 0.35:
                    _MAX_DIR_OFFSET_NEG = 0.10   # v19.7: tighter negative cap in loss-heavy regime (WR 30-35%)
                    _MAX_DIR_OFFSET_POS = 0.15   # positive cap unchanged
                else:
                    _MAX_DIR_OFFSET_NEG = 0.15   # healthy regime: full correction allowed
                    _MAX_DIR_OFFSET_POS = 0.15
                self._buy_prob_offset  = float(np.clip(_raw_buy,  -_MAX_DIR_OFFSET_NEG, _MAX_DIR_OFFSET_POS))
                self._sell_prob_offset = float(np.clip(_raw_sell, -_MAX_DIR_OFFSET_NEG, _MAX_DIR_OFFSET_POS))
                if abs(self._sell_prob_offset) > 0.005 or abs(self._buy_prob_offset) > 0.005:
                    _cap_tag = f"-{_MAX_DIR_OFFSET_NEG:.2f}/+{_MAX_DIR_OFFSET_POS:.2f}"
                    self.logger.info(
                        f"🎯 [v19.7 Dir-Cal] Direction calibration (val-set, cap={_cap_tag} wr={_wr_for_cap:.0%}): "
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
            # win_acc < threshold: model predicts "LOSS" for nearly all wins — hasn't
            # learned the winning pattern.  loss_acc < threshold: predicts "WIN" for
            # nearly all losses — no filter value.  Both must be adequate for the model
            # to add value over the raw confidence gate.
            #
            # v67.0 CALIBRATION FIX: Lowered win_acc gate 0.40→0.28, raised loss_acc
            # gate 0.40→0.50.  The previous 40%/40% gate was disabling the NN completely
            # during deep-crisis phases (win_acc=17.8%) because:
            #   1. With WR=29% in training data the class imbalance is 370W/539L (0.686 ratio)
            #   2. The NN correctly identified 88% of losses but only 18% of wins
            #   3. Disabled NN → _opt_threshold=0.609 still applied → G4 permanent 0% pass
            # New thresholds: win_acc≥28% is above break-even (~29.85% at MIN_RR=2.35) and
            # matches the minimal filtering value needed to prune low-confidence signals.
            # loss_acc≥50% ensures the model still filters out majority of losing setups.
            # Asymmetric design (low win_acc, higher loss_acc) matches the asymmetric cost
            # structure of trading: missing a win is recoverable; taking a bad loss is not.
            # v70.0: Adaptive win_acc gate — at training WR<25% (deep-crisis), lower to 0.20.
            # Rationale: at WR=18-25% a model with win_acc=24.2% + loss_acc=93.7% still has
            # significant filter value — it correctly identifies 93.7% of losing trades.
            # Disabling NN completely (as v67.0 static 0.28 gate does at 24.2%) leaves G4 with
            # zero probability filtering, which is strictly worse than an imperfect model.
            # The 0.20 floor is above the minimum sampling noise level (8 wins req) and still
            # 2× better than random (10% win_acc would be noise; 20% has directional signal).
            # At WR≥25%: retain 0.28 institutional floor (meaningful signal quality required).
            _win_acc_floor = 0.20 if (_wr_for_cap < 0.25) else 0.28
            quality_ok = (
                win_acc  >= _win_acc_floor  # v70.0: adaptive 0.28→0.20 at training WR<25%
                and loss_acc >= 0.50        # v67.0: 0.40→0.50 — must filter majority of losses
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
                    f"(need win≥{_win_acc_floor:.0%} loss≥50%, wins={wins} losses={losses} need both ≥8)"
                )

            # ── v60.0: HistGradientBoosting ensemble ──────────────────────
            # Trains a tree-based complement to the MLP.  Trees and neural nets have
            # orthogonal inductive biases: MLP excels at smooth feature interactions;
            # HistGBT excels at axis-aligned threshold effects (RSI>70, ATR cliffs,
            # volume spikes) that appear naturally in crypto microstructure.
            # Blend: 70% MLP + 30% HistGBT in predict_signal() when fitted.
            # Only trains when quality_ok=True (≥8 wins+losses, ≥40% per-class accuracy).
            # Fallback: self._hgbt=None → predict_signal() falls back to MLP-only.
            try:
                from sklearn.ensemble import HistGradientBoostingClassifier as _HGBT
                if quality_ok and len(X_tr) >= 20:
                    _hgbt_model = _HGBT(
                        max_iter=100,
                        max_depth=4,
                        min_samples_leaf=4,
                        learning_rate=0.10,
                        l2_regularization=1.0,
                        random_state=42,
                        class_weight="balanced",
                    )
                    _hgbt_model.fit(X_tr, y_tr.flatten().astype(int))
                    # v61.0: Isotonic probability calibration on held-out validation set.
                    # CalibratedClassifierCV(cv='prefit') fits a monotone mapping:
                    # raw HistGBT score → true win probability, using only out-of-sample
                    # data (X_va) so zero data leakage occurs.  Requires ≥15 val samples
                    # and both classes present; falls back to uncalibrated otherwise.
                    # Reference: Niculescu-Mizil & Caruana (2005) — trees over-produce
                    # extreme probabilities; isotonic regression corrects this.
                    try:
                        from sklearn.calibration import CalibratedClassifierCV as _CCCV
                        _va_labels = y_va.flatten().astype(int)
                        if len(X_va) >= 15 and len(np.unique(_va_labels)) >= 2:
                            _hgbt_cal = _CCCV(_hgbt_model, method="isotonic", cv="prefit")
                            _hgbt_cal.fit(X_va, _va_labels)
                            self._hgbt = _hgbt_cal
                        else:
                            self._hgbt = _hgbt_model  # too few val samples for calibration
                    except Exception:
                        self._hgbt = _hgbt_model      # fallback: uncalibrated
                    _hgbt_va_p    = self._hgbt.predict_proba(X_va)
                    _hgbt_va_prob = _hgbt_va_p[:, 1] if _hgbt_va_p.shape[1] > 1 else _hgbt_va_p[:, 0]
                    _hgbt_va_acc  = float(np.mean(
                        (_hgbt_va_prob >= 0.5).astype(int) == y_va.flatten().astype(int)
                    ))
                    # v61.0: Adaptive blend weight — proportional to relative validation accuracy.
                    # HistGBT weight ∈ [0.20, 0.40]: if GBT val_acc > MLP val_acc it earns more
                    # weight (max 40%); if MLP wins it gets less (min 20%).  This is principled
                    # Bayesian model combination: give more credence to the better-calibrated model.
                    try:
                        _, _, _, _, _, _, _, _, _, _A4_val2 = self._forward(X_va, training=False)
                        _mlp_va_acc = float(np.mean(
                            (_A4_val2.flatten() >= self._opt_threshold).astype(int)
                            == y_va.flatten().astype(int)
                        ))
                    except Exception:
                        _mlp_va_acc = 0.50
                    _combined_acc  = max(0.01, _hgbt_va_acc + _mlp_va_acc)
                    _hgbt_w        = float(np.clip(_hgbt_va_acc / _combined_acc, 0.20, 0.40))
                    self._hgbt_weight = _hgbt_w
                    self.logger.info(
                        f"🌲 [v61.0 HistGBT] Fitted+calibrated: train={len(X_tr)} "
                        f"gbt_va={_hgbt_va_acc:.1%} mlp_va={_mlp_va_acc:.1%} "
                        f"blend=({1.0-_hgbt_w:.0%}MLP+{_hgbt_w:.0%}GBT)"
                    )
                else:
                    self._hgbt = None
            except Exception as _e_hgbt:
                self._hgbt = None
                self.logger.debug(f"[v60.0 HistGBT] skipped: {_e_hgbt}")

            # ── v63.0: ExtraTreesClassifier — 3rd ensemble member ─────────
            # ExtraTrees randomises split THRESHOLDS (not just split features),
            # making it orthogonal to both HistGBT (optimised thresholds) and
            # MLP (smooth boundaries). Captures noisy/discontinuous features
            # like RSI cliffs, ATR bands, and funding-rate step changes that
            # both MLP and HistGBT can over-smooth or over-fit.
            # Adaptive weight ∈ [0.10, 0.25] based on val_acc comparison.
            # Isotonic calibration applied when val set ≥ 15 samples.
            try:
                if n >= 30 and len(X_tr) >= 20:
                    from sklearn.ensemble import ExtraTreesClassifier as _ETC
                    _et_raw = _ETC(
                        n_estimators=80, max_depth=8, min_samples_leaf=3,
                        random_state=42, n_jobs=1, class_weight="balanced"
                    )
                    _et_raw.fit(X_tr, y_tr.flatten().astype(int))
                    self._et = None
                    if len(X_va) >= 15 and len(np.unique(y_va.flatten().astype(int))) > 1:
                        try:
                            from sklearn.calibration import CalibratedClassifierCV as _CCCV3
                            _et_cal3 = _CCCV3(_et_raw, method="isotonic", cv="prefit")
                            _et_cal3.fit(X_va, y_va.flatten().astype(int))
                            self._et = _et_cal3
                        except Exception:
                            self._et = _et_raw
                    else:
                        self._et = _et_raw
                    # Adaptive weight based on val_acc vs MLP val_acc
                    try:
                        _et_va_preds  = (self._et.predict_proba(X_va)[:, 1] >= self._opt_threshold).astype(int)
                        _et_va_acc    = float(np.mean(_et_va_preds == y_va.flatten().astype(int)))
                        _, _, _, _, _, _, _, _, _, _A4_et = self._forward(X_va, training=False)
                        _mlp_et_acc   = float(np.mean(
                            (_A4_et.flatten() >= self._opt_threshold).astype(int)
                            == y_va.flatten().astype(int)
                        ))
                        _et_comb      = max(0.01, _et_va_acc + _mlp_et_acc)
                        _et_w         = float(np.clip(_et_va_acc / _et_comb, 0.10, 0.25))
                        self._et_weight = _et_w
                        self.logger.info(
                            f"🌳 [v63.0 ExtraTrees] Fitted+calibrated: train={len(X_tr)} "
                            f"et_va={_et_va_acc:.1%} mlp_va={_mlp_et_acc:.1%} "
                            f"et_w={_et_w:.0%}"
                        )
                    except Exception:
                        self._et_weight = 0.15
                else:
                    self._et = None
            except Exception as _e_et:
                self._et = None
                self.logger.debug(f"[v63.0 ExtraTrees] skipped: {_e_et}")

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
                    # v18.92: pass time-decay sample weights to PyTorch Transformer
                    # _sw_raw was computed at top of train() — same exponential schedule
                    # as numpy MLP (oldest=1.0×, newest=2.0×, mean=1.0).
                    self._torch_predictor.fit(X_all_norm, y_all, sample_weight=_sw_raw)
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
