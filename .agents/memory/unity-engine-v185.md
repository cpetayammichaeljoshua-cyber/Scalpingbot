---
    name: Unity Engine v185.0 console compaction fixes
    description: Five console display bugs fixed — truncations, missing labels, health section verbosity
    ---

    ## Rule
    Five console display fixes applied in _print() method and _GATE_DISPLAY_LABELS:

    **Fix 1 - RL Risk line abbreviation**: Metric labels were too long (87 chars → truncated at "EV/min=+0."). 
    Changed Sharpe→SR, Sortino→Sort, Calmar→Cal, Omega→Ω, EV/min→EV/m. Now 70 chars, all 5 metrics visible.

    **Fix 2 - SwarmBT line**: "strong=/good=/weak= | top-EV:" shortened to "s=/g=/w= | top-EV:", dropping "pts" suffix.

    **Fix 3 - Health section**: Was printing one row per health layer (30 rows/cycle → ~48 lines total). 
    Replaced with 1 summary row "✅ N/M layers healthy  ⚠️ X warn  ❌ Y FAIL" + individual rows for non-✅ only.
    Console now ~18 lines/cycle when all healthy.
    Logic: _h_ok (✅), _h_warn (not ✅ and not ❌), _h_fail (❌). Concatenated as _h_warn + _h_fail for the loop.

    **Fix 4 - _GATE_DISPLAY_LABELS missing entries**: gate_gclh and gate_gslk had _gate_stats init + _record() calls 
    but no _GATE_DISPLAY_LABELS entry → showed as raw "gate_gclh=1" in Gates row instead of "GCLH=XX%".
    Added adjacent to gate_gdcr/gmdr/gxpr block. These are hard-block gates, NOT in _SOFT_GATE_KEYS.

    **Fix 5 - Markov p_ij truncation**: state_summary() returns "LONG_ALT:1.00(3) | LONG_MAJOR:1.00(3) | ..."
    With "Markov p_ij: " prefix → 97 chars → truncated at col 80.
    IMPORTANT: Replace "LONG_" first (removes underscore), so "_ALT"/"_MAJOR" patterns don't fire afterward.
    Result abbreviation: LALT/LMAJOR/SALT/SMAJOR → 75 chars total → fits in 80-char row.

    **Why:** W=84 console box → inner=80 chars (row() truncates at txt[:W-4]). All log lines must fit in 80 chars.

    **How to apply:** Any new console row must be counted to <80 chars before adding. Use abbreviated metric names. 
    The Gates row still truncates (too many gates to show in one row — inherent, not a bug).
    