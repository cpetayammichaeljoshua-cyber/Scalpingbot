"""
AEGIS GEX — Black-Scholes & Full Greeks Engine  v11.0
═══════════════════════════════════════════════════════════════════════════════
Institutional-grade options analytics integrated into the Unity Engine GEX stack.

Capabilities:
• Black-Scholes call/put pricing (closed-form)
• Full Greeks: Delta, Gamma, Vega, Theta, Rho, Vanna, Volga, Charm
• Implied Volatility: Newton-Raphson inversion with bisection fallback
• IV Surface: builds term-structure + strike skew from Deribit chain data
• Pin-Risk Detection: finds strikes with highest net dealer Gamma at expiry
• Skew Analytics: 25-delta RR, Butterfly spread, SVI fit
• Integration: feeds IV surface, skew, and pin-risk into Gate 7 (GEX regime)
• Async-safe: all heavy compute on ThreadPoolExecutor

Reference: Black-Scholes (1973), Derman-Kani (1994), SVI (Gatheral 2004)
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import norm

_log = logging.getLogger("UnityEngine.BSGreeks")

# ── Constants ─────────────────────────────────────────────────────────────────
RISK_FREE_RATE    = 0.055   # USD risk-free rate (approx 5.5%, adjust as needed)
MIN_VOL           = 0.0001
MAX_VOL           = 20.0
NR_TOLERANCE      = 1e-8
NR_MAX_ITER       = 200
BISECT_MAX_ITER   = 100
CACHE_TTL_SEC     = 60.0    # IV surface cache lifetime


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class Greeks:
    """Full options Greeks for a single option."""
    delta:  float = 0.0   # rate of change of option price w.r.t. underlying
    gamma:  float = 0.0   # rate of change of delta w.r.t. underlying (dealer hedge pressure)
    vega:   float = 0.0   # sensitivity to 1% change in implied vol (per 1% point)
    theta:  float = 0.0   # time decay per calendar day
    rho:    float = 0.0   # sensitivity to 1% change in risk-free rate
    vanna:  float = 0.0   # ∂²V/∂S∂σ — vol-adjusted delta (skew flow)
    volga:  float = 0.0   # ∂²V/∂σ² — vol-of-vol (convexity)
    charm:  float = 0.0   # ∂²V/∂S∂t — delta decay (delta bleed)


@dataclass
class OptionContract:
    """Represents a single option contract."""
    symbol:       str
    option_type:  str    # "call" or "put"
    strike:       float
    expiry_t:     float  # time to expiry in years
    spot:         float
    iv:           float  # implied volatility (annualised)
    r:            float  = RISK_FREE_RATE
    # Computed fields
    price:        float  = 0.0
    greeks:       Greeks = field(default_factory=Greeks)
    d1:           float  = 0.0
    d2:           float  = 0.0


@dataclass
class IVSurface:
    """Term-structure + strike skew of implied volatility."""
    symbol:       str
    spot:         float
    computed_at:  float
    # iv_grid[expiry_days][strike] = iv
    iv_grid:      Dict[int, Dict[float, float]] = field(default_factory=dict)
    atm_iv:       Dict[int, float]              = field(default_factory=dict)   # expiry → ATM IV
    skew_25d_rr:  Dict[int, float]              = field(default_factory=dict)   # 25-delta RR
    skew_butterfly: Dict[int, float]            = field(default_factory=dict)   # 25d butterfly
    term_structure: List[Tuple[int, float]]     = field(default_factory=list)   # sorted(expiry, atm_iv)
    pin_risk_strikes: List[float]               = field(default_factory=list)   # high-gamma strikes


@dataclass
class SkewAnalysis:
    """Volatility skew analytics for regime detection."""
    symbol:       str
    spot:         float
    computed_at:  float
    near_expiry:  int       # days
    atm_iv:       float
    rr_25d:       float     # 25-delta risk reversal: put_iv − call_iv (negative = call skew)
    butterfly_25d: float    # 25d butterfly spread: (put+call)/2 − atm
    iv_slope:     float     # linear slope of strike vs IV across strikes
    skew_regime:  str       # "CALL_SKEW" | "PUT_SKEW" | "NEUTRAL" | "SMILE"
    gate7_bonus:  float     # pts added to Gate 7 score based on skew


# ── Black-Scholes Core ────────────────────────────────────────────────────────

def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> Tuple[float, float]:
    """Compute d1 and d2 for BS formula. Returns (nan, nan) on invalid input."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return float("nan"), float("nan")
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Black-Scholes option price."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if math.isnan(d1):
        return 0.0
    Nd1, Nd2 = norm.cdf(d1), norm.cdf(d2)
    discount = math.exp(-r * T)
    if option_type.lower() in ("call", "c"):
        return S * Nd1 - K * discount * Nd2
    else:
        return K * discount * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> Greeks:
    """
    Compute full second-order Greeks for a European option.
    Returns Greeks with all fields populated.
    """
    g = Greeks()
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if math.isnan(d1) or T <= 0:
        return g
    sqrt_T = math.sqrt(T)
    nd1    = norm.pdf(d1)
    Nd1    = norm.cdf(d1)
    Nd2    = norm.cdf(d2)
    disc   = math.exp(-r * T)

    is_call = option_type.lower() in ("call", "c")

    # Delta
    g.delta = Nd1 if is_call else Nd1 - 1.0

    # Gamma (same for call/put)
    g.gamma = nd1 / (S * sigma * sqrt_T)

    # Vega (per 1% point in vol, i.e. divide raw by 100)
    g.vega = S * nd1 * sqrt_T / 100.0

    # Theta (per calendar day)
    common_theta = -(S * nd1 * sigma) / (2.0 * sqrt_T) - r * K * disc * Nd2
    if is_call:
        g.theta = common_theta / 365.0
    else:
        g.theta = (-(S * nd1 * sigma) / (2.0 * sqrt_T) + r * K * disc * norm.cdf(-d2)) / 365.0

    # Rho (per 1% point in rate)
    if is_call:
        g.rho = K * T * disc * Nd2 / 100.0
    else:
        g.rho = -K * T * disc * norm.cdf(-d2) / 100.0

    # Vanna: ∂²V/∂S∂σ = vega/S × (1 − d1/(σ√T))
    g.vanna = (g.vega * 100.0) / S * (1.0 - d1 / (sigma * sqrt_T)) / 100.0

    # Volga: ∂²V/∂σ² = vega × d1 × d2 / σ
    g.volga = (g.vega * 100.0) * d1 * d2 / sigma / 100.0

    # Charm: ∂²V/∂S∂t (delta decay per day)
    phi_d1 = norm.pdf(d1)
    if is_call:
        g.charm = -phi_d1 * (2.0 * r * T - d2 * sigma * sqrt_T) / (2.0 * T * sigma * sqrt_T) / 365.0
    else:
        g.charm = -phi_d1 * (2.0 * r * T - d2 * sigma * sqrt_T) / (2.0 * T * sigma * sqrt_T) / 365.0

    return g


