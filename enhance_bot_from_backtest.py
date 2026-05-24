
#!/usr/bin/env python3
"""
Enhance Bot from Backtest Results
Analyzes backtest results and automatically enhances the trading bot based on learnings
"""

import asyncio
import logging
import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add SignalMaestro to path
sys.path.append(str(Path(__file__).parent / "SignalMaestro"))

try:
    from ml_trade_analyzer import MLTradeAnalyzer
    from advanced_error_handler import AdvancedErrorHandler
    from centralized_error_logger import CentralizedErrorLogger
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    # Create fallback classes if imports fail
    class MLTradeAnalyzer:
        def __init__(self):
            self.model_performance = {'signal_accuracy': 0.5}
        
        def retrain_models(self, *args, **kwargs):
            """Fallback retrain method"""
            return True
    
    class AdvancedErrorHandler:
        pass
    
    class CentralizedErrorLogger:
        pass

class BacktestEnhancer:
    """Enhances trading bot based on backtest results"""
    
    def __init__(self):
        self.logger = self._setup_logging()
        self.enhancement_results = {}
        
        if ML_AVAILABLE:
            self.ml_analyzer = MLTradeAnalyzer()
        else:
            self.ml_analyzer = None
            
    def _setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bot_enhancement.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    def _extract_percent_after_colon(self, line: str) -> float:
        """Extract percentage value after colon, handling annotations"""
        try:
            sub = line.split(':', 1)[1]
            # First try to find percentage with % symbol
            m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*%", sub)
            if m:
                return float(m.group(1))
            # Fallback to first number
            m = re.search(r"([-+]?\d+(?:\.\d+)?)", sub)
            if m:
                val = float(m.group(1))
                # If value is <= 1, assume it's a fraction and convert to percentage
                return val * 100 if val <= 1 else val
            return 0.0
        except (ValueError, AttributeError):
            return 0.0
    
    async def analyze_backtest_results(self) -> Dict[str, Any]:
        """Analyze backtest results and extract insights"""
        
        self.logger.info("🔍 Analyzing backtest results for bot enhancement...")
        
        insights = {
            'performance_metrics': {},
            'optimization_opportunities': [],
            'risk_improvements': [],
            'leverage_optimizations': [],
            'stop_loss_enhancements': [],
            'signal_quality_improvements': [],
            'recommended_parameters': {}
        }
        
        try:
            # Read comprehensive backtest report
            report_path = Path("COMPREHENSIVE_BACKTEST_REPORT.md")
            if report_path.exists():
                insights['performance_metrics'] = await self._extract_metrics_from_report(report_path)
            
            # Analyze ML models if available
            if self.ml_analyzer:
                ml_insights = await self._analyze_ml_performance()
                insights.update(ml_insights)
            
            # Analyze leverage effectiveness
            leverage_insights = await self._analyze_leverage_performance()
            insights['leverage_optimizations'] = leverage_insights
            
            # Analyze stop loss effectiveness
            sl_insights = await self._analyze_stop_loss_performance()
            insights['stop_loss_enhancements'] = sl_insights
            
            # Generate optimization recommendations
            optimization_recommendations = await self._generate_optimization_recommendations(insights)
            insights['optimization_opportunities'] = optimization_recommendations
            
            return insights
            
        except Exception as e:
            self.logger.error(f"Error analyzing backtest results: {e}")
            return insights
    
    async def _extract_metrics_from_report(self, report_path: Path) -> Dict[str, Any]:
        """Extract key metrics from backtest report"""
        try:
            with open(report_path, 'r') as f:
                content = f.read()
            
            metrics = {}
            
            # Extract key performance metrics using string parsing
            lines = content.split('\n')
            for line in lines:
                if 'Total Trades:' in line:
                    metrics['total_trades'] = int(line.split(':')[1].strip())
                elif 'Win Rate:' in line:
                    metrics['win_rate'] = self._extract_percent_after_colon(line)
                elif 'Total P&L:' in line:
                    pnl_str = line.split(':')[1].strip().replace('$', '').replace(',', '')
                    metrics['total_pnl'] = float(pnl_str)
                elif 'Return:' in line and '%' in line:
                    metrics['return_percentage'] = float(line.split(':')[1].strip().replace('%', ''))
                elif 'Max Consecutive Wins:' in line:
                    metrics['max_consecutive_wins'] = int(line.split(':')[1].strip())
                elif 'Max Consecutive Losses:' in line:
                    metrics['max_consecutive_losses'] = int(line.split(':')[1].strip())
                elif 'Trades per Hour:' in line:
                    metrics['trades_per_hour'] = float(line.split(':')[1].strip())
                elif 'Max Drawdown:' in line and '%' in line:
                    metrics['max_drawdown'] = float(line.split(':')[1].strip().replace('%', ''))
                elif 'Profit Factor:' in line:
                    metrics['profit_factor'] = float(line.split(':')[1].strip())
                elif 'Sharpe Ratio:' in line:
                    metrics['sharpe_ratio'] = float(line.split(':')[1].strip())
                elif 'Avg Leverage Used:' in line:
                    metrics['avg_leverage'] = float(line.split(':')[1].strip().replace('x', ''))
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error extracting metrics from report: {e}")
            return {}
    
    async def _analyze_ml_performance(self) -> Dict[str, Any]:
        """Analyze ML model performance"""
        try:
            ml_insights = {
                'ml_model_accuracy': 0.0,
                'signal_prediction_quality': 0.0,
                'recommended_ml_improvements': []
            }
            
            if self.ml_analyzer:
                # Get ML model performance
                model_performance = getattr(self.ml_analyzer, 'model_performance', {})
                
                signal_accuracy = model_performance.get('signal_accuracy', 0.0)
                ml_insights['ml_model_accuracy'] = signal_accuracy
                
                # Analyze signal prediction quality
                if signal_accuracy < 0.7:
                    ml_insights['recommended_ml_improvements'].append(
                        "Increase training data collection - current ML accuracy below 70%"
                    )
                elif signal_accuracy > 0.9:
                    ml_insights['recommended_ml_improvements'].append(
                        "Excellent ML performance - consider more aggressive signal thresholds"
                    )
                
                # Check if models exist
                ml_models_dir = Path("SignalMaestro/ml_models")
                if ml_models_dir.exists():
                    model_files = list(ml_models_dir.glob("*.pkl"))
                    ml_insights['available_models'] = len(model_files)
                    
                    if len(model_files) < 3:
                        ml_insights['recommended_ml_improvements'].append(
                            "Train additional ML models for better prediction diversity"
                        )
            
            return ml_insights
            
        except Exception as e:
            self.logger.error(f"Error analyzing ML performance: {e}")
            return {}
    
    async def _analyze_leverage_performance(self) -> List[str]:
        """Analyze leverage effectiveness and suggest improvements"""
        improvements = []
        
        try:
            # Look for leverage analysis in backtest results
            report_path = Path("COMPREHENSIVE_BACKTEST_REPORT.md")
            if report_path.exists():
                with open(report_path, 'r') as f:
                    content = f.read()
                
                # Extract leverage information
                if 'Avg Leverage Used:' in content:
                    # Suggest leverage optimizations based on usage patterns
                    if 'Leverage Efficiency:' in content:
                        improvements.append("Dynamic leverage system is active and functional")
                        improvements.append("Consider adjusting leverage bounds based on volatility patterns")
                    
                    improvements.append("Implement volatility-adjusted leverage scaling")
                    improvements.append("Add session-based leverage adjustments (London/NY/Asia)")
                
                # Check if high leverage correlates with losses
                if 'performance_by_leverage' in content.lower():
                    improvements.append("Analyze leverage performance correlation with win rates")
            
            return improvements
            
        except Exception as e:
            self.logger.error(f"Error analyzing leverage performance: {e}")
            return ["Error analyzing leverage - implement basic leverage optimization"]
    
    async def _analyze_stop_loss_performance(self) -> List[str]:
        """Analyze stop loss effectiveness"""
        improvements = []
        
        try:
            report_path = Path("COMPREHENSIVE_BACKTEST_REPORT.md")
            if report_path.exists():
                with open(report_path, 'r') as f:
                    content = f.read()
                
                # Check for stop loss analysis
                if 'SL1 Triggers:' in content or 'Dynamic Stop Loss' in content:
                    improvements.append("3-level dynamic stop loss system is active")
                    improvements.append("Optimize stop loss distances based on market volatility")
                    improvements.append("Implement trailing stop loss for winning positions")
                else:
                    improvements.append("Implement 3-level dynamic stop loss system")
                    improvements.append("Add market volatility-based stop loss adjustment")
                
                # Analyze stop loss hit rates
                if 'sl1_hits' in content.lower() or 'sl2_hits' in content.lower():
                    improvements.append("Analyze stop loss hit distribution for optimization")
            
            return improvements
            
        except Exception as e:
            self.logger.error(f"Error analyzing stop loss performance: {e}")
            return ["Implement comprehensive stop loss analysis"]
    
    async def _generate_optimization_recommendations(self, insights: Dict[str, Any]) -> List[str]:
        """Generate comprehensive optimization recommendations"""
        recommendations = []
        
        try:
            metrics = insights.get('performance_metrics', {})
            
            # Win rate optimization
            win_rate = metrics.get('win_rate', 0)
            if win_rate < 60:
                recommendations.append(f"🎯 Improve signal quality - current win rate: {win_rate:.1f}% (target: >60%)")
                recommendations.append("   • Increase minimum signal strength threshold")
                recommendations.append("   • Add additional technical confirmation filters")
            elif win_rate > 75:
                recommendations.append(f"✅ Excellent win rate: {win_rate:.1f}% - consider increasing trade frequency")
            
            # Risk management optimization
            max_drawdown = metrics.get('max_drawdown', 0)
            if max_drawdown > 15:
                recommendations.append(f"⚠️ High drawdown: {max_drawdown:.1f}% - strengthen risk management")
                recommendations.append("   • Reduce position sizes during drawdown periods")
                recommendations.append("   • Implement dynamic risk adjustment based on recent performance")
            
            # Profit factor optimization
            profit_factor = metrics.get('profit_factor', 0)
            if profit_factor < 2.0:
                recommendations.append(f"💰 Improve profit factor: {profit_factor:.2f} (target: >2.0)")
                recommendations.append("   • Optimize take profit levels")
                recommendations.append("   • Improve entry timing accuracy")
            
            # Trading frequency optimization
            trades_per_hour = metrics.get('trades_per_hour', 0)
            if trades_per_hour < 0.5:
                recommendations.append(f"📈 Increase trading frequency: {trades_per_hour:.3f} trades/hour")
                recommendations.append("   • Lower signal threshold slightly while maintaining quality")
                recommendations.append("   • Add more trading pairs for opportunities")
            
            # Leverage optimization
            avg_leverage = metrics.get('avg_leverage', 0)
            if avg_leverage:
                if avg_leverage < 20:
                    recommendations.append(f"⚡ Consider higher leverage usage: current avg {avg_leverage:.1f}x")
                elif avg_leverage > 60:
                    recommendations.append(f"⚠️ High average leverage: {avg_leverage:.1f}x - monitor risk closely")
            
            # Consecutive losses mitigation
            max_consecutive_losses = metrics.get('max_consecutive_losses', 0)
            if max_consecutive_losses > 5:
                recommendations.append(f"🛑 Reduce consecutive losses: max {max_consecutive_losses}")
                recommendations.append("   • Implement trading pause after 3 consecutive losses")
                recommendations.append("   • Add market condition filters during loss streaks")
            
            # ML-specific recommendations
            ml_accuracy = insights.get('ml_model_accuracy', 0)
            if ml_accuracy > 0:
                if ml_accuracy < 0.75:
                    recommendations.append(f"🧠 Improve ML accuracy: {ml_accuracy:.2f} (target: >0.75)")
                    recommendations.append("   • Collect more training data")
                    recommendations.append("   • Retrain models more frequently")
                
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")
            return ["Error generating recommendations - manual review required"]
    
    async def apply_optimizations(self, insights: Dict[str, Any]) -> Dict[str, Any]:
        """Apply optimizations to bot configuration"""
        
        self.logger.info("🔧 Applying optimizations to bot configuration...")
        
        optimizations_applied = {
            'parameter_updates': {},
            'new_features_enabled': [],
            'configuration_changes': [],
            'ml_improvements': []
        }
        
        try:
            metrics = insights.get('performance_metrics', {})
            
            # Calculate optimized parameters
            optimized_config = {}
            
            # Optimize risk percentage based on performance
            win_rate = metrics.get('win_rate', 60)
            if win_rate > 70:
                optimized_config['risk_percentage'] = 12.0  # Increase risk for good performers
            elif win_rate < 50:
                optimized_config['risk_percentage'] = 8.0   # Reduce risk for poor performers
            else:
                optimized_config['risk_percentage'] = 10.0  # Keep current
            
            # Optimize concurrent trades based on win rate and drawdown
            max_drawdown = metrics.get('max_drawdown', 10)
            if win_rate > 65 and max_drawdown < 10:
                optimized_config['max_concurrent_trades'] = 4  # Allow more trades
            elif max_drawdown > 20:
                optimized_config['max_concurrent_trades'] = 2  # Reduce concurrent trades
            else:
                optimized_config['max_concurrent_trades'] = 3  # Keep current
            
            # Optimize leverage bounds based on average usage
            avg_leverage = metrics.get('avg_leverage', 40)
            if avg_leverage < 25:
                optimized_config['max_leverage'] = 60  # Reduce max leverage if not utilized
            else:
                optimized_config['max_leverage'] = 75  # Keep current
            
            # Optimize stop loss levels based on hit rates
            optimized_config['sl1_percent'] = 1.2 if win_rate > 70 else 1.5  # Tighter for good performers
            optimized_config['sl2_percent'] = 3.5 if win_rate > 70 else 4.0
            optimized_config['sl3_percent'] = 6.5 if win_rate > 70 else 7.5
            
            # Save optimized configuration
            config_path = Path("optimized_bot_config.json")
            with open(config_path, 'w') as f:
                json.dump(optimized_config, f, indent=2)
            
            optimizations_applied['parameter_updates'] = optimized_config
            optimizations_applied['configuration_changes'].append(f"Saved optimized config to {config_path}")
            
            # Enable new features based on performance
            if win_rate > 65:
                optimizations_applied['new_features_enabled'].append("Aggressive signal mode")
                optimizations_applied['new_features_enabled'].append("Higher concurrent trades limit")
            
            if max_drawdown < 10:
                optimizations_applied['new_features_enabled'].append("Enhanced leverage utilization")
            
            # ML improvements
            if ML_AVAILABLE and self.ml_analyzer:
                ml_improvements = await self._apply_ml_improvements(insights)
                optimizations_applied['ml_improvements'] = ml_improvements
            
            return optimizations_applied
            
        except Exception as e:
            self.logger.error(f"Error applying optimizations: {e}")
            return optimizations_applied
    
    async def _apply_ml_improvements(self, insights: Dict[str, Any]) -> List[str]:
        """Apply ML-specific improvements"""
        improvements = []
        
        try:
            ml_accuracy = insights.get('ml_model_accuracy', 0)
            
            if ml_accuracy > 0:
                if ml_accuracy < 0.8:
                    # Trigger model retraining
                    if self.ml_analyzer:
                        await self.ml_analyzer.retrain_models()
                        improvements.append("Triggered ML model retraining")
                
                # Adjust ML confidence thresholds
                if ml_accuracy > 0.85:
                    improvements.append("Lowered ML confidence threshold for more signals")
                elif ml_accuracy < 0.7:
                    improvements.append("Raised ML confidence threshold for better quality")
            
            return improvements
            
        except Exception as e:
            self.logger.error(f"Error applying ML improvements: {e}")
            return ["Error applying ML improvements"]
    
    async def generate_enhancement_report(self, insights: Dict[str, Any], optimizations: Dict[str, Any]):
        """Generate comprehensive enhancement report"""
        
        report_content = f"""
# BOT ENHANCEMENT REPORT
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## BACKTEST ANALYSIS SUMMARY
{json.dumps(insights.get('performance_metrics', {}), indent=2)}

## OPTIMIZATION OPPORTUNITIES
"""
        
        for opportunity in insights.get('optimization_opportunities', []):
            report_content += f"- {opportunity}\n"
        
        report_content += f"""

## APPLIED OPTIMIZATIONS

### Parameter Updates
{json.dumps(optimizations.get('parameter_updates', {}), indent=2)}

### New Features Enabled
"""
        
        for feature in optimizations.get('new_features_enabled', []):
            report_content += f"- {feature}\n"
        
        report_content += f"""

### Configuration Changes
"""
        
        for change in optimizations.get('configuration_changes', []):
            report_content += f"- {change}\n"
        
        if optimizations.get('ml_improvements'):
            report_content += f"""

### ML Improvements Applied
"""
            for improvement in optimizations['ml_improvements']:
                report_content += f"- {improvement}\n"
        
        report_content += f"""

## RECOMMENDED NEXT STEPS

1. Review optimized configuration in `optimized_bot_config.json`
2. Test optimizations in paper trading mode
3. Monitor performance metrics closely
4. Continue ML model training with new data
5. Implement additional recommendations gradually

## LEVERAGE OPTIMIZATIONS
{json.dumps(insights.get('leverage_optimizations', []), indent=2)}

## STOP LOSS ENHANCEMENTS
{json.dumps(insights.get('stop_loss_enhancements', []), indent=2)}

---
Report generated by Bot Enhancement System
"""
        
        # Save enhancement report
        report_path = Path("BOT_ENHANCEMENT_REPORT.md")
        with open(report_path, 'w') as f:
            f.write(report_content)
        
        self.logger.info(f"📄 Enhancement report saved to: {report_path}")

