
import aiohttp
import logging
from typing import Optional, List, Dict
import websockets
import json


"""
Binance trading integration using ccxt library
Handles trade execution, portfolio management, and market data
ENHANCED with comprehensive error handling and resilience
ENHANCED with real-time WebSocket market data streaming
"""

import asyncio
import logging
import ccxt.async_support as ccxt
from typing import Dict, Any, List, Optional, Callable
from decimal import Decimal, ROUND_DOWN
import time
from datetime import datetime, timedelta
import threading

from config import Config
from technical_analysis import TechnicalAnalysis

# Import dynamic leverage manager
try:
    from dynamic_leverage_manager import DynamicLeverageManager
    DYNAMIC_LEVERAGE_AVAILABLE = True
except ImportError:
    DYNAMIC_LEVERAGE_AVAILABLE = False

# Enhanced error handling imports
try:
    from advanced_error_handler import (
        handle_errors, RetryConfigs, CircuitBreaker,
        APIException, NetworkException, TradingException,
        InsufficientFundsException, RateLimitException
    )
    from api_resilience_layer import resilient_api_call, get_global_resilience_manager
    ENHANCED_ERROR_HANDLING = True
except ImportError:
    ENHANCED_ERROR_HANDLING = False
    # Create fallback decorators
    def handle_errors(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def resilient_api_call(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

class BinanceTrader:
    """Binance trading interface using ccxt with enhanced error handling"""
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.exchange = None
        self.technical_analysis = TechnicalAnalysis()
        
        # Enhanced error handling components
        self.enhanced_error_handling = ENHANCED_ERROR_HANDLING
        self.circuit_breaker = None
        self.resilience_manager = None
        
        # Dynamic leverage management
        self.leverage_manager = None
        if DYNAMIC_LEVERAGE_AVAILABLE and self.config.ENABLE_DYNAMIC_LEVERAGE:
            try:
                self.leverage_manager = DynamicLeverageManager()
                self.logger.info("🎯 Dynamic leverage management enabled")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to initialize dynamic leverage manager: {e}")
        
        # Current leverage settings per symbol
        self.current_leverage = {}  # symbol -> leverage
        self.last_leverage_check = {}  # symbol -> timestamp
        
        # Real-time market data streaming
        self.websocket_streams = {}  # symbol -> websocket connection
        self.current_prices = {}  # symbol -> current price
        self.price_callbacks = {}  # symbol -> list of callback functions
        self.ws_running = False
        self.ws_base_url = "wss://fstream.binance.com/ws/"
        
        # Position tracking and TP/SL management
        self.active_positions = {}  # symbol -> position data
        self.stop_loss_orders = {}  # symbol -> stop loss order info
        self.take_profit_orders = {}  # symbol -> list of TP orders
        self.position_monitors = {}  # symbol -> monitoring task
        
        # Import and initialize TP/SL system
        try:
            from dynamic_stop_loss_system import ThreeSLOneTpManager, ThreeSLOneTpConfig
            self.tp_sl_managers = {}  # symbol -> ThreeSLOneTpManager
            self.tp_sl_config = ThreeSLOneTpConfig()
            self.tp_sl_enabled = True
            self.logger.info("✅ 3SL/1TP system enabled")
        except ImportError as e:
            self.tp_sl_enabled = False
            self.logger.warning(f"⚠️ TP/SL system not available: {e}")
        
        if ENHANCED_ERROR_HANDLING:
            # Initialize circuit breaker for Binance API
            self.circuit_breaker = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=300  # 5 minutes
            )
            
            # Get global resilience manager
            self.resilience_manager = get_global_resilience_manager()
            
            self.logger.info("✅ Enhanced error handling enabled for Binance trader")
        else:
            self.logger.warning("⚠️ Enhanced error handling not available - using basic error handling")
        
    async def initialize(self):
        """Initialize Binance exchange connection"""
        try:
            # Use testnet if API keys are empty or testnet is enabled
            use_testnet = (not self.config.BINANCE_API_KEY or 
                          not self.config.BINANCE_API_SECRET or 
                          self.config.BINANCE_TESTNET)
            
            # Configure for futures trading if enabled
            default_type = 'future' if self.config.ENABLE_FUTURES_TRADING else 'spot'
            
            self.exchange = ccxt.binance({
                'apiKey': self.config.BINANCE_API_KEY or 'dummy_key',
                'secret': self.config.BINANCE_API_SECRET or 'dummy_secret',
                'sandbox': use_testnet,
                'timeout': self.config.BINANCE_REQUEST_TIMEOUT * 1000,
                'rateLimit': 1200,
                'enableRateLimit': True,
                'options': {
                    'defaultType': default_type,
                }
            })
            
            if use_testnet:
                self.logger.info("Using Binance testnet (sandbox mode)")
            
            # Test connection
            await self.exchange.load_markets()
            self.logger.info("Binance exchange initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Binance exchange: {e}")
            raise
    
    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
    
    async def ping(self) -> bool:
        """Test exchange connectivity"""
        try:
            # Try to fetch server time first (doesn't require API auth)
            await self.exchange.fetch_time()
            self.logger.info("Binance connection successful")
            return True
        except Exception as e:
            self.logger.warning(f"Binance ping failed: {e}")
            try:
                # Fallback: try to fetch ticker for BTCUSDT (public endpoint)
                await self.exchange.fetch_ticker('BTC/USDT')
                self.logger.info("Binance public API accessible")
                return True
            except Exception as e2:
                self.logger.error(f"Binance completely inaccessible: {e2}")
                return False
    
    @handle_errors(retry_config=RetryConfigs.API_RETRY)
    @resilient_api_call
    async def get_account_balance(self) -> Dict[str, Dict[str, float]]:
        """Get account balance for all assets with enhanced error handling"""
        try:
            # Use resilient API call if available
            if self.resilience_manager:
                balance = await self.resilience_manager.make_resilient_api_call(
                    "binance", self.exchange.fetch_balance
                )
            else:
                balance = await self.exchange.fetch_balance()
            
            # Filter out zero balances and format response
            filtered_balance = {}
            for symbol, data in balance['total'].items():
                if data > 0:
                    filtered_balance[symbol] = {
                        'free': balance['free'].get(symbol, 0),
                        'used': balance['used'].get(symbol, 0),
                        'total': data
                    }
            
            self.logger.debug(f"💰 Retrieved balance for {len(filtered_balance)} assets")
            return filtered_balance
            
        except Exception as e:
            self.logger.error(f"❌ Error getting account balance: {e}")
            if ENHANCED_ERROR_HANDLING:
                if 'rate limit' in str(e).lower():
                    raise RateLimitException("Rate limit exceeded getting account balance")
                elif 'network' in str(e).lower() or 'timeout' in str(e).lower():
                    raise NetworkException(f"Network error getting account balance: {e}")
                else:
                    raise APIException(f"API error getting account balance: {e}")
            raise
    
    async def get_portfolio_value(self) -> float:
        """Calculate total portfolio value in USDT"""
        try:
            balance = await self.get_account_balance()
            total_value = 0.0
            
            for symbol, data in balance.items():
                if symbol == 'USDT':
                    total_value += data['total']
                else:
                    # Convert to USDT value
                    try:
                        ticker_symbol = f"{symbol}/USDT"
                        if ticker_symbol in self.exchange.markets:
                            ticker = await self.exchange.fetch_ticker(ticker_symbol)
                            total_value += data['total'] * ticker['last']
                    except Exception:
                        # Skip if can't get price
                        continue
            
            return total_value
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio value: {e}")
            return 0.0
    
    @handle_errors(retry_config=RetryConfigs.API_RETRY)
    @resilient_api_call
    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for symbol with enhanced error handling"""
        try:
            # Use resilient API call if available
            if self.resilience_manager:
                ticker = await self.resilience_manager.make_resilient_api_call(
                    "binance", self.exchange.fetch_ticker, symbol
                )
            else:
                ticker = await self.exchange.fetch_ticker(symbol)
                
            price = ticker.get('last') or ticker.get('close') or ticker.get('price')
            
            if price is None:
                self.logger.warning(f"⚠️ No price data available for {symbol}")
                if ENHANCED_ERROR_HANDLING:
                    raise APIException(f"No price data returned for {symbol}")
                return 0.0
                
            price_float = float(price)
            self.logger.debug(f"📊 Price for {symbol}: {price_float}")
            return price_float
            
        except Exception as e:
            self.logger.error(f"❌ Error getting price for {symbol}: {e}")
            if ENHANCED_ERROR_HANDLING:
                if 'rate limit' in str(e).lower():
                    raise RateLimitException(f"Rate limit exceeded getting price for {symbol}")
                elif 'network' in str(e).lower() or 'timeout' in str(e).lower():
                    raise NetworkException(f"Network error getting price for {symbol}: {e}")
                else:
                    raise APIException(f"API error getting price for {symbol}: {e}")
            return 0.0
    
    @handle_errors(retry_config=RetryConfigs.API_RETRY)
    @resilient_api_call
    async def get_market_data(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[List]:
        """Get OHLCV market data with enhanced error handling"""
        try:
            # Use resilient API call if available
            if self.resilience_manager:
                ohlcv = await self.resilience_manager.make_resilient_api_call(
                    "binance", self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit
                )
            else:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Validate the data
            if not ohlcv or len(ohlcv) == 0:
                self.logger.warning(f"⚠️ No OHLCV data returned for {symbol} {timeframe}")
                if ENHANCED_ERROR_HANDLING:
                    raise APIException(f"No OHLCV data available for {symbol} {timeframe}")
                return []
                
            # Check if data contains valid values
            valid_data = []
            for candle in ohlcv:
                if len(candle) >= 6 and all(x is not None for x in candle[:6]):
                    valid_data.append(candle)
            
            if len(valid_data) == 0:
                self.logger.warning(f"⚠️ No valid OHLCV data for {symbol} {timeframe}")
                if ENHANCED_ERROR_HANDLING:
                    raise APIException(f"Invalid OHLCV data format for {symbol} {timeframe}")
                return []
                
            self.logger.debug(f"📊 Retrieved {len(valid_data)} candles for {symbol} {timeframe}")
            return valid_data
            
        except Exception as e:
            self.logger.error(f"❌ Error getting market data for {symbol} {timeframe}: {e}")
            if ENHANCED_ERROR_HANDLING:
                if 'rate limit' in str(e).lower():
                    raise RateLimitException(f"Rate limit exceeded getting market data for {symbol}")
                elif 'network' in str(e).lower() or 'timeout' in str(e).lower():
                    raise NetworkException(f"Network error getting market data: {e}")
                else:
                    raise APIException(f"API error getting market data: {e}")
            return []
    
    async def get_technical_analysis(self, symbol: str) -> Dict[str, Any]:
        """Get technical analysis for symbol"""
        try:
            # Get market data
            ohlcv_1h = await self.get_market_data(symbol, '1h', 100)
            ohlcv_4h = await self.get_market_data(symbol, '4h', 100)
            ohlcv_1d = await self.get_market_data(symbol, '1d', 50)
            
            # Check if we have valid market data
            if not ohlcv_1h and not ohlcv_4h and not ohlcv_1d:
                self.logger.warning(f"No market data available for {symbol}")
                return {'symbol': symbol, 'error': 'No market data available'}
            
            # Get 24h price change with fallback
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                price_change_24h = ticker.get('percentage', 0)
                volume = ticker.get('baseVolume', 0)
            except Exception as ticker_error:
                self.logger.warning(f"Error getting ticker data for {symbol}: {ticker_error}")
                price_change_24h = 0
                volume = 0
            
            # Calculate technical indicators
            analysis = await self.technical_analysis.analyze(
                ohlcv_1h, ohlcv_4h, ohlcv_1d
            )
            
            # Only add these if analysis was successful
            if 'error' not in analysis:
                analysis['price_change_24h'] = price_change_24h
                analysis['volume'] = volume
                analysis['symbol'] = symbol
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error getting technical analysis for {symbol}: {e}")
            return {'symbol': symbol, 'error': str(e)}
    
    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get open futures positions (if using futures)"""
        try:
            # For spot trading, we'll return current holdings as "positions"
            balance = await self.get_account_balance()
            positions = []
            
            for symbol, data in balance.items():
                if symbol != 'USDT' and data['total'] > 0:
                    try:
                        ticker_symbol = f"{symbol}/USDT"
                        if ticker_symbol in self.exchange.markets:
                            ticker = await self.exchange.fetch_ticker(ticker_symbol)
                            current_price = ticker['last']
                            
                            # Estimate unrealized PnL (simplified)
                            # This would be more accurate with actual entry prices
                            estimated_value = data['total'] * current_price
                            
                            positions.append({
                                'symbol': ticker_symbol,
                                'side': 'LONG',  # Spot holdings are always long
                                'size': data['total'],
                                'entryPrice': current_price,  # Simplified
                                'markPrice': current_price,
                                'unrealizedPnl': 0,  # Would need trade history for accurate PnL
                                'value': estimated_value
                            })
                    except Exception:
                        continue
            
            return positions
            
        except Exception as e:
            self.logger.error(f"Error getting open positions: {e}")
            return []
    
    # =============================================================================
    # DYNAMIC LEVERAGE MANAGEMENT METHODS
    # =============================================================================
    
    async def adjust_leverage_dynamically(self, symbol: str) -> Dict[str, Any]:
        """
        Dynamically adjust leverage for a symbol based on current volatility
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Dictionary with adjustment results
        """
        try:
            if not self.leverage_manager or not self.config.ENABLE_FUTURES_TRADING:
                return {
                    'success': False,
                    'message': 'Dynamic leverage management not available or futures trading disabled'
                }
            
            # Check if we need to update leverage (cooldown period)
            current_time = time.time()
            last_check = self.last_leverage_check.get(symbol, 0)
            cooldown = self.config.LEVERAGE_CHANGE_COOLDOWN
            
            if current_time - last_check < cooldown:
                return {
                    'success': False,
                    'message': f'Leverage check cooldown active for {symbol} ({int(cooldown - (current_time - last_check))}s remaining)'
                }
            
            # Get current market data for volatility calculation
            ohlcv_data = {}
            timeframes = ['5m', '15m', '1h', '4h']
            
            for tf in timeframes:
                try:
                    market_data = await self.get_market_data(symbol, tf, 100)
                    if market_data:
                        ohlcv_data[tf] = market_data
                except Exception as e:
                    self.logger.warning(f"Failed to get {tf} data for {symbol}: {e}")
            
            if len(ohlcv_data) < 2:
                return {
                    'success': False,
                    'message': f'Insufficient market data for volatility analysis of {symbol}'
                }
            
            # Get current leverage
            current_leverage = self.current_leverage.get(symbol, self.config.DEFAULT_LEVERAGE)
            
            # Calculate optimal leverage using the leverage manager
            adjustment = await self.leverage_manager.adjust_leverage_for_symbol(
                symbol, current_leverage, ohlcv_data
            )
            
            if not adjustment:
                self.last_leverage_check[symbol] = current_time
                return {
                    'success': True,
                    'message': f'No leverage adjustment needed for {symbol}',
                    'current_leverage': current_leverage
                }
            
            # Apply the new leverage
            try:
                await self.set_leverage(symbol, adjustment.new_leverage)
                self.current_leverage[symbol] = adjustment.new_leverage
                self.last_leverage_check[symbol] = current_time
                
                return {
                    'success': True,
                    'message': f'Leverage adjusted for {symbol}',
                    'old_leverage': adjustment.old_leverage,
                    'new_leverage': adjustment.new_leverage,
                    'volatility_score': adjustment.volatility_score,
                    'reason': adjustment.reason,
                    'position_size_impact': adjustment.position_size_impact
                }
                
            except Exception as e:
                self.logger.error(f"Failed to set leverage for {symbol}: {e}")
                return {
                    'success': False,
                    'message': f'Failed to apply leverage adjustment for {symbol}: {e}'
                }
            
        except Exception as e:
            self.logger.error(f"Error in dynamic leverage adjustment for {symbol}: {e}")
            return {
                'success': False,
                'message': f'Error in leverage adjustment: {e}'
            }
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a futures symbol
        
        Args:
            symbol: Trading symbol
            leverage: Leverage value (2-125 depending on symbol)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.config.ENABLE_FUTURES_TRADING:
                self.logger.warning("Futures trading is disabled - cannot set leverage")
                return False
            
            # Validate leverage range
            min_lev = self.config.MIN_LEVERAGE
            max_lev = self.config.MAX_LEVERAGE
            
            if leverage < min_lev or leverage > max_lev:
                self.logger.warning(f"Leverage {leverage}x outside allowed range ({min_lev}x-{max_lev}x)")
                leverage = max(min_lev, min(leverage, max_lev))
            
            # Set leverage using ccxt
            response = await self.exchange.set_leverage(leverage, symbol)
            
            if response:
                self.current_leverage[symbol] = leverage
                self.logger.info(f"⚡ {symbol}: Leverage set to {leverage}x")
                return True
            else:
                self.logger.warning(f"Failed to set leverage for {symbol}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error setting leverage for {symbol}: {e}")
            return False
    
    async def get_current_leverage(self, symbol: str) -> int:
        """
        Get current leverage for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current leverage value
        """
        try:
            if symbol in self.current_leverage:
                return self.current_leverage[symbol]
            
            if not self.config.ENABLE_FUTURES_TRADING:
                return 1  # Spot trading has 1x leverage
            
            # Try to get from exchange if not cached
            try:
                positions = await self.exchange.fetch_positions([symbol])
                if positions and len(positions) > 0:
                    leverage = positions[0].get('leverage', self.config.DEFAULT_LEVERAGE)
                    self.current_leverage[symbol] = int(leverage)
                    return int(leverage)
            except Exception as e:
                self.logger.debug(f"Could not fetch leverage from exchange for {symbol}: {e}")
            
            # Return default if not found
            return self.config.DEFAULT_LEVERAGE
            
        except Exception as e:
            self.logger.error(f"Error getting current leverage for {symbol}: {e}")
            return self.config.DEFAULT_LEVERAGE
    
    async def get_futures_account_balance(self) -> Dict[str, Any]:
        """Get futures account balance"""
        try:
            if not self.config.ENABLE_FUTURES_TRADING:
                self.logger.warning("Futures trading is disabled")
                return {}
            
            # Get futures account info
            balance = await self.exchange.fetch_balance()
            
            if 'USDT' in balance:
                usdt_info = balance['USDT']
                return {
                    'total_wallet_balance': usdt_info.get('total', 0),
                    'available_balance': usdt_info.get('free', 0),
                    'used_margin': usdt_info.get('used', 0),
                    'unrealized_pnl': balance.get('info', {}).get('totalUnrealizedProfit', 0),
                    'margin_ratio': balance.get('info', {}).get('totalMarginBalance', 0)
                }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error getting futures account balance: {e}")
            return {}
    
    async def get_futures_positions(self) -> List[Dict[str, Any]]:
        """Get all open futures positions"""
        try:
            if not self.config.ENABLE_FUTURES_TRADING:
                return []
            
            positions = await self.exchange.fetch_positions()
            
            # Filter open positions
            open_positions = []
            for position in positions:
                if position['contracts'] > 0:  # Position size > 0
                    open_positions.append({
                        'symbol': position['symbol'],
                        'side': position['side'],
                        'size': position['contracts'],
                        'notional': position['notional'],
                        'entry_price': position['entryPrice'],
                        'mark_price': position['markPrice'],
                        'leverage': position.get('leverage', 1),
                        'unrealized_pnl': position['unrealizedPnl'],
                        'unrealized_pnl_percentage': position['percentage'],
                        'margin_used': position['initialMargin']
                    })
            
            return open_positions
            
        except Exception as e:
            self.logger.error(f"Error getting futures positions: {e}")
            return []
    
    async def calculate_optimal_leverage_for_trade(self, symbol: str, trade_direction: str, 
                                                 trade_size_usdt: float) -> Dict[str, Any]:
        """
        Calculate optimal leverage for a specific trade
        
        Args:
            symbol: Trading symbol
            trade_direction: 'LONG' or 'SHORT'
            trade_size_usdt: Trade size in USDT
            
        Returns:
            Dictionary with optimal leverage and risk analysis
        """
        try:
            if not self.leverage_manager:
                return {
                    'recommended_leverage': self.config.DEFAULT_LEVERAGE,
                    'max_leverage': self.config.MAX_LEVERAGE,
                    'risk_analysis': 'Dynamic leverage management not available',
                    'confidence': 'low'
                }
            
            # Get market data for volatility analysis
            ohlcv_data = {}
            timeframes = ['5m', '15m', '1h', '4h']
            
            for tf in timeframes:
                try:
                    market_data = await self.get_market_data(symbol, tf, 100)
                    if market_data:
                        ohlcv_data[tf] = market_data
                except Exception:
                    continue
            
            if len(ohlcv_data) < 2:
                return {
                    'recommended_leverage': self.config.DEFAULT_LEVERAGE,
                    'max_leverage': self.config.MAX_LEVERAGE,
                    'risk_analysis': 'Insufficient data for volatility analysis',
                    'confidence': 'low'
                }
            
            # Get optimal leverage recommendation
            leverage_analysis = await self.leverage_manager.get_optimal_leverage_for_trade(
                symbol, trade_direction, trade_size_usdt, ohlcv_data
            )
            
            self.logger.info(f"📊 {symbol}: Optimal leverage {leverage_analysis['recommended_leverage']}x "
                           f"(Volatility: {leverage_analysis.get('volatility_score', 'N/A'):.2f}, "
                           f"Risk: {leverage_analysis.get('risk_level', 'unknown')})")
            
            return leverage_analysis
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal leverage for {symbol}: {e}")
            return {
                'recommended_leverage': self.config.DEFAULT_LEVERAGE,
                'max_leverage': self.config.MAX_LEVERAGE,
                'risk_analysis': f'Error in analysis: {e}',
                'confidence': 'low'
            }
    
    async def monitor_portfolio_risk(self) -> Dict[str, Any]:
        """Monitor overall portfolio leverage and risk"""
        try:
            if not self.leverage_manager:
                return {'error': 'Dynamic leverage management not available'}
            
            # Get current positions
            positions = await self.get_futures_positions()
            
            # Monitor portfolio leverage
            portfolio_analysis = await self.leverage_manager.monitor_portfolio_leverage(positions)
            
            # Log important portfolio metrics
            if portfolio_analysis.get('portfolio_leverage', 0) > self.config.MAX_PORTFOLIO_LEVERAGE:
                self.logger.warning(f"⚠️ Portfolio leverage ({portfolio_analysis['portfolio_leverage']:.1f}x) "
                                  f"exceeds maximum ({self.config.MAX_PORTFOLIO_LEVERAGE}x)")
            
            return portfolio_analysis
            
        except Exception as e:
            self.logger.error(f"Error monitoring portfolio risk: {e}")
            return {'error': str(e)}
    
    # =============================================================================
    # ENHANCED TRADING METHODS WITH LEVERAGE SUPPORT
    # =============================================================================
    
    async def execute_trade(self, signal: Dict[str, Any], user_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a trade based on signal and user settings with dynamic leverage management"""
        try:
            symbol = signal['symbol']
            action = signal['action'].upper()
            
            # Get current price for calculations
            current_price = await self.get_current_price(symbol)
            if not current_price:
                return {
                    'success': False,
                    'error': f'Could not get current price for {symbol}'
                }
            
            # Calculate initial position size
            position_size = await self._calculate_position_size(signal, user_settings)
            
            if position_size <= 0:
                return {
                    'success': False,
                    'error': 'Invalid position size calculated'
                }
            
            # Calculate trade size in USDT for leverage optimization
            trade_size_usdt = position_size * current_price
            
            # Dynamic leverage adjustment if enabled
            leverage_info = None
            if self.config.ENABLE_FUTURES_TRADING and self.leverage_manager:
                try:
                    # Get optimal leverage for this trade
                    leverage_info = await self.calculate_optimal_leverage_for_trade(
                        symbol, action, trade_size_usdt
                    )
                    
                    optimal_leverage = leverage_info.get('recommended_leverage', self.config.DEFAULT_LEVERAGE)
                    
                    # Apply leverage adjustment if needed
                    current_leverage = await self.get_current_leverage(symbol)
                    if current_leverage != optimal_leverage:
                        self.logger.info(f"🎯 {symbol}: Adjusting leverage {current_leverage}x → {optimal_leverage}x for trade")
                        leverage_set = await self.set_leverage(symbol, optimal_leverage)
                        if not leverage_set:
                            self.logger.warning(f"⚠️ Failed to set optimal leverage for {symbol}, using current leverage")
                    
                    # Adjust position size based on leverage for futures
                    if self.config.ENABLE_FUTURES_TRADING:
                        # For futures, position size calculation considers leverage
                        leverage_multiplier = optimal_leverage / self.config.DEFAULT_LEVERAGE
                        position_size = position_size * leverage_multiplier
                        
                        self.logger.info(f"📊 {symbol}: Position adjusted for {optimal_leverage}x leverage "
                                       f"(Size: {position_size:.6f}, Value: ${trade_size_usdt:.2f})")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ Error in dynamic leverage adjustment for {symbol}: {e}")
            
            # Determine order type and price
            order_type = 'market'  # Default to market orders
            price = None
            
            if 'price' in signal and user_settings.get('use_limit_orders', False):
                order_type = 'limit'
                price = signal['price']
            
            # Execute the trade
            order = None
            if action in ['BUY', 'LONG']:
                order = await self._execute_buy_order(symbol, position_size, order_type, price)
            elif action in ['SELL', 'SHORT']:
                order = await self._execute_sell_order(symbol, position_size, order_type, price)
            else:
                return {
                    'success': False,
                    'error': f'Unsupported action: {action}'
                }
            
            if order:
                # Set stop loss and take profit if specified
                await self._set_stop_loss_take_profit(order, signal, user_settings)
                
                # Log leverage information if available
                leverage_used = await self.get_current_leverage(symbol) if self.config.ENABLE_FUTURES_TRADING else 1
                
                result = {
                    'success': True,
                    'order_id': order['id'],
                    'symbol': symbol,
                    'side': action,
                    'amount': order['amount'],
                    'price': order.get('price', order.get('average', 0)),
                    'fee': order.get('fee', {}),
                    'timestamp': order['timestamp'],
                    'leverage_used': leverage_used,
                    'trade_value_usdt': trade_size_usdt
                }
                
                # Add leverage analysis to result if available
                if leverage_info:
                    result['leverage_analysis'] = {
                        'volatility_score': leverage_info.get('volatility_score', 'N/A'),
                        'risk_level': leverage_info.get('risk_level', 'unknown'),
                        'confidence': leverage_info.get('confidence', 'low'),
                        'risk_factors': leverage_info.get('risk_factors', [])
                    }
                
                self.logger.info(f"✅ {symbol}: Trade executed - {action} {order['amount']:.6f} @ {result['price']:.4f} "
                               f"(Leverage: {leverage_used}x, Value: ${trade_size_usdt:.2f})")
                
                return result
            else:
                return {
                    'success': False,
                    'error': 'Failed to execute order'
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error executing trade for {symbol}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _calculate_position_size(self, signal: Dict[str, Any], user_settings: Dict[str, Any]) -> float:
        """Calculate position size based on risk management"""
        try:
            # Get account balance
            balance = await self.get_account_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            
            # Get risk percentage from user settings
            risk_percentage = user_settings.get('risk_percentage', self.config.DEFAULT_RISK_PERCENTAGE)
            
            # Calculate risk amount
            risk_amount = usdt_balance * (risk_percentage / 100)
            
            # Get current price
            symbol = signal['symbol']
            current_price = await self.get_current_price(symbol)
            
            # If specific quantity is provided in signal, use it (with limits)
            if 'quantity' in signal:
                quantity = float(signal['quantity'])
                max_quantity = risk_amount / current_price
                return min(quantity, max_quantity)
            
            # Calculate position size based on stop loss
            if 'stop_loss' in signal:
                stop_loss = float(signal['stop_loss'])
                entry_price = signal.get('price', current_price)
                
                # Calculate risk per unit
                if signal['action'].upper() in ['BUY', 'LONG']:
                    risk_per_unit = abs(entry_price - stop_loss)
                else:
                    risk_per_unit = abs(stop_loss - entry_price)
                
                if risk_per_unit > 0:
                    quantity = risk_amount / risk_per_unit
                    # Convert to base currency quantity
                    position_size = min(quantity, risk_amount / current_price)
                else:
                    position_size = risk_amount / current_price
            else:
                # No stop loss specified, use full risk amount
                position_size = risk_amount / current_price
            
            # Apply position size limits
            max_position = user_settings.get('max_position_size', self.config.MAX_POSITION_SIZE)
            min_position = user_settings.get('min_position_size', self.config.MIN_POSITION_SIZE)
            
            position_value = position_size * current_price
            
            if position_value > max_position:
                position_size = max_position / current_price
            elif position_value < min_position:
                position_size = min_position / current_price
            
            # Round to appropriate precision
            market = self.exchange.markets.get(symbol, {})
            precision = market.get('precision', {}).get('amount', 8)
            
            return float(Decimal(str(position_size)).quantize(
                Decimal('0.' + '0' * (precision - 1) + '1'),
                rounding=ROUND_DOWN
            ))
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0.0
    
    async def _execute_buy_order(self, symbol: str, amount: float, order_type: str, price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Execute a buy order"""
        try:
            if order_type == 'market':
                order = await self.exchange.create_market_buy_order(symbol, amount)
            else:
                order = await self.exchange.create_limit_buy_order(symbol, amount, price)
            
            self.logger.info(f"Buy order executed: {order['id']} for {amount} {symbol}")
            return order
            
        except Exception as e:
            self.logger.error(f"Error executing buy order: {e}")
            return None
    
    async def _execute_sell_order(self, symbol: str, amount: float, order_type: str, price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Execute a sell order"""
        try:
            if order_type == 'market':
                order = await self.exchange.create_market_sell_order(symbol, amount)
            else:
                order = await self.exchange.create_limit_sell_order(symbol, amount, price)
            
            self.logger.info(f"Sell order executed: {order['id']} for {amount} {symbol}")
            return order
            
        except Exception as e:
            self.logger.error(f"Error executing sell order: {e}")
            return None
    
    async def _set_stop_loss_take_profit(self, order: Dict[str, Any], signal: Dict[str, Any], user_settings: Dict[str, Any]):
        """Set stop loss and take profit orders"""
        try:
            symbol = order['symbol']
            amount = order['amount']
            side = 'sell' if signal['action'].upper() in ['BUY', 'LONG'] else 'buy'
            
            # Set stop loss
            if 'stop_loss' in signal:
                stop_loss_price = float(signal['stop_loss'])
                try:
                    stop_order = await self.exchange.create_order(
                        symbol=symbol,
                        type='stop_market',
                        side=side,
                        amount=amount,
                        params={'stopPrice': stop_loss_price}
                    )
                    self.logger.info(f"Stop loss set at {stop_loss_price} for order {order['id']}")
                except Exception as e:
                    self.logger.warning(f"Failed to set stop loss: {e}")
            
            # Set take profit
            if 'take_profit' in signal:
                take_profit_price = float(signal['take_profit'])
                try:
                    tp_order = await self.exchange.create_limit_order(
                        symbol=symbol,
                        side=side,
                        amount=amount,
                        price=take_profit_price
                    )
                    self.logger.info(f"Take profit set at {take_profit_price} for order {order['id']}")
                except Exception as e:
                    self.logger.warning(f"Failed to set take profit: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error setting stop loss/take profit: {e}")
    
    async def get_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Get order status"""
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            return order
            
        except Exception as e:
            self.logger.error(f"Error getting order status: {e}")
            return {}
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order"""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            self.logger.info(f"Order {order_id} cancelled successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    async def get_trading_fees(self, symbol: str) -> Dict[str, float]:
        """Get trading fees for symbol"""
        try:
            fees = await self.exchange.fetch_trading_fee(symbol)
            return {
                'maker': fees.get('maker', 0.001),
                'taker': fees.get('taker', 0.001)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting trading fees: {e}")
            return {'maker': 0.001, 'taker': 0.001}
    
    async def get_market_summary(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get market summary for multiple symbols"""
        try:
            summaries = {}
            
            for symbol in symbols:
                try:
                    ticker = await self.exchange.fetch_ticker(symbol)
                    summaries[symbol] = {
                        'price': ticker['last'],
                        'change_24h': ticker['percentage'],
                        'volume': ticker['baseVolume'],
                        'high_24h': ticker['high'],
                        'low_24h': ticker['low']
                    }
                except Exception:
                    continue
            
            return summaries
            
        except Exception as e:
            self.logger.error(f"Error getting market summary: {e}")
            return {}
    
    # =============================================================================
    # REAL-TIME WEBSOCKET MARKET DATA STREAMING
    # =============================================================================
    
    async def start_price_stream(self, symbols: List[str], callback: Optional[Callable] = None):
        """Start real-time price streaming for multiple symbols"""
        try:
            self.ws_running = True
            
            # Convert symbols to lowercase format for WebSocket
            ws_symbols = []
            for symbol in symbols:
                if symbol.endswith('USDT'):
                    ws_symbol = symbol.lower() + '@ticker'
                    ws_symbols.append(ws_symbol)
                    
                    # Initialize price tracking
                    self.current_prices[symbol] = 0.0
                    if callback:
                        if symbol not in self.price_callbacks:
                            self.price_callbacks[symbol] = []
                        self.price_callbacks[symbol].append(callback)
            
            # Create combined stream URL
            stream_names = '/'.join(ws_symbols)
            ws_url = f"{self.ws_base_url}{stream_names}"
            
            self.logger.info(f"🌐 Starting WebSocket price stream for {len(symbols)} symbols")
            
            # Start WebSocket connection in background task
            asyncio.create_task(self._websocket_handler(ws_url))
            
        except Exception as e:
            self.logger.error(f"Error starting price stream: {e}")
    
    async def _websocket_handler(self, ws_url: str):
        """Handle WebSocket connection and message processing"""
        try:
            while self.ws_running:
                try:
                    async with websockets.connect(ws_url) as websocket:
                        self.logger.info("✅ WebSocket connection established")
                        
                        async for message in websocket:
                            if not self.ws_running:
                                break
                                
                            try:
                                data = json.loads(message)
                                await self._process_price_update(data)
                            except json.JSONDecodeError:
                                continue
                                
                except websockets.exceptions.ConnectionClosed:
                    self.logger.warning("🔄 WebSocket connection closed, reconnecting...")
                    await asyncio.sleep(5)
                except Exception as e:
                    self.logger.error(f"WebSocket error: {e}")
                    await asyncio.sleep(10)
                    
        except Exception as e:
            self.logger.error(f"Critical WebSocket error: {e}")
    
    async def _process_price_update(self, data: Dict[str, Any]):
        """Process incoming price update from WebSocket"""
        try:
            if 's' in data and 'c' in data:  # symbol and close price
                symbol = data['s']
                price = float(data['c'])
                
                # Update current price
                self.current_prices[symbol] = price
                
                # Call registered callbacks
                if symbol in self.price_callbacks:
                    for callback in self.price_callbacks[symbol]:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(symbol, price)
                            else:
                                callback(symbol, price)
                        except Exception as e:
                            self.logger.error(f"Error in price callback for {symbol}: {e}")
                
                # Update position monitoring
                if symbol in self.active_positions:
                    await self._monitor_position_tp_sl(symbol, price)
                    
        except Exception as e:
            self.logger.error(f"Error processing price update: {e}")
    
    async def stop_price_stream(self):
        """Stop WebSocket price streaming"""
        self.ws_running = False
        self.logger.info("🛑 WebSocket price streaming stopped")
    
    def get_current_price_cached(self, symbol: str) -> float:
        """Get current price from WebSocket cache"""
        return self.current_prices.get(symbol, 0.0)
    
    # =============================================================================
    # POSITION TRACKING AND TP/SL LIFECYCLE MANAGEMENT
    # =============================================================================
    
    async def execute_real_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Execute real trade with integrated TP/SL management"""
        try:
            symbol = signal['symbol']
            direction = signal['direction'].upper()
            entry_price = signal['entry_price']
            
            # Calculate position size based on risk management
            position_size = await self._calculate_position_size_for_signal(signal)
            
            if position_size <= 0:
                return {'success': False, 'error': 'Invalid position size'}
            
            # Execute market order
            order_result = None
            if direction == 'LONG':
                order_result = await self._execute_buy_order(symbol, position_size, 'market')
            elif direction == 'SHORT':
                order_result = await self._execute_sell_order(symbol, position_size, 'market')
            
            if not order_result:
                return {'success': False, 'error': 'Failed to execute order'}
            
            # Initialize TP/SL management if enabled
            if self.tp_sl_enabled:
                await self._setup_tp_sl_management(symbol, direction, entry_price, position_size, signal)
            
            # Track position
            position_data = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'position_size': position_size,
                'order_id': order_result['id'],
                'timestamp': datetime.now(),
                'tp_levels': [signal.get('tp1'), signal.get('tp2'), signal.get('tp3')],
                'stop_loss': signal.get('stop_loss'),
                'status': 'active'
            }
            
            self.active_positions[symbol] = position_data
            
            self.logger.info(f"✅ Real trade executed: {direction} {position_size} {symbol} @ {entry_price}")
            
            return {
                'success': True,
                'order_id': order_result['id'],
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'position_size': position_size,
                'tp_sl_enabled': self.tp_sl_enabled
            }
            
        except Exception as e:
            self.logger.error(f"Error executing real trade for {symbol}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _setup_tp_sl_management(self, symbol: str, direction: str, entry_price: float, 
                                     position_size: float, signal: Dict[str, Any]):
        """Setup 3-level TP/SL management system"""
        try:
            from dynamic_stop_loss_system import ThreeSLOneTpManager
            
            # Initialize TP/SL manager for this position
            tp_sl_manager = ThreeSLOneTpManager(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                position_size=position_size,
                config=self.tp_sl_config
            )
            
            self.tp_sl_managers[symbol] = tp_sl_manager
            
            self.logger.info(f"🎯 TP/SL management setup for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error setting up TP/SL management for {symbol}: {e}")
    
    async def _monitor_position_tp_sl(self, symbol: str, current_price: float):
        """Monitor position for TP/SL hits and execute lifecycle management"""
        try:
            if symbol not in self.tp_sl_managers:
                return
            
            tp_sl_manager = self.tp_sl_managers[symbol]
            
            # Update TP/SL manager with current price
            actions = await asyncio.to_thread(tp_sl_manager.update_price, current_price)
            
            # Execute any required actions
            for action in actions:
                await self._execute_tp_sl_action(symbol, action)
                
        except Exception as e:
            self.logger.error(f"Error monitoring TP/SL for {symbol}: {e}")
    
    async def _execute_tp_sl_action(self, symbol: str, action: Dict[str, Any]):
        """Execute TP/SL action (close position, move SL, etc.)"""
        try:
            action_type = action.get('type')
            
            if action_type == 'close_position':
                # Close position completely
                await self._close_position(symbol, action.get('percentage', 100))
                
            elif action_type == 'partial_close':
                # Close partial position at TP level
                await self._close_position(symbol, action.get('percentage', 33))
                
            elif action_type == 'move_stop_loss':
                # Move stop loss to new level
                new_sl_price = action.get('new_stop_loss')
                await self._update_stop_loss(symbol, new_sl_price)
                
            elif action_type == 'stop_loss_hit':
                # Stop loss was hit - close entire position
                await self._close_position(symbol, 100)
                
            self.logger.info(f"🎯 TP/SL action executed for {symbol}: {action_type}")
            
        except Exception as e:
            self.logger.error(f"Error executing TP/SL action for {symbol}: {e}")
    
    async def _close_position(self, symbol: str, percentage: float):
        """Close position (full or partial)"""
        try:
            if symbol not in self.active_positions:
                return
            
            position = self.active_positions[symbol]
            direction = position['direction']
            position_size = position['position_size']
            
            # Calculate amount to close
            close_amount = position_size * (percentage / 100)
            
            # Execute closing order
            if direction == 'LONG':
                await self._execute_sell_order(symbol, close_amount, 'market')
            else:  # SHORT
                await self._execute_buy_order(symbol, close_amount, 'market')
            
            # Update position tracking
            if percentage >= 100:
                # Position fully closed
                position['status'] = 'closed'
                if symbol in self.tp_sl_managers:
                    del self.tp_sl_managers[symbol]
            else:
                # Partial close - update remaining size
                position['position_size'] -= close_amount
            
            self.logger.info(f"✅ Closed {percentage}% of {symbol} position")
            
        except Exception as e:
            self.logger.error(f"Error closing position for {symbol}: {e}")
    
    async def _update_stop_loss(self, symbol: str, new_sl_price: float):
        """Update stop loss order to new price"""
        try:
            # Cancel existing stop loss if any
            if symbol in self.stop_loss_orders:
                old_order_id = self.stop_loss_orders[symbol].get('order_id')
                if old_order_id:
                    await self.cancel_order(old_order_id, symbol)
            
            # Create new stop loss order
            position = self.active_positions[symbol]
            direction = position['direction']
            position_size = position['position_size']
            
            side = 'sell' if direction == 'LONG' else 'buy'
            
            stop_order = await self.exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=side,
                amount=position_size,
                params={'stopPrice': new_sl_price}
            )
            
            # Update tracking
            self.stop_loss_orders[symbol] = {
                'order_id': stop_order['id'],
                'price': new_sl_price,
                'timestamp': datetime.now()
            }
            
            self.logger.info(f"🛡️ Stop loss updated for {symbol}: {new_sl_price}")
            
        except Exception as e:
            self.logger.error(f"Error updating stop loss for {symbol}: {e}")
    
    async def _calculate_position_size_for_signal(self, signal: Dict[str, Any]) -> float:
        """Calculate position size for signal based on risk management"""
        try:
            # Use existing position calculation logic
            user_settings = {
                'risk_percentage': getattr(self.config, 'DEFAULT_RISK_PERCENTAGE', 2.0),
                'max_position_size': getattr(self.config, 'MAX_POSITION_SIZE', 1000),
                'min_position_size': getattr(self.config, 'MIN_POSITION_SIZE', 10)
            }
            
            return await self._calculate_position_size(signal, user_settings)
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0.0
    
    # Convenience method to make get_ohlcv_data available
    async def get_ohlcv_data(self, symbol: str, timeframe: str, limit: int = 100) -> List[List]:
        """Get OHLCV data - convenience wrapper for get_market_data"""
        return await self.get_market_data(symbol, timeframe, limit)
    
    async def test_connection(self) -> bool:
        """Test connection - convenience wrapper for ping"""
        return await self.ping()
