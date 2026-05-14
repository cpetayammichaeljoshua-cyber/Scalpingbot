"""
Utility functions for the trading bot
Provides helper functions for formatting, validation, and calculations
"""

import re
import json
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from decimal import Decimal, ROUND_DOWN
import logging

def format_currency(amount: float, currency: str = "USD", decimals: int = 2) -> str:
    """
    Format currency amount with appropriate symbol and decimals
    
    Args:
        amount: Currency amount
        currency: Currency code (USD, BTC, ETH, etc.)
        decimals: Number of decimal places
        
    Returns:
        Formatted currency string
    """
    try:
        # Currency symbols mapping
        symbols = {
            'USD': '$',
            'USDT': '$',
            'BUSD': '$',
            'EUR': '€',
            'GBP': '£',
            'BTC': '₿',
            'ETH': 'Ξ'
        }
        
        symbol = symbols.get(currency.upper(), currency.upper() + ' ')
        
        if currency.upper() in ['BTC', 'ETH']:
            # Crypto currencies - more decimals for small amounts
            if amount < 1:
                decimals = 6
            elif amount < 10:
                decimals = 4
        
        # Format with appropriate decimals
        formatted_amount = f"{amount:,.{decimals}f}"
        
        if currency.upper() in ['USD', 'USDT', 'BUSD', 'EUR', 'GBP']:
            return f"{symbol}{formatted_amount}"
        else:
            return f"{formatted_amount} {symbol.strip()}"
            
    except Exception:
        return f"{amount:.{decimals}f} {currency}"

def format_percentage(value: float, decimals: int = 2, show_sign: bool = True) -> str:
    """
    Format percentage value
    
    Args:
        value: Percentage value
        decimals: Number of decimal places
        show_sign: Whether to show + sign for positive values
        
    Returns:
        Formatted percentage string
    """
    try:
        sign = ""
        if show_sign and value > 0:
            sign = "+"
        elif value < 0:
            sign = "-"
            value = abs(value)
        
        return f"{sign}{value:.{decimals}f}%"
        
    except Exception:
        return f"{value:.{decimals}f}%"

def format_timestamp(timestamp: Union[int, float, str, datetime], format_type: str = "datetime") -> str:
    """
    Format timestamp to human readable string
    
    Args:
        timestamp: Unix timestamp, datetime object, or ISO string
        format_type: Format type ('datetime', 'date', 'time', 'relative')
        
    Returns:
        Formatted timestamp string
    """
    try:
        # Convert to datetime object
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return str(timestamp)
        
        if format_type == "datetime":
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif format_type == "date":
            return dt.strftime("%Y-%m-%d")
        elif format_type == "time":
            return dt.strftime("%H:%M:%S")
        elif format_type == "relative":
            return format_relative_time(dt)
        else:
            return dt.isoformat()
            
    except Exception:
        return str(timestamp)

def format_relative_time(dt: datetime) -> str:
    """
    Format datetime as relative time (e.g., '2 minutes ago')
    
    Args:
        dt: DateTime object
        
    Returns:
        Relative time string
    """
    try:
        now = datetime.utcnow()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"
            
    except Exception:
        return "Unknown"

def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change between two values
    
    Args:
        old_value: Original value
        new_value: New value
        
    Returns:
        Percentage change
    """
    try:
        if old_value == 0:
            return 0 if new_value == 0 else 100
        
        return ((new_value - old_value) / old_value) * 100
        
    except Exception:
        return 0

def calculate_profit_loss(entry_price: float, exit_price: float, quantity: float, side: str) -> Dict[str, float]:
    """
    Calculate profit/loss for a trade
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade quantity
        side: Trade side ('BUY' or 'SELL')
        
    Returns:
        Dictionary with PnL calculations
    """
    try:
        if side.upper() in ['BUY', 'LONG']:
            # Long position
            price_diff = exit_price - entry_price
        else:
            # Short position
            price_diff = entry_price - exit_price
        
        pnl = price_diff * quantity
        pnl_percentage = (price_diff / entry_price) * 100
        
        return {
            'pnl': pnl,
            'pnl_percentage': pnl_percentage,
            'entry_value': entry_price * quantity,
            'exit_value': exit_price * quantity,
            'price_difference': price_diff
        }
        
    except Exception:
        return {
            'pnl': 0,
            'pnl_percentage': 0,
            'entry_value': 0,
            'exit_value': 0,
            'price_difference': 0
        }

def validate_json_webhook(data: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    """
    Validate JSON webhook data
    
    Args:
        data: JSON data to validate
        required_fields: List of required field names
        
    Returns:
        Validation result
    """
    try:
        errors = []
        warnings = []
        
        # Check required fields
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
            elif data[field] is None or data[field] == "":
                warnings.append(f"Empty value for field: {field}")
        
        # Check data types for common fields
        type_checks = {
            'price': (int, float),
            'quantity': (int, float),
            'amount': (int, float),
            'stop_loss': (int, float),
            'take_profit': (int, float),
            'leverage': (int,),
            'timestamp': (int, float, str)
        }
        
        for field, expected_types in type_checks.items():
            if field in data and not isinstance(data[field], expected_types):
                warnings.append(f"Unexpected type for {field}: expected {expected_types}, got {type(data[field])}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
        
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Validation error: {str(e)}"],
            'warnings': []
        }

def generate_webhook_signature(payload: str, secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for webhook validation
    
    Args:
        payload: Webhook payload
        secret: Secret key
        
    Returns:
        Hexadecimal signature
    """
    try:
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
        
    except Exception:
        return ""

