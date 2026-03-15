# Trading Agency Framework - Integration Guide

## Overview
The Perfect Scalping Bot now includes a **Trading Agency Framework** - a multi-agent system inspired by the agency-agents repository architecture. Each specialized agent runs in parallel for maximum efficiency and accuracy.

## 🎭 The Trading Agency - 6 Specialized Agents

### 1. 📊 Signal Analysis Agent
**Expertise**: Market data analysis, technical indicator calculation, signal generation
- Analyzes 20+ technical indicators
- Calculates combined signal strength (0-100)
- Identifies optimal trading opportunities
- Parallel processing: Works independently of other agents

### 2. 🛡️ Risk Management Agent
**Expertise**: Risk validation, leverage calculation, position sizing
- Validates price ordering (SL < Entry < TP levels)
- Calculates risk-reward ratios
- Recommends optimal leverage (25x-50x based on volatility)
- Ensures compliance with risk parameters

### 3. ⚡ Trade Execution Agent
**Expertise**: Order placement, trade monitoring, TP/SL management
- Opens and tracks active trades
- Monitors price levels for TP/SL hits
- Manages trade state machine
- Updates Cornix webhook integration

### 4. 📈 Performance Analytics Agent
**Expertise**: Performance tracking, statistics, trade logging
- Tracks win rate and profit metrics
- Maintains trade history
- Calculates average profit per trade
- Provides real-time performance dashboard

### 5. 📊 CVD Analysis Agent
**Expertise**: Volume delta calculation, market bias detection
- Calculates Cumulative Volume Delta
- Detects price-volume divergences
- Identifies market bias (bullish/bearish/neutral)
- Rate-limited API calls (60-second cache)

### 6. 🧠 ML Prediction Agent
**Expertise**: Trade outcome prediction, signal filtering, accuracy improvement
- Predicts trade success probability
- Filters signals based on ML confidence
- Boosts confidence when CVD aligns with signal
- Learns from historical trade outcomes

## 🔄 Agent Coordination & Parallel Processing

### Signal Generation Pipeline (Fully Parallel)
```
Signal Analysis Agent ──┐
                       ├─→ (Combined Result)
CVD Analysis Agent    ──┤
                       │
Risk Management Agent ─┤
ML Prediction Agent ───┘
```

**All agents run concurrently:**
```python
# Execute independent analyses in parallel
signal_result, cvd_result = await asyncio.gather(
    signal_agent.process(...),
    cvd_agent.process(...)
)
```

### Trade Execution Pipeline
```
Signal Results ────→ Risk Validation ────→ ML Filtering ────→ Execute Trade
                     (Serial validation)
```

## 🚀 Integration Points in Bot

### 1. Bot Initialization
```python
# Automatically initialized in __init__
self.agency_coordinator = TradingAgencyCoordinator(self.logger, self.ml_analyzer)
```

### 2. Signal Generation
Replace existing signal generation with agent-based processing:
```python
# Call the agency for signal generation
result = await self.agency_coordinator.process_signal_generation(
    market_data=df,
    indicators=indicators,
    cvd_data=self.cvd_data
)

if result['signal_generated']:
    signal = result['signal']
    # Signal includes: optimal_leverage, risk_validated, ml_confidence
```

### 3. Trade Execution
```python
# Use execution agent for order placement
exec_result = await self.agency_coordinator.process_trade_execution(signal)
```

### 4. Trade Monitoring
```python
# Use execution agent for monitoring
monitor_result = await self.agency_coordinator.process_trade_monitoring(
    symbol=symbol,
    current_price=price
)
```

### 5. Performance Tracking
```python
# Use analytics agent for tracking
await self.agency_coordinator.analytics_agent.process(trade_data={...})
```

## 📊 Agent Status Monitoring

Get real-time status of all agents:
```python
status = self.agency_coordinator.get_agency_status()
# Returns:
# {
#     'coordinator': 'TradingAgencyCoordinator',
#     'agents_count': 6,
#     'agent_status': {
#         'Signal Analysis Agent': {'status': 'ready', 'last_result_timestamp': ...},
#         'Risk Management Agent': {'status': 'ready', ...},
#         ...
#     }
# }
```

## ⚙️ Configuration & Tuning

### Risk Management Parameters
```python
agent = RiskManagementAgent(logger)
agent.max_leverage = 50          # Maximum leverage
agent.min_leverage = 25          # Minimum leverage
agent.max_risk_per_trade = 0.025 # 2.5% max risk
```

### CVD Caching (Reduce API Load)
```python
agent = CVDAnalysisAgent(logger)
agent.cache_duration = 60  # Cache for 60 seconds
```

### ML Confidence Threshold
```python
agent = MLPredictionAgent(logger, ml_analyzer)
# Filters signals with confidence < 75%
```

## 🎯 Key Benefits

1. **Parallel Processing**: All independent agents run simultaneously
2. **Specialization**: Each agent is optimized for its domain
3. **Modularity**: Easy to add/remove/upgrade agents
4. **Scalability**: Framework supports unlimited agent additions
5. **Monitoring**: Built-in status tracking for all agents
6. **Error Isolation**: Agent failures don't crash the bot
7. **Performance**: Reduced API calls through intelligent caching

## 📝 Example: Custom Agent Addition

To add a new agent:

```python
class MyCustomAgent(BaseAgent):
    def __init__(self, logger: logging.Logger):
        super().__init__("My Custom Agent", logger)
    
    async def process(self, **kwargs) -> AgentResult:
        start_time = datetime.now()
        self.status = AgentStatus.PROCESSING
        
        try:
            # Your logic here
            result_data = {...}
            
            self.status = AgentStatus.READY
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return AgentResult(
                agent_name=self.name,
                status=self.status,
                timestamp=datetime.now().isoformat(),
                data=result_data,
                processing_time_ms=processing_time
            )
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.ERROR,
                timestamp=datetime.now().isoformat(),
                data={},
                error=str(e)
            )
```

Then register with coordinator:
```python
coordinator.my_agent = MyCustomAgent(logger)
```

## 🔧 Troubleshooting

### Agent Returns Error Status
Check the `error` field in AgentResult:
```python
result = await agent.process(...)
if result.status == AgentStatus.ERROR:
    print(f"Error: {result.error}")
```

### Slow Performance
- Check `processing_time_ms` in AgentResult
- Profile individual agents
- Reduce data payload to agents
- Increase CVD cache duration

### Signal Generation Fails
1. Check Signal Analysis Agent output
2. Verify Risk Management Agent validations
3. Check ML Prediction Agent confidence
4. Review CVD Analysis Agent data

## 📚 References
- Agent Framework: `SignalMaestro/trading_agents.py`
- Bot Integration: `SignalMaestro/perfect_scalping_bot.py`
- Inspired by: https://github.com/msitarzewski/agency-agents
