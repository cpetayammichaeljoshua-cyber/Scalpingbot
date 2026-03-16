#!/usr/bin/env python3
"""
NeuralSignalTrainer — Self-learning signal quality filter for MiroFish Swarm.

Architecture  : 40-feature input → Dense(128, ReLU) → Dense(64, ReLU)
                → Dense(32, ReLU) → Dense(1, Sigmoid)
Optimizer     : Adam with L2 regularisation + dropout (training only)
Loss          : Focal BCE with dynamic class-weighting (adapts to actual W/L ratio)
Persistence   : Weights saved as JSON — survives bot restarts with full warm-start
Training data : Labeled trades from TradeMemory (TP1/TP2/TP3 = win, SL = loss)
Output        : win_probability ∈ [0, 1] for any SwarmSignal

Architecture v2 (40-feature, 4-layer):
  • Expanded from 30 → 40 features: 10 new non-linear interaction & regime terms
  • Wider hidden layers (64/32/16 → 128/64/32) for greater model capacity
  • New features capture: RSI-direction alignment, BB-direction alignment,
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
import time
import logging
from typing import List, Dict, Optional, Tuple

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "nn_weights.json")

MIN_TRAIN_SAMPLES = 20   # minimum labeled trades before NN activates
INPUT_DIM        = 40    # v2 expanded: +10 interaction/regime features over v1 30-feature set

# Agent order — all 8 votes used as features
AGENT_ORDER = [
    "TrendAgent", "MomentumAgent", "VolumeAgent",
    "VolatilityAgent", "OrderFlowAgent", "SentimentAgent",
    "FundingFlowAgent", "AIOrchestrationAgent",
]
_SESSION = {"ASIAN": 0.0, "EU": 0.33, "US": 1.0, "TRANSITION": 0.17}
_VOTE    = {"BUY": 1.0, "SELL": -1.0, "NEUTRAL": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering  (40 features — v2)
# ─────────────────────────────────────────────────────────────────────────────

def build_features(trade: Dict) -> "np.ndarray":
    """
    40-feature normalised vector from a trade record dict (v2 — expanded from 30).

    Features 1-12:  scalar signal quality indicators
    Features 13-16: time / leverage encoding
    Features 17-24: all 8 agent votes [-1, 0, +1]
    Features 25-26: derived consensus metrics (agreement fraction, purity)
    Features 27-28: RSI regime flags (overbought / oversold binary)
    Features 29-30: Bollinger Band extreme zone flags (upper / lower extreme)
    Features 31-40: v2 non-linear interaction & regime terms
      31 — RSI strength aligned to direction  (punishes counter-RSI signals)
      32 — BB position aligned to direction   (punishes counter-BB signals)
      33 — confidence × consensus product     (joint quality gate interaction)
      34 — R:R quadratic scaling              (super-linear reward for high R:R)
      35 — participation rate squared         (super-linear reward for quorum)
      36 — consensus cubed                    (strongly amplifies near-unanimous)
      37 — log-normalised volume ratio        (handles vol spikes non-linearly)
      38 — ATR ratio quadratic                (super-linear for high volatility)
      39 — sub-day cosine cycle               (captures intra-session 6h rhythm)
      40 — RSI trap risk aligned to direction (warns of exhaustion in direction)
    """
    if not _HAS_NUMPY:
        raise ImportError("numpy required for neural signal trainer")

    votes = json.loads(trade.get("agent_votes_json", "{}"))
    # All 8 agent votes (FundingFlow + AI now included, not just first 6)
    agent_feats = [_VOTE.get(votes.get(a, "NEUTRAL"), 0.0) for a in AGENT_ORDER]

    direction = 1.0 if trade.get("action", "BUY") == "BUY" else -1.0
    session   = _SESSION.get((trade.get("session") or "US").upper(), 1.0)

    rsi        = float(trade.get("rsi", 50.0))
    hour       = float(trade.get("hour_of_day", 12))
    leverage   = float(trade.get("leverage", 10))
    bb_pos     = float(trade.get("bb_position", 0.5))
    confidence = float(trade.get("confidence", 70.0)) / 100.0
    consensus  = float(trade.get("swarm_consensus", 0.75))
    vol_ratio  = float(trade.get("volume_ratio", 1.0))
    rr         = float(trade.get("risk_reward_ratio", 1.5))
    atr_ratio  = float(trade.get("atr_ratio", 0.003))
    part_rate  = float(trade.get("participation_rate", 0.625))

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
        float(trade.get("signal_strength",     65.0)) / 100.0,          # 3
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
    ] + agent_feats + [                                                   # 17-24 all 8 agent votes

        # ── Derived consensus metrics (25-26) ────────────────────────────────
        agreement_frac,                                                   # 25 direction agreement [0,1]
        consensus_purity,                                                 # 26 dominant-side purity [0,1]

        # ── RSI regime flags (27-28) ─────────────────────────────────────────
        rsi_overbought,                                                   # 27 1 if RSI>70 (OB trap risk)
        rsi_oversold,                                                     # 28 1 if RSI<30 (OS trap risk)

        # ── Bollinger Band extreme zone flags (29-30) ────────────────────────
        bb_upper_extreme,                                                 # 29 1 if price near upper BB
        bb_lower_extreme,                                                 # 30 1 if price near lower BB

        # ── v2 Non-linear interaction & regime features (31-40) ──────────────
        rsi_aligned,                                                      # 31 RSI aligned to direction
        bb_aligned,                                                       # 32 BB pos aligned to direction
        conf_x_consensus,                                                 # 33 confidence × consensus
        rr_quadratic,                                                     # 34 R:R quadratic
        part_sq,                                                          # 35 participation squared
        consensus_cubed,                                                  # 36 consensus cubed
        vol_log,                                                          # 37 log vol ratio
        atr_quad,                                                         # 38 ATR quadratic
        hour_cos2,                                                        # 39 sub-day cosine (6h)
        rsi_trap,                                                         # 40 RSI trap risk aligned
    ]

    arr = np.array(f, dtype=np.float32)
    if arr.shape[0] != INPUT_DIM:
        raise ValueError(f"Feature shape {arr.shape[0]} ≠ {INPUT_DIM}")
    return arr


def build_label(trade: Dict) -> float:
    """1.0 = any TP hit (profitable), 0.0 = SL or expired without profit."""
    outcome = (trade.get("outcome") or "EXPIRED").upper()
    if outcome in ("TP1", "TP2", "TP3"):
        return 1.0
    if outcome == "SL":
        return 0.0
    return 1.0 if (trade.get("pnl_pct") or 0.0) > 0 else 0.0


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

    def fit(self, X: "np.ndarray", y: "np.ndarray"):
        """
        Compute per-feature loss patterns from training data.

        X: (N, INPUT_DIM) feature matrix
        y: (N,) binary labels (1=win, 0=loss)
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

            # Danger zones: for each feature, find percentile bands with loss_rate > 60%
            self.danger_zones = []
            n_bins = 10
            for fi in range(INPUT_DIM):
                col   = X[:, fi]
                col_y = y
                edges = np.percentile(col, np.linspace(0, 100, n_bins + 1))
                for bi in range(n_bins):
                    lo, hi = edges[bi], edges[bi + 1]
                    mask = (col >= lo) & (col <= hi)
                    if mask.sum() < 3:
                        continue
                    loss_rate = 1.0 - col_y[mask].mean()
                    if loss_rate > 0.65:  # 65%+ loss rate in this bin = danger zone
                        self.danger_zones.append((fi, float(lo), float(hi), float(loss_rate)))

            self.is_fitted = True
        except Exception:
            pass

    def danger_penalty(self, x: "np.ndarray") -> float:
        """
        Return a penalty [0, 0.15] to subtract from win_probability for signals
        that fall inside known danger zones.  Higher = more dangerous pattern.
        """
        if not self.is_fitted or not self.danger_zones:
            return 0.0
        try:
            penalty = 0.0
            for fi, lo, hi, loss_rate in self.danger_zones:
                if lo <= x[fi] <= hi:
                    # Weight by feature importance
                    imp = min(self.feature_importance[fi], 3.0) / 3.0
                    penalty += (loss_rate - 0.65) * imp * 0.5
            return min(penalty, 0.15)
        except Exception:
            return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# NeuralSignalTrainer