def validate_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """
    Validate webhook signature
    
    Args:
        payload: Webhook payload
        signature: Provided signature
        secret: Secret key
        
    Returns:
        True if signature is valid
    """
    try:
        expected_signature = generate_webhook_signature(payload, secret)
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception:
        return False

def sanitize_symbol(symbol: str) -> str:
    """
    Sanitize trading symbol
    
    Args:
        symbol: Trading symbol
        
    Returns:
        Sanitized symbol
    """
    try:
        # Remove any non-alphanumeric characters
        symbol = re.sub(r'[^A-Za-z0-9]', '', symbol.upper())
        
        # Ensure it ends with USDT if it's a known crypto
        known_cryptos = ['BTC', 'ETH', 'BNB', 'ADA', 'DOT', 'LINK', 'LTC', 'BCH', 'XLM', 'EOS', 'TRX', 'XRP', 'SOL', 'AVAX', 'MATIC']
        
        if symbol in known_cryptos:
            symbol += 'USDT'
        elif not symbol.endswith('USDT') and not symbol.endswith('BUSD'):
            # Check if it's already a valid pair
            for crypto in known_cryptos:
                if symbol.startswith(crypto) and symbol != crypto:
                    break
            else:
                # Add USDT if not a recognized pair
                if len(symbol) <= 5:  # Likely a single crypto symbol
                    symbol += 'USDT'
        
        return symbol
        
    except Exception:
        return symbol.upper()

def calculate_position_size(account_balance: float, risk_percentage: float, entry_price: float, stop_loss: float) -> Dict[str, float]:
    """
    Calculate optimal position size based on risk management
    
    Args:
        account_balance: Account balance in USD
        risk_percentage: Risk percentage (e.g., 2.0 for 2%)
        entry_price: Entry price
        stop_loss: Stop loss price
        
    Returns:
        Position size calculations
    """
    try:
        # Calculate risk amount
        risk_amount = account_balance * (risk_percentage / 100)
        
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit == 0:
            # No stop loss provided, use conservative approach
            position_size = risk_amount / entry_price
            position_value = position_size * entry_price
        else:
            # Calculate position size based on stop loss
            position_size = risk_amount / risk_per_unit
            position_value = position_size * entry_price
        
        return {
            'position_size': position_size,
            'position_value': position_value,
            'risk_amount': risk_amount,
            'risk_per_unit': risk_per_unit,
            'risk_percentage_actual': (risk_amount / account_balance) * 100
        }
        
    except Exception:
        return {
            'position_size': 0,
            'position_value': 0,
            'risk_amount': 0,
            'risk_per_unit': 0,
            'risk_percentage_actual': 0
        }

def round_to_precision(value: float, precision: int) -> float:
    """
    Round value to specified precision
    
    Args:
        value: Value to round
        precision: Number of decimal places
        
    Returns:
        Rounded value
    """
    try:
        return float(Decimal(str(value)).quantize(
            Decimal('0.' + '0' * (precision - 1) + '1'),
            rounding=ROUND_DOWN
        ))
    except Exception:
        return round(value, precision)

def extract_numbers_from_text(text: str) -> List[float]:
    """
    Extract all numbers from text
    
    Args:
        text: Input text
        
    Returns:
        List of numbers found
    """
    try:
        # Pattern to match numbers (including decimals)
        pattern = r'\d+\.?\d*'
        matches = re.findall(pattern, text)
        
        numbers = []
        for match in matches:
            try:
                numbers.append(float(match))
            except ValueError:
                continue
        
        return numbers
        
    except Exception:
        return []

def is_market_hours(timezone: str = 'UTC') -> bool:
    """
    Check if markets are currently open (simplified check)
    
    Args:
        timezone: Timezone to check
        
    Returns:
        True if markets are open
    """
    try:
        # Crypto markets are always open
        return True
        
    except Exception:
        return True

