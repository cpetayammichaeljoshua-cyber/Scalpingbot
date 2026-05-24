#!/usr/bin/env python3
"""
Console Output Formatter for Agency Trading Agents
Displays agent decisions with rich formatting
"""

from typing import Dict, Any, List
from datetime import datetime

class AgencyConsoleFormatter:
    """Formats and displays agency agent decisions"""
    
    COLORS = {
        'green': '\033[92m',
        'red': '\033[91m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'reset': '\033[0m',
        'bold': '\033[1m'
    }
    
    AGENTS = {
        'signal_analyst': ('🎯', 'Signal Analyst'),
        'risk_manager': ('📊', 'Risk Manager'),
        'market_observer': ('🔍', 'Market Observer'),
        'position_optimizer': ('⚡', 'Position Optimizer'),
        'execution_specialist': ('🚀', 'Execution Specialist')
    }
    
    @classmethod
    def format_signal_analysis(cls, analysis: Dict[str, Any], verbose: bool = True) -> str:
        """Format complete signal analysis for console"""
        
        output = []
        output.append("\n" + "="*80)
        output.append(f"AGENCY ANALYSIS: {analysis['symbol']} | {analysis['timestamp']}")
        output.append("="*80)
        
        # Print each agent's decision
        agent_decisions = analysis.get('agent_decisions', {})
        for agent_name, decision in agent_decisions.items():
            agent_emoji, agent_full = cls.AGENTS.get(agent_name, ('?', agent_name))
            
            output.append(f"\n{agent_emoji} {agent_full.upper()}")
            output.append(f"   Recommendation: {cls._color_recommendation(decision['recommendation'])}")
            output.append(f"   Confidence: {cls._color_confidence(decision['confidence'])}%")
            
            if decision['reasoning']:
                for reason in decision['reasoning'][:2]:  # Top 2 reasons
                    output.append(f"   • {reason}")
            
            if verbose and decision['metrics']:
                for metric_name, metric_value in list(decision['metrics'].items())[:2]:
                    if isinstance(metric_value, float):
                        output.append(f"   └─ {metric_name}: {metric_value:.4f}")
                    else:
                        output.append(f"   └─ {metric_name}: {metric_value}")
        
        # Print consensus
        consensus = analysis.get('consensus', {})
        output.append("\n" + "-"*80)
        output.append("CONSENSUS VOTING")
        output.append("-"*80)
        
        agreement = consensus.get('agreement_level', 0) * 100
        avg_conf = consensus.get('average_confidence', 0)
        
        agreement_color = cls._color_agreement(agreement)
        output.append(f"Agent Agreement: {agreement_color}{agreement:.0f}%{cls.COLORS['reset']}")
        output.append(f"Average Confidence: {cls._color_confidence(int(avg_conf))}%")
        
        rec_count = consensus.get('recommendation_count', {})
        for rec, count in rec_count.items():
            agent_count = consensus.get('agent_count', 1)
            pct = (count / agent_count) * 100 if agent_count > 0 else 0
            output.append(f"  {rec}: {count}/{agent_count} agents ({pct:.0f}%)")
        
        # Print final decision
        output.append("\n" + "="*80)
        final_rec = analysis.get('final_recommendation', 'HOLD')
        confidence_score = analysis.get('confidence_score', 0)
        
        if final_rec in ['BUY', 'SELL']:
            output.append(f"{cls.COLORS['green']}{cls.COLORS['bold']}")
            output.append(f"FINAL RECOMMENDATION: {final_rec}")
            output.append(f"Signal Strength: {confidence_score}%")
            output.append(f"{cls.COLORS['reset']}")
        else:
            output.append(f"{cls.COLORS['yellow']}")
            output.append(f"FINAL RECOMMENDATION: {final_rec}")
            output.append(f"Insufficient Consensus")
            output.append(f"{cls.COLORS['reset']}")
        
        output.append("="*80)
        
        return "\n".join(output)
    
    @classmethod
    def format_position_monitor(cls, monitoring: Dict[str, Any]) -> str:
        """Format position monitoring output"""
        
        output = []
        output.append("\n" + "-"*60)
        output.append(f"📍 POSITION MONITOR: {monitoring['symbol']}")
        output.append("-"*60)
        
        agent = monitoring['agent']
        rec = monitoring['recommendation']
        conf = monitoring['confidence']
        
        output.append(f"Agent: {agent}")
        output.append(f"Recommendation: {cls._color_recommendation(rec)}")
        output.append(f"Confidence: {cls._color_confidence(conf)}%")
        
        for reason in monitoring.get('reasoning', [])[:2]:
            output.append(f"• {reason}")
        
        output.append("-"*60)
        
        return "\n".join(output)
    
    @classmethod
    def format_statistics(cls, stats: Dict[str, Any]) -> str:
        """Format agency statistics"""
        
        output = []
        output.append("\n" + "="*60)
        output.append("AGENCY STATISTICS")
        output.append("="*60)
        
        output.append(f"Total Analyzed: {stats.get('total_analyzed', 0)}")
        output.append(f"Average Confidence: {stats.get('avg_confidence', 0)}%")
        output.append(f"Agent Agreement: {stats.get('avg_agent_agreement', 0)}%")
        
        output.append("\nSignal Distribution:")
        dist = stats.get('recommendation_distribution', {})
        output.append(f"  🟢 BUY:  {dist.get('BUY', 0)}")
        output.append(f"  🔴 SELL: {dist.get('SELL', 0)}")
        output.append(f"  ⚪ HOLD: {dist.get('HOLD', 0)}")
        
        output.append("="*60)
        
        return "\n".join(output)
    
    @staticmethod
    def _color_recommendation(rec: str) -> str:
        """Color recommendation based on type"""
        
        if rec in ['BUY', 'APPROVE', 'EXECUTE_MARKET', 'TAKE_HALF', 'TAKE_PARTIAL', 'FAVORABLE']:
            color = '\033[92m'  # Green
        elif rec in ['SELL', 'SKIP', 'TIGHTEN_STOP', 'CAUTION']:
            color = '\033[91m'  # Red
        else:
            color = '\033[93m'  # Yellow
        
        return f"{color}{rec}\033[0m"
    
    @staticmethod
    def _color_confidence(conf: int) -> str:
        """Color confidence based on level"""
        
        if conf >= 80:
            color = '\033[92m'  # Green
        elif conf >= 60:
            color = '\033[93m'  # Yellow
        else:
            color = '\033[91m'  # Red
        
        return f"{color}{conf}\033[0m"
    
    @staticmethod
    def _color_agreement(agreement: float) -> str:
        """Color agreement percentage"""
        
        if agreement >= 75:
            color = '\033[92m'  # Green
        elif agreement >= 50:
            color = '\033[93m'  # Yellow
        else:
            color = '\033[91m'  # Red
        
        return f"{color}{agreement:.0f}%\033[0m"
    
    @classmethod
    def print_agent_banner(cls):
        """Print agency header"""
        
        print("\n" + cls.COLORS['bold'] + cls.COLORS['cyan'])
        print("╔" + "═"*78 + "╗")
        print("║" + " "*78 + "║")
        print("║" + "  🎭 AGENCY TRADING AGENTS - SPECIALIZED TRADING TEAM".center(78) + "║")
        print("║" + "  Powered by Multi-Agent Signal Analysis & Parallel Processing".center(78) + "║")
        print("║" + " "*78 + "║")
        print("╚" + "═"*78 + "╝")
        print(cls.COLORS['reset'])
    
    @classmethod
    def print_agent_roster(cls):
        """Print full roster with details"""
        
        cls.print_agent_banner()
        
        roster = [
            {
                'emoji': '🎯',
                'name': 'Signal Analyst',
                'role': 'Validation Specialist',
                'expertise': 'Signal validation, Pattern detection, Indicator analysis'
            },
            {
                'emoji': '📊',
                'name': 'Risk Manager',
                'role': 'Position Protection',
                'expertise': 'Position sizing, Risk assessment, Stop loss optimization'
            },
            {
                'emoji': '🔍',
                'name': 'Market Observer',
                'role': 'Market Intelligence',
                'expertise': 'Market analysis, Regime detection, Volatility assessment'
            },
            {
                'emoji': '⚡',
                'name': 'Position Optimizer',
                'role': 'Trade Management',
                'expertise': 'Position optimization, Profit taking, Stop loss trailing'
            },
            {
                'emoji': '🚀',
                'name': 'Execution Specialist',
                'role': 'Order Execution',
                'expertise': 'Order execution, Timing optimization, Slippage management'
            }
        ]
        
        for agent in roster:
            print(f"\n{agent['emoji']} {agent['name'].upper()}")
            print(f"   Role: {agent['role']}")
            print(f"   Expertise: {agent['expertise']}")
        
        print("\n" + "="*80 + "\n")

def print_parallel_processing_status(processor_stats: Dict) -> str:
    """Print parallel processing status"""
    
    output = []
    output.append("Parallel Processing Status:")
    output.append(f"  Active Tasks: {processor_stats.get('active_tasks', 0)}")
    output.append(f"  Processed: {processor_stats.get('total_processed', 0)}")
    output.append(f"  Success Rate: {processor_stats.get('successful', 0)}/{processor_stats.get('total_processed', 0)}")
    output.append(f"  Avg Time: {processor_stats.get('avg_process_time', 0):.3f}s")
    output.append(f"  Peak Concurrent: {processor_stats.get('peak_concurrent', 0)}")
    
    return "\n".join(output)
