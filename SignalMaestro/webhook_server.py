"""
Webhook server for receiving external trading signals
Handles HTTP endpoints for Cornix, TradingView, and other signal sources
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
import logging
import json
import hmac
import hashlib
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime
import threading

from config import Config
from signal_parser import SignalParser
from risk_manager import RiskManager
from utils import format_currency, validate_json_webhook

class WebhookServer:
    """Flask-based webhook server for trading signals"""
    
    def __init__(self, telegram_bot, binance_trader, cornix_integration, database):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.telegram_bot = telegram_bot
        self.binance_trader = binance_trader
        self.cornix = cornix_integration
        self.db = database
        self.signal_parser = SignalParser()
        self.risk_manager = RiskManager()
        
        # Initialize Flask app
        self.app = Flask(__name__, 
                        static_folder='static',
                        static_url_path='/static',
                        template_folder='templates')
        self.app.secret_key = self.config.SESSION_SECRET
        
        # Setup routes
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/', methods=['GET'])
        def index():
            """Dashboard homepage"""
            return render_template('index.html')
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'service': 'trading_signal_bot'
            })
        
        @self.app.route('/api/status', methods=['GET'])
        def get_status():
            """Get system status"""
            return asyncio.run(self._get_system_status())
        
        @self.app.route('/webhook/tradingview', methods=['POST'])
        def tradingview_webhook():
            """TradingView webhook endpoint"""
            try:
                # Validate webhook signature if configured
                if not self._validate_webhook_signature(request):
                    return jsonify({'error': 'Invalid signature'}), 401
                
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'No JSON data provided'}), 400
                
                # Process TradingView signal
                result = asyncio.run(self._process_tradingview_signal(data))
                
                return jsonify(result)
                
            except Exception as e:
                self.logger.error(f"Error processing TradingView webhook: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/webhook/signal', methods=['POST'])
        def signal_webhook():
            """Generic signal webhook endpoint"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'No JSON data provided'}), 400
                
                result = asyncio.run(self._process_generic_signal(data))
                return jsonify(result)
                
            except Exception as e:
                self.logger.error(f"Error processing signal webhook: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/webhook/cornix', methods=['POST'])
        def cornix_webhook():
            """Cornix webhook endpoint for receiving signals"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'No JSON data provided'}), 400
                
                result = asyncio.run(self._process_cornix_signal(data))
                return jsonify(result)
                
            except Exception as e:
                self.logger.error(f"Error processing Cornix webhook: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/portfolio', methods=['GET'])
        def get_portfolio():
            """Get portfolio information"""
            return asyncio.run(self._get_portfolio_data())
        
        @self.app.route('/api/trades', methods=['GET'])
        def get_trades():
            """Get recent trades"""
            limit = request.args.get('limit', 50, type=int)
            return asyncio.run(self._get_trades_data(limit))
        
        @self.app.route('/api/signals', methods=['GET'])
        def get_signals():
            """Get recent signals"""
            limit = request.args.get('limit', 50, type=int)
            return asyncio.run(self._get_signals_data(limit))
        
        @self.app.route('/api/analytics', methods=['GET'])
        def get_analytics():
            """Get trading analytics"""
            days = request.args.get('days', 30, type=int)
            return asyncio.run(self._get_analytics_data(days))
        
        @self.app.route('/api/test-signal', methods=['POST'])
        def test_signal():
            """Test signal parsing endpoint"""
            try:
                data = request.get_json()
                text = data.get('text', '')
                
                if not text:
                    return jsonify({'error': 'No signal text provided'}), 400
                
                # Parse signal
                parsed_signal = self.signal_parser.parse_signal(text)
                
                if parsed_signal:
                    # Validate signal
                    validation = self.signal_parser.validate_signal(parsed_signal)
                    
                    return jsonify({
                        'success': True,
                        'parsed_signal': parsed_signal,
                        'validation': validation
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Could not parse signal'
                    })
                    
            except Exception as e:
                self.logger.error(f"Error testing signal: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({'error': 'Endpoint not found'}), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({'error': 'Internal server error'}), 500
    
    def _validate_webhook_signature(self, request) -> bool:
        """Validate webhook signature for security"""
        try:
            if not self.config.WEBHOOK_SECRET:
                return True  # No validation if no secret configured
            
            signature = request.headers.get('X-Signature')
            if not signature:
                return False
            
            body = request.get_data()
            expected_signature = hmac.new(
                self.config.WEBHOOK_SECRET.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            self.logger.error(f"Error validating webhook signature: {e}")
            return False
    
    async def _process_tradingview_signal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process TradingView webhook signal"""
        try:
            # Extract signal information from TradingView format
            symbol = data.get('ticker', '').upper()
            action = data.get('strategy', {}).get('order_action', '').upper()
            price = data.get('strategy', {}).get('order_price', 0)
            
            # Convert TradingView format to internal format
            signal_text = f"{action} {symbol} at {price}"
            
            # Add additional TradingView data
            if 'strategy' in data:
                strategy_data = data['strategy']
                if 'stop_loss' in strategy_data:
                    signal_text += f" SL: {strategy_data['stop_loss']}"
                if 'take_profit' in strategy_data:
                    signal_text += f" TP: {strategy_data['take_profit']}"
            
            # Parse and process signal
            parsed_signal = self.signal_parser.parse_signal(signal_text)
            
            if not parsed_signal:
                return {
                    'success': False,
                    'error': 'Failed to parse TradingView signal',
                    'original_data': data
                }
            
            # Add TradingView metadata
            parsed_signal['source'] = 'tradingview'
            parsed_signal['webhook_data'] = data
            
            # Process the signal
            result = await self._process_parsed_signal(parsed_signal, user_id=None)
            
            return {
                'success': True,
                'signal': parsed_signal,
                'processing_result': result
            }
            
        except Exception as e:
            self.logger.error(f"Error processing TradingView signal: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _process_generic_signal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process generic signal webhook"""
        try:
            # Check if data contains a text signal or structured data
            if 'text' in data:
                # Text-based signal
                signal_text = data['text']
                parsed_signal = self.signal_parser.parse_signal(signal_text)
            elif 'signal' in data:
                # Structured signal data
                parsed_signal = data['signal']
            else:
                # Try to parse the entire data as a signal
                parsed_signal = data
            
            if not parsed_signal:
                return {
                    'success': False,
                    'error': 'Failed to parse signal'
                }
            
            # Add metadata
            parsed_signal['source'] = 'webhook'
            parsed_signal['webhook_data'] = data
            
            # Process the signal
            result = await self._process_parsed_signal(parsed_signal, user_id=None)
            
            return {
                'success': True,
                'signal': parsed_signal,
                'processing_result': result
            }
            
        except Exception as e:
            self.logger.error(f"Error processing generic signal: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _process_cornix_signal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process Cornix webhook signal"""
        try:
            # Cornix signals come in a specific format
            action = data.get('action', '').upper()
            symbol = data.get('symbol', '').upper()
            price = data.get('price', 0)
            quantity = data.get('quantity', 0)
            stop_loss = data.get('stop_loss', 0)
            take_profit = data.get('take_profit', 0)
            
            # Create structured signal
            parsed_signal = {
                'action': action,
                'symbol': symbol,
                'price': float(price) if price else 0,
                'quantity': float(quantity) if quantity else 0,
                'stop_loss': float(stop_loss) if stop_loss else 0,
                'take_profit': float(take_profit) if take_profit else 0,
                'source': 'cornix',
                'webhook_data': data
            }
            
            # Process the signal
            result = await self._process_parsed_signal(parsed_signal, user_id=None)
            
            return {
                'success': True,
                'signal': parsed_signal,
                'processing_result': result
            }
            
        except Exception as e:
            self.logger.error(f"Error processing Cornix signal: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _process_parsed_signal(self, signal: Dict[str, Any], user_id: Optional[int]) -> Dict[str, Any]:
        """Process a parsed signal through the trading pipeline"""
        try:
            # Validate signal
            validation = self.signal_parser.validate_signal(signal)
            
            if not validation['valid']:
                return {
                    'status': 'rejected',
                    'reason': 'Signal validation failed',
                    'errors': validation['errors']
                }
            
            # Risk management check
            risk_assessment = await self.risk_manager.validate_signal(signal)
            
            if not risk_assessment['valid']:
                return {
                    'status': 'rejected',
                    'reason': 'Risk management check failed',
                    'errors': risk_assessment['errors']
                }
            
            # Save signal to database
            signal_id = await self.db.save_signal(
                user_id or 0,  # Use 0 for webhook signals
                json.dumps(signal.get('webhook_data', {})),
                signal,
                validation
            )
            
            # Check if auto-trading is enabled
            if self.config.AUTO_TRADE_ENABLED:
                # Execute trade
                user_settings = {'risk_percentage': self.config.DEFAULT_RISK_PERCENTAGE}
                trade_result = await self.binance_trader.execute_trade(signal, user_settings)
                
                if trade_result['success']:
                    # Save trade to database
                    await self.db.save_trade(signal_id, user_id or 0, trade_result)
                    
                    # Forward to Cornix
                    cornix_result = await self.cornix.forward_signal(signal, trade_result)
                    
                    # Update signal status
                    await self.db.update_signal_status(signal_id, 'executed')
                    
                    return {
                        'status': 'executed',
                        'trade_result': trade_result,
                        'cornix_result': cornix_result,
                        'signal_id': signal_id
                    }
                else:
                    await self.db.update_signal_status(signal_id, 'failed')
                    return {
                        'status': 'failed',
                        'reason': 'Trade execution failed',
                        'error': trade_result.get('error')
                    }
            else:
                # Just forward to Cornix without executing
                cornix_result = await self.cornix.forward_signal(signal)
                await self.db.update_signal_status(signal_id, 'forwarded')
                
                return {
                    'status': 'forwarded',
                    'cornix_result': cornix_result,
                    'signal_id': signal_id
                }
                
        except Exception as e:
            self.logger.error(f"Error processing parsed signal: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def _get_system_status(self) -> Dict[str, Any]:
        """Get system status information"""
        try:
            # Check component health
            binance_healthy = await self.binance_trader.ping()
            db_healthy = await self.db.health_check()
            
            # Get recent stats
            recent_signals = await self.db.get_signals(limit=10)
            recent_trades = await self.db.get_trades(limit=10)
            
            return jsonify({
                'status': 'online',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {
                    'binance': 'healthy' if binance_healthy else 'unhealthy',
                    'database': 'healthy' if db_healthy else 'unhealthy',
                    'telegram_bot': 'healthy',  # Assume healthy if server is running
                    'cornix': 'configured' if self.config.CORNIX_BOT_UUID else 'not_configured'
                },
                'stats': {
                    'recent_signals': len(recent_signals),
                    'recent_trades': len(recent_trades),
                    'auto_trading': self.config.AUTO_TRADE_ENABLED
                }
            })
            
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            })
    
    async def _get_portfolio_data(self) -> Dict[str, Any]:
        """Get portfolio data"""
        try:
            balance = await self.binance_trader.get_account_balance()
            total_value = await self.binance_trader.get_portfolio_value()
            positions = await self.binance_trader.get_open_positions()
            
            return jsonify({
                'balance': balance,
                'total_value': total_value,
                'positions': positions,
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio data: {e}")
            return jsonify({'error': str(e)})
    
    async def _get_trades_data(self, limit: int) -> Dict[str, Any]:
        """Get recent trades data"""
        try:
            trades = await self.db.get_trades(limit=limit)
            
            return jsonify({
                'trades': trades,
                'count': len(trades),
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Error getting trades data: {e}")
            return jsonify({'error': str(e)})
    
    async def _get_signals_data(self, limit: int) -> Dict[str, Any]:
        """Get recent signals data"""
        try:
            signals = await self.db.get_signals(limit=limit)
            
            return jsonify({
                'signals': signals,
                'count': len(signals),
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Error getting signals data: {e}")
            return jsonify({'error': str(e)})
    
    async def _get_analytics_data(self, days: int) -> Dict[str, Any]:
        """Get trading analytics data"""
        try:
            stats = await self.db.get_trading_stats(days=days)
            portfolio_history = await self.db.get_portfolio_history(days=days)
            
            return jsonify({
                'stats': stats,
                'portfolio_history': portfolio_history,
                'period_days': days,
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Error getting analytics data: {e}")
            return jsonify({'error': str(e)})
    
    def run(self):
        """Run the webhook server"""
        try:
            self.logger.info("Starting webhook server...")
            self.app.run(
                host=self.config.WEBHOOK_HOST,
                port=self.config.WEBHOOK_PORT,
                debug=False,
                threaded=True
            )
        except Exception as e:
            self.logger.error(f"Error running webhook server: {e}")
            raise