# ─────────────────────────────────────────────────────────────────────────────

class NeuralSignalTrainer:
    """
    Three-hidden-layer MLP (v2 wider) trained with mini-batch Adam + focal BCE loss.

    Forward:  X(N,40) → Z1=X·W1+b1 → A1=ReLU(Z1) → [dropout]
                      → Z2=A1·W2+b2 → A2=ReLU(Z2) → [dropout]
                      → Z3=A2·W3+b3 → A3=ReLU(Z3)
                      → Z4=A3·W4+b4 → out=σ(Z4)  (N,1)

    Architecture v2: 40→128→64→32→1
      • 40 input features (v1 had 30; +10 non-linear interaction & regime terms)
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
    _MC_PASSES = 20
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
        # reject_threshold: signals below this are rejected.
        # boost_threshold:  signals above this get a confidence boost.
        self._opt_threshold    = 0.50   # default; overwritten after each training run
        self._reject_threshold = 0.40   # lower bound (never below this)
        self._boost_threshold  = 0.70   # upper bound (only boost above this)

        # FIX 4: Feature normalisation statistics (fit on training data).
        self._feat_mean: Optional["np.ndarray"] = None
        self._feat_std:  Optional["np.ndarray"] = None
        self._feat_fitted = False

        # Loss pattern analyzer
        self.loss_analyzer = LossPatternAnalyzer()

        if not _HAS_NUMPY:
            self.logger.warning("⚠️  numpy not found — NeuralSignalTrainer disabled")
            return

        self._xavier_init()
        self._load_weights()

    # ── Weight initialisation ─────────────────────────────────────────────

    def _xavier_init(self):
        rng = np.random.default_rng(42)

        def _w(fan_in, fan_out):
            # He initialisation for ReLU activations (fan_in only) — better than
            # Xavier for deep ReLU networks as it accounts for the dead-neuron effect
            s = np.sqrt(2.0 / fan_in)
            return rng.normal(0, s, (fan_in, fan_out)).astype(np.float32)

        # v2 architecture: 40 → 128 → 64 → 32 → 1  (wider + deeper capacity)
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
        Focal Binary Cross-Entropy loss with dynamic class weighting.

        For each sample:
          • If y_true == 1 (win):  weight = 1.0,  p_t = y_pred,       focal = (1-p_t)^γ
          • If y_true == 0 (loss): weight = α,    p_t = 1 - y_pred,   focal = (1-p_t)^γ

        Loss = -weight * focal * log(p_t + ε)

        α = n_wins / n_losses (computed dynamically at training time, clamped 1–5).
        """
        _eps = 1e-7
        γ = self.focal_gamma
        α = self.class_weight_loss  # set dynamically in train()

        p = np.clip(y_pred, _eps, 1.0 - _eps)

        # p_t: probability of correct class
        p_t     = np.where(y_true == 1, p, 1.0 - p)
        weight  = np.where(y_true == 1, 1.0, α)
        focal_w = (1.0 - p_t) ** γ

        loss = -weight * focal_w * np.log(p_t)
        return loss  # shape (N, 1)

    # ── Optimal threshold computation ─────────────────────────────────────

    def _compute_optimal_threshold(self, X_val: "np.ndarray",
                                   y_val: "np.ndarray") -> float:
        """
        Compute optimal binary classification threshold on validation data
        using Youden's J statistic: J = TPR + TNR - 1 (maximise balanced accuracy).

        Returns threshold in [0.25, 0.75] clamped for safety.
        Falls back to 0.50 on any error.
        """
        try:
            _, _, _, _, _, _, _, _, _, A4v = self._forward(X_val, training=False)
            probs = A4v.flatten()
            y_flat = y_val.flatten()

            best_thresh = 0.50
            best_j      = -1.0
            for t in np.arange(0.25, 0.76, 0.025):
                preds = (probs >= t).astype(int)
                tp = int(np.sum((preds == 1) & (y_flat == 1)))
                tn = int(np.sum((preds == 0) & (y_flat == 0)))
                fp = int(np.sum((preds == 1) & (y_flat == 0)))
                fn = int(np.sum((preds == 0) & (y_flat == 1)))
                tpr = tp / max(tp + fn, 1)
                tnr = tn / max(tn + fp, 1)
                j = tpr + tnr - 1.0
                if j > best_j:
                    best_j = j
                    best_thresh = float(t)

            # Derived reject / boost thresholds around optimal
            self._reject_threshold = max(0.25, best_thresh - 0.10)
            self._boost_threshold  = min(0.75, best_thresh + 0.10)
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
                "participation_rate": getattr(signal, "participation_rate", 0.875),
                "rsi":                signal.rsi,
                "volume_ratio":       signal.volume_ratio,
                "risk_reward_ratio":  signal.risk_reward_ratio,
                "atr_ratio":          atr_ratio,
                "bb_position":        bb_position,
                "hour_of_day":        signal.timestamp.hour if signal.timestamp else 12,
                "session":            getattr(signal, "market_session", "US"),
                "agent_votes_json":   json.dumps(signal.agent_votes or {}),
                "leverage":           getattr(signal, "leverage", 10),
            }
            X_raw = build_features(rec).reshape(1, -1)
            X_norm = self._normalise(X_raw)
            base_prob = float(self.predict_batch(X_raw)[0])  # predict_batch normalises inside

            # Apply loss-pattern penalty
            if self.loss_analyzer.is_fitted:
                penalty = self.loss_analyzer.danger_penalty(X_norm[0])
                base_prob = max(0.0, base_prob - penalty)

            return base_prob
        except Exception as e:
            self.logger.debug(f"predict_signal error: {e}")
            return 0.5

    def predict_signal_with_uncertainty(self, signal, bb_position: float = 0.5,
                                        n_passes: int = _MC_PASSES
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
                "participation_rate": getattr(signal, "participation_rate", 0.875),
                "rsi":                signal.rsi,
                "volume_ratio":       signal.volume_ratio,
                "risk_reward_ratio":  signal.risk_reward_ratio,
                "atr_ratio":          atr_ratio,
                "bb_position":        bb_position,
                "hour_of_day":        signal.timestamp.hour if signal.timestamp else 12,
                "session":            getattr(signal, "market_session", "US"),
                "agent_votes_json":   json.dumps(signal.agent_votes or {}),
                "leverage":           getattr(signal, "leverage", 10),
            }
            X_raw  = build_features(rec).reshape(1, -1)
            X_norm = self._normalise(X_raw)
            mean_arr, std_arr = self.predict_mc(X_norm, n_passes=n_passes)
            mean_p = float(mean_arr[0])
            std_p  = float(std_arr[0])

            # Apply loss-pattern penalty to mean prediction
            if self.loss_analyzer.is_fitted:
                penalty = self.loss_analyzer.danger_penalty(X_norm[0])
                mean_p = max(0.0, mean_p - penalty)

            return mean_p, std_p
        except Exception as e:
            self.logger.debug(f"predict_signal_with_uncertainty error: {e}")
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
        Computes optimal decision threshold from validation data (Youden's J).
        """
        if not _HAS_NUMPY:
            return {"status": "disabled", "reason": "numpy not available"}

        if len(trades) < MIN_TRAIN_SAMPLES:
            return {"status": "skipped", "reason": f"only {len(trades)} samples (need {MIN_TRAIN_SAMPLES})"}

        t0 = time.time()
        try:
            X_all = np.array([build_features(t) for t in trades], dtype=np.float32)
            y_all = np.array([build_label(t)    for t in trades], dtype=np.float32).reshape(-1, 1)

            wins   = int(np.sum(y_all == 1))
            losses = int(np.sum(y_all == 0))

            # FIX 7: Dynamic class weight — adapt to actual W/L ratio.
            # Penalise the minority class proportionally (clamped 1.0–5.0).
            # Previously fixed at 2.0 regardless of actual data distribution.
            if losses > 0 and wins > 0:
                dynamic_weight = float(wins) / float(losses)
                self.class_weight_loss = float(np.clip(dynamic_weight, 1.0, 5.0))
            else:
                self.class_weight_loss = self._default_class_weight_loss
            self.logger.info(
                f"🔢 Dynamic class weight: {self.class_weight_loss:.2f}x "
                f"(W={wins} L={losses})"
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
            # Normalise full dataset for final accuracy + loss-pattern fitting
            X_all_norm = self._normalise(X_all)

            if not (warm_restart and self.trained):
                self._xavier_init()
                # Reset base LR on cold restart so cosine schedule starts fresh
                self._base_lr = self.lr if self.lr > 1e-5 else 0.001

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
                    _eps = 1e-7
                    γ    = self.focal_gamma
                    α    = self.class_weight_loss

                    p    = np.clip(A4, _eps, 1.0 - _eps)
                    p_t  = np.where(yb == 1, p, 1.0 - p)
                    wt   = np.where(yb == 1, 1.0, α)
                    focal_w = (1.0 - p_t) ** γ

                    # d(focal_BCE)/d(A4): chain rule through focal weight
                    d_pt_dp = np.where(yb == 1, 1.0, -1.0)
                    grad_p = wt * (
                        γ * (1.0 - p_t) ** (γ - 1) * np.log(p_t + _eps)
                        - (1.0 - p_t) ** γ / (p_t + _eps)
                    ) * d_pt_dp
                    # Through sigmoid: dA4/dZ4 = A4*(1-A4)
                    dZ4 = grad_p * A4 * (1.0 - A4) / m

                    dW4 = (A3.T @ dZ4) + self.l2 * self.W4
                    db4 = np.mean(dZ4, axis=0, keepdims=True)

                    dA3 = dZ4 @ self.W4.T
                    dZ3 = dA3 * self._relu_d(Z3)
                    dW3 = (A2.T @ dZ3) / m + self.l2 * self.W3
                    db3 = np.mean(dZ3, axis=0, keepdims=True)

                    dA2 = dZ3 @ self.W3.T
                    if mask2 is not None:
                        dA2 = dA2 * mask2
                    dZ2 = dA2 * self._relu_d(Z2)
                    dW2 = (A1.T @ dZ2) / m + self.l2 * self.W2
                    db2 = np.mean(dZ2, axis=0, keepdims=True)

                    dA1 = dZ2 @ self.W2.T
                    if mask1 is not None:
                        dA1 = dA1 * mask1
                    dZ1 = dA1 * self._relu_d(Z1)
                    dW1 = (Xb.T @ dZ1) / m + self.l2 * self.W1
                    db1 = np.mean(dZ1, axis=0, keepdims=True)

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

            # FIX 5: Compute optimal decision threshold from validation data
            self._opt_threshold = self._compute_optimal_threshold(X_va, y_va)
            self.logger.info(
                f"🎯 Optimal NN threshold: {self._opt_threshold:.3f} "
                f"(reject<{self._reject_threshold:.3f} boost>{self._boost_threshold:.3f})"
            )

            # Full-dataset accuracy at optimal threshold
            _, _, _, _, _, _, _, _, _, A4_all = self._forward(X_all_norm, training=False)
            preds  = (A4_all.flatten() >= self._opt_threshold).astype(int)
            y_flat = y_all.flatten().astype(int)
            acc    = float(np.mean(preds == y_flat))

            # Per-class accuracy (crucial for loss-prevention)
            win_acc  = float(np.mean(preds[y_flat == 1] == 1)) if wins  > 0 else 0.0
            loss_acc = float(np.mean(preds[y_flat == 0] == 0)) if losses > 0 else 0.0

            self.trained           = True
            self.n_samples_trained = len(trades)
            self.last_train_time   = time.time()
            self.last_accuracy     = acc
            self.last_val_loss     = best_val
            self.last_win_rate     = wins  / n if n > 0 else 0.0
            self.last_loss_rate    = losses / n if n > 0 else 0.0

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
        if not _HAS_NUMPY:
            return
        try:
            data = {
                "W1": self.W1.tolist(), "b1": self.b1.tolist(),
                "W2": self.W2.tolist(), "b2": self.b2.tolist(),
                "W3": self.W3.tolist(), "b3": self.b3.tolist(),
                "W4": self.W4.tolist(), "b4": self.b4.tolist(),
                "n_samples_trained":   self.n_samples_trained,
                "last_train_time":     self.last_train_time,
                "last_accuracy":       self.last_accuracy,
                "last_val_loss":       self.last_val_loss,
                "last_win_rate":       self.last_win_rate,
                "last_loss_rate":      self.last_loss_rate,
                "_t":                  self._t,
                "_base_lr":            self._base_lr,
                "class_weight_loss":   self.class_weight_loss,
                # FIX 5: persist threshold
                "_opt_threshold":      self._opt_threshold,
                "_reject_threshold":   self._reject_threshold,
                "_boost_threshold":    self._boost_threshold,
                # FIX 4: persist normalisation stats
                "_feat_mean":  self._feat_mean.tolist()  if self._feat_mean  is not None else None,
                "_feat_std":   self._feat_std.tolist()   if self._feat_std   is not None else None,
                "_feat_fitted": self._feat_fitted,
                # Persist loss analyzer state
                "danger_zones":        self.loss_analyzer.danger_zones,
                "feature_importance":  self.loss_analyzer.feature_importance,
                "win_means":  self.loss_analyzer.win_means.tolist()  if self.loss_analyzer.win_means  is not None else None,
                "loss_means": self.loss_analyzer.loss_means.tolist() if self.loss_analyzer.loss_means is not None else None,
            }
            with open(WEIGHTS_PATH, "w") as f:
                json.dump(data, f)
            self.logger.debug(f"💾 NN weights saved → {WEIGHTS_PATH}")
        except Exception as e:
            self.logger.warning(f"Weight save failed: {e}")

    def _load_weights(self):
        if not _HAS_NUMPY or not os.path.exists(WEIGHTS_PATH):
            return
        try:
            with open(WEIGHTS_PATH) as f:
                d = json.load(f)

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

            # FIX 7: Restore dynamic class weight
            self.class_weight_loss = float(d.get("class_weight_loss", self._default_class_weight_loss))

            # FIX 5: Restore optimal thresholds
            self._opt_threshold    = float(d.get("_opt_threshold",    0.50))
            self._reject_threshold = float(d.get("_reject_threshold", 0.40))
            self._boost_threshold  = float(d.get("_boost_threshold",  0.70))

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
                self.loss_analyzer.is_fitted = True

            if self.n_samples_trained >= MIN_TRAIN_SAMPLES:
                self.trained = True
                self.logger.info(
                    f"🧠 NN weights loaded | {self.n_samples_trained} samples | "
                    f"acc={self.last_accuracy:.1%} | "
                    f"thresh={self._opt_threshold:.3f} | "
                    f"class_w={self.class_weight_loss:.2f} | "
                    f"danger_zones={len(self.loss_analyzer.danger_zones)}"
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
        return (
            f"NN: trained | {self.n_samples_trained} samples | "
            f"acc={self.last_accuracy:.1%} | "
            f"W/L split={win_acc:.1%}/{1.0-win_acc:.1%} | "
            f"class_w={self.class_weight_loss:.2f}x | "
            f"thresh={self._opt_threshold:.3f} | "
            f"danger_zones={dz} | "
            f"last trained {age_h:.1f}h ago"
        )