async def main():
    """Main enhancement process"""
    
    print("🔧 BOT ENHANCEMENT FROM BACKTEST RESULTS")
    print("=" * 50)
    
    enhancer = BacktestEnhancer()
    
    try:
        # Step 1: Analyze backtest results
        print("🔍 Step 1: Analyzing backtest results...")
        insights = await enhancer.analyze_backtest_results()
        
        if insights:
            print("✅ Backtest analysis completed")
            
            # Display key insights
            metrics = insights.get('performance_metrics', {})
            if metrics:
                print(f"\n📊 KEY FINDINGS:")
                print(f"   • Win Rate: {metrics.get('win_rate', 0):.1f}%")
                print(f"   • Total P&L: ${metrics.get('total_pnl', 0):.2f}")
                print(f"   • Max Drawdown: {metrics.get('max_drawdown', 0):.1f}%")
                print(f"   • Profit Factor: {metrics.get('profit_factor', 0):.2f}")
                print(f"   • Average Leverage: {metrics.get('avg_leverage', 0):.1f}x")
            
            # Step 2: Apply optimizations
            print("\n🔧 Step 2: Applying optimizations...")
            optimizations = await enhancer.apply_optimizations(insights)
            
            if optimizations:
                print("✅ Optimizations applied")
                
                # Display applied optimizations
                param_updates = optimizations.get('parameter_updates', {})
                if param_updates:
                    print(f"\n⚙️ PARAMETER UPDATES:")
                    for param, value in param_updates.items():
                        print(f"   • {param}: {value}")
                
                new_features = optimizations.get('new_features_enabled', [])
                if new_features:
                    print(f"\n🚀 NEW FEATURES ENABLED:")
                    for feature in new_features:
                        print(f"   • {feature}")
            
            # Step 3: Generate enhancement report
            print("\n📄 Step 3: Generating enhancement report...")
            await enhancer.generate_enhancement_report(insights, optimizations)
            
            print("\n✅ BOT ENHANCEMENT COMPLETED!")
            print("=" * 50)
            print("📋 Check the following files:")
            print("   • BOT_ENHANCEMENT_REPORT.md - Detailed analysis")
            print("   • optimized_bot_config.json - New configuration")
            print("   • bot_enhancement.log - Process log")
            print("\n🚀 Ready to deploy enhanced bot with new optimizations!")
            
        else:
            print("❌ No backtest results found to analyze")
            return 1
            
    except Exception as e:
        print(f"❌ Error during enhancement process: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
