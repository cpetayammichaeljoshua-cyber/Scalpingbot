#!/usr/bin/env python3
"""
Comprehensive Leverage Monitoring and Logging System

This module provides real-time monitoring and comprehensive logging for the dynamic leverage 
adjustment system. It tracks leverage changes, portfolio risk metrics, volatility trends, 
and provides alerting for extreme market conditions.

Features:
- Real-time leverage change logging with detailed context
- Portfolio risk monitoring and alerts
- Volatility trend analysis and reporting
- Performance metrics tracking
- Risk limit monitoring and notifications
- Comprehensive dashboard data generation
"""

import asyncio
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import numpy as np
from collections import defaultdict, deque

@dataclass
class LeverageChangeEvent:
    """Leverage change event for logging"""
    timestamp: datetime
    symbol: str
    old_leverage: int
    new_leverage: int
    volatility_score: float
    risk_level: str
    reason: str
    signal_strength: float
    portfolio_impact: float
    trade_value_usdt: float
    
@dataclass
class PortfolioRiskAlert:
    """Portfolio risk alert"""
    timestamp: datetime
    alert_type: str
    severity: str
    message: str
    portfolio_leverage: float
    positions_count: int
    total_exposure: float
    recommendation: str

@dataclass
class VolatilityAlert:
    """Volatility alert for extreme market conditions"""
    timestamp: datetime
    symbol: str
    volatility_score: float
    previous_score: float
    change_percentage: float
    alert_level: str
    recommended_action: str

