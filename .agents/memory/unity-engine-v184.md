---
    name: Unity Engine v184.0 dead-gate fix
    description: G8.5Y5-PCO and G8.5Z5-ICS missing _gate_stats_recent deque since v143.0
    ---

    ## Rule
    G8.5Y5-PCO (PCA-Signal-Orthogonality) and G8.5Z5-ICS (Information-Coefficient-Sharpe FLOAM-IR) were silent dead-recording gates since v143.0. Both had _gate_stats init entries but no _gate_stats_recent deque.

    **Why:** Every signal hit self._gate_stats_recent["gate_g85y5_pco"].append(...) -> KeyError -> silently swallowed by except Exception: pass -> quality_score adjustment (+-2.0/+-1.0/-1.0/-2.0/-3.5pts each) never applied -> _record() never called -> both gates invisible to /gates, gate_stats_summary(), gate_bottleneck_str() since introduction.

    Root cause identical to v182.0 (version-block gap): v143.0 added _gate_stats entries for y5/z5 after x5_adf but forgot _gate_stats_recent lines. gate_g85x5_adf had its own recent placed 80 lines later (line 6381); y5/z5 never got theirs.

    **Fix:** Added 2 _gate_stats_recent deque inits immediately after their _gate_stats entries at ~line 6300-6303.

    **How to apply:** Run this parity check after any version with new gates to catch recurrence:
    import re
    stats_keys = set(re.findall(r'self._gate_stats["(gate_[^"]+)"] = {"pass"', content))
    recent_keys = set(re.findall(r'self._gate_stats_recent["(gate_[^"]+)"] = deque', content))
    missing = stats_keys - recent_keys  # must be empty
    The invariant: every _gate_stats key must have a matching _gate_stats_recent deque. Run it before every release.
    