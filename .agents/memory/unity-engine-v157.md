---
name: Unity Engine v157.0 upgrades
description: G8.5AA CWD Confidence-WR Divergence Penalty (138th gate, -1.5/-1.0pts anti-signal) + Kelly Step 132 Near-GXPR De-size (×0.78 at 45-65% near-zero pnl rate); v156→v157
---

## Changes in v157.0

### G8.5AA — CWD: Confidence-WR Divergence Penalty (Phase 2.02, 138th scoring gate)

**Source: confirmed anti-signal from 2,798 resolved live trades**

- AI confidence ≥90% at WR<30% produces WORSE outcomes than confidence 70-80% at the same WR level
- Mechanism: in a losing regime the model's high certainty mirrors the structural bias causing the losing streak (overfitted pattern-matching) rather than detecting genuine reversal edge
- Penalty tiers:
  - `-1.5pts`: confidence ≥92 + WR<30% — primary confirmed anti-signal
  - `-1.0pts`: confidence ≥90 + WR<25% — ultra-crisis: AI still high-conf when engine at DD>49%
- Penalty-only gate (positive tier not added — positive case requires separate walk-forward validation)
- Cold-start safe: skips when `len(booster._pnl_ring) < 20`
- Uses existing `confidence` local variable (float 0-100 scale, assigned at line 6554)
- Uses `booster.win_rate / 100.0` (0-100 → 0-1 normalisation, same as GDCR/GMDR pattern)
- Fires at exactly WR=29.0% (current live state) when conf≥92

**Wiring:**
- `gate_g85aa_cwd` in gate_stats init + gate_stats_recent init
- `_last_g85aa_cwd: int = 0` sentinel attr after _last_g85z5_ics
- `"gate_g85aa_cwd": "G8.5AA"` in _GATE_DISPLAY_LABELS
- `"gate_g85aa_cwd"` in _SOFT_GATE_KEYS frozenset
- Gate code after G8.5Z5 pass line, before Gate 8.5m (BTC Macro GEX)
- Uses `score +=` and `_record()` pattern (consistent with all other soft-gates)

### Kelly Step 132 — GCWD Near-GXPR Pre-Block De-size

**Graduated response to EXPIRED bleed building up**

- GXPR hard-blocks at ≥65% near-zero P&L rate (45min block)
- Kelly Step 132 de-sizes at 45-65% (approaching but below GXPR threshold)
- Reads `self._pnl_ring` directly (Booster owns this ring, Kelly Step is also on Booster)
- Near-zero proxy: `|pnl| < 0.005` (same definition as GXPR's 0.5% threshold)
- De-size: `Kelly × 0.78` (fills gap between normal sizing and hard-block)
- Uses `getattr(self, "_kelly_ceil", self.last_kelly_fraction)` safe ceil access (v130.0 lesson)
- Cold-start safe: skips when `len(_pnl_ring) < 20`
- Continuity: at 65%+ GXPR fires hard-block; at 45-65% Kelly Step 132 de-sizes; at <45% normal

### Infrastructure
- UNITY_VERSION 156 → 157
- Gate count: 137-gate → 138-gate (all banners updated)
- KEY GATES banner updated with G8.5AA + Kelly132 entries

## Live State at v157.0 Build
- WR=29.0%, W=812, L=1986, Sharpe=-4.87, MaxDD=49.37%
- GDCR fires at boot; G8.5AA fires on any GDCR-relief signal with conf≥92

## Boot validation
- SYNTAX OK (ast.parse clean)
- Engine running live (v156.0 already active; restart will pick up v157.0)

## PATTERN REAFFIRMED
- Scoring gates alone cannot move WR off 24-29% — but G8.5AA is different: it penalizes a CONFIRMED anti-signal from real trade data, not a theoretical model. It reduces the final quality_score on overconfident-in-crisis signals, making them less likely to pass G10 IRONS.
- Kelly Step 132 acts on the same EXPIRED bleed data source as GXPR — giving graduated pre-block response consistent with loop engineering (observe → de-size → hard-block).
