#!/usr/bin/env python3
"""
Agency Trading Agents Integration for perfect_scalping_bot.py
Drop-in integration using specialized agents with parallel processing
"""

import asyncio
from typing import Dict, Any, List, Optional
from agency_trading_agents import AgencyTradingAgents
from parallel_trade_processor import ParallelTradeProcessor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgencyBotIntegration:
    """
    Integration layer for Agency Trading Agents
    Coordinates agent-based analysis with parallel signal processing
    """
    
    def __init__(self, account_size: float = 1000.0):
        self.agents = AgencyTradingAgents(account_size=account_size)
        self.processor = ParallelTradeProcessor(max_concurrent_tasks=10, max_workers=4)
        self.signal_results = []
    
    async def analyze_signal_with_agency(self, symbol: str, current_price: float,
                                        indicators: Dict[str, Any], 
                                        direction: str, atr: float) -> Optional[Dict]:
        """
        Analyze signal using agency agents
        Replaces generate_scalping_signal() call
        """
        
        # Prepare signal and market data
        signal = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': current_price,
            'timestamp': None
        }
        
        market_data = {
            'current_price': current_price,
            'atr': atr,
            'spread': indicators.get('spread', 0.001),
            'bid_volume': indicators.get('bid_volume', 0),
            'ask_volume': indicators.get('ask_volume', 0)
        }
        
        # Get agent analysis
        try:
            analysis = await self.agents.analyze_signal_with_agents(
                symbol, signal, indicators, market_data
            )
            
            # Return only if agents recommend action
            if analysis['final_recommendation'] in ['BUY', 'SELL']:
                return self._format_signal_output(analysis, current_price, atr)
            
            return None
            
        except Exception as e:
            logger.error(f"Agency analysis error for {symbol}: {e}")
            return None
    
    async def process_multiple_signals_with_agents(self, signal_list: List[tuple]) -> List[Dict]:
        """
        Process multiple signals using agents in parallel
        signal_list: [(symbol, price, indicators, direction, atr), ...]
        """
        
        tasks = []
        for symbol, price, indicators, direction, atr in signal_list:
            coro = self.analyze_signal_with_agency(symbol, price, indicators, direction, atr)
            tasks.append((symbol, 'agency_analysis', coro))
        
        results = await self.processor.submit_batch(tasks)
        return [r for r in results if r is not None]
    
    async def monitor_position_with_agents(self, symbol: str, trade_info: Dict,
                                           current_price: float) -> Optional[Dict]:
        """Monitor position using optimizer agent"""
        
        try:
            monitoring_result = await self.agents.monitor_position(
                symbol, trade_info, current_price
            )
            
            return monitoring_result
            
        except Exception as e:
            logger.error(f"Position monitoring error for {symbol}: {e}")
            return None
    
    def _format_signal_output(self, analysis: Dict, entry_price: float, atr: float) -> Dict:
        """Format agency analysis into trading signal"""
        
        # Get agent consensus
        consensus = analysis['consensus']
        agent_decisions = analysis['agent_decisions']
        
        # Extract risk manager metrics
        risk_metrics = agent_decisions.get('risk_manager', {}).get('metrics', {})
        
        # Extract execution specialist recommendation
        execution_rec = agent_decisions.get('execution_specialist', {}).get('recommendation', 'EXECUTE_MARKET')
        
        signal = {
            'symbol': analysis['symbol'],
            'direction': analysis['consensus']['top_recommendation'],
            'entry_price': entry_price,
            'confidence': analysis['confidence_score'],
            'agency_consensus': True,
            'agent_agreement': int(consensus['agreement_level'] * 100),
            'agent_decisions': agent_decisions,
            'position_size': risk_metrics.get('position_size', 0),
            'stop_loss': risk_metrics.get('stop_loss', 0),
            'risk_amount': risk_metrics.get('risk_amount', 0),
            'execution_method': execution_rec,
            'reasoning': self._build_reasoning(analysis),
            'timestamp': analysis['timestamp'],
            'enhanced': True
        }
        
        return signal
    
    def _build_reasoning(self, analysis: Dict) -> str:
        """Build human-readable reasoning from agent decisions"""
        
        reasoning_parts = []
        agent_decisions = analysis['agent_decisions']
        
        # Get top reasons from each agent
        for agent_name, decision in agent_decisions.items():
            if decision['reasoning']:
                top_reason = decision['reasoning'][0]
                reasoning_parts.append(f"{agent_name}: {top_reason}")
        
        consensus = analysis['consensus']
        reasoning_parts.append(
            f"Consensus: {consensus['agreement_level']*100:.0f}% of agents agree"
        )
        
        return " | ".join(reasoning_parts[:3])
    
    def print_agency_status(self):
        """Print status of agency trading system"""
        self.agents.print_agent_roster()
        print(f"Signal Processor: {self.processor.max_concurrent_tasks} concurrent tasks")
        print(f"Decisions Analyzed: {len(self.agents.decision_history)}\n")
    
    def get_agent_statistics(self) -> Dict:
        """Get statistics from all agents"""
        
        history = self.agents.decision_history[-50:]  # Last 50 decisions
        
        if not history:
            return {}
        
        # Calculate agent accuracy (by recommendation frequency)
        buy_signals = sum(1 for h in history if h['final_recommendation'] == 'BUY')
        sell_signals = sum(1 for h in history if h['final_recommendation'] == 'SELL')
        skipped = sum(1 for h in history if h['final_recommendation'] == 'HOLD')
        
        avg_confidence = sum(h['confidence_score'] for h in history) / len(history)
        avg_agreement = sum(
            h['consensus'].get('agreement_level', 0) for h in history
        ) / len(history)
        
        return {
            'total_analyzed': len(history),
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'skipped': skipped,
            'avg_confidence': int(avg_confidence),
            'avg_agent_agreement': int(avg_agreement * 100),
            'recommendation_distribution': {
                'BUY': buy_signals,
                'SELL': sell_signals,
                'HOLD': skipped
            }
        }
    
    async def shutdown(self):
        """Shutdown processors"""
        await self.processor.shutdown()

# INTEGRATION INSTRUCTIONS:
# ========================
#
# In perfect_scalping_bot.py:
#
# 1. Add import at top:
#    from agency_bot_integration import AgencyBotIntegration
#
# 2. In __init__:
#    self.agency = AgencyBotIntegration(account_size=1000.0)
#    self.agency.print_agency_status()
#
# 3. In scan_for_signals() async function, replace:
#    OLD: signal = self.generate_scalping_signal(symbol, indicators, df)
#    NEW: signal = await self.agency.analyze_signal_with_agency(
#             symbol, current_price, indicators, direction, atr
#         )
#
# 4. For batch processing signals:
#    signal_list = [(sym, price, ind, dir, atr) for ...]
#    signals = await self.agency.process_multiple_signals_with_agents(signal_list)
#
# 5. For monitoring existing trades:
#    result = await self.agency.monitor_position_with_agents(symbol, trade_info, price)
#
# 6. Get statistics:
#    stats = self.agency.get_agent_statistics()
#    print(f"Agent Agreement: {stats['avg_agent_agreement']}%")
#
# 7. On shutdown:
#    await self.agency.shutdown()
