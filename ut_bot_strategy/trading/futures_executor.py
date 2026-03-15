"""
Binance Futures Trading Executor

Handles all trading operations on Binance Futures:
- Position management
- Order execution (Market, Limit, Stop)
- Leverage setting
- Margin type configuration
"""

import logging
import asyncio
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

try:
    import ccxt.async_support as ccxt_async
except ImportError:
    ccxt_async = None


@dataclass
class OrderResult:
    """Result of order execution"""
    success: bool
    order_id: Optional[str] = None
    symbol: str = ""
    side: str = ""
    order_type: str = ""
    quantity: float = 0.0
    price: float = 0.0
    status: str = ""
    message: str = ""
    timestamp: Optional[datetime] = None


@dataclass
class PositionInfo:
    """Current position information"""
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin_type: str
    liquidation_price: float


class FuturesExecutor:
    """
    Binance Futures trading executor with comprehensive order management
    
    Features:
    - Automatic leverage configuration
    - Isolated/Cross margin support
    - Market and limit order execution
    - Stop loss and take profit orders
    - Position monitoring
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str = "ETHUSDT",
        testnet: bool = False
    ):
        """
        Initialize the futures executor
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            symbol: Trading pair symbol
            testnet: Use testnet (for testing)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol
        self.testnet = testnet
        self._client = None
        self._ccxt_client = None
        self._initialized = False
        
        self.quantity_precision = 3
        self.price_precision = 2
        self.min_quantity = 0.001
        self.min_notional = 5.0
        
        logger.info(f"FuturesExecutor initialized for {symbol}")
    
    async def initialize(self) -> bool:
        """Initialize the trading clients"""
        try:
            if not ccxt_async:
                logger.error("CCXT async module not available")
                return False
            
            if not self.api_key or not self.api_secret:
                logger.error("Binance API credentials not configured")
                return False
            
            self._ccxt_client = ccxt_async.binance({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'sandbox': self.testnet,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'enableRateLimit': True,
                    'recvWindow': 10000
                },
                'timeout': 30000,
                'enableRateLimit': True
            })
            
            logger.info("Testing Binance API credentials...")
            try:
                balance = await self._ccxt_client.fetch_balance()
                logger.info("Binance API credentials validated successfully")
            except Exception as auth_error:
                logger.error(f"Binance authentication failed: {auth_error}")
                self._ccxt_client = None
                return False
            
            await self._load_market_info()
            self._initialized = True
            logger.info("Futures executor initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize futures executor: {e}")
            self._ccxt_client = None
            return False
    
    async def _load_market_info(self) -> None:
        """Load market precision and limits"""
        try:
            if not self._ccxt_client:
                return
            markets: Dict[str, Any] = await self._ccxt_client.load_markets()
            if self.symbol in markets:
                market = markets[self.symbol]
                self.quantity_precision = market.get('precision', {}).get('amount', 3)
                self.price_precision = market.get('precision', {}).get('price', 2)
                limits = market.get('limits', {})
                self.min_quantity = limits.get('amount', {}).get('min', 0.001)
                self.min_notional = limits.get('cost', {}).get('min', 5.0)
                logger.info(f"Loaded market info: qty_prec={self.quantity_precision}, price_prec={self.price_precision}")
        except Exception as e:
            logger.warning(f"Could not load market info, using defaults: {e}")
    
    def _round_quantity(self, quantity: float) -> float:
        """Round quantity to correct precision"""
        factor = 10 ** self.quantity_precision
        return float(int(quantity * factor) / factor)
    
    def _round_price(self, price: float) -> float:
        """Round price to correct precision"""
        factor = 10 ** self.price_precision
        return float(round(price * factor) / factor)
    
    async def get_account_balance(self) -> Dict[str, float]:
        """Get futures account balance"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return {'total': 0.0, 'free': 0.0, 'used': 0.0}
                
            balance: Dict[str, Any] = await self._ccxt_client.fetch_balance()
            usdt_balance: Dict[str, Any] = balance.get('USDT', {})
            
            return {
                'total': float(usdt_balance.get('total', 0)),
                'free': float(usdt_balance.get('free', 0)),
                'used': float(usdt_balance.get('used', 0))
            }
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return {'total': 0.0, 'free': 0.0, 'used': 0.0}
    
    async def set_leverage(self, leverage: int) -> bool:
        """Set leverage for the symbol"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return False
                
            await self._ccxt_client.set_leverage(leverage, self.symbol)
            logger.info(f"Leverage set to {leverage}x for {self.symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False
    
    async def set_margin_type(self, isolated: bool = True) -> bool:
        """Set margin type (isolated or cross)"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return False
                
            margin_type = 'ISOLATED' if isolated else 'CROSSED'
            await self._ccxt_client.set_margin_mode(margin_type, self.symbol)
            logger.info(f"Margin type set to {margin_type} for {self.symbol}")
            return True
        except Exception as e:
            if 'No need to change' in str(e):
                return True
            logger.error(f"Failed to set margin type: {e}")
            return False
    
    async def get_position(self) -> Optional[PositionInfo]:
        """Get current position for the symbol"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return None
                
            positions: List[Dict[str, Any]] = await self._ccxt_client.fetch_positions([self.symbol])
            for pos in positions:
                if pos['symbol'] == self.symbol and float(pos.get('contracts', 0)) != 0:
                    return PositionInfo(
                        symbol=pos['symbol'],
                        side='LONG' if pos['side'] == 'long' else 'SHORT',
                        size=float(pos.get('contracts', 0)),
                        entry_price=float(pos.get('entryPrice', 0)),
                        mark_price=float(pos.get('markPrice', 0)),
                        unrealized_pnl=float(pos.get('unrealizedPnl', 0)),
                        leverage=int(pos.get('leverage', 1)),
                        margin_type=str(pos.get('marginType', 'isolated')),
                        liquidation_price=float(pos.get('liquidationPrice', 0))
                    )
            return None
        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return None
    
    async def place_market_order(
        self,
        side: str,
        quantity: float,
        reduce_only: bool = False
    ) -> OrderResult:
        """
        Place a market order
        
        Args:
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            reduce_only: Only reduce position
            
        Returns:
            OrderResult with execution details
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return OrderResult(success=False, symbol=self.symbol, side=side, message="Client not initialized")
                
            quantity = self._round_quantity(quantity)
            
            if quantity < self.min_quantity:
                return OrderResult(
                    success=False,
                    message=f"Quantity {quantity} below minimum {self.min_quantity}"
                )
            
            params: Dict[str, Any] = {'reduceOnly': reduce_only} if reduce_only else {}
            
            order: Dict[str, Any] = await self._ccxt_client.create_market_order(
                symbol=self.symbol,
                side=side.lower(),
                amount=quantity,
                params=params
            )
            
            logger.info(f"Market order placed: {side} {quantity} {self.symbol}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('id', '')),
                symbol=self.symbol,
                side=side,
                order_type='MARKET',
                quantity=quantity,
                price=float(order.get('average', 0)),
                status=str(order.get('status', 'FILLED')),
                message="Order executed successfully",
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return OrderResult(
                success=False,
                symbol=self.symbol,
                side=side,
                message=str(e)
            )
    
    async def place_stop_loss(
        self,
        side: str,
        quantity: float,
        stop_price: float
    ) -> OrderResult:
        """
        Place a stop loss order
        
        Args:
            side: 'BUY' for short position, 'SELL' for long position
            quantity: Order quantity
            stop_price: Stop trigger price
            
        Returns:
            OrderResult with order details
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return OrderResult(success=False, symbol=self.symbol, side=side, message="Client not initialized")
                
            quantity = self._round_quantity(quantity)
            stop_price = self._round_price(stop_price)
            
            order: Dict[str, Any] = await self._ccxt_client.create_order(
                symbol=self.symbol,
                type='STOP_MARKET',
                side=side.lower(),
                amount=quantity,
                params={
                    'stopPrice': stop_price,
                    'reduceOnly': True
                }
            )
            
            logger.info(f"Stop loss placed: {side} {quantity} @ {stop_price}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('id', '')),
                symbol=self.symbol,
                side=side,
                order_type='STOP_MARKET',
                quantity=quantity,
                price=stop_price,
                status=str(order.get('status', 'NEW')),
                message="Stop loss placed",
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Stop loss order failed: {e}")
            return OrderResult(
                success=False,
                symbol=self.symbol,
                side=side,
                message=str(e)
            )
    
    async def place_take_profit(
        self,
        side: str,
        quantity: float,
        take_profit_price: float
    ) -> OrderResult:
        """
        Place a take profit order
        
        Args:
            side: 'BUY' for short position, 'SELL' for long position
            quantity: Order quantity
            take_profit_price: Take profit trigger price
            
        Returns:
            OrderResult with order details
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return OrderResult(success=False, symbol=self.symbol, side=side, message="Client not initialized")
                
            quantity = self._round_quantity(quantity)
            take_profit_price = self._round_price(take_profit_price)
            
            order: Dict[str, Any] = await self._ccxt_client.create_order(
                symbol=self.symbol,
                type='TAKE_PROFIT_MARKET',
                side=side.lower(),
                amount=quantity,
                params={
                    'stopPrice': take_profit_price,
                    'reduceOnly': True
                }
            )
            
            logger.info(f"Take profit placed: {side} {quantity} @ {take_profit_price}")
            
            return OrderResult(
                success=True,
                order_id=str(order.get('id', '')),
                symbol=self.symbol,
                side=side,
                order_type='TAKE_PROFIT_MARKET',
                quantity=quantity,
                price=take_profit_price,
                status=str(order.get('status', 'NEW')),
                message="Take profit placed",
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Take profit order failed: {e}")
            return OrderResult(
                success=False,
                symbol=self.symbol,
                side=side,
                message=str(e)
            )
    
    async def execute_trade(
        self,
        signal: Dict,
        leverage: int,
        quantity: float,
        use_isolated: bool = True
    ) -> Dict:
        """
        Execute a complete trade with SL and TP
        
        Args:
            signal: Trading signal with entry, SL, TP
            leverage: Leverage to use
            quantity: Position size
            use_isolated: Use isolated margin
            
        Returns:
            Dictionary with all order results
        """
        direction = signal.get('direction', 'LONG')
        entry_price = signal.get('entry_price', 0)
        stop_loss = signal.get('stop_loss', 0)
        take_profit = signal.get('take_profit', 0)
        
        await self.set_margin_type(isolated=use_isolated)
        await self.set_leverage(leverage)
        
        entry_side = 'BUY' if direction == 'LONG' else 'SELL'
        exit_side = 'SELL' if direction == 'LONG' else 'BUY'
        
        entry_result = await self.place_market_order(entry_side, quantity)
        
        if not entry_result.success:
            return {
                'success': False,
                'entry': entry_result,
                'message': f"Entry order failed: {entry_result.message}"
            }
        
        sl_result = await self.place_stop_loss(exit_side, quantity, stop_loss)
        tp_result = await self.place_take_profit(exit_side, quantity, take_profit)
        
        return {
            'success': True,
            'entry': entry_result,
            'stop_loss': sl_result,
            'take_profit': tp_result,
            'leverage': leverage,
            'direction': direction,
            'message': "Trade executed successfully"
        }
    
    async def close_position(self) -> OrderResult:
        """Close current position"""
        position = await self.get_position()
        
        if not position:
            return OrderResult(
                success=False,
                message="No open position to close"
            )
        
        close_side = 'SELL' if position.side == 'LONG' else 'BUY'
        return await self.place_market_order(close_side, position.size, reduce_only=True)
    
    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders for the symbol"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if not self._ccxt_client:
                return False
                
            await self._ccxt_client.cancel_all_orders(self.symbol)
            logger.info(f"All orders cancelled for {self.symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
            return False
    
    async def close(self) -> None:
        """Clean up resources"""
        try:
            if self._ccxt_client:
                try:
                    await self._ccxt_client.close()
                    logger.info("CCXT client closed")
                except Exception as e:
                    logger.warning(f"Error closing CCXT client: {e}")
        finally:
            self._ccxt_client = None
            logger.info("Futures executor closed")