class LeverageMonitor:
    """Comprehensive leverage monitoring and logging system"""
    
    def __init__(self, database_path: str = "leverage_monitoring.db"):
        self.logger = logging.getLogger(__name__)
        self.database_path = database_path
        
        # Monitoring configuration
        self.monitoring_config = {
            'portfolio_leverage_warning': 4.0,
            'portfolio_leverage_critical': 6.0,
            'volatility_spike_threshold': 50.0,  # % increase
            'volatility_warning_threshold': 5.0,
            'volatility_critical_threshold': 8.0,
            'max_position_exposure': 2.0,  # $2 per position for $10 capital
            'risk_check_interval': 300,  # 5 minutes
        }
        
        # In-memory tracking
        self.leverage_history = defaultdict(deque)  # symbol -> deque of leverage changes
        self.volatility_history = defaultdict(deque)  # symbol -> deque of volatility scores
        self.portfolio_metrics_history = deque(maxlen=288)  # 24 hours of 5-min intervals
        self.active_alerts = []
        
        # Performance tracking
        self.performance_metrics = {
            'total_leverage_adjustments': 0,
            'risk_prevented_events': 0,
            'portfolio_risk_alerts': 0,
            'volatility_alerts': 0,
            'average_portfolio_leverage': 0.0,
            'max_portfolio_leverage_today': 0.0,
            'leverage_efficiency_score': 0.0
        }
        
        # Initialize database
        self._init_monitoring_database()
        
        self.logger.info("📊 Leverage monitoring system initialized")
    
    def _init_monitoring_database(self):
        """Initialize monitoring database tables"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Leverage change events table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS leverage_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        symbol TEXT NOT NULL,
                        old_leverage INTEGER,
                        new_leverage INTEGER,
                        volatility_score REAL,
                        risk_level TEXT,
                        reason TEXT,
                        signal_strength REAL,
                        portfolio_impact REAL,
                        trade_value_usdt REAL
                    )
                ''')
                
                # Portfolio risk alerts table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS portfolio_risk_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        alert_type TEXT,
                        severity TEXT,
                        message TEXT,
                        portfolio_leverage REAL,
                        positions_count INTEGER,
                        total_exposure REAL,
                        recommendation TEXT
                    )
                ''')
                
                # Volatility alerts table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS volatility_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        symbol TEXT,
                        volatility_score REAL,
                        previous_score REAL,
                        change_percentage REAL,
                        alert_level TEXT,
                        recommended_action TEXT
                    )
                ''')
                
                # Performance metrics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        portfolio_leverage REAL,
                        total_positions INTEGER,
                        total_exposure REAL,
                        average_volatility REAL,
                        risk_score REAL,
                        leverage_efficiency REAL
                    )
                ''')
                
                conn.commit()
                self.logger.info("📊 Monitoring database initialized successfully")
                
        except Exception as e:
            self.logger.error(f"❌ Error initializing monitoring database: {e}")
            raise
    
    async def log_leverage_change(self, symbol: str, old_leverage: int, new_leverage: int,
                                volatility_score: float, risk_level: str, reason: str,
                                signal_strength: float = 0.0, trade_value_usdt: float = 0.0):
        """
        Log a leverage change event with comprehensive context
        
        Args:
            symbol: Trading symbol
            old_leverage: Previous leverage value
            new_leverage: New leverage value
            volatility_score: Current volatility score
            risk_level: Risk level assessment
            reason: Reason for the change
            signal_strength: Associated signal strength
            trade_value_usdt: Trade value in USDT
        """
        try:
            # Calculate portfolio impact
            leverage_change_ratio = new_leverage / old_leverage if old_leverage > 0 else 1.0
            portfolio_impact = (leverage_change_ratio - 1.0) * 100  # Percentage impact
            
            # Create event
            event = LeverageChangeEvent(
                timestamp=datetime.now(),
                symbol=symbol,
                old_leverage=old_leverage,
                new_leverage=new_leverage,
                volatility_score=volatility_score,
                risk_level=risk_level,
                reason=reason,
                signal_strength=signal_strength,
                portfolio_impact=portfolio_impact,
                trade_value_usdt=trade_value_usdt
            )
            
            # Store in database
            await self._store_leverage_event(event)
            
            # Update in-memory tracking
            self.leverage_history[symbol].append(event)
            if len(self.leverage_history[symbol]) > 100:  # Keep last 100 changes
                self.leverage_history[symbol].popleft()
            
            # Update performance metrics
            self.performance_metrics['total_leverage_adjustments'] += 1
            
            # Log with appropriate level based on change significance
            if abs(new_leverage - old_leverage) >= 3:
                self.logger.warning(f"⚡ SIGNIFICANT LEVERAGE CHANGE: {symbol} {old_leverage}x → {new_leverage}x "
                                  f"(Volatility: {volatility_score:.2f}, Risk: {risk_level}, Reason: {reason})")
            else:
                self.logger.info(f"⚡ {symbol}: Leverage adjusted {old_leverage}x → {new_leverage}x "
                               f"(Vol: {volatility_score:.2f}, Risk: {risk_level})")
            
            # Check for risk alerts
            await self._check_leverage_risk_alerts(symbol, new_leverage, volatility_score)
            
        except Exception as e:
            self.logger.error(f"❌ Error logging leverage change for {symbol}: {e}")
    
    async def log_volatility_change(self, symbol: str, current_volatility: float, previous_volatility: float):
        """Log significant volatility changes"""
        try:
            if previous_volatility <= 0:
                return
            
            change_percentage = ((current_volatility - previous_volatility) / previous_volatility) * 100
            
            # Update volatility history
            self.volatility_history[symbol].append({
                'timestamp': datetime.now(),
                'volatility': current_volatility,
                'change_pct': change_percentage
            })
            if len(self.volatility_history[symbol]) > 100:
                self.volatility_history[symbol].popleft()
            
            # Generate alerts for significant changes
            if abs(change_percentage) >= self.monitoring_config['volatility_spike_threshold']:
                alert_level = 'CRITICAL' if abs(change_percentage) >= 75 else 'WARNING'
                
                if change_percentage > 0:
                    recommended_action = f"Consider reducing leverage due to {change_percentage:.1f}% volatility spike"
                else:
                    recommended_action = f"Monitor for potential leverage increase opportunity after {abs(change_percentage):.1f}% volatility drop"
                
                alert = VolatilityAlert(
                    timestamp=datetime.now(),
                    symbol=symbol,
                    volatility_score=current_volatility,
                    previous_score=previous_volatility,
                    change_percentage=change_percentage,
                    alert_level=alert_level,
                    recommended_action=recommended_action
                )
                
                await self._store_volatility_alert(alert)
                self.performance_metrics['volatility_alerts'] += 1
                
                self.logger.warning(f"🌪️ {alert_level} VOLATILITY ALERT: {symbol} "
                                  f"{previous_volatility:.2f} → {current_volatility:.2f} "
                                  f"({change_percentage:+.1f}%)")
            
        except Exception as e:
            self.logger.error(f"❌ Error logging volatility change for {symbol}: {e}")
    
    async def monitor_portfolio_risk(self, positions: List[Dict[str, Any]], 
                                   account_balance: Dict[str, Any]):
        """Monitor overall portfolio risk and generate alerts"""
        try:
            if not positions:
                return
            
            # Calculate portfolio metrics
            total_notional = sum(pos.get('notional', 0) for pos in positions)
            total_margin = sum(pos.get('margin_used', 0) for pos in positions)
            available_balance = account_balance.get('available_balance', 0)
            total_balance = account_balance.get('total_wallet_balance', 0)
            
            portfolio_leverage = total_notional / total_margin if total_margin > 0 else 0
            margin_ratio = total_margin / total_balance if total_balance > 0 else 0
            
            # Check portfolio leverage limits
            alerts = []
            if portfolio_leverage > self.monitoring_config['portfolio_leverage_critical']:
                alerts.append(PortfolioRiskAlert(
                    timestamp=datetime.now(),
                    alert_type='EXCESSIVE_LEVERAGE',
                    severity='CRITICAL',
                    message=f'Portfolio leverage {portfolio_leverage:.1f}x exceeds critical limit',
                    portfolio_leverage=portfolio_leverage,
                    positions_count=len(positions),
                    total_exposure=total_notional,
                    recommendation='Immediately reduce position sizes or close positions'
                ))
            elif portfolio_leverage > self.monitoring_config['portfolio_leverage_warning']:
                alerts.append(PortfolioRiskAlert(
                    timestamp=datetime.now(),
                    alert_type='HIGH_LEVERAGE',
                    severity='WARNING',
                    message=f'Portfolio leverage {portfolio_leverage:.1f}x above recommended limit',
                    portfolio_leverage=portfolio_leverage,
                    positions_count=len(positions),
                    total_exposure=total_notional,
                    recommendation='Consider reducing leverage on volatile positions'
                ))
            
            # Check individual position exposure
            max_position_value = max(pos.get('notional', 0) for pos in positions) if positions else 0
            if max_position_value > self.monitoring_config['max_position_exposure']:
                alerts.append(PortfolioRiskAlert(
                    timestamp=datetime.now(),
                    alert_type='LARGE_POSITION',
                    severity='WARNING',
                    message=f'Position exposure ${max_position_value:.2f} exceeds recommended ${self.monitoring_config["max_position_exposure"]:.2f}',
                    portfolio_leverage=portfolio_leverage,
                    positions_count=len(positions),
                    total_exposure=total_notional,
                    recommendation='Consider reducing position size to maintain proper risk management'
                ))
            
            # Store alerts and update metrics
            for alert in alerts:
                await self._store_portfolio_risk_alert(alert)
                self.active_alerts.append(alert)
                self.performance_metrics['portfolio_risk_alerts'] += 1
                
                self.logger.warning(f"🚨 {alert.severity} PORTFOLIO RISK: {alert.message}")
            
            # Update performance tracking
            self.performance_metrics['average_portfolio_leverage'] = portfolio_leverage
            if portfolio_leverage > self.performance_metrics['max_portfolio_leverage_today']:
                self.performance_metrics['max_portfolio_leverage_today'] = portfolio_leverage
            
            # Store performance metrics
            await self._store_performance_metrics(portfolio_leverage, len(positions), 
                                                total_notional, margin_ratio)
            
            # Log portfolio status
            self.logger.info(f"📊 Portfolio Status: Leverage {portfolio_leverage:.1f}x, "
                           f"Positions: {len(positions)}, Exposure: ${total_notional:.2f}, "
                           f"Margin Ratio: {margin_ratio:.1%}")
            
        except Exception as e:
            self.logger.error(f"❌ Error monitoring portfolio risk: {e}")
    
    async def _check_leverage_risk_alerts(self, symbol: str, leverage: int, volatility_score: float):
        """Check for specific leverage risk conditions"""
        try:
            # High leverage with high volatility warning
            if leverage >= 8 and volatility_score >= self.monitoring_config['volatility_warning_threshold']:
                self.logger.warning(f"⚠️ RISK WARNING: {symbol} using {leverage}x leverage "
                                  f"with high volatility {volatility_score:.2f}")
                self.performance_metrics['risk_prevented_events'] += 1
            
            # Emergency conditions
            if leverage >= 5 and volatility_score >= self.monitoring_config['volatility_critical_threshold']:
                self.logger.error(f"🚨 CRITICAL RISK: {symbol} using {leverage}x leverage "
                                f"with extreme volatility {volatility_score:.2f}")
                self.performance_metrics['risk_prevented_events'] += 1
            
        except Exception as e:
            self.logger.error(f"❌ Error checking leverage risk alerts: {e}")
    
    async def _store_leverage_event(self, event: LeverageChangeEvent):
        """Store leverage event in database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO leverage_events 
                    (timestamp, symbol, old_leverage, new_leverage, volatility_score, 
                     risk_level, reason, signal_strength, portfolio_impact, trade_value_usdt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event.timestamp, event.symbol, event.old_leverage, event.new_leverage,
                    event.volatility_score, event.risk_level, event.reason,
                    event.signal_strength, event.portfolio_impact, event.trade_value_usdt
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error storing leverage event: {e}")
    
    async def _store_portfolio_risk_alert(self, alert: PortfolioRiskAlert):
        """Store portfolio risk alert in database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO portfolio_risk_alerts 
                    (timestamp, alert_type, severity, message, portfolio_leverage, 
                     positions_count, total_exposure, recommendation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    alert.timestamp, alert.alert_type, alert.severity, alert.message,
                    alert.portfolio_leverage, alert.positions_count, alert.total_exposure,
                    alert.recommendation
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error storing portfolio risk alert: {e}")
    
    async def _store_volatility_alert(self, alert: VolatilityAlert):
        """Store volatility alert in database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO volatility_alerts 
                    (timestamp, symbol, volatility_score, previous_score, 
                     change_percentage, alert_level, recommended_action)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    alert.timestamp, alert.symbol, alert.volatility_score,
                    alert.previous_score, alert.change_percentage,
                    alert.alert_level, alert.recommended_action
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error storing volatility alert: {e}")
    
    async def _store_performance_metrics(self, portfolio_leverage: float, positions_count: int,
                                       total_exposure: float, risk_score: float):
        """Store performance metrics in database"""
        try:
            # Calculate leverage efficiency (how well leverage is optimized)
            efficiency = min(100, (portfolio_leverage / 5.0) * 100) if portfolio_leverage <= 5.0 else max(0, 100 - (portfolio_leverage - 5.0) * 20)
            
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO performance_metrics 
                    (timestamp, portfolio_leverage, total_positions, total_exposure, 
                     risk_score, leverage_efficiency)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now(), portfolio_leverage, positions_count, total_exposure,
                    risk_score, efficiency
                ))
                conn.commit()
                
            self.performance_metrics['leverage_efficiency_score'] = efficiency
            
        except Exception as e:
            self.logger.error(f"Error storing performance metrics: {e}")
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Get comprehensive monitoring summary"""
        try:
            # Calculate recent activity
            recent_alerts = [alert for alert in self.active_alerts 
                           if (datetime.now() - alert.timestamp).seconds < 3600]  # Last hour
            
            # Get volatility trends
            volatility_trends = {}
            for symbol, history in self.volatility_history.items():
                if history:
                    recent_vol = list(history)[-5:]  # Last 5 readings
                    if len(recent_vol) >= 2:
                        trend = "increasing" if recent_vol[-1]['volatility'] > recent_vol[0]['volatility'] else "decreasing"
                        volatility_trends[symbol] = {
                            'current': recent_vol[-1]['volatility'],
                            'trend': trend,
                            'change_5periods': recent_vol[-1]['volatility'] - recent_vol[0]['volatility']
                        }
            
            return {
                'monitoring_status': 'active',
                'performance_metrics': self.performance_metrics.copy(),
                'recent_alerts_count': len(recent_alerts),
                'active_alerts': [asdict(alert) for alert in recent_alerts],
                'volatility_trends': volatility_trends,
                'monitoring_config': self.monitoring_config.copy(),
                'symbols_tracked': len(self.leverage_history),
                'total_leverage_events': sum(len(history) for history in self.leverage_history.values()),
                'summary_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error generating monitoring summary: {e}")
            return {'error': str(e)}
    
    async def generate_daily_report(self) -> Dict[str, Any]:
        """Generate comprehensive daily monitoring report"""
        try:
            # Get data from last 24 hours
            yesterday = datetime.now() - timedelta(days=1)
            
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Leverage events
                cursor.execute('''
                    SELECT COUNT(*), AVG(volatility_score), COUNT(DISTINCT symbol)
                    FROM leverage_events 
                    WHERE timestamp >= ?
                ''', (yesterday,))
                leverage_stats = cursor.fetchone()
                
                # Risk alerts
                cursor.execute('''
                    SELECT alert_type, COUNT(*) 
                    FROM portfolio_risk_alerts 
                    WHERE timestamp >= ?
                    GROUP BY alert_type
                ''', (yesterday,))
                risk_alerts = dict(cursor.fetchall())
                
                # Volatility alerts
                cursor.execute('''
                    SELECT COUNT(*), AVG(ABS(change_percentage))
                    FROM volatility_alerts 
                    WHERE timestamp >= ?
                ''', (yesterday,))
                volatility_stats = cursor.fetchone()
            
            report = {
                'report_date': datetime.now().date().isoformat(),
                'leverage_adjustments': {
                    'total_adjustments': leverage_stats[0] if leverage_stats[0] else 0,
                    'average_volatility': round(leverage_stats[1], 2) if leverage_stats[1] else 0,
                    'symbols_affected': leverage_stats[2] if leverage_stats[2] else 0
                },
                'risk_management': {
                    'risk_alerts_by_type': risk_alerts,
                    'total_risk_events': sum(risk_alerts.values()),
                    'risk_prevention_score': self.performance_metrics['risk_prevented_events']
                },
                'volatility_analysis': {
                    'volatility_alerts': volatility_stats[0] if volatility_stats[0] else 0,
                    'average_volatility_change': round(volatility_stats[1], 2) if volatility_stats[1] else 0
                },
                'performance_summary': {
                    'max_portfolio_leverage': self.performance_metrics['max_portfolio_leverage_today'],
                    'average_leverage_efficiency': self.performance_metrics['leverage_efficiency_score'],
                    'total_monitoring_events': (leverage_stats[0] or 0) + sum(risk_alerts.values()) + (volatility_stats[0] or 0)
                }
            }
            
            self.logger.info(f"📈 Daily Report Generated: {report['leverage_adjustments']['total_adjustments']} "
                           f"leverage adjustments, {report['risk_management']['total_risk_events']} risk events")
            
            return report
            
        except Exception as e:
            self.logger.error(f"❌ Error generating daily report: {e}")
            return {'error': str(e)}
    
    def update_monitoring_config(self, new_config: Dict[str, Any]):
        """Update monitoring configuration"""
        try:
            for key, value in new_config.items():
                if key in self.monitoring_config:
                    old_value = self.monitoring_config[key]
                    self.monitoring_config[key] = value
                    self.logger.info(f"🔧 Updated monitoring config: {key} {old_value} → {value}")
            
            self.logger.info("✅ Monitoring configuration updated successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error updating monitoring config: {e}")