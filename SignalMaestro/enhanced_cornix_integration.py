
"""
Enhanced Cornix Integration with Advanced SL/TP Management
Handles dynamic stop loss updates and position management
"""

import aiohttp
import logging
import json
import asyncio
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from config import Config

class EnhancedCornixIntegration:
    """Enhanced Cornix integration with advanced trade management, retry logic, and comprehensive error handling"""
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.webhook_url = self.config.CORNIX_WEBHOOK_URL
        self.bot_uuid = self.config.CORNIX_BOT_UUID
        
        # Retry configuration
        self.max_retries = 3
        self.base_delay = 1.0
        self.max_delay = 30.0
        self.backoff_multiplier = 2.0
        
        # Connection statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.last_connection_test = None
        self.connection_status = 'unknown'
        
    async def send_advanced_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Send advanced trading signal to Cornix with ML enhancement data and comprehensive error handling"""
        try:
            self.logger.info(f"🚀 Sending advanced signal to Cornix: {signal.get('symbol')} {signal.get('direction')}")
            
            # Validate signal data first
            validation_result = self._validate_advanced_signal(signal)
            if not validation_result['valid']:
                self.logger.error(f"❌ Advanced signal validation failed: {validation_result['error']}")
                return {'success': False, 'error': f"Signal validation failed: {validation_result['error']}"}
            
            # Format for Cornix webhook with advanced features
            cornix_payload = {
                'uuid': self.bot_uuid,
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'enhanced_perfect_scalping_bot_v3',
                'signal_type': 'advanced_ml_enhanced',
                
                # Core trading data
                'action': signal['direction'].lower(),
                'symbol': signal['symbol'].replace('USDT', '/USDT'),
                'entry_price': float(signal['entry']),
                'stop_loss': float(signal['stop_loss']),
                
                # Multiple take profits
                'take_profit_1': float(signal['take_profits'][0]) if len(signal['take_profits']) > 0 else None,
                'take_profit_2': float(signal['take_profits'][1]) if len(signal['take_profits']) > 1 else None,
                'take_profit_3': float(signal['take_profits'][2]) if len(signal['take_profits']) > 2 else None,
                
                'leverage': int(signal.get('leverage', 10)),
                'exchange': 'binance_futures',
                'type': 'futures',
                'margin_type': 'cross',
                'position_size_percentage': 100,
                
                # Enhanced TP distribution
                'tp_distribution': [40, 35, 25],  # 40% at TP1, 35% at TP2, 25% at TP3
                
                # Advanced SL management
                'sl_management': {
                    'move_to_entry_on_tp1': True,
                    'move_to_tp1_on_tp2': True,
                    'close_all_on_tp3': True,
                    'auto_sl_updates': True
                },
                
                # Signal metadata
                'strategy': signal.get('strategy', 'Advanced Time-Fibonacci Theory'),
                'timeframe': 'Multi-TF',
                'ml_enhanced': signal.get('ml_enhanced', False),
                'real_trade_executed': signal.get('real_trade_executed', False),
                'signal_message': signal.get('message', ''),
                'auto_execute': True,
                'priority': 'high'
            }
            
            # Send with retry logic
            result = await self._send_webhook_with_retry(cornix_payload)
            
            if result.get('success'):
                self.logger.info(f"✅ Advanced signal sent to Cornix successfully: {signal['symbol']}")
                self.successful_requests += 1
                return {'success': True, 'response': result}
            else:
                self.logger.warning(f"⚠️ Cornix advanced signal failed: {result}")
                self.failed_requests += 1
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            self.logger.error(f"❌ Error sending advanced signal to Cornix: {e}")
            self.failed_requests += 1
            return {'success': False, 'error': str(e)}
    
    async def send_initial_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Send initial trading signal to Cornix with proper formatting"""
        try:
            # Format for Cornix webhook
            cornix_payload = {
                'uuid': self.bot_uuid,
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'enhanced_perfect_scalping_bot',
                'action': signal['action'].lower(),
                'symbol': signal['symbol'].replace('USDT', '/USDT'),
                'entry_price': float(signal['entry_price']),
                'stop_loss': float(signal['stop_loss']),
                'take_profit_1': float(signal['tp1']),
                'take_profit_2': float(signal['tp2']),
                'take_profit_3': float(signal['tp3']),
                'leverage': signal.get('leverage', 10),
                'exchange': 'binance_futures',
                'type': 'futures',
                'margin_type': 'cross',
                'position_size_percentage': 100,
                
                # Enhanced TP distribution
                'tp_distribution': [40, 35, 25],  # 40% at TP1, 35% at TP2, 25% at TP3
                
                # Advanced SL management
                'sl_management': {
                    'move_to_entry_on_tp1': True,
                    'move_to_tp1_on_tp2': True,
                    'close_all_on_tp3': True,
                    'auto_sl_updates': True
                },
                
                # Signal metadata
                'risk_reward': signal.get('risk_reward_ratio', 3.0),
                'signal_strength': signal.get('signal_strength', 85),
                'strategy': 'Enhanced Perfect Scalping',
                'timeframe': 'Multi-TF',
                'auto_execute': True
            }
            
            result = await self._send_webhook_with_retry(cornix_payload)
            
            if result.get('status') == 'success':
                self.logger.info(f"✅ Initial signal sent to Cornix: {signal['symbol']}")
                return {'success': True, 'response': result}
            else:
                self.logger.warning(f"⚠️ Cornix signal failed: {result}")
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            self.logger.error(f"❌ Error sending signal to Cornix: {e}")
            return {'success': False, 'error': str(e)}
    
    async def update_stop_loss(self, symbol: str, new_sl: float, reason: str) -> Dict[str, Any]:
        """Send stop loss update to Cornix"""
        try:
            update_payload = {
                'uuid': self.bot_uuid,
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'update_stop_loss',
                'symbol': symbol.replace('USDT', '/USDT'),
                'new_stop_loss': new_sl,
                'reason': reason,
                'update_type': 'trailing_sl',
                'auto_execute': True,
                'priority': 'high'
            }
            
            result = await self._send_webhook_with_retry(update_payload)
            
            if result.get('status') == 'success':
                self.logger.info(f"✅ SL update sent to Cornix: {symbol} -> {new_sl}")
                return {'success': True, 'response': result}
            else:
                self.logger.warning(f"⚠️ Cornix SL update failed: {result}")
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            self.logger.error(f"❌ Error updating SL in Cornix: {e}")
            return {'success': False, 'error': str(e)}
    
    async def close_position(self, symbol: str, reason: str, percentage: int = 100) -> Dict[str, Any]:
        """Send position closure to Cornix"""
        try:
            closure_payload = {
                'uuid': self.bot_uuid,
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'close_position',
                'symbol': symbol.replace('USDT', '/USDT'),
                'close_percentage': percentage,
                'reason': reason,
                'close_type': 'market_order',
                'auto_execute': True,
                'priority': 'high',
                'final_closure': percentage == 100
            }
            
            result = await self._send_webhook_with_retry(closure_payload)
            
            if result.get('status') == 'success':
                self.logger.info(f"✅ Position closure sent to Cornix: {symbol} ({percentage}%)")
                return {'success': True, 'response': result}
            else:
                self.logger.warning(f"⚠️ Cornix closure failed: {result}")
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            self.logger.error(f"❌ Error closing position in Cornix: {e}")
            return {'success': False, 'error': str(e)}
    
    async def partial_take_profit(self, symbol: str, tp_level: int, percentage: int) -> Dict[str, Any]:
        """Send partial take profit to Cornix"""
        try:
            tp_payload = {
                'uuid': self.bot_uuid,
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'partial_take_profit',
                'symbol': symbol.replace('USDT', '/USDT'),
                'tp_level': tp_level,
                'close_percentage': percentage,
                'reason': f'TP{tp_level} hit - partial closure',
                'auto_execute': True,
                'update_remaining_sl': True
            }
            
            result = await self._send_webhook_with_retry(tp_payload)
            
            if result.get('status') == 'success':
                self.logger.info(f"✅ Partial TP sent to Cornix: {symbol} TP{tp_level} ({percentage}%)")
                return {'success': True, 'response': result}
            else:
                self.logger.warning(f"⚠️ Cornix partial TP failed: {result}")
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            self.logger.error(f"❌ Error sending partial TP to Cornix: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _send_webhook_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send webhook request to Cornix with retry logic and comprehensive error handling"""
        
        for attempt in range(self.max_retries + 1):
            try:
                self.total_requests += 1
                
                # Calculate delay for this attempt (exponential backoff)
                if attempt > 0:
                    delay = min(self.base_delay * (self.backoff_multiplier ** (attempt - 1)), self.max_delay)
                    self.logger.info(f"🔄 Retrying Cornix webhook in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})")
                    await asyncio.sleep(delay)
                
                result = await self._send_webhook(payload)
                
                # Check if request was successful
                if result.get('success') or result.get('status') == 'success':
                    if attempt > 0:
                        self.logger.info(f"✅ Cornix webhook succeeded on attempt {attempt + 1}")
                    return {'success': True, **result}
                
                # Check if error is retryable
                status_code = result.get('status_code', 0)
                error_msg = result.get('error', '')
                
                if not self._is_retryable_error(status_code, error_msg):
                    self.logger.warning(f"🚫 Non-retryable error from Cornix: {status_code} - {error_msg}")
                    return {'success': False, **result}
                
                if attempt < self.max_retries:
                    self.logger.warning(f"⚠️ Retryable error from Cornix (attempt {attempt + 1}): {status_code} - {error_msg}")
                else:
                    self.logger.error(f"❌ Max retries ({self.max_retries}) exceeded for Cornix webhook")
                    return {'success': False, **result}
                    
            except Exception as e:
                if attempt < self.max_retries:
                    self.logger.warning(f"⚠️ Exception on Cornix webhook attempt {attempt + 1}: {e}")
                else:
                    self.logger.error(f"❌ Final attempt failed for Cornix webhook: {e}")
                    return {'success': False, 'error': f'All retry attempts failed: {str(e)}'}
        
        return {'success': False, 'error': 'Max retries exceeded'}
    
    def _is_retryable_error(self, status_code: int, error_msg: str) -> bool:
        """Determine if an error is retryable"""
        # Retryable HTTP status codes
        retryable_codes = [408, 429, 500, 502, 503, 504]
        
        # Non-retryable codes (client errors)
        non_retryable_codes = [400, 401, 403, 404, 405, 409, 422]
        
        if status_code in non_retryable_codes:
            return False
            
        if status_code in retryable_codes:
            return True
            
        # Network-related errors are usually retryable
        retryable_errors = [
            'timeout', 'connection', 'network', 'dns', 'ssl',
            'temporary failure', 'service unavailable'
        ]
        
        error_lower = error_msg.lower()
        return any(err in error_lower for err in retryable_errors)
    
    async def _send_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send single webhook request to Cornix with enhanced error handling"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'EnhancedPerfectScalpingBot/3.0',
                'Accept': 'application/json'
            }
            
            # Add authentication if configured
            if hasattr(self.config, 'WEBHOOK_SECRET') and self.config.WEBHOOK_SECRET:
                headers['Authorization'] = f"Bearer {self.config.WEBHOOK_SECRET}"
            
            # Enhanced timeout configuration
            timeout = aiohttp.ClientTimeout(
                total=30,  # Total timeout
                connect=10,  # Connection timeout
                sock_read=15  # Socket read timeout
            )
            
            self.logger.debug(f"📤 Sending webhook to: {self.webhook_url}")
            self.logger.debug(f"📊 Payload size: {len(json.dumps(payload))} bytes")
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers=headers
                ) as response:
                    
                    response_text = await response.text()
                    self.logger.debug(f"📥 Cornix response: {response.status} - {len(response_text)} bytes")
                    
                    if response.status == 200:
                        try:
                            response_data = json.loads(response_text)
                            return {
                                'success': True,
                                'status': 'success',
                                'status_code': response.status,
                                'response': response_data
                            }
                        except json.JSONDecodeError:
                            # Some webhooks return plain text
                            return {
                                'success': True,
                                'status': 'success',
                                'status_code': response.status,
                                'response': response_text
                            }
                    elif response.status == 201:
                        # Created - also successful
                        return {
                            'success': True,
                            'status': 'success',
                            'status_code': response.status,
                            'response': response_text
                        }
                    else:
                        error_detail = self._categorize_http_error(response.status)
                        return {
                            'success': False,
                            'status': 'error',
                            'status_code': response.status,
                            'error': response_text,
                            'error_category': error_detail['category'],
                            'error_description': error_detail['description']
                        }
                        
        except asyncio.TimeoutError:
            return {
                'success': False,
                'status': 'error',
                'error': 'Request timeout - Cornix server did not respond in time',
                'error_category': 'timeout'
            }
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'status': 'error',
                'error': f'Network error: {str(e)}',
                'error_category': 'network'
            }
        except Exception as e:
            return {
                'success': False,
                'status': 'error',
                'error': f'Unexpected error: {str(e)}',
                'error_category': 'unknown'
            }
    
    def _categorize_http_error(self, status_code: int) -> Dict[str, str]:
        """Categorize HTTP error codes for better debugging"""
        error_categories = {
            400: {'category': 'client_error', 'description': 'Bad Request - Invalid payload format'},
            401: {'category': 'auth_error', 'description': 'Unauthorized - Check webhook secret/API key'},
            403: {'category': 'auth_error', 'description': 'Forbidden - Insufficient permissions'},
            404: {'category': 'config_error', 'description': 'Not Found - Check webhook URL'},
            405: {'category': 'client_error', 'description': 'Method Not Allowed - POST not supported'},
            408: {'category': 'timeout', 'description': 'Request Timeout - Server processing too slow'},
            409: {'category': 'client_error', 'description': 'Conflict - Duplicate request'},
            422: {'category': 'validation_error', 'description': 'Unprocessable Entity - Data validation failed'},
            429: {'category': 'rate_limit', 'description': 'Too Many Requests - Rate limit exceeded'},
            500: {'category': 'server_error', 'description': 'Internal Server Error - Cornix server issue'},
            502: {'category': 'server_error', 'description': 'Bad Gateway - Server proxy issue'},
            503: {'category': 'server_error', 'description': 'Service Unavailable - Server overloaded'},
            504: {'category': 'timeout', 'description': 'Gateway Timeout - Server processing timeout'}
        }
        
        return error_categories.get(status_code, {
            'category': 'unknown_error',
            'description': f'Unknown HTTP error code: {status_code}'
        })
    
    def _validate_advanced_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Validate advanced signal data before sending to Cornix"""
        try:
            # Required fields
            required_fields = ['symbol', 'direction', 'entry', 'stop_loss', 'take_profits', 'leverage']
            
            for field in required_fields:
                if field not in signal:
                    return {'valid': False, 'error': f'Missing required field: {field}'}
            
            # Validate symbol format
            symbol = signal['symbol']
            if not symbol or not symbol.endswith('USDT'):
                return {'valid': False, 'error': f'Invalid symbol format: {symbol}. Expected format: XXXUSDT'}
            
            # Validate direction
            direction = signal['direction'].upper()
            if direction not in ['LONG', 'SHORT', 'BUY', 'SELL']:
                return {'valid': False, 'error': f'Invalid direction: {direction}. Must be LONG, SHORT, BUY, or SELL'}
            
            # Validate numeric values
            try:
                entry = float(signal['entry'])
                stop_loss = float(signal['stop_loss'])
                leverage = int(signal['leverage'])
                
                if entry <= 0 or stop_loss <= 0:
                    return {'valid': False, 'error': 'Entry price and stop loss must be positive'}
                
                if leverage < 1 or leverage > 125:
                    return {'valid': False, 'error': f'Invalid leverage: {leverage}. Must be between 1 and 125'}
                    
            except (ValueError, TypeError) as e:
                return {'valid': False, 'error': f'Invalid numeric values: {e}'}
            
            # Validate take profits
            take_profits = signal['take_profits']
            if not isinstance(take_profits, list) or len(take_profits) < 1:
                return {'valid': False, 'error': 'At least one take profit level is required'}
            
            try:
                tp_values = [float(tp) for tp in take_profits]
                if any(tp <= 0 for tp in tp_values):
                    return {'valid': False, 'error': 'All take profit levels must be positive'}
            except (ValueError, TypeError):
                return {'valid': False, 'error': 'Invalid take profit values'}
            
            # Validate price relationships
            if direction in ['LONG', 'BUY']:
                # For long positions: SL < Entry < TP1 < TP2 < TP3
                if stop_loss >= entry:
                    return {'valid': False, 'error': f'For LONG: Stop loss ({stop_loss}) must be below entry ({entry})'}
                
                if tp_values[0] <= entry:
                    return {'valid': False, 'error': f'For LONG: First take profit ({tp_values[0]}) must be above entry ({entry})'}
                
                # Check TP ordering
                for i in range(len(tp_values) - 1):
                    if tp_values[i] >= tp_values[i + 1]:
                        return {'valid': False, 'error': f'Take profits must be in ascending order for LONG'}
                        
            else:  # SHORT/SELL
                # For short positions: TP3 < TP2 < TP1 < Entry < SL
                if stop_loss <= entry:
                    return {'valid': False, 'error': f'For SHORT: Stop loss ({stop_loss}) must be above entry ({entry})'}
                
                if tp_values[0] >= entry:
                    return {'valid': False, 'error': f'For SHORT: First take profit ({tp_values[0]}) must be below entry ({entry})'}
                
                # Check TP ordering (descending for shorts)
                for i in range(len(tp_values) - 1):
                    if tp_values[i] <= tp_values[i + 1]:
                        return {'valid': False, 'error': f'Take profits must be in descending order for SHORT'}
            
            return {'valid': True, 'error': None}
            
        except Exception as e:
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    async def test_connection(self) -> Dict[str, Any]:
        """Comprehensive Cornix webhook connection test with detailed diagnostics"""
        try:
            self.logger.info("🔍 Starting comprehensive Cornix connection test...")
            
            # Pre-flight checks
            preflight_result = self._check_configuration()
            if not preflight_result['valid']:
                return {
                    'success': False,
                    'stage': 'preflight',
                    'error': preflight_result['error'],
                    'recommendations': preflight_result.get('recommendations', [])
                }
            
            # Test basic connectivity
            test_start = time.time()
            test_payload = {
                'type': 'connection_test',
                'timestamp': datetime.utcnow().isoformat(),
                'uuid': self.bot_uuid,
                'source': 'enhanced_perfect_scalping_bot_v3',
                'test_message': 'Enhanced bot connection test with comprehensive diagnostics',
                'test_id': f'test_{int(time.time())}',
                'version': '3.0'
            }
            
            result = await self._send_webhook_with_retry(test_payload)
            test_duration = time.time() - test_start
            
            self.last_connection_test = datetime.utcnow()
            
            if result.get('success'):
                self.connection_status = 'connected'
                self.logger.info(f"✅ Cornix connection test successful in {test_duration:.2f}s")
                
                return {
                    'success': True,
                    'stage': 'complete',
                    'response': result,
                    'webhook_url': self.webhook_url,
                    'bot_uuid': self.bot_uuid,
                    'test_duration': test_duration,
                    'connection_status': self.connection_status,
                    'statistics': self.get_connection_statistics()
                }
            else:
                self.connection_status = 'failed'
                self.logger.error(f"❌ Cornix connection test failed after {test_duration:.2f}s")
                
                return {
                    'success': False,
                    'stage': 'webhook_test',
                    'error': result.get('error', 'Unknown error'),
                    'webhook_url': self.webhook_url,
                    'bot_uuid': self.bot_uuid,
                    'test_duration': test_duration,
                    'connection_status': self.connection_status,
                    'debug_info': result
                }
            
        except Exception as e:
            self.connection_status = 'error'
            self.logger.error(f"❌ Connection test exception: {e}")
            return {
                'success': False,
                'stage': 'exception',
                'error': str(e),
                'connection_status': self.connection_status
            }
    
    def _check_configuration(self) -> Dict[str, Any]:
        """Check Cornix configuration completeness"""
        issues = []
        recommendations = []
        
        if not self.webhook_url:
            issues.append('CORNIX_WEBHOOK_URL not configured')
            recommendations.append('Set CORNIX_WEBHOOK_URL environment variable')
        elif not self.webhook_url.startswith(('http://', 'https://')):
            issues.append('Invalid webhook URL format')
            recommendations.append('Webhook URL must start with http:// or https://')
        
        if not self.bot_uuid:
            issues.append('CORNIX_BOT_UUID not configured')
            recommendations.append('Set CORNIX_BOT_UUID environment variable from Cornix dashboard')
        
        if hasattr(self.config, 'WEBHOOK_SECRET') and not self.config.WEBHOOK_SECRET:
            recommendations.append('Consider setting WEBHOOK_SECRET for enhanced security')
        
        return {
            'valid': len(issues) == 0,
            'error': '; '.join(issues) if issues else None,
            'recommendations': recommendations
        }
    
    def get_connection_statistics(self) -> Dict[str, Any]:
        """Get connection statistics and performance metrics"""
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': round(success_rate, 2),
            'last_connection_test': self.last_connection_test.isoformat() if self.last_connection_test else None,
            'connection_status': self.connection_status,
            'webhook_url_configured': bool(self.webhook_url),
            'bot_uuid_configured': bool(self.bot_uuid)
        }
    
    async def validate_webhook_configuration(self) -> Dict[str, Any]:
        """Comprehensive webhook configuration validation"""
        try:
            self.logger.info("🔍 Validating Cornix webhook configuration...")
            
            validation_result = {
                'webhook_url': {
                    'configured': bool(self.webhook_url),
                    'valid_format': False,
                    'reachable': False
                },
                'bot_uuid': {
                    'configured': bool(self.bot_uuid),
                    'valid_format': False
                },
                'authentication': {
                    'webhook_secret_configured': bool(hasattr(self.config, 'WEBHOOK_SECRET') and self.config.WEBHOOK_SECRET)
                },
                'overall_status': 'unknown'
            }
            
            # Validate webhook URL
            if self.webhook_url:
                validation_result['webhook_url']['valid_format'] = self.webhook_url.startswith(('http://', 'https://'))
                
                # Test reachability
                connection_test = await self.test_connection()
                validation_result['webhook_url']['reachable'] = connection_test.get('success', False)
            
            # Validate bot UUID format (basic check)
            if self.bot_uuid:
                # Basic UUID format check (not strict RFC validation)
                validation_result['bot_uuid']['valid_format'] = len(self.bot_uuid) > 10 and '-' in self.bot_uuid
            
            # Determine overall status
            if (validation_result['webhook_url']['configured'] and 
                validation_result['webhook_url']['valid_format'] and 
                validation_result['webhook_url']['reachable'] and
                validation_result['bot_uuid']['configured'] and
                validation_result['bot_uuid']['valid_format']):
                validation_result['overall_status'] = 'ready'
            elif (validation_result['webhook_url']['configured'] and 
                  validation_result['bot_uuid']['configured']):
                validation_result['overall_status'] = 'configured_but_unreachable'
            else:
                validation_result['overall_status'] = 'incomplete_configuration'
            
            validation_result['statistics'] = self.get_connection_statistics()
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Error validating webhook configuration: {e}")
            return {
                'overall_status': 'validation_error',
                'error': str(e)
            }
    
    async def send_test_signal(self) -> Dict[str, Any]:
        """Send a test signal to verify Cornix integration is working properly"""
        try:
            self.logger.info("🧪 Sending test signal to Cornix...")
            
            # Create a realistic test signal
            test_signal = {
                'symbol': 'BTCUSDT',
                'direction': 'LONG',
                'entry': 45000.0,
                'stop_loss': 44000.0,
                'take_profits': [46000.0, 47000.0, 48000.0],
                'leverage': 10,
                'strategy': 'Test Signal',
                'ml_enhanced': False,
                'real_trade_executed': False,
                'message': 'This is a test signal to verify Cornix integration'
            }
            
            result = await self.send_advanced_signal(test_signal)
            
            if result.get('success'):
                self.logger.info("✅ Test signal sent successfully to Cornix")
            else:
                self.logger.warning(f"⚠️ Test signal failed: {result.get('error')}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error sending test signal: {e}")
            return {'success': False, 'error': str(e)}
    
    def format_tradingview_alert(self, signal: Dict[str, Any]) -> str:
        """Format signal as TradingView alert for Cornix"""
        try:
            parts = [
                f"uuid={self.bot_uuid}",
                f"action={signal['action'].lower()}",
                f"symbol={signal['symbol']}",
                f"price={signal['entry_price']}",
                f"sl={signal['stop_loss']}",
                f"tp1={signal['tp1']}",
                f"tp2={signal['tp2']}",
                f"tp3={signal['tp3']}"
            ]
            
            return "\n".join(parts)
            
        except Exception as e:
            self.logger.error(f"❌ Error formatting TradingView alert: {e}")
            return ""
    
    def reset_statistics(self) -> None:
        """Reset connection statistics"""
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.last_connection_test = None
        self.connection_status = 'unknown'
        self.logger.info("🔄 Cornix integration statistics reset")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of Cornix integration"""
        stats = self.get_connection_statistics()
        
        # Determine health based on recent performance
        if stats['total_requests'] == 0:
            health = 'unknown'
        elif stats['success_rate'] >= 95:
            health = 'excellent'
        elif stats['success_rate'] >= 80:
            health = 'good' 
        elif stats['success_rate'] >= 60:
            health = 'fair'
        else:
            health = 'poor'
        
        return {
            'health': health,
            'connection_status': self.connection_status,
            'statistics': stats,
            'configuration': {
                'webhook_url_configured': bool(self.webhook_url),
                'bot_uuid_configured': bool(self.bot_uuid),
                'webhook_secret_configured': bool(hasattr(self.config, 'WEBHOOK_SECRET') and self.config.WEBHOOK_SECRET)
            },
            'retry_config': {
                'max_retries': self.max_retries,
                'base_delay': self.base_delay,
                'max_delay': self.max_delay,
                'backoff_multiplier': self.backoff_multiplier
            }
        }