def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe ratio for a list of returns
    
    Args:
        returns: List of period returns
        risk_free_rate: Risk-free rate (annual)
        
    Returns:
        Sharpe ratio
    """
    try:
        if not returns or len(returns) < 2:
            return 0
        
        import numpy as np
        
        returns_array = np.array(returns)
        excess_returns = returns_array - (risk_free_rate / 252)  # Daily risk-free rate
        
        if np.std(excess_returns) == 0:
            return 0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)  # Annualized
        
        return float(sharpe)
        
    except Exception:
        return 0

def calculate_max_drawdown(equity_curve: List[float]) -> Dict[str, float]:
    """
    Calculate maximum drawdown from equity curve
    
    Args:
        equity_curve: List of equity values over time
        
    Returns:
        Drawdown statistics
    """
    try:
        if not equity_curve or len(equity_curve) < 2:
            return {'max_drawdown': 0, 'max_drawdown_percent': 0, 'current_drawdown': 0}
        
        import numpy as np
        
        equity_array = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (running_max - equity_array) / running_max
        
        max_drawdown = np.max(drawdown)
        max_drawdown_amount = np.max(running_max - equity_array)
        current_drawdown = drawdown[-1]
        
        return {
            'max_drawdown': float(max_drawdown_amount),
            'max_drawdown_percent': float(max_drawdown * 100),
            'current_drawdown': float(current_drawdown * 100)
        }
        
    except Exception:
        return {'max_drawdown': 0, 'max_drawdown_percent': 0, 'current_drawdown': 0}

def format_trade_summary(trade_data: Dict[str, Any]) -> str:
    """
    Format trade data into a readable summary
    
    Args:
        trade_data: Trade data dictionary
        
    Returns:
        Formatted trade summary
    """
    try:
        symbol = trade_data.get('symbol', 'UNKNOWN')
        side = trade_data.get('side', 'UNKNOWN')
        amount = trade_data.get('amount', 0)
        price = trade_data.get('price', 0)
        pnl = trade_data.get('pnl', 0)
        
        summary = f"💹 **Trade Summary**\n"
        summary += f"📊 Symbol: {symbol}\n"
        summary += f"🔄 Side: {side}\n"
        summary += f"📦 Amount: {amount}\n"
        summary += f"💰 Price: {format_currency(price)}\n"
        summary += f"📈 P&L: {format_currency(pnl)}\n"
        
        if pnl > 0:
            summary += "✅ Status: Profitable"
        elif pnl < 0:
            summary += "❌ Status: Loss"
        else:
            summary += "⚪ Status: Break-even"
        
        return summary
        
    except Exception:
        return "Error formatting trade summary"

def format_signal_summary(signal_data: Dict[str, Any]) -> str:
    """
    Format signal data into a readable summary
    
    Args:
        signal_data: Signal data dictionary
        
    Returns:
        Formatted signal summary
    """
    try:
        symbol = signal_data.get('symbol', 'UNKNOWN')
        action = signal_data.get('action', 'UNKNOWN')
        price = signal_data.get('price', 0)
        stop_loss = signal_data.get('stop_loss', 0)
        take_profit = signal_data.get('take_profit', 0)
        
        summary = f"🎯 **Trading Signal**\n"
        summary += f"📊 Symbol: {symbol}\n"
        summary += f"🔄 Action: {action}\n"
        
        if price:
            summary += f"💰 Entry: {format_currency(price)}\n"
        
        if stop_loss:
            summary += f"🛑 Stop Loss: {format_currency(stop_loss)}\n"
        
        if take_profit:
            summary += f"🎯 Take Profit: {format_currency(take_profit)}\n"
        
        # Calculate risk-reward ratio
        if price and stop_loss and take_profit:
            risk = abs(price - stop_loss)
            reward = abs(take_profit - price)
            if risk > 0:
                rr_ratio = reward / risk
                summary += f"⚖️ Risk/Reward: 1:{rr_ratio:.2f}\n"
        
        return summary
        
    except Exception:
        return "Error formatting signal summary"

def validate_trading_pair(symbol: str, supported_pairs: List[str]) -> bool:
    """
    Validate if trading pair is supported
    
    Args:
        symbol: Trading symbol
        supported_pairs: List of supported pairs
        
    Returns:
        True if pair is supported
    """
    try:
        return symbol.upper() in [pair.upper() for pair in supported_pairs]
        
    except Exception:
        return False

def get_market_session() -> str:
    """
    Get current market session based on UTC time
    
    Returns:
        Market session name
    """
    try:
        current_hour = datetime.utcnow().hour
        
        # Simplified market sessions (UTC)
        if 0 <= current_hour < 8:
            return "Asian"
        elif 8 <= current_hour < 16:
            return "European"
        else:
            return "American"
            
    except Exception:
        return "Unknown"

def rate_limit_check(last_request_time: float, min_interval: float) -> bool:
    """
    Check if enough time has passed since last request
    
    Args:
        last_request_time: Timestamp of last request
        min_interval: Minimum interval in seconds
        
    Returns:
        True if request is allowed
    """
    try:
        current_time = time.time()
        return (current_time - last_request_time) >= min_interval
        
    except Exception:
        return True

def escape_markdown(text: str) -> str:
    """
    Escape markdown special characters for Telegram
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    try:
        # Characters that need escaping in Telegram MarkdownV2
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        
        return text
        
    except Exception:
        return text

def create_progress_bar(current: int, total: int, length: int = 20) -> str:
    """
    Create a text-based progress bar
    
    Args:
        current: Current progress
        total: Total amount
        length: Length of progress bar
        
    Returns:
        Progress bar string
    """
    try:
        if total == 0:
            return "█" * length
        
        filled = int(length * current / total)
        empty = length - filled
        
        bar = "█" * filled + "░" * empty
        percentage = (current / total) * 100
        
        return f"{bar} {percentage:.1f}%"
        
    except Exception:
        return "Error creating progress bar"
