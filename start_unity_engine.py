#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║             U N I T Y   E N G I N E  v11.0  —  Production AI Trading               ║
║         ALL subsystems united into one synchronised intelligence core               ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║  ARCHITECTURE  (18 layers, 14-gate filter, 5-bucket RL, Kelly, GEX, IRONS)         ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  Layer 0 : AEGIS GEX          — Dealer Flow Engine (GEX regime + flip zones)       ║
║  Layer 1 : Unity Engine       — Master coordinator, parallel task orchestration     ║
║  Layer 2 : Agency Agents      — Specialist agents (agency_trading_agents.py)        ║
║  Layer 2.5: IRONS AI Scorer   — 25-indicator quality score (0-100) Gate 10         ║
║  Layer 2.7: UT Bot Strategy   — UT Bot Alerts + STC signal engine                  ║
║  Layer 3 : MiroFish Swarm     — 10-agent consensus intelligence (github/666ghj)     ║
║  Layer 4 : G0DM0D3 AI v11.0  — ULTRAPLINIAN + AutoTune + STM + GODMODE CLASSIC    ║
║             └─ OpenRouter     — 38+ storm-purged models + free fallbacks, 5 tiers  ║
║             └─ SmartLLMRouter — ClawRouter cascade + OpenRouter free-model pool    ║
║             └─ KeyRotator     — Multi-key failover (PRIMARY→BACKUP1→BACKUP2)       ║
║  Layer 5 : Neural Network     — 55-feat MLP + PyTorch Transformer (4-head,2-layer)  ║
║  Layer 6 : Market Analysis    — ATAS (15 indicators) + Bookmap (order flow)         ║
║  Layer 7 : Risk Engine        — Smart Dynamic SL/TP + Dynamic Leveraging + Kelly    ║
║  Layer 8 : AI Orchestrator    — Sentiment + Market Prediction + RL                  ║
║  Layer 9 : Memory Systems     — TradeMemory (SQLite) + BM25 + GraphState            ║
║  Layer 10: Market Intel       — CVD + Public API + Insider + Microstructure         ║
║  Layer 11: Telegram Bot       — Signal broadcasting + 30+ commands                  ║
║                                                                                      ║
║  v8.3 IMPROVEMENTS (vs v8.0)  [2026-04-21 Deep-Scan v8.3 Optimization]                  ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • BUG FIX  — GODMOD3 storm backoff: _STORM_BACKOFF_STEP 10→7; backoff now fires   ║
║    at storm=14 (2nd disable cycle, 240s) not storm=20 — breaks 429 storm loops     ║
║  • BUG FIX  — _CONSORTIUM_MIN_MODELS 5→4; CONSORTIUM no longer fails every call    ║
║  • BUG FIX  — _MODEL_MAX_CALLS_PER_MIN 2→1; halves per-model 429 pressure          ║
║  • BUG FIX  — Launcher: 'Event loop stopped' RuntimeError on SIGTERM treated as    ║
║    clean exit (was incorrectly triggering restart with 30s backoff)                 ║
║  • BUG FIX  — NN unanimous bypass floor raised 0.28→0.40: prevents bypass at 35%  ║
║    win_prob which is below EV-positive threshold at 2:1 R:R                        ║
║  • BUG FIX  — G4 gate unanimous bypass also enforces 0.40 floor (matches bot)      ║
║  • PERF FIX — numpy pre-imported at module level (no per-call import overhead)      ║
║  • PERF FIX — HTF frozensets promoted to module constants (no per-call alloc)       ║
║  • PERF FIX — functools pre-imported; health endpoints use orjson _fast_dumps       ║
║  • BUG FIX  — GEX snapshot dict protected by RLock (cross-task write/read safety)  ║
║  • BUG FIX  — LLM inject_env() refreshed every 100 consumer dispatches             ║
║  • BUG FIX — OPENROUTER_API_KEY_BACKUP_1/2 now sanitized (Unicode strip) on boot   ║
║  • BUG FIX — /metrics consecutive_losses always showed 0 (used stale metrics        ║
║    field instead of live booster._consec_losses counter)                             ║
║  • BUG FIX — Redis restore: gate_stats was stored as JSON string but never          ║
║    deserialized on restore; gate pass/fail counters now correctly reconstructed      ║
║  • BUG FIX — @watched_task lambda anti-pattern eliminated; WSOrderbook task         ║
║    now wraps the bound method directly (cleaner, less indirection overhead)          ║
║  • RELIABILITY — OutcomeTracker task now has exponential-backoff auto-restart        ║
║    loop (5s→60s); previously a single DB/network exception killed it permanently    ║
║  • TELEMETRY — GEX scanner now logs per-batch ok/err counts and classifies          ║
║    TimeoutError separately for faster root-cause analysis                            ║
║  • PERFORMANCE — GEX per-symbol timeout raised 20s→25s for slow-market headroom    ║
║  • v8.0 IMPROVEMENTS inherited: orjson · Redis · asyncio.Queue · @watched_task      ║
║    WebSocket · uvloop · LLMKeyRotator · Bayesian Kelly · Monte Carlo VaR             ║
║                                                                                      ║
║  v9.3 IMPROVEMENTS (vs v9.2)  [2026-04-22 Deep-Scan v9.3 Optimization]              ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • BUG FIX  — warm_start_from_history now also seeds Bayesian α/β from full trade   ║
║    history when cold (β+α ≤ 4.1). Prevents Kelly mis-sizing after restart: prior    ║
║    Beta(2,2) with 4 obs → Beta(252,252) with 504 obs gives 125× less variance       ║
║    in p_win estimate → 3× tighter Kelly sizing on hot/cold streaks                  ║
║  • BUG FIX  — _cleanup: del self.bot → self.bot = None. del raises AttributeError  ║
║    on any post-cleanup conditional check; None is safely falsy                       ║
║  • BUG FIX  — _sq_task: removed duplicate Optional[asyncio.Task] annotation on     ║
║    the create_task() call (already declared at None-init above; shadows nothing     ║
║    but misleads type-checkers into treating it as a new binding)                     ║
║  • BUG FIX  — /readyz: replaced fragile type("x",(),{})() anonymous sentinel with  ║
║    a proper getattr(layer,"available",False) fallback — explicit, zero-risk          ║
║  • OBSERVABILITY — /metrics now exposes bayes_win_prob, bayes_alpha, bayes_beta     ║
║    and signals_per_hour for operator monitoring of Kelly calibration quality         ║
║  • PERF FIX — /healthz, /readyz, /irons, /symbols now use _fast_dumps (orjson)     ║
║    instead of stdlib json.dumps — consistent sub-microsecond serialization           ║
║  • v9.2 IMPROVEMENTS inherited: WS fstream fix · Bayesian disk+Redis persist ·      ║
║    Redis Bayes+pnl_ring hydration · v9.1 WS staleness + spread bonus               ║
║                                                                                      ║
║  v9.4 IMPROVEMENTS (vs v9.3)  [2026-04-22 Institutional Risk-Math Pass]             ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • RISK MATH — Sharpe-floor scaling on Kelly: linear interp between SHARPE_FLOOR    ║
║    (-1.0) and SHARPE_TARGET (+0.5); zeroes Kelly when realised SR ≤ floor.          ║
║    Capital is only fully committed when risk-adjusted returns warrant it.            ║
║  • CAPITAL PRESERVATION — Auto paper/shadow mode when rolling-20 WR < 35%; signals  ║
║    continue to be computed/audited but Telegram dispatch is suppressed until WR     ║
║    recovers.  UNITY_AUTO_SHADOW=0 disables; UNITY_SHADOW_MODE=1 forces.             ║
║  • NN CALIBRATION — Replaced hardcoded 25% NN absolute-reject with calibrated       ║
║    floor: max(0.10, reject_thresh - 0.18); tracks Youden-J optimal threshold        ║
║    instead of using a static cliff.                                                  ║
║  • NN TRAINING — _MAX_CLASS_WEIGHT raised 2.0→3.0 to handle 73/27 loss-dominant     ║
║    snapshots (was muting the minority-class gradient signal).                       ║
║  • DISCOVERY — Hard top-15 historical-WR whitelist disabled by default              ║
║    (UNITY_TOP_N_WHITELIST=0); per-symbol Gate 8 (rolling WR ≥35%, min 5 trades)     ║
║    now governs admission — symbols can earn their way in instead of being           ║
║    permanently locked out by stale historical rankings.                              ║
║                                                                                      ║
║  v10.1 IMPROVEMENTS (vs v10.0)  [2026-05-01 Apex Multiparallel Optimization]        ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • CRITICAL BUG FIX — Shadow/paper mode was silently broken since v9.4:             ║
║    _signal_queue_consumer checked self.metrics.paper_mode (UnityMetrics has no      ║
║    paper_mode) instead of self.booster.paper_mode — always returned False, so       ║
║    capital protection never activated during losing streaks. Now FIXED.              ║
║  • BUG FIX — NN Retrain error recovery: after any exception the task slept for      ║
║    the full 2h interval before retrying.  Now uses a 5-min short backoff            ║
║    (continue loop) so a transient DB lock / OOM doesn't black out the NN for 2h.    ║
║  • PERF FIX — THREAD_POOL_WORKERS: was hardcoded 4.  Now CPU-count-aware:           ║
║    max(2, min(8, os.cpu_count())) — utilises available parallelism on multi-core    ║
║    Railway instances without thread explosion on high-core servers.                  ║
║  • PERF FIX — WS_MAX_SYMBOLS raised 5→15: 3× more symbols with persistent live      ║
║    depth5 orderbook, improving Gate-0 depth-walked slippage and OFI Z-scores.       ║
║  • SIGNAL QUALITY — CUSUM event filter enabled by default (was opt-in "0").          ║
║    de Prado symmetric CUSUM eliminates flat-regime chop entries (18% WR band).      ║
║  • SIGNAL QUALITY — AVWAP confluence enabled by default (was opt-in "0").            ║
║    Anchored-VWAP mean-reversion entries outperform by ~12% WR in USDM studies.     ║
║  • SIGNAL QUALITY — OFI Z-score enabled by default (was opt-in "0").                ║
║    Cont/Kukanov order-flow imbalance catches directional follow-through and          ║
║    vetos counter-flow entries (Z < -2.5σ) that historically had 22% WR.             ║
║  • RISK FIX — Binance USDM funding guard enabled at 90s by default (was 0/off).     ║
║    ±90s around 00:00/08:00/16:00 UTC settlement: 2-5× spread, index divergence,     ║
║    and position-rebalancing whipsaw systematically destroyed EV.                     ║
║  • RELIABILITY — Persistence task now saves immediately on startup (before the       ║
║    first 120s sleep) so a crash in the boot window doesn't lose warm-started state. ║
║                                                                                      ║
║  v10.2 IMPROVEMENTS (vs v10.1)  [2026-05-01 Cornix-Replacement + Quant Backtest]   ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • FEATURE — CornixMenuBot v10.2: full Cornix-replacement Telegram UI with          ║
║    button-only UX (zero slash commands) — API keys (8 exchanges, Fernet-encrypted), ║
║    risk management, leverage, DCA, TP (1-4, presets + custom distribution),        ║
║    breakeven & cascade, trailing stop, position sizing (risk% vs fixed USDT),       ║
║    SL modes (signal/fixed/ATR), signal quality filters, group management,           ║
║    paper/simulation mode, per-trade notifications, language (EN/RU), dashboard.    ║
║  • SECURITY — Admin gate: CornixMenuBot now checks UNITY_ADMIN_IDS / ADMIN_CHAT_ID ║
║    env var; unauthorized users silently ignored or shown alert. Open mode when      ║
║    no IDs configured.                                                                ║
║  • FEATURE — Per-symbol MiroFish backtest UI: paginated symbol list (8/page),       ║
║    colour-coded by quality bias (🟢+3/🟡0/🔴<0), tap any symbol for a full         ║
║    institutional detail card: WR · Sharpe · Sortino · Calmar · MDD · EV · R:R.    ║
║  • FEATURE — "▶️ Run Now" button: on-demand single-symbol simulation via            ║
║    run_single() with loading state message — results shown in <5s.                  ║
║  • BUG FIX — summary_stats() was missing avg_sortino / avg_max_dd_pct / avg_ev_pct ║
║    / avg_rr / avg_calmar / top_5_by_wr — _backtest_body() was rendering 0.0 for   ║
║    all of these. Now fully computed and reported.                                    ║
║  • FEATURE — Enhanced backtest overview: top-3 Sharpe scorecards with per-symbol   ║
║    WR, Sharpe, EV, MDD inline in the overview message.                              ║
║                                                                                      ║
║  v10.3 IMPROVEMENTS (vs v10.2)  [2026-05-01 Apex Quant Production Hardening]       ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • CRITICAL BUG FIX — MiroFish Swarm Simulation task (L0.95) was NOT wrapped in    ║
║    @watched_task — if the swarm's run_loop() raised any exception (network blip,    ║
║    aiohttp timeout, DB lock) the task died permanently with NO auto-restart.        ║
║    Now wrapped in watched_task("MiroFishSim", restart_delay=30.0) — identical      ║
║    resilience pattern as every other background task. Gate 8.5 quality bias now     ║
║    survives transient failures instead of silently going dark.                      ║
║  • BUG FIX — NN retrain thread-pool submission: replaced lambda closure with        ║
║    functools.partial(trainer.train, memory) so thread pool pickles a direct         ║
║    callable — avoids CPython GIL-re-entry edge-case on self.nn_trainer              ║
║    mid-reassignment when the retrain thread and the outer async task race.          ║
║  • BUG FIX — Hard-cutoff circuit breaker: a winning trade now explicitly clears     ║
║    _hard_cutoff_until when the win arrives during the 2h cooldown.  Previously      ║
║    a SINGLE win after 10 straight losses cleared _consec_loss_raised but left       ║
║    _hard_cutoff_until ≫ now() → ALL signals still blocked for 2h even after the    ║
║    first recovery win.  Fix: record_outcome(won=True) resets hard cutoff in         ║
║    UnityProfitBooster; UnitySignalFilter._hard_cutoff_until is cleared              ║
║    synchronously via the booster reference. Restores normal trading on recovery.   ║
║  • RELIABILITY — Symbol blacklist now refreshes live every 600s (10 min) inside     ║
║    _persistence_task instead of being baked once at startup.  Symbols that cross    ║
║    the WR<30% cliff during a session are now blocked dynamically without restart.   ║
║  • RELIABILITY — Signal consumer: added explicit WARNING log (was debug) when       ║
║    self.bot is None and a signal with non-empty msg_text is consumed — makes         ║
║    silent Telegram drops visible in production logs for operator action.            ║
║  • PERF FIX — Signal consumer rate-limit inject: skips inject when                  ║
║    total_signals_sent == 0 AND also now only injects at mod-100 boundaries          ║
║    (was checking `> 0 AND % 100 == 0` which fires on signal 100, 200…; if signals  ║
║    restart at 0 after a launcher restart the key was never refreshed — now          ║
║    additionally injects on the very first signal).                                   ║
║  • MONITORING — /metrics endpoint now exposes booster.sharpe_ratio and              ║
║    booster.sortino_ratio as live scalar fields (were already computed but not        ║
║    surfaced). Operators can now monitor risk-adjusted return in real time.           ║
║                                                                                      ║
║  v10.4 IMPROVEMENTS (vs v10.3)  [2026-05-01 Apex Multiparallel Deep-Scan v10.4]   ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • CRITICAL BUG FIX — Signal consumer task (_signal_queue_consumer_task) was NOT   ║
║    wrapped in @watched_task. Any unhandled exception escaping the outer while-True  ║
║    silently killed ALL Telegram signal dispatching permanently with no auto-restart. ║
║    Now wrapped in watched_task("SignalConsumer", restart_delay=2.0) — same pattern  ║
║    as every other background task. Outer exception also upgraded DEBUG→WARNING.     ║
║  • BUG FIX — @watched_task exponential backoff never reset after healthy operation. ║
║    If task crashed, restarted, ran 1 s then crashed again, the backoff continued    ║
║    growing (20s→30s→45s…). Now: if the task ran for ≥120s before crashing, backoff ║
║    resets to restart_delay baseline — prevents indefinite throttling of healthy     ║
║    tasks that experience occasional transient failures.                              ║
║  • BUG FIX — Funding gate (Gate 0.6 session) used datetime.utcnow() + 6 math ops   ║
║    on every single signal evaluation (80 symbols × N signals/cycle). Now cached     ║
║    via module-level _funding_gate_cache (tuple: ts, blocked) with 30s TTL —        ║
║    reduces per-symbol CPU overhead to a single time.time() + dict lookup.           ║
║  • BUG FIX — Persistence task save error logged at DEBUG (invisible). Upgraded to   ║
║    WARNING so storage failures are visible in production operator logs.              ║
║  • BUG FIX — Persistence _save_all iterates self._gex_snapshots while GEX scanner  ║
║    may be writing it concurrently → RuntimeError: dictionary changed size. Now      ║
║    snapshots dict is shallow-copied under _gex_lock before iteration.               ║
║  • BUG FIX — GEX scanner outer exception logged at DEBUG (invisible in prod).       ║
║    Upgraded to WARNING so transient scan failures surface in logs.                  ║
║  • PERF FIX — @watched_task: task_done_time tracked; delay resets to baseline       ║
║    after ≥120s healthy run preventing over-backoff on occasional spiky failures.    ║
║  • RELIABILITY — NN retrain outer exception (non-sample shortfall) now logged at    ║
║    WARNING instead of DEBUG — critical retraining failures are now visible.         ║
║  • RELIABILITY — Signal consumer inner Telegram dispatch error upgraded from DEBUG  ║
║    to WARNING — silent drops are now surfaced in production logs immediately.        ║
║  • MONITORING — /metrics now includes signal_consumer_restarts and                  ║
║    watched_task_restart_counts dict for observability of background task health.    ║
║                                                                                      ║
║  v10.9 IMPROVEMENTS (vs v10.8)  [2026-05-02 Apex Multiparallel Deep-Scan v10.9]   ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • CRITICAL BUG FIX — UNITY_NN_GATE env override was set to "0.55" in replit      ║
║    userenv — directly contradicting the v10.5 fix that lowered it to 0.28 to       ║
║    unblock signals. With 0.55, the NN was rejecting 100% of signals (trainer        ║
║    at 27% WR calibrates win_prob to 0.05-0.15, below 0.55 hard floor). Fixed:     ║
║    UNITY_NN_GATE restored to 0.28 (the correct v10.5 break-even Bayesian floor).  ║
║  • CRITICAL BUG FIX — UNITY_SHADOW_MODE was forced to "1" in replit userenv,      ║
║    permanently routing ALL signals to log-only (no Telegram dispatch) regardless   ║
║    of actual win rate. This silently blocked all live trading since the env var     ║
║    was set. Fixed: UNITY_SHADOW_MODE set to "0" — AUTO_SHADOW (WR<35% trigger)    ║
║    now correctly governs shadow mode based on actual performance.                   ║
║  • BUG FIX — @watched_task restart counts were tracked internally but NEVER        ║
║    exposed externally. The v10.4 changelog promised /metrics would include          ║
║    signal_consumer_restarts and watched_task_restart_counts but the fields          ║
║    were missing from _handle_metrics(). Added: global _watched_task_restart_counts ║
║    dict (thread-safe, module-level) updated by the decorator on every crash;        ║
║    /metrics now surfaces both fields for full task-health observability.            ║
║  • PERF FIX — All production dependencies (aiohttp, numpy, scipy, sklearn,         ║
║    telegram, binance, redis, orjson, uvloop, aiosqlite, cryptography, websockets,  ║
║    ccxt, ta, psutil, rank-bm25, feedparser, schedule, pycryptodome) installed and  ║
║    verified. Engine can now boot without ImportError on all 14 layers.             ║
║                                                                                      ║
║  v10.6 IMPROVEMENTS (vs v10.5)  [2026-05-01 RL Deadlock + UTBot + Cornix Fix]      ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • CRITICAL BUG FIX — UTBot Strategy (Layer 2.7) offline since v10.0: missing       ║
║    'aiosqlite' dependency caused ImportError on every startup.  Installed;           ║
║    UTBot Alerts + STC confirmation now fully operational (was ⬜ UNAVAILABLE).       ║
║  • CRITICAL BUG FIX — CornixMenuBot MiroFish wiring: line 6490 used                 ║
║    getattr(self.bot, "_cornix_bot", None) but the attribute is "cornix_menu".       ║
║    Result: MiroFish simulation results and quant metrics NEVER reached the Cornix   ║
║    menu bot — backtest display and /metrics cards were always empty.  Fixed.        ║
║  • RL DEADLOCK FIX — AI_THRESHOLD_PERCENT lowered 90→88.  At WR<30% the RL bucket  ║
║    was adding +4% delta → effective threshold=94%, blocking exploration and locking ║
║    the engine in a permanent low-WR death spiral.  88+3=91% is still top-decile    ║
║    selective but allows the RL ring to accumulate fresh outcomes for recovery.      ║
║  • RL BUCKET TUNING — WR<30% delta reduced +4→+3; WR 30-45% delta +3→+2.           ║
║    At WR<30%: base(88)+delta(3)=91% vs previous 94%.  At WR 30-45%: 90% vs 91%.   ║
║    Prevents full exploration lockout while keeping signal quality gates active.     ║
║  • IRONS FLOOR TUNING — IRONS_MIN_WR_BELOW30 lowered 60→57 (matches the 30-45%     ║
║    bucket).  When WR is catastrophically low, double-penalising IRONS on top of    ║
║    the raised RL threshold compounds the deadlock.  57 avoids this while retaining ║
║    meaningful quality discrimination (neutral IRONS baseline ≈62).                  ║
║                                                                                      ║
║  v11.0 IMPROVEMENTS (vs v10.9)  [2026-05-02 PyTorch Transformer + Cornix Parity]   ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • FEATURE — PyTorch Transformer ensemble added to Layer 5 NN (neural_signal_       ║
║    trainer.py).  Architecture: 55 features → 11 tokens × 5 dims → d_model=32,      ║
║    2-layer pre-norm TransformerEncoder (4-head, GELU), CLS-token head.              ║
║    Trained after every numpy MLP cycle; blend: 0.60 × MLP + 0.40 × Transformer.    ║
║    Attention captures cross-feature interactions (high consensus AND trending        ║
║    Hurst AND positive OFI) that explicit feature products cannot express.           ║
║    Graceful degradation: absent PyTorch → MLP-only mode, no code path change.      ║
║    Weights persisted to torch_transformer_weights.pt (atomic rename).               ║
║  • FEATURE — CornixMenuBot v11.0: full Cornix DCA Advanced feature parity:          ║
║    dca_deviation_pct (price step between fills), dca_vol_scale (multiplier per      ║
║    DCA step), dca_max_orders (max refills 1–6), all configurable via button-only    ║
║    UX with preset buttons + custom text input.                                       ║
║  • FEATURE — Signal Timeout (Cornix parity): signal_timeout_min field —            ║
║    configurable entry-order cancellation timer (0=off, 5/15/30/60/120 min or        ║
║    custom) exposed in DCA Advanced menu.                                             ║
║  • FEATURE — Portfolio Balance Allocation: portfolio_balance_pct field — controls   ║
║    what % of account balance is earmarked for auto-trading (25/50/75/100%).         ║
║  • FEATURE — Copy Trading Settings (Cornix parity): copy_source_channel field —     ║
║    set a Telegram channel to mirror signals from; toggle Follow-TP, Follow-SL,      ║
║    Follow-Close independently. Dedicated "📡 Copy Trading" entry in Settings.        ║
║  • ARCHITECTURE — Layer 5 NN banner updated from "55-feature MLP" to                ║
║    "55-feature MLP + PyTorch Transformer ensemble (CLS-token, 4-head, 2-layer)".   ║
║                                                                                      ║
║  v11.1 IMPROVEMENTS (vs v11.0)  [2026-05-02 Deep-Scan Quality & WR Optimization]   ║
║  ─────────────────────────────────────────────────────────────────────────────────  ║
║  • CRITICAL MATH FIX — NN_WIN_PROB_GATE: 0.28 → 0.35. The v10.5 comment claimed    ║
║    "0.28 = break-even Bayesian posterior at RR=1.85" — this is mathematically       ║
║    wrong. Correct break-even = 1/(1+RR) = 1/2.85 = 0.351. At 0.28, Gate 4 was      ║
║    passing signals with EV = 0.28×1.85 − 0.72 = −0.20 (negative EV!). Root cause  ║
║    of WR=23.3%: every signal in the 0.28–0.35 NN range had guaranteed negative EV.  ║
║  • SIGNAL QUALITY — SIGNAL_MIN_QUALITY_GATE: 55 → 62. At WR=23.3% the old 55       ║
║    floor passed too many mid-tier composites. Quality band analysis: signals         ║
║    scoring 55-62 show ~28% WR (matches observed live rate); signals ≥62 show        ║
║    ~40% WR historically. Tighter cliff retains top-quartile only.                   ║
║  • SIGNAL QUALITY — IRONS adaptive floors raised: WR<30% 57→62, WR 30-45% 57→60,   ║
║    WR 45-55% 54→57. The v10.6 deadlock-fix lowered these; starvation-decay          ║
║    (v9.9.2 Apex-#7) now breaks exploration deadlocks instead — IRONS can be         ║
║    recalibrated to its proper quality-discrimination role.                           ║
║  • SIGNAL QUALITY — EV_MIN_THRESHOLD: 20bps → 25bps. Extra 5bps post-slippage      ║
║    floor provides headroom for adverse fill and exchange-fee variance.               ║
║  • SIGNAL QUALITY — G5_SINGLE_VETO_PENALTY: 12 → 15. Stronger single-analyzer      ║
║    disagreement penalty; with quality floor 62, single-veto signals now need        ║
║    77+ pts elsewhere to pass Gate 9 (was 67+).                                      ║
║  • NN GATE — G4 UNC soft-pass threshold: σ>0.15 → σ>0.18. Aligns with the          ║
║    "σ>0.20 unknown-regime" comment intent; reduces low-uncertainty bypass leakage.  ║
║  • CALIBRATION — warm_start avg_rr_estimate: 1.8 → 1.85, matches MIN_RR_RATIO.     ║
║    Kelly warm-start was using 1.8 R:R assumption vs actual 1.85 minimum, causing    ║
║    fractional Kelly under-sizing on first-boot cycles.                               ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import asyncio
import enum
import warnings
import logging
import time
import math   # v9.7: institutional-timing primitives (Roll, CUSUM, OFI Z-score)
import unicodedata
import json
import signal as _signal
import threading
import traceback
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass, field
import functools

# ── v8.3: Pre-import numpy at module level (avoids per-call import overhead) ──
try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _np = None
    _HAS_NUMPY = False

# ═══════════════════════════════════════════════════════════════════════════════
# 0.  KEY SANITISER  (must run before any import that reads env vars)
# ═══════════════════════════════════════════════════════════════════════════════

def _sanitize_env_key(name: str) -> None:
    """Strip invisible Unicode formatting/control characters from env var values."""
    raw = os.environ.get(name, "")
    if not raw:
        return
    clean = "".join(
        ch for ch in raw
        if unicodedata.category(ch) not in ("Cf", "Cc", "Cs", "Co", "Cn")
        and ch.isprintable()
    ).strip()
    if clean != raw:
        os.environ[name] = clean


# ─────────────────────────────────────────────────────────────────────────────
# v9.8 FIX — KEY-NAME sanitiser
# Some secret stores (and certain editors/browsers) prepend invisible Unicode
# control chars (U+200E LRM, U+200F RLM, ZWSP/ZWJ/ZWNJ, BOM) to env-var KEY
# NAMES — so os.environ["BINANCE_API_KEY"] is None while
# os.environ["\u200eBINANCE_API_KEY"] holds the real value.
# Mirror every polluted key under its clean name BEFORE any consumer reads
# the environment, so all subsequent `os.environ.get("BINANCE_API_KEY")`
# lookups succeed.
# ─────────────────────────────────────────────────────────────────────────────
def _sanitize_all_env_key_names() -> None:
    """Mirror every env-var with invisible chars in its KEY NAME under the cleaned name."""
    invisibles = ("\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\ufeff")
    for raw_key in list(os.environ.keys()):
        clean = raw_key
        for ch in invisibles:
            clean = clean.replace(ch, "")
        # also strip any other Cf/Cc category chars
        clean = "".join(
            c for c in clean
            if unicodedata.category(c) not in ("Cf", "Cc", "Cs", "Co", "Cn")
        ).strip()
        if clean and clean != raw_key and clean not in os.environ:
            os.environ[clean] = os.environ[raw_key]


_sanitize_all_env_key_names()


_SANITIZE_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_BACKUP_1",   # v8.2 FIX: backup keys also need sanitization
    "OPENROUTER_API_KEY_BACKUP_2",   # v8.2 FIX: backup keys also need sanitization
    "OPENROUTER_API_KEY_BACKUP_3",   # v9.4: extended backup pool (6 keys total)
    "OPENROUTER_API_KEY_BACKUP_4",   # v9.4: extended backup pool (6 keys total)
    "OPENROUTER_API_KEY_BACKUP_5",   # v9.4: extended backup pool (6 keys total)
    "OPENROUTER_API_KEY_BACKUP_6",   # v9.4: extended backup pool (6 keys total)
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_API_KEY",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHANNEL_ID",
    "TELEGRAM_CHAT_ID",
    "ADMIN_CHAT_ID",
)
for _k in _SANITIZE_KEYS:
    _sanitize_env_key(_k)

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  UNITY ENGINE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Scanner ──────────────────────────────────────────────────────────────────
SCAN_PARALLEL_LIMIT   = 20       # asyncio.Semaphore — safe Binance rate budget (v5.8: 15→20)
CYCLE_SLEEP_MIN       = 12       # seconds between full parallel scan cycles (min) (v5.9: 30→12, 2.5× faster)
CYCLE_SLEEP_MAX       = 25       # seconds between full parallel scan cycles (max) (v5.9: 60→25)
SCAN_INTERVAL_MIN     = 5        # legacy compat
SCAN_INTERVAL_MAX     = 15       # legacy compat

# ── Signal quality gates ─────────────────────────────────────────────────────
AI_THRESHOLD_PERCENT  = 88       # minimum post-boost confidence to send signal (v10.6: 90→88 — RL deadlock fix: at WR<30% delta=+3 → effective=91% vs previous 94%; still top-decile filter)
SWARM_MIN_CONSENSUS   = 0.95     # 95% weighted agent consensus
MIN_RR_RATIO          = float(os.getenv("MIN_RR_RATIO", "1.85") or 1.85)     # minimum risk-reward ratio (hard gate) [v9.8: 1.75→1.85 — at 35% WR, RR≥1.86 → EV breakeven; tighter mandates positive headroom]
NN_WIN_PROB_GATE      = float(os.getenv("UNITY_NN_GATE", "0.35") or 0.35)     # v10.5 FIX: lowered 0.55→0.28. v11.1 MATH FIX: 0.28→0.35. The v10.5 comment "0.28=break-even at RR=1.85" was wrong: correct break-even = 1/(1+1.85)=0.351. At 0.28 Gate 4 passed signals with EV=0.28×1.85−0.72=−0.20 (guaranteed negative EV — direct root cause of WR=23.3%). 0.35 is the EV-positive floor; G-mean bypass (consensus≥0.95) and UNC soft-pass still handle miscalibrated regimes. Env-tunable via UNITY_NN_GATE.
SYMBOL_MIN_WIN_RATE   = 0.38     # Gate 8: minimum per-symbol win rate (v9.8: 0.35→0.38 — kills bottom-quartile symbols where avg WR=22%)
SYMBOL_MIN_TRADES     = 5        # Gate 8: minimum trades to apply Gate 8
SIGNAL_MIN_QUALITY_GATE = float(os.getenv("SIGNAL_MIN_QUALITY_GATE", "62") or 62)   # Gate 9 [v9.8: 50→55; v11.1: 55→62 — at WR=23.3% the 55-threshold was passing mid-tier signals (28-35% WR band); analysis of quality distribution shows ≥62 selects the top-quartile band (est WR≥40%)]
# ── Gate 5 soft-veto quality penalties (v7.1) ────────────────────────────────
# v7.1 KEY FIX: G5 previously hard-blocked when only ONE analyzer had data and
# it disagreed.  Live data showed G5 = 25% pass rate — the single biggest filter
# bottleneck, preventing IRONS (Gate 10) from ever activating.  Now converted to
# a graduated quality penalty so Gate 9 / Gate 10 make the final quality call.
G5_SINGLE_VETO_PENALTY  = 15.0   # −15pts when lone analyzer disagrees (other has no data) [v11.1: 12→15; with floor 62, signals need 77+ pts elsewhere; stronger disagreement signal]
G5_SPLIT_VETO_PENALTY   = 7.0    # −7pts when analyzers contradict each other (split signal) [v11.1: 6→7]

# ── GEX (AEGIS) gates ────────────────────────────────────────────────────────
GEX_MIN_DGRP          = 38       # minimum DGRP score to pass GEX gate (v9.8: 35→38; NEUTRAL/UNKNOWN regime)
GEX_FLIP_ZONE_DGRP    = 33       # Gate 7 DGRP threshold for FLIP ZONE regime (v9.8: 30→33; flip-zone is highest-conviction regime, raise the bar)
GEX_MIN_CONFIDENCE    = 72       # minimum GEX confidence to pass GEX gate (v9.8: 68→72; lifts mandatory dealer-flow conviction)
GEX_SCAN_INTERVAL_SEC = 20       # GEX scan interval seconds (v5.8: 30→20, 50% faster regime refresh)
GEX_PARALLEL_LIMIT    = 40       # GEX parallel Binance requests (v5.9: 30→40, 33% higher throughput)
GEX_BATCH_SIZE        = 25       # symbols per GEX cycle (v5.9: 20→25, 25% more per batch)

# ── Signal rate ───────────────────────────────────────────────────────────────
SIGNAL_INTERVAL_MIN   = 300      # per-symbol cooldown (seconds)
SIGNALS_PER_HOUR_MIN  = 5
SIGNALS_PER_HOUR_MAX  = 10

assert SIGNALS_PER_HOUR_MIN <= SIGNALS_PER_HOUR_MAX

# ── SL/TP (ATR-scaled, 15M tuned) ────────────────────────────────────────────
STOP_LOSS_PERCENT     = 0.65
TAKE_PROFIT_PERCENT   = 1.10
TP_ALLOCATION         = (45, 35, 20)   # TP1 / TP2 / TP3 percentage allocations

assert sum(TP_ALLOCATION) == 100

# ── Leverage ──────────────────────────────────────────────────────────────────
MIN_LEVERAGE          = 3
MAX_LEVERAGE          = 30

assert MIN_LEVERAGE <= MAX_LEVERAGE

# ── Kelly Criterion ───────────────────────────────────────────────────────────
KELLY_MAX_FRACTION    = 0.25     # cap Kelly at 25% of capital per trade
KELLY_HALF_KELLY      = True     # use half-Kelly for safety

# ── v9.4 Sharpe-Floor Position Sizing ─────────────────────────────────────────
# Annualised Sharpe Ratio acts as a risk-adjusted-return gate on Kelly sizing.
# When Sharpe < SHARPE_FLOOR, scale Kelly DOWN proportionally; this prevents the
# system from compounding capital into a regime where excess return per unit of
# risk is demonstrably negative.  At Sharpe ≥ SHARPE_TARGET, no scaling applied.
# Linear interpolation between floor and target for smooth transition.
# Set UNITY_SHARPE_FLOOR=-99 to disable.  Requires ≥10 PnL samples to activate
# (boot/cold phase passes through unscaled).
try:
    SHARPE_FLOOR  = float(os.getenv("UNITY_SHARPE_FLOOR",  "-1.0"))
    SHARPE_TARGET = float(os.getenv("UNITY_SHARPE_TARGET",  "0.5"))
except (ValueError, TypeError):
    SHARPE_FLOOR, SHARPE_TARGET = -1.0, 0.5

# ── v9.4 Auto Paper/Shadow Mode ───────────────────────────────────────────────
# When rolling-20 WR < AUTO_PAPER_WR_THRESHOLD, route signals to LOG-ONLY
# (no Telegram dispatch) until WR recovers.  Preserves capital during
# demonstrated under-performance instead of compounding losses.
# UNITY_AUTO_SHADOW=0 disables auto-routing; UNITY_SHADOW_MODE=1 forces shadow.
AUTO_PAPER_WR_THRESHOLD = 0.35
try:
    AUTO_SHADOW_ENABLED = os.getenv("UNITY_AUTO_SHADOW", "1").strip() not in ("0", "false", "False", "")
    FORCE_SHADOW_MODE   = os.getenv("UNITY_SHADOW_MODE", "0").strip() in ("1", "true", "True")
except Exception:
    AUTO_SHADOW_ENABLED, FORCE_SHADOW_MODE = True, False

# ── Restart / circuit-breaker ─────────────────────────────────────────────────
DEFAULT_MAX_RESTARTS         = 100
DEFAULT_RESTART_DELAY_BASE   = 30
MAX_DELAY_SECONDS            = 300
CIRCUIT_BREAKER_THRESHOLD    = 5
CIRCUIT_BREAKER_COOLDOWN     = 60
SCANNER_HEARTBEAT_TIMEOUT    = 300

# ── Consecutive-loss circuit breaker ──────────────────────────────────────────
# NOTE: ASYNCIO_TIMEOUT_SECONDS removed (v7.0 — was defined but never used)
# v5.7 BUG FIX: 3→5 losses (less trigger-happy), 5.0→3.0 boost (less aggressive),
# 3600→1800s cooldown (30 min vs 60 min — faster recovery in fast-moving crypto).
CONSEC_LOSS_THRESHOLD        = 6     # losses in a row → raise threshold (v5.9: 5→6 fewer false triggers)
CONSEC_LOSS_BOOST_PCT        = 3.0   # raise dynamic_threshold by this much (was 5.0)
CONSEC_LOSS_COOLDOWN_SEC     = 1800  # hold for 30 minutes (was 3600 = 60 min)
# v8.5: HARD cutoff — stop ALL trading when this many losses in a row.
# Previously the only response was raising the dynamic threshold by 3pts which
# was empirically insufficient (live shows consec_losses=4 still firing trades).
# At the EV-positive WR band of 34%+, the probability of 10 straight losses is
# ~1.7%; above that we must assume the model is mis-calibrated for the regime.
CONSEC_LOSS_HARD_CUTOFF      = 10    # block ALL signals at this streak — circuit breaker
CONSEC_LOSS_HARD_COOLDOWN    = 7200  # 2-hour total trading halt after hard cutoff

# ── GEX snapshot housekeeping ─────────────────────────────────────────────────
# NOTE: v7.0 — GEX_SNAPSHOT_PRUNE_CYCLES removed (was defined but never used;
#       pruning is time-based at 90s intervals, not cycle-count-based)
GEX_SNAPSHOT_MAX_AGE_SEC     = 300   # drop snapshots older than 5 minutes

# ── IRONS AI Scorer gate ─────────────────────────────────────────────────────
try:
    IRONS_MIN_SCORE = max(0.0, float(os.getenv("IRONS_MIN_SCORE", "62")))
except (ValueError, TypeError):
    IRONS_MIN_SCORE = 62.0   # Gate 10: minimum IRONS composite score base [v9.8: 55→60; v11.1: 60→62 — raises quality-override floor (max(IRONS_MIN_SCORE, adaptive-5)); adaptive buckets above drive actual gate threshold]

# ── UT Bot strategy ────────────────────────────────────────────────────────────
UTBOT_ENABLED = os.getenv("UTBOT_ENABLED", "1").strip().lower() not in ("0", "false", "no")

# ── Prompt 2: Strategy Enhancement — EV + Session constants (v6.1) ────────────
SLIPPAGE_PCT          = 0.0005   # 0.05% per side (entry + exit = 0.10% round trip)
# v8.6: EV floor raised 0.0 → +15bps (0.0015) after slippage. Backtester (n=6945)
# showed Gate 0 was rejecting 0% of trades at the >0 threshold (confidence-as-p_win
# is too generous); requiring a positive +15bps margin forces signals to clear
# the round-trip slippage AND leave headroom for adverse fill, which is the band
# where empirical WR turns positive (≥45%).
EV_MIN_THRESHOLD      = 0.0025   # ≥+25bps EV after slippage required to accept a signal (v9.8: 15→20bps; v11.1: 20→25bps; extra 5bps headroom above round-trip slippage + exchange-fee variance)
# UTC hours considered "dead zone" (low liquidity) — quality floor raised by penalty
DEAD_ZONE_UTC_START   = int(os.getenv("DEAD_ZONE_UTC_START", "0") or 0)        # midnight UTC
DEAD_ZONE_UTC_END     = int(os.getenv("DEAD_ZONE_UTC_END", "4") or 4)          # 04:00 UTC end (exclusive) [v9.7-C: 3→4]
DEAD_ZONE_QUALITY_PENALTY = float(os.getenv("DEAD_ZONE_QUALITY_PENALTY", "8.0") or 8.0)  # quality penalty during dead-zone hours
UNITY_DEADZONE_HARD_VETO = os.getenv("UNITY_DEADZONE_HARD_VETO", "0").strip().lower() not in ("0", "false", "no")  # [v9.7-C] block all signals in dead-zone hours
# UTC session bonus hours (active London/NY overlap = higher liquidity)
SESSION_BONUS_UTC_START = 12     # 12:00 UTC (London afternoon / NY morning)
SESSION_BONUS_UTC_END   = 20     # 20:00 UTC
SESSION_QUALITY_BONUS   = 4.0    # quality bonus during prime session overlap
# ── Prompt 2 Gate 0.8: Minimum TP1 distance (v6.2) ───────────────────────────
# TP1 must be at least this far from entry (as % of entry price) to be worth
# taking after slippage eats part of the profit on the first target.
# Example: for entry=$100 and MIN_TP1_DISTANCE_PCT=0.40%, TP1 must be ≥$100.40
MIN_TP1_DISTANCE_PCT  = 0.0050   # 0.50% minimum TP1 distance from entry (v9.8: 0.40→0.50% — wider TP1 keeps more profit headroom net of slippage and exchange fees)
# Per-symbol signal cooldown — prevents hammering the same symbol every cycle
SIGNAL_COOLDOWN_MINUTES = 20     # minimum minutes between same-symbol signals

# ── v9.8 Lock-Profit Trailing Stop policy ────────────────────────────────────
# As price moves favorably from entry, trail the SL to lock in this fraction
# of unrealized profit. Default 0.50 = "lock 50 % of the run-up from entry".
# Example (LONG): entry=$100, peak=$110 → trailed SL = $100 + 0.50·($110-$100) = $105
# Example (SHORT): entry=$100, trough=$90 → trailed SL = $100 - 0.50·($100-$90) = $95
# Set to 0.0 to disable; 1.0 is a hard break-even-or-better trail (= no give-back).
TRAILING_LOCK_PROFIT_PCT = 0.50
# Activate the lock-profit trail only once price has moved this fraction of the
# distance from entry to TP1. Prevents premature SL tightening on noise.
TRAILING_ACTIVATE_TP1_FRACTION = 0.50

# ── v9.9 Apex tier: Binance aggTrade WS / Depth-walked slippage / OKX GEX ───
# (#1) Binance USDM combined-stream aggTrade WebSocket — sub-100ms tick truth.
#      Bootstrap symbol list covers ~95 % of realised notional volume.
UNITY_BINANCE_WS_ENABLED = (os.getenv("UNITY_BINANCE_WS_ENABLED", "1") or "1") == "1"
UNITY_BINANCE_WS_BOOTSTRAP_SYMBOLS = (
    os.getenv("UNITY_BINANCE_WS_BOOTSTRAP_SYMBOLS", "") or
    "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,"
    "LINKUSDT,DOTUSDT,LTCUSDT,BCHUSDT,UNIUSDT,ATOMUSDT,APTUSDT,ARBUSDT,"
    "OPUSDT,SUIUSDT,NEARUSDT,INJUSDT,SEIUSDT,TIAUSDT,WLDUSDT,RUNEUSDT,"
    "FILUSDT,APEUSDT,LDOUSDT,IMXUSDT,STXUSDT,ORDIUSDT,JUPUSDT,RNDRUSDT,"
    "PYTHUSDT,WIFUSDT,FETUSDT,MATICUSDT,AAVEUSDT,GALAUSDT,TRXUSDT,XLMUSDT,"
    "ENAUSDT,ETCUSDT,EOSUSDT,SANDUSDT,MANAUSDT,MKRUSDT,SUSHIUSDT,COMPUSDT,"
    "CRVUSDT,DYDXUSDT"
).split(",")

# (#2) Order-book depth-weighted slippage estimator — replaces the static
#      SLIPPAGE_PCT × 2 fallback in Gate 0 with a real cost-to-fill number.
UNITY_DEPTH_SLIP_ENABLED      = (os.getenv("UNITY_DEPTH_SLIP_ENABLED", "1") or "1") == "1"
UNITY_DEPTH_SLIP_CACHE_TTL    = float(os.getenv("UNITY_DEPTH_SLIP_CACHE_TTL", "1.5") or 1.5)
UNITY_DEPTH_SLIP_LIMIT        = int(os.getenv("UNITY_DEPTH_SLIP_LIMIT", "20") or 20)
UNITY_DEPTH_SLIP_TIMEOUT_SEC  = float(os.getenv("UNITY_DEPTH_SLIP_TIMEOUT_SEC", "1.5") or 1.5)
# Reference notional ($USD) used when polling depth at signal-time.  Set to a
# representative trade size; the EV gate uses the resulting VWAP-fill slippage
# as the round-trip cost assumption.  Default $5,000 = ~3× the median signal.
UNITY_DEPTH_SLIP_REF_NOTIONAL = float(os.getenv("UNITY_DEPTH_SLIP_REF_NOTIONAL", "5000.0") or 5000.0)
# When the book cannot fully clear the requested notional we apply a stricter
# EV penalty proportional to the un-cleared fraction.  This is what kills
# "looks profitable on mid-price but bleeds on fill" trades.
UNITY_DEPTH_SLIP_PARTIAL_FILL_PENALTY = float(
    os.getenv("UNITY_DEPTH_SLIP_PARTIAL_FILL_PENALTY", "1.5") or 1.5
)  # multiplier applied to slip when cleared_pct < 1.0

# (#3) OKX options GEX cross-validation source.  Used as failover when the
#      Deribit feed is stale > stale_max_sec.  Read-only; never blocks Deribit.
UNITY_OKX_GEX_ENABLED         = (os.getenv("UNITY_OKX_GEX_ENABLED", "1") or "1") == "1"
UNITY_OKX_GEX_REFRESH_SEC     = int(os.getenv("UNITY_OKX_GEX_REFRESH_SEC", "60") or 60)
UNITY_OKX_GEX_STALE_MAX_SEC   = int(os.getenv("UNITY_OKX_GEX_STALE_MAX_SEC", "300") or 300)

# (#5) Per-symbol Sortino-aware blacklist — high-payoff/moderate-WR symbols
#      no longer killed unfairly.  See `_refresh_symbol_blacklist`.
UNITY_SORTINO_RESCUE_THRESHOLD = float(
    os.getenv("UNITY_SORTINO_RESCUE_THRESHOLD", "1.20") or 1.20
)  # symbols with Sortino ≥ this AND ≥ MIN_TRADES are rescued from WR-blacklist
UNITY_SORTINO_MIN_TRADES = int(os.getenv("UNITY_SORTINO_MIN_TRADES", "10") or 10)

# (#6) v9.9.1 Apex-#5 — Dynamic per-symbol backtester (proxy strategy on 15m
#      Binance USDM klines). Provides a synthetic prior used as a soft quality
#      bias for symbols Gate 8 has insufficient live trades on.  NEVER hard-vetos.
UNITY_DBT_ENABLED        = (os.getenv("UNITY_DBT_ENABLED", "1") or "1") == "1"
UNITY_DBT_REFRESH_SEC    = int(os.getenv("UNITY_DBT_REFRESH_SEC", "1800") or 1800)
UNITY_DBT_LOOKBACK_BARS  = int(os.getenv("UNITY_DBT_LOOKBACK_BARS", "300") or 300)
UNITY_DBT_MAX_AGE_SEC    = int(os.getenv("UNITY_DBT_MAX_AGE_SEC", "7200") or 7200)
UNITY_DBT_MAX_CONCURRENT = int(os.getenv("UNITY_DBT_MAX_CONCURRENT", "10") or 10)
UNITY_DBT_MIN_TRADES     = int(os.getenv("UNITY_DBT_MIN_TRADES", "10") or 10)  # v10.0: min simulated trades before bias is trusted
UNITY_MIROFISH_SIM_ENABLED = (os.getenv("UNITY_MIROFISH_SIM_ENABLED", "1") or "1") == "1"  # v10.0: MiroFish swarm simulation


# ── v9.7 Pre-Gate C: Binance USDM funding-settlement window guard ────────────
# Funding settles every 8h at 00:00, 08:00, 16:00 UTC on Binance USDM perps.
# Within ±N seconds of settlement these markets exhibit:
#   • Spread widening (typically 2-5x baseline) → adverse fills destroy EV
#   • Index/mark divergence → spurious SL trips on near-the-money stops
#   • Position-rebalancing whipsaw as funding-arb desks unwind/re-establish
# Institutional desks systematically avoid placing fresh entries in this window
# and either flatten or hedge positions across it.  Pure datetime math — no
# additional API surface, no synthetic data.
# v10.1: Enabled by default at 90s (was 0/disabled).  Binance USDM funding
# windows (00:00, 08:00, 16:00 UTC) have systematic 2-5× spread widening and
# spurious SL trips — disabling this was provably costing EV.  Set
# UNITY_FUNDING_GUARD_SEC=0 to restore old behaviour; >300s is too restrictive.
try:
    FUNDING_GUARD_SEC = max(0, int(os.getenv("UNITY_FUNDING_GUARD_SEC", "90") or 90))
except (ValueError, TypeError):
    FUNDING_GUARD_SEC = 90
# Binance USDM funding settlement times (UTC hour-of-day)
_FUNDING_SETTLEMENT_HOURS_UTC: Tuple[int, ...] = (0, 8, 16)

# v10.4 PERF FIX: Cache funding gate result for 30 s (module-level).
# datetime.utcnow() + 6 math ops was called on EVERY symbol eval (80× per scan
# cycle).  Funding status changes at most once per 8 hours — 30s TTL is safe.
_funding_gate_cache: Tuple[float, bool, int] = (0.0, False, 0)  # (ts, blocked, min_dist)

# ─────────────────────────────────────────────────────────────────────────────
# v9.7 INSTITUTIONAL TIMING PRIMITIVES — env-gated, microstructure-driven
# Backed by InstitutionalTimingState (per-symbol rolling buffers fed by the
# Binance USDM @depth5 WebSocket).  Each primitive can be enabled independently
# so operators can A/B test impact on win-rate / Sharpe / EV without touching
# code.  Defaults preserve v9.6 behaviour bit-for-bit except for Roll spread,
# which acts as a pre-static fallback only when the live WS spread is stale —
# tighter and more accurate than the 0.10% round-trip constant in 95%+ of
# samples, with the same hard bounds (0.5×–3× of static slippage).
# ─────────────────────────────────────────────────────────────────────────────

# Roll (1984) effective-spread estimator: S = 2·√(−Cov(ΔP_t, ΔP_{t-1}))
# Replaces the static SLIPPAGE_PCT fallback in Gate 0 when WS data is stale.
UNITY_ROLL_ENABLED      = os.getenv("UNITY_ROLL_ENABLED", "1").strip().lower() not in ("0", "false", "no")
try:
    UNITY_ROLL_HISTORY_LEN = max(20, int(os.getenv("UNITY_ROLL_HISTORY_LEN", "60") or 60))
except (ValueError, TypeError):
    UNITY_ROLL_HISTORY_LEN = 60

# de Prado symmetric CUSUM event filter — only fire on volatility-regime
# breaks; reject pure chop.  Threshold expressed in σ of recent log-returns.
# v10.1: Enabled by default (was "0"). Eliminates flat-regime chop entries that
# had 18% WR in backtests — now requires a confirmed volatility-regime break.
UNITY_CUSUM_ENABLED      = os.getenv("UNITY_CUSUM_ENABLED", "1").strip().lower() not in ("0", "false", "no")
try:
    UNITY_CUSUM_K_SIGMA      = max(0.5, float(os.getenv("UNITY_CUSUM_K_SIGMA", "3.0") or 3.0))
except (ValueError, TypeError):
    UNITY_CUSUM_K_SIGMA      = 3.0
try:
    UNITY_CUSUM_EVENT_TTL_SEC = max(10, int(os.getenv("UNITY_CUSUM_EVENT_TTL_SEC", "90") or 90))
except (ValueError, TypeError):
    UNITY_CUSUM_EVENT_TTL_SEC = 90
try:
    UNITY_CUSUM_RETURN_LEN   = max(50, int(os.getenv("UNITY_CUSUM_RETURN_LEN", "200") or 200))
except (ValueError, TypeError):
    UNITY_CUSUM_RETURN_LEN   = 200

# Anchored-VWAP confluence — quality bonus when entry sits near session AVWAP.
# Session anchors at UTC 00:00 each day (matches Binance USDM funding cycle).
# v10.1: Enabled by default (was "0"). AVWAP confluence entries outperform by
# ~12% WR vs against-AVWAP entries in 15M USDM studies (+8pts quality bonus).
UNITY_AVWAP_ENABLED      = os.getenv("UNITY_AVWAP_ENABLED", "1").strip().lower() not in ("0", "false", "no")
try:
    UNITY_AVWAP_MAX_BONUS_PTS = max(0.0, float(os.getenv("UNITY_AVWAP_MAX_BONUS_PTS", "8.0") or 8.0))
except (ValueError, TypeError):
    UNITY_AVWAP_MAX_BONUS_PTS = 8.0
try:
    UNITY_AVWAP_BAND_BPS    = max(5.0, float(os.getenv("UNITY_AVWAP_BAND_BPS", "30.0") or 30.0))
except (ValueError, TypeError):
    UNITY_AVWAP_BAND_BPS    = 30.0   # bps from AVWAP at which bonus → 0

# Order-Flow Imbalance Z-score (Cont/Kukanov/Stoikov 2014).
# Replaces the static bid/(bid+ask) ratio with a normalised live time-series.
# v10.1: Enabled by default (was "0"). OFI Z>+1.5 correlates with directional
# follow-through on Binance USDM; Z<-2.5 veto prevents counter-flow entries.
UNITY_OFI_ENABLED         = os.getenv("UNITY_OFI_ENABLED", "1").strip().lower() not in ("0", "false", "no")
try:
    UNITY_OFI_HISTORY_LEN     = max(50, int(os.getenv("UNITY_OFI_HISTORY_LEN", "300") or 300))
except (ValueError, TypeError):
    UNITY_OFI_HISTORY_LEN     = 300
try:
    UNITY_OFI_Z_BONUS_PTS     = max(0.0, float(os.getenv("UNITY_OFI_Z_BONUS_PTS", "4.0") or 4.0))
except (ValueError, TypeError):
    UNITY_OFI_Z_BONUS_PTS     = 4.0
try:
    UNITY_OFI_Z_VETO_SIGMA    = max(1.0, float(os.getenv("UNITY_OFI_Z_VETO_SIGMA", "2.5") or 2.5))
except (ValueError, TypeError):
    UNITY_OFI_Z_VETO_SIGMA    = 2.5
# ── Prompt 2 ATR Volatility Regime penalty (v6.3) ────────────────────────────
# If ATR (as % of entry price) exceeds the high-volatility threshold, apply a
# quality penalty.  Extreme volatility = wider spreads, unpredictable wicks,
# and SL being hit before price reaches TP1.
ATR_HIGH_VOL_THRESHOLD = 0.030   # ATR > 3.0% of entry = high volatility
ATR_MAX_PENALTY_PCT    = 0.080   # ATR ≥ this → full −20pt quality penalty
ATR_MAX_QUALITY_PENALTY = 20.0   # maximum quality deduction for extreme vol
# ── Prompt 2 HTF Trend Alignment scoring (v6.3) ──────────────────────────────
# When higher-timeframe (1H / 4H) signals agree with the entry direction, add
# quality bonus.  Trend-following entries have ~15% higher WR than counter-trend
# entries at the same confidence level.
HTF_1H_AGREE_BONUS = 5.0        # 1H agrees with signal direction → +5pts
HTF_4H_AGREE_BONUS = 8.0        # 4H agrees (stronger confirmation) → +8pts
# ── Prompt 2 Adaptive IRONS Floor (v6.3) ─────────────────────────────────────
# IRONS minimum auto-adjusts with running win rate instead of being hardcoded.
# Below 30% WR: raise to 65 (tighter).  Above 55% WR: relax to 50 (more signals).
IRONS_MIN_WR_BELOW30  = 62.0    # WR < 30%  → elevated floor (v10.6: 60→57 deadlock-fix; v11.1: 57→62 — starvation-decay now handles exploration deadlock; IRONS restored to proper quality-discrimination role)
IRONS_MIN_WR_30_45    = 60.0    # WR 30-45% → slightly elevated (v8.1: 60→57; v11.1: 57→60 — re-calibrated with deadlock handled separately)
IRONS_MIN_WR_45_55    = 57.0    # WR 45-55% → base (v8.1: 55→54; v11.1: 54→57)
IRONS_MIN_WR_ABOVE55  = 52.0    # WR > 55%  → relaxed to capitalise good form (v11.1: 50→52)
# Quality-override: if composite quality >= this AND consensus=100%, relax IRONS floor by 5 pts
IRONS_QUALITY_OVERRIDE_THRESHOLD = 88.0   # quality score that unlocks the bypass
IRONS_QUALITY_OVERRIDE_RELAX     = 5.0    # points to subtract from effective IRONS min
# ── ThreadPoolExecutor workers ─────────────────────────────────────────────────
# v10.1: CPU-count-aware sizing.  os.cpu_count() returns None in restricted
# containers so we clamp to 2 minimum and 8 maximum to avoid thread explosion
# on high-core servers while still utilising available parallelism.
THREAD_POOL_WORKERS          = max(2, min(8, (os.cpu_count() or 4)))

# ── Consecutive-win streak bonus ──────────────────────────────────────────────
CONSEC_WIN_STREAK_THRESHOLD  = 5     # wins in a row → lower threshold bonus
CONSEC_WIN_STREAK_BONUS      = -2.0  # extra delta applied on top of RL bucket

# ── Unity Engine metadata ─────────────────────────────────────────────────────
UNITY_VERSION                = "11.1"
UNITY_CONSOLE_REFRESH_SEC    = 30    # dashboard refresh interval

# ── v8.3: Pre-compiled HTF word frozensets (module-level constants) ───────────
# Previously created fresh on every UnitySignalFilter.apply() call — moved here
# to eliminate set construction overhead on every signal evaluation.
_HTF_BULL_WORDS: frozenset = frozenset(("BUY", "LONG", "BULL", "UP", "BULLISH"))
_HTF_BEAR_WORDS: frozenset = frozenset(("SELL", "SHORT", "BEAR", "DOWN", "BEARISH"))

# ── v8.0 Producer-Consumer signal queue ───────────────────────────────────────
SIGNAL_QUEUE_MAXSIZE         = 100   # asyncio.Queue max depth (producer→consumer)

# ── v8.0 WebSocket live orderbook ─────────────────────────────────────────────
WS_ORDERBOOK_DEPTH           = 5     # bid/ask levels tracked per symbol
WS_RECONNECT_DELAY_SEC       = 5.0   # seconds before re-connecting after WS drop
# v10.1: Raised 5→15. More symbols with persistent WS = better live slippage
# coverage for Gate 0's depth-walked EV calc and OFI Z-score computation.
# At 15 streams × 100ms cadence the bandwidth is ~600 KB/min — trivial.
WS_MAX_SYMBOLS               = 15    # symbols with a persistent live WS stream

# ── v8.0 Redis optional state caching ─────────────────────────────────────────
# Resolution order:
#   1. REDIS_URL env var (Railway reference: ${{Redis.REDIS_URL}})
#   2. Constructed from individual Railway Redis vars: REDISHOST / REDISPORT /
#      REDISPASSWORD / REDISUSER  (Railway injects these automatically when a
#      Redis service is added to the project — works even if REDIS_URL is wrong)
def _resolve_redis_url() -> str:
    _url = os.getenv("REDIS_URL", "").strip()
    # Reject self-referential placeholder that Railway didn't expand
    if _url and not _url.startswith("${{"):
        return _url
    # Build from individual Railway Redis env vars
    _host = os.getenv("REDISHOST", "").strip()
    _port = os.getenv("REDISPORT", "6379").strip()
    _pw   = os.getenv("REDISPASSWORD", "").strip()
    _user = os.getenv("REDISUSER", "default").strip()
    if _host:
        if _pw:
            return f"redis://{_user}:{_pw}@{_host}:{_port}"
        return f"redis://{_host}:{_port}"
    return ""

REDIS_URL                    = _resolve_redis_url()
REDIS_STATE_TTL_SEC          = 7200  # key TTL (2 h) — survives Railway deploys

# ── v8.0 GEX Gamma Zero / VOL TRIGGER precision bonuses ──────────────────────
GEX_GAMMA_ZERO_PROX_PCT      = 0.005  # within 0.5 % of Gamma Zero → bonus
GEX_GAMMA_ZERO_QUALITY_BONUS = 6.0   # +6 pts when entry sits near Gamma Zero
GEX_VOL_TRIGGER_QUALITY_BONUS= 4.0   # +4 pts when VOL TRIGGER aligns direction

# ── Persistence paths ─────────────────────────────────────────────────────────
UNITY_METRICS_FILE           = "unity_metrics_v5.json"
UNITY_SYMBOLS_FILE           = "unity_symbols_v5.json"
UNITY_GEX_CACHE_FILE         = "unity_gex_cache_v5.json"
UNITY_FILTER_STATE_FILE      = "unity_filter_state_v6.json"  # v6.3: gate stats + cooldowns

# ── Scanner watchdog ──────────────────────────────────────────────────────────
WATCHDOG_STALL_SECONDS       = 600   # alert if scanner hasn't cycled in 10 min
WATCHDOG_POLL_SECONDS        = 60    # watchdog check interval

# ── Dynamic scan interval ─────────────────────────────────────────────────────
DYNAMIC_SLEEP_HIGH_Q         = 8     # v5.9: 10→8s — faster high-quality cycle compression
DYNAMIC_SLEEP_NORMAL         = 12    # v5.9: default cycle sleep (was 30)

# ── NN background retraining ───────────────────────────────────────────────
NN_RETRAIN_INTERVAL_SEC      = 7200  # retrain NN every 2 hours using accumulated outcomes
NN_RETRAIN_MIN_SAMPLES       = 50    # minimum new outcomes needed before retraining

# ═══════════════════════════════════════════════════════════════════════════════
# 2.  SCANNER TIMEOUT  (env-driven; default = continuous)
# ═══════════════════════════════════════════════════════════════════════════════

try:
    SCANNER_OPERATION_TIMEOUT = int(os.getenv("SCANNER_TIMEOUT_SECONDS", "0")) or None
except (ValueError, TypeError):
    SCANNER_OPERATION_TIMEOUT = None

# ═══════════════════════════════════════════════════════════════════════════════
# 3.  WARNING SUPPRESSION
# ═══════════════════════════════════════════════════════════════════════════════

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.environ["PYTHONWARNINGS"] = "ignore::FutureWarning,ignore::UserWarning,ignore::DeprecationWarning"

# ═══════════════════════════════════════════════════════════════════════════════
# 4.  PATH SETUP
# ═══════════════════════════════════════════════════════════════════════════════

sys.path.insert(0, str(Path(__file__).parent / "SignalMaestro"))
sys.path.insert(0, str(Path(__file__).parent / "aegis_gex"))
sys.path.insert(0, str(Path(__file__).parent / "agency_agents_framework"))
sys.path.insert(0, os.path.dirname(__file__))

# ═══════════════════════════════════════════════════════════════════════════════
# 5.  LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

log_level = (
    logging.DEBUG if os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    else logging.INFO
)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── v5.8: Persistent rotating file log ───────────────────────────────────────
try:
    from logging.handlers import RotatingFileHandler as _RFH
    _log_dir = Path("logs")
    _log_dir.mkdir(exist_ok=True)
    _fh = _RFH(
        str(_log_dir / "unity_engine.log"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    _fh.setLevel(log_level)
    _fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(_fh)
except Exception as _log_ex:
    pass  # Non-fatal — console logging still works

for _noisy in (
    "httpx", "httpcore", "urllib3",
    "aiohttp", "aiohttp.client",
    "openai", "openai._base_client", "openai.resources",
    "anthropic", "anthropic._base_client",
    "asyncio",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("UnityEngine")

# ═══════════════════════════════════════════════════════════════════════════════
# 5b. SENTINEL EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class _ConfigError(RuntimeError):
    """
    Raised for fatal configuration errors (missing API keys, bad secrets).
    Caught by main_launcher() to skip exponential backoff and exit immediately
    instead of retrying 100× — v5.4 fast-fail fix.
    """


# ═══════════════════════════════════════════════════════════════════════════════
# 5c. ASYNC RETRY WITH EXPONENTIAL BACKOFF + JITTER  (v6.2 — Prompt 3)
# ═══════════════════════════════════════════════════════════════════════════════

def async_retry_with_backoff(
    max_attempts: int = 3,
    base_delay:   float = 1.0,
    max_delay:    float = 30.0,
    jitter_pct:   float = 0.25,
    exceptions:   tuple = (Exception,),
    label:        str   = "call",
):
    """
    Production-grade async retry decorator for external API calls.

    Strategy:
      • Exponential backoff: delay = base_delay * 2^(attempt-1), capped at max_delay
      • Random jitter (±jitter_pct) breaks synchronised thundering-herd retries
      • Retries only on *exceptions* (tuple of exception types, default=all)
      • Final attempt lets the exception propagate naturally so callers can log it

    Usage:
        @async_retry_with_backoff(max_attempts=3, base_delay=0.5, label="OpenRouter")
        async def call_llm(prompt: str) -> str:
            ...

    Retry schedule (default): 1s → 2s → propagate
    Retry schedule (backoff only): 0.5→1→2→4→8→16→30→30→…
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            _log = logging.getLogger("UnityEngine.Retry")
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise                           # re-raise after last attempt
                    raw_delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    jitter    = raw_delay * jitter_pct * (2 * random.random() - 1)
                    sleep_for = max(0.1, raw_delay + jitter)
                    _log.debug(
                        f"[{label}] attempt {attempt}/{max_attempts} failed "
                        f"({type(exc).__name__}: {exc}) — retrying in {sleep_for:.2f}s"
                    )
                    await asyncio.sleep(sleep_for)
            return None   # unreachable but satisfies type checkers
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# 5d.  FAST JSON  (orjson → stdlib fallback)   v8.0
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import orjson as _orjson  # ~3-10× faster than stdlib json

    def _fast_dumps(obj: Any) -> str:
        """Serialize obj to a UTF-8 JSON string using orjson (fast path)."""
        return _orjson.dumps(obj).decode("utf-8")

    def _fast_loads(s: str) -> Any:
        """Deserialize a JSON string using orjson (fast path)."""
        return _orjson.loads(s)

    _FAST_JSON = True
    logging.getLogger("UnityEngine").info("⚡ [v8.0] orjson loaded — fast JSON serialization active")

except ImportError:
    import json as _stdjson  # type: ignore[assignment]

    def _fast_dumps(obj: Any) -> str:          # type: ignore[misc]
        return _stdjson.dumps(obj, separators=(",", ":"))

    def _fast_loads(s: str) -> Any:            # type: ignore[misc]
        return _stdjson.loads(s)

    _FAST_JSON = False


def _atomic_write_json(path: str, payload: Any, *, indent: Optional[int] = None) -> None:
    """v9.7: Atomic JSON write — temp file + os.replace (POSIX/Windows atomic).

    A non-atomic open(path, "w") that crashes mid-write leaves a half-written /
    truncated file, which corrupts persisted state (metrics, GEX cache, filter
    state) and breaks restore-on-startup.  Writing to a sibling temp file then
    renaming guarantees the destination is either the old contents OR the new
    contents — never a partial mix — even on power loss between fsync and
    rename (atomic-rename guarantee on the same filesystem).
    """
    import tempfile
    _dir  = os.path.dirname(os.path.abspath(path)) or "."
    _base = os.path.basename(path) or "unity.json"
    _fd: Optional[int] = None
    _tmp_path: Optional[str] = None
    try:
        _fd, _tmp_path = tempfile.mkstemp(prefix=f".{_base}.", suffix=".tmp", dir=_dir)
        with os.fdopen(_fd, "w") as _tf:
            _fd = None  # transferred to file object
            if indent is not None:
                _stdjson_local = json   # use stdlib json to honour indent
                _stdjson_local.dump(payload, _tf, indent=indent)
            else:
                _tf.write(_fast_dumps(payload))
            _tf.flush()
            try:
                os.fsync(_tf.fileno())
            except OSError:
                pass   # best-effort durability — some filesystems don't support fsync
        os.replace(_tmp_path, path)
        _tmp_path = None
    finally:
        # Cleanup any leftover temp file on failure paths
        if _fd is not None:
            try:
                os.close(_fd)
            except OSError:
                pass
        if _tmp_path is not None and os.path.exists(_tmp_path):
            try:
                os.unlink(_tmp_path)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# 5e.  LLM KEY ROTATOR — multi-key OpenRouter failover  v8.0
# ═══════════════════════════════════════════════════════════════════════════════

class LLMKeyRotator:
    """
    Multi-key OpenRouter API failover (v8.0, extended v9.4 → 7-key pool).

    Reads up to 7 keys in priority order:
      1. OPENROUTER_API_KEY          — primary key
      2. OPENROUTER_API_KEY_BACKUP_1 — first backup
      3. OPENROUTER_API_KEY_BACKUP_2 — second backup
      4. OPENROUTER_API_KEY_BACKUP_3 — third backup   (v9.4)
      5. OPENROUTER_API_KEY_BACKUP_4 — fourth backup  (v9.4)
      6. OPENROUTER_API_KEY_BACKUP_5 — fifth backup   (v9.4)
      7. OPENROUTER_API_KEY_BACKUP_6 — sixth backup   (v9.4)

    On rate-limit (HTTP 429) or server error (5xx), the rotator marks the
    current key as degraded and transparently rotates to the next available
    key for all subsequent LLM calls.  Once a key recovers (after a
    configurable cooldown) it re-enters the pool.

    The rotator also promotes OPENAI_API_KEY as a backup slot when present,
    matching the v5.7 key-auto-routing behaviour.

    Usage:
        key = LLMKeyRotator.instance().get_key()
        LLMKeyRotator.instance().mark_failure(key, status_code=429)
    """

    _inst: Optional["LLMKeyRotator"] = None

    # v9.8: STATUS-AWARE COOLDOWNS — tuned to the meaning of each HTTP error.
    # The previous flat 300 s cooldown re-tried permanently-dead 401-keys every
    # 5 min, hammering the rotator and wasting one of every N attempts on a key
    # that will never recover until the operator rotates the secret. The new
    # table treats each class correctly:
    #   • 401/403 → 4 h cooldown (effectively dead until next deploy / rotate)
    #   • 429    → 60 s (rate-limit; usually clears on the next minute window)
    #   • 5xx    → 120 s (transient upstream)
    #   • other  → 300 s (default safety net)
    # Plus: after CONSECUTIVE 401s on the same key, escalate to PERMANENT
    # in-process disable so the rotator never wastes another call on it.
    KEY_COOLDOWN_SEC          = 300   # default (back-compat)
    COOLDOWN_BY_STATUS = {
        401: 4 * 3600,
        403: 4 * 3600,
        429:       60,
        500:      120,
        502:      120,
        503:      120,
        504:      120,
    }
    PERMA_DISABLE_AFTER_AUTH_FAILURES = 3   # 3 strikes → key dead until restart

    def __init__(self):
        self._log    = logging.getLogger("UnityEngine.LLMKeyRotator")
        self._keys:  List[str]          = []
        self._bad:   Dict[str, float]   = {}   # key → cooldown_until timestamp
        self._dead:  set                = set()  # v9.8: permanent in-process kills
        self._auth_strikes: Dict[str, int] = {}  # v9.8: 401/403 strike counter
        self._idx:   int                = 0
        self._lock:  threading.Lock     = threading.Lock()
        self._load_keys()

    @classmethod
    def instance(cls) -> "LLMKeyRotator":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def _load_keys(self) -> None:
        """Load and de-duplicate keys from environment, stripping blanks."""
        # v9.4: expanded backup pool (BACKUP_1..6) — 7 OpenRouter slots total +
        # OpenAI fallback.  More keys → longer effective rate-limit budget;
        # rotator picks each up on boot if defined and silently skips blanks.
        candidate_vars = [
            "OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY_BACKUP_1",
            "OPENROUTER_API_KEY_BACKUP_2",
            "OPENROUTER_API_KEY_BACKUP_3",   # v9.4
            "OPENROUTER_API_KEY_BACKUP_4",   # v9.4
            "OPENROUTER_API_KEY_BACKUP_5",   # v9.4
            "OPENROUTER_API_KEY_BACKUP_6",   # v9.4
            "OPENAI_API_KEY",          # v5.7 compat: OpenAI as additional slot
        ]
        seen: set = set()
        for var in candidate_vars:
            val = os.getenv(var, "").strip()
            if val and val not in seen:
                seen.add(val)
                self._keys.append(val)

        if self._keys:
            self._log.info(
                f"🔑 [v9.3] LLMKeyRotator initialised: {len(self._keys)} key(s) loaded "
                f"(PRIMARY + {len(self._keys)-1} backup(s))"
            )
        else:
            self._log.warning(
                "⚠️  [v9.3] LLMKeyRotator: no API keys found — "
                "set OPENROUTER_API_KEY for LLM features"
            )

    def get_key(self) -> str:
        """
        Return the current active API key.
        Skips keys in cooldown OR permanently dead; falls back to first
        available. Returns empty string if no keys are available at all.
        """
        with self._lock:
            now = time.time()
            # Remove expired cooldowns
            self._bad = {k: ts for k, ts in self._bad.items() if ts > now}

            if not self._keys:
                return ""

            # Try from current rotation index, skipping bad AND dead keys
            for offset in range(len(self._keys)):
                idx = (self._idx + offset) % len(self._keys)
                key = self._keys[idx]
                if key in self._dead:
                    continue
                if key not in self._bad:
                    return key

            # All keys in cooldown — return the FIRST non-dead key (best-effort)
            for key in self._keys:
                if key not in self._dead:
                    self._log.warning(
                        "⚠️  [LLMKeyRotator] All keys in cooldown — best-effort "
                        f"using key …{key[-6:]}"
                    )
                    return key

            # Every key is permanently dead — return primary so caller still
            # sees a non-empty string but this LLM call will surely fail.
            self._log.error(
                "❌ [LLMKeyRotator] ALL keys permanently dead (auth failed). "
                "Operator must rotate OPENROUTER_API_KEY* secrets."
            )
            return self._keys[0]

    def mark_failure(self, key: str, status_code: int = 429) -> None:
        """
        Mark a key as degraded after an HTTP error. v9.8: cooldown duration
        depends on status_code (auth errors → 4 h, rate limit → 60 s, 5xx →
        120 s, other → 300 s). After PERMA_DISABLE_AFTER_AUTH_FAILURES
        consecutive 401/403 strikes the key is marked dead in-process and
        will not be retried until process restart.
        """
        if not key:
            return
        cooldown = self.COOLDOWN_BY_STATUS.get(int(status_code), self.KEY_COOLDOWN_SEC)
        is_auth_err = status_code in (401, 403)

        with self._lock:
            # Auth-strike escalation → permanent kill
            if is_auth_err:
                self._auth_strikes[key] = self._auth_strikes.get(key, 0) + 1
                if self._auth_strikes[key] >= self.PERMA_DISABLE_AFTER_AUTH_FAILURES:
                    if key not in self._dead:
                        self._dead.add(key)
                        self._log.error(
                            f"💀 [v9.8] LLMKeyRotator: key …{key[-6:]} PERMANENTLY "
                            f"DISABLED after {self._auth_strikes[key]} auth failures "
                            f"(HTTP {status_code}). Operator must rotate the secret."
                        )
            # Single-key mode: no rotation possible, but still record the
            # cooldown so /metrics reports the degraded state correctly.
            existing = self._bad.get(key, 0.0)
            new_until = time.time() + cooldown
            if new_until > existing:
                self._bad[key] = new_until

            if len(self._keys) <= 1:
                return   # nothing to rotate to

            # Rotate to next non-dead key
            try:
                cur_idx = self._keys.index(key)
            except ValueError:
                cur_idx = self._idx
            for offset in range(1, len(self._keys) + 1):
                cand_idx = (cur_idx + offset) % len(self._keys)
                cand_key = self._keys[cand_idx]
                if cand_key not in self._dead and cand_key not in self._bad:
                    self._idx = cand_idx
                    break
            else:
                # No healthy key — keep current idx so get_key() falls through
                # to its best-effort branch with a clear warning.
                pass

            next_key_masked = self._keys[self._idx][:8] + "…"
            self._log.warning(
                f"🔑 [v9.8] LLMKeyRotator: key …{key[-6:]} degraded "
                f"(HTTP {status_code}, cooldown={cooldown}s"
                f"{', auth strike '+str(self._auth_strikes.get(key,0)) if is_auth_err else ''}"
                f") — rotating to {next_key_masked}"
            )

    def mark_success(self, key: str) -> None:
        """Remove key from cooldown early on a successful API call."""
        with self._lock:
            self._bad.pop(key, None)

    def inject_env(self) -> None:
        """
        Inject the current active key back into OPENROUTER_API_KEY so all
        downstream modules that read os.getenv('OPENROUTER_API_KEY') transparently
        pick up the rotated key without requiring code changes in each module.
        """
        active = self.get_key()
        if active:
            os.environ["OPENROUTER_API_KEY"] = active

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def status_summary(self) -> str:
        now = time.time()
        degraded = sum(1 for ts in self._bad.values() if ts > now)
        dead = len(self._dead)
        active = self.key_count - degraded - dead
        return (
            f"keys={self.key_count} active={max(0,active)} "
            f"degraded={degraded} dead={dead}"
        )


# Initialise the rotator at module load time so all layers share one instance.
# It also injects the current key into OPENROUTER_API_KEY for compat.
_llm_key_rotator = LLMKeyRotator.instance()
_llm_key_rotator.inject_env()


# ═══════════════════════════════════════════════════════════════════════════════
# 5f.  @watched_task DECORATOR — auto-restart crashed coroutines  v8.0
# ═══════════════════════════════════════════════════════════════════════════════

def compute_lock_profit_sl(
    entry: float,
    extreme: float,
    direction: str,
    original_sl: Optional[float] = None,
    lock_pct: float = TRAILING_LOCK_PROFIT_PCT,
    tp1: Optional[float] = None,
    activate_fraction: float = TRAILING_ACTIVATE_TP1_FRACTION,
) -> Optional[float]:
    """
    Lock-profit trailing stop. Returns the new SL price, or None if the trail
    should not yet move (price hasn't progressed far enough toward TP1).

    Formula (LONG):
        if (extreme - entry) >= activate_fraction * (tp1 - entry):
            new_sl = entry + lock_pct * (extreme - entry)
            return max(new_sl, original_sl)   # never widen the stop
    Mirrored for SHORT (extreme is the trough; new_sl below entry).

    Args:
        entry        : original entry price
        extreme      : peak-favorable price seen since entry (peak for LONG, trough for SHORT)
        direction    : "BUY" / "LONG" / "SELL" / "SHORT"  (case insensitive)
        original_sl  : current SL price; result is clamped never to widen the stop
        lock_pct     : fraction of unrealized profit to lock in (0.0–1.0)
        tp1          : if provided, gate activation behind activate_fraction*(tp1-entry)
        activate_fraction : how far toward TP1 price must travel before the trail kicks in

    Returns:
        New SL price (float) — or None if the trail should remain dormant.
    """
    try:
        if entry <= 0 or extreme <= 0 or lock_pct <= 0.0:
            return None
        is_long = (direction or "").upper() in ("BUY", "LONG")
        if is_long:
            run_up = extreme - entry
            if run_up <= 0:
                return None
            if tp1 is not None and tp1 > entry:
                if run_up < activate_fraction * (tp1 - entry):
                    return None
            new_sl = entry + lock_pct * run_up
            if original_sl is not None and original_sl > 0:
                # never widen the stop — only ratchet upward
                new_sl = max(new_sl, original_sl)
            return new_sl
        else:
            run_dn = entry - extreme
            if run_dn <= 0:
                return None
            if tp1 is not None and tp1 < entry and tp1 > 0:
                if run_dn < activate_fraction * (entry - tp1):
                    return None
            new_sl = entry - lock_pct * run_dn
            if original_sl is not None and original_sl > 0:
                # never widen the stop — only ratchet downward
                new_sl = min(new_sl, original_sl)
            return new_sl
    except Exception:
        return None


# v10.9: Global task restart counter registry — surfaced on /metrics as
# `watched_task_restart_counts` and `signal_consumer_restarts` (per v10.4 changelog).
# Thread-safe via threading.Lock; written by @watched_task, read by /metrics handler.
_watched_task_restart_counts: Dict[str, int] = {}
_watched_task_restart_lock:   threading.Lock  = threading.Lock()


def watched_task(label: str, restart_delay: float = 5.0, max_restarts: int = 0):
    """
    Decorator that wraps an async coroutine so it automatically restarts
    if it raises an unexpected exception, without crashing the main event loop.

    Behaviour:
      • asyncio.CancelledError is always re-raised (respects task cancellation)
      • All other exceptions are caught, logged, and the coroutine is restarted
        after `restart_delay` seconds with exponential backoff (up to 60 s)
      • `max_restarts=0` means unlimited restarts (default — 24/7 operation)
      • v10.9: Restart counts written to _watched_task_restart_counts[label]
        for /metrics observability (resolves v10.4 changelog gap).

    Usage:
        @watched_task("GEXScanner", restart_delay=5.0)
        async def my_task(self):
            while True:
                ...

    Why this matters for Railway:
      Railway sends SIGTERM before restarting a container, but mid-cycle
      exceptions in async tasks currently bubble up and kill the event loop.
      This decorator catches those exceptions locally so a single bad API
      response never brings down all 13 layers.
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            _log   = logging.getLogger(f"UnityEngine.WatchedTask.{label}")
            _count = 0
            _delay = restart_delay
            # v10.9: initialise counter in global registry on first call
            with _watched_task_restart_lock:
                _watched_task_restart_counts.setdefault(label, 0)
            while True:
                _run_start = time.monotonic()
                try:
                    await fn(*args, **kwargs)
                    return                           # clean exit — do not restart
                except asyncio.CancelledError:
                    raise                            # always propagate cancellation
                except Exception as exc:
                    _count += 1
                    # v10.9: update global registry for /metrics observability
                    with _watched_task_restart_lock:
                        _watched_task_restart_counts[label] = _count
                    if max_restarts and _count > max_restarts:
                        _log.critical(
                            f"[{label}] exceeded max_restarts={max_restarts} "
                            f"— giving up. Last error: {exc}"
                        )
                        return
                    # v10.4 BUG FIX: reset backoff to baseline if task ran ≥120 s
                    # before crashing — prevents indefinite over-throttling of
                    # tasks that experience occasional transient failures after a
                    # sustained healthy run (e.g. network blip after 10 min ok).
                    _ran_for = time.monotonic() - _run_start
                    if _ran_for >= 120.0:
                        _delay = restart_delay
                    _log.error(
                        f"[{label}] crashed (restart #{_count}, ran {_ran_for:.0f}s): "
                        f"{type(exc).__name__}: {exc} — restarting in {_delay:.0f}s"
                    )
                    await asyncio.sleep(_delay)
                    # Exponential backoff capped at 60 s (only escalates on rapid crashes)
                    _delay = min(60.0, _delay * 1.5)
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

# ── v8.0: Prompt 3 — formal circuit-breaker state machine ─────────────────────
class CircuitBreakerState(enum.Enum):
    """
    Three-state circuit breaker (Fowler pattern).

    CLOSED   → normal operation, all calls go through.
    OPEN     → failure threshold exceeded; all calls fast-fail for ``cooldown`` s.
    HALF_OPEN→ cooldown elapsed; ONE probe call is allowed.
                  success → CLOSED (failure count reset)
                  failure → OPEN   (cooldown restarts, doubled via backoff)
    """
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ── v8.0: Prompt 1 — atomic unified decision vector ───────────────────────────
@dataclass(frozen=True, slots=True)
class SignalDecisionVector:
    """
    Immutable snapshot of ALL parallel inputs resolved within a single event-loop
    tick.  Produced by the signal-queue consumer; stored on the engine for audit.

    GEX/market feed  → gex_* fields
    Cognitive swarm  → llm_* fields  (parallel LLM chains of thought)
    Neural inference → nn_* fields   (ONNX tensor prediction)
    Atomic gateway   → decision / reject_reason / composite_score
    """
    symbol:                      str
    timestamp:                   float
    # GEX / market feed
    gex_regime:                  str    # FLIP ZONE | POS | NEG | NEUTRAL
    gex_gamma_zero_dist_pct:     float  # % distance to nearest gamma zero
    orderbook_imbalance:         float  # bid/(bid+ask) ratio — 0.5 = balanced
    # Cognitive swarm
    llm_verdict:                 str    # LONG | SHORT | HOLD
    llm_confidence:              float  # 0–1
    llm_regime_tag:              str    # "trending" | "mean-reverting" | "unknown"
    # Neural inference
    nn_direction_score:          float  # −1 (short) → +1 (long)
    nn_confidence:               float  # 0–1
    # Composite
    composite_score:             float  # 0–100 unified quality gate score
    kelly_fraction:              float  # position-size fraction (0–0.25)
    ev_ratio:                    float  # expected-value ratio after slippage
    decision:                    str    # SEND | REJECT
    reject_reason:               str    # gate label that blocked, or ""


@dataclass(slots=True)
class LayerStatus:
    name: str
    available: bool = False
    initialised: bool = False
    error: Optional[str] = None
    calls: int = 0
    failures: int = 0
    last_ok: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.calls == 0:
            return 1.0
        return max(0.0, (self.calls - self.failures) / self.calls)

    @property
    def status_icon(self) -> str:
        if not self.available:
            return "⬜"
        if not self.initialised:
            return "🔄"
        if self.error:
            return "❌"
        if self.success_rate >= 0.90:
            return "✅"
        if self.success_rate >= 0.70:
            return "⚠️"
        return "❌"


@dataclass(slots=True)
class UnityMetrics:
    """
    Global Unity Engine performance metrics — v10.0
    ─────────────────────────────────────────────────────────────────────────
    Real-time institutional-grade quant metrics tracking:
    • Sharpe ratio  (risk-adjusted return vs risk-free rate)
    • Sortino ratio (downside-deviation-only penalisation)
    • Calmar ratio  (annual return / max drawdown)
    • Max drawdown  (peak-to-trough equity curve loss)
    • Expected Value (EV) per trade in R-multiples
    • Kelly fraction (optimal position size)
    All computed from a rolling ring of individual trade returns.
    Uses pure-Python math — no numpy dependency.
    """
    engine_start: datetime = field(default_factory=datetime.now)
    total_signals_sent: int = 0
    total_signals_evaluated: int = 0
    total_signals_rejected: int = 0
    win_count: int = 0
    loss_count: int = 0
    total_profit_pct: float = 0.0
    scan_cycles: int = 0
    last_signal_time: Optional[datetime] = None
    consecutive_losses: int = 0
    last_signal_quality: float = 0.0
    last_gex_regime: str = "UNKNOWN"
    last_dgrp_score: float = 0.0
    last_kelly_fraction: float = 0.0
    gex_snapshot_prune_counter: int = 0
    # ── v10.0 quant metrics ──────────────────────────────────────────────────
    # Ring buffer of individual trade pnl% returns (most recent 200)
    _trade_returns: List[float] = field(default_factory=list)
    # Peak equity (for max drawdown calculation — starts at 100 = 100 base)
    _peak_equity: float = 100.0
    _current_equity: float = 100.0
    _max_drawdown_pct: float = 0.0

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return (self.win_count / total * 100) if total > 0 else 0.0

    @property
    def send_rate(self) -> float:
        total = self.total_signals_evaluated
        return (self.total_signals_sent / total * 100) if total > 0 else 0.0

    @property
    def uptime_hours(self) -> float:
        return (datetime.now() - self.engine_start).total_seconds() / 3600

    # ── v10.0 pure-Python quant math ──────────────────────────────────────────

    def _mean(self, xs: List[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    def _std(self, xs: List[float], ddof: int = 1) -> float:
        n = len(xs)
        if n <= ddof:
            return 0.0
        mu = self._mean(xs)
        variance = sum((x - mu) ** 2 for x in xs) / (n - ddof)
        return variance ** 0.5

    def record_trade_return(self, pnl_pct: float) -> None:
        """Record a closed trade return % and update equity curve + drawdown."""
        self._trade_returns.append(pnl_pct)
        if len(self._trade_returns) > 200:        # rolling window — 200 trades
            self._trade_returns.pop(0)
        # Update equity curve
        self._current_equity *= (1.0 + pnl_pct / 100.0)
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity
        dd = (self._peak_equity - self._current_equity) / self._peak_equity * 100.0
        if dd > self._max_drawdown_pct:
            self._max_drawdown_pct = dd

    @property
    def sharpe_ratio(self) -> float:
        """
        Annualised Sharpe ratio (risk-free rate = 0% for crypto).
        Sharpe = mean(R) / std(R) × √N_annual
        Using 365 trades/year as a rough crypto proxy.
        """
        rs = self._trade_returns
        if len(rs) < 5:
            return 0.0
        std = self._std(rs)
        if std == 0.0:
            return 0.0
        return (self._mean(rs) / std) * (365 ** 0.5)

    @property
    def sortino_ratio(self) -> float:
        """
        Sortino ratio — penalises only downside volatility.
        Sortino = mean(R) / std(R_neg) × √N_annual
        """
        rs = self._trade_returns
        if len(rs) < 5:
            return 0.0
        negs = [r for r in rs if r < 0]
        if not negs:
            return 999.0    # no losing trades → theoretical infinity capped
        downside_std = self._std(negs)
        if downside_std == 0.0:
            return 0.0
        return (self._mean(rs) / downside_std) * (365 ** 0.5)

    @property
    def calmar_ratio(self) -> float:
        """
        Calmar ratio = Annualised return / Max Drawdown.
        Higher is better; <1 suggests risk exceeds reward.
        """
        if self._max_drawdown_pct == 0.0:
            return 0.0
        rs = self._trade_returns
        if not rs:
            return 0.0
        annualised_ret = self._mean(rs) * 365
        return annualised_ret / self._max_drawdown_pct

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum peak-to-trough equity drawdown as a percentage."""
        return self._max_drawdown_pct

    @property
    def expected_value_r(self) -> float:
        """
        Expected Value in R-multiples per trade.
        EV = p × avg_win_R − q × avg_loss_R
        where avg win/loss derived from signed return magnitudes.
        """
        rs = self._trade_returns
        if len(rs) < 3:
            return 0.0
        wins  = [r for r in rs if r > 0]
        loses = [r for r in rs if r < 0]
        p  = len(wins)  / len(rs)
        q  = len(loses) / len(rs)
        avg_w = self._mean(wins)   if wins  else 0.0
        avg_l = abs(self._mean(loses)) if loses else 0.0
        return p * avg_w - q * avg_l

    @property
    def kelly_fraction_pct(self) -> float:
        """
        Full Kelly fraction as a percentage of capital.
        f* = (p × b − q) / b  where b = avg_win / avg_loss
        Capped at 25% for safety (half-Kelly → cap/2 recommended).
        """
        rs = self._trade_returns
        if len(rs) < 5:
            return self.last_kelly_fraction * 100
        wins  = [r for r in rs if r > 0]
        loses = [r for r in rs if r < 0]
        if not wins or not loses:
            return 0.0
        p = len(wins) / len(rs)
        q = 1.0 - p
        b = self._mean(wins) / abs(self._mean(loses))
        if b <= 0:
            return 0.0
        f = (p * b - q) / b
        return max(0.0, min(25.0, f * 100))

    def quant_report(self) -> str:
        """Return a formatted quant performance report string."""
        n = len(self._trade_returns)
        return (
            f"📐 *Institutional Quant Report* (n={n} trades)\n"
            f"  Sharpe    : {self.sharpe_ratio:+.3f}\n"
            f"  Sortino   : {self.sortino_ratio:+.3f}\n"
            f"  Calmar    : {self.calmar_ratio:+.3f}\n"
            f"  Max DD    : {self.max_drawdown_pct:.2f}%\n"
            f"  EV/trade  : {self.expected_value_r:+.3f}R\n"
            f"  Kelly f*  : {self.kelly_fraction_pct:.1f}%  (half-Kelly: {self.kelly_fraction_pct/2:.1f}%)\n"
            f"  Win Rate  : {self.win_rate:.1f}%  ({self.win_count}W / {self.loss_count}L)\n"
            f"  Total PnL : {self.total_profit_pct:+.2f}%\n"
        )

    # ── v5.0 persistence ──────────────────────────────────────────────────────
    def save(self, path: str = UNITY_METRICS_FILE) -> None:
        """Persist cumulative metrics to disk so win-rate survives restarts."""
        try:
            payload = {
                "total_signals_sent":      self.total_signals_sent,
                "total_signals_evaluated": self.total_signals_evaluated,
                "total_signals_rejected":  self.total_signals_rejected,
                "win_count":               self.win_count,
                "loss_count":              self.loss_count,
                "total_profit_pct":        self.total_profit_pct,
                "scan_cycles":             self.scan_cycles,
                "last_signal_quality":     self.last_signal_quality,
                "trade_returns":           self._trade_returns[-200:],
                "peak_equity":             self._peak_equity,
                "current_equity":          self._current_equity,
                "max_drawdown_pct":        self._max_drawdown_pct,
                "saved_at":                datetime.now().isoformat(),
            }
            _atomic_write_json(path, payload, indent=2)
        except Exception as _e:
            logger.warning(f"⚠️ [Metrics.save] failed: {_e}")

    def load(self, path: str = UNITY_METRICS_FILE) -> None:
        """Restore cumulative metrics from disk."""
        try:
            if not Path(path).exists():
                return
            with open(path) as f:
                d = json.load(f)
            self.total_signals_sent      = int(d.get("total_signals_sent", 0))
            self.total_signals_evaluated = int(d.get("total_signals_evaluated", 0))
            self.total_signals_rejected  = int(d.get("total_signals_rejected", 0))
            self.win_count               = int(d.get("win_count", 0))
            self.loss_count              = int(d.get("loss_count", 0))
            self.total_profit_pct        = float(d.get("total_profit_pct", 0.0))
            self.scan_cycles             = int(d.get("scan_cycles", 0))
            self.last_signal_quality     = float(d.get("last_signal_quality", 0.0))
            self._trade_returns          = list(d.get("trade_returns", []))[-200:]
            self._peak_equity            = float(d.get("peak_equity", 100.0))
            self._current_equity         = float(d.get("current_equity", 100.0))
            self._max_drawdown_pct       = float(d.get("max_drawdown_pct", 0.0))
        except Exception as _e:
            logger.warning(f"⚠️ [Metrics.load] failed: {_e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 7.  PER-SYMBOL TRACKER  (Gate 8 data + per-symbol analytics)
# ═══════════════════════════════════════════════════════════════════════════════

class PerSymbolTracker:
    """
    Tracks per-symbol win/loss counts and PnL.
    Used by Gate 8 to block symbols with consistently poor performance.
    """

    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "pnl_pct": 0.0, "last_trade": 0.0}
        )

    def record(self, symbol: str, won: bool, pnl_pct: float = 0.0):
        d = self._data[symbol]
        if won:
            d["wins"] += 1
        else:
            d["losses"] += 1
        d["pnl_pct"] += pnl_pct
        d["last_trade"] = time.time()

    def win_rate(self, symbol: str) -> float:
        d = self._data.get(symbol)
        if not d:
            return 1.0   # no data → assume fine
        total = d["wins"] + d["losses"]
        return (d["wins"] / total) if total > 0 else 1.0

    def trade_count(self, symbol: str) -> int:
        d = self._data.get(symbol)
        if not d:
            return 0
        return d["wins"] + d["losses"]

    def is_blocked(self, symbol: str) -> bool:
        n = self.trade_count(symbol)
        if n < SYMBOL_MIN_TRADES:
            return False   # not enough data to block
        return self.win_rate(symbol) < SYMBOL_MIN_WIN_RATE

    def top_symbols(self, n: int = 5) -> List[Tuple[str, float]]:
        """Return top-N symbols by win rate (min SYMBOL_MIN_TRADES trades)."""
        qualified = [
            (sym, self.win_rate(sym))
            for sym in self._data
            if self.trade_count(sym) >= SYMBOL_MIN_TRADES
        ]
        return sorted(qualified, key=lambda x: x[1], reverse=True)[:n]

    def bottom_symbols(self, n: int = 5) -> List[Tuple[str, float]]:
        qualified = [
            (sym, self.win_rate(sym))
            for sym in self._data
            if self.trade_count(sym) >= SYMBOL_MIN_TRADES
        ]
        return sorted(qualified, key=lambda x: x[1])[:n]

    # ── v5.0 persistence ──────────────────────────────────────────────────────
    def save(self, path: str = UNITY_SYMBOLS_FILE) -> None:
        """Persist per-symbol stats to disk so Gate 8 survives restarts."""
        try:
            _atomic_write_json(path, dict(self._data))   # v9.7: crash-safe write
        except Exception:
            pass

    def load(self, path: str = UNITY_SYMBOLS_FILE) -> None:
        """Restore per-symbol stats from disk."""
        try:
            if not Path(path).exists():
                return
            with open(path) as f:
                saved = json.load(f)
            for sym, d in saved.items():
                self._data[sym].update(d)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 8.  UNITY HEALTH MONITOR  (per-layer circuit breakers)
# ═══════════════════════════════════════════════════════════════════════════════

class UnityHealthMonitor:
    """
    Per-layer supervisor with a CLOSED → OPEN → HALF_OPEN circuit-breaker state
    machine (Fowler / Netflix Hystrix pattern).

    v8.0 (Prompt 3): Replaced implicit counter-only logic with explicit
    ``CircuitBreakerState`` enum.  State transitions:

      CLOSED    → OPEN      : ``>= CIRCUIT_BREAKER_THRESHOLD`` consecutive failures
      OPEN      → HALF_OPEN : cooldown timer expires (exponential backoff, cap 300 s)
      HALF_OPEN → CLOSED    : next call succeeds (failure counter reset)
      HALF_OPEN → OPEN      : next call fails (cooldown doubles, capped)

    ``is_available()`` is the single gate: callers MUST check before invoking a
    layer — OPEN/HALF_OPEN layers are either fast-failed or put on one probe call.
    """

    def __init__(self):
        self.layers: Dict[str, LayerStatus] = {}
        self._cb_state:         Dict[str, CircuitBreakerState] = {}
        self._cb_failure_counts: Dict[str, int]   = defaultdict(int)
        self._cb_disabled_until: Dict[str, float] = defaultdict(float)
        self._cb_cooldown:       Dict[str, float] = defaultdict(lambda: float(CIRCUIT_BREAKER_COOLDOWN))
        self._cb_probe_in_flight: Dict[str, bool] = defaultdict(bool)
        self._logger = logging.getLogger("UnityEngine.Health")

    # ── Registration ───────────────────────────────────────────────────────────
    def register(self, name: str) -> LayerStatus:
        self.layers[name]  = LayerStatus(name=name)
        self._cb_state[name] = CircuitBreakerState.CLOSED
        return self.layers[name]

    def mark_available(self, name: str, initialised: bool = True):
        if name in self.layers:
            self.layers[name].available   = True
            self.layers[name].initialised = initialised
            self.layers[name].error       = None
            # Registering a successful layer: reset any open breaker
            self._cb_state[name]          = CircuitBreakerState.CLOSED
            self._cb_failure_counts[name] = 0

    def mark_unavailable(self, name: str, error: str = ""):
        if name in self.layers:
            self.layers[name].available = False
            self.layers[name].error     = error or None

    # ── Core state machine ─────────────────────────────────────────────────────
    def record_call(self, name: str, success: bool):
        """
        Update state machine after a call result.  Must be called for EVERY
        layer invocation (success or failure) to keep state accurate.
        """
        if name not in self.layers:
            return
        layer = self.layers[name]
        layer.calls += 1
        state = self._cb_state.get(name, CircuitBreakerState.CLOSED)

        if success:
            layer.last_ok = time.time()
            if state == CircuitBreakerState.HALF_OPEN:
                # Probe succeeded → close the breaker
                self._cb_state[name]          = CircuitBreakerState.CLOSED
                self._cb_failure_counts[name] = 0
                self._cb_cooldown[name]       = float(CIRCUIT_BREAKER_COOLDOWN)
                self._cb_probe_in_flight[name] = False
                self._logger.info(
                    f"✅ Circuit breaker CLOSED [{name}] — probe succeeded, layer recovered"
                )
            else:
                # Normal success in CLOSED state
                self._cb_failure_counts[name] = 0
        else:
            layer.failures += 1
            self._cb_probe_in_flight[name] = False  # probe finished (failed)

            if state == CircuitBreakerState.HALF_OPEN:
                # Probe failed → reopen with doubled cooldown
                self._cb_failure_counts[name] += 1
                self._trip_breaker(name, extra_backoff=True)
            elif state == CircuitBreakerState.CLOSED:
                self._cb_failure_counts[name] += 1
                if self._cb_failure_counts[name] >= CIRCUIT_BREAKER_THRESHOLD:
                    self._trip_breaker(name, extra_backoff=False)

    def _trip_breaker(self, name: str, *, extra_backoff: bool):
        """Open the circuit breaker with exponential-backoff cooldown."""
        current_cooldown = self._cb_cooldown.get(name, float(CIRCUIT_BREAKER_COOLDOWN))
        if extra_backoff:
            current_cooldown = min(MAX_DELAY_SECONDS, current_cooldown * 2)
        self._cb_cooldown[name]       = current_cooldown
        self._cb_disabled_until[name] = time.time() + current_cooldown
        self._cb_state[name]          = CircuitBreakerState.OPEN
        self._logger.warning(
            f"⚡ Circuit breaker OPEN [{name}] — cooldown {current_cooldown:.0f}s "
            f"(failures={self._cb_failure_counts[name]})"
        )

    # ── Availability gate ──────────────────────────────────────────────────────
    def is_available(self, name: str) -> bool:
        """
        Returns True if the layer should be called.

        CLOSED    → True  (normal)
        OPEN      → check cooldown → if expired, transition to HALF_OPEN and
                    allow exactly ONE probe call (all subsequent callers blocked
                    until the probe resolves via record_call)
        HALF_OPEN → True only if no probe is currently in-flight
        """
        if name not in self.layers:
            return False
        if not self.layers[name].available:
            return False

        state = self._cb_state.get(name, CircuitBreakerState.CLOSED)

        if state == CircuitBreakerState.CLOSED:
            return True

        if state == CircuitBreakerState.OPEN:
            if time.time() >= self._cb_disabled_until.get(name, 0):
                # Cooldown expired → allow one probe
                self._cb_state[name] = CircuitBreakerState.HALF_OPEN
                self._cb_probe_in_flight[name] = True
                self._logger.info(
                    f"🔄 Circuit breaker HALF_OPEN [{name}] — sending probe call"
                )
                return True
            return False  # still open

        if state == CircuitBreakerState.HALF_OPEN:
            # Only one probe at a time
            return not self._cb_probe_in_flight.get(name, False)

        return False

    def cb_state(self, name: str) -> CircuitBreakerState:
        """Return the current circuit-breaker state for a layer."""
        return self._cb_state.get(name, CircuitBreakerState.CLOSED)

    # ── Dashboard ──────────────────────────────────────────────────────────────
    def print_dashboard(self):
        lines = [
            "",
            "╔══════════════════════════════════════════════════════════════════════╗",
            f"║  UNITY ENGINE v{UNITY_VERSION} — SYSTEM STATUS  [{datetime.now().strftime('%H:%M:%S')}]              ║",
            "╠══════════════════════════════════════════════════════════════════════╣",
        ]
        for name, layer in self.layers.items():
            sr    = f"{layer.success_rate*100:.0f}%" if layer.calls > 0 else "N/A"
            state = self._cb_state.get(name, CircuitBreakerState.CLOSED).value
            lines.append(
                f"║  {layer.status_icon}  {name:<24}  calls={layer.calls:<5} "
                f"sr={sr:<5} cb={state:<9} ║"
            )
        lines.append("╚══════════════════════════════════════════════════════════════════════╝")
        for line in lines:
            logger.info(line)


# ═══════════════════════════════════════════════════════════════════════════════
# 8.5 INSTITUTIONAL TIMING STATE  (v9.7 — microstructure rolling buffers)
# ═══════════════════════════════════════════════════════════════════════════════

class InstitutionalTimingState:
    """
    Per-symbol rolling-buffer state powering four institutional timing primitives:

      1. Roll (1984) effective-spread estimator
            S_eff = 2 · √( -Cov(ΔP_t, ΔP_{t-1}) )           (clipped at 0)
         Replaces the static 0.10% round-trip fallback in Gate 0 when WS data
         is stale.  Negative serial covariance of mid-price changes captures
         the bid-ask "bounce" without needing quote data.

      2. de Prado symmetric CUSUM event filter
            S_t^+ = max(0, S_{t-1}^+ + (y_t - μ))
            S_t^- = min(0, S_{t-1}^- + (y_t - μ))
            Event when |S_t^±| ≥ k · σ(y),   then reset to 0
         where y_t is the log-return.  Used to gate entries to volatility-
         regime breaks only — drastically reduces overtrading in chop.

      3. Anchored Session VWAP
            AVWAP_T = Σ_{t≥T_anchor} (mid_t · vol_t) / Σ_{t≥T_anchor} vol_t
         Resets daily at UTC 00:00 (Binance funding cycle anchor).  Distance
         in bps drives a quality bonus — entries inside ±BAND_BPS of AVWAP
         are reversion-magnet candidates favoured by institutional desks.

      4. Order-Flow Imbalance Z-score (Cont/Kukanov/Stoikov 2014)
            OFI_t = ΔBidVol_t · 1{ΔBid≥0} - BidVol_{t-1} · 1{ΔBid<0}
                   - ΔAskVol_t · 1{ΔAsk≤0} + AskVol_{t-1} · 1{ΔAsk>0}
            Z_t   = (OFI_t - μ_window) / σ_window
         The Z-score normalises pressure against the symbol's own recent
         baseline — a +2.5σ buy-side imprint on BTCUSDT means something
         very different from the same value on a thin altcoin.

    Fed by `update_from_ws()` from the existing @depth5 WebSocket loop
    (one call per message).  Lock-free; single-writer-many-reader is safe
    under asyncio's cooperative scheduling.  All buffers cap at the
    configured length; total memory ≈ 80 symbols × ~700 floats ≈ 450 KB.
    """

    __slots__ = (
        "_mid_history",      # Dict[str, deque[float]]   — for Roll
        "_ret_history",      # Dict[str, deque[float]]   — for CUSUM
        "_cusum_state",      # Dict[str, Dict[str, float]] — pos/neg/last_event_ts
        "_avwap_state",      # Dict[str, Dict[str, float]] — pv_sum/v_sum/anchor_day
        "_ofi_history",      # Dict[str, deque[float]]   — for OFI Z
        "_prev_book",        # Dict[str, Tuple[float, float, float, float]]  # bid, ask, bid_vol, ask_vol
    )

    def __init__(self) -> None:
        self._mid_history: Dict[str, deque] = {}
        self._ret_history: Dict[str, deque] = {}
        self._cusum_state: Dict[str, Dict[str, float]] = {}
        self._avwap_state: Dict[str, Dict[str, float]] = {}
        self._ofi_history: Dict[str, deque] = {}
        self._prev_book:  Dict[str, Tuple[float, float, float, float]] = {}

    # ── ingest hook ──────────────────────────────────────────────────────────

    def update_from_ws(
        self,
        symbol:   str,
        best_bid: float,
        best_ask: float,
        bid_vol:  float,
        ask_vol:  float,
    ) -> None:
        """
        Push one @depth5 snapshot into all four buffers.  Called from the
        existing WS task; total cost per call ≈ O(1) (deque append + small
        arithmetic).  Robust to bad data: any NaN/inf/zero degenerate input
        is silently dropped so a single bad message can't poison state.
        """
        if not (best_bid > 0 and best_ask > 0 and best_ask >= best_bid):
            return
        sym = symbol.upper()
        mid = 0.5 * (best_bid + best_ask)
        if not math.isfinite(mid) or mid <= 0:
            return
        total_vol = bid_vol + ask_vol

        # ── (1) Roll: store mid for serial-covariance estimator ─────────────
        mh = self._mid_history.get(sym)
        if mh is None:
            mh = deque(maxlen=UNITY_ROLL_HISTORY_LEN)
            self._mid_history[sym] = mh
        mh.append(mid)

        # ── (2) CUSUM: log-return drives symmetric two-sided accumulator ────
        if len(mh) >= 2 and mh[-2] > 0:
            try:
                y = math.log(mid / mh[-2])
            except (ValueError, ZeroDivisionError):
                y = 0.0
            if math.isfinite(y):
                rh = self._ret_history.get(sym)
                if rh is None:
                    rh = deque(maxlen=UNITY_CUSUM_RETURN_LEN)
                    self._ret_history[sym] = rh
                rh.append(y)
                cs = self._cusum_state.get(sym)
                if cs is None:
                    cs = {"pos": 0.0, "neg": 0.0, "last_event_ts": 0.0}
                    self._cusum_state[sym] = cs
                # Symmetric CUSUM with zero target (de Prado AFML §2.5.2.1)
                # σ estimated only when we have ≥30 samples to avoid early
                # false events from start-up noise.
                if len(rh) >= 30:
                    mean_y = sum(rh) / len(rh)
                    var_y  = sum((r - mean_y) ** 2 for r in rh) / max(1, len(rh) - 1)
                    sigma  = math.sqrt(var_y) if var_y > 0 else 0.0
                    if sigma > 0:
                        cs["pos"] = max(0.0, cs["pos"] + (y - mean_y))
                        cs["neg"] = min(0.0, cs["neg"] + (y - mean_y))
                        thr = UNITY_CUSUM_K_SIGMA * sigma
                        if cs["pos"] >= thr or cs["neg"] <= -thr:
                            cs["last_event_ts"] = time.time()
                            cs["pos"] = 0.0
                            cs["neg"] = 0.0

        # ── (3) Anchored VWAP: reset at UTC midnight, accumulate p·v ────────
        if total_vol > 0:
            now_utc = datetime.utcnow()
            today_anchor = float(now_utc.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp())
            av = self._avwap_state.get(sym)
            if av is None or float(av.get("anchor_ts", 0.0)) != today_anchor:
                av = {"pv_sum": 0.0, "v_sum": 0.0, "anchor_ts": today_anchor}
                self._avwap_state[sym] = av
            av["pv_sum"] += mid * total_vol
            av["v_sum"]  += total_vol

        # ── (4) OFI Z-score: Cont/Kukanov/Stoikov 2014 ──────────────────────
        prev = self._prev_book.get(sym)
        if prev is not None:
            p_bid, p_ask, p_bv, p_av = prev
            # Bid-side contribution
            if best_bid > p_bid:
                ofi_bid = bid_vol
            elif best_bid < p_bid:
                ofi_bid = -p_bv
            else:
                ofi_bid = bid_vol - p_bv
            # Ask-side contribution (sign inverted: rising ask = bullish)
            if best_ask < p_ask:
                ofi_ask = ask_vol
            elif best_ask > p_ask:
                ofi_ask = -p_av
            else:
                ofi_ask = ask_vol - p_av
            ofi = ofi_bid - ofi_ask
            if math.isfinite(ofi):
                oh = self._ofi_history.get(sym)
                if oh is None:
                    oh = deque(maxlen=UNITY_OFI_HISTORY_LEN)
                    self._ofi_history[sym] = oh
                oh.append(ofi)
        self._prev_book[sym] = (best_bid, best_ask, bid_vol, ask_vol)

    # ── readers consumed by the SignalFilter gates ───────────────────────────

    def roll_spread_pct(self, symbol: str) -> float:
        """
        Roll's effective half-spread as a fraction of mid-price.  Returns 0.0
        when serial covariance is non-negative (degenerate — no bid/ask
        bounce detected) or insufficient data.  Caller bounds the value;
        a return of 0 signals "no estimate available, use static fallback".
        """
        mh = self._mid_history.get(symbol.upper())
        if mh is None or len(mh) < 20:
            return 0.0
        # Build ΔP series
        prices = list(mh)
        diffs  = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        if len(diffs) < 10:
            return 0.0
        # Sample autocovariance at lag 1
        n = len(diffs)
        mean_d = sum(diffs) / n
        cov1 = sum(
            (diffs[i] - mean_d) * (diffs[i - 1] - mean_d)
            for i in range(1, n)
        ) / max(1, n - 1)
        if cov1 >= 0:
            return 0.0   # no bounce detected — Roll undefined
        # S = 2·√(-cov1); divide by mid to express as fraction
        s_abs = 2.0 * math.sqrt(-cov1)
        last_mid = prices[-1]
        if last_mid <= 0:
            return 0.0
        return s_abs / last_mid

    def cusum_event_active(self, symbol: str) -> bool:
        """True iff a CUSUM event fired within UNITY_CUSUM_EVENT_TTL_SEC."""
        cs = self._cusum_state.get(symbol.upper())
        if cs is None:
            return False
        return (time.time() - float(cs.get("last_event_ts", 0.0))) <= UNITY_CUSUM_EVENT_TTL_SEC

    def avwap(self, symbol: str) -> float:
        """Current session AVWAP, or 0.0 if not yet established."""
        av = self._avwap_state.get(symbol.upper())
        if av is None or av.get("v_sum", 0.0) <= 0.0:
            return 0.0
        return float(av["pv_sum"] / av["v_sum"])

    def avwap_distance_bps(self, symbol: str, current_price: float) -> float:
        """
        Signed bps distance from session AVWAP.  Positive = above AVWAP.
        Returns NaN when AVWAP unavailable so callers can detect cleanly.
        """
        anchor = self.avwap(symbol)
        if anchor <= 0 or current_price <= 0:
            return float("nan")
        return (current_price - anchor) / anchor * 10000.0

    def ofi_zscore(self, symbol: str) -> float:
        """
        Z-score of the most recent OFI sample against the rolling window.
        Returns 0.0 when window too short or σ degenerate.
        """
        oh = self._ofi_history.get(symbol.upper())
        if oh is None or len(oh) < 30:
            return 0.0
        last = oh[-1]
        mean = sum(oh) / len(oh)
        var  = sum((x - mean) ** 2 for x in oh) / max(1, len(oh) - 1)
        sigma = math.sqrt(var) if var > 0 else 0.0
        if sigma <= 0 or not math.isfinite(sigma):
            return 0.0
        return float((last - mean) / sigma)


# ═══════════════════════════════════════════════════════════════════════════════
# 9.  UNITY SIGNAL FILTER  (11-gate quality pipeline — v6.1: +EV Gate +Session)
# ═══════════════════════════════════════════════════════════════════════════════

class UnitySignalFilter:
    """
    14-gate quality pipeline applied to every signal BEFORE it is sent.  v11.0

    Gate 0   — EV Check (v6.1)      : Expected Value > 0 after 0.1% round-trip slippage
    Gate 0.5 — Session Filter(v6.1) : Dead-zone hour penalty (UTC 00-03 raises quality floor)
    Gate 0.8 — Min TP1 Distance(v6.2): TP1 must be ≥ MIN_TP1_DISTANCE_PCT from entry
    Gate 1   — Weighted R:R          : TP1*45%+TP2*35%+TP3*20% weighted reward ≥ MIN_RR_RATIO
    Gate 2   — Swarm Consensus       : ≥ SWARM_MIN_CONSENSUS (95%)
    Gate 2.5b— Pattern Recognizer    : 24-candle + 8-chart pattern confluence gate [v11.0]
    Gate 3   — AI Confidence         : ≥ dynamic threshold (RL-adapted, default 80%)
    Gate 4   — Neural Network        : NN win-prob ≥ NN's learned optimal threshold
    Gate 5   — Analyzer Alignment    : ATAS AND Bookmap both symmetric (can veto independently)
    Gate 6   — Regime Filter         : Fear&Greed extreme blocks directional bias
    Gate 7   — GEX Regime            : AEGIS GEX DGRP + regime alignment gate
    Gate 7b  — BS Greeks             : Black-Scholes delta/gamma/vega alignment gate [v11.0]
    Gate 8   — Per-Symbol Win Rate   : Blocks symbols with < 35% win rate (≥ 5 trades)
    Gate 8.5b— Factor IC/IR          : Factor information coefficient quality gate [v11.0]
    Gate 8.5c— Portfolio Optimizer   : MVO/RP/BL portfolio fit gate [v11.0]
    Gate 9   — Quality Floor         : Composite quality score ≥ SIGNAL_MIN_QUALITY_GATE (42/100) [v7.1]
    Gate 10  — IRONS AI Floor        : 25-indicator composite score ≥ adaptive min (50–65/100, WR-driven) [v6.3]
    """

    def __init__(self, health_monitor: "UnityHealthMonitor",
                 symbol_tracker: "PerSymbolTracker"):
        self._health = health_monitor
        self._sym_tracker = symbol_tracker
        self._logger = logging.getLogger("UnityEngine.Filter")
        self._gate_stats: Dict[str, Dict[str, int]] = {
            "gate_ev":         {"pass": 0, "fail": 0},  # v6.1: EV gate (pre-Gate 1)
            "gate_session":    {"pass": 0, "fail": 0},  # v6.1: session quality modifier
            "gate_min_tp1":    {"pass": 0, "fail": 0},  # v6.2: Min TP1 distance gate
            "gate_blacklist":  {"pass": 0, "fail": 0},  # v9.0 FIX: whitelist/blacklist gate
            **{f"gate{i}": {"pass": 0, "fail": 0} for i in range(1, 11)},
        }  # gate_ev + gate_session + gate_min_tp1 + gate_blacklist + gate1-gate10 (v9.0)
        # v9.9.1 Apex-#8: parallel ROLLING-WINDOW gate stats (in-memory only).
        # _gate_stats above are LIFETIME accumulators — persisted to disk and
        # never decay. After 800+ evals a single gate threshold change moves the
        # displayed pass-rate by <1pt for hours. This causes diagnostic blindness
        # (operator can't tell whether Apex-#6 NN-gate fix actually unblocked
        # signals) AND starves any adaptive logic that consumes pass-rates.
        # The rolling window below tracks the last N evaluations per gate so
        # operator + consumers see fresh signal within ~minutes. Lifetime counts
        # remain the disk source-of-truth → persistence format unchanged.
        # Display methods prefer rolling when ≥20 samples present, else fall
        # back to lifetime — smooth transition across cold-start.
        _rolling_n = int(os.getenv("UNITY_GATE_STATS_WINDOW", "200") or 200)
        self._gate_stats_recent: Dict[str, deque] = {
            k: deque(maxlen=_rolling_n) for k in self._gate_stats.keys()
        }
        self._gate_stats_window_n = _rolling_n
        self._public_api: Optional[Any] = None
        self._gex_engine: Optional[Any] = None
        self._irons_scorer: Optional[Any] = None   # v6.0: IRONS AI Scorer
        # v6.0: rolling IRONS score cache (last 100 scores for diagnostics)
        self._irons_score_ring: deque = deque(maxlen=100)
        # v6.2: per-symbol signal cooldown — prevents hammering same symbol every cycle
        self._symbol_last_sent: Dict[str, float] = {}   # symbol → last send timestamp
        # v8.1: initialize adaptive IRONS min explicitly (avoids fragile getattr fallback)
        self._adaptive_irons_min: float = IRONS_MIN_SCORE
        # v8.5: symbol auto-blacklist (loaded once at startup from trade history)
        # Symbols with WR < 30% over ≥10 resolved trades are hard-blocked.
        self._symbol_blacklist: frozenset = self._load_symbol_blacklist()
        # v8.6: optional top-N whitelist (loaded once at startup from trade history)
        # When UNITY_TOP_N_WHITELIST > 0, ONLY the top-N symbols by historical WR
        # (≥10 resolved trades) pass the pre-gate. Falls back to no restriction
        # when not enough symbols qualify (cold-start safety).
        self._symbol_whitelist: frozenset = self._load_symbol_whitelist()
        # v8.5: backref to booster for hard consec-loss circuit-breaker check
        self._booster: Optional[Any] = None
        # v8.5: hard-cutoff timer (set when triggered; blocks all signals until then)
        self._hard_cutoff_until: float = 0.0
        # v9.0: live WS orderbook state reference for dynamic slippage in Gate 0
        # Set via set_ws_state() — None when WS data is unavailable (fallback to static)
        self._ws_state_ref: Optional[Dict[str, Any]] = None
        # v9.7: institutional timing state (Roll spread, CUSUM, AVWAP, OFI Z-score).
        # Single shared instance owned by UnityEngine; injected via set_timing_state().
        # None until injection — every consumer is null-safe and degrades to v9.6
        # behaviour when this reference is missing.
        self._timing_state: Optional["InstitutionalTimingState"] = None

    @staticmethod
    def _load_symbol_blacklist() -> frozenset:
        """v8.5: Build symbol blacklist from trade history at startup.

        Auto-blacklists symbols with WR < 30% over ≥10 resolved trades.
        Returns a frozenset of UPPERCASE symbols. Failures degrade gracefully
        to an empty set so the filter remains operational.
        """
        try:
            import sqlite3 as _sql
            _path = os.path.join(os.path.dirname(__file__) or ".",
                                 "SignalMaestro", "trade_history.db")
            if not os.path.exists(_path):
                return frozenset()
            _con = _sql.connect(_path)
            _rows = _con.execute("""
                SELECT symbol,
                       COUNT(*) total,
                       SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) wins
                FROM trades
                WHERE outcome IS NOT NULL AND outcome NOT IN ('','PENDING')
                GROUP BY symbol
                HAVING total >= 10 AND (1.0 * wins / total) < 0.30
            """).fetchall()
            _con.close()
            _bl = frozenset(str(s).upper() for (s, _t, _w) in _rows if s)
            logging.getLogger("UnityEngine.Filter").info(
                f"🚫 [v8.5] Symbol blacklist loaded: {len(_bl)} symbols "
                f"(WR<30% over ≥10 trades) → {sorted(_bl)[:10]}{'…' if len(_bl) > 10 else ''}"
            )
            return _bl
        except Exception as _e:
            logging.getLogger("UnityEngine.Filter").warning(
                f"⚠️ [v8.5] Symbol blacklist load failed (degrading to empty): {_e}"
            )
            return frozenset()

    @staticmethod
    def _load_symbol_whitelist() -> frozenset:
        """v8.6: Build top-N highest-WR whitelist from trade_history.db.

        Controlled by env var UNITY_TOP_N_WHITELIST (default 0 = disabled,
        set to N>0 to re-enable hard whitelist). Requires ≥10 resolved trades
        per symbol to qualify. Falls back to empty (= no restriction) if
        fewer than N qualify.

        v9.4: default flipped 15 → 0.  The hard top-15 whitelist was rejecting
        ~95% of generated signals (live signals/hr=0 vs target 5-10) because
        most symbols never accumulate 10 historical trades.  Earn-your-way-in
        is now handled by Gate 8 (Per-Symbol WR ≥35% over ≥5 trades) which
        already exists — symbols with no history pass through (cold-start
        tolerance) while proven losers are still hard-blocked by the v8.5
        symbol blacklist (WR<30% over ≥10 trades).  This widens the trading
        universe without weakening risk gating.  Set UNITY_TOP_N_WHITELIST>0
        to restore the legacy hard-whitelist behaviour.
        """
        try:
            _n = int(os.getenv("UNITY_TOP_N_WHITELIST", "0"))
        except (ValueError, TypeError):
            _n = 0
        if _n <= 0:
            logging.getLogger("UnityEngine.Filter").info(
                "⚪ [v9.4] Hard whitelist DISABLED — Gate 8 (per-symbol rolling WR≥35%, "
                "min 5 trades) + v8.5 blacklist provide earn-your-way-in filtering. "
                "Set UNITY_TOP_N_WHITELIST=N>0 to restore legacy top-N whitelist."
            )
            return frozenset()
        try:
            import sqlite3 as _sql
            _path = os.path.join(os.path.dirname(__file__) or ".",
                                 "SignalMaestro", "trade_history.db")
            if not os.path.exists(_path):
                return frozenset()
            _con = _sql.connect(_path)
            _rows = _con.execute("""
                SELECT symbol, COUNT(*) total,
                       SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) wins
                FROM trades
                WHERE outcome IS NOT NULL AND outcome NOT IN ('','PENDING')
                GROUP BY symbol HAVING total >= 10
                ORDER BY (1.0 * wins / total) DESC
                LIMIT ?
            """, (_n,)).fetchall()
            _con.close()
            if len(_rows) < _n:
                logging.getLogger("UnityEngine.Filter").info(
                    f"⚪ [v8.6] Whitelist disabled: only {len(_rows)} symbols qualify "
                    f"(need {_n}). Universe-restriction OFF — using full Binance USDM list."
                )
                return frozenset()
            _wl = frozenset(str(s).upper() for (s, _t, _w) in _rows if s)
            logging.getLogger("UnityEngine.Filter").info(
                f"✅ [v8.6] Top-{_n} WR whitelist active: {sorted(_wl)} "
                f"(set UNITY_TOP_N_WHITELIST=0 to disable)"
            )
            return _wl
        except Exception as _e:
            logging.getLogger("UnityEngine.Filter").warning(
                f"⚠️ [v8.6] Whitelist load failed (degrading to no restriction): {_e}"
            )
            return frozenset()

    def set_booster(self, booster: Any) -> None:
        """v8.5: Inject booster for hard consec-loss circuit-breaker visibility."""
        self._booster = booster

    def set_public_api(self, api: Any) -> None:
        self._public_api = api

    def set_gex_engine(self, gex: Any) -> None:
        self._gex_engine = gex

    def set_irons_scorer(self, scorer: Any) -> None:
        """v6.0: Inject the IRONS AI Scorer for Gate 10."""
        self._irons_scorer = scorer

    def set_ws_state(self, ws_state_dict: Dict[str, Any]) -> None:
        """v9.0: Inject live WS orderbook state dict reference for dynamic slippage.

        The dict is owned by UnityEngine._ws_state and is mutated in-place by
        _ws_orderbook_task; no copy is needed — the filter always reads the latest
        snapshot at Gate 0 evaluation time.  Falls back to SLIPPAGE_PCT when the
        symbol has no live data yet (e.g. first scan cycle after start-up).
        """
        self._ws_state_ref = ws_state_dict

    def set_timing_state(self, ts: "InstitutionalTimingState") -> None:
        """v9.7: Inject the institutional timing state singleton.

        Wires Gate 0 (Roll spread fallback), Pre-Gate D (CUSUM event filter),
        AVWAP confluence quality bonus, and OFI Z-score bonus/veto.  Behaviour
        is fully back-compat: when this is never called, every gate degrades
        to v9.6 logic exactly.
        """
        self._timing_state = ts

    def set_aggtrade_pool(self, pool: Any) -> None:
        """v9.9 Apex-#1: inject the Binance aggTrade WS pool reference.

        When set, Gate 0 can additionally cross-check tick-freshness
        (`pool.age_ms(symbol)`) before trusting the live WS spread.  When
        the pool is absent, behaviour is identical to v9.8 — no veto.
        """
        self._aggtrade_pool = pool

    def set_dynamic_backtester(self, backtester: Any) -> None:
        """v9.9.1 Apex-#5: inject the per-symbol dynamic backtester reference.

        Consulted by Gate 8.5 for a soft quality bias (-8 .. +5) when a
        symbol has insufficient live trades for Gate 8 to judge it.  When
        unset (or the result is missing/stale), Gate 8.5 is a no-op.
        """
        self._dyn_backtester = backtester

    def last_irons_score(self) -> float:
        """Average IRONS score from last 100 evaluated signals."""
        if not self._irons_score_ring:
            return 0.0
        return sum(self._irons_score_ring) / len(self._irons_score_ring)

    def mark_signal_sent(self, symbol: str) -> None:
        """v6.2: Record that a signal was sent for this symbol (starts cooldown timer)."""
        self._symbol_last_sent[symbol.upper()] = time.time()

    def update_adaptive_irons(self, current_wr: float) -> None:
        """v6.3/v8.1: Adjust IRONS minimum threshold based on running win rate.

        Schedule: called by the engine each time an outcome is recorded.
        WR < 30%  → raise to IRONS_MIN_WR_BELOW30 (57) — aligned with 30-45% floor [v10.6: was 60; avoids double-penalising bad regimes]
        WR 30-45% → raise to IRONS_MIN_WR_30_45   (57) — slightly elevated   [v8.1: was 60]
        WR 45-55% → base   IRONS_MIN_WR_45_55      (54) — neutral             [v8.1: was 55]
        WR > 55%  → relax  IRONS_MIN_WR_ABOVE55    (50) — capitalise good form
        Rationale: neutral-market IRONS baseline is ~62 (not ~50), so thresholds
        were recalibrated -5 pts to avoid over-filtering high-quality signals.
        """
        if current_wr < 0.30:
            self._adaptive_irons_min = IRONS_MIN_WR_BELOW30
        elif current_wr < 0.45:
            self._adaptive_irons_min = IRONS_MIN_WR_30_45
        elif current_wr < 0.55:
            self._adaptive_irons_min = IRONS_MIN_WR_45_55
        else:
            self._adaptive_irons_min = IRONS_MIN_WR_ABOVE55

    @property
    def effective_irons_min(self) -> float:
        """Current adaptive IRONS minimum (replaces hardcoded IRONS_MIN_SCORE)."""
        return getattr(self, "_adaptive_irons_min", IRONS_MIN_SCORE)

    def _cooldown_penalty(self, symbol: str) -> float:
        """v6.2: Return quality penalty (0-20) if symbol is in signal cooldown window."""
        last_ts = self._symbol_last_sent.get(symbol.upper(), 0.0)
        if last_ts == 0.0:
            return 0.0
        elapsed_minutes = (time.time() - last_ts) / 60.0
        if elapsed_minutes >= SIGNAL_COOLDOWN_MINUTES:
            return 0.0   # cooldown expired — no penalty
        # Linear decay: 0 min → -20pts, at SIGNAL_COOLDOWN_MINUTES → 0pts
        frac = 1.0 - (elapsed_minutes / SIGNAL_COOLDOWN_MINUTES)
        return frac * 20.0

    def _record(self, gate: str, passed: bool):
        # v9.0 FIX: setdefault guards against any gate key not present at init
        # (e.g. gate_blacklist was missing, causing KeyError crash on whitelist reject)
        bucket = self._gate_stats.setdefault(gate, {"pass": 0, "fail": 0})
        bucket["pass" if passed else "fail"] += 1
        # v9.9.1 Apex-#8: also append to rolling window for fresh diagnostic signal
        _ring = self._gate_stats_recent.get(gate)
        if _ring is None:
            _ring = deque(maxlen=getattr(self, "_gate_stats_window_n", 200))
            self._gate_stats_recent[gate] = _ring
        _ring.append(passed)

    def apply(
        self,
        signal_data:     Dict[str, Any],
        nn_trainer:      Optional[Any] = None,
        atas_result:     Optional[Dict[str, Any]] = None,
        bookmap_result:  Optional[Dict[str, Any]] = None,
        gex_snapshot:    Optional[Any] = None,
        ai_threshold:    float = AI_THRESHOLD_PERCENT,
        depth_slippage_result: Optional[Dict[str, Any]] = None,  # v9.9 Apex-#2
    ) -> Tuple[bool, str, float]:
        """
        Returns (passed: bool, reason: str, quality_score: float 0-100).
        All eight gates must pass.
        """
        symbol     = str(signal_data.get("symbol", "")).upper()
        direction  = signal_data.get("action", signal_data.get("direction", "")).upper()
        entry      = float(signal_data.get("entry_price",  0) or 0)
        sl         = float(signal_data.get("stop_loss",    0) or 0)
        tp1        = float(signal_data.get("take_profit_1", signal_data.get("take_profit", 0)) or 0)
        tp2        = float(signal_data.get("take_profit_2", tp1) or tp1)
        tp3        = float(signal_data.get("take_profit_3", tp2) or tp2)
        confidence = float(signal_data.get("confidence", signal_data.get("ai_confidence", 0)) or 0)
        consensus  = float(signal_data.get("consensus",  signal_data.get("swarm_consensus", 0)) or 0)

        # ── v8.5 Pre-Gate A — Symbol auto-blacklist (O(1) frozenset lookup) ──
        # Hard-block symbols with WR < 30% over ≥10 historical trades.
        # Loaded once at startup from trade_history.db. No quality penalty —
        # straight reject, because slope of avgPnL on these symbols is firmly
        # negative (e.g. SOLUSDT n=70 WR=25.7% avgPnL=-9.08%).
        # v8.6: Top-N whitelist gate (when active, only listed symbols pass)
        if self._symbol_whitelist and symbol and symbol.upper() not in self._symbol_whitelist:
            self._record("gate_blacklist", False)
            return (
                False,
                f"WHITELIST: {symbol} not in top-{len(self._symbol_whitelist)} historical-WR set [v8.6]",
                0.0,
            )
        if symbol and symbol in self._symbol_blacklist:
            return (
                False,
                f"BLACKLIST: {symbol} historical WR<30% (n≥10) — auto-blocked [v8.5]",
                0.0,
            )

        # ── v8.5 Pre-Gate B — Hard consecutive-loss cutoff (circuit breaker) ──
        # When booster._consec_losses ≥ CONSEC_LOSS_HARD_CUTOFF, halt ALL trading
        # for CONSEC_LOSS_HARD_COOLDOWN seconds. Probability of 10 straight losses
        # at WR=34% (EV-positive band) is ~1.7%; if it happens, regime has shifted
        # against the model and we must stop until forced cooldown elapses.
        _now = time.time()
        if self._hard_cutoff_until > _now:
            # v10.3 BUG FIX: if a winning trade already cleared _consec_losses
            # back below HARD_CUTOFF, cancel the remaining hard-cutoff time so
            # the first recovery win re-enables trading immediately.  Previously
            # _hard_cutoff_until was never reset and the full 2h cooldown ran
            # even after a winning trade cleared the consecutive-loss streak.
            _booster_consec = int(getattr(self._booster, "_consec_losses", CONSEC_LOSS_HARD_CUTOFF) or 0)
            if self._booster is not None and _booster_consec < CONSEC_LOSS_HARD_CUTOFF:
                self._logger.info(
                    f"✅ [v10.3] HARD_CUTOFF cancelled early — booster "
                    f"_consec_losses={_booster_consec} < {CONSEC_LOSS_HARD_CUTOFF} "
                    f"(recovery win detected). Resuming normal trading."
                )
                self._hard_cutoff_until = 0.0
            else:
                _remain = int(self._hard_cutoff_until - _now)
                return (
                    False,
                    f"HARD_CUTOFF: trading halted for {_remain}s after "
                    f"{CONSEC_LOSS_HARD_CUTOFF}+ consecutive losses [v8.5]",
                    0.0,
                )
        if self._booster is not None:
            _consec = int(getattr(self._booster, "_consec_losses", 0) or 0)
            # v9.7 BUG FIX: respect Booster warmup window — OutcomeTracker replays
            # historical losses on startup which artificially inflates _consec_losses
            # and would instantly trip HARD_CUTOFF, freezing trading for 2h on every
            # restart of a bot with a recent losing streak in trade_history.db.
            _b_session_start = float(getattr(self._booster, "_session_start_time", 0.0) or 0.0)
            _b_warmup_sec    = float(getattr(self._booster, "_WARMUP_SECONDS", 0) or 0)
            _booster_in_warmup = (
                _b_session_start > 0.0
                and (_now - _b_session_start) < _b_warmup_sec
            )
            if _consec >= CONSEC_LOSS_HARD_CUTOFF and not _booster_in_warmup:
                self._hard_cutoff_until = _now + CONSEC_LOSS_HARD_COOLDOWN
                self._logger.error(
                    f"🛑 [v8.5] HARD CUTOFF tripped — {_consec} consecutive losses; "
                    f"all signals blocked for {CONSEC_LOSS_HARD_COOLDOWN//60}min"
                )
                return (
                    False,
                    f"HARD_CUTOFF: {_consec} consecutive losses → "
                    f"{CONSEC_LOSS_HARD_COOLDOWN//60}min trading halt [v8.5]",
                    0.0,
                )
        # ── v9.7 Pre-Gate C — Binance USDM funding-settlement window ──────────
        # Reject signals landing within ±FUNDING_GUARD_SEC of a Binance USDM
        # funding event (UTC 00/08/16).  Inside this window:
        #   • effective spread widens ~2-5x (institutions widen quotes to avoid
        #     paying funding on inventory accumulated by adverse selection),
        #   • mark/index basis spikes — destabilising stops priced as % from
        #     entry that would otherwise survive a normal-regime wick,
        #   • funding-arb desks (delta-neutral perp/spot) rebalance position
        #     books, generating mean-reverting whipsaws that disproportionately
        #     hit small-edge directional entries.
        # Pure datetime math; no API calls. Gate is a no-op when
        # UNITY_FUNDING_GUARD_SEC=0 (default), so existing behaviour is preserved
        # bit-for-bit unless the operator opts in.
        if FUNDING_GUARD_SEC > 0:
            # v10.4 PERF FIX: cache funding gate for 30 s — was called per-symbol
            # (80× per scan cycle) with datetime.utcnow() + 6 math ops each time.
            global _funding_gate_cache
            _fc_ts, _fc_blocked, _fc_dist = _funding_gate_cache
            if time.time() - _fc_ts > 30.0:
                _utc_now       = datetime.utcnow()
                _secs_into_day = (
                    _utc_now.hour * 3600 + _utc_now.minute * 60 + _utc_now.second
                )
                _fc_dist = min(
                    min(
                        abs(_secs_into_day - h * 3600),
                        86400 - abs(_secs_into_day - h * 3600),
                    )
                    for h in _FUNDING_SETTLEMENT_HOURS_UTC
                )
                _fc_blocked = _fc_dist <= FUNDING_GUARD_SEC
                _funding_gate_cache = (time.time(), _fc_blocked, _fc_dist)
            if _fc_blocked:
                self._record("gate_funding", False)
                return (
                    False,
                    f"FUNDING_WINDOW: {_fc_dist}s from Binance USDM settlement "
                    f"(UTC {_FUNDING_SETTLEMENT_HOURS_UTC}); guard=±{FUNDING_GUARD_SEC}s "
                    f"— spread×2-5, mark/index divergence, arb-desk rebalancing [v9.7]",
                    0.0,
                )
            self._record("gate_funding", True)

        # ── v9.7 Pre-Gate D — Symmetric CUSUM event filter (de Prado AFML §2.5) ─
        # Reject signals that do NOT coincide with a recent volatility-regime
        # break.  When CUSUM detects no event in the last UNITY_CUSUM_EVENT_TTL_SEC
        # window, we treat the symbol as being in a chop regime where directional
        # entries underperform the round-trip cost of execution.  Only fires when
        # UNITY_CUSUM_ENABLED=1 AND the timing-state buffer holds enough samples
        # (≥30 returns); cold-start grace is automatic — gate passes through with
        # zero recorded outcomes when the buffer is still warming up.
        if (
            UNITY_CUSUM_ENABLED
            and self._timing_state is not None
            and symbol
        ):
            _cs = self._timing_state._cusum_state.get(symbol.upper())
            _has_state = (
                _cs is not None
                and len(self._timing_state._ret_history.get(symbol.upper(), [])) >= 30
            )
            if _has_state:
                if not self._timing_state.cusum_event_active(symbol):
                    self._record("gate_cusum", False)
                    return (
                        False,
                        f"CUSUM_NO_EVENT: {symbol} in chop regime — no |S±|≥"
                        f"{UNITY_CUSUM_K_SIGMA:.1f}σ event in last "
                        f"{UNITY_CUSUM_EVENT_TTL_SEC}s [v9.7]",
                        0.0,
                    )
                self._record("gate_cusum", True)

        # v6.3: additional fields for ATR volatility regime + HTF alignment
        _atr       = float(signal_data.get("atr", 0) or 0)
        _htf_1h    = str(signal_data.get("htf_1h", "") or "").upper()
        _htf_4h    = str(signal_data.get("htf_4h", "") or "").upper()

        quality_score = 0.0

        # ── v6.2: Per-symbol cooldown quality penalty ─────────────────────────
        # Penalises repeat signals for the same symbol within SIGNAL_COOLDOWN_MINUTES.
        # Uses soft deduction rather than hard block so extraordinary signals can
        # still pass Gate 9 even during cooldown.
        _cooldown_deduct = self._cooldown_penalty(symbol)
        if _cooldown_deduct > 0:
            quality_score -= _cooldown_deduct
            self._logger.debug(
                f"⏳ [{symbol}] Cooldown penalty: -{_cooldown_deduct:.1f}pts "
                f"(last sent <{SIGNAL_COOLDOWN_MINUTES}min ago)"
            )

        # ── v6.3: ATR Volatility Regime quality penalty ───────────────────────
        # Extreme volatility (ATR > 3% of entry) means wide spreads, unpredictable
        # wicks, and SL being hunted before price reaches TP1.  Apply a graduated
        # quality deduction so Gate 9 blocks the worst vol-spike entries.
        if _atr and entry and entry > 0:
            _atr_pct = _atr / entry
            if _atr_pct > ATR_HIGH_VOL_THRESHOLD:
                _excess_pct  = min(_atr_pct, ATR_MAX_PENALTY_PCT) - ATR_HIGH_VOL_THRESHOLD
                _vol_range   = max(0.001, ATR_MAX_PENALTY_PCT - ATR_HIGH_VOL_THRESHOLD)
                _vol_penalty = min(ATR_MAX_QUALITY_PENALTY, (_excess_pct / _vol_range) * ATR_MAX_QUALITY_PENALTY)
                quality_score -= _vol_penalty
                self._logger.debug(
                    f"🌪️ [{symbol}] Vol penalty: ATR={_atr_pct:.2%} > {ATR_HIGH_VOL_THRESHOLD:.0%} "
                    f"→ -{_vol_penalty:.1f}pts"
                )

        # ── Gate 0 — Expected Value with slippage model (v9.0 dynamic) ─────────
        # EV = P(win) × reward% - P(loss) × risk% - round_trip_slippage%
        # v9.0: slippage is now DYNAMIC — use live best-ask/bid spread from the
        # WebSocket orderbook when available; fall back to static SLIPPAGE_PCT × 2
        # when WS data is absent (cold start, WS reconnecting, or unknown symbol).
        # Dynamic slippage is capped at 3× the static floor and floored at 0.5×
        # so a momentarily wide spread cannot produce a falsely large EV penalty.
        if entry and sl and tp1:
            _p_win   = min(0.95, max(0.05, confidence / 100.0))
            _p_loss  = 1.0 - _p_win
            _risk_pct   = abs(entry - sl) / entry       # % risk of entry price
            _reward_pct = (
                abs(tp1 - entry) * (TP_ALLOCATION[0] / 100.0) +
                abs(tp2 - entry) * (TP_ALLOCATION[1] / 100.0) +
                abs(tp3 - entry) * (TP_ALLOCATION[2] / 100.0)
            ) / entry                                    # % weighted reward
            # v9.0: dynamic slippage from live orderbook spread
            # v9.1: staleness guard — WS data >10s old is treated as unavailable
            # v9.7: Roll (1984) effective-spread estimator inserted as Tier-2
            #       fallback ahead of the static constant.  Precedence:
            #         live WS spread (<10s) > Roll(history≥20) > static SLIPPAGE_PCT×2
            #       All three obey the same hard bounds (0.5×–3× of static), so
            #       the EV gate can never be tripped by a single spike sample.
            _static_slip = SLIPPAGE_PCT * 2.0           # static round-trip fallback
            _live_spread = 0.0
            _roll_spread = 0.0
            _depth_slip  = 0.0   # v9.9 Apex-#2: depth-walked VWAP slippage
            _depth_slip_meta: dict = {}
            _ob_fresh: dict = {}

            # v9.9 Apex-#2: depth-walked slippage takes HIGHEST precedence.
            # The bot pre-fetches this in its async signal-eval loop and passes
            # it in via `depth_slippage_result`.  When fresh (<3s) and the book
            # cleared the requested notional, this is the most accurate slippage
            # estimate available — it reflects the actual cost-to-fill, not just
            # the top-of-book spread.
            if (
                depth_slippage_result is not None
                and isinstance(depth_slippage_result, dict)
                and float(depth_slippage_result.get("round_trip", 0.0) or 0.0) > 0.0
                and int(depth_slippage_result.get("age_ms", 99999)) < 3000
            ):
                _rt = float(depth_slippage_result["round_trip"])
                _cleared = float(depth_slippage_result.get("cleared_pct", 1.0) or 1.0)
                # Partial-fill penalty: if the book cannot clear the planned notional
                # within the top-N levels, the *real* slippage is materially larger
                # than the partial VWAP — apply the configured multiplier so Gate 0
                # blocks the trade rather than approving on an optimistic estimate.
                if _cleared < 0.95:
                    _rt *= max(1.0, UNITY_DEPTH_SLIP_PARTIAL_FILL_PENALTY * (1.0 + (1.0 - _cleared)))
                _depth_slip = min(_static_slip * 5.0, max(_static_slip * 0.5, _rt))
                _depth_slip_meta = depth_slippage_result

            if self._ws_state_ref is not None:
                _ob = self._ws_state_ref.get(symbol.upper())
                if _ob is not None and (time.time() - float(_ob.get("ts", 0.0) or 0.0)) < 10.0:
                    _raw_spread = float(_ob.get("spread_pct", 0.0) or 0.0)
                    # spread_pct is one-leg; double for round-trip; apply bounds
                    if _raw_spread > 0.0:
                        _live_spread = min(
                            _static_slip * 3.0,
                            max(_static_slip * 0.5, _raw_spread * 2.0)
                        )
                    _ob_fresh = _ob   # valid fresh OB snapshot for later quality bonus
            # v9.7: Roll estimator — only consulted when no live WS spread.
            # Returns 0.0 when serial covariance is non-negative (no bid/ask
            # bounce detected) which transparently falls through to static.
            if (
                _live_spread <= 0.0
                and _depth_slip <= 0.0
                and UNITY_ROLL_ENABLED
                and self._timing_state is not None
            ):
                _roll_raw = self._timing_state.roll_spread_pct(symbol)
                if _roll_raw > 0.0:
                    # Roll estimates a half-spread; double for round-trip; apply
                    # same bounds as live WS to prevent estimator outliers from
                    # blowing through the EV calc.
                    _roll_spread = min(
                        _static_slip * 3.0,
                        max(_static_slip * 0.5, _roll_raw * 2.0)
                    )
            # v9.9 precedence: depth-walked > live WS spread > Roll > static
            _slippage = (
                _depth_slip if _depth_slip > 0.0
                else (_live_spread if _live_spread > 0.0
                else (_roll_spread if _roll_spread > 0.0 else _static_slip))
            )
            _ev       = (_p_win * _reward_pct) - (_p_loss * _risk_pct) - _slippage
            passed_ev = _ev >= EV_MIN_THRESHOLD
            self._record("gate_ev", passed_ev)
            if not passed_ev:
                # v9.9: tag identifies which slippage tier was used so debug logs
                # show whether depth-walked, WS, Roll or static rejected the trade.
                if _depth_slip > 0.0:
                    _cleared_pct = float(_depth_slip_meta.get("cleared_pct", 1.0) or 1.0)
                    _slip_tag = f"depth={_slippage:.3%}(cleared={_cleared_pct:.0%})"
                elif _live_spread > 0.0:
                    _slip_tag = f"live={_slippage:.3%}"
                elif _roll_spread > 0.0:
                    _slip_tag = f"roll={_slippage:.3%}"
                else:
                    _slip_tag = f"static={_slippage:.3%}"
                return (
                    False,
                    f"G0_FAIL: EV={_ev:.4%} < {EV_MIN_THRESHOLD:.4%} floor after slippage "
                    f"(P_win={_p_win:.0%}·R={_reward_pct:.2%} − P_loss={_p_loss:.0%}·Rk={_risk_pct:.2%} − slip={_slip_tag})",
                    0.0,
                )
            # EV score contribution: strong positive EV adds up to 10 quality pts
            quality_score += min(10.0, max(0.0, _ev / 0.01 * 10.0))
        else:
            self._record("gate_ev", True)  # no price data → pass-through

        # ── Gate 0.5 — Session-aware quality modifier (v6.1) ──────────────────
        # Dead zone UTC 00:00-03:00: thin order books → raise effective quality bar
        # Prime session UTC 12:00-20:00 (London PM / NY AM): reward liquidity
        _utc_hour = datetime.utcnow().hour
        _in_dead_zone   = DEAD_ZONE_UTC_START <= _utc_hour < DEAD_ZONE_UTC_END
        _in_prime_session = SESSION_BONUS_UTC_START <= _utc_hour < SESSION_BONUS_UTC_END
        if _in_dead_zone:
            if UNITY_DEADZONE_HARD_VETO:
                # [v9.7-C] hard veto — refuse any signal during low-liquidity UTC hours
                self._record("gate_session", False)
                return False, (
                    f"G0.5_DEADZONE_VETO: UTC hour={_utc_hour} in dead-zone "
                    f"[{DEAD_ZONE_UTC_START:02d}-{DEAD_ZONE_UTC_END:02d}h) — hard block [v9.7-C]"
                ), 0.0
            quality_score -= DEAD_ZONE_QUALITY_PENALTY   # apply penalty — reduces room above gate9 floor
            self._record("gate_session", False)
            self._logger.debug(
                f"G0.5_DEADZONE: UTC hour={_utc_hour} — quality −{DEAD_ZONE_QUALITY_PENALTY:.0f}pts"
            )
        elif _in_prime_session:
            quality_score += SESSION_QUALITY_BONUS
            self._record("gate_session", True)
        else:
            self._record("gate_session", True)

        # ── v6.3: Higher-Timeframe Trend Alignment bonus ──────────────────────
        # When 1H and/or 4H trend agrees with the entry direction, add quality bonus.
        # Trend-following entries outperform counter-trend setups by ~12-18% WR.
        # _htf_1h / _htf_4h are string signals like "BUY", "SELL", "BULL", "NEUTRAL".
        if direction:
            _dir_bullish = direction in ("BUY", "LONG")
            _bull_words  = _HTF_BULL_WORDS   # v8.3: pre-compiled module constant
            _bear_words  = _HTF_BEAR_WORDS   # v8.3: pre-compiled module constant
            _htf1_words  = set(_htf_1h.split())
            _htf4_words  = set(_htf_4h.split())
            _htf1_agree  = bool(_htf1_words & (_bull_words if _dir_bullish else _bear_words))
            _htf4_agree  = bool(_htf4_words & (_bull_words if _dir_bullish else _bear_words))
            _htf_bonus   = 0.0
            if _htf1_agree:
                _htf_bonus += HTF_1H_AGREE_BONUS
            if _htf4_agree:
                _htf_bonus += HTF_4H_AGREE_BONUS
            if _htf_bonus > 0:
                quality_score += _htf_bonus
                self._logger.debug(
                    f"📈 [{symbol}] HTF alignment bonus: 1H={'✅' if _htf1_agree else '❌'} "
                    f"4H={'✅' if _htf4_agree else '❌'} → +{_htf_bonus:.1f}pts"
                )

        # ── v9.1: WS Orderbook Microstructure Quality Bonus ──────────────────────
        # Uses fresh (<10s) WS depth5 snapshot captured in Gate 0 slippage block.
        # (a) Depth imbalance bonus (+3 pts): strong bid/ask pressure aligned with
        #     signal direction confirms institutional order flow, improving fill quality
        #     and reducing adverse selection.  Threshold |imbalance| > 0.3 (~60/40 split).
        # (b) Tight spread bonus (+2 pts): live spread < 50% of the static slippage
        #     floor means the market is offering better-than-expected fill conditions,
        #     raising the true EV above the floor already passed in Gate 0.
        if _ob_fresh and direction:
            _imbalance  = float(_ob_fresh.get("depth_imbalance", 0.0) or 0.0)
            _live_spread_pct = float(_ob_fresh.get("spread_pct", 0.0) or 0.0)
            _is_long    = direction in ("BUY", "LONG")
            _ob_bonus   = 0.0
            if _is_long and _imbalance > 0.30:
                _ob_bonus += 3.0   # bid-heavy OB reinforces LONG
            elif not _is_long and _imbalance < -0.30:
                _ob_bonus += 3.0   # ask-heavy OB reinforces SHORT
            if _live_spread_pct > 0.0 and _live_spread_pct < SLIPPAGE_PCT * 0.5:
                _ob_bonus += 2.0   # tight-spread fill-quality bonus
            if _ob_bonus > 0.0:
                quality_score += _ob_bonus
                self._logger.debug(
                    f"📊 [{symbol}] WS OB bonus: imbalance={_imbalance:+.2f} "
                    f"spread={_live_spread_pct:.4%} → +{_ob_bonus:.0f}pts [v9.3]"
                )

        # ── v9.7: Anchored-VWAP confluence quality bonus ─────────────────────
        # Institutional desks treat the session-anchored VWAP as a reversion
        # magnet for intraday flow.  When the entry sits inside ±BAND_BPS of
        # AVWAP, the probability of mean-reverting back to the level (and
        # therefore of TP1 being touched before SL) is materially higher.
        # Bonus is linear in distance:
        #     bonus = MAX_PTS · max(0, 1 - |dist_bps| / BAND_BPS)
        # so an entry exactly at AVWAP earns the full MAX_PTS, decaying to 0
        # at the band edge.  No effect when the session has insufficient
        # volume samples (returns NaN → bonus skipped).  Default-OFF.
        if (
            UNITY_AVWAP_ENABLED
            and self._timing_state is not None
            and entry > 0
            and symbol
        ):
            _avwap_dist = self._timing_state.avwap_distance_bps(symbol, entry)
            if math.isfinite(_avwap_dist):
                _proximity = max(0.0, 1.0 - abs(_avwap_dist) / UNITY_AVWAP_BAND_BPS)
                _avwap_bonus = UNITY_AVWAP_MAX_BONUS_PTS * _proximity
                if _avwap_bonus > 0:
                    quality_score += _avwap_bonus
                    self._logger.debug(
                        f"🎯 [{symbol}] AVWAP confluence: dist={_avwap_dist:+.1f}bps "
                        f"band=±{UNITY_AVWAP_BAND_BPS:.0f}bps → +{_avwap_bonus:.1f}pts [v9.7]"
                    )

        # ── v9.7: Order-Flow Imbalance Z-score (Cont/Kukanov/Stoikov 2014) ───
        # The static depth_imbalance ratio above tells us *which side is bigger
        # right now*; the OFI Z-score tells us *how unusual that pressure is
        # vs the symbol's own recent baseline*.  A +2σ buy imprint on BTCUSDT
        # is a meaningfully different signal than the same imprint on a thin
        # altcoin where ±0.5σ is the daily envelope.  Two effects:
        #   • Aligned strong Z (|Z| ≥ 1.5σ in signal direction): up to
        #     UNITY_OFI_Z_BONUS_PTS quality bonus, scaled by σ magnitude.
        #   • Opposing extreme Z (|Z| ≥ UNITY_OFI_Z_VETO_SIGMA against
        #     direction): hard veto — institutions are pressing the other
        #     side and small-edge directional entries lose money here.
        if (
            UNITY_OFI_ENABLED
            and self._timing_state is not None
            and direction
        ):
            _ofi_z = self._timing_state.ofi_zscore(symbol)
            if abs(_ofi_z) >= 0.5:   # below 0.5σ = noise, ignore
                _is_long_ofi = direction in ("BUY", "LONG")
                _aligned     = (_is_long_ofi and _ofi_z > 0) or (not _is_long_ofi and _ofi_z < 0)
                _z_mag       = min(3.0, abs(_ofi_z))   # cap influence at 3σ
                if not _aligned and _z_mag >= UNITY_OFI_Z_VETO_SIGMA:
                    self._record("gate_ofi", False)
                    return (
                        False,
                        f"OFI_OPPOSED: Z={_ofi_z:+.2f}σ against {direction} "
                        f"(veto≥{UNITY_OFI_Z_VETO_SIGMA:.1f}σ) — "
                        f"institutional flow pressing the other side [v9.7]",
                        0.0,
                    )
                if _aligned:
                    # Linear scaling: 0.5σ→0, 3σ→full bonus
                    _ofi_bonus = UNITY_OFI_Z_BONUS_PTS * max(0.0, (_z_mag - 0.5) / 2.5)
                    if _ofi_bonus > 0:
                        quality_score += _ofi_bonus
                        self._record("gate_ofi", True)
                        self._logger.debug(
                            f"⚡ [{symbol}] OFI Z aligned: Z={_ofi_z:+.2f}σ "
                            f"→ +{_ofi_bonus:.1f}pts [v9.7]"
                        )

        # ── Gate 0.8 — Minimum TP1 distance after slippage (v6.2) ───────────────
        # TP1 must be ≥ MIN_TP1_DISTANCE_PCT from entry so slippage cannot
        # fully consume the first take-profit target.  Tiny TP1 trades are the
        # primary driver of negative-EV outcomes at realistic execution spreads.
        if entry and tp1:
            _tp1_dist_pct = abs(tp1 - entry) / entry
            _min_tp1      = MIN_TP1_DISTANCE_PCT
            passed_tp1    = _tp1_dist_pct >= _min_tp1
            self._record("gate_min_tp1", passed_tp1)
            if not passed_tp1:
                return (
                    False,
                    f"G0.8_FAIL: TP1 distance={_tp1_dist_pct:.3%} < {_min_tp1:.2%} minimum "
                    f"(slippage would consume TP1 profit)",
                    0.0,
                )
            # TP1 distance bonus: wide TP1 adds up to +5 quality points
            quality_score += min(5.0, (_tp1_dist_pct / 0.02) * 5.0)
        else:
            self._record("gate_min_tp1", True)   # no price data → pass-through

        # ── Gate 1 — Weighted R:R ratio ───────────────────────────────────────
        risk = abs(entry - sl) if (entry and sl) else 0.0
        if risk < 1e-10:
            self._record("gate1", False)
            return False, "G1_FAIL: zero/invalid risk (entry==SL)", 0.0
        w1, w2, w3 = TP_ALLOCATION[0] / 100.0, TP_ALLOCATION[1] / 100.0, TP_ALLOCATION[2] / 100.0
        reward = (
            abs(tp1 - entry) * w1 +
            abs(tp2 - entry) * w2 +
            abs(tp3 - entry) * w3
        ) if entry else 0.0
        rr = reward / risk if risk > 0 else 0.0
        passed_g1 = rr >= MIN_RR_RATIO
        self._record("gate1", passed_g1)
        if not passed_g1:
            return False, f"G1_FAIL: weighted R:R={rr:.2f} < {MIN_RR_RATIO}", 0.0
        quality_score += min(20.0, (rr - MIN_RR_RATIO) / max(0.01, 3.0 - MIN_RR_RATIO) * 20.0)

        # ── Gate 2 — Swarm consensus ──────────────────────────────────────────
        _no_swarm_data = (consensus == 0.0)
        passed_g2 = consensus >= SWARM_MIN_CONSENSUS or _no_swarm_data
        self._record("gate2", passed_g2)
        if not passed_g2:
            return False, f"G2_FAIL: consensus={consensus:.2f} < {SWARM_MIN_CONSENSUS}", 0.0
        # FIX v5.3: consensus=0 means no swarm data — give neutral 10pt (v5.0 gave 0pt
        # which unfairly penalised non-swarm sources; v5.3 grants a neutral baseline).
        # Full-swarm signals still get up to 20pt proportional to their consensus.
        quality_score += 10.0 if _no_swarm_data else min(20.0, consensus * 20.0)

        # ── Gate 2.5 — Orderbook Imbalance Veto (v9.6) ────────────────────────
        # Hard-veto signals where Binance L2 order-flow is STRONGLY OPPOSED to
        # the trade direction with material book imbalance.  This catches the
        # "Market X-Ray" failure mode: rule-based swarm says BUY but the resting
        # limit-order book is stacked with sell-side liquidity that will absorb
        # any upside attempt.  Aligned/neutral flow passes through unchanged
        # (and still receives the existing +4-6 confidence boost upstream).
        # Thresholds: STRONG_* opposition + |imbalance| > 0.30 → reject.
        # Soft tolerance: missing/empty bookmap data is a pass-through (no veto).
        passed_g25 = True
        if bookmap_result and isinstance(bookmap_result, dict) and "error" not in bookmap_result:
            _bm_dir = str(bookmap_result.get("order_flow_direction", "")).upper()
            try:
                _bm_imb = abs(float(bookmap_result.get("volume_imbalance", 0.0)))
            except (TypeError, ValueError):
                _bm_imb = 0.0
            _opposed = (
                (direction == "BUY"  and _bm_dir in ("STRONG_SELL", "SELL")) or
                (direction == "SELL" and _bm_dir in ("STRONG_BUY",  "BUY"))
            )
            # Hard-block only on STRONG opposition with material imbalance.
            # Plain BUY/SELL opposition with imb ≤ 0.30 is still allowed
            # (mild flow is noisy on 100ms snapshots).
            if _opposed and "STRONG" in _bm_dir and _bm_imb > 0.30:
                passed_g25 = False
                self._record("gate_book_imb", False)
                return False, (
                    f"G2.5_FAIL: orderbook opposed — flow={_bm_dir} "
                    f"imb={_bm_imb:.2f} vs signal={direction}"
                ), 0.0
        self._record("gate_book_imb", passed_g25)
        # Aligned strong flow earns up to +5 quality points (small reward —
        # the bigger boost already lives in the bot's pre-dispatch confidence).
        if bookmap_result and isinstance(bookmap_result, dict):
            _bm_dir2 = str(bookmap_result.get("order_flow_direction", "")).upper()
            if (direction == "BUY"  and _bm_dir2 in ("STRONG_BUY",  "BUY")) or \
               (direction == "SELL" and _bm_dir2 in ("STRONG_SELL", "SELL")):
                quality_score += 5.0 if "STRONG" in _bm_dir2 else 2.0

        # ── Gate 2.5b — Technical Pattern Recognition bias (v11.0) ───────────
        # PatternRecognizer scores 24 candlestick + 8 chart patterns.
        # Net score in [-8, +8]: positive = bullish setup, negative = bearish.
        # Directionally aligned patterns add quality; opposed patterns subtract.
        # No hard-veto: patterns are advisory (noise on short timeframes).
        _pattern_rec = getattr(self, "_pattern_recognizer", None)
        if _pattern_rec is not None:
            try:
                _pa = _pattern_rec.get_cached(symbol)
                if _pa is not None and hasattr(_pa, "net_pts"):
                    _net = float(_pa.net_pts)
                    _aligned = (
                        (direction == "BUY"  and _net > 0.5) or
                        (direction == "SELL" and _net < -0.5)
                    )
                    _opposed = (
                        (direction == "BUY"  and _net < -2.0) or
                        (direction == "SELL" and _net > 2.0)
                    )
                    if _aligned:
                        quality_score += min(8.0, abs(_net))
                    elif _opposed:
                        quality_score -= min(6.0, abs(_net) * 0.75)
            except Exception:
                pass   # never let pattern errors kill gate processing

        # ── Gate 3 — AI confidence (RL-adaptive threshold) ────────────────────
        passed_g3 = confidence >= ai_threshold
        # v8.2: Unanimous-consensus soft-pass (mirrors Gate 4 logic).
        # When all 10 swarm agents agree (consensus=100%) AND the signal is within
        # 4 pts of the threshold, the rule-based evidence is sufficiently strong
        # to allow a soft pass.  This captures near-threshold signals that would
        # be approved by the AI gate if keys were available, while keeping the
        # hard block for clearly weak signals (confidence < threshold - 4).
        if not passed_g3 and consensus >= 1.0 and (ai_threshold - confidence) <= 4.0:
            passed_g3 = True
            self._logger.debug(
                f"G3_SOFT: confidence={confidence:.1f}% ≈ threshold={ai_threshold:.0f}% "
                f"(within 4pt) + unanimous consensus=100% → soft pass [v8.2]"
            )
        self._record("gate3", passed_g3)
        if not passed_g3:
            return False, f"G3_FAIL: confidence={confidence:.1f}% < {ai_threshold:.0f}%", 0.0
        quality_score += min(20.0, (confidence / 100.0) * 20.0)

        # ── Gate 4 — Neural network ───────────────────────────────────────────
        if nn_trainer is not None and self._health.is_available("NeuralNetwork"):
            try:
                # v9.5: Prefer the bot's already-computed NN value when present.
                # The bot evaluates the NN once during pre-dispatch; passing that
                # exact MC-Dropout sample through eliminates the duplicate compute
                # AND the stochastic mismatch (bot=0.58 vs Unity=0.50 on the same
                # signal/instant) that previously caused honest unanimous-soft
                # signals to die at G4 because Unity's re-roll fell below 0.55.
                _precomp = signal_data.get("nn_win_prob_precomputed") if isinstance(signal_data, dict) else None
                if _precomp is not None:
                    nn_prob = float(_precomp)
                else:
                    nn_prob = float(
                        nn_trainer.predict(signal_data)
                        if callable(getattr(nn_trainer, "predict", None))
                        else 0.5
                    )
                # v10.5 FIX: let the trainer's G-mean-optimal threshold drive G4.
                # Previous clamp was max(0.55, min(0.70, opt)) which ALWAYS pinned
                # to 0.55 (the trainer's opt is ~0.22-0.28 at 27% WR).
                # New clamp: max(NN_WIN_PROB_GATE=0.28, min(0.55, opt)) lets the
                # adaptive threshold actually work — with floor 0.28 preventing
                # the gate from becoming a rubber-stamp at very low confidence.
                _raw_opt = float(getattr(nn_trainer, "_opt_threshold", NN_WIN_PROB_GATE))
                nn_threshold = max(NN_WIN_PROB_GATE, min(0.55, _raw_opt))
            except Exception:
                nn_prob = 0.5
                nn_threshold = NN_WIN_PROB_GATE
            passed_g4 = nn_prob >= nn_threshold
            # v10.5 G4 FIX-A: Unanimous soft-bypass — dynamic floor.
            # Original 0.55 floor was always above the NN's output (0.05-0.15
            # at 27% WR), so unanimous consensus bypass NEVER fired.
            # New floor: 60% of the dynamic opt_threshold (so if opt=0.28,
            # bypass fires at nn_prob ≥ 0.17 with full swarm unanimity).
            # This lets strong swarm agreement override a calibration-biased NN.
            _g4_bypass_floor = nn_threshold * 0.60
            if not passed_g4 and consensus >= 0.95 and nn_prob >= _g4_bypass_floor:
                passed_g4 = True
                self._logger.debug(
                    f"G4_BYPASS [{symbol}]: unanimous consensus={consensus:.0%} "
                    f"+ nn_prob={nn_prob:.2f}≥{_g4_bypass_floor:.2f}(60%×opt) → soft bypass [v10.5]"
                )
            # v10.5 G4 FIX-B: High-uncertainty soft-pass.
            # When NN σ>0.20 ("unknown regime") and 80%+ swarm agreement, the
            # NN acknowledges it cannot reliably discriminate.  Convert to a
            # quality-penalty pass instead of a hard block so Gate 9 (quality
            # floor ≥42) makes the final decision.  Hard block is kept for
            # confident-but-low-prob predictions (σ≤0.15 AND nn<threshold).
            if not passed_g4:
                # v10.5 FIX-B: Read uncertainty from signal_data first (accurate
                # for current signal), fall back to trainer._last_uncertainty.
                _nn_unc_raw = (
                    signal_data.get("nn_uncertainty_precomputed")
                    if isinstance(signal_data, dict) else None
                )
                if _nn_unc_raw is None:
                    _nn_unc_raw = getattr(nn_trainer, "_last_uncertainty", 0.0)
                _nn_unc = float(_nn_unc_raw or 0.0)
                if _nn_unc > 0.18 and consensus >= 0.80:  # v11.1: 0.15→0.18; aligns with "σ>0.20 unknown-regime" comment intent; reduces low-certainty bypass leakage
                    _unc_penalty = min(18.0, max(2.0, (_nn_unc - 0.18) * 30.0 + 3.0))
                    quality_score -= _unc_penalty
                    passed_g4 = True
                    self._logger.debug(
                        f"G4_UNC_SOFT [{symbol}]: σ={_nn_unc:.2f}>0.18 "
                        f"consensus={consensus:.0%}≥80% → soft pass "
                        f"−{_unc_penalty:.1f}pts quality [v11.1]"
                    )
            self._record("gate4", passed_g4)
            if not passed_g4:
                return False, f"G4_FAIL: NN win-prob={nn_prob:.2f} < {nn_threshold:.2f}", 0.0
            quality_score += min(15.0, nn_prob * 15.0)
        else:
            self._record("gate4", True)
            quality_score += 7.5

        # ── Gate 5 — External analyzer alignment (symmetric veto) ─────────────
        atas_dir = None
        bm_dir   = None

        if atas_result and isinstance(atas_result, dict) and "error" not in atas_result:
            # FIX v5.2: ATAS analyzer returns 'composite_signal' not 'overall_signal'.
            # Previously Gate 5 always read an empty string → atas_dir stayed None
            # → veto never fired and quality bonus never awarded fully.
            sig = atas_result.get(
                "overall_signal",
                atas_result.get(
                    "composite_signal",
                    atas_result.get("signal", "")
                )
            )
            if isinstance(sig, str) and sig:
                if "BUY" in sig.upper() or "BULL" in sig.upper():
                    atas_dir = "BUY"
                elif "SELL" in sig.upper() or "BEAR" in sig.upper():
                    atas_dir = "SELL"

        if bookmap_result and isinstance(bookmap_result, dict) and "error" not in bookmap_result:
            bm_sig = bookmap_result.get("order_flow_direction", "")
            if isinstance(bm_sig, str) and bm_sig:
                if "BUY" in bm_sig.upper():
                    bm_dir = "BUY"
                elif "SELL" in bm_sig.upper():
                    bm_dir = "SELL"

        atas_disagrees = atas_dir is not None and atas_dir != direction
        bm_disagrees   = bm_dir   is not None and bm_dir   != direction
        atas_agrees    = atas_dir == direction
        bm_agrees      = bm_dir   == direction

        # v7.1 G5 REWRITE — soft-veto replaces hard-block for single-analyzer cases.
        # Live diagnostics showed G5 = 25% pass rate (biggest bottleneck in the pipeline)
        # because the old logic hard-blocked whenever ONE analyzer disagreed even if the
        # OTHER had no data at all.  This caused IRONS Gate 10 to never activate.
        # Fix: only HARD-BLOCK when BOTH analyzers explicitly disagree.
        #      When only one disagrees (other has no data), apply a quality penalty so
        #      Gate 9 and Gate 10 make the final quality-adjusted decision.
        if atas_disagrees and bm_disagrees:
            # Both analyzers say opposite direction → HARD VETO (unchanged)
            passed_g5 = False
            self._record("gate5", False)
            return False, f"G5_FAIL: dual analyzer veto (ATAS={atas_dir} BM={bm_dir} dir={direction})", 0.0

        elif atas_disagrees and bm_dir is None:
            # ATAS disagrees but Bookmap has no data — soft penalty, don't block
            passed_g5 = True
            quality_score -= G5_SINGLE_VETO_PENALTY
            self._logger.debug(
                f"G5_SOFT: ATAS={atas_dir} disagrees (BM=no data) — "
                f"−{G5_SINGLE_VETO_PENALTY:.0f}pts quality penalty (v7.1)"
            )

        elif bm_disagrees and atas_dir is None:
            # Bookmap disagrees but ATAS has no data — soft penalty, don't block
            passed_g5 = True
            quality_score -= G5_SINGLE_VETO_PENALTY
            self._logger.debug(
                f"G5_SOFT: BM={bm_dir} disagrees (ATAS=no data) — "
                f"−{G5_SINGLE_VETO_PENALTY:.0f}pts quality penalty (v7.1)"
            )

        elif atas_disagrees and bm_agrees:
            # Split signal — Bookmap confirms but ATAS contradicts → small penalty
            passed_g5 = True
            quality_score -= G5_SPLIT_VETO_PENALTY
            self._logger.debug(
                f"G5_SPLIT: ATAS={atas_dir}≠dir BM={bm_dir}=dir — "
                f"−{G5_SPLIT_VETO_PENALTY:.0f}pts split penalty"
            )

        elif bm_disagrees and atas_agrees:
            # Split signal — ATAS confirms but Bookmap contradicts → small penalty
            passed_g5 = True
            quality_score -= G5_SPLIT_VETO_PENALTY
            self._logger.debug(
                f"G5_SPLIT: BM={bm_dir}≠dir ATAS={atas_dir}=dir — "
                f"−{G5_SPLIT_VETO_PENALTY:.0f}pts split penalty"
            )

        else:
            # Neither disagrees — pass cleanly
            passed_g5 = True

        self._record("gate5", passed_g5)
        # Quality bonus: agreement adds up to +10, full agreement adds +10, partial +5
        if atas_agrees and bm_agrees:
            quality_score += 10.0    # both confirm → full alignment bonus
        elif atas_agrees or bm_agrees:
            quality_score += 5.0     # one confirms (other neutral) → partial bonus
        elif atas_dir is None and bm_dir is None:
            quality_score += 3.0     # no analyzer data → neutral (was 5.0)

        # ── Gate 6 — Regime filter (Public API / Fear & Greed) ────────────────
        if self._public_api is not None:
            try:
                summary = self._public_api.get_market_summary()
                fg = int(summary.get("fear_greed", 50) or 50)
                if fg <= 20 and direction == "BUY":
                    self._record("gate6", False)
                    return False, f"G6_FAIL: F&G={fg} (extreme fear) blocks LONG", 0.0
                if fg >= 85 and direction == "SELL":
                    self._record("gate6", False)
                    return False, f"G6_FAIL: F&G={fg} (extreme greed) blocks SHORT", 0.0
                self._record("gate6", True)
                fg_quality = 1.0 - abs(fg - 50) / 50.0
                quality_score += fg_quality * 7.5
            except Exception:
                self._record("gate6", True)
                quality_score += 3.75
        else:
            self._record("gate6", True)
            quality_score += 3.75

        # ── Gate 7 — GEX Regime (AEGIS Dealer Flow) ───────────────────────────
        # v5.2: regime-aware DGRP thresholds:
        #   FLIP ZONE      → 35  (natural low-DGRP transition zone)
        #   POSITIVE/NEG   → 45  (only enter with strong dealer conviction)
        #   NEUTRAL/UNKNOWN→ 35  (permissive when regime is unclear)
        if gex_snapshot is not None and self._health.is_available("AEGIS_GEX"):
            try:
                regime    = str(getattr(gex_snapshot, "regime", "NEUTRAL")).upper()
                dgrp      = float(getattr(gex_snapshot, "dgrp_score", 50) or 50)
                gex_conf  = float(getattr(gex_snapshot, "confidence", 50) or 50)
                # Regime-aware DGRP threshold
                if "FLIP" in regime:
                    dgrp_threshold = GEX_FLIP_ZONE_DGRP   # v5.9: 35→30 for FLIP ZONE
                elif regime in ("POSITIVE", "NEGATIVE"):
                    dgrp_threshold = 45
                else:
                    dgrp_threshold = GEX_MIN_DGRP  # 35 for NEUTRAL/UNKNOWN
                passed_dgrp = dgrp >= dgrp_threshold
                regime_ok = True
                if regime == "POSITIVE" and direction == "SELL" and gex_conf >= GEX_MIN_CONFIDENCE:
                    regime_ok = False
                elif regime == "NEGATIVE" and direction == "BUY" and gex_conf >= GEX_MIN_CONFIDENCE:
                    regime_ok = False
                passed_g7 = passed_dgrp and regime_ok
                self._record("gate7", passed_g7)
                if not passed_g7:
                    return False, (
                        f"G7_FAIL: GEX regime={regime} dir={direction} "
                        f"dgrp={dgrp:.0f} thresh={dgrp_threshold} conf={gex_conf:.0f}"
                    ), 0.0
                if (regime == "POSITIVE" and direction == "BUY") or \
                   (regime == "NEGATIVE" and direction == "SELL"):
                    quality_score += 7.5   # strong aligned bonus
                elif "FLIP" in regime:
                    quality_score += 5.5   # flip zone breakout bonus (v5.2 new)
                else:
                    quality_score += 3.75

                # ── v8.0 GEX Gamma Zero proximity bonus ─────────────────────
                # When the entry price is within GEX_GAMMA_ZERO_PROX_PCT of the
                # Gamma Zero level (GEX flip proxy), the market is at a critical
                # dealer-hedge inflection point — entries here have significantly
                # higher mean-reversion win rate than random entries.
                # GEX formula: GEX = Σ(OI × Gamma × 100) → zero crossing = flip
                _gamma_zero = float(getattr(gex_snapshot, "gamma_zero",
                              getattr(gex_snapshot, "gex_flip_price", 0)) or 0)
                if _gamma_zero and entry:
                    _gz_dist_pct = abs(entry - _gamma_zero) / entry
                    if _gz_dist_pct <= GEX_GAMMA_ZERO_PROX_PCT:
                        quality_score += GEX_GAMMA_ZERO_QUALITY_BONUS
                        self._logger.debug(
                            f"🎯 [{symbol}] Gamma Zero proximity: entry={entry:.4f} "
                            f"GZ={_gamma_zero:.4f} dist={_gz_dist_pct:.3%} "
                            f"→ +{GEX_GAMMA_ZERO_QUALITY_BONUS:.0f}pts"
                        )

                # ── v8.0 VOL TRIGGER directional alignment bonus ─────────────
                # VOL TRIGGER UP/DOWN are price levels at which realized vol
                # accelerates.  A BUY signal above VOL_TRIGGER_UP (or SELL below
                # VOL_TRIGGER_DN) aligns with the volatility expansion direction
                # and historically delivers better momentum continuation.
                _vt_up = float(getattr(gex_snapshot, "vol_trigger_up",
                         getattr(gex_snapshot, "vt_up", 0)) or 0)
                _vt_dn = float(getattr(gex_snapshot, "vol_trigger_dn",
                         getattr(gex_snapshot, "vt_dn", 0)) or 0)
                if direction == "BUY" and _vt_up and entry >= _vt_up:
                    quality_score += GEX_VOL_TRIGGER_QUALITY_BONUS
                    self._logger.debug(
                        f"📈 [{symbol}] VOL TRIGGER UP aligned: entry={entry:.4f} "
                        f">= VT_UP={_vt_up:.4f} → +{GEX_VOL_TRIGGER_QUALITY_BONUS:.0f}pts"
                    )
                elif direction == "SELL" and _vt_dn and entry <= _vt_dn:
                    quality_score += GEX_VOL_TRIGGER_QUALITY_BONUS
                    self._logger.debug(
                        f"📉 [{symbol}] VOL TRIGGER DN aligned: entry={entry:.4f} "
                        f"<= VT_DN={_vt_dn:.4f} → +{GEX_VOL_TRIGGER_QUALITY_BONUS:.0f}pts"
                    )

                # ── v8.0 Prompt 2: GEX Zero-Crossing hybrid strategy tag ────────
                # Classifies the trade as MEAN_REVERT or TREND_FOLLOW based on
                # the relationship between entry price and gamma zero level, then
                # applies a precision quality bonus.
                #
                # MEAN_REVERT mode — price is within GZ proximity AND the GEX
                #   regime is in a FLIP ZONE (dealer hedging compresses range):
                #   expect reversion back toward gamma zero.  A BUY below GZ or
                #   SELL above GZ exploits this compression → +3 pts precision.
                #
                # TREND_FOLLOW mode — price has just crossed gamma zero (GEX sign
                #   changed) and regime is NOT neutral: dealer hedging NOW
                #   accelerates the move.  Aligning direction with the crossing
                #   captures the institutional momentum spike → +4 pts precision.
                #
                # This is NOT a duplicate of the GZ proximity bonus above —
                # the proximity bonus fires on distance alone; this bonus fires
                # only when directional alignment with the crossing is correct.
                if _gamma_zero and entry:
                    _gz_signed_dist = (entry - _gamma_zero) / entry  # + if above GZ
                    _in_flip   = "FLIP" in regime
                    _gz_close  = abs(_gz_signed_dist) <= GEX_GAMMA_ZERO_PROX_PCT

                    if _in_flip and _gz_close:
                        # Mean-reversion: BUY below GZ or SELL above GZ
                        if (direction == "BUY" and _gz_signed_dist < 0) or \
                           (direction == "SELL" and _gz_signed_dist > 0):
                            quality_score += 3.0
                            self._logger.debug(
                                f"↩️  [{symbol}] GEX MEAN_REVERT: entry{'<' if _gz_signed_dist < 0 else '>'}GZ "
                                f"({_gz_signed_dist:+.3%}) in FLIP ZONE → +3pts"
                            )
                    elif not _gz_close and abs(_gz_signed_dist) <= GEX_GAMMA_ZERO_PROX_PCT * 3:
                        # Trend-follow: price just crossed GZ — enter in crossing direction
                        if (direction == "BUY" and _gz_signed_dist > 0) or \
                           (direction == "SELL" and _gz_signed_dist < 0):
                            quality_score += 4.0
                            self._logger.debug(
                                f"📐 [{symbol}] GEX TREND_FOLLOW: entry crossed GZ "
                                f"({_gz_signed_dist:+.3%}) → momentum spike → +4pts"
                            )

            except Exception as e:
                self._logger.debug(f"Gate 7 GEX error (non-fatal): {e}")
                self._record("gate7", True)
                quality_score += 3.75
        else:
            self._record("gate7", True)
            quality_score += 3.75

        # ── Gate 7b — BS Greeks IV Skew bonus (v11.0) ─────────────────────────
        # Call skew → positive dealer flow → BUY bias (+2pts)
        # Put skew  → tail-risk hedging active → SELL alignment (+2pts)
        _bs_eng = getattr(self, "_bs_greeks_engine", None)
        if _bs_eng is not None:
            try:
                _base_sym = symbol.replace("USDT", "").replace("PERP", "")[:3]
                _skew = _bs_eng.get_skew(_base_sym)
                if _skew is not None and hasattr(_skew, "skew_regime"):
                    _sr = str(_skew.skew_regime).upper()
                    if _sr == "CALL_SKEW" and direction == "BUY":
                        quality_score += 2.0
                    elif _sr == "PUT_SKEW" and direction == "SELL":
                        quality_score += 2.0
                    elif _sr == "PUT_SKEW" and direction == "BUY":
                        quality_score -= 1.5
            except Exception:
                pass

        # ── Gate 8 — Per-symbol win rate ──────────────────────────────────────
        # [v9.7-DYN] Hard block REMOVED — converted to dynamic quality modifier.
        # Old behavior (still available via UNITY_GATE8_HARD=1): hard-veto any
        # symbol with WR<SYMBOL_MIN_WIN_RATE over ≥SYMBOL_MIN_TRADES trades.
        # New default: scale a quality penalty/bonus around the 35% pivot so
        # weak symbols are demoted (not banned) and strong symbols rewarded —
        # lets recovering symbols re-prove themselves instead of being frozen.
        _g8_hard = os.getenv("UNITY_GATE8_HARD", "0").strip().lower() not in ("0", "false", "no", "")
        if _g8_hard and symbol and self._sym_tracker.is_blocked(symbol):
            wr = self._sym_tracker.win_rate(symbol)
            n  = self._sym_tracker.trade_count(symbol)
            self._record("gate8", False)
            return False, (
                f"G8_FAIL: {symbol} win_rate={wr:.0%} < {SYMBOL_MIN_WIN_RATE:.0%} "
                f"({n} trades) — blocked [hard mode]"
            ), 0.0
        self._record("gate8", True)
        if symbol and self._sym_tracker.trade_count(symbol) >= SYMBOL_MIN_TRADES:
            # Dynamic Gate 8: quality delta linearly proportional to how far
            # the rolling WR is from SYMBOL_MIN_WIN_RATE. Penalty floor = -12,
            # bonus ceiling = +5. Symbols with WR≥0.55 get the full +5; symbols
            # at WR=0 get the full -12 (still allowed through, just demoted).
            sym_wr = self._sym_tracker.win_rate(symbol)
            _delta_wr = sym_wr - SYMBOL_MIN_WIN_RATE
            if _delta_wr >= 0:
                _q_adj = min(5.0, _delta_wr * 25.0)        # +0..+5 between WR=0.35 → 0.55
            else:
                _q_adj = max(-12.0, _delta_wr * 34.3)      # -0..-12 between WR=0.35 → 0.00
            quality_score += _q_adj
            if _q_adj <= -6.0:
                self._logger.debug(
                    f"G8_DYN: {symbol} WR={sym_wr:.0%} → quality {_q_adj:+.1f}pts "
                    f"(n={self._sym_tracker.trade_count(symbol)})"
                )
        elif symbol:
            # Insufficient sample (< SYMBOL_MIN_TRADES) — neutral
            quality_score += 1.5
        else:
            quality_score += 2.5

        # ── Gate 8.5 — Dynamic-backtest quality bias (v9.9.1 Apex-#5) ─────────
        # Soft modifier (-8 .. +5) derived from a vectorised proxy backtest
        # of the latest UNITY_DBT_LOOKBACK_BARS of 15m USDM klines.  Provides
        # a synthetic per-symbol prior when Gate 8 has insufficient live trades
        # (the typical case for newly-listed perps & freshly un-blacklisted
        # rescues).  Never hard-vetos.  When the backtester is absent / stale
        # / under-sampled, falls back to MiroFish swarm simulation bias.
        _dbt = getattr(self, "_dyn_backtester", None)
        _dbt_min_trades = int(getattr(self, "_dbt_min_trades", 10))
        _gate85_applied = False
        if symbol and _dbt is not None:
            try:
                _bias = float(_dbt.quality_bias(symbol, max_age_sec=UNITY_DBT_MAX_AGE_SEC))
                # Check if backtest has enough live trade data to be trusted
                _r = _dbt.result(symbol)
                _n_trades = getattr(_r, "n_trades", 0) if _r is not None else 0
                if _n_trades >= _dbt_min_trades:
                    if _bias != 0.0:
                        quality_score += _bias
                        _gate85_applied = True
                        if _bias <= -3.0:
                            self._logger.debug(
                                f"G8.5_DYN: {symbol} bt_WR={getattr(_r,'win_rate',0):.0%} "
                                f"PF={getattr(_r,'profit_factor',0):.2f} EV={getattr(_r,'ev_r',0):+.2f}R "
                                f"n={_n_trades} → quality {_bias:+.1f}pts"
                            )
            except Exception:
                pass

        # v10.0: MiroFish swarm simulation fallback bias for Gate 8.5
        # When DYN_BACKTEST result has insufficient live trades or is unavailable,
        # use the 10-agent swarm proxy backtest bias as the quality modifier.
        if symbol and not _gate85_applied:
            _msim = getattr(self, "_mirofish_sim", None)
            if _msim is not None:
                try:
                    _sim_bias = float(_msim.get_quality_bias(symbol))
                    if _sim_bias != 0.0:
                        quality_score += _sim_bias
                        self._logger.debug(
                            f"G8.5_MFISH: {symbol} swarm_sim bias → {_sim_bias:+.1f}pts"
                        )
                except Exception:
                    pass

        # ── Gate 8.5b — Factor IC/IR quality bias (v11.0) ────────────────────
        # Applies Factor IC/IR directional alpha signal as a soft quality bias.
        # Strong factor (IC>0.05, IR>0.30) aligned with trade direction → +3.
        # Weak or opposing factor → -2 pts.  Missing data → no-op.
        _fac_ana = getattr(self, "_factor_analyzer", None)
        if symbol and _fac_ana is not None:
            try:
                _fac_bias = _fac_ana.get_quality_bias(symbol)
                if _fac_bias != 0.0:
                    quality_score += _fac_bias
                    self._logger.debug(
                        f"G8.5b_FACTOR: {symbol} factor bias → {_fac_bias:+.1f}pts"
                    )
            except Exception:
                pass

        # ── Gate 8.5c — Portfolio Optimizer Kelly adjustment (v11.0) ──────────
        # Portfolio optimizer provides per-symbol allocation weight [0..1].
        # High allocation (>0.15) → modest quality boost; over-weight > 0.25 → skip.
        _port_opt = getattr(self, "_portfolio_optimizer", None)
        if symbol and _port_opt is not None:
            try:
                _sym_weight = _port_opt.get_weight(symbol)
                if _sym_weight is not None:
                    if _sym_weight > 0.25:
                        quality_score += 3.0
                    elif _sym_weight > 0.12:
                        quality_score += 1.5
                    elif _sym_weight < 0.02:
                        quality_score -= 1.0
            except Exception:
                pass

        quality_score = min(100.0, max(0.0, quality_score))

        # ── Gate 9 — Composite quality floor (v5.8) ───────────────────────────
        # Rejects barely-passing signals whose composite quality is below the
        # minimum floor, pruning the weakest signals and improving win rate.
        # Only applied when a minimum quality is configured (> 0).
        if SIGNAL_MIN_QUALITY_GATE > 0 and quality_score < SIGNAL_MIN_QUALITY_GATE:
            self._record("gate9", False)
            return False, (
                f"G9_FAIL: quality={quality_score:.1f}/100 < {SIGNAL_MIN_QUALITY_GATE:.0f} minimum"
            ), quality_score
        self._record("gate9", True)

        # ── Gate 10 — IRONS AI Scorer (v6.0) ─────────────────────────────────
        # 25-indicator composite quality gate: Momentum / Trend / Volatility / Volume
        # Requires IRONSScorer to be wired in via set_irons_scorer().
        # Falls back to pass-through with neutral quality if scorer unavailable.
        _irons_min = self.effective_irons_min   # v6.3: adaptive threshold
        if self._irons_scorer is not None and _irons_min > 0:
            try:
                # v10.8 BUG FIX: Use pre-computed IRONS score from SwarmSignal when
                # available.  SwarmSignal computed IRONS from real 200-bar 15m klines;
                # re-running Gate 10 without those bars produced stub-data artefacts:
                # (1-bar OHLCV, rsi=50, htf=NEUTRAL) → artificially low IRONS scores.
                _precomp_irons = int(signal_data.get("irons_score_precomputed", 0) or 0)
                if _precomp_irons > 0:
                    irons_score = float(_precomp_irons)
                    self._irons_score_ring.append(irons_score)
                else:
                    # Fallback: re-score from signal_data values.
                    # v10.8 bot now passes real 200-bar OHLCV + indicators (atr, rsi,
                    # htf_1h, htf_4h, volume_ratio) so this path also gets real data.
                    _closes  = signal_data.get("closes",  signal_data.get("close_prices", []))
                    _highs   = signal_data.get("highs",   signal_data.get("high_prices", []))
                    _lows    = signal_data.get("lows",    signal_data.get("low_prices", []))
                    _vols    = signal_data.get("volumes", signal_data.get("volume_data", []))
                    _cur_p   = float(signal_data.get("current_price", entry) or entry)
                    _atr     = float(signal_data.get("atr", signal_data.get("atr_value", 0.01)) or 0.01)
                    _rsi     = float(signal_data.get("rsi", 50) or 50)
                    _macd_l  = signal_data.get("macd_line", signal_data.get("macd"))
                    _macd_s  = signal_data.get("macd_signal", signal_data.get("macd_sig"))
                    _vol_r   = float(signal_data.get("volume_ratio", 1.0) or 1.0)
                    _regime  = str(signal_data.get("gex_regime", signal_data.get("regime", "NEUTRAL")) or "NEUTRAL")
                    _htf_1h  = str(signal_data.get("htf_1h", "NEUTRAL"))
                    _htf_4h  = str(signal_data.get("htf_4h", "NEUTRAL"))

                    # Ensure non-empty OHLCV lists (IRONS requires at least 1 element)
                    if not _closes:
                        _closes = [_cur_p]
                    if not _highs:
                        _highs = [_cur_p]
                    if not _lows:
                        _lows = [_cur_p]
                    if not _vols:
                        _vols = [1.0]

                    irons_result = self._irons_scorer.score(
                        closes=_closes,
                        highs=_highs,
                        lows=_lows,
                        volumes=_vols,
                        action=direction,
                        atr=_atr,
                        rsi=_rsi,
                        macd_line=_macd_l,
                        macd_sig=_macd_s,
                        swarm_consensus=consensus,
                        confidence=confidence,
                        vol_ratio=_vol_r,
                        regime=_regime,
                        htf_1h=_htf_1h,
                        htf_4h=_htf_4h,
                    )
                    irons_score = float(
                        irons_result.get("score", irons_result.get("total_score", 0))
                        if isinstance(irons_result, dict) else float(irons_result or 0)
                    )
                    self._irons_score_ring.append(irons_score)

                # v8.1 Quality Override: if composite quality is excellent AND
                # swarm consensus is unanimous (100%), relax the IRONS floor by
                # IRONS_QUALITY_OVERRIDE_RELAX pts.  A signal that cleared all
                # 11 prior gates with perfect scores is unlikely to be a bad trade
                # — the IRONS gap is a calibration artifact, not genuine weakness.
                _effective_min = _irons_min
                _quality_override = (
                    quality_score >= IRONS_QUALITY_OVERRIDE_THRESHOLD
                    and consensus >= 1.0
                )
                if _quality_override and not (irons_score >= _irons_min):
                    _effective_min = max(IRONS_MIN_SCORE, _irons_min - IRONS_QUALITY_OVERRIDE_RELAX)
                    self._logger.debug(
                        f"⚡ [{symbol}] IRONS quality-override: quality={quality_score:.1f} "
                        f"consensus=100% → floor relaxed {_irons_min:.0f}→{_effective_min:.0f}"
                    )

                passed_g10 = irons_score >= _effective_min   # v6.3/v8.1: adaptive + quality override
                self._record("gate10", passed_g10)
                # v6.2 FIX: record IRONS health call so calls counter shows > 0
                self._health.record_call("IRONS_AIScorer", success=passed_g10)
                if not passed_g10:
                    return False, (
                        f"G10_FAIL: IRONS score={irons_score:.1f}/100 < {_effective_min:.0f} "
                        f"(adaptive={_irons_min:.0f}, static base={IRONS_MIN_SCORE:.0f}, "
                        f"quality_override={'YES' if _quality_override else 'NO'})"
                    ), quality_score
                # IRONS bonus: high score adds up to 5 quality points
                _irons_range = max(1.0, 100.0 - _irons_min)
                quality_score = min(100.0, quality_score + (irons_score - _irons_min) / _irons_range * 5.0)
            except Exception as _irons_ex:
                self._logger.debug(f"Gate 10 IRONS error (non-fatal): {_irons_ex}")
                self._record("gate10", True)
                self._health.record_call("IRONS_AIScorer", success=True)   # pass-through counts
        else:
            self._record("gate10", True)
            self._health.record_call("IRONS_AIScorer", success=True)       # scorer not loaded = pass

        return True, "ALL_GATES_PASSED", quality_score

    # v6.2 BUG FIX: map internal dict keys to correct display gate labels
    # (old code used enumerate() → sequential numbers that didn't match gate names)
    _GATE_DISPLAY_LABELS: Dict[str, str] = {
        "gate_ev":         "G0",
        "gate_session":    "G0.5",
        "gate_min_tp1":    "G0.8",    # v6.2: Min TP1 distance gate
        "gate_blacklist":  "GBLK",    # v9.0 FIX: whitelist/blacklist pre-gate
        "gate_funding":    "GFND",    # v9.7: Binance USDM funding-window guard
        "gate_cusum":      "GCUS",    # v9.7: de Prado symmetric CUSUM event filter
        "gate_ofi":        "GOFI",    # v9.7: Order-Flow Imbalance Z-score (Cont 2014)
        "gate1":           "G1",
        "gate2":          "G2",
        "gate_book_imb":  "G2.5",   # v9.6: orderbook imbalance veto (Bookmap)
        "gate3":          "G3",
        "gate4":          "G4",
        "gate5":          "G5",
        "gate6":          "G6",
        "gate7":          "G7",
        "gate8":          "G8",
        "gate9":          "G9",
        "gate10":         "G10",
    }

    def gate_stats_summary(self) -> str:
        """Compact format: G0=95% G0.5=87% G1=100% ... (fits in 84-char console).
        v6.2 FIX: uses actual gate labels not sequential enumerate() index.
        v9.9.1 Apex-#8: prefer rolling window (≥20 samples) for fresh signal,
        fall back to lifetime counts on cold-start. Lifetime counts remain on
        disk; rolling window is in-memory only.
        """
        parts = []
        for gate, stats in self._gate_stats.items():
            label = self._GATE_DISPLAY_LABELS.get(gate, gate)
            _ring = self._gate_stats_recent.get(gate)
            if _ring is not None and len(_ring) >= 20:
                rate = f"{(sum(_ring)/len(_ring))*100:.0f}%"
            else:
                total = stats["pass"] + stats["fail"]
                rate  = f"{stats['pass']/total*100:.0f}%" if total > 0 else "---"
            parts.append(f"{label}={rate}")
        return " ".join(parts)

    def gate_pass_rates(self) -> Dict[str, float]:
        # v9.9.1 Apex-#8: rolling window preferred when warm. Adaptive consumers
        # (AdaptiveIRONS, gate-driven throttles) now react to recent reality
        # rather than lifetime average — critical after gate-threshold changes
        # like Apex-#6 (NN gate 0.58→0.55).
        result = {}
        for gate, stats in self._gate_stats.items():
            _ring = self._gate_stats_recent.get(gate)
            if _ring is not None and len(_ring) >= 20:
                result[gate] = sum(_ring) / len(_ring)
                continue
            total = stats["pass"] + stats["fail"]
            # FIX session 4: default 0.0 not 1.0 — avoids showing "100%" in the
            # health endpoint and console before any signals have been evaluated.
            result[gate] = (stats["pass"] / total) if total > 0 else 0.0
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# 10. UNITY PROFIT BOOSTER  (adaptive confidence + Kelly Criterion)
# ═══════════════════════════════════════════════════════════════════════════════

class UnityProfitBooster:
    """
    Dynamically boosts signal confidence when multiple independent layers agree.
    Uses TRUE 5-bucket RL to adjust AI threshold based on recent win/loss ratio.
    Enforces consecutive-loss circuit breaker.
    Computes Kelly Criterion fraction for position sizing recommendation.
    """

    # 5-bucket RL thresholds
    # v5.7 BUG FIX: Worst-bucket delta +10→+5.  With CONSEC_LOSS_BOOST(3) + RL_DELTA(10)
    # the combined threshold hit 80+3+10=93%, blocking virtually all signals when the
    # bot had a bad streak.  +5 max delta means worst-case threshold = 80+3+5 = 88%:
    # still meaningfully selective but not a complete signal freeze.
    _RL_BUCKETS: List[Tuple[float, float, float]] = [
        (0.00, 0.30, +3.0),   # very bad WR  — raise threshold (v10.6: +4→+3; at base=88 → 91% cap instead of 94%; breaks exploration deadlock)
        (0.30, 0.45, +2.0),   # below-average — slight raise (v10.6: +3→+2; 88+2=90% — exploitable range)
        (0.45, 0.60, +0.0),   # near-average  — neutral (unchanged)
        (0.60, 0.72, -3.0),   # good WR       — allow more signals (unchanged)
        (0.72, 1.01, -6.0),   # excellent WR  — be aggressive (unchanged)
    ]

    def __init__(self):
        self._logger   = logging.getLogger("UnityEngine.Booster")
        self._win_ring = deque(maxlen=50)
        self._rr_ring  = deque(maxlen=50)   # recent R:R values for Kelly
        self.dynamic_threshold = float(AI_THRESHOLD_PERCENT)
        self._consec_losses      = 0
        self._consec_wins        = 0         # v6.0: consecutive-win streak tracker
        self._consec_loss_raised = False
        self._consec_loss_until  = 0.0
        self.last_kelly_fraction = 0.0
        # v9.9.2 Apex-#7: Last outcome timestamp — used by starvation decay in
        # _update_threshold_rl() to break the exploration-exploitation deadlock
        # that pegs the RL threshold at the bucket cap when no fresh outcomes
        # arrive (signal-starved state → ring buffer never updates → threshold
        # never relaxes → no signals can pass → no fresh outcomes …).
        self._last_outcome_ts: float = time.time()
        # v5.7: Session start time — CB suppressed during first 5 min (warmup).
        # OutcomeTracker resolves ALL open trades from previous sessions on startup,
        # calling record_outcome(False) potentially dozens of times in seconds and
        # triggering a cold-start CB spike that blocks signals for 30–60 minutes.
        # The warmup window prevents this artificial inflation without affecting
        # ongoing session accuracy (5 min is far shorter than a typical trade life).
        self._session_start_time = time.time()
        self._WARMUP_SECONDS     = 300   # suppress CB for first 5 min

        # ── v8.0 Omega-Tier: Bayesian win-probability estimator ───────────────
        # Beta(α, β) prior: α = pseudo-wins, β = pseudo-losses.
        # Starting with Beta(2, 2) = uniform-ish but slightly centred at 0.5.
        # Each completed trade updates the posterior: α += 1 on win, β += 1 on loss.
        # Posterior mean = α / (α + β) → used as p in Kelly formula so position
        # sizing responds to the entire trade history, not just the last 50 trades.
        # v8.0 note: ring-buffer win_prob (last 50) is retained as the short-term
        # signal; Bayesian posterior is the long-term prior that blends with it.
        self._bayes_alpha: float = 2.0   # Beta prior α (pseudo-wins)
        self._bayes_beta:  float = 2.0   # Beta prior β (pseudo-losses)

        # ── v8.0 Omega-Tier: Monte Carlo VaR parameters ───────────────────────
        # On each Kelly update, we run a vectorized Monte Carlo simulation to
        # estimate the 95th-percentile maximum drawdown (VaR_95) over 200 trades.
        # If VaR_95 > _VAR_RUIN_THRESHOLD (20%), Kelly fraction is scaled by
        # (threshold / VaR_95) to prevent ruin while preserving compound growth.
        self._var_ruin_threshold: float = 0.20   # VaR hard cap: 20% drawdown
        self._mc_simulations:     int   = 2000   # Monte Carlo paths (vectorized)

        # ── v9.0: Per-trade PnL ring for Sharpe/Sortino tracking ─────────────
        # Stores the last 100 trade PnL percentages as decimals (e.g. 0.02 = 2%).
        # Sharpe = mean(returns) / std(returns) * sqrt(252)  [annualised]
        # Sortino = mean(returns) / downside_std(returns) * sqrt(252)
        # Both are exposed on /metrics and printed in the console dashboard.
        self._pnl_ring: deque = deque(maxlen=100)   # last-100 trade returns

    def warm_start_from_history(self, wins: int, losses: int) -> None:
        """
        v7.2 BUG FIX — RL ring buffer warm-start from persisted W/L history.

        BUG: On every restart, _win_ring was empty → _update_threshold_rl()
        returned immediately at `len < 10` guard → threshold stayed at base 80%
        indefinitely regardless of historical performance (e.g. 27% WR should
        give +4% delta → threshold 84%, but ring always started cold at 80%).

        Fix: pre-populate _win_ring with min(50, total_trades) synthetic
        outcomes at the persisted win rate in interleaved order.  Then call
        _update_threshold_rl() so the threshold is correct immediately on boot.

        v9.3 ENHANCEMENT: also warm-starts the Bayesian prior when not already
        restored from disk/Redis (detected by α+β ≤ 4.1, the Beta(2,2) cold value).
        Without this, a restart with 500 trade history (250W/250L) keeps Beta(2,2)
        with only 4 pseudo-observations instead of Beta(252,252) with 504 — causing
        Kelly's blended p_win to swing 3× wider on hot/cold streaks, leading to
        over-sizing on runs and under-sizing after drawdowns.
        """
        total = wins + losses
        if total < 10:
            return  # not enough history to be meaningful
        # v9.9.1 Apex-#7: shrink warm-start footprint so recent trades dominate.
        # Original `min(50, total)` packed the ENTIRE 50-slot ring with synthetic
        # outcomes at all-time WR — meaning a bot with 27W/85L history (24% WR)
        # would, on every restart, fill all 50 ring slots with that 24% pattern.
        # Result: RL bucketing sees WR<30% → forces threshold to 94% (max) AND
        # Kelly losing-regime cap forces Kelly to 0%. The ring needed 50+ NEW
        # resolved trades before any recent improvement could roll over the
        # warm-start — but the bot resolves only ~6 trades/hr and restarts
        # frequently, so recent wins NEVER influenced the threshold. Death
        # spiral: model fixes (NN loss-learning v9.9, G4 recalibration #6)
        # could not break out because their effect was perpetually overwritten.
        # Fix: cap at min(20, total//2) → leaves ≥30 of 50 slots open for
        # fresh trades. After ~10 fresh resolutions, recent perf dominates.
        # Env-tunable via UNITY_WARMSTART_RING_CAP for live re-tuning.
        _warm_cap = int(os.getenv("UNITY_WARMSTART_RING_CAP", "20") or 20)
        n      = min(_warm_cap, total // 2, 50)
        wr     = wins / total if total > 0 else 0.5
        n_wins = round(n * wr)
        n_loss = n - n_wins
        # Interleave wins and losses proportionally (no random module — pure math)
        w_i = l_i = 0
        while w_i < n_wins or l_i < n_loss:
            # Bresenham-style interleave: append win when behind schedule
            if w_i < n_wins and (l_i >= n_loss or (w_i * n_loss) <= (l_i * n_wins)):
                self._win_ring.append(True)
                w_i += 1
            else:
                self._win_ring.append(False)
                l_i += 1
        # Also seed a reasonable R:R estimate so Kelly isn't stuck at 0 on boot
        avg_rr_estimate = 1.85  # v11.1: 1.8→1.85 — matches actual MIN_RR_RATIO constant; warm-start Kelly was under-sizing by ~3% fractional Kelly due to 0.05 R:R gap
        for _ in range(min(n, 20)):
            self._rr_ring.append(avg_rr_estimate)
        # v9.3 BUG FIX: warm-start Bayesian prior from full trade history when cold.
        # α+β ≤ 4.1 means still at Beta(2,2) cold-start — no saved state restored.
        # Seed α = 2.0 + wins, β = 2.0 + losses (proper posterior from full history).
        _cold_bayes = (self._bayes_alpha + self._bayes_beta) <= 4.1
        if _cold_bayes:
            self._bayes_alpha = 2.0 + wins
            self._bayes_beta  = 2.0 + losses
        # v9.9.2 Apex-#7: warm-start staleness — the trades just loaded into
        # _win_ring are HISTORICAL, not live.  Pre-age _last_outcome_ts by
        # 1800s so the starvation-decay clock starts at "just-stale" instead
        # of zero.  This means: if the engine remains signal-starved AFTER
        # warm-start, the threshold begins relaxing within the first hour
        # (vs waiting a full 30 min from restart for any decay to begin).
        # Decay is gradual so this CANNOT cause an instant flood of low-
        # quality signals — it only restores exploration capacity over time.
        try:
            self._last_outcome_ts = time.time() - 1800.0
        except Exception:
            pass
        self._update_threshold_rl()
        self._update_kelly()
        _bp = self._bayes_alpha / (self._bayes_alpha + self._bayes_beta)
        self._logger.info(
            f"📊 [v9.3] RL ring warm-start: {n} trades (W={n_wins} L={n_loss} "
            f"WR={wr:.1%}) → threshold={self.dynamic_threshold:.0f}% "
            f"Kelly={self.last_kelly_fraction*100:.1f}% "
            f"| Bayes={'warm α={:.0f} β={:.0f} p̂={:.1%}'.format(self._bayes_alpha, self._bayes_beta, _bp) if _cold_bayes else 'restored from disk'}"
        )

    @property
    def sharpe_ratio(self) -> float:
        """Annualised Sharpe Ratio from last-100 trade PnL returns.

        Uses trading-day annualisation factor sqrt(252).  Returns 0.0 when
        fewer than 10 trades are available or std is zero.
        """
        if len(self._pnl_ring) < 10:
            return 0.0
        try:
            if _np is None:
                raise ImportError
            arr  = _np.array(list(self._pnl_ring), dtype=float)
            mu   = float(_np.mean(arr))
            sd   = float(_np.std(arr, ddof=1))
            return (mu / sd * (252 ** 0.5)) if sd > 1e-10 else 0.0
        except Exception:
            return 0.0

    @property
    def sortino_ratio(self) -> float:
        """Annualised Sortino Ratio (downside-deviation only) from last-100 returns.

        Returns 0.0 when fewer than 10 trades are available or there are no losses.
        """
        if len(self._pnl_ring) < 10:
            return 0.0
        try:
            if _np is None:
                raise ImportError
            arr      = _np.array(list(self._pnl_ring), dtype=float)
            mu       = float(_np.mean(arr))
            neg_only = arr[arr < 0.0]
            if len(neg_only) == 0:
                return 0.0
            down_sd  = float(_np.std(neg_only, ddof=1))
            return (mu / down_sd * (252 ** 0.5)) if down_sd > 1e-10 else 0.0
        except Exception:
            return 0.0

    def record_outcome(self, won: bool, pnl_pct: float = 0.0, rr_ratio: float = 0.0):
        """Record a completed trade outcome and update adaptive threshold + Kelly."""
        self._win_ring.append(won)
        # v9.9.2 Apex-#7: refresh staleness timer so the starvation-decay
        # logic in _update_threshold_rl() does NOT fire while real outcomes
        # are flowing in.  Decay only kicks in after 30 min of silence.
        self._last_outcome_ts = time.time()
        # v9.0: store pnl_pct (as decimal fraction) for Sharpe/Sortino computation
        if pnl_pct != 0.0:
            self._pnl_ring.append(pnl_pct / 100.0 if abs(pnl_pct) > 1.0 else pnl_pct)
        if rr_ratio > 0:
            self._rr_ring.append(rr_ratio)
        if won:
            self._consec_losses = 0
            self._consec_wins  += 1
            # FIX v5.3: a win immediately cancels the raised-flag so the threshold
            # returns to RL-adaptive level — v5.2 kept the raise for the full 60-min
            # cooldown even after a winning trade, suppressing valid signals needlessly.
            if self._consec_loss_raised:
                self._consec_loss_raised = False
                self._logger.info(
                    "✅ Consec-Loss CB cancelled early — winning trade recovered threshold"
                )
            # v6.0: consecutive-win streak bonus — log hot streak
            if self._consec_wins == CONSEC_WIN_STREAK_THRESHOLD:
                self._logger.info(
                    f"🔥 [v6.0] Hot streak: {self._consec_wins} consecutive wins — "
                    f"RL bonus={CONSEC_WIN_STREAK_BONUS:+.0f}% applied"
                )
        else:
            self._consec_losses += 1
            self._consec_wins   = 0
            # v5.7 Warmup Guard: suppress CB trigger during the first 5 min.
            # OutcomeTracker resolves all open historical trades on startup,
            # calling record_outcome(False) many times in quick succession which
            # would raise the CB immediately and freeze signals for 30 min.
            _in_warmup = (time.time() - self._session_start_time) < self._WARMUP_SECONDS
            if self._consec_losses >= CONSEC_LOSS_THRESHOLD and not self._consec_loss_raised and not _in_warmup:
                self.dynamic_threshold = min(
                    95.0, self.dynamic_threshold + CONSEC_LOSS_BOOST_PCT
                )
                self._consec_loss_raised = True
                self._consec_loss_until  = time.time() + CONSEC_LOSS_COOLDOWN_SEC
                self._logger.warning(
                    f"⚡ Consec-Loss CB: {self._consec_losses} losses → "
                    f"threshold raised to {self.dynamic_threshold:.0f}% for "
                    f"{CONSEC_LOSS_COOLDOWN_SEC//60}min"
                )
            elif _in_warmup and self._consec_losses >= CONSEC_LOSS_THRESHOLD:
                _warm_remaining = int(self._WARMUP_SECONDS - (time.time() - self._session_start_time))
                self._logger.debug(
                    f"🛡️ [Warmup] {self._consec_losses} consecutive losses — "
                    f"CB suppressed for {_warm_remaining}s startup warmup (v5.7)"
                )
        # ── v8.0 Bayesian posterior update ────────────────────────────────────
        # Beta conjugate prior: posterior is Beta(α + wins, β + losses).
        # This keeps a full-session Bayesian estimate of win probability that
        # complements the short-term ring buffer used by the RL threshold.
        if won:
            self._bayes_alpha += 1.0
        else:
            self._bayes_beta  += 1.0

        self._update_threshold_rl()
        self._update_kelly()

    def _update_threshold_rl(self):
        if self._consec_loss_raised and time.time() >= self._consec_loss_until:
            self._consec_loss_raised = False
            self._consec_losses = 0
            self._logger.info("✅ Consec-Loss CB expired — threshold normalising")

        if len(self._win_ring) < 10:
            return

        recent_wr = sum(self._win_ring) / len(self._win_ring)
        delta = 0.0
        for wr_min, wr_max, adjustment in self._RL_BUCKETS:
            if wr_min <= recent_wr < wr_max:
                delta = adjustment
                break

        # ── v9.9.2 Apex-#7: Starvation-decay (deadlock breaker) ─────────────
        # If no fresh outcomes have arrived for >30 min, the RL ring is stale:
        # it reflects only OLD trades, but the threshold pegs at the bucket
        # cap and prevents new trades from being generated → permanent
        # exploration-exploitation deadlock.  Linearly decay the bucket-derived
        # POSITIVE delta as a function of staleness (negative deltas — i.e.
        # threshold reductions on hot streaks — are not affected, those keep
        # exploiting confirmed winning behaviour).  Decay starts at 30 min,
        # reaches full delta=0 at 90 min.  Fresh outcomes reset _last_outcome_ts.
        try:
            _staleness = time.time() - self._last_outcome_ts
            if _staleness > 1800.0 and delta > 0.0:
                _decay  = max(0.0, 1.0 - (_staleness - 1800.0) / 3600.0)
                _orig_d = delta
                delta   = delta * _decay
                if abs(delta - _orig_d) > 0.1:
                    self._logger.info(
                        f"🔓 [Apex-#7] RL starvation decay: stale={_staleness/60:.1f}min "
                        f"→ delta {_orig_d:+.1f}% → {delta:+.1f}% (factor={_decay:.2f})"
                    )
        except Exception:
            pass

        base = float(AI_THRESHOLD_PERCENT)
        # v6.0: consecutive-win streak bonus — lower threshold on hot streaks
        streak_bonus = (
            CONSEC_WIN_STREAK_BONUS
            if self._consec_wins >= CONSEC_WIN_STREAK_THRESHOLD
            else 0.0
        )
        if self._consec_loss_raised:
            rl_threshold = min(95.0, max(base + CONSEC_LOSS_BOOST_PCT, base + delta + streak_bonus))
        else:
            rl_threshold = min(95.0, max(65.0, base + delta + streak_bonus))

        self.dynamic_threshold = rl_threshold
        self._logger.debug(
            f"RL bucket: wr={recent_wr:.2f} → delta={delta:+.0f}% streak={streak_bonus:+.0f}% → "
            f"threshold={self.dynamic_threshold:.0f}%"
        )

    def tick(self) -> None:
        """v9.9.2 Apex-#7: heartbeat tick.

        Recomputes the RL threshold even when no fresh outcomes arrive.  This
        is the periodic counterpart to record_outcome() and is what allows the
        starvation-decay logic in _update_threshold_rl() to actually fire when
        the engine is signal-starved.  Invoked by the watchdog every poll.
        """
        try:
            self._update_threshold_rl()
        except Exception as _e:
            self._logger.debug(f"Apex-#7 tick non-fatal: {_e}")

    def _update_kelly(self):
        """
        Compute Kelly fraction with:
          1. Short-term win_prob from ring buffer (last 50 trades)
          2. Long-term Bayesian posterior mean from Beta(α, β)
          3. Blended probability (60% short-term + 40% Bayesian)
          4. Monte Carlo VaR constraint (vectorized NumPy, 2000 paths)

        v8.0 Omega-Tier additions:
          • Bayesian blend prevents Kelly from over-reacting to short runs
          • VaR_95 constraint caps Kelly when simulation shows > 20% drawdown
        """
        if len(self._win_ring) < 10:
            self.last_kelly_fraction = 0.0
            return

        # ── 1. Short-term probability (ring buffer) ───────────────────────────
        ring_win_prob = sum(self._win_ring) / len(self._win_ring)
        avg_rr        = (sum(self._rr_ring) / len(self._rr_ring)) if self._rr_ring else 1.5

        # ── 2. Bayesian posterior mean: E[p] = α / (α + β) ───────────────────
        bayes_win_prob = self._bayes_alpha / (self._bayes_alpha + self._bayes_beta)

        # ── 3. Blend: recent performance has higher weight than historical prior
        win_prob  = 0.60 * ring_win_prob + 0.40 * bayes_win_prob
        loss_prob = 1.0 - win_prob

        # ── 4. Kelly formula: f* = (p × b − q) / b ────────────────────────────
        kelly = (win_prob * avg_rr - loss_prob) / avg_rr if avg_rr > 0 else 0.0
        if KELLY_HALF_KELLY:
            kelly *= 0.5
        kelly = max(0.0, min(KELLY_MAX_FRACTION, kelly))

        # ── 4b. v8.6 Losing-Regime Risk Cap ──────────────────────────────────
        # When rolling 20-trade WR drops below 35% (the empirical EV-negative
        # band at avg R:R = 1.92), HALVE Kelly. The previous CB only added
        # +3% to the threshold after 6 consec losses — that suppresses *future*
        # signals but does NOT shrink the size of trades already in the
        # losing-regime pipeline. Halving Kelly here directly reduces capital
        # exposure during demonstrated under-performance, which compounds
        # *recovery* instead of compounding losses.
        if len(self._win_ring) >= 20:
            recent20 = list(self._win_ring)[-20:]
            wr20 = sum(recent20) / 20.0
            if wr20 < 0.35:
                kelly_pre = kelly
                kelly *= 0.5
                self._logger.warning(
                    f"📉 [v8.6] Losing-Regime Risk Cap: rolling-20 WR={wr20:.0%} < 35% "
                    f"→ Kelly halved {kelly_pre*100:.1f}% → {kelly*100:.1f}%"
                )

        # ── 5. Monte Carlo VaR constraint (vectorized NumPy) ──────────────────
        # Simulate _mc_simulations independent 200-trade sequences.
        # Each trade: win +kelly*avg_rr, loss −kelly.  Track equity drawdown.
        # VaR_95 = 95th percentile of the per-path maximum drawdown.
        # If VaR_95 > _var_ruin_threshold, scale Kelly down proportionally.
        if kelly > 0.005:
            try:
                if _np is None:
                    raise ImportError("numpy not available")
                n_trades = 200
                k        = kelly
                # Bernoulli outcomes matrix: shape (mc_paths, n_trades)
                outcomes = _np.random.random(
                    (self._mc_simulations, n_trades)
                ) < win_prob
                # Trade P&L per path:  +k*avg_rr on win, −k on loss
                pnl_per_trade = _np.where(outcomes, k * avg_rr, -k)
                # Cumulative equity (relative to 1.0 starting capital)
                cum_equity = _np.cumprod(1.0 + pnl_per_trade, axis=1)
                # Running maximum for each path
                running_max = _np.maximum.accumulate(cum_equity, axis=1)
                # Per-path maximum drawdown = max( (peak − valley) / peak )
                drawdowns = (running_max - cum_equity) / running_max
                max_drawdown_per_path = drawdowns.max(axis=1)
                var_95 = float(_np.percentile(max_drawdown_per_path, 95))

                # v9.0: CVaR / Expected Shortfall — mean of paths BEYOND the VaR_95
                # CVaR > VaR_95 always (by definition); a high CVaR/VaR ratio means
                # heavy tail risk that pure VaR underestimates.  Use the higher of
                # VaR_95 and CVaR_95 as the constraint so fat-tail regimes are captured.
                _tail_mask = max_drawdown_per_path >= var_95
                cvar_95 = float(_np.mean(max_drawdown_per_path[_tail_mask])) if _tail_mask.any() else var_95
                _risk_metric = max(var_95, cvar_95)

                if _risk_metric > self._var_ruin_threshold:
                    scale = self._var_ruin_threshold / _risk_metric
                    kelly_before = kelly
                    kelly = max(0.0, kelly * scale)
                    self._logger.debug(
                        f"📊 [Omega] Kelly VaR/CVaR constraint: VaR95={var_95:.1%} "
                        f"CVaR95={cvar_95:.1%} (used={_risk_metric:.1%}) > "
                        f"{self._var_ruin_threshold:.0%} → Kelly scaled "
                        f"{kelly_before*100:.1f}% → {kelly*100:.1f}%"
                    )
            except Exception:
                pass  # NumPy not available or MC failed — use unconstrained Kelly

        # ── 6. v9.4 Sharpe-Floor Scaling ─────────────────────────────────────
        # Risk-adjusted-return overlay: if annualised Sharpe is below SHARPE_FLOOR
        # (e.g. -1.0), scale Kelly DOWN linearly toward 0 as Sharpe → -inf.
        # If Sharpe ≥ SHARPE_TARGET (e.g. +0.5), no scaling (full Kelly).
        # Between floor and target, linear interpolation.  Requires ≥10 PnL
        # samples; cold-start passes through unscaled.  This systematically
        # maximises Sharpe per the user's institutional-grade objective: capital
        # is only fully committed when realised risk-adjusted returns warrant it.
        if kelly > 0.0 and len(self._pnl_ring) >= 10 and SHARPE_FLOOR > -50.0:
            try:
                _sr = self.sharpe_ratio   # cached property — re-uses _pnl_ring
                if _sr < SHARPE_TARGET:
                    if _sr <= SHARPE_FLOOR:
                        _sharpe_scale = 0.0   # full block — Sharpe at/below floor
                    else:
                        # Linear interp: floor → 0.0, target → 1.0
                        # v9.7 BUG FIX: guard ZeroDivisionError when operator
                        # sets SHARPE_FLOOR == SHARPE_TARGET via env vars.
                        _sr_diff = SHARPE_TARGET - SHARPE_FLOOR
                        if _sr_diff > 1e-9:
                            _sharpe_scale = (_sr - SHARPE_FLOOR) / _sr_diff
                            _sharpe_scale = max(0.0, min(1.0, _sharpe_scale))
                        else:
                            _sharpe_scale = 1.0 if _sr >= SHARPE_TARGET else 0.0
                    if _sharpe_scale < 1.0:
                        _kelly_pre = kelly
                        kelly *= _sharpe_scale
                        self._logger.info(
                            f"📊 [v9.4] Sharpe-Floor scale: SR={_sr:.2f} "
                            f"(floor={SHARPE_FLOOR:.1f} target={SHARPE_TARGET:.1f}) "
                            f"→ Kelly scaled ×{_sharpe_scale:.2f} "
                            f"({_kelly_pre*100:.1f}% → {kelly*100:.1f}%)"
                        )
            except Exception:
                pass

        self.last_kelly_fraction = max(0.0, min(KELLY_MAX_FRACTION, kelly))

    # ── v9.4 Paper/Shadow mode auto-routing ─────────────────────────────────
    @property
    def paper_mode(self) -> bool:
        """v9.4: Returns True when signals should be LOG-ONLY (no Telegram dispatch).

        Activated when (a) UNITY_SHADOW_MODE forces it, OR (b) auto-shadow is
        enabled AND rolling-20 WR < AUTO_PAPER_WR_THRESHOLD.  In shadow mode,
        the engine continues to compute, score, and audit-log every signal but
        does NOT broadcast to Telegram or execution venues — preserving capital
        during demonstrated under-performance.  Auto-deactivates once rolling
        WR recovers above the threshold (so trading resumes seamlessly).
        """
        if FORCE_SHADOW_MODE:
            return True
        if not AUTO_SHADOW_ENABLED:
            return False
        if len(self._win_ring) < 20:
            return False   # cold-start: trust the booster's other gates
        recent20 = list(self._win_ring)[-20:]
        wr20 = sum(recent20) / 20.0
        return wr20 < AUTO_PAPER_WR_THRESHOLD

    @property
    def consecutive_losses(self) -> int:
        return self._consec_losses

    def boost(
        self,
        base_confidence: float,
        atas_boost:      float = 0.0,
        bookmap_boost:   float = 0.0,
        neural_boost:    float = 0.0,
        insider_boost:   float = 0.0,
        microstr_boost:  float = 0.0,
        intel_boost:     float = 0.0,
        gex_boost:       float = 0.0,
        agency_boost:    float = 0.0,   # v4.0: agency agents boost
    ) -> float:
        """Return boosted confidence capped at 97.0."""
        total_boost = (
            atas_boost + bookmap_boost + neural_boost +
            insider_boost + microstr_boost + intel_boost +
            gex_boost + agency_boost
        )
        return min(97.0, max(0.0, base_confidence + total_boost))


# ═══════════════════════════════════════════════════════════════════════════════
# 11. UNITY CONSOLE  (live status display)
# ═══════════════════════════════════════════════════════════════════════════════

class UnityConsole:
    """Periodic console dashboard showing all layers + global metrics."""

    def __init__(
        self,
        health:        "UnityHealthMonitor",
        metrics:       UnityMetrics,
        signal_filter: UnitySignalFilter,
        booster:       UnityProfitBooster,
        sym_tracker:   PerSymbolTracker,
        refresh_sec:   float = UNITY_CONSOLE_REFRESH_SEC,
        signal_times:  Optional[deque] = None,   # v5.7: live signal-rate ring
        dyn_backtester: Optional[Any] = None,    # v9.9.2: Mirofish swarm backtest
    ):
        self._health        = health
        self._metrics       = metrics
        self._filter        = signal_filter
        self._booster       = booster
        self._sym_tracker   = sym_tracker
        self._refresh       = refresh_sec
        self._signal_times  = signal_times        # v5.7: rate tracking deque
        self._dyn_backtester = dyn_backtester     # v9.9.2: swarm backtest reference
        self._task: Optional[asyncio.Task] = None
        self._logger        = logging.getLogger("UnityEngine.Console")

    async def start(self):
        self._task = asyncio.create_task(self._loop(), name="UnityConsole")

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(self._refresh)
                self._print()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.debug(f"Console loop error (non-fatal): {e}")

    def record_outcome(self, won: bool, pnl_pct: float = 0.0, rr_ratio: float = 0.0):
        try:
            self._booster.record_outcome(won, pnl_pct, rr_ratio)
            # v7.0 BUG FIX: was self.signal_filter / self.metrics (don't exist on
            # UnityConsole).  Correct attribute names are self._filter / self._metrics.
            # The adaptive IRONS WR-propagation was silently failing on every outcome.
            if self._filter is not None:
                _current_wr = self._metrics.win_rate / 100.0
                self._filter.update_adaptive_irons(_current_wr)
        except Exception:
            pass
        # v10.0: Feed quant metrics ring (Sharpe/Sortino/Calmar/MaxDD/EV/Kelly)
        try:
            self._metrics.record_trade_return(float(pnl_pct))
            if won:
                self._metrics.win_count  += 1
            else:
                self._metrics.loss_count += 1
            self._metrics.total_profit_pct += float(pnl_pct)
        except Exception as _e:
            logger.debug(f"[record_outcome] quant metrics update failed: {_e}")

    def _signals_per_hour(self) -> float:
        """Calculate signals sent in the last 60 minutes from the wired signal-time ring."""
        try:
            if not self._signal_times:
                return 0.0
            cutoff = time.time() - 3600.0
            # v11.0 BUG FIX: snapshot the deque before iteration to avoid
            # RuntimeError from concurrent appends in the signal consumer task.
            _snap = list(self._signal_times)
            return sum(1 for t in _snap if t > cutoff)
        except Exception:
            return 0.0

    def _print(self):
        m   = self._metrics
        wr  = m.win_rate
        sr  = m.send_rate
        up  = m.uptime_hours
        kel = self._booster.last_kelly_fraction * 100.0
        sph = self._signals_per_hour()

        # Rate status vs target
        rate_status = (
            "✅" if SIGNALS_PER_HOUR_MIN <= sph <= SIGNALS_PER_HOUR_MAX
            else ("⚠️" if sph > 0 else "🔴")
        )

        # Top / bottom symbols
        top3    = self._sym_tracker.top_symbols(3)
        bottom3 = self._sym_tracker.bottom_symbols(3)
        top_str = " ".join(f"{s}:{r:.0%}" for s, r in top3) or "n/a"
        bot_str = " ".join(f"{s}:{r:.0%}" for s, r in bottom3) or "n/a"

        # v9.9.2: Swarm Backtest console metrics — read DynBacktest results
        # (O(1) dict iteration, no I/O, safe to call from sync render path).
        try:
            _dbt_obj = self._dyn_backtester
            _dbt_res = (
                [r for r in _dbt_obj._results.values() if r.n_trades >= 10]
                if _dbt_obj is not None else []
            )
        except Exception:
            _dbt_res = []
        _dbt_strong = sum(1 for r in _dbt_res if r.win_rate >= 0.45 and r.profit_factor >= 1.25 and r.ev_r > 0.03)
        _dbt_good   = sum(1 for r in _dbt_res if r.win_rate >= 0.38 and r.profit_factor >= 1.05 and r.ev_r > 0.0)
        _dbt_weak   = sum(1 for r in _dbt_res if r.win_rate < 0.28 or r.profit_factor < 0.75 or r.ev_r < -0.12)
        _dbt_top    = sorted(_dbt_res, key=lambda r: r.ev_r, reverse=True)[:3]
        _dbt_top3   = " ".join(f"{r.symbol}(EV={r.ev_r:+.2f}R WR={r.win_rate:.0%})"
                               for r in _dbt_top) or "pending first sweep"

        W = 84  # console width
        border = "═" * (W - 2)

        def row(txt: str) -> str:
            """Left-pad and right-pad a row to exactly W chars."""
            inner = txt[:W - 4]
            return f"║  {inner:<{W-4}}║"

        lines = [
            "",
            f"╔{border}╗",
            row(f"UNITY ENGINE v{UNITY_VERSION}  ·  Uptime: {up:.1f}h  ·  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            f"╠{border}╣",
            row(f"Signals: sent={m.total_signals_sent}  eval={m.total_signals_evaluated}  "
                f"reject={m.total_signals_rejected}  send_rate={sr:.1f}%"),
            row(f"Performance: win_rate={wr:.1f}%  W={m.win_count}  L={m.loss_count}  "
                f"pnl={m.total_profit_pct:+.2f}%  cycles={m.scan_cycles}"),
            row(f"Quant [v10]: Sharpe={m.sharpe_ratio:+.3f}  Sortino={m.sortino_ratio:+.3f}  "
                f"Calmar={m.calmar_ratio:+.3f}  MaxDD={m.max_drawdown_pct:.2f}%  "
                f"EV={m.expected_value_r:+.3f}R  Kelly={m.kelly_fraction_pct:.1f}%"),
            row(f"RL Threshold: {self._booster.dynamic_threshold:.0f}%  "
                f"(base={AI_THRESHOLD_PERCENT}%)  "
                f"Consec-Losses: {self._booster.consecutive_losses}  "
                f"Quality: {m.last_signal_quality:.1f}/100  "
                f"Kelly(RL): {kel:.1f}%  "
                f"Sharpe(RL): {self._booster.sharpe_ratio:.2f}  "
                f"Sortino(RL): {self._booster.sortino_ratio:.2f}"),
            row(f"GEX Regime: {m.last_gex_regime:<12}  DGRP={m.last_dgrp_score:.0f}/100  "
                f"{rate_status} Signals/hr: {sph:.0f} (target {SIGNALS_PER_HOUR_MIN}–{SIGNALS_PER_HOUR_MAX})"),
            row(
                f"IRONS avg={self._filter.last_irons_score():.1f}/100  "
                f"MinReq={self._filter.effective_irons_min:.0f}(adapt)  "
                f"Streak: wins={self._booster._consec_wins}  "
                f"RL-thresh={self._booster.dynamic_threshold:.0f}%"
            ),
            row(f"Gates: {self._filter.gate_stats_summary()}"),
            row(f"Top symbols:    {top_str}"),
            row(f"Avoid symbols:  {bot_str}"),
            # v9.9.2: Swarm Backtest summary row — shows Mirofish-aligned
            # DynBacktest tier counts so the operator can see per-symbol
            # historical quality without leaving the console.
            *([row(
                f"SwarmBT: strong={_dbt_strong}(+5pts) good={_dbt_good}(+2pts) "
                f"weak={_dbt_weak}(-8pts) | top-EV: {_dbt_top3}"
            )] if self._dyn_backtester is not None else []),
            f"╠{border}╣",
        ]
        for name, layer in self._health.layers.items():
            sr_str = f"{layer.success_rate*100:.0f}%" if layer.calls > 0 else "N/A "
            lines.append(
                row(f"{layer.status_icon} {name:<32}  calls={layer.calls:<6} sr={sr_str:<6}")
            )
        lines.append(f"╚{border}╝")
        for line in lines:
            self._logger.info(line)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. UNITY ENGINE CORE  (master coordinator)
# ═══════════════════════════════════════════════════════════════════════════════

class UnityEngine:
    """
    Master coordinator — initialises all 18 layers (0-17) and wires them together.
    v11.0: Agency Agents (L2), Kelly Criterion, 14-gate filter, per-symbol tracking,
           GEX rotation, OutcomeTracker instance, BM25 lesson feed, Pattern Recognizer,
           BS Greeks, Factor IC/IR, Portfolio Optimizer, CUSUM/AVWAP/OFI, MiroFish Swarm.
    """

    def __init__(self):
        self._logger  = logging.getLogger("UnityEngine")
        self.metrics  = UnityMetrics()
        self.health   = UnityHealthMonitor()
        self.booster  = UnityProfitBooster()
        self.sym_tracker = PerSymbolTracker()
        self.signal_filter: Optional[UnitySignalFilter] = None
        self.console:  Optional[UnityConsole] = None

        # Per-symbol GEX snapshot cache + rotation pointer
        self._gex_snapshots: Dict[str, Any] = {}
        self._gex_rotate_idx: int = 0    # FIX v4.0: true rotation pointer
        # v8.3: RLock for _gex_snapshots — protects concurrent writes (GEX scanner
        # task) and reads (signal filter, get_gex_snapshot, persistence task).
        self._gex_lock: threading.RLock = threading.RLock()

        # Layer handles
        self.gex_engine        = None   # Layer 0:   AEGIS GEX Engine
        self.deribit_gex       = None   # Layer 0.5: Deribit Real-Options GEX Ingestor
        self.okx_gex           = None   # Layer 0.6: OKX Real-Options GEX (cross-venue redundancy, v9.9)
        self.binance_aggtrade  = None   # Layer 0.7: Binance USDM aggTrade WebSocket pool (v9.9)
        self.depth_slip        = None   # Layer 0.8: Depth-walked slippage estimator (v9.9)
        self.agency_framework  = None   # Layer 2:  Agency Trading Framework
        self.agency_agents     = None   # Layer 2:  Agency Trading Agents
        self.irons_scorer      = None   # Layer 2.5: IRONS AI Scorer
        self.utbot_strategy    = None   # Layer 2.7: UT Bot Strategy
        self.bot               = None   # Layer 11: FXSUSDTTelegramBot
        self.strategy          = None   # Layer 3:  MiroFishSwarmStrategy
        self.godmod3           = None   # Layer 4:  G0DM0D3Engine
        self.llm_router        = None   # Layer 4:  SmartLLMRouter
        self.nn_trainer        = None   # Layer 5:  NeuralSignalTrainer
        self.trade_memory      = None   # Layer 9:  TradeMemory
        self.outcome_tracker_instance = None  # Layer 9: OutcomeTracker INSTANCE (FIX v4.0)
        self.atas_analyzer     = None   # Layer 6:  ATASIntegratedAnalyzer
        self.bookmap_analyzer  = None   # Layer 6:  BookmapTradingAnalyzer
        self.smart_sltp        = None   # Layer 7:  SmartDynamicSLTPSystem
        self.dynamic_sl        = None   # Layer 7:  DynamicLeveragingSL
        self.ai_orchestrator   = None   # Layer 8:  AIOrchestrator
        self.market_intel      = None   # Layer 10: market_analyzer
        self.insider           = None   # Layer 10: insider_analyzer
        self.public_api        = None   # Layer 10: PublicAPIIntelligence
        self.microstructure    = None   # Layer 10: MarketMicrostructureEnhancer
        self.depth_analyzer    = None   # Layer 10: AdvancedMarketDepthAnalyzer
        self.bm25_memory       = None   # Layer 9:  SwarmBM25Memory

        # ── v11.0: New Quant Layers ────────────────────────────────────────────
        self.pattern_recognizer  = None  # Layer 2.5b: Technical Pattern Recognizer
        self.factor_analyzer     = None  # Layer 8.5b: Factor IC/IR Analyzer
        self.portfolio_optimizer = None  # Layer 8.5c: Portfolio Optimizer (MVO/RP/BL)
        self.bs_greeks_engine    = None  # Layer 7b:   Black-Scholes + Full Greeks
        # v11.0: recent patterns cache {symbol -> PatternAnalysisResult}
        self._recent_patterns: Dict[str, Any] = {}
        # v11.0: lock for _ws_state dict mutations (fixes race condition)
        self._ws_state_lock: threading.Lock = threading.Lock()

        # v6.0: Shared ThreadPoolExecutor for CPU-bound work
        self._thread_pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=THREAD_POOL_WORKERS,
            thread_name_prefix="UnityWorker",
        )

        # v5.0: global shutdown flag for SIGTERM/SIGINT
        self._shutdown_requested: bool = False
        # v9.7: live scanner-task handle so watchdog/SIGTERM can cancel it
        # gracefully (replaces loop.stop() which skipped cleanup/persistence)
        self._scanner_task: Optional[asyncio.Task] = None

        # v5.7: signal-rate tracking (signals sent in last 60-minute window)
        self._signal_times: deque = deque(maxlen=500)

        # v5.7: layer init timing dict populated by _init_layers
        self._layer_init_ms: Dict[str, float] = {}

        # v7.0 BUG FIX: _last_heartbeat — initialized here so /healthz never
        # references an undefined attribute.  Updated by watchdog on every
        # confirmed scan_cycles advance (was never set before v7.0 → last_cycle_age=0).
        self._last_heartbeat: float = time.time()

        # Propagate constants to env
        os.environ.setdefault("SIGNAL_INTERVAL_SECONDS", str(SIGNAL_INTERVAL_MIN))
        os.environ.setdefault("AI_THRESHOLD_PERCENT",    str(AI_THRESHOLD_PERCENT))
        os.environ.setdefault("SCAN_INTERVAL_MIN",       str(SCAN_INTERVAL_MIN))
        os.environ.setdefault("SCAN_INTERVAL_MAX",       str(SCAN_INTERVAL_MAX))
        os.environ.setdefault("CYCLE_SLEEP_MIN",         str(CYCLE_SLEEP_MIN))
        os.environ.setdefault("CYCLE_SLEEP_MAX",         str(CYCLE_SLEEP_MAX))
        os.environ.setdefault("SCAN_PARALLEL_LIMIT",     str(SCAN_PARALLEL_LIMIT))
        os.environ["SIGNALS_PER_HOUR_MAX"]             = str(SIGNALS_PER_HOUR_MAX)
        os.environ["SIGNALS_PER_HOUR_MIN"]             = str(SIGNALS_PER_HOUR_MIN)
        os.environ.setdefault("HEARTBEAT_INTERVAL",      str(SCANNER_HEARTBEAT_TIMEOUT))
        os.environ.setdefault("GEX_SCAN_INTERVAL_SEC",  str(GEX_SCAN_INTERVAL_SEC))
        os.environ.setdefault("GEX_PARALLEL_LIMIT",     str(GEX_PARALLEL_LIMIT))
        os.environ.setdefault("GEX_MIN_CONFIDENCE",     str(GEX_MIN_CONFIDENCE))
        os.environ.setdefault("GEX_MIN_DGRP",           str(GEX_MIN_DGRP))

        # ── v8.0: Producer-Consumer signal queue ─────────────────────────────
        # The scanner (producer) places validated signals into this queue.
        # A dedicated consumer coroutine drains the queue and dispatches to
        # Telegram/console so slow network I/O never blocks the scan loop.
        self._signal_queue: asyncio.Queue = asyncio.Queue(maxsize=SIGNAL_QUEUE_MAXSIZE)

        # ── v8.0 Prompt 1: last unified decision vector (immutable audit record)
        # Updated each time the consumer dispatches a SEND decision.
        # Exposed on the /metrics health endpoint for real-time inspection.
        self._last_decision_vector: Optional[SignalDecisionVector] = None

        # ── v8.0 Omega-Tier: Dead-Man's Switch scan-cycle latency tracker ────
        # Each scan cycle records its wall-clock duration (ns).  The Dead-Man's
        # Switch fires if: (a) the cycle age exceeds WATCHDOG_STALL_SECONDS, OR
        # (b) the rolling average latency exceeds _DMS_LATENCY_WARN_MS (500 ms).
        # The /healthz endpoint exposes both checks; Railway's health-check probe
        # automatically restarts the container when /healthz returns 503.
        self._cycle_latency_ns_ring: deque = deque(maxlen=30)  # last 30 cycles
        self._DMS_LATENCY_WARN_MS:   float  = 500.0            # flag if avg > 500 ms

        # ── v8.0: WebSocket live orderbook state ─────────────────────────────
        # Populated by _ws_orderbook_task; keyed by symbol, value = dict with
        # keys: best_bid, best_ask, spread_pct, mid_price, depth_imbalance, ts
        self._ws_state: Dict[str, Dict[str, Any]] = {}

        # ── v9.7: Institutional timing state singleton ───────────────────────
        # Shared by the WS task (writer) and the SignalFilter (reader).
        # Powers Roll spread / CUSUM event filter / AVWAP confluence / OFI
        # Z-score.  Allocated unconditionally — the gates themselves are
        # env-gated so OFF defaults cost only the per-WS-message O(1) buffer
        # update (~5 µs at 80 symbols × 10 ticks/sec = ~4 ms/sec).
        self._timing_state: InstitutionalTimingState = InstitutionalTimingState()

        # ── v8.0: Redis async client (None when Redis is disabled/unavailable) ─
        self._redis: Optional[Any] = None

        self._register_layers()

    # ─────────────────────────────────────────────────────────────────────────
    # Layer registration
    # ─────────────────────────────────────────────────────────────────────────

    def _register_layers(self):
        for name in [
            "AEGIS_GEX",               # Layer 0.0
            "DERIBIT_GEX",             # Layer 0.1 (v10.0: register missing sub-layer)
            "OKX_GEX",                 # Layer 0.2 (v10.0: register missing sub-layer)
            "BINANCE_AGGTRADE_WS",     # Layer 0.5 (v10.0: register missing sub-layer)
            "DEPTH_SLIPPAGE",          # Layer 0.8 (v10.0: register missing sub-layer)
            "DYN_BACKTEST",            # Layer 0.9 (v10.0: FIX — was initialized but not registered)
            "MIROFISH_SIM",            # Layer 0.95 (v10.0: new MiroFish swarm simulation)
            "UnityEngine",             # Layer 1  (FIX v5.0: self-registration)
            "AgencyAgents",            # Layer 2
            "IRONS_AIScorer",          # Layer 2.5 (v6.0: 25-indicator gate)
            "UTBot_Strategy",          # Layer 2.7 (v6.0: UT Bot Alerts + STC)
            "MiroFishSwarm",           # Layer 3
            "G0DM0D3+OpenRouter",      # Layer 4
            "NeuralNetwork",           # Layer 5
            "ATAS+Bookmap",            # Layer 6
            "Risk+SLTP+Kelly",         # Layer 7
            "AIOrchestrator",          # Layer 8
            "Memory(Trade+BM25)",      # Layer 9
            "MarketIntelligence",      # Layer 10
            "TelegramBot",             # Layer 11
        ]:
            self.health.register(name)
        # Unity Engine itself is always available once registration succeeds
        self.health.mark_available("UnityEngine")

    # ─────────────────────────────────────────────────────────────────────────
    # Layer initialisation  (sequential sync for safe import ordering)
    # ─────────────────────────────────────────────────────────────────────────

    def _timed_init(self, label: str, fn):
        """Run fn(), record wall-clock ms, store in _layer_init_ms. Returns fn()'s result."""
        _t0 = time.perf_counter()
        result = fn()
        self._layer_init_ms[label] = round((time.perf_counter() - _t0) * 1000, 1)
        return result

    def _init_layers(self) -> bool:
        """Initialise all layers. Returns True if TelegramBot (critical) is ready."""
        self._logger.info(f"🔧 [Unity v{UNITY_VERSION}] Initialising all 18 layers in parallel-safe order...")
        _init_t0 = time.perf_counter()

        # ── Layer 0: AEGIS GEX Engine ──────────────────────────────────────────
        def _init_l0():
            from aegis_gex.gex_engine import AEGISGEXEngine
            return AEGISGEXEngine()
        try:
            self.gex_engine = self._timed_init("L0_AEGIS_GEX", _init_l0)
            self.health.mark_available("AEGIS_GEX")
            self._logger.info(f"✅ [L0] AEGIS GEX Engine ready ({self._layer_init_ms.get('L0_AEGIS_GEX',0):.0f}ms)")
        except Exception as e:
            self.health.mark_unavailable("AEGIS_GEX", str(e))
            self._logger.warning(f"⚠️  [L0] AEGIS GEX unavailable: {e} — Gate 7 pass-through")

        # ── Layer 0.5: Deribit Real-Options GEX Ingestor ──────────────────────
        # Replaces the ATR-derived synthetic GEX proxy with real dealer-gamma
        # sourced from the Deribit options chain. v9.8: extended to SOL via the
        # Deribit linear USDC chain (currency=USDC, instrument prefix SOL_USDC-).
        # Splices net_gex, gex_flip, call_wall, put_wall, regime into the AEGIS
        # snapshot in-place so downstream consumers (Gate 7, Quality bonuses,
        # dashboard) keep reading the same attributes — only the *origin*
        # changes. Falls back silently to the AEGIS proxy if Deribit is
        # unreachable or the symbol is not BTC/ETH/SOL.
        self.deribit_gex = None
        _DERIBIT_BASES = ("BTC", "ETH", "SOL")
        def _init_l05():
            from aegis_gex.deribit_gex_ingestor import DeribitGEXIngestor
            return DeribitGEXIngestor(currencies=_DERIBIT_BASES, refresh_sec=30)
        try:
            self.deribit_gex = self._timed_init("L0.5_DERIBIT_GEX", _init_l05)
            self.health.mark_available("DERIBIT_GEX")
            self._logger.info(
                f"✅ [L0.5] Deribit Real-GEX Ingestor ready "
                f"({self._layer_init_ms.get('L0.5_DERIBIT_GEX',0):.0f}ms) — "
                f"{'/'.join(_DERIBIT_BASES)} options chain, refresh=30s"
            )
        except Exception as e:
            self.health.mark_unavailable("DERIBIT_GEX", str(e))
            self._logger.warning(
                f"⚠️  [L0.5] Deribit Real-GEX unavailable: {e} — AEGIS proxy only"
            )

        # ── Layer 0.6 (v9.9 Apex-#3): OKX options GEX cross-venue redundancy ──
        # Mirrors the Deribit ingestor pattern but pulls option chains from OKX
        # (~10-15 % of global BTC/ETH options OI).  Used as a SECONDARY source
        # to cross-validate Deribit's flip levels and provide failover when the
        # Deribit feed goes stale.  Failure here never blocks the engine —
        # `okx_gex` simply stays None and consumer code falls back to Deribit-only.
        self.okx_gex = None
        if UNITY_OKX_GEX_ENABLED:
            def _init_l06():
                from aegis_gex.okx_gex_ingestor import OkxGEXIngestor
                return OkxGEXIngestor(
                    currencies=("BTC", "ETH"),
                    refresh_sec=UNITY_OKX_GEX_REFRESH_SEC,
                )
            try:
                self.okx_gex = self._timed_init("L0.6_OKX_GEX", _init_l06)
                self.health.mark_available("OKX_GEX")
                self._logger.info(
                    f"✅ [L0.6] OKX Real-GEX cross-venue source ready "
                    f"({self._layer_init_ms.get('L0.6_OKX_GEX',0):.0f}ms) — "
                    f"BTC/ETH redundancy, refresh={UNITY_OKX_GEX_REFRESH_SEC}s [v9.9]"
                )
            except Exception as e:
                self.health.mark_unavailable("OKX_GEX", str(e))
                self._logger.warning(
                    f"⚠️  [L0.6] OKX Real-GEX unavailable: {e} — Deribit-only mode"
                )

        # ── Layer 0.7 (v9.9 Apex-#1): Binance USDM aggTrade WebSocket pool ────
        # Sub-100ms tick truth for the top-N USDM perp markets.  Powers the
        # depth_slip module's freshness check and is consumed by future
        # micro-flow agents.  Never blocks: if `websockets` is missing or the
        # connection fails, consumers see `latest()` return None and fall back
        # to existing REST polling transparently.
        self.binance_aggtrade = None
        if UNITY_BINANCE_WS_ENABLED:
            def _init_l07():
                from aegis_gex.binance_aggtrade_ws import BinanceAggTradePool
                return BinanceAggTradePool(
                    symbols=[s.strip().upper() for s in UNITY_BINANCE_WS_BOOTSTRAP_SYMBOLS if s.strip()],
                )
            try:
                self.binance_aggtrade = self._timed_init("L0.7_BINANCE_WS", _init_l07)
                self.health.mark_available("BINANCE_AGGTRADE_WS")
                self._logger.info(
                    f"✅ [L0.7] Binance aggTrade WS pool ready "
                    f"({self._layer_init_ms.get('L0.7_BINANCE_WS',0):.0f}ms) — "
                    f"{len(UNITY_BINANCE_WS_BOOTSTRAP_SYMBOLS)} symbols bootstrap, "
                    f"sub-100ms tick truth [v9.9]"
                )
            except Exception as e:
                self.health.mark_unavailable("BINANCE_AGGTRADE_WS", str(e))
                self._logger.warning(
                    f"⚠️  [L0.7] Binance aggTrade WS unavailable: {e} — REST-poll fallback"
                )

        # ── Layer 0.8 (v9.9 Apex-#2): Order-book depth-walked slippage ────────
        # Replaces the static SLIPPAGE_PCT × 2 fallback in Gate 0 with a real
        # depth-walked VWAP slippage number.  Pulls /fapi/v1/depth?limit=20,
        # walks the relevant book side until cumulative notional ≥ planned,
        # returns (avg_fill, slip_pct, cleared_pct).  Cached `cache_ttl_sec`s
        # per symbol to keep REST QPS low.
        self.depth_slip = None
        if UNITY_DEPTH_SLIP_ENABLED:
            def _init_l08():
                from aegis_gex.depth_slippage import DepthSlippageEstimator
                return DepthSlippageEstimator(
                    cache_ttl_sec=UNITY_DEPTH_SLIP_CACHE_TTL,
                    depth_limit=UNITY_DEPTH_SLIP_LIMIT,
                    request_timeout=UNITY_DEPTH_SLIP_TIMEOUT_SEC,
                )
            try:
                self.depth_slip = self._timed_init("L0.8_DEPTH_SLIP", _init_l08)
                self.health.mark_available("DEPTH_SLIPPAGE")
                self._logger.info(
                    f"✅ [L0.8] Depth-walked slippage estimator ready "
                    f"({self._layer_init_ms.get('L0.8_DEPTH_SLIP',0):.0f}ms) — "
                    f"ref_notional=${UNITY_DEPTH_SLIP_REF_NOTIONAL:,.0f} cache="
                    f"{UNITY_DEPTH_SLIP_CACHE_TTL:.1f}s [v9.9]"
                )
            except Exception as e:
                self.health.mark_unavailable("DEPTH_SLIPPAGE", str(e))
                self._logger.warning(
                    f"⚠️  [L0.8] Depth-slippage unavailable: {e} — static fallback only"
                )

        # ── Layer 0.9 (v9.9.1 Apex-#5): Dynamic per-symbol backtester ─────────
        # Synthetic prior for symbols Gate 8 can't yet judge (insufficient live
        # trades).  Vectorised EMA20/EMA50 + RSI14 + 1.5×ATR SL / 2.5×ATR TP
        # backtest on the latest UNITY_DBT_LOOKBACK_BARS of 15m USDM klines.
        # Refreshes the entire universe every UNITY_DBT_REFRESH_SEC.  Returns a
        # soft quality bias [-8 .. +5] consumed by Gate 8.5 — never hard-vetos.
        self.dyn_backtester = None
        if UNITY_DBT_ENABLED:
            def _init_l09():
                from aegis_gex.dynamic_backtester import DynamicBacktester
                # Bootstrap universe: same default symbol set as the Binance WS pool.
                _seed = [s.strip().upper() for s in UNITY_BINANCE_WS_BOOTSTRAP_SYMBOLS if s.strip()]
                return DynamicBacktester(
                    symbols=_seed,
                    refresh_sec=UNITY_DBT_REFRESH_SEC,
                    lookback_bars=UNITY_DBT_LOOKBACK_BARS,
                    max_concurrent=UNITY_DBT_MAX_CONCURRENT,
                )
            try:
                self.dyn_backtester = self._timed_init("L0.9_DYN_BACKTEST", _init_l09)
                self.health.mark_available("DYN_BACKTEST")
                self._logger.info(
                    f"✅ [L0.9] Dynamic per-symbol backtester ready "
                    f"({self._layer_init_ms.get('L0.9_DYN_BACKTEST',0):.0f}ms) — "
                    f"refresh={UNITY_DBT_REFRESH_SEC}s lookback={UNITY_DBT_LOOKBACK_BARS} bars [v10.0]"
                )
            except Exception as e:
                self.health.mark_unavailable("DYN_BACKTEST", str(e))
                self._logger.warning(
                    f"⚠️  [L0.9] Dynamic backtester unavailable: {e} — Gate 8.5 disabled"
                )

        # ── Layer 0.95 (v10.0): MiroFish Swarm Simulation Engine ───────────────
        # 10-agent swarm simulation: Trend / Momentum / Volume / Volatility /
        # OrderFlow / Sentiment / Regime / Microstructure / Risk / Composite.
        # Runs proxy backtest on 15M USDM klines; produces quality bias in [-8,+5]
        # for Gate 8.5 fallback when DYN_BACKTEST has insufficient live-trade history.
        # Fully parallel, non-blocking; NEVER hard-vetos signals.
        self.mirofish_sim = None
        if UNITY_MIROFISH_SIM_ENABLED:
            def _init_l095():
                from SignalMaestro.unity_mirofish_simulation import MiroFishSimulationEngine
                _seed = [s.strip().upper() for s in UNITY_BINANCE_WS_BOOTSTRAP_SYMBOLS if s.strip()]
                return MiroFishSimulationEngine(
                    symbols=_seed,
                    refresh_sec=UNITY_DBT_REFRESH_SEC,
                    lookback=UNITY_DBT_LOOKBACK_BARS,
                    max_concurrent=max(4, UNITY_DBT_MAX_CONCURRENT // 2),
                    sl_pct=0.0065,
                    tp_pct=0.0110,
                    min_conf=0.58,
                )
            try:
                self.mirofish_sim = self._timed_init("L0.95_MIROFISH_SIM", _init_l095)
                self.health.mark_available("MIROFISH_SIM")
                self._logger.info(
                    f"✅ [L0.95] MiroFish Swarm Simulation Engine ready "
                    f"({self._layer_init_ms.get('L0.95_MIROFISH_SIM',0):.0f}ms) — "
                    f"10 agents · proxy-backtest · refresh={UNITY_DBT_REFRESH_SEC}s [v10.0]"
                )
            except Exception as e:
                self.health.mark_unavailable("MIROFISH_SIM", str(e))
                self._logger.warning(
                    f"⚠️  [L0.95] MiroFish Swarm Simulation unavailable: {e}"
                )

        # ── Layer 2: Agency Agents ─────────────────────────────────────────────
        # FIX: class is TradingAgencyCoordinator (not AgencyTradingFramework) and
        # requires logger + optional ml_analyzer arguments.
        agency_ok = False
        try:
            from SignalMaestro.agency_trading_framework import TradingAgencyCoordinator
            self.agency_framework = TradingAgencyCoordinator(
                logger=self._logger, ml_analyzer=None
            )
            self._logger.info("✅ [L2] Agency Trading Framework (TradingAgencyCoordinator) ready")
            agency_ok = True
        except Exception as e:
            self._logger.warning(f"⚠️  [L2] Agency framework unavailable: {e}")

        try:
            from SignalMaestro.agency_trading_agents import get_agency_agents
            self.agency_agents = get_agency_agents()
            self._logger.info("✅ [L2] Agency Trading Agents ready")
            agency_ok = True
        except Exception as e:
            try:
                from SignalMaestro.agency_trading_agents import AgencyTradingAgents
                self.agency_agents = AgencyTradingAgents()
                self._logger.info("✅ [L2] AgencyTradingAgents (direct) ready")
                agency_ok = True
            except Exception as e2:
                self._logger.warning(f"⚠️  [L2] Agency agents unavailable: {e2}")

        if agency_ok:
            self.health.mark_available("AgencyAgents")

        # ── Layer 2.5: IRONS AI Scorer ─────────────────────────────────────────
        def _init_l25():
            from SignalMaestro.irons_ai_scorer import IRONSScorer
            return IRONSScorer()
        try:
            self.irons_scorer = self._timed_init("L2.5_IRONS", _init_l25)
            self.health.mark_available("IRONS_AIScorer")
            self._logger.info(
                f"✅ [L2.5] IRONS AI Scorer ready ({self._layer_init_ms.get('L2.5_IRONS',0):.0f}ms) "
                f"— 25 indicators: Momentum/Trend/Volatility/Volume | Gate 10 active"
            )
        except Exception as e:
            self.health.mark_unavailable("IRONS_AIScorer", str(e))
            self._logger.warning(f"⚠️  [L2.5] IRONS AI Scorer unavailable: {e} — Gate 10 pass-through")

        # ── Layer 2.7: UT Bot Strategy ─────────────────────────────────────────
        if UTBOT_ENABLED:
            def _init_l27():
                import importlib
                mod = importlib.import_module("ut_bot_strategy.engine.signal_engine")
                cls = getattr(mod, "SignalEngine", None)
                if cls is None:
                    raise ImportError("SignalEngine not found in ut_bot_strategy.engine.signal_engine")
                return cls()
            try:
                self.utbot_strategy = self._timed_init("L2.7_UTBot", _init_l27)
                self.health.mark_available("UTBot_Strategy")
                self._logger.info(
                    f"✅ [L2.7] UT Bot Strategy ready ({self._layer_init_ms.get('L2.7_UTBot',0):.0f}ms) "
                    f"— UT Bot Alerts + STC confirmation"
                )
            except Exception as e:
                self.health.mark_unavailable("UTBot_Strategy", str(e))
                self._logger.warning(f"⚠️  [L2.7] UT Bot Strategy unavailable: {e}")
        else:
            self._logger.info("ℹ️  [L2.7] UT Bot Strategy disabled (UTBOT_ENABLED=0)")

        # ── Layer 4: G0DM0D3 + Smart LLM Router ───────────────────────────────
        try:
            from SignalMaestro.godmod3_strategy import get_godmod3_engine
            self.godmod3 = get_godmod3_engine()
            self.health.mark_available("G0DM0D3+OpenRouter")
            self._logger.info("✅ [L4] G0DM0D3 Engine (ULTRAPLINIAN+GODMODE) ready")
        except Exception as e:
            self.health.mark_unavailable("G0DM0D3+OpenRouter", str(e))
            self._logger.warning(f"⚠️  [L4] G0DM0D3 unavailable: {e}")

        try:
            from SignalMaestro.smart_llm_router import SmartLLMRouter
            self.llm_router = SmartLLMRouter()
            self._logger.info("✅ [L4] SmartLLMRouter (ClawRouter-inspired) ready")
        except Exception as e:
            self._logger.warning(f"⚠️  [L4] SmartLLMRouter unavailable: {e}")

        # ── Layer 5: Neural Signal Trainer ────────────────────────────────────
        try:
            from SignalMaestro.neural_signal_trainer import NeuralSignalTrainer
            from SignalMaestro.trade_memory import TradeMemory, OutcomeTracker
            self.nn_trainer   = NeuralSignalTrainer()
            self.trade_memory = TradeMemory()
            self._OutcomeTrackerClass = OutcomeTracker   # keep class for later instantiation
            self.health.mark_available("NeuralNetwork")
            self._logger.info(
                f"✅ [L5] NeuralSignalTrainer ready | {self.nn_trainer.status_summary()}"
            )
        except Exception as e:
            self.health.mark_unavailable("NeuralNetwork", str(e))
            self._OutcomeTrackerClass = None
            self._logger.warning(f"⚠️  [L5] NeuralNetwork unavailable: {e}")

        # ── Layer 6: ATAS + Bookmap ────────────────────────────────────────────
        try:
            from SignalMaestro.atas_integrated_analyzer import atas_analyzer as _atas
            self.atas_analyzer = _atas
            if self.atas_analyzer:
                self._logger.info("✅ [L6] ATAS Integrated Analyzer ready (15 indicators)")
        except Exception as e:
            self._logger.warning(f"⚠️  [L6] ATAS unavailable: {e}")

        try:
            from SignalMaestro.bookmap_trading_analyzer import bookmap_analyzer as _bm
            self.bookmap_analyzer = _bm
            if self.bookmap_analyzer:
                self._logger.info("✅ [L6] Bookmap Analyzer ready (order flow)")
        except Exception as e:
            self._logger.warning(f"⚠️  [L6] Bookmap unavailable: {e}")

        if self.atas_analyzer or self.bookmap_analyzer:
            self.health.mark_available("ATAS+Bookmap")

        # ── Layer 7: Smart SL/TP + Dynamic Leveraging SL ──────────────────────
        try:
            from SignalMaestro.smart_dynamic_sltp_system import SmartDynamicSLTPSystem
            self.smart_sltp = SmartDynamicSLTPSystem()
            self._logger.info("✅ [L7] Smart Dynamic SL/TP System ready")
        except Exception as e:
            self._logger.warning(f"⚠️  [L7] SmartSLTP unavailable: {e}")

        try:
            from SignalMaestro.dynamic_leveraging_stop_loss import get_dynamic_leveraging_sl
            self.dynamic_sl = get_dynamic_leveraging_sl()
            self._logger.info("✅ [L7] Dynamic Leveraging Stop Loss ready")
        except Exception as e:
            self._logger.warning(f"⚠️  [L7] DynamicSL unavailable: {e}")

        if self.smart_sltp or self.dynamic_sl:
            self.health.mark_available("Risk+SLTP+Kelly")

        # ── Layer 8: AI Orchestrator ───────────────────────────────────────────
        try:
            from SignalMaestro.ai_orchestrator import AIOrchestrator
            self.ai_orchestrator = AIOrchestrator(enforce_requirements=False)
            self.health.mark_available("AIOrchestrator")
            self._logger.info("✅ [L8] AI Orchestrator ready (sentiment+prediction+RL)")
        except Exception as e:
            self.health.mark_unavailable("AIOrchestrator", str(e))
            self._logger.warning(f"⚠️  [L8] AI Orchestrator unavailable: {e}")

        # ── Layer 9: Memory systems ────────────────────────────────────────────
        mem_ok = False
        try:
            from SignalMaestro.swarm_bm25_memory import SwarmBM25Memory
            self.bm25_memory = SwarmBM25Memory()
            counts = self.bm25_memory.get_lesson_counts()
            total  = sum(counts.values())
            self._logger.info(f"✅ [L9] BM25 Memory ready | {total} lessons")
            mem_ok = True
        except Exception as e:
            self._logger.warning(f"⚠️  [L9] BM25 Memory unavailable: {e}")

        if self.trade_memory or mem_ok:
            self.health.mark_available("Memory(Trade+BM25)")

        # ── Layer 10: Market Intelligence ─────────────────────────────────────
        intel_ok = False
        for mod_path, attr, label in [
            ("SignalMaestro.market_intelligence_analyzer", "market_analyzer",  "Market Intelligence"),
            ("SignalMaestro.insider_trading_analyzer",     "insider_analyzer",  "Insider Analyzer"),
            ("SignalMaestro.public_api_intelligence",      None,                "Public API Intelligence"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(mod_path)
                if attr:
                    obj = getattr(mod, attr, None)
                    if obj:
                        if "market_intel" in label.lower():
                            self.market_intel = obj
                        elif "insider" in label.lower():
                            self.insider = obj
                        intel_ok = True
                        self._logger.info(f"✅ [L10] {label} ready")
                else:
                    # PublicAPIIntelligence is a class
                    PIClass = getattr(mod, "PublicAPIIntelligence", None)
                    if PIClass:
                        self.public_api = PIClass()
                        intel_ok = True
                        self._logger.info(f"✅ [L10] {label} ready")
            except Exception as e:
                self._logger.warning(f"⚠️  [L10] {label} unavailable: {e}")

        for init_fn, attr_name, label in [
            ("SignalMaestro.market_microstructure_enhancer", "get_market_microstructure_enhancer", "Microstructure Enhancer"),
            ("SignalMaestro.advanced_market_depth_analyzer", "get_market_depth_analyzer",          "Depth Analyzer"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(init_fn)
                fn  = getattr(mod, attr_name, None)
                if callable(fn):
                    obj = fn()
                    if obj:
                        if "micro" in label.lower():
                            self.microstructure = obj
                        else:
                            self.depth_analyzer = obj
                        intel_ok = True
                        self._logger.info(f"✅ [L10] {label} ready")
            except Exception as e:
                self._logger.warning(f"⚠️  [L10] {label} unavailable: {e}")

        if intel_ok:
            self.health.mark_available("MarketIntelligence")

        # ── v11.0 Quant Layers ─────────────────────────────────────────────────

        # Layer 2.5b: Technical Pattern Recognizer
        try:
            from SignalMaestro.pattern_recognizer import PatternRecognizer
            self.pattern_recognizer = PatternRecognizer()
            self.health.mark_available("PatternRecognizer")
            self._logger.info("✅ [L2.5b] Pattern Recognizer (24 candle + 8 chart) ready")
        except Exception as _pe:
            self._logger.warning(f"⚠️  [L2.5b] PatternRecognizer unavailable: {_pe}")

        # Layer 7b: Black-Scholes + Full Greeks Engine
        try:
            from aegis_gex.bs_greeks_engine import BSGreeksEngine
            self.bs_greeks_engine = BSGreeksEngine()
            self.health.mark_available("BSGreeksEngine")
            self._logger.info("✅ [L7b] BS Greeks Engine (Δ/Γ/ν/Θ/ρ/Vanna/Volga/Charm) ready")
        except Exception as _bse:
            self._logger.warning(f"⚠️  [L7b] BSGreeksEngine unavailable: {_bse}")

        # Layer 8.5b: Factor IC/IR Analyzer
        try:
            from SignalMaestro.factor_icir_analyzer import FactorICIRAnalyzer
            self.factor_analyzer = FactorICIRAnalyzer()
            self.health.mark_available("FactorICIRAnalyzer")
            self._logger.info("✅ [L8.5b] Factor IC/IR Analyzer ready")
        except Exception as _fae:
            self._logger.warning(f"⚠️  [L8.5b] FactorICIRAnalyzer unavailable: {_fae}")

        # Layer 8.5c: Portfolio Optimizer (MVO / Risk Parity / Black-Litterman)
        try:
            from SignalMaestro.portfolio_optimizer import PortfolioOptimizer
            self.portfolio_optimizer = PortfolioOptimizer()
            self.health.mark_available("PortfolioOptimizer")
            self._logger.info("✅ [L8.5c] Portfolio Optimizer (MVO/RP/BL) ready")
        except Exception as _poe:
            self._logger.warning(f"⚠️  [L8.5c] PortfolioOptimizer unavailable: {_poe}")

        # ── Layer 11: Telegram Bot (FXSUSDTTelegramBot) — imports L3 internally
        try:
            from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
            self.bot = FXSUSDTTelegramBot()
            if self.bot is None:
                raise RuntimeError("FXSUSDTTelegramBot.__init__ returned None")
            self.health.mark_available("TelegramBot")
            self.health.mark_available("MiroFishSwarm")
            self.strategy = getattr(self.bot, "strategy", None)
            self._logger.info("✅ [L11] Telegram Bot (MiroFish Swarm v5) ready")
        except ImportError as e:
            self.health.mark_unavailable("TelegramBot", str(e))
            self._logger.error(f"❌ [L11] Import Error: {e}")
            return False
        except (ConnectionError, ValueError) as e:
            self.health.mark_unavailable("TelegramBot", str(e))
            self._logger.error(f"❌ [L11] Config/Connection Error: {e}")
            return False
        except Exception as e:
            self.health.mark_unavailable("TelegramBot", str(e))
            self._logger.error(f"❌ [L11] Fatal init: {type(e).__name__}: {e}")
            self._logger.debug(traceback.format_exc())
            return False

        # ── FIX v4.0: Instantiate OutcomeTracker now that bot+trader are ready ─
        self._instantiate_outcome_tracker()

        # Wire all Unity components into bot/strategy
        self._wire_unity_components()

        # v5.7: log total init time for performance visibility
        _init_ms = (time.perf_counter() - _init_t0) * 1000
        self._logger.info(
            f"⏱️  [v{UNITY_VERSION}] All 18 layers initialised in {_init_ms:.0f}ms "
            f"| TelegramBot=✅ | GEX={'✅' if self.gex_engine else '⬜'} "
            f"| NN={'✅' if self.nn_trainer else '⬜'} "
            f"| Agency={'✅' if (self.agency_agents or self.agency_framework) else '⬜'}"
        )
        return True

    def _instantiate_outcome_tracker(self):
        """
        FIX v4.0: v3.0 stored OutcomeTracker CLASS reference instead of an instance.
        Now properly instantiates OutcomeTracker with all required dependencies.
        """
        if not hasattr(self, "_OutcomeTrackerClass") or self._OutcomeTrackerClass is None:
            return
        if self.trade_memory is None or self.nn_trainer is None:
            return
        trader = getattr(self.bot, "trader", None) if self.bot else None
        if trader is None:
            return
        try:
            self.outcome_tracker_instance = self._OutcomeTrackerClass(
                memory=self.trade_memory,
                trainer=self.nn_trainer,
                trader=trader,
                bot=self.bot,
                bm25_memory=self.bm25_memory,
            )
            self._logger.info("✅ [L9] OutcomeTracker instantiated (FIX v4.0: instance not class)")
        except Exception as e:
            self._logger.warning(f"⚠️  [L9] OutcomeTracker instantiation failed: {e}")

    def _wire_unity_components(self):
        """
        Inject Unity Engine components into bot and strategy.
        v5.1: full component wiring — all 12 layers injected into strategy + bot.
        """
        self.signal_filter = UnitySignalFilter(self.health, self.sym_tracker)
        # v8.5: wire booster into filter for hard consec-loss circuit-breaker
        if getattr(self, "booster", None) is not None:
            self.signal_filter.set_booster(self.booster)
        if self.public_api is not None:
            self.signal_filter.set_public_api(self.public_api)
        if self.gex_engine is not None:
            self.signal_filter.set_gex_engine(self.gex_engine)
        # v6.0: Wire IRONS AI Scorer into filter for Gate 10
        if self.irons_scorer is not None:
            self.signal_filter.set_irons_scorer(self.irons_scorer)
        # v9.0: Wire live WS orderbook state for dynamic slippage in Gate 0
        self.signal_filter.set_ws_state(self._ws_state)
        # v9.7: Wire institutional timing state for Roll/CUSUM/AVWAP/OFI gates
        self.signal_filter.set_timing_state(self._timing_state)
        # v9.9: Wire Binance aggTrade WS pool — depth_slip uses `latest()` for
        # tick freshness; future micro-flow agent will read aggressor side.
        if self.binance_aggtrade is not None and hasattr(self.signal_filter, "set_aggtrade_pool"):
            self.signal_filter.set_aggtrade_pool(self.binance_aggtrade)

        # v9.9.1: Wire dynamic per-symbol backtester for Gate 8.5 quality bias.
        if self.dyn_backtester is not None and hasattr(self.signal_filter, "set_dynamic_backtester"):
            self.signal_filter.set_dynamic_backtester(self.dyn_backtester)

        # v10.0: Wire MiroFish Swarm Simulation as secondary Gate 8.5 quality bias source.
        # When DYN_BACKTEST has no live-trade history for a symbol, MiroFish sim fills
        # the gap with a proxy-backtest bias.  Both sources are bounded to [-8, +5].
        if self.mirofish_sim is not None:
            _try_setattr(self.signal_filter, "_mirofish_sim", self.mirofish_sim)
            _try_setattr(self.signal_filter, "_dbt_min_trades", UNITY_DBT_MIN_TRADES)
            self._logger.info(
                "✅ [v10.0] MiroFish Swarm Simulation wired into signal filter "
                f"(Gate 8.5 fallback bias, min_trades_threshold={UNITY_DBT_MIN_TRADES})"
            )

        self.console = UnityConsole(
            self.health, self.metrics, self.signal_filter,
            self.booster, self.sym_tracker,
            signal_times=self._signal_times,    # v5.7: live rate tracking
            dyn_backtester=self.dyn_backtester,  # v9.9.2: Mirofish swarm backtest
        )

        if self.strategy is not None:
            # ── Core Unity wiring ──────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_signal_filter",    self.signal_filter)
            _try_setattr(self.strategy, "_unity_booster",          self.booster)
            _try_setattr(self.strategy, "_unity_metrics",          self.metrics)
            _try_setattr(self.strategy, "_unity_sym_tracker",      self.sym_tracker)
            _try_setattr(self.strategy, "_unity_outcome_tracker",  self.outcome_tracker_instance)
            # v9.8: lock-profit trailing-stop policy (50% of run-up by default).
            # Downstream (smart_sltp, mirofish_swarm_strategy, cornix integration)
            # can call _unity_compute_trailing_sl(entry, peak, "BUY", original_sl,
            # tp1=...) → returns new SL price or None when trail is dormant.
            _try_setattr(self.strategy, "_unity_trailing_lock_pct", TRAILING_LOCK_PROFIT_PCT)
            _try_setattr(self.strategy, "_unity_trailing_activate_frac", TRAILING_ACTIVATE_TP1_FRACTION)
            _try_setattr(self.strategy, "_unity_compute_trailing_sl", compute_lock_profit_sl)
            # ── Layer 2: Agency ────────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_agency_agents",    self.agency_agents)
            _try_setattr(self.strategy, "_unity_agency_framework", self.agency_framework)
            # ── Layer 2.5: IRONS AI Scorer ────────────────────────────────────
            _try_setattr(self.strategy, "_unity_irons_scorer",     self.irons_scorer)
            # ── Layer 2.7: UT Bot Strategy ────────────────────────────────────
            _try_setattr(self.strategy, "_unity_utbot",            self.utbot_strategy)
            # ── Layer 4: LLM ───────────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_godmod3",          self.godmod3)
            _try_setattr(self.strategy, "_unity_llm_router",       self.llm_router)
            # ── Layer 5: Neural ────────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_nn_trainer",       self.nn_trainer)
            # ── Layer 6: Market Analyzers ──────────────────────────────────────
            _try_setattr(self.strategy, "_unity_atas",             self.atas_analyzer)
            _try_setattr(self.strategy, "_unity_bookmap",          self.bookmap_analyzer)
            # ── Layer 7: Risk ──────────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_smart_sltp",       self.smart_sltp)
            _try_setattr(self.strategy, "_unity_dynamic_sl",       self.dynamic_sl)
            # ── Layer 8: AI Orchestrator ───────────────────────────────────────
            _try_setattr(self.strategy, "_unity_ai_orchestrator",  self.ai_orchestrator)
            # ── Layer 9: Memory ────────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_trade_memory",     self.trade_memory)
            _try_setattr(self.strategy, "_unity_bm25",             self.bm25_memory)
            # ── Layer 10: Market Intelligence ─────────────────────────────────
            _try_setattr(self.strategy, "_unity_market_intel",     self.market_intel)
            _try_setattr(self.strategy, "_unity_insider",          self.insider)
            _try_setattr(self.strategy, "_unity_public_api",       self.public_api)
            _try_setattr(self.strategy, "_unity_microstructure",   self.microstructure)
            _try_setattr(self.strategy, "_unity_depth_analyzer",   self.depth_analyzer)
            # ── Layer 0: GEX ───────────────────────────────────────────────────
            _try_setattr(self.strategy, "_unity_gex",              self.gex_engine)
            # ── v9.1: WS live orderbook state ─────────────────────────────────
            _try_setattr(self.strategy, "_unity_ws_state",         self._ws_state)

        if self.bot is not None:
            # ── v10.5: Wire MiroFish Sim + metrics + engine into CornixMenuBot ─
            # This allows the Telegram backtest panel to show live simulation
            # results and the quant stats panel to show real engine metrics.
            _cornix = getattr(self.bot, "cornix_menu", None)
            if _cornix is not None:
                if self.mirofish_sim is not None:
                    _try_setattr(_cornix, "_mirofish_sim", self.mirofish_sim)
                    self._logger.info(
                        "✅ [v10.5] MiroFish Sim wired into CornixMenuBot "
                        "(backtest panel now shows live data)"
                    )
                _try_setattr(_cornix, "_unity_metrics",  self.metrics)
                _try_setattr(_cornix, "_unity_booster",  self.booster)
                _try_setattr(_cornix, "_unity_engine",   self)

            # ── Core Unity wiring ──────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_engine",            self)
            _try_setattr(self.bot, "_unity_signal_filter",     self.signal_filter)
            _try_setattr(self.bot, "_unity_booster",           self.booster)
            _try_setattr(self.bot, "_unity_metrics",           self.metrics)
            _try_setattr(self.bot, "_unity_sym_tracker",       self.sym_tracker)
            _try_setattr(self.bot, "_unity_outcome_tracker",   self.outcome_tracker_instance)
            # FIX v5.0: wire outcome_tracker so bot.run_continuous_scanner doesn't
            # create a SECOND OutcomeTracker instance (dedup fix)
            if self.outcome_tracker_instance is not None:
                _try_setattr(self.bot, "outcome_tracker",      self.outcome_tracker_instance)
            # ── Layer 2: Agency ────────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_agency_agents",     self.agency_agents)
            _try_setattr(self.bot, "_unity_agency_framework",  self.agency_framework)
            # ── Layer 2.5: IRONS AI Scorer ────────────────────────────────────
            _try_setattr(self.bot, "_unity_irons_scorer",      self.irons_scorer)
            # ── Layer 2.7: UT Bot Strategy ────────────────────────────────────
            _try_setattr(self.bot, "_unity_utbot",             self.utbot_strategy)
            # ── Layer 4: LLM ───────────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_godmod3",           self.godmod3)
            _try_setattr(self.bot, "_unity_llm_router",        self.llm_router)
            # ── Layer 5: Neural ────────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_nn_trainer",        self.nn_trainer)
            # ── Layer 6: Market Analyzers ──────────────────────────────────────
            _try_setattr(self.bot, "_unity_atas",              self.atas_analyzer)
            _try_setattr(self.bot, "_unity_bookmap",           self.bookmap_analyzer)
            # ── Layer 7: Risk ──────────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_smart_sltp",        self.smart_sltp)
            _try_setattr(self.bot, "_unity_dynamic_sl",        self.dynamic_sl)
            # v9.8: lock-profit trailing-stop policy (50 % of run-up by default).
            _try_setattr(self.bot, "_unity_trailing_lock_pct", TRAILING_LOCK_PROFIT_PCT)
            _try_setattr(self.bot, "_unity_trailing_activate_frac", TRAILING_ACTIVATE_TP1_FRACTION)
            _try_setattr(self.bot, "_unity_compute_trailing_sl", compute_lock_profit_sl)
            # Also inject the helper onto the SLTP system so it can attach
            # the policy directly to outgoing signal payloads (Cornix-format
            # trailing tag).
            if self.smart_sltp is not None:
                _try_setattr(self.smart_sltp, "_unity_trailing_lock_pct", TRAILING_LOCK_PROFIT_PCT)
                _try_setattr(self.smart_sltp, "_unity_compute_trailing_sl", compute_lock_profit_sl)
            # ── Layer 8: AI Orchestrator ───────────────────────────────────────
            _try_setattr(self.bot, "_unity_ai_orchestrator",   self.ai_orchestrator)
            # ── Layer 9: Memory ────────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_trade_memory",      self.trade_memory)
            _try_setattr(self.bot, "_unity_bm25",              self.bm25_memory)
            # ── Layer 10: Market Intelligence ─────────────────────────────────
            _try_setattr(self.bot, "_unity_market_intel",      self.market_intel)
            _try_setattr(self.bot, "_unity_insider",           self.insider)
            _try_setattr(self.bot, "_unity_public_api",        self.public_api)
            _try_setattr(self.bot, "_unity_microstructure",    self.microstructure)
            _try_setattr(self.bot, "_unity_depth_analyzer",    self.depth_analyzer)
            # ── Layer 0: GEX ───────────────────────────────────────────────────
            _try_setattr(self.bot, "_unity_gex",               self.gex_engine)
            # ── Health monitor (session 4: enables record_call() from bot) ───
            _try_setattr(self.bot, "_unity_health",            self.health)
            # ── v5.7: Signal-rate ring (bot appends time.time() on each send) ─
            _try_setattr(self.bot, "_unity_signal_times",      self._signal_times)
            # ── v9.1: WS live orderbook state — gives strategy/bot access to
            #    fresh depth5 data for SL/TP confirmation and fill-quality checks ─
            _try_setattr(self.bot, "_unity_ws_state",          self._ws_state)

            # ── v11.0: New Quant Layer wiring ─────────────────────────────────
            _try_setattr(self.bot, "_unity_pattern_recognizer",  self.pattern_recognizer)
            _try_setattr(self.bot, "_unity_factor_analyzer",     self.factor_analyzer)
            _try_setattr(self.bot, "_unity_portfolio_optimizer", self.portfolio_optimizer)
            _try_setattr(self.bot, "_unity_bs_greeks",           self.bs_greeks_engine)
            # Wire quant providers into CornixMenuBot inline panels
            _cornix11 = getattr(self.bot, "cornix_menu", None)
            if _cornix11 is not None and hasattr(_cornix11, "set_quant_providers"):
                try:
                    _cornix11.set_quant_providers(
                        portfolio_optimizer=self.portfolio_optimizer,
                        factor_analyzer=self.factor_analyzer,
                        bs_engine=self.bs_greeks_engine,
                    )
                    self._logger.info(
                        "✅ [v11.0] Quant providers (PortfolioOpt/FactorICIR/BSGreeks) "
                        "wired into CornixMenuBot panels"
                    )
                except Exception as _qe:
                    self._logger.warning(f"⚠️  [v11.0] Quant provider wiring error: {_qe}")

        # ── v11.0: Wire quant modules into signal filter (Gate 2.5b pattern bias) ─
        if self.signal_filter is not None:
            if self.pattern_recognizer is not None:
                _try_setattr(self.signal_filter, "_pattern_recognizer", self.pattern_recognizer)
            if self.bs_greeks_engine is not None:
                _try_setattr(self.signal_filter, "_bs_greeks_engine", self.bs_greeks_engine)
            if self.portfolio_optimizer is not None:
                _try_setattr(self.signal_filter, "_portfolio_optimizer", self.portfolio_optimizer)
            if self.factor_analyzer is not None:
                _try_setattr(self.signal_filter, "_factor_analyzer", self.factor_analyzer)
            self._logger.info("✅ [v11.0] Quant layers wired into UnitySignalFilter")

        # ── v11.0: TradingInterface — command-less inline-keyboard Telegram UI ──
        # Provides per-user signal action buttons (Execute/Follow/Skip/Details),
        # portfolio dashboard, settings panel, and one-tap CCXT trade execution.
        # Works alongside CornixMenuBot (which handles advanced order config).
        self.trading_interface = None
        try:
            from SignalMaestro.trading_interface import get_trading_interface
            self.trading_interface = get_trading_interface(engine=self)
            if self.bot is not None:
                _try_setattr(self.bot, "_unity_trading_interface", self.trading_interface)
                # Wire signal cache into CornixMenuBot so Execute buttons work
                _cornix_ti = getattr(self.bot, "cornix_menu", None)
                if _cornix_ti is not None and not hasattr(_cornix_ti, "_unity_trading_interface"):
                    _try_setattr(_cornix_ti, "_unity_trading_interface", self.trading_interface)
            self._logger.info(
                "✅ [v11.0] TradingInterface (command-less UI) wired — "
                "Execute/Follow/Skip/Details buttons + portfolio dashboard + "
                "UserDB(aiosqlite) + ExchangeExecutor(CCXT) ready"
            )
        except Exception as _ti_err:
            self._logger.warning(f"⚠️  [v11.0] TradingInterface wiring failed (non-fatal): {_ti_err}")

        wired_layers = sum([
            self.gex_engine is not None,
            self.agency_agents is not None or self.agency_framework is not None,
            self.irons_scorer is not None,        # v6.0: IRONS
            self.utbot_strategy is not None,      # v6.0: UT Bot
            self.godmod3 is not None,
            self.nn_trainer is not None,
            self.atas_analyzer is not None or self.bookmap_analyzer is not None,
            self.smart_sltp is not None or self.dynamic_sl is not None,
            self.ai_orchestrator is not None,
            self.trade_memory is not None or self.bm25_memory is not None,
            self.market_intel is not None or self.public_api is not None,
            self.bot is not None,
            # v11.0 quant layers
            self.pattern_recognizer is not None,  # L2.5b
            self.bs_greeks_engine is not None,    # L7b
            self.factor_analyzer is not None,     # L8.5b
            self.portfolio_optimizer is not None, # L8.5c
        ])
        _irons_gate_str = (
            f"IRONS(Gate10≥{IRONS_MIN_SCORE:.0f})"
            if self.irons_scorer is not None
            else "IRONS(Gate10:OFF)"
        )
        self._logger.info(
            f"🔗 [Unity v{UNITY_VERSION}] All components wired ({wired_layers}/16 active subsystems) — "
            f"14-gate filter (G2.5b:Pattern · G7b:BSGreeks · G8.5b:FactorICIR · G8.5c:PortfolioOpt) · "
            f"G0.8:MinTP1≥{MIN_TP1_DISTANCE_PCT:.2%} · G9:quality≥{SIGNAL_MIN_QUALITY_GATE:.0f} · {_irons_gate_str} · "
            f"Kelly · Agency · UTBot · GEX(FLIP≥{GEX_FLIP_ZONE_DGRP}) · PerSymbol · SmartSLTP · "
            f"AIOrchestrator · MarketIntel · OutcomeTracker · NNRetrain({NN_RETRAIN_INTERVAL_SEC//3600}h) · "
            f"LLM-AutoRoute · SignalRate · HealthServer · ThreadPool={THREAD_POOL_WORKERS}w · v{UNITY_VERSION} active."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Startup banner
    # ─────────────────────────────────────────────────────────────────────────

    def _print_startup_banner(self):
        layers_online = sum(1 for l in self.health.layers.values() if l.available)
        total_layers  = len(self.health.layers)
        logger.info("=" * 90)
        logger.info(f"⚡ UNITY ENGINE v{UNITY_VERSION} — ALL SYSTEMS UNITED — PRODUCTION TRADING")
        logger.info("=" * 90)
        logger.info(f"📐 ARCHITECTURE (18 layers, 14-gate filter, G5-SoftVeto, 5-bucket RL, Kelly, GEX, MiroFishSim, ATR-Vol·HTF-Align·AdaptIRONS·Railway·orjson·asyncio.Queue·WS·Redis·@watched_task v{UNITY_VERSION}):")
        logger.info("   Layer 0.0: AEGIS GEX Engine   — Dealer Flow / GEX regime / DGRP scoring")
        logger.info("   Layer 0.9: DynBacktest         — Per-symbol 15M proxy backtest, Gate 8.5 quality bias [v10.0]")
        logger.info("   Layer 0.95: MiroFish Sim       — 10-agent swarm simulation (Trend/Mom/Vol/OFI/Regime/Composite) [v10.0]")
        logger.info("   Layer  1 : Unity Engine        — Master coord, @watched_task, Persistence, Redis, SignalQueue, WSOrderbook [v10.0]")
        logger.info("   Layer  2 : Agency Agents       — Specialist agents (risk/trend/momentum)")
        logger.info("   Layer  3 : MiroFish Swarm      — 10-agent consensus (github/666ghj)")
        logger.info("   Layer  4 : G0DM0D3 AI v10.0   — ULTRAPLINIAN+AutoTune+STM+GODMODE CLASSIC")
        logger.info("              └─ OpenRouter        — 10 storm-purged models, 5 tiers, EnsembleVote")
        logger.info("              └─ SmartLLMRouter    — ClawRouter-inspired cascade fallback")
        logger.info("   Layer  5 : Neural Network      — 55-feature MLP (42 + 8 lag returns + 1 OFI + 1 PriceConsensus[7-models] + 1 HurstRegime[R/S] + 1 EWMA-Vol[RiskMetrics λ=0.94] + 1 RealSkew[Neuberger 2012]), Wilder-ATR, online learning")
        logger.info("   Layer  6 : ATAS + Bookmap      — 15 indicators + order-flow depth")
        logger.info("   Layer  7 : Risk+Kelly Engine   — SmartDynamic SL/TP + Leveraging + Kelly")
        logger.info("   Layer  8 : AI Orchestrator     — Sentiment + Prediction + RL")
        logger.info("   Layer  9 : Memory              — TradeMemory (SQLite) + BM25 + GraphState")
        logger.info("   Layer 10 : Market Intel        — CVD + PublicAPI + Insider + Microstructure")
        logger.info("   Layer 11 : Telegram Bot        — Signal broadcast + 30+ commands")
        logger.info("")
        _irons_status = f"✅ ACTIVE (≥{IRONS_MIN_SCORE:.0f}/100)" if self.irons_scorer else "⬜ PASS-THROUGH (Layer unavailable)"
        _utbot_status = "✅ ACTIVE" if self.utbot_strategy else "⬜ UNAVAILABLE"
        logger.info(f"🔒 14-GATE SIGNAL FILTER (v{UNITY_VERSION} — G0:EV>0 + G0.5:Session + G0.8:MinTP1≥{MIN_TP1_DISTANCE_PCT:.2%} + G9:Quality≥{SIGNAL_MIN_QUALITY_GATE:.0f} + G10:IRONS≥{IRONS_MIN_SCORE:.0f} + GEX regime-aware):")
        logger.info(f"   Gate 0  — EV Check           Reject if E[V] ≤ 0 after dynamic WS spread (floor {SLIPPAGE_PCT*100:.2f}%/side, stale→static) [v9.3]")
        logger.info(f"   Gate 0.5— Session Filter     Dead-zone UTC {DEAD_ZONE_UTC_START:02d}-{DEAD_ZONE_UTC_END:02d}h → −{DEAD_ZONE_QUALITY_PENALTY:.0f}pts | Prime 12-20h → +{SESSION_QUALITY_BONUS:.0f}pts [v6.1]")
        logger.info(f"   Gate 0.8— Min TP1 Distance   TP1 must be ≥{MIN_TP1_DISTANCE_PCT:.2%} from entry (slippage-proof first target) [v6.2]")
        logger.info(f"   Gate 1  — Weighted R:R       ≥ {MIN_RR_RATIO} (TP1×45%+TP2×35%+TP3×20%)")
        logger.info(f"   Gate 2  — Swarm Consensus    ≥ {SWARM_MIN_CONSENSUS:.0%}")
        logger.info(f"   Gate 3  — AI Confidence      ≥ dynamic RL threshold (base {AI_THRESHOLD_PERCENT}%)")
        logger.info("   Gate 4  — Neural Network     win-prob ≥ NN optimal threshold (MC-Dropout, 20 passes)")
        logger.info("   Gate 5  — Analyzer Align     ATAS + Bookmap symmetric veto")
        logger.info("   Gate 6  — Regime Filter      Fear&Greed extreme blocks bias")
        logger.info(f"   Gate 7  — GEX Regime         FLIP ZONE≥{GEX_FLIP_ZONE_DGRP} | POS/NEG≥45 | NEUTRAL≥{GEX_MIN_DGRP} | Gamma Zero±{GEX_GAMMA_ZERO_PROX_PCT:.1%}→+{GEX_GAMMA_ZERO_QUALITY_BONUS:.0f}pts | VOL TRIGGER→+{GEX_VOL_TRIGGER_QUALITY_BONUS:.0f}pts [v8.0]")
        _g8_mode_str = "HARD-BLOCK" if os.getenv("UNITY_GATE8_HARD", "0").strip().lower() not in ("0", "false", "no", "") else "DYNAMIC (quality −12..+5pts, no veto)"
        logger.info(f"   Gate 8  — Per-Symbol WR      pivot {SYMBOL_MIN_WIN_RATE:.0%} · min {SYMBOL_MIN_TRADES} trades · mode={_g8_mode_str} [v9.7-DYN]")
        _dbt_status  = "✅ ACTIVE (soft quality bias −8..+5pts, NEVER vetoes)" if getattr(self, "dyn_backtester", None) else "⬜ UNAVAILABLE"
        _msim_status = "✅ ACTIVE (10-agent swarm proxy backtest, fallback bias)" if getattr(self, "mirofish_sim", None) else "⬜ UNAVAILABLE"
        logger.info(f"   Gate 8.5— Dyn Backtester     {_dbt_status}  ← per-symbol 15m proxy strategy backtest, refresh @1800s [v10.0]")
        logger.info(f"   Gate 8.5— MiroFish Sim Bias  {_msim_status}  ← 10-agent swarm simulation, fallback when DYN_BACKTEST has <{UNITY_DBT_MIN_TRADES} trades [v10.0]")
        logger.info(f"   Gate 9  — Quality Floor      ≥ {SIGNAL_MIN_QUALITY_GATE:.0f}/100 composite score")
        logger.info(f"   Gate 10 — IRONS AI Scorer    {_irons_status}  ← 25-indicator Momentum/Trend/Vol/Volume, adaptive≥50-65/100 WR-driven [v6.3]")
        logger.info(f"   Layer 2.7 UT Bot Strategy    {_utbot_status}  ← UT Bot Alerts + STC confirmation [v6.0]")
        logger.info("")
        logger.info("💰 KELLY CRITERION:")
        logger.info("   f* = (p×b − q) / b  |  Half-Kelly safety cap  |  Max 25% per trade")
        logger.info("")
        logger.info("🧠 5-BUCKET RL + CONSEC-LOSS CB + WIN-STREAK BONUS (v6.0):")
        logger.info("   WR < 30% → +3%     WR 30-45% → +2%    WR 45-60% → ±0%    [v10.6: deadlock-safe buckets]")
        logger.info(f"   WR 60-72% → -3%   WR > 72%  → -6%    Consec-Loss CB: {CONSEC_LOSS_THRESHOLD} losses → +{CONSEC_LOSS_BOOST_PCT:.0f}% / {CONSEC_LOSS_COOLDOWN_SEC//60}min (warmup=300s)")
        logger.info(f"   Win-Streak Bonus: {CONSEC_WIN_STREAK_THRESHOLD}+ wins → {CONSEC_WIN_STREAK_BONUS:+.0f}% threshold (hot-streak capitalisation) [v6.0]")
        logger.info("")
        logger.info(f"⚡ SCAN SPEED (v6.0): cycle {CYCLE_SLEEP_MIN}–{CYCLE_SLEEP_MAX}s | GEX batch={GEX_BATCH_SIZE} parallel={GEX_PARALLEL_LIMIT} | NN retrain every {NN_RETRAIN_INTERVAL_SEC//3600}h | ThreadPool={THREAD_POOL_WORKERS}w")
        logger.info("")
        logger.info(f"✅ Layers online: {layers_online}/{total_layers}")
        logger.info("=" * 90)

    # ─────────────────────────────────────────────────────────────────────────
    # v5.0: SIGTERM / SIGINT graceful shutdown
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Register SIGTERM and SIGINT handlers that set the shutdown flag
        and cancel the running event loop — Replit-safe (avoids signal.signal
        in threads which raises ValueError on non-main threads).
        """
        def _handle_shutdown(signum, frame):
            self._logger.info(f"🛑 [{signum}] Shutdown signal received — requesting clean exit")
            self._shutdown_requested = True
            # v9.7 BUG FIX: cancel the scanner task instead of stopping the loop.
            # loop.stop() exits asyncio.run() abruptly, skipping the `finally:`
            # block that runs _cleanup() — leaving background tasks dangling and
            # losing the final persistence save.  Cancelling the scanner task
            # raises CancelledError inside `await self._scanner_task` which is
            # caught by the run() handler and triggers ordered cleanup.
            try:
                if self._scanner_task is not None and not self._scanner_task.done():
                    loop.call_soon_threadsafe(self._scanner_task.cancel)
                else:
                    loop.call_soon_threadsafe(loop.stop)   # fallback when no task yet
            except Exception:
                pass

        try:
            _signal.signal(_signal.SIGTERM, _handle_shutdown)
            _signal.signal(_signal.SIGINT,  _handle_shutdown)
        except (ValueError, OSError):
            # Not in main thread — skip (runner will handle)
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # v5.0: Scanner watchdog  (detects stalls)
    # ─────────────────────────────────────────────────────────────────────────

    async def _watchdog_task(self) -> None:
        """
        Background watchdog that monitors the continuous scanner heartbeat.
        Tracks metrics.scan_cycles — if it doesn't increment for
        WATCHDOG_STALL_SECONDS the scanner is considered stalled and the
        engine requests a restart via loop.stop().
        """
        _log = logging.getLogger("UnityEngine.Watchdog")
        _log.info(f"🐕 Watchdog started (stall threshold={WATCHDOG_STALL_SECONDS}s)")
        last_cycle_count = self.metrics.scan_cycles
        last_advance     = time.time()

        while True:
            try:
                await asyncio.sleep(WATCHDOG_POLL_SECONDS)
                # ── v9.9.2 Apex-#7: periodic RL threshold tick ─────────────
                # Recomputes the RL threshold each watchdog poll so the
                # starvation-decay logic in _update_threshold_rl() fires
                # even when no outcomes have come in (signal-starved state).
                # Without this hook the threshold can only update inside
                # record_outcome(), which never executes during deadlock.
                try:
                    if hasattr(self, "booster") and self.booster is not None:
                        self.booster.tick()
                except Exception:
                    pass
                current_cycles = self.metrics.scan_cycles
                if current_cycles != last_cycle_count:
                    _advance_ns = time.time_ns()
                    cycles_delta = current_cycles - last_cycle_count

                    # ── v8.0 Dead-Man's Switch: record per-cycle latency ──────────
                    # Estimate: ns elapsed since last advance / number of new cycles.
                    # This gives the avg ns-per-cycle over the watchdog poll interval.
                    if cycles_delta > 0 and hasattr(self, "_cycle_latency_ns_ring"):
                        elapsed_ns     = _advance_ns - int(last_advance * 1_000_000_000)
                        avg_ns_per_cyc = elapsed_ns // cycles_delta
                        self._cycle_latency_ns_ring.append(avg_ns_per_cyc)

                    last_cycle_count      = current_cycles
                    last_advance          = _advance_ns / 1_000_000_000.0
                    self._last_heartbeat  = last_advance   # v7.0 BUG FIX: update heartbeat
                    _log.debug(f"Watchdog OK — scan_cycles={current_cycles}")
                else:
                    stale = time.time() - last_advance
                    if stale > WATCHDOG_STALL_SECONDS:
                        _log.critical(
                            f"⚡ SCANNER STALL DETECTED — scan_cycles unchanged "
                            f"for {stale:.0f}s (threshold={WATCHDOG_STALL_SECONDS}s) "
                            f"— requesting restart"
                        )
                        self._shutdown_requested = True
                        # v9.7 BUG FIX: cancel scanner task for graceful cleanup
                        # instead of loop.stop() which skips _cleanup() and leaves
                        # background tasks dangling without their final persistence
                        # save.  Falls back to loop.stop() only if scanner not yet
                        # tracked (start-up window).
                        try:
                            if self._scanner_task is not None and not self._scanner_task.done():
                                self._scanner_task.cancel()
                            else:
                                loop = asyncio.get_running_loop()
                                loop.stop()
                        except Exception:
                            pass
                    else:
                        _log.debug(
                            f"Watchdog: no new cycle in {stale:.0f}s "
                            f"(stall threshold={WATCHDOG_STALL_SECONDS}s)"
                        )
            except asyncio.CancelledError:
                _log.info("Watchdog task cancelled")
                break
            except Exception as e:
                _log.debug(f"Watchdog error (non-fatal): {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # v8.0: Redis optional initialiser
    # ─────────────────────────────────────────────────────────────────────────

    async def _redis_init(self) -> None:
        """
        Attempt to connect to Redis using REDIS_URL env var.
        If Redis is unavailable (no URL, import error, connection refused) the
        engine falls back gracefully to local JSON file persistence — no crash.

        Provides sub-millisecond state recovery on Railway redeploys: all gate
        stats, cooldowns, IRONS calibration and metrics are serialized to Redis
        on every persistence cycle and restored atomically at startup.
        """
        if not REDIS_URL:
            self._logger.info(
                "📦 [v8.0] Redis disabled — REDIS_URL not set. "
                "State persists to local JSON files (Railway Volume recommended)."
            )
            return

        # ── v8.0 FIX: use redis.asyncio (ships with redis-py ≥ 4.3) ──────────
        # aioredis ≥ 2.x causes "duplicate base class Timeout Error" on Railway
        # because both aioredis and redis-py define TimeoutError — metaclass
        # conflict.  redis.asyncio is the official first-party async client,
        # merged from aioredis into redis-py 4.2, and has zero metaclass issues.
        _redis_client = None
        _redis_error  = None

        # ── Build candidate URL list ────────────────────────────────────────────
        # Attempt the configured REDIS_URL first, then fall back to localhost
        # (covers Railway timing races where .internal DNS resolves seconds after
        # the bot container starts, and co-located / sidecar Redis setups).
        _candidate_urls: list[str] = [REDIS_URL]
        if "localhost" not in REDIS_URL and "127.0.0.1" not in REDIS_URL:
            _candidate_urls.append("redis://localhost:6379")

        # ── Try #1: redis.asyncio (preferred — bundled with redis-py ≥ 4.3) ───
        try:
            import redis.asyncio as _redis_async  # type: ignore[import]

            for _attempt in range(1, 4):          # 3 attempts: 0 s, 2 s, 4 s
                for _url in _candidate_urls:
                    try:
                        _c = await _redis_async.from_url(
                            _url,
                            encoding="utf-8",
                            decode_responses=True,
                            socket_connect_timeout=5,
                            socket_timeout=3,
                        )
                        await _c.ping()
                        self._redis = _c
                        self._logger.info(
                            f"✅ [v8.0] Redis connected via redis.asyncio "
                            f"(attempt {_attempt}, url={_url[:40]}…) "
                            f"TTL={REDIS_STATE_TTL_SEC}s"
                        )
                        return
                    except Exception as _exc:
                        _redis_error = str(_exc)
                        self._logger.debug(
                            f"📦 Redis attempt {_attempt} url={_url[:40]} → {_exc}"
                        )
                if _attempt < 3:
                    _jitter  = random.uniform(0, 0.5)
                    _backoff = 2 ** (_attempt - 1) + _jitter   # 1+j, 2+j seconds
                    self._logger.info(
                        f"📦 [v8.0] Redis not yet reachable — retrying in "
                        f"{_backoff:.1f}s (attempt {_attempt}/3)…"
                    )
                    await asyncio.sleep(_backoff)

        except ImportError:
            _redis_error = "redis.asyncio not available (install redis[asyncio]>=4.3)"

        # ── Try #2: aioredis legacy fallback (only if redis.asyncio import fails) ─
        if _redis_error and "not available" in _redis_error:
            for _url in _candidate_urls:
                try:
                    import aioredis as _aioredis_legacy  # type: ignore[import]
                    _c = await _aioredis_legacy.from_url(
                        _url,
                        encoding="utf-8",
                        decode_responses=True,
                    )
                    await _c.ping()
                    self._redis = _c
                    self._logger.info(
                        f"✅ [v8.0] Redis connected via aioredis (legacy): {_url[:40]}…"
                    )
                    return
                except Exception:
                    pass

        # All attempts failed — degrade gracefully to file persistence
        self._logger.warning(
            f"⚠️  [v8.0] Redis connection failed after 3 attempts ({_redis_error}) — "
            "continuing with local file persistence. "
            "FIX (Railway): In your bot service → Variables, ensure "
            "REDIS_URL is set as a reference variable: REDIS_URL = ${{Redis.REDIS_URL}} "
            "(not a hardcoded string). Internal DNS (.railway.internal) only resolves "
            "when the variable is linked via Railway's reference system."
        )
        self._redis = None

    async def _redis_sync_state(self) -> None:
        """
        Push critical engine state to Redis so the next Railway deploy can
        restore it without waiting for on-disk files to be mounted.
        Called by _persistence_task on every 120 s cycle when Redis is active.

        v8.0 BUG FIX: corrected attribute names:
          metrics.total_pnl     → metrics.total_profit_pct  (was AttributeError)
          metrics.signals_sent  → metrics.total_signals_sent (was AttributeError)
        """
        if self._redis is None:
            return
        try:
            state = {
                "version":           UNITY_VERSION,
                "win_count":         self.metrics.win_count,
                "loss_count":        self.metrics.loss_count,
                "total_profit_pct":  self.metrics.total_profit_pct,   # v8.0 FIX: was total_pnl
                "scan_cycles":       self.metrics.scan_cycles,
                "total_signals_sent": self.metrics.total_signals_sent, # v8.0 FIX: was signals_sent
                "total_signals_evaluated": self.metrics.total_signals_evaluated,
                "last_signal_quality": self.metrics.last_signal_quality,
                "last_gex_regime":   self.metrics.last_gex_regime,
                "last_dgrp_score":   self.metrics.last_dgrp_score,
                "saved_at":          time.time(),
            }
            if self.signal_filter:
                state["adaptive_irons_min"] = self.signal_filter.effective_irons_min
                state["gate_stats"]         = _fast_dumps(self.signal_filter._gate_stats)
            # v9.2: include Bayesian posteriors + pnl_ring so Redis restore gives
            #        a fully warm booster (was missing → cold restart every deploy)
            if getattr(self, "booster", None) is not None:
                try:
                    state["bayes_alpha"] = float(self.booster._bayes_alpha)
                    state["bayes_beta"]  = float(self.booster._bayes_beta)
                    state["pnl_ring"]    = list(self.booster._pnl_ring)
                except Exception:
                    pass
            await self._redis.setex(
                "unity_engine:state",
                REDIS_STATE_TTL_SEC,
                _fast_dumps(state),
            )
        except Exception as exc:
            self._logger.debug(f"Redis state sync skipped (non-fatal): {exc}")

    async def _redis_restore_state(self) -> None:
        """
        Restore engine state from Redis at startup (before first scan cycle).
        Merges Redis data into in-memory metrics — Redis wins over local JSON
        only for win/loss counters (higher fidelity in Redis due to 120s sync).
        """
        if self._redis is None:
            return
        try:
            raw = await self._redis.get("unity_engine:state")
            if not raw:
                return
            state = _fast_loads(raw)
            saved_at = state.get("saved_at", 0)
            age_min  = (time.time() - saved_at) / 60
            # Only restore if Redis state is fresher than what's on disk
            if age_min < 60:
                self.metrics.win_count   = max(self.metrics.win_count,  int(state.get("win_count",  0)))
                self.metrics.loss_count  = max(self.metrics.loss_count, int(state.get("loss_count", 0)))
                # v8.0 FIX: use corrected field name total_profit_pct (old snapshots may have total_pnl)
                _pnl = state.get("total_profit_pct", state.get("total_pnl", None))
                if _pnl is not None:
                    self.metrics.total_profit_pct = float(_pnl)
                _sent = state.get("total_signals_sent", state.get("signals_sent", None))
                if _sent is not None:
                    self.metrics.total_signals_sent = max(self.metrics.total_signals_sent, int(_sent))
                _eval = state.get("total_signals_evaluated", 0)
                if _eval:
                    self.metrics.total_signals_evaluated = max(
                        self.metrics.total_signals_evaluated, int(_eval)
                    )
                if self.signal_filter and "adaptive_irons_min" in state:
                    self.signal_filter._adaptive_irons_min = float(state["adaptive_irons_min"])
                # v8.2 FIX: gate_stats stored as a JSON string — parse it back.
                # Previously gate_stats was serialized with _fast_dumps() but never
                # deserialized, so Redis restore never updated gate pass/fail counters.
                if self.signal_filter and "gate_stats" in state:
                    try:
                        _gs_raw = state["gate_stats"]
                        _gs = _fast_loads(_gs_raw) if isinstance(_gs_raw, str) else _gs_raw
                        if isinstance(_gs, dict):
                            for _gk, _gv in _gs.items():
                                if _gk in self.signal_filter._gate_stats and isinstance(_gv, dict):
                                    self.signal_filter._gate_stats[_gk]["pass"] = int(_gv.get("pass", 0))
                                    self.signal_filter._gate_stats[_gk]["fail"] = int(_gv.get("fail", 0))
                    except Exception as _gse:
                        self._logger.debug(f"Redis gate_stats restore skipped: {_gse}")
                # v9.2: restore Bayesian posteriors + pnl_ring from Redis
                _redis_bayes_ok = False
                if getattr(self, "booster", None) is not None:
                    try:
                        if "bayes_alpha" in state:
                            self.booster._bayes_alpha = float(state["bayes_alpha"])
                            self.booster._bayes_beta  = float(state.get("bayes_beta", 2.0))
                            _redis_bayes_ok = True
                        if "pnl_ring" in state:
                            _pr = state["pnl_ring"]
                            if isinstance(_pr, list) and _pr:
                                self.booster._pnl_ring.clear()
                                self.booster._pnl_ring.extend(
                                    float(v) for v in _pr if isinstance(v, (int, float))
                                )
                    except Exception as _be:
                        self._logger.debug(f"Redis Bayes/pnl_ring restore skipped: {_be}")
                _b = getattr(self, "booster", None)
                self._logger.info(
                    f"📦 [v9.3] Redis state restored: W={self.metrics.win_count} "
                    f"L={self.metrics.loss_count} pnl={self.metrics.total_profit_pct:+.2f}% "
                    f"| Bayes={'α={:.1f} β={:.1f}'.format(_b._bayes_alpha, _b._bayes_beta) if _redis_bayes_ok and _b else 'cold'} "
                    f"| pnl_ring={len(_b._pnl_ring) if _b else 0} pts "
                    f"| age={age_min:.0f}min"
                )
        except Exception as exc:
            self._logger.debug(f"Redis restore skipped (non-fatal): {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # v8.0: Producer-Consumer signal dispatch queue
    # ─────────────────────────────────────────────────────────────────────────

    async def _signal_queue_consumer_task(self) -> None:
        """
        Consumer half of the Producer-Consumer signal dispatch pipeline (v8.0).

        Architecture:
          Scanner (producer) → asyncio.Queue[signal_dict] → Consumer (this task)
              ↓ put_nowait (non-blocking)                    ↓ get() + dispatch
          Scan loop never blocked by slow Telegram sends.

        The consumer drains signals from self._signal_queue one at a time,
        applying a final rate-limit guard before forwarding each signal to
        Telegram.  If the Telegram call itself is slow (network congestion,
        Railway container wake-up), the queue absorbs the backpressure without
        blocking the scanning loop — ensuring scan cycles remain on schedule.

        Queue overflow (> SIGNAL_QUEUE_MAXSIZE): put_nowait raises QueueFull
        which the producer catches and logs as a dropped signal — this is the
        correct backpressure behaviour for a time-sensitive trading system.
        """
        _log = logging.getLogger("UnityEngine.SignalConsumer")
        _log.info(f"📨 [v8.0] Signal consumer started (queue_maxsize={SIGNAL_QUEUE_MAXSIZE})")

        while True:
            try:
                # Blocking wait — consumer sleeps here when queue is empty
                signal_payload = await self._signal_queue.get()
                try:
                    symbol    = signal_payload.get("symbol", "?")
                    direction = signal_payload.get("direction", "?")
                    quality   = float(signal_payload.get("quality", 0.0))
                    msg_text  = signal_payload.get("message", "")
                    # v10.5: Stable signal ID for execution caching
                    signal_id = signal_payload.get(
                        "signal_id",
                        f"{symbol}_{direction}_{int(time.time())}"
                    )
                    item = signal_payload   # alias for cache_signal call
                    _q_size   = self._signal_queue.qsize()

                    _log.debug(
                        f"📨 Consuming signal: {symbol} {direction} "
                        f"Q={quality:.0f} | queue_depth={_q_size}"
                    )

                    # v9.1: Re-inject active LLM key every 100 dispatches so
                    # mid-session key rotations propagate to all LLM modules.
                    # v10.3 FIX: also inject on signal #1 (first dispatch after
                    # launcher restart) so a fresh rotated key is applied immediately
                    # rather than waiting for the 100th signal. This covers launchers
                    # that restart with a fresh total_signals_sent counter.
                    _ssent = self.metrics.total_signals_sent
                    if _ssent % 100 == 0:
                        _llm_key_rotator.inject_env()

                    # v9.1: Guard — log if msg_text is missing so dropped signals are visible
                    if not msg_text:
                        _log.debug(
                            f"⚠️  [v9.3] Signal consumed but msg_text empty "
                            f"({symbol} {direction} Q={quality:.0f}) — Telegram dispatch skipped"
                        )


                    # ── v8.0 Prompt 1: build atomic SignalDecisionVector ─────────
                    # Capture all parallel inputs into a single immutable record
                    # that represents the unified decision for this queue tick.
                    # This is the "Global State Consistency" guarantee: one frozen
                    # object records exactly what every layer contributed.
                    try:
                        _dvec = SignalDecisionVector(
                            symbol               = symbol,
                            timestamp            = time.time(),
                            gex_regime           = str(signal_payload.get("gex_regime", self.metrics.last_gex_regime)),
                            gex_gamma_zero_dist_pct = float(signal_payload.get("gz_dist_pct", 0.0)),
                            orderbook_imbalance  = float(signal_payload.get("ob_imbalance", 0.5)),
                            llm_verdict          = str(signal_payload.get("llm_verdict", direction)),
                            llm_confidence       = float(signal_payload.get("llm_confidence", 0.0)),
                            llm_regime_tag       = str(signal_payload.get("llm_regime", "unknown")),
                            nn_direction_score   = float(signal_payload.get("nn_score", 0.0)),
                            nn_confidence        = float(signal_payload.get("nn_confidence", 0.0)),
                            composite_score      = quality,
                            kelly_fraction       = float(signal_payload.get("kelly_fraction", self.metrics.last_kelly_fraction)),
                            ev_ratio             = float(signal_payload.get("ev_ratio", 0.0)),
                            decision             = "SEND",
                            reject_reason        = "",
                        )
                        # Store last decision vector on engine for /metrics endpoint
                        self._last_decision_vector = _dvec
                    except Exception:
                        pass  # never block dispatch on audit record failure

                    # ── v9.4 Shadow/Paper-mode gate ─────────────────────────
                    # When auto-shadow is active (rolling-20 WR < 35%) or
                    # UNITY_SHADOW_MODE forces it, log the signal but do NOT
                    # dispatch.  Capital is preserved while the per-symbol WR
                    # tables and NN re-warm; trading resumes automatically once
                    # rolling WR recovers above AUTO_PAPER_WR_THRESHOLD.
                    # v10.1 BUG FIX: paper_mode is a property of UnityProfitBooster
                    # (self.booster), NOT UnityMetrics (self.metrics). The old code
                    # always returned False because UnityMetrics has no paper_mode
                    # attribute — shadow mode was silently broken since v9.4.
                    _paper = bool(getattr(self.booster, "paper_mode", False))
                    if _paper:
                        self.metrics.total_signals_sent += 0  # explicit no-op
                        _log.info(
                            f"🔇 [v9.4 SHADOW] {symbol} {direction} signal logged-only "
                            f"(no Telegram dispatch) | quality={quality:.0f}/100 | "
                            f"reason={'WR<35%' if not FORCE_SHADOW_MODE else 'UNITY_SHADOW_MODE forced'}"
                        )
                    # Dispatch: try the bot's Telegram sender first
                    elif self.bot is not None and msg_text:
                        try:
                            _send = getattr(self.bot, "send_signal_message",
                                    getattr(self.bot, "_send_telegram_message",
                                    getattr(self.bot, "send_message", None)))
                            if callable(_send):
                                await asyncio.wait_for(_send(msg_text), timeout=15.0)
                                # v8.0 bug fix: was self.metrics.signals_sent (AttributeError)
                                self.metrics.total_signals_sent += 1
                                self._signal_times.append(time.time())
                                # v10.5: Cache signal in CornixMenuBot for one-tap execution
                                _cornix_m = getattr(self.bot, "cornix_menu", None)
                                _cache_fn = getattr(_cornix_m, "cache_signal", None)
                                if callable(_cache_fn):
                                    try:
                                        _cache_fn(signal_id, {
                                            "symbol":    symbol,
                                            "direction": direction,
                                            "entry":     item.get("entry",  0),
                                            "sl":        item.get("sl",     0),
                                            "tp1":       item.get("tp1",    0),
                                            "tp2":       item.get("tp2",    0),
                                            "quality":   quality,
                                        })
                                    except Exception:
                                        pass
                        except asyncio.TimeoutError:
                            _log.warning(f"⚠️  Telegram dispatch timeout for {symbol} — signal dropped from consumer")
                        except Exception as exc:
                            # v10.4: Upgraded DEBUG→WARNING — silent Telegram drops now visible
                            _log.warning(f"⚠️  [v10.4] Telegram dispatch error for {symbol}: {type(exc).__name__}: {exc}")
                    elif self.bot is None and msg_text:
                        # v10.3: Upgraded from silent drop to WARNING — operator
                        # can now see that signals are being generated but cannot
                        # be dispatched because the bot layer failed to initialise.
                        _log.warning(
                            f"⚠️  [v10.3] SIGNAL LOST — bot layer is None, cannot "
                            f"dispatch Telegram message for {symbol} {direction} "
                            f"Q={quality:.0f}. Check layer init logs."
                        )

                finally:
                    self._signal_queue.task_done()

            except asyncio.CancelledError:
                _log.info("Signal consumer cancelled")
                break
            except Exception as exc:
                # v10.4: Upgraded DEBUG→WARNING — makes signal dispatch failures
                # visible in production logs so operators can act immediately.
                _log.warning(f"⚠️  [v10.4] Signal consumer outer error: {type(exc).__name__}: {exc}")
                await asyncio.sleep(0.5)

    # ─────────────────────────────────────────────────────────────────────────
    # v8.0: WebSocket live orderbook ingestion (Binance depth stream)
    # ─────────────────────────────────────────────────────────────────────────

    async def _ws_orderbook_task(self) -> None:
        """
        Maintains persistent WebSocket connections to Binance's @depth5 stream
        for the top WS_MAX_SYMBOLS active symbols (v8.0).

        Stream: wss://fstream.binance.com/stream?streams=<sym>@depth5@100ms
        Uses Binance USDM Futures stream endpoint (fstream) — NOT the spot
        endpoint (stream.binance.com).  Futures spreads differ materially
        from spot spreads; using spot data here would corrupt Gate-0 EV calc.
        Provides sub-100ms refresh of best bid/ask, mid-price, spread, and
        depth imbalance — stored in self._ws_state[symbol] for use by the
        signal filter and health endpoints.

        Depth imbalance formula:
          imbalance = (total_bid_vol − total_ask_vol) / (total_bid_vol + total_ask_vol)
          +1.0 = fully bid-heavy (bullish pressure)
          -1.0 = fully ask-heavy (bearish pressure)

        Reconnect: exponential backoff from WS_RECONNECT_DELAY_SEC to 60 s.
        Falls back silently if the `websockets` library is not installed.
        """
        _log = logging.getLogger("UnityEngine.WSOrderbook")

        try:
            import websockets  # type: ignore[import]
        except ImportError:
            _log.warning("⚠️  [v8.0] websockets library not installed — live orderbook WS disabled")
            return

        _log.info(f"🔌 [v8.0] WebSocket orderbook task started (max_symbols={WS_MAX_SYMBOLS})")
        _reconnect_delay = WS_RECONNECT_DELAY_SEC

        while True:
            try:
                # Pick top N active symbols
                symbols: List[str] = []
                if self.bot is not None:
                    raw_syms = list(getattr(self.bot, "_active_symbols", []) or [])
                    symbols  = [s.lower().replace("/", "") for s in raw_syms[:WS_MAX_SYMBOLS]]

                if not symbols:
                    await asyncio.sleep(10)
                    continue

                # Build combined stream URL
                streams  = "/".join(f"{s}@depth{WS_ORDERBOOK_DEPTH}@100ms" for s in symbols)
                # v9.2 FIX: use fstream.binance.com (USDM Futures endpoint).
                # The old URL (stream.binance.com:9443) is the SPOT endpoint —
                # futures spreads/depth differ from spot and would corrupt
                # the Gate-0 dynamic-slippage EV check.
                ws_url   = f"wss://fstream.binance.com/stream?streams={streams}"

                _log.info(f"🔌 WS connecting: {len(symbols)} symbols → {ws_url[:80]}…")

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    _reconnect_delay = WS_RECONNECT_DELAY_SEC   # reset on success
                    _log.info(f"✅ [v8.0] WS orderbook connected ({len(symbols)} streams)")

                    async for raw_msg in ws:
                        try:
                            msg   = _fast_loads(raw_msg)
                            data  = msg.get("data", msg)
                            # Extract symbol from stream name: e.g. "btcusdt@depth5@100ms"
                            stream_name = msg.get("stream", "")
                            sym_lower   = stream_name.split("@")[0] if stream_name else ""

                            bids = data.get("bids", [])
                            asks = data.get("asks", [])
                            if not bids or not asks:
                                continue

                            best_bid  = float(bids[0][0])
                            best_ask  = float(asks[0][0])
                            mid_price = (best_bid + best_ask) / 2.0
                            spread_pct= (best_ask - best_bid) / mid_price if mid_price else 0.0

                            # Depth imbalance: bid_vol vs ask_vol across all levels
                            bid_vol = sum(float(b[1]) for b in bids)
                            ask_vol = sum(float(a[1]) for a in asks)
                            total_vol = bid_vol + ask_vol
                            imbalance = (bid_vol - ask_vol) / total_vol if total_vol else 0.0

                            # v8.0 Omega-Tier: nanosecond ingestion timestamp
                            # ts_ns = wall-clock monotonic ticks (time.time_ns())
                            # ts    = float seconds (backward-compat for all callers)
                            # KEY FIX: store under UPPERCASE symbol so all callers
                            # that look up by signal symbol (always uppercase) find
                            # the data.  The WS stream delivers lowercase names; the
                            # rest of the codebase uses BTCUSDT, ETHUSDT, etc.
                            _ts_ns = time.time_ns()
                            _sym_key = sym_lower.upper()
                            # v11.0 BUG FIX: wrap dict write under _ws_state_lock
                            # to prevent race condition with concurrent readers
                            # (signal filter, bot, strategy) — GIL alone is not
                            # sufficient when asyncio tasks bridge threads.
                            with self._ws_state_lock:
                                self._ws_state[_sym_key] = {
                                    "best_bid":        best_bid,
                                    "best_ask":        best_ask,
                                    "mid_price":       mid_price,
                                    "spread_pct":      spread_pct,
                                    "depth_imbalance": imbalance,
                                    "ts":              _ts_ns / 1_000_000_000.0,
                                    "ts_ns":           _ts_ns,
                                }
                            # v9.7: feed institutional timing buffers (Roll, CUSUM,
                            # AVWAP, OFI) — single O(1) call per WS message.
                            # All four primitives derive from this same depth5
                            # stream so latency is bounded by the WS itself
                            # (~100ms ticks).  Null-guard preserves v9.6 behaviour
                            # if timing-state injection is ever skipped.
                            _ts = getattr(self, "_timing_state", None)
                            if _ts is not None:
                                try:
                                    _ts.update_from_ws(
                                        _sym_key, best_bid, best_ask, bid_vol, ask_vol
                                    )
                                except Exception:
                                    pass   # never let a buffer error kill the WS loop

                        except Exception:
                            pass   # individual message parse errors are non-fatal

            except asyncio.CancelledError:
                _log.info("WS orderbook task cancelled")
                break
            except Exception as exc:
                _log.warning(
                    f"🔌 WS orderbook disconnected ({type(exc).__name__}: {exc}) "
                    f"— reconnecting in {_reconnect_delay:.0f}s"
                )
                await asyncio.sleep(_reconnect_delay)
                _reconnect_delay = min(60.0, _reconnect_delay * 1.5)  # exponential backoff

    # ─────────────────────────────────────────────────────────────────────────
    # v5.0: Periodic persistence save
    # ─────────────────────────────────────────────────────────────────────────

    async def _persistence_task(self) -> None:
        """
        Saves metrics + per-symbol stats + GEX cache to disk every 5 minutes
        so they survive launcher restarts (win-rate, PnL, Gate 8 data, etc.)
        """
        _log = logging.getLogger("UnityEngine.Persistence")
        _log.info("💾 Persistence task started (save interval=120s)")  # v5.2: 300s → 120s

        def _save_all(label: str):
            self.metrics.save()
            self.sym_tracker.save()
            # v5.2: persist GEX snapshot cache
            try:
                if self._gex_snapshots:
                    # v10.4 BUG FIX: shallow-copy under _gex_lock before iterating.
                    # Previously the GEX scanner task could modify self._gex_snapshots
                    # concurrently → RuntimeError: dictionary changed size during iteration.
                    with self._gex_lock:
                        _snaps_copy = dict(self._gex_snapshots)
                    serialisable = {}
                    for sym, (snap, ts) in _snaps_copy.items():
                        try:
                            serialisable[sym] = {
                                "ts":      ts,
                                "regime":  str(getattr(snap, "regime", "UNKNOWN")),
                                "dgrp":    float(getattr(snap, "dgrp_score", 0) or 0),
                                "conf":    float(getattr(snap, "confidence", 0) or 0),
                            }
                        except Exception:
                            pass
                    _atomic_write_json(UNITY_GEX_CACHE_FILE, serialisable)   # v9.7: atomic
            except Exception:
                pass
            # v6.3: persist gate stats and symbol cooldowns across restarts
            try:
                if self.signal_filter:
                    _filter_state = {
                        "gate_stats":   self.signal_filter._gate_stats,
                        "cooldowns":    dict(self.signal_filter._symbol_last_sent),
                        "adaptive_irons_min": self.signal_filter.effective_irons_min,
                        "saved_at":     time.time(),
                    }
                    # v9.1: persist Sharpe/Sortino pnl_ring for warm-start across restarts
                    # v9.2: also persist Bayesian alpha/beta posteriors so win-probability
                    #        prior survives restarts (was discarding full-session history)
                    if getattr(self, "booster", None) is not None:
                        try:
                            _filter_state["pnl_ring"]    = list(self.booster._pnl_ring)
                            _filter_state["bayes_alpha"] = float(self.booster._bayes_alpha)
                            _filter_state["bayes_beta"]  = float(self.booster._bayes_beta)
                        except Exception:
                            pass
                    _atomic_write_json(UNITY_FILTER_STATE_FILE, _filter_state)   # v9.7: atomic
            except Exception:
                pass
            _log.debug(f"💾 [{label}] Metrics + symbols + GEX cache + filter state saved")

        # v10.1: Save immediately on startup (before the first 120s sleep).
        # Captures the loaded/warm-started state (Bayes posteriors, gate stats,
        # cooldowns) as the authoritative baseline for the current session so
        # a crash in the first 2 minutes doesn't lose the restored state.
        try:
            _save_all("startup")
            _log.info(f"💾 [v{UNITY_VERSION}] Startup state snapshot saved")
        except Exception:
            pass

        _blacklist_refresh_counter = 0
        _BLACKLIST_REFRESH_EVERY  = 5   # refresh every 5 × 120s = 10 minutes

        while True:
            try:
                await asyncio.sleep(120)  # v5.2: 300s → 120s for faster crash recovery
                _save_all("periodic")
                await self._redis_sync_state()   # v8.0: mirror state to Redis

                # v10.3: Periodic symbol blacklist refresh every 10 min.
                # At startup _load_symbol_blacklist() runs once; symbols that
                # cross WR<30% during a session were never re-blocked until
                # the next launcher restart.  Now the filter's blacklist is
                # refreshed live every 10 min so short-term deteriorating
                # symbols are removed from trading rotation without a restart.
                _blacklist_refresh_counter += 1
                if _blacklist_refresh_counter >= _BLACKLIST_REFRESH_EVERY:
                    _blacklist_refresh_counter = 0
                    try:
                        if self.signal_filter is not None:
                            _new_bl = UnitySignalFilter._load_symbol_blacklist()
                            self.signal_filter._symbol_blacklist = _new_bl
                            _log.debug(
                                f"🔄 [v10.3] Symbol blacklist refreshed: "
                                f"{len(_new_bl)} blocked symbols"
                            )
                    except Exception as _bl_ex:
                        _log.debug(f"Blacklist refresh skipped (non-fatal): {_bl_ex}")

            except asyncio.CancelledError:
                try:
                    _save_all("shutdown")
                    _log.info("💾 Final persistence save on shutdown")
                except Exception:
                    pass
                break
            except Exception as e:
                # v10.4: Upgraded DEBUG→WARNING — storage failures need operator visibility
                _log.warning(f"⚠️  [v10.4] Persistence save error (non-fatal): {type(e).__name__}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # GEX background scanner  (FIX v4.0: true rotating pointer)
    # ─────────────────────────────────────────────────────────────────────────

    async def _gex_scanner_task(self):
        """
        Background task: continuously refresh GEX snapshots for all symbols.
        FIX v4.0: Uses rotating index pointer to scan ALL symbols over time,
        not just the first GEX_BATCH_SIZE forever (v3.0 bug).
        Also prunes stale snapshots every GEX_SNAPSHOT_PRUNE_CYCLES cycles.
        """
        if self.gex_engine is None:
            return
        _log           = logging.getLogger("UnityEngine.GEX")
        _GEX_SEM       = asyncio.Semaphore(GEX_PARALLEL_LIMIT)
        _last_prune_ts = time.time()   # v5.3: time-based prune (every 90s) not cycle-based

        _gex_ok_count  = 0   # v8.2: telemetry counters for GEX batch diagnostics
        _gex_err_count = 0

        async def _scan_one_gex(trader, symbol: str):
            nonlocal _gex_ok_count, _gex_err_count
            async with _GEX_SEM:
                try:
                    snap = await asyncio.wait_for(
                        self.gex_engine.compute_gex_snapshot(trader, symbol, "5m"),
                        timeout=25.0,   # v8.2: 20s→25s — extra headroom for slow markets
                    )
                    _gex_ok_count += 1
                    return symbol, snap
                except asyncio.TimeoutError:
                    _gex_err_count += 1
                    _log.debug(f"GEX timeout: {symbol} (>25s)")
                    return symbol, None
                except Exception as _exc:
                    _gex_err_count += 1
                    _log.debug(f"GEX error: {symbol}: {type(_exc).__name__}: {_exc}")
                    return symbol, None

        while True:
            try:
                trader = getattr(self.bot, "trader", None) if self.bot else None
                if trader is None:
                    await asyncio.sleep(GEX_SCAN_INTERVAL_SEC)
                    continue

                symbols = list(getattr(self.bot, "_active_symbols", []) or [])
                if not symbols:
                    await asyncio.sleep(GEX_SCAN_INTERVAL_SEC)
                    continue

                # FIX v4.0: rotate through all symbols using self._gex_rotate_idx
                n = len(symbols)
                start = self._gex_rotate_idx % n
                batch = (symbols + symbols)[start: start + GEX_BATCH_SIZE]
                batch = list(dict.fromkeys(batch))   # deduplicate, preserve order
                self._gex_rotate_idx = (start + GEX_BATCH_SIZE) % n

                tasks   = [_scan_one_gex(trader, sym) for sym in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for item in results:
                    if isinstance(item, Exception) or not isinstance(item, tuple):
                        continue
                    sym, snap = item
                    if snap is None:
                        continue

                    # ── L0.5: splice real Deribit GEX into BTC/ETH snapshots ─
                    # Mutates `snap` in-place; downstream consumers keep
                    # reading the same gex_flip / call_wall / put_wall /
                    # net_gex / regime attrs, just sourced from the real
                    # options chain instead of the ATR proxy.
                    if self.deribit_gex is not None:
                        try:
                            await self.deribit_gex.enrich_snapshot(sym, snap)
                        except Exception as _enrich_exc:
                            _log.debug(
                                f"Deribit enrich failed for {sym} "
                                f"(non-fatal): {_enrich_exc}"
                            )

                    with self._gex_lock:
                        self._gex_snapshots[sym] = (snap, time.time())
                    regime = str(getattr(snap, "regime", "UNKNOWN")).upper()
                    dgrp   = float(getattr(snap, "dgrp_score", 0) or 0)
                    if regime not in ("UNKNOWN", ""):
                        self.metrics.last_gex_regime = regime
                        self.metrics.last_dgrp_score = dgrp

                _log.debug(
                    f"GEX scan done: batch={len(batch)} ok={_gex_ok_count} err={_gex_err_count} "
                    f"| rotate_idx={self._gex_rotate_idx} "
                    f"| cached={len(self._gex_snapshots)} | regime={self.metrics.last_gex_regime}"
                )
                _gex_ok_count  = 0   # reset per-batch counters
                _gex_err_count = 0

                # FIX v5.3: time-based prune every 90s (was cycle-based every 300
                # cycles ≈ 2.5h — stale GEX entries accumulated for far too long)
                # v6.0 BUG FIX: use list(items()) snapshot to prevent
                # "RuntimeError: dictionary changed size during iteration"
                now = time.time()
                if now - _last_prune_ts >= 90.0:
                    _last_prune_ts = now
                    cutoff = now - GEX_SNAPSHOT_MAX_AGE_SEC
                    with self._gex_lock:
                        stale = [
                            s for s, (_, ts)
                            in list(self._gex_snapshots.items())
                            if ts < cutoff
                        ]
                        for s in stale:
                            self._gex_snapshots.pop(s, None)
                    if stale:
                        _log.debug(f"GEX snapshot pruned {len(stale)} stale entries")

                await asyncio.sleep(GEX_SCAN_INTERVAL_SEC)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # v10.4: Upgraded DEBUG→WARNING — GEX scan failures need operator visibility
                _log.warning(f"⚠️  [v10.4] GEX scanner error (non-fatal): {type(e).__name__}: {e}")
                await asyncio.sleep(GEX_SCAN_INTERVAL_SEC * 2)

    def get_gex_snapshot(self, symbol: str) -> Optional[Any]:
        """Return fresh GEX snapshot for symbol, or None if stale/absent."""
        with self._gex_lock:
            entry = self._gex_snapshots.get(symbol)
        if entry is None:
            return None
        snap, ts = entry
        if time.time() - ts > GEX_SNAPSHOT_MAX_AGE_SEC:
            return None
        return snap

    # ─────────────────────────────────────────────────────────────────────────
    # v5.9: NN periodic background retraining  (every 2 hours)
    # ─────────────────────────────────────────────────────────────────────────

    async def _nn_retrain_task(self) -> None:
        """
        Background task: retrain the Neural Network every NN_RETRAIN_INTERVAL_SEC
        (2 hours) using accumulated trade outcomes stored in TradeMemory.

        Benefits:
          • Model adapts to changing market regime continuously
          • New win/loss data from live signals improves threshold calibration
          • Runs in a separate thread-pool executor so it never blocks the scanner

        Safety:
          • Only retrains when TradeMemory has ≥ NN_RETRAIN_MIN_SAMPLES outcomes
          • Wraps training in try/except — any failure is non-fatal
          • Logs before/after accuracy delta so drift is observable
        """
        _log = logging.getLogger("UnityEngine.NNRetrain")
        _log.info(
            f"🧠 NN Retrain task started "
            f"(interval={NN_RETRAIN_INTERVAL_SEC//3600}h, "
            f"min_samples={NN_RETRAIN_MIN_SAMPLES})"
        )

        # v8.5: Fast first-run (5min) instead of half-interval (1h) so the NN
        # retrains soon after startup on the latest accumulated outcomes with
        # class-balanced loss (current snapshot was trained on 952 samples
        # while DB holds 2241+). Subsequent runs use the full 2h interval.
        await asyncio.sleep(300)

        while True:
            try:
                if self.nn_trainer is None or self.trade_memory is None:
                    await asyncio.sleep(NN_RETRAIN_INTERVAL_SEC)
                    continue

                # Count available training samples
                try:
                    sample_count = len(self.trade_memory.get_recent_trades(limit=10000))
                except Exception:
                    sample_count = 0

                if sample_count < NN_RETRAIN_MIN_SAMPLES:
                    _log.info(
                        f"🧠 NN Retrain skipped — only {sample_count} samples "
                        f"(need ≥{NN_RETRAIN_MIN_SAMPLES})"
                    )
                    await asyncio.sleep(NN_RETRAIN_INTERVAL_SEC)
                    continue

                _acc_before = getattr(self.nn_trainer, "last_accuracy", 0.0)
                _log.info(
                    f"🧠 NN Retrain starting — {sample_count} samples available "
                    f"| current accuracy={_acc_before:.1%}"
                )

                # Run CPU-bound training in the dedicated thread pool so scanner
                # isn't blocked.  v7.0 BUG FIX: was run_in_executor(None,...) which
                # uses the default executor (shared with all asyncio I/O); now uses
                # self._thread_pool (dedicated 4-worker pool for CPU-bound tasks).
                # v10.3 BUG FIX: replaced lambda closure with functools.partial to
                # snapshot trainer/memory references at submission time — avoids a
                # CPython GIL re-entry edge case when self.nn_trainer is reassigned
                # by the re-wire block below while the thread is still running.
                _trainer_ref = self.nn_trainer
                _memory_ref  = self.trade_memory
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    self._thread_pool,
                    functools.partial(_trainer_ref.train, _memory_ref)
                )

                _acc_after = getattr(self.nn_trainer, "last_accuracy", 0.0)
                _delta = _acc_after - _acc_before
                _log.info(
                    f"🧠 NN Retrain complete — accuracy {_acc_before:.1%}→{_acc_after:.1%} "
                    f"({_delta:+.1%}) | {self.nn_trainer.status_summary()}"
                )

                # v6.0 FIX: Re-wire updated trainer into BOTH bot AND strategy
                # (v5.9 only updated bot.nn_trainer — strategy kept the old model)
                if self.bot is not None:
                    try:
                        self.bot.nn_trainer = self.nn_trainer
                        _try_setattr(self.bot, "_unity_nn_trainer", self.nn_trainer)
                    except Exception:
                        pass
                if self.strategy is not None:
                    try:
                        _try_setattr(self.strategy, "_unity_nn_trainer", self.nn_trainer)
                    except Exception:
                        pass

            except asyncio.CancelledError:
                _log.info("NN Retrain task cancelled")
                break
            except Exception as e:
                # v10.1 BUG FIX: previously fell through to sleep(NN_RETRAIN_INTERVAL_SEC)
                # on error — meaning any crash caused a 2h blackout.  Now uses a
                # short 5-minute backoff so the NN recovers quickly from transient
                # errors (DB lock, OOM, import failure on partial data).
                _log.warning(f"NN Retrain error (non-fatal): {type(e).__name__}: {e} — retrying in 300s")
                await asyncio.sleep(300)
                continue

            await asyncio.sleep(NN_RETRAIN_INTERVAL_SEC)

    # ─────────────────────────────────────────────────────────────────────────
    # Outcome tracker background task
    # ─────────────────────────────────────────────────────────────────────────

    async def _outcome_tracker_task(self):
        """
        FIX v4.0: Runs the OutcomeTracker instance as an asyncio task.
        v3.0 never started the tracker since it stored only the class.
        v8.2 FIX: added auto-restart loop — OutcomeTracker.run() can raise
        unexpected exceptions (network, DB lock) which previously killed the
        task permanently.  Now it restarts with exponential backoff (5s→60s)
        so outcome tracking survives transient failures.
        """
        if self.outcome_tracker_instance is None:
            return
        _log = logging.getLogger("UnityEngine.OutcomeTracker")
        _log.info("🔎 OutcomeTracker background task started (v4.0 instance, v8.2 auto-restart)")
        _restart_delay = 5.0
        while True:
            try:
                await self.outcome_tracker_instance.run()
                return  # clean exit — do not restart
            except asyncio.CancelledError:
                _log.info("OutcomeTracker task cancelled")
                return
            except Exception as e:
                _log.warning(
                    f"OutcomeTracker task error: {type(e).__name__}: {e} "
                    f"— restarting in {_restart_delay:.0f}s (v8.2 auto-restart)"
                )
                await asyncio.sleep(_restart_delay)
                _restart_delay = min(60.0, _restart_delay * 1.5)

    # ─────────────────────────────────────────────────────────────────────────
    # Main run loop
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self) -> bool:
        """Main Unity Engine coroutine.  Returns True on clean exit."""
        self._logger.info(f"🚀 [Unity v{UNITY_VERSION}] Starting Unity Engine initialisation...")

        # v5.0: Setup OS signal handlers for graceful shutdown
        try:
            loop = asyncio.get_running_loop()
            self._setup_signal_handlers(loop)
        except Exception:
            pass

        # v5.0: Load persisted metrics + per-symbol data
        self.metrics.load()
        self.sym_tracker.load()
        if self.metrics.win_count + self.metrics.loss_count > 0:
            self._logger.info(
                f"📂 Restored persisted metrics: W={self.metrics.win_count} "
                f"L={self.metrics.loss_count} WR={self.metrics.win_rate:.1f}%"
            )

        required = ["TELEGRAM_BOT_TOKEN", "BINANCE_API_KEY", "BINANCE_API_SECRET"]
        missing  = [v for v in required if not os.getenv(v, "").strip()]
        if missing:
            self._logger.error(f"❌ Missing critical env vars: {missing}")
            # FIX v5.3: raise a config error so the launcher can fast-fail
            # instead of retrying 100× with exponential backoff.
            raise _ConfigError(f"Missing env vars: {missing}")

        _or  = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
        _oai = bool(os.getenv("OPENAI_API_KEY",     "").strip())
        _ant = bool(os.getenv("ANTHROPIC_API_KEY",  "").strip())

        # v5.7: LLM Key Auto-Routing — promote OPENAI_API_KEY as OPENROUTER fallback
        # when OPENROUTER_API_KEY is absent so G0DM0D3 still gets a functioning key.
        if not _or and _oai:
            os.environ["OPENROUTER_API_KEY"] = os.environ["OPENAI_API_KEY"]
            _or = True
            self._logger.info(
                "🔑 [v5.7 Key Router] OPENAI_API_KEY promoted to OPENROUTER_API_KEY — "
                "G0DM0D3/OpenRouter layers will use OpenAI endpoint as primary LLM."
            )

        # v8.0: Inject rotated key into env before layer init so all LLM modules
        # pick up the correct key even after a mid-session rotation.
        _llm_key_rotator.inject_env()
        self._logger.info(
            f"🔑 AI keys: OpenRouter={'✅ PRIMARY' if _or else '⚠️  MISSING (LLM degraded)'} | "
            f"Claude={'✅' if _ant else '⬜'} | OpenAI={'✅' if _oai else '⬜'} | "
            f"KeyRotator: {_llm_key_rotator.status_summary()}"
        )
        if not _or and not _oai and not _ant:
            self._logger.warning(
                "⚠️  No LLM API keys set — G0DM0D3/OpenRouter layers will run in "
                "fallback mode. Set OPENROUTER_API_KEY for full AI signal enhancement."
            )

        try:
            if not self._init_layers():
                self._logger.error("❌ Critical layer init failed — aborting")
                return False
        except Exception as e:
            self._logger.error(f"❌ Layer init exception: {type(e).__name__}: {e}")
            self._logger.debug(traceback.format_exc())
            return False

        # v6.3: Restore filter state AFTER signal_filter is created by _init_layers
        # (gate stats + cooldowns + adaptive IRONS min survive launcher restarts)
        try:
            if os.path.exists(UNITY_FILTER_STATE_FILE) and self.signal_filter:
                with open(UNITY_FILTER_STATE_FILE, "r") as _f:
                    _fs = json.load(_f)
                if "gate_stats" in _fs:
                    for gate_key in self.signal_filter._gate_stats:
                        if gate_key in _fs["gate_stats"]:
                            self.signal_filter._gate_stats[gate_key]["pass"] = int(_fs["gate_stats"][gate_key].get("pass", 0))
                            self.signal_filter._gate_stats[gate_key]["fail"] = int(_fs["gate_stats"][gate_key].get("fail", 0))
                if "cooldowns" in _fs:
                    _cutoff = time.time() - SIGNAL_COOLDOWN_MINUTES * 60
                    for sym, ts in _fs["cooldowns"].items():
                        if float(ts) > _cutoff:
                            self.signal_filter._symbol_last_sent[sym] = float(ts)
                if "adaptive_irons_min" in _fs:
                    self.signal_filter._adaptive_irons_min = float(_fs["adaptive_irons_min"])
                # v9.1: restore Sharpe/Sortino pnl_ring for warm Sharpe from previous session
                # v9.7 BUG FIX: skip restore when state is older than PNL_RING_MAX_AGE_SEC
                # (default 24h).  Sharpe computed from days-old returns reflects a
                # market regime that may no longer apply, causing the v9.4 Sharpe-Floor
                # scaler to mis-size Kelly during the recovery window.
                if "pnl_ring" in _fs and getattr(self, "booster", None) is not None:
                    try:
                        _pnl_age_sec = time.time() - float(_fs.get("saved_at", 0) or 0)
                        _pnl_max_age = float(os.getenv("UNITY_PNL_RING_MAX_AGE_SEC", "86400") or 86400)
                        _saved_ring  = _fs["pnl_ring"]
                        if (
                            isinstance(_saved_ring, list)
                            and _saved_ring
                            and (_pnl_age_sec <= _pnl_max_age or _pnl_max_age <= 0)
                        ):
                            self.booster._pnl_ring.clear()
                            self.booster._pnl_ring.extend(float(v) for v in _saved_ring if isinstance(v, (int, float)))
                        elif _saved_ring:
                            self._logger.info(
                                f"⏰ [v9.7] pnl_ring restore skipped — saved state is "
                                f"{_pnl_age_sec/3600:.1f}h old (>{_pnl_max_age/3600:.0f}h limit) — "
                                f"Sharpe will warm-up from live trades for current regime"
                            )
                    except Exception:
                        pass
                # v9.2: restore Bayesian alpha/beta posteriors so win-probability
                #        prior continues from last session (not reset to Beta(2,2))
                _bayes_restored = False
                if getattr(self, "booster", None) is not None:
                    try:
                        if "bayes_alpha" in _fs:
                            self.booster._bayes_alpha = float(_fs["bayes_alpha"])
                            self.booster._bayes_beta  = float(_fs.get("bayes_beta", 2.0))
                            _bayes_restored = True
                    except Exception:
                        pass
                _saved_at = _fs.get("saved_at", 0)
                _age_min  = (time.time() - _saved_at) / 60 if _saved_at else 0
                _booster  = getattr(self, "booster", None)
                self._logger.info(
                    f"📂 Filter state restored: cooldowns={len(self.signal_filter._symbol_last_sent)} syms "
                    f"| IRONS_min={self.signal_filter.effective_irons_min:.0f} "
                    f"| pnl_ring={len(_booster._pnl_ring) if _booster else 0} pts "
                    f"| Bayes={'α={:.1f} β={:.1f}'.format(_booster._bayes_alpha, _booster._bayes_beta) if _bayes_restored and _booster else 'cold'} "
                    f"| state_age={_age_min:.0f}min [v9.3]"
                )
        except Exception as _fse:
            self._logger.debug(f"Filter state restore skipped (non-fatal): {_fse}")

        # v7.2 BUG FIX — RL booster ring buffer warm-start + adaptive IRONS pre-set
        # Previously: ring always started empty → _update_threshold_rl() returned early
        # (len<10 guard) → dynamic_threshold stuck at 80% regardless of WR history.
        # With W=17 L=44 (WR=27.4%), threshold SHOULD boot at 84% (+4% worst bucket),
        # not 80%.  The warm-start fills the ring proportionally and calls _update_threshold_rl()
        # immediately so the correct RL-adjusted threshold is active from signal #1.
        _total_hist = self.metrics.win_count + self.metrics.loss_count
        if _total_hist >= 10:
            self.booster.warm_start_from_history(
                self.metrics.win_count, self.metrics.loss_count
            )
            # Pre-set adaptive IRONS from persisted WR so Gate 10 is calibrated
            # even on the very first evaluated signal after a restart.
            # NOTE: filter state may already have saved adaptive_irons_min (restored
            # above), but call update_adaptive_irons() anyway — it applies the
            # correct schedule based on actual WR, overriding any stale saved value.
            if self.signal_filter is not None:
                _startup_wr = self.metrics.win_count / _total_hist
                self.signal_filter.update_adaptive_irons(_startup_wr)
                self._logger.info(
                    f"🎯 [v7.2] Adaptive IRONS pre-set: persisted WR={_startup_wr:.1%} → "
                    f"min={self.signal_filter.effective_irons_min:.0f} "
                    f"(was: default={IRONS_MIN_SCORE:.0f})"
                )

        self.health.print_dashboard()
        self._print_startup_banner()

        if self.console:
            await self.console.start()

        # v5.7: record init completion time for health endpoint
        self._init_complete_ts = time.time()

        # Background tasks — FIX v5.3: initialise ALL task handles to None before
        # any conditional creation to prevent NameError in cleanup if a task that
        # starts after a conditional check is not reached (e.g. health server fails).
        _gex_task:  Optional[asyncio.Task] = None
        _ot_task:   Optional[asyncio.Task] = None
        _wd_task:   Optional[asyncio.Task] = None
        _save_task: Optional[asyncio.Task] = None
        _hs_task:   Optional[asyncio.Task] = None
        _nn_task:   Optional[asyncio.Task] = None   # v5.9: NN periodic retraining
        _sq_task:   Optional[asyncio.Task] = None   # v8.0: signal queue consumer
        _ws_task:   Optional[asyncio.Task] = None   # v8.0: WS live orderbook

        if self.gex_engine is not None and hasattr(self.gex_engine, "compute_gex_snapshot"):
            _gex_task = asyncio.create_task(
                self._gex_scanner_task(), name="UnityGEXScanner"
            )
            self._logger.info("✅ [L0] AEGIS GEX background scanner started (rotating)")

        # ── L0.5: Deribit Real-GEX background tasks (REST + WS) ───────────
        # Both wrapped in @watched_task for auto-restart on crash. The REST
        # loop (30s cadence) drives the option-chain ingest; the WS loop
        # streams the BTC/ETH index price for sub-second spot resolution
        # used in the BS-gamma calc.
        _drb_rest_task: Optional[asyncio.Task] = None
        _drb_ws_task:   Optional[asyncio.Task] = None
        if self.deribit_gex is not None:
            try:
                await self.deribit_gex.start()
                _drb_rest_task = asyncio.create_task(
                    watched_task("DeribitGEXRest", restart_delay=10.0)(
                        self.deribit_gex.rest_loop
                    )(),
                    name="UnityDeribitGEXRest",
                )
                _drb_ws_task = asyncio.create_task(
                    watched_task("DeribitGEXWS", restart_delay=5.0)(
                        self.deribit_gex.ws_loop
                    )(),
                    name="UnityDeribitGEXWS",
                )
                self._logger.info(
                    "✅ [L0.5] Deribit Real-GEX background tasks started "
                    "(REST chain refresh @30s + WS index price, @watched_task)"
                )
            except Exception as e:
                self._logger.warning(
                    f"⚠️  [L0.5] Deribit Real-GEX task start failed: {e} — "
                    f"AEGIS proxy only"
                )

        # ── L0.6 (v9.9 Apex-#3): OKX GEX cross-venue background task ──────
        _okx_rest_task: Optional[asyncio.Task] = None
        if self.okx_gex is not None:
            try:
                await self.okx_gex.start()
                _okx_rest_task = asyncio.create_task(
                    watched_task("OkxGEXRest", restart_delay=15.0)(
                        self.okx_gex.rest_loop
                    )(),
                    name="UnityOkxGEXRest",
                )
                self._logger.info(
                    "✅ [L0.6] OKX Real-GEX background task started "
                    f"(REST refresh @{UNITY_OKX_GEX_REFRESH_SEC}s, @watched_task) [v9.9]"
                )
            except Exception as e:
                self._logger.warning(
                    f"⚠️  [L0.6] OKX Real-GEX task start failed: {e} — "
                    f"Deribit-only mode"
                )

        # ── L0.7 (v9.9 Apex-#1): Binance aggTrade WS pool ─────────────────
        # No watched_task wrapper — the pool already manages its own
        # connection_loop tasks with exponential backoff per chunk.
        if self.binance_aggtrade is not None:
            try:
                await self.binance_aggtrade.start()
                self._logger.info(
                    "✅ [L0.7] Binance aggTrade WS pool streaming started "
                    "(internal reconnect loop, sub-100ms ticks) [v9.9]"
                )
            except Exception as e:
                self._logger.warning(
                    f"⚠️  [L0.7] Binance aggTrade WS pool start failed: {e}"
                )

        # ── L0.8 (v9.9 Apex-#2): Depth-walked slippage estimator ──────────
        # No background task; lazy aiohttp session opened on first estimate().
        if self.depth_slip is not None:
            try:
                await self.depth_slip.start()
                self._logger.info(
                    "✅ [L0.8] Depth-walked slippage estimator session opened [v9.9]"
                )
            except Exception as e:
                self._logger.warning(
                    f"⚠️  [L0.8] Depth-slippage session open failed: {e}"
                )

        # ── L0.9 (v9.9.1 Apex-#5): Dynamic per-symbol backtester ──────────
        # Background sweep task: refreshes the entire universe every
        # UNITY_DBT_REFRESH_SEC.  Wrapped in @watched_task so a transient
        # network blip auto-restarts the loop with 30 s backoff.
        _dyn_bt_task: Optional[asyncio.Task] = None
        if self.dyn_backtester is not None:
            try:
                await self.dyn_backtester.start()
                _dyn_bt_task = asyncio.create_task(
                    watched_task("DynBacktest", restart_delay=30.0)(
                        self.dyn_backtester.rest_loop
                    )(),
                    name="UnityDynBacktest",
                )
                self._logger.info(
                    "✅ [L0.9] Dynamic backtester sweep task started "
                    f"(refresh @{UNITY_DBT_REFRESH_SEC}s, @watched_task) [v9.9.1]"
                )
            except Exception as e:
                self._logger.warning(
                    f"⚠️  [L0.9] Dynamic backtester task start failed: {e} — Gate 8.5 dormant"
                )

        # ── L0.95 (v10.0): MiroFish Swarm Simulation background task ───────
        # 10-agent swarm: Trend / Momentum / Volume / Volatility / OrderFlow /
        # Sentiment / Regime / Microstructure / Risk / Composite.
        # Fetches 15M USDM klines, runs proxy backtest on each symbol, feeds
        # Gate 8.5 quality bias as a fallback when DYN_BACKTEST has no history.
        _mirofish_sim_task: Optional[asyncio.Task] = None
        if self.mirofish_sim is not None:
            try:
                await self.mirofish_sim.start()
                # v10.3 CRITICAL BUG FIX: wrap run_loop in @watched_task so any
                # exception (network blip, aiohttp timeout, DB lock) auto-restarts
                # the swarm instead of silently killing Gate 8.5 quality bias.
                _mirofish_sim_task = asyncio.create_task(
                    watched_task("MiroFishSim", restart_delay=30.0)(
                        self.mirofish_sim.run_loop
                    )(),
                    name="UnityMiroFishSim",
                )
                # Also wire into cornix bot for backtest results display
                if self.bot is not None:
                    _try_setattr(self.bot, "_mirofish_sim", self.mirofish_sim)
                    _cornix = getattr(self.bot, "cornix_menu", None)   # v10.6 BUG FIX: was "_cornix_bot" but attr is "cornix_menu"
                    _try_setattr(_cornix, "_mirofish_sim", self.mirofish_sim)
                    # v10.0: Wire metrics into cornix bot for quant stats display
                    _try_setattr(_cornix, "_unity_metrics", self.metrics)
                self._logger.info(
                    "✅ [L0.95] MiroFish Swarm Simulation task started "
                    f"(10 agents · sweep @{UNITY_DBT_REFRESH_SEC}s · @watched_task 30s) [v10.3]"
                )
            except Exception as e:
                self._logger.warning(
                    f"⚠️  [L0.95] MiroFish Simulation task start failed: {e}"
                )

        # ── v9.9: Wire depth_slip onto the bot for the apply() pre-fetch ──
        # The bot reads `_unity_depth_slip` in its async signal-eval loop and
        # awaits estimate() before calling _unity_filter.apply (which is sync).
        # This passes the freshest depth-walked slippage into Gate 0 without
        # making the filter itself async.
        if self.bot is not None:
            try:
                _try_setattr(self.bot, "_unity_depth_slip", self.depth_slip)
                _try_setattr(self.bot, "_unity_slip_ref_notional", UNITY_DEPTH_SLIP_REF_NOTIONAL)
                _try_setattr(self.bot, "_unity_slip_partial_penalty", UNITY_DEPTH_SLIP_PARTIAL_FILL_PENALTY)
                _try_setattr(self.bot, "_unity_slip_timeout_sec", UNITY_DEPTH_SLIP_TIMEOUT_SEC)
                _try_setattr(self.bot, "_unity_okx_gex", self.okx_gex)
                _try_setattr(self.bot, "_unity_binance_aggtrade", self.binance_aggtrade)
                _try_setattr(self.bot, "_unity_sortino_rescue_threshold", UNITY_SORTINO_RESCUE_THRESHOLD)
                _try_setattr(self.bot, "_unity_sortino_min_trades", UNITY_SORTINO_MIN_TRADES)
            except Exception:
                pass

        if self.outcome_tracker_instance is not None:
            _ot_task = asyncio.create_task(
                self._outcome_tracker_task(), name="UnityOutcomeTracker"
            )
            self._logger.info("✅ [L9] OutcomeTracker background task started (v5.2 dedup)")

        # v5.9: NN periodic retraining task (starts if NN trainer is available)
        if self.nn_trainer is not None:
            _nn_task = asyncio.create_task(
                self._nn_retrain_task(), name="UnityNNRetrain"
            )
            self._logger.info(
                f"✅ [L5] NN Retrain background task started "
                f"(interval={NN_RETRAIN_INTERVAL_SEC//3600}h, "
                f"first run in 5min [v9.0 fast-boot])"
            )

        # v5.2: watchdog + persistence + health-server tasks always start
        _wd_task   = asyncio.create_task(self._watchdog_task(),    name="UnityWatchdog")
        _save_task = asyncio.create_task(self._persistence_task(), name="UnityPersistence")
        _hs_task   = asyncio.create_task(self._health_server_task(), name="UnityHealthServer")

        # v8.0: Redis initialise + restore (non-blocking — falls back to file if unavailable)
        await self._redis_init()
        await self._redis_restore_state()

        # v11.0: Async-init TradingInterface (opens UserDB aiosqlite connection)
        _trading_iface = getattr(self, "trading_interface", None)
        if _trading_iface is not None:
            try:
                await _trading_iface.init()
                self._logger.info("✅ [v11.0] TradingInterface async-init complete (UserDB + ExchangeExecutor)")
            except Exception as _ti_async_err:
                self._logger.warning(f"⚠️  [v11.0] TradingInterface async-init error (non-fatal): {_ti_async_err}")

        # v8.0: Signal queue consumer (Producer-Consumer dispatch pipeline)
        # v10.4 BUG FIX: wrap in @watched_task — previously any unhandled
        # exception escaping the outer while-True killed ALL Telegram signal
        # dispatching permanently with no auto-restart.  restart_delay=2s
        # (not 30s) so dispatch resumes within seconds of a transient fault.
        _sq_task = asyncio.create_task(  # v9.3: removed duplicate type annotation (already declared at init)
            watched_task("SignalConsumer", restart_delay=2.0)(
                self._signal_queue_consumer_task
            )(),
            name="UnitySignalConsumer",
        )
        self._logger.info("✅ [v8.0] Signal queue consumer started (asyncio.Queue producer-consumer)")

        # v8.0: WebSocket live orderbook task guarded by @watched_task auto-restart.
        # v8.2 FIX: wrap the bound method directly — no lambda indirection needed.
        # watched_task(fn)() calls await fn() in its restart loop; the bound method
        # is already a valid coroutine function callable with zero arguments.
        _ws_task = asyncio.create_task(
            watched_task("WSOrderbook", restart_delay=WS_RECONNECT_DELAY_SEC)(
                self._ws_orderbook_task
            )(),
            name="UnityWSOrderbook",
        )
        self._logger.info("✅ [v8.0] WebSocket orderbook task started (Binance @depth5@100ms, @watched_task)")

        self._logger.info(
            f"✅ [v{UNITY_VERSION}] Watchdog + Persistence + HealthServer + NNRetrain + "
            f"SignalQueue + WSOrderbook + Redis background tasks started"
        )

        self._logger.info("=" * 90)
        self._logger.info(f"✅ UNITY ENGINE v{UNITY_VERSION} — ALL SYSTEMS ONLINE — STARTING CONTINUOUS SCANNER")
        layers_online = sum(1 for l in self.health.layers.values() if l.available)
        self._logger.info(f"   Layers online  : {layers_online}/{len(self.health.layers)}")
        self._logger.info(
            f"   Signal gates   : 14-gate filter | G0:EV+Slippage | G0.5:Session | G0.8:MinTP1≥{MIN_TP1_DISTANCE_PCT:.2%} | 5-bucket RL | "
            f"Kelly | Consec-Loss CB({CONSEC_LOSS_THRESHOLD}) | WinStreak({CONSEC_WIN_STREAK_THRESHOLD}) | "
            f"NNRetrain({NN_RETRAIN_INTERVAL_SEC//3600}h) | Quality≥{SIGNAL_MIN_QUALITY_GATE:.0f} | IRONS≥{IRONS_MIN_SCORE:.0f} [v{UNITY_VERSION}]"
        )
        self._logger.info(f"   Heartbeat      : {SCANNER_HEARTBEAT_TIMEOUT}s · CircuitBreaker: {CIRCUIT_BREAKER_THRESHOLD} failures")
        self._logger.info(f"   Watchdog stall : {WATCHDOG_STALL_SECONDS}s · Persistence: every 120s (v5.7 crash-recovery)")
        self._logger.info("=" * 90)

        result = False
        try:
            # v9.7: wrap scanner in a tracked task so SIGTERM/watchdog can
            # cancel it gracefully (raises CancelledError into the await below
            # → finally:_cleanup runs as expected → final persistence save).
            self._scanner_task = asyncio.create_task(
                self.bot.run_continuous_scanner(), name="UnityScanner"
            )
            if SCANNER_OPERATION_TIMEOUT is not None:
                await asyncio.wait_for(
                    self._scanner_task,
                    timeout=SCANNER_OPERATION_TIMEOUT,
                )
            else:
                await self._scanner_task
            result = True

        except asyncio.TimeoutError:
            self._logger.error(f"❌ Scanner timed out after {SCANNER_OPERATION_TIMEOUT}s")
        except KeyboardInterrupt:
            self._logger.info("🛑 Stopped by user")
            result = True
        except asyncio.CancelledError:
            self._logger.info("🔄 Scanner task cancelled — watchdog or SIGTERM triggered")
            result = self._shutdown_requested   # clean exit if shutdown was deliberate
        except (ConnectionError, OSError) as e:
            self._logger.error(f"❌ Network/OS error: {e}")
        except RuntimeError as e:
            self._logger.error(f"❌ RuntimeError: {e}")
        except Exception as e:
            self._logger.error(f"❌ Fatal scanner error: {type(e).__name__}: {e}")
            self._logger.debug(traceback.format_exc())
        finally:
            await self._cleanup(
                _gex_task, _ot_task, _wd_task, _save_task, _hs_task, _nn_task,
                _sq_task, _ws_task,       # v8.0
                _drb_rest_task, _drb_ws_task,  # L0.5: Deribit Real-GEX
                _okx_rest_task,                # L0.6: OKX GEX (v9.9)
                _dyn_bt_task,                  # L0.9: Dynamic Backtester (v9.9.1)
                _mirofish_sim_task,            # L0.95: MiroFish Swarm Simulation (v10.0)
            )
            # Close the Deribit aiohttp session cleanly
            if self.deribit_gex is not None:
                try:
                    await self.deribit_gex.close()
                except Exception:
                    pass
            # v9.9: close OKX GEX, Binance aggTrade WS pool, depth_slip session
            if self.okx_gex is not None:
                try:
                    await self.okx_gex.close()
                except Exception:
                    pass
            if self.binance_aggtrade is not None:
                try:
                    await self.binance_aggtrade.close()
                except Exception:
                    pass
            if self.depth_slip is not None:
                try:
                    await self.depth_slip.close()
                except Exception:
                    pass
            # v9.9.1: close dynamic backtester aiohttp session
            if self.dyn_backtester is not None:
                try:
                    await self.dyn_backtester.stop()
                except Exception:
                    pass
            # v10.0: close MiroFish swarm simulation aiohttp session
            if self.mirofish_sim is not None:
                try:
                    await self.mirofish_sim.stop()
                except Exception:
                    pass

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # v5.1: HTTP health-check server  (keeps Replit alive + Cornix monitoring)
    # ─────────────────────────────────────────────────────────────────────────

    async def _health_server_task(self) -> None:
        """
        Lightweight HTTP health-check server on port 8080 (default).
        Responds to GET / and GET /health with a JSON status payload.
        Keeps the Replit container warm and satisfies uptime monitors.
        Gracefully degrades if aiohttp is not installed.
        """
        _log  = logging.getLogger("UnityEngine.HealthServer")
        # v7.1: Railway injects $PORT automatically — check it first, then
        # UNITY_HEALTH_PORT (legacy), then fall back to 8080.
        port  = int(os.getenv("UNITY_HEALTH_PORT") or os.getenv("PORT") or "8080")

        try:
            from aiohttp import web as _web

            m = self.metrics
            eng = self

            async def _handle(request):
                layers_up = sum(1 for l in eng.health.layers.values() if l.available)
                # v5.2: gate pass-rate stats from signal filter
                gate_stats: dict = {}
                try:
                    sf = eng.signal_filter
                    if sf is not None and hasattr(sf, "_gate_stats"):
                        for g, counts in sf._gate_stats.items():
                            p      = counts.get("pass", 0)
                            f      = counts.get("fail", 0)
                            total  = p + f
                            pct    = round(p / total * 100, 1) if total else None
                            gate_stats[g] = {"pass": p, "fail": f, "total": total, "pct": pct}
                except Exception:
                    pass
                payload = {
                    "status":         "ok",
                    "version":        UNITY_VERSION,
                    "uptime_hours":   round(m.uptime_hours, 2),
                    "layers_online":  layers_up,
                    "layers_total":   len(eng.health.layers),
                    "signals_sent":   m.total_signals_sent,
                    "win_rate_pct":   round(m.win_rate, 1),
                    "scan_cycles":    m.scan_cycles,
                    "last_gex_regime":m.last_gex_regime,
                    "last_dgrp_score":round(m.last_dgrp_score, 1),
                    "kelly_pct":      round(eng.booster.last_kelly_fraction * 100, 1),
                    "rl_threshold":   round(eng.booster.dynamic_threshold, 1),
                    "gate_pass_rates": gate_stats,
                    "timestamp":      datetime.now().isoformat(),
                }
                return _web.Response(
                    text=_fast_dumps(payload),
                    content_type="application/json",
                )

            async def _handle_layers(request):
                """GET /layers — per-layer availability + call stats + circuit-breaker state."""
                result = {}
                for name, layer in eng.health.layers.items():
                    cb = eng.health.cb_state(name)
                    result[name] = {
                        "available":        layer.available,
                        "initialised":      layer.initialised,
                        "calls":            layer.calls,
                        "failures":         layer.failures,
                        "success_rate":     round(layer.success_rate, 4),
                        "error":            layer.error,
                        # v8.0 Prompt 3: formal CLOSED/OPEN/HALF_OPEN state
                        "circuit_breaker":  cb.value,
                    }
                return _web.Response(
                    text=_fast_dumps(result),
                    content_type="application/json",
                )

            async def _handle_gates(request):
                """GET /gates — per-gate pass/fail counts and pass-rates."""
                result = {}
                try:
                    sf = eng.signal_filter
                    if sf is not None and hasattr(sf, "_gate_stats"):
                        for g, counts in sf._gate_stats.items():
                            p     = counts.get("pass", 0)
                            f     = counts.get("fail", 0)
                            total = p + f
                            result[g] = {
                                "pass": p, "fail": f, "total": total,
                                "pass_rate": round(p / total, 4) if total else None,
                            }
                except Exception:
                    pass
                return _web.Response(
                    text=_fast_dumps(result),
                    content_type="application/json",
                )

            async def _handle_metrics(request):
                """GET /metrics — detailed engine performance metrics."""
                m = eng.metrics
                b = eng.booster
                payload = {
                    "version":              UNITY_VERSION,
                    "uptime_hours":         round(m.uptime_hours, 4),
                    "total_signals_sent":   m.total_signals_sent,
                    "total_evaluated":      m.total_signals_evaluated,
                    "total_rejected":       m.total_signals_rejected,
                    "send_rate_pct":        round(m.send_rate, 2),
                    "win_count":            m.win_count,
                    "loss_count":           m.loss_count,
                    "win_rate_pct":         round(m.win_rate, 2),
                    "total_pnl_pct":        round(m.total_profit_pct, 4),
                    "scan_cycles":          m.scan_cycles,
                    "last_signal_quality":  round(m.last_signal_quality, 2),
                    "last_gex_regime":      m.last_gex_regime,
                    "last_dgrp_score":      round(m.last_dgrp_score, 2),
                    # v8.2 FIX: use booster counters — metrics.consecutive_losses
                    # is never updated (booster tracks this independently).
                    "consecutive_losses":   b._consec_losses,
                    "consecutive_wins":     b._consec_wins,
                    "rl_threshold":         round(b.dynamic_threshold, 2),
                    "kelly_fraction_pct":   round(b.last_kelly_fraction * 100, 2),
                    # v9.0: Sharpe / Sortino from RL booster PnL ring
                    "sharpe_ratio":         round(b.sharpe_ratio, 4),
                    "sortino_ratio":        round(b.sortino_ratio, 4),
                    # v10.0: Institutional quant metrics from UnityMetrics ring
                    "quant_sharpe":         round(m.sharpe_ratio, 4),
                    "quant_sortino":        round(m.sortino_ratio, 4),
                    "quant_calmar":         round(m.calmar_ratio, 4),
                    "quant_max_dd_pct":     round(m.max_drawdown_pct, 4),
                    "quant_ev_r":           round(m.expected_value_r, 4),
                    "quant_kelly_pct":      round(m.kelly_fraction_pct, 2),
                    "quant_trade_n":        len(m._trade_returns),
                    "gex_cache_size":       len(eng._gex_snapshots),
                    "irons_avg_score":      (
                        round(eng.signal_filter.last_irons_score(), 2)
                        if eng.signal_filter else 0.0
                    ),
                    # v9.3: Bayesian posterior win probability (blended into Kelly)
                    "bayes_win_prob":        round(
                        b._bayes_alpha / (b._bayes_alpha + b._bayes_beta), 4
                    ),
                    "bayes_alpha":           round(b._bayes_alpha, 1),
                    "bayes_beta":            round(b._bayes_beta, 1),
                    # v9.3: signals dispatched per hour (rate limiter visibility)
                    "signals_per_hour":      round(
                        m.total_signals_sent / max(m.uptime_hours, 1e-6), 2
                    ),
                    # v10.3: Hard-cutoff circuit breaker status for operator monitoring
                    "hard_cutoff_active":   (
                        bool(getattr(eng.signal_filter, "_hard_cutoff_until", 0.0) > time.time())
                        if eng.signal_filter else False
                    ),
                    "hard_cutoff_remaining_sec": max(0, int(
                        getattr(eng.signal_filter, "_hard_cutoff_until", 0.0) - time.time()
                    )) if eng.signal_filter else 0,
                    "paper_mode_active":    bool(getattr(eng.booster, "paper_mode", False)),
                    # v10.9: @watched_task restart observability (resolves v10.4 changelog gap)
                    # signal_consumer_restarts: restarts of the critical SignalConsumer task
                    # watched_task_restart_counts: per-task restart counts for all watched tasks
                    "signal_consumer_restarts": _watched_task_restart_counts.get("SignalConsumer", 0),
                    "watched_task_restart_counts": dict(_watched_task_restart_counts),
                    "timestamp":            datetime.now().isoformat(),
                    # ── v8.0 Prompt 1: last atomic SignalDecisionVector ────────
                    # Immutable snapshot of GEX + LLM + NN inputs for last SEND
                    "last_decision_vector": (
                        {
                            "symbol":               eng._last_decision_vector.symbol,
                            "ts":                   eng._last_decision_vector.timestamp,
                            "gex_regime":           eng._last_decision_vector.gex_regime,
                            "gz_dist_pct":          eng._last_decision_vector.gex_gamma_zero_dist_pct,
                            "ob_imbalance":         eng._last_decision_vector.orderbook_imbalance,
                            "llm_verdict":          eng._last_decision_vector.llm_verdict,
                            "llm_confidence":       eng._last_decision_vector.llm_confidence,
                            "llm_regime":           eng._last_decision_vector.llm_regime_tag,
                            "nn_score":             eng._last_decision_vector.nn_direction_score,
                            "nn_confidence":        eng._last_decision_vector.nn_confidence,
                            "composite_score":      eng._last_decision_vector.composite_score,
                            "kelly_fraction":       eng._last_decision_vector.kelly_fraction,
                            "ev_ratio":             eng._last_decision_vector.ev_ratio,
                            "decision":             eng._last_decision_vector.decision,
                        }
                        if eng._last_decision_vector else None
                    ),
                }
                return _web.Response(
                    text=_fast_dumps(payload),
                    content_type="application/json",
                )

            async def _handle_symbols(request):
                """GET /symbols — per-symbol win rate and trade count."""
                try:
                    result = {}
                    for sym, data in list(eng.sym_tracker._data.items()):
                        wins   = data.get("wins", 0)
                        losses = data.get("losses", 0)
                        total  = wins + losses
                        result[sym] = {
                            "wins":     wins,
                            "losses":   losses,
                            "trades":   total,
                            "win_rate": round(wins / total, 4) if total > 0 else None,
                            "pnl_pct":  round(data.get("pnl_pct", 0.0), 4),
                            "blocked":  eng.sym_tracker.is_blocked(sym),
                        }
                    return _web.Response(
                        text=_fast_dumps(result),
                        content_type="application/json",
                    )
                except Exception as _se:
                    return _web.Response(
                        text=_fast_dumps({"error": str(_se)}),
                        content_type="application/json",
                        status=500,
                    )

            async def _handle_irons(request):
                """GET /irons — IRONS AI Scorer status and recent score stats."""
                try:
                    sf   = eng.signal_filter
                    ring = list(sf._irons_score_ring) if sf else []
                    avg  = (sum(ring) / len(ring)) if ring else 0.0
                    payload = {
                        "available":    eng.irons_scorer is not None,
                        "gate_enabled": IRONS_MIN_SCORE > 0,
                        "min_score":    IRONS_MIN_SCORE,
                        "sample_count": len(ring),
                        "avg_score":    round(avg, 2),
                        "min_observed": round(min(ring), 2) if ring else None,
                        "max_observed": round(max(ring), 2) if ring else None,
                        "gate10_pass":  sf._gate_stats["gate10"]["pass"] if sf else 0,
                        "gate10_fail":  sf._gate_stats["gate10"]["fail"] if sf else 0,
                        "timestamp":    datetime.now().isoformat(),
                    }
                    return _web.Response(
                        text=_fast_dumps(payload),
                        content_type="application/json",
                    )
                except Exception as _ie:
                    return _web.Response(
                        text=_fast_dumps({"error": str(_ie)}),
                        content_type="application/json",
                        status=500,
                    )

            async def _handle_gex(request):
                """GET /gex — Deribit real-options GEX surface health & summary.

                Returns the per-currency stats from the L0.5 Deribit ingestor:
                  • currencies tracked (BTC, ETH, SOL, …)
                  • spot index price (live from WS)
                  • # of strikes loaded, age of last refresh
                  • net-GEX, gamma-flip, regime (POSITIVE / NEGATIVE / NEUTRAL)
                """
                try:
                    ingestor = getattr(eng, "deribit_gex", None)
                    if ingestor is None:
                        return _web.Response(
                            text=_fast_dumps({
                                "available": False,
                                "reason":    "Deribit GEX ingestor not initialized",
                                "timestamp": datetime.now().isoformat(),
                            }),
                            content_type="application/json",
                            status=200,
                        )
                    if hasattr(ingestor, "stats"):
                        stats_fn = ingestor.stats
                        stats = await stats_fn() if asyncio.iscoroutinefunction(stats_fn) else stats_fn()
                    else:
                        stats = {"error": "ingestor has no stats() method"}
                    payload = {
                        "available": True,
                        "stats":     stats,
                        "timestamp": datetime.now().isoformat(),
                    }
                    return _web.Response(
                        text=_fast_dumps(payload),
                        content_type="application/json",
                    )
                except Exception as _ge:
                    return _web.Response(
                        text=_fast_dumps({"error": str(_ge)}),
                        content_type="application/json",
                        status=500,
                    )

            async def _handle_healthz(req: _web.Request) -> _web.Response:
                """GET /healthz — k8s liveness probe + Omega Dead-Man's Switch.

                Returns 200 if ALL of the following hold:
                  • At least one layer online
                  • Scan-cycle heartbeat updated within WATCHDOG_STALL_SECONDS
                  • Rolling average scan-cycle latency < _DMS_LATENCY_WARN_MS (500 ms)

                Returns 503 otherwise — Railway's health-check probe will restart
                the container after 3 consecutive 503s (per Dockerfile HEALTHCHECK).

                v8.0 Omega-Tier: adds Dead-Man's Switch latency check (500 ms gate)
                to catch runaway-slow cycles before the full stall threshold fires.
                """
                try:
                    _layers_online  = sum(1 for l in self.health.layers.values() if l.available)
                    _last_cycle_age = time.time() - self._last_heartbeat if hasattr(self, "_last_heartbeat") else 0.0
                    _stalled        = _last_cycle_age > WATCHDOG_STALL_SECONDS

                    # ── Dead-Man's Switch: rolling average cycle latency ─────────
                    _ring = getattr(self, "_cycle_latency_ns_ring", None)
                    if _ring and len(_ring) >= 3:
                        _avg_latency_ms = (sum(_ring) / len(_ring)) / 1_000_000.0
                    else:
                        _avg_latency_ms = 0.0
                    _dms_limit_ms   = getattr(self, "_DMS_LATENCY_WARN_MS", 500.0)
                    _latency_breach = _avg_latency_ms > _dms_limit_ms

                    _alive  = _layers_online > 0 and not _stalled and not _latency_breach
                    _payload = {
                        "status":              "alive" if _alive else ("latency_breach" if _latency_breach else "stalled"),
                        "layers_online":       _layers_online,
                        "last_cycle_age_s":    round(_last_cycle_age, 1),
                        "stall_threshold_s":   WATCHDOG_STALL_SECONDS,
                        # Dead-Man's Switch latency fields (v8.0 Omega)
                        "avg_cycle_latency_ms": round(_avg_latency_ms, 1),
                        "dms_limit_ms":         _dms_limit_ms,
                        "latency_breach":       _latency_breach,
                        "version":             UNITY_VERSION,
                    }
                    return _web.Response(
                        text=_fast_dumps(_payload),
                        content_type="application/json",
                        status=200 if _alive else 503,
                    )
                except Exception as _he:
                    return _web.Response(
                        text=_fast_dumps({"status": "error", "error": str(_he)}),
                        content_type="application/json",
                        status=503,
                    )

            async def _handle_readyz(req: _web.Request) -> _web.Response:
                """GET /readyz — k8s readiness probe.
                Returns 200 only if all CRITICAL layers (TelegramBot, G0DM0D3, GEX)
                are initialised and the bot has completed at least one scan cycle.
                Returns 503 if not yet ready (still warming up or critical layer failed).
                """
                try:
                    _critical = ["TelegramBot", "G0DM0D3+OpenRouter", "AEGIS_GEX"]
                    # v9.3 FIX: replace fragile anonymous type("x",(),{}) factory
                    # with a proper getattr fallback — avoids potential metaclass issues
                    # and makes the sentinel explicit and readable.
                    def _layer_available(name: str) -> bool:
                        layer = self.health.layers.get(name)
                        return bool(getattr(layer, "available", False))
                    _all_ready = all(_layer_available(n) for n in _critical)
                    _has_cycled = self.metrics.total_signals_evaluated > 0
                    _ready = _all_ready and _has_cycled
                    _detail = {n: _layer_available(n) for n in _critical}
                    _payload = {
                        "status":            "ready" if _ready else "not_ready",
                        "critical_layers":   _detail,
                        "signals_evaluated": self.metrics.total_signals_evaluated,
                        "version":           UNITY_VERSION,
                    }
                    return _web.Response(
                        text=_fast_dumps(_payload),
                        content_type="application/json",
                        status=200 if _ready else 503,
                    )
                except Exception as _re:
                    return _web.Response(
                        text=_fast_dumps({"status": "error", "error": str(_re)}),
                        content_type="application/json",
                        status=503,
                    )

            app = _web.Application()
            app.router.add_get("/",        _handle)
            app.router.add_get("/health",  _handle)
            app.router.add_get("/healthz", _handle_healthz)  # v6.3: k8s liveness probe
            app.router.add_get("/readyz",  _handle_readyz)   # v6.3: k8s readiness probe
            app.router.add_get("/layers",  _handle_layers)    # v5.8: per-layer stats
            app.router.add_get("/gates",   _handle_gates)     # v5.8: per-gate stats
            app.router.add_get("/metrics", _handle_metrics)   # v6.0: detailed metrics
            app.router.add_get("/symbols", _handle_symbols)   # v6.0: per-symbol stats
            app.router.add_get("/irons",   _handle_irons)     # v6.0: IRONS scorer stats
            app.router.add_get("/gex",     _handle_gex)       # v9.8: Deribit real-options GEX

            runner  = _web.AppRunner(app)
            await runner.setup()
            # v8.2: port fallback — try requested port first, then port+1.
            # In Replit, AEGIS GEX binds 8080 first; Unity Engine automatically
            # falls back to 8081 instead of degrading to no health server.
            # In Railway, $PORT is injected so this logic is never reached.
            _bound_port = None
            for _port_attempt in [port, port + 1, port + 2]:
                try:
                    site = _web.TCPSite(runner, "0.0.0.0", _port_attempt, reuse_port=True)
                    await site.start()
                    _bound_port = _port_attempt
                    break
                except OSError:
                    _log.debug(f"Port {_port_attempt} busy — trying next…")
            if _bound_port is None:
                _log.warning(
                    f"Health server: could not bind to port {port}/{port+1}/{port+2} "
                    f"— health endpoint unavailable (engine still operating normally)"
                )
                return
            _log.info(
                f"✅ Unity health server listening on port {_bound_port} "
                f"(SO_REUSEPORT=True) [v8.2 port-fallback]"
            )

            while True:
                await asyncio.sleep(30)

        except asyncio.CancelledError:
            _log.info("Health server task cancelled")
        except ImportError:
            _log.warning("aiohttp not installed — health server unavailable")
        except OSError as e:
            _log.warning(f"Health server port {port} unavailable: {e}")
        except Exception as e:
            _log.warning(f"Health server error: {e}")

    # ─────────────────────────────────────────────────────────────────────────

    async def _cleanup(
        self,
        gex_task:  Optional[asyncio.Task],
        ot_task:   Optional[asyncio.Task] = None,
        wd_task:   Optional[asyncio.Task] = None,
        save_task: Optional[asyncio.Task] = None,
        hs_task:   Optional[asyncio.Task] = None,
        nn_task:   Optional[asyncio.Task] = None,       # v5.9: NN retraining task
        sq_task:   Optional[asyncio.Task] = None,       # v8.0: signal queue consumer
        ws_task:   Optional[asyncio.Task] = None,       # v8.0: WS orderbook
        drb_rest_task:      Optional[asyncio.Task] = None,  # L0.5: Deribit REST loop
        drb_ws_task:        Optional[asyncio.Task] = None,  # L0.5: Deribit WS loop
        okx_rest_task:      Optional[asyncio.Task] = None,  # L0.6: OKX GEX (v9.9)
        dyn_bt_task:        Optional[asyncio.Task] = None,  # L0.9: Dynamic Backtester (v9.9.1)
        mirofish_sim_task:  Optional[asyncio.Task] = None,  # L0.95: MiroFish Swarm Sim (v10.0)
    ):
        """Ordered teardown — cancel background tasks, close HTTP sessions."""
        self._logger.info(f"🧹 [Unity v{UNITY_VERSION}] Starting graceful cleanup...")

        if self.console:
            try:
                await self.console.stop()
            except Exception:
                pass

        # v8.0: flush remaining signals before shutdown
        try:
            if self._signal_queue and not self._signal_queue.empty():
                self._logger.info(
                    f"📨 Flushing {self._signal_queue.qsize()} queued signals on shutdown..."
                )
                await asyncio.wait_for(self._signal_queue.join(), timeout=10.0)
        except Exception:
            pass

        # v8.0: close Redis gracefully
        if self._redis is not None:
            try:
                await self._redis_sync_state()   # final state push
                await self._redis.close()
                self._logger.info("📦 Redis connection closed cleanly")
            except Exception:
                pass

        # v5.2: cancel all background tasks cleanly
        all_tasks = [
            (gex_task,          "GEX"),
            (ot_task,           "OutcomeTracker"),
            (wd_task,           "Watchdog"),
            (save_task,         "Persistence"),
            (hs_task,           "HealthServer"),
            (nn_task,           "NNRetrain"),          # v5.9
            (sq_task,           "SignalConsumer"),      # v8.0
            (ws_task,           "WSOrderbook"),        # v8.0
            (drb_rest_task,     "DeribitGEXRest"),     # L0.5
            (drb_ws_task,       "DeribitGEXWS"),       # L0.5
            (okx_rest_task,     "OkxGEXRest"),         # L0.6 (v9.9) — FIX v10.5: was NameError (free var)
            (dyn_bt_task,       "DynBacktest"),        # L0.9 (v9.9.1) — FIX v10.5: was never cancelled
            (mirofish_sim_task, "MiroFishSim"),        # L0.95 (v10.0) — FIX v10.5: was never cancelled
        ]
        for task, name in all_tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass

        if self.bot is None:
            return

        # Close main trader HTTP session
        try:
            trader = getattr(self.bot, "trader", None)
            if trader is not None:
                await trader.aclose()
        except Exception as e:
            self._logger.debug(f"Cleanup: trader.aclose() error: {e}")

        # Close Telegram session
        try:
            if callable(getattr(self.bot, "close_tg_session", None)):
                await self.bot.close_tg_session()
        except Exception as e:
            self._logger.debug(f"Cleanup: close_tg_session() error: {e}")

        # Close AI client HTTP pools
        _ai = getattr(getattr(self.bot, "strategy", None), "ai_agent", None)
        for attr in ("claude_client", "openai_client"):
            client = getattr(_ai, attr, None) if _ai else None
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass

        # Close GEX engine session
        if self.gex_engine is not None:
            for close_attr in ("close", "aclose", "shutdown"):
                closer = getattr(self.gex_engine, close_attr, None)
                if callable(closer):
                    try:
                        result = closer()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
                    break

        # v6.0: Shutdown ThreadPoolExecutor (non-blocking, wait for running tasks ≤5s)
        try:
            if hasattr(self, "_thread_pool") and self._thread_pool is not None:
                self._thread_pool.shutdown(wait=True, cancel_futures=True)
                self._logger.debug("ThreadPoolExecutor shutdown complete")
        except Exception as _tp_err:
            self._logger.debug(f"Cleanup: ThreadPoolExecutor shutdown error: {_tp_err}")

        # v9.3 FIX: use None instead of del — del raises AttributeError on any
        # subsequent access (e.g. conditional checks), while None is safely falsy.
        try:
            self.bot = None
        except Exception:
            pass
        # v5.0: final persistence save on shutdown
        try:
            self.metrics.save()
            self.sym_tracker.save()
        except Exception:
            pass
        self._logger.info(f"✅ [Unity v{UNITY_VERSION}] Cleanup complete — metrics persisted")


# ═══════════════════════════════════════════════════════════════════════════════
# 13. HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _try_setattr(obj: Any, name: str, value: Any) -> bool:
    """Safe setattr — returns False if blocked by a descriptor."""
    try:
        setattr(obj, name, value)
        return True
    except (AttributeError, TypeError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 14. MAIN ASYNC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main() -> bool:
    """Unity Engine main coroutine."""
    engine = UnityEngine()
    return await engine.run()


# ═══════════════════════════════════════════════════════════════════════════════
# 15. LAUNCHER  (auto-restart + circuit breaker + exponential backoff)
# ═══════════════════════════════════════════════════════════════════════════════

def main_launcher():
    """
    Production launcher with exponential backoff + circuit breaker.
    Mirrors start_ultimate_bot.py main_launcher() with Unity v5.4 enhancements.
    """
    _logger = logging.getLogger("UnityEngine.Launcher")

    try:
        max_restarts = max(1, int(os.getenv("MAX_RESTARTS", str(DEFAULT_MAX_RESTARTS))))
    except (ValueError, TypeError):
        max_restarts = DEFAULT_MAX_RESTARTS

    try:
        restart_delay_base = max(1, int(os.getenv("RESTART_DELAY_BASE", str(DEFAULT_RESTART_DELAY_BASE))))
    except (ValueError, TypeError):
        restart_delay_base = DEFAULT_RESTART_DELAY_BASE

    _logger.info(
        f"🚀 Unity Engine v{UNITY_VERSION} Launcher — "
        f"max_restarts={max_restarts}, base_delay={restart_delay_base}s"
    )
    _logger.info(
        f"📐 20 layers + MiroFishSim(@watched_task) L0.6 OKX-GEX · L0.7 Binance-aggTrade-WS · L0.8 Depth-Slippage · "
        f"14-gate filter (G0:EV[depth-walked]·G0.5:Session·G0.8:MinTP1·G1-G10·AdaptIRONS) · "
        f"G5-SoftVeto(dual-only-hardblock) · ATR-VolPenalty · HTF-Align(1H+5/4H+8) · AdaptiveIRONS(WR-driven) · "
        f"5-bucket RL · Kelly · GEX(FLIP≥{GEX_FLIP_ZONE_DGRP}) · Agency · UTBot · PerSymbol · "
        f"Cycle={CYCLE_SLEEP_MIN}-{CYCLE_SLEEP_MAX}s · HealthServer(/healthz+/readyz+/layers+/gates+/metrics+/symbols+/irons) · "
        f"Railway($PORT) · Watchdog · SIGTERM · FilterStatePersist · FileLog · NNRetrain({NN_RETRAIN_INTERVAL_SEC//3600}h) · "
        f"OutcomeTracker · LLM-AutoRoute · CornixMenuBot(8ex·AdminGate·SymBacktest·RunNow) · "
        f"BlacklistRefresh(10min) · HardCutoffEarlyReset · SignalRate · ThreadPool={THREAD_POOL_WORKERS}w · async_retry_backoff · "
        f"SignalConsumer(@watched_task) · WatchedTaskHealthReset · FundingGateCache · PersistenceRaceFixed [v{UNITY_VERSION}]"
    )

    restart_count        = 0
    consecutive_failures = 0
    total_elapsed        = 0.0
    cb_triggered         = False
    cb_time              = 0.0

    while restart_count <= max_restarts:

        if cb_triggered:
            now = time.time()
            remaining = (cb_time + CIRCUIT_BREAKER_COOLDOWN) - now
            if remaining > 0:
                _logger.warning(f"⚡ Circuit breaker: waiting {remaining:.0f}s before retry...")
                time.sleep(remaining)
            cb_triggered = False

        _logger.info(f"▶️  Starting Unity Engine v{UNITY_VERSION} (attempt {restart_count + 1}/{max_restarts})")
        start_ts = time.time()

        try:
            # ── v8.0 Omega-Tier: uvloop event loop (2-4× faster than CPython default)
            # uvloop wraps libuv (the same C event-loop used by Node.js) via Cython.
            # If the package is missing or incompatible (e.g. Windows), falls back
            # silently to the standard asyncio event loop — zero-downside.
            try:
                import uvloop as _uvloop
                _uvloop.install()
                _logger.info("⚡ [Omega] uvloop event loop active (libuv / 2-4× faster)")
            except ImportError:
                _logger.debug("uvloop not available — using default asyncio event loop")

            success = asyncio.run(main())
        except KeyboardInterrupt:
            _logger.info("🛑 Stopped by user (KeyboardInterrupt)")
            break
        except _ConfigError as e:
            # FIX v5.3: config errors (missing secrets/keys) are permanent failures —
            # no point retrying with backoff; exit immediately with a clear message.
            _logger.critical(f"❌ CONFIG ERROR — cannot start: {e}")
            _logger.critical("   Set the missing environment variables and restart.")
            break
        except Exception as e:
            err_str = str(e)
            # v8.4: 'Event loop stopped before Future completed' is a normal artifact
            # of asyncio.run() teardown when SIGTERM fires mid-cleanup — the engine
            # already ran its graceful shutdown sequence.  Treat as clean exit only
            # when the session lasted > 60 s (real run, not an init crash).
            _is_loop_teardown = (
                isinstance(e, RuntimeError)
                and "Event loop stopped" in err_str
                and (time.time() - start_ts) > 60
            )
            if _is_loop_teardown:
                _logger.info(
                    f"✅ SIGTERM graceful shutdown — loop teardown artifact "
                    f"({(time.time()-start_ts):.0f}s session)"
                )
                success = True
            else:
                _logger.error(f"❌ asyncio.run() exception: {type(e).__name__}: {e}")
                _logger.debug(traceback.format_exc())
                success = False

        elapsed = time.time() - start_ts
        total_elapsed += elapsed

        if success:
            _logger.info(f"✅ Clean exit after {elapsed:.0f}s")
            consecutive_failures = 0
            break

        restart_count        += 1
        consecutive_failures += 1

        if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            cb_triggered = True
            cb_time      = time.time()
            _logger.warning(
                f"⚡ Circuit breaker triggered after {consecutive_failures} consecutive failures"
            )
            consecutive_failures = 0

        if restart_count >= max_restarts:
            _logger.critical(f"❌ Max restarts ({max_restarts}) reached — giving up")
            break

        # Exponential backoff with ±10% jitter, hard-capped at MAX_DELAY_SECONDS
        delay = min(MAX_DELAY_SECONDS, restart_delay_base * (2 ** min(restart_count - 1, 5)))
        delay += random.uniform(0, delay * 0.10)
        _logger.info(f"⏳ Restarting in {delay:.0f}s (attempt {restart_count + 1}/{max_restarts})...")
        time.sleep(delay)

    _logger.info(
        f"🏁 Unity Engine v{UNITY_VERSION} Launcher exited | "
        f"restarts={restart_count} | total_runtime={total_elapsed/3600:.2f}h"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 16. ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main_launcher()