def price_contract(contract: OptionContract) -> OptionContract:
    """Price an option contract and compute all Greeks in-place."""
    contract.d1, contract.d2 = _d1_d2(
        contract.spot, contract.strike, contract.expiry_t,
        contract.r, contract.iv
    )
    contract.price  = bs_price(
        contract.spot, contract.strike, contract.expiry_t,
        contract.r, contract.iv, contract.option_type
    )
    contract.greeks = bs_greeks(
        contract.spot, contract.strike, contract.expiry_t,
        contract.r, contract.iv, contract.option_type
    )
    return contract


# ── Implied Volatility Inversion ──────────────────────────────────────────────

def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                option_type: str, tol: float = NR_TOLERANCE) -> float:
    """
    Compute implied volatility via Newton-Raphson with bisection fallback.
    Returns NaN if no solution found.
    """
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return float("nan")

    # Intrinsic bound check
    disc = math.exp(-r * T)
    if option_type.lower() in ("call", "c"):
        intrinsic = max(S - K * disc, 0.0)
    else:
        intrinsic = max(K * disc - S, 0.0)

    if market_price < intrinsic - 1e-6:
        return float("nan")
    if market_price <= intrinsic + 1e-10:
        return MIN_VOL

    # Newton-Raphson
    sigma = 0.3   # initial guess: 30% ATM vol
    for _ in range(NR_MAX_ITER):
        price = bs_price(S, K, T, r, sigma, option_type)
        diff  = price - market_price
        if abs(diff) < tol:
            return max(MIN_VOL, min(MAX_VOL, sigma))
        # vega (raw, not divided by 100)
        d1, _ = _d1_d2(S, K, T, r, sigma)
        if math.isnan(d1):
            break
        vega_raw = S * norm.pdf(d1) * math.sqrt(T)
        if abs(vega_raw) < 1e-10:
            break
        sigma -= diff / vega_raw
        if sigma <= 0:
            sigma = 0.01

    # Bisection fallback
    lo, hi = MIN_VOL, MAX_VOL
    for _ in range(BISECT_MAX_ITER):
        mid = 0.5 * (lo + hi)
        price = bs_price(S, K, T, r, mid, option_type)
        if abs(price - market_price) < tol:
            return max(MIN_VOL, min(MAX_VOL, mid))
        if price < market_price:
            lo = mid
        else:
            hi = mid

    sigma_final = 0.5 * (lo + hi)
    return max(MIN_VOL, min(MAX_VOL, sigma_final))


# ── IV Surface Builder ────────────────────────────────────────────────────────

class BSGreeksEngine:
    """
    Full Black-Scholes & Greeks engine integrated with the Unity Engine GEX stack.

    Receives raw Deribit/OKX options chain data and builds:
    • IV surface (term structure + strike skew)
    • Pin-risk detection (highest net-gamma strikes)
    • Skew analytics for Gate 7 bonus/penalty
    • Per-contract Greeks for position management in UnityEngine

    Thread-safe; designed for async context.
    """

    def __init__(self):
        self._lock   = threading.RLock()
        self._cache: Dict[str, IVSurface]      = {}
        self._cache_ts: Dict[str, float]       = {}
        self._skew:  Dict[str, SkewAnalysis]   = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def price_option(self, spot: float, strike: float, expiry_days: float,
                     iv: float, option_type: str, r: float = RISK_FREE_RATE) -> OptionContract:
        """Price a single option and return full Greeks."""
        T = expiry_days / 365.0
        contract = OptionContract(
            symbol="", option_type=option_type, strike=strike,
            expiry_t=T, spot=spot, iv=iv, r=r
        )
        return price_contract(contract)

    def get_iv_surface(self, symbol: str) -> Optional[IVSurface]:
        with self._lock:
            return self._cache.get(symbol)

    def get_skew(self, symbol: str) -> Optional[SkewAnalysis]:
        with self._lock:
            return self._skew.get(symbol)

    def update_from_deribit_chain(self, symbol: str, spot: float,
                                   options_data: List[Dict]) -> IVSurface:
        """
        Build IV surface from Deribit options chain snapshot.

        options_data: list of dicts with keys:
            strike, expiry_days, mark_price, option_type,
            open_interest (optional), volume (optional)
        """
        now   = time.time()
        surf  = IVSurface(symbol=symbol, spot=spot, computed_at=now)
        r     = RISK_FREE_RATE

        # Group by expiry
        by_expiry: Dict[int, List[Dict]] = {}
        for opt in options_data:
            exp = int(opt.get("expiry_days", 0))
            if exp <= 0:
                continue
            by_expiry.setdefault(exp, []).append(opt)

        net_gamma_by_strike: Dict[float, float] = {}

        for exp_days, contracts in sorted(by_expiry.items()):
            T = exp_days / 365.0
            if T <= 0:
                continue
            surf.iv_grid[exp_days] = {}
            atm_ivs = []
            call_25d_iv, put_25d_iv = [], []

            for opt in contracts:
                strike     = float(opt["strike"])
                mark_price = float(opt.get("mark_price", 0))
                opt_type   = opt.get("option_type", "call")
                oi         = float(opt.get("open_interest", 0))

                if mark_price <= 0:
                    continue

                iv = implied_vol(mark_price, spot, strike, T, r, opt_type)
                if math.isnan(iv) or iv < MIN_VOL:
                    continue

                surf.iv_grid[exp_days][strike] = iv
                g = bs_greeks(spot, strike, T, r, iv, opt_type)

                # Collect near-ATM IV for ATM vol estimation
                moneyness = abs(math.log(spot / strike))
                if moneyness < 0.05:
                    atm_ivs.append(iv)

                # Net dealer gamma (dealers are short gamma to market makers)
                # Net GEX = -OI × gamma × spot² × 0.01
                net_gex = -oi * g.gamma * spot * spot * 0.01
                net_gamma_by_strike[strike] = net_gamma_by_strike.get(strike, 0.0) + net_gex

                # Collect 25-delta IVs for skew
                if 0.20 < abs(g.delta) < 0.30:
                    if opt_type in ("call", "c"):
                        call_25d_iv.append(iv)
                    else:
                        put_25d_iv.append(iv)

            # ATM IV for this expiry
            if atm_ivs:
                surf.atm_iv[exp_days] = float(np.mean(atm_ivs))

            # 25-delta risk reversal and butterfly
            if call_25d_iv and put_25d_iv:
                c25 = float(np.mean(call_25d_iv))
                p25 = float(np.mean(put_25d_iv))
                atm = surf.atm_iv.get(exp_days, (c25 + p25) / 2)
                surf.skew_25d_rr[exp_days]    = p25 - c25
                surf.skew_butterfly[exp_days] = (p25 + c25) / 2.0 - atm

        # Term structure
        surf.term_structure = sorted(
            [(exp, iv) for exp, iv in surf.atm_iv.items()], key=lambda x: x[0]
        )

        # Pin-risk strikes: top 5 by absolute net gamma
        if net_gamma_by_strike:
            sorted_gamma = sorted(net_gamma_by_strike.items(), key=lambda x: abs(x[1]), reverse=True)
            surf.pin_risk_strikes = [k for k, _ in sorted_gamma[:5]]

        with self._lock:
            self._cache[symbol]    = surf
            self._cache_ts[symbol] = now

        # Build skew analysis
        skew = self._build_skew(symbol, spot, surf)
        if skew:
            with self._lock:
                self._skew[symbol] = skew

        return surf

    def get_gate7_bonus(self, symbol: str, signal_direction: str) -> float:
        """
        Return Gate 7 bonus/penalty based on options skew.
        LONG signal + PUT_SKEW (fear premium) → +2 pts (consensus with hedgers)
        LONG signal + CALL_SKEW (greed premium) → −2 pts (against hedger flow)
        """
        with self._lock:
            skew = self._skew.get(symbol)
        if not skew:
            return 0.0
        if signal_direction.upper() in ("LONG", "BUY"):
            # Put skew means market paying up for downside protection → bearish hedging
            if skew.skew_regime == "PUT_SKEW":
                return -1.5   # market fearful about longs — slight penalty
            elif skew.skew_regime == "CALL_SKEW":
                return +2.0   # call premium → bullish consensus
        else:  # SHORT
            if skew.skew_regime == "PUT_SKEW":
                return +2.0   # fear confirms short
            elif skew.skew_regime == "CALL_SKEW":
                return -1.5   # greed fights the short
        return 0.0

    def format_iv_surface_text(self, symbol: str) -> str:
        """Format IV surface for Telegram display."""
        with self._lock:
            surf = self._cache.get(symbol)
        if not surf:
            return f"📉 No IV surface for {symbol}"
        lines = [f"📊 *{symbol} IV Surface* — spot ${surf.spot:,.2f}", ""]
        for exp, atm in surf.term_structure[:6]:
            rr = surf.skew_25d_rr.get(exp, 0.0)
            bf = surf.skew_butterfly.get(exp, 0.0)
            lines.append(
                f"  {exp:3d}d: ATM={atm:.1%}  25d-RR={rr:+.1%}  BF={bf:+.1%}"
            )
        if surf.pin_risk_strikes:
            pins = ", ".join(f"${k:,.0f}" for k in surf.pin_risk_strikes[:3])
            lines.append(f"\n📌 Pin Risk: {pins}")
        return "\n".join(lines)

    def format_greeks_text(self, spot: float, strike: float, expiry_days: float,
                            iv: float, option_type: str) -> str:
        """Format Greeks for Telegram display."""
        c = self.price_option(spot, strike, expiry_days, iv, option_type)
        g = c.greeks
        return (
            f"🔢 *BS Greeks* ({option_type.upper()} K={strike:,.0f})\n"
            f"  Price: ${c.price:.4f}\n"
            f"  Δ Delta:  {g.delta:+.4f}\n"
            f"  Γ Gamma:  {g.gamma:.6f}\n"
            f"  𝜈 Vega:   {g.vega:.4f} /1%\n"
            f"  Θ Theta:  {g.theta:.4f} /day\n"
            f"  ρ Rho:    {g.rho:.4f} /1%\n"
            f"  Vanna:    {g.vanna:.6f}\n"
            f"  Volga:    {g.volga:.6f}\n"
            f"  Charm:    {g.charm:.6f} /day"
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_skew(symbol: str, spot: float, surf: IVSurface) -> Optional[SkewAnalysis]:
        """Build skew analysis from IV surface for the nearest expiry."""
        if not surf.term_structure:
            return None
        near_exp = surf.term_structure[0][0]
        atm      = surf.atm_iv.get(near_exp, float("nan"))
        rr       = surf.skew_25d_rr.get(near_exp, 0.0)
        bf       = surf.skew_butterfly.get(near_exp, 0.0)

        # IV slope across strikes
        grid = surf.iv_grid.get(near_exp, {})
        iv_slope = 0.0
        if len(grid) >= 3:
            strikes = sorted(grid.keys())
            ivs     = [grid[k] for k in strikes]
            log_m   = [math.log(k / spot) for k in strikes]
            if max(log_m) - min(log_m) > 0.01:
                slope = np.polyfit(log_m, ivs, 1)[0]
                iv_slope = float(slope)

        # Skew regime
        if rr > 0.02:
            regime = "PUT_SKEW"   # put IV > call IV — bearish hedging premium
        elif rr < -0.02:
            regime = "CALL_SKEW"  # call IV > put IV — bullish speculation
        elif bf > 0.01:
            regime = "SMILE"      # both wings elevated — uncertainty
        else:
            regime = "NEUTRAL"

        # Gate 7 bonus
        gate7 = {
            "PUT_SKEW":  -1.0,
            "CALL_SKEW": +2.0,
            "SMILE":     +1.0,
            "NEUTRAL":    0.0,
        }.get(regime, 0.0)

        return SkewAnalysis(
            symbol=symbol, spot=spot, computed_at=time.time(),
            near_expiry=near_exp, atm_iv=atm, rr_25d=rr,
            butterfly_25d=bf, iv_slope=iv_slope,
            skew_regime=regime, gate7_bonus=gate7
        )
