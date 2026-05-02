"""
Trading signal parser for various signal formats
Handles parsing and validation of trading signals from text
"""

import re
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal, InvalidOperation

class SignalParser:
    """Parser for cryptocurrency trading signals"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Define regex patterns for different signal formats
        self.patterns = {
            # BUY BTCUSDT at 45000
            'simple_buy_sell': re.compile(
                r'(BUY|SELL|LONG|SHORT)\s+([A-Z]+USDT?)\s+(?:at\s+)?(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            
            # BUY BTCUSDT 50% at 45000
            'with_percentage': re.compile(
                r'(BUY|SELL|LONG|SHORT)\s+([A-Z]+USDT?)\s+(\d+(?:\.\d+)?)%\s+(?:at\s+)?(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            
            # LONG BTC SL: 44000 TP: 48000
            'with_sl_tp': re.compile(
                r'(BUY|SELL|LONG|SHORT)\s+([A-Z]+USDT?)\s+.*?SL:?\s*(\d+(?:\.\d+)?)\s+.*?TP:?\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            
            # Entry: 45000, SL: 44000, TP: 48000
            'entry_format': re.compile(
                r'(?:ENTRY|Entry):?\s*(\d+(?:\.\d+)?)\s*,?\s*(?:SL|Stop Loss):?\s*(\d+(?:\.\d+)?)\s*,?\s*(?:TP|Take Profit):?\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            ),
            
            # Quantity format: quantity: 0.5 BTC
            'quantity_format': re.compile(
                r'(?:quantity|qty|amount):?\s*(\d+(?:\.\d+)?)\s*([A-Z]+)',
                re.IGNORECASE
            ),
            
            # Price levels: 45000-46000
            'price_range': re.compile(
                r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)',
                re.IGNORECASE
            )
        }
    
    def parse_signal(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse trading signal from text
        
        Args:
            text: Input text containing trading signal
            
        Returns:
            Dictionary with parsed signal data or None if no valid signal found
        """
        try:
            text = text.strip()
            
            # Try different parsing strategies
            signal = self._parse_simple_signal(text)
            if signal:
                return signal
            
            signal = self._parse_complex_signal(text)
            if signal:
                return signal
            
            signal = self._parse_structured_signal(text)
            if signal:
                return signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing signal: {e}")
            return None
    
    def _parse_simple_signal(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse simple BUY/SELL signals"""
        try:
            # Check for simple buy/sell pattern
            match = self.patterns['simple_buy_sell'].search(text)
            if match:
                action, symbol, price = match.groups()
                
                signal = {
                    'action': action.upper(),
                    'symbol': self._normalize_symbol(symbol),
                    'price': float(price),
                    'type': 'simple',
                    'source': 'text_parsing'
                }
                
                # Look for additional information in the text
                self._extract_additional_info(text, signal)
                
                return signal
            
            # Check for percentage-based signals
            match = self.patterns['with_percentage'].search(text)
            if match:
                action, symbol, percentage, price = match.groups()
                
                signal = {
                    'action': action.upper(),
                    'symbol': self._normalize_symbol(symbol),
                    'price': float(price),
                    'percentage': float(percentage),
                    'type': 'percentage',
                    'source': 'text_parsing'
                }
                
                self._extract_additional_info(text, signal)
                return signal
            
            return None
            
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"Error parsing simple signal: {e}")
            return None
    
    def _parse_complex_signal(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse complex signals with SL/TP"""
        try:
            # Check for signals with stop loss and take profit
            match = self.patterns['with_sl_tp'].search(text)
            if match:
                action, symbol, stop_loss, take_profit = match.groups()
                
                signal = {
                    'action': action.upper(),
                    'symbol': self._normalize_symbol(symbol),
                    'stop_loss': float(stop_loss),
                    'take_profit': float(take_profit),
                    'type': 'complex',
                    'source': 'text_parsing'
                }
                
                # Try to find entry price
                entry_price = self._extract_entry_price(text)
                if entry_price:
                    signal['price'] = entry_price
                
                self._extract_additional_info(text, signal)
                return signal
            
            return None
            
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"Error parsing complex signal: {e}")
            return None
    
    def _parse_structured_signal(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse structured signals with entry, SL, TP format"""
        try:
            # Look for entry format
            entry_match = self.patterns['entry_format'].search(text)
            if entry_match:
                entry_price, stop_loss, take_profit = entry_match.groups()
                
                # Try to determine action from context
                action = self._determine_action_from_context(text)
                if not action:
                    return None
                
                # Try to extract symbol
                symbol = self._extract_symbol_from_text(text)
                if not symbol:
                    return None
                
                signal = {
                    'action': action,
                    'symbol': symbol,
                    'price': float(entry_price),
                    'stop_loss': float(stop_loss),
                    'take_profit': float(take_profit),
                    'type': 'structured',
                    'source': 'text_parsing'
                }
                
                self._extract_additional_info(text, signal)
                return signal
            
            return None
            
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"Error parsing structured signal: {e}")
            return None
    
    def _extract_additional_info(self, text: str, signal: Dict[str, Any]):
        """Extract additional information from signal text"""
        try:
            # Extract quantity if specified
            qty_match = self.patterns['quantity_format'].search(text)
            if qty_match:
                quantity, unit = qty_match.groups()
                signal['quantity'] = float(quantity)
                signal['quantity_unit'] = unit.upper()
            
            # Extract leverage if mentioned
            leverage_match = re.search(r'(?:leverage|x):?\s*(\d+)', text, re.IGNORECASE)
            if leverage_match:
                signal['leverage'] = int(leverage_match.group(1))
            
            # Extract timeframe if mentioned
            timeframe_match = re.search(r'(\d+[mhd])', text, re.IGNORECASE)
            if timeframe_match:
                signal['timeframe'] = timeframe_match.group(1).lower()
            
            # Extract confidence level
            confidence_match = re.search(r'(?:confidence|probability):?\s*(\d+)%', text, re.IGNORECASE)
            if confidence_match:
                signal['confidence'] = int(confidence_match.group(1))
            
            # Extract risk level
            if any(word in text.lower() for word in ['high risk', 'risky', 'aggressive']):
                signal['risk_level'] = 'high'
            elif any(word in text.lower() for word in ['low risk', 'safe', 'conservative']):
                signal['risk_level'] = 'low'
            else:
                signal['risk_level'] = 'medium'
            
        except Exception as e:
            self.logger.warning(f"Error extracting additional info: {e}")
    
    def _extract_entry_price(self, text: str) -> Optional[float]:
        """Extract entry price from text"""
        try:
            # Look for entry price patterns
            entry_patterns = [
                r'(?:entry|enter|buy at|sell at):?\s*(\d+(?:\.\d+)?)',
                r'(?:price):?\s*(\d+(?:\.\d+)?)',
                r'@\s*(\d+(?:\.\d+)?)'
            ]
            
            for pattern in entry_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return float(match.group(1))
            
            return None
            
        except (ValueError, AttributeError):
            return None
    
    def _determine_action_from_context(self, text: str) -> Optional[str]:
        """Determine trading action from context"""
        text_lower = text.lower()
        
        buy_words = ['buy', 'long', 'bullish', 'up', 'call', 'bull']
        sell_words = ['sell', 'short', 'bearish', 'down', 'put', 'bear']
        
        buy_count = sum(1 for word in buy_words if word in text_lower)
        sell_count = sum(1 for word in sell_words if word in text_lower)
        
        if buy_count > sell_count:
            return 'BUY'
        elif sell_count > buy_count:
            return 'SELL'
        
        return None
    
    def _extract_symbol_from_text(self, text: str) -> Optional[str]:
        """Extract trading symbol from text"""
        # Common crypto symbols
        symbols = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'DOTUSDT',
            'LINKUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT', 'EOSUSDT',
            'TRXUSDT', 'XRPUSDT', 'SOLUSDT', 'AVAXUSDT', 'MATICUSDT'
        ]
        
        text_upper = text.upper()
        
        # Look for exact symbol matches
        for symbol in symbols:
            if symbol in text_upper:
                return symbol
        
        # Look for symbol without USDT
        symbol_patterns = [
            r'\b(BTC|BITCOIN)\b',
            r'\b(ETH|ETHEREUM)\b',
            r'\b(BNB|BINANCE)\b',
            r'\b(ADA|CARDANO)\b',
            r'\b(DOT|POLKADOT)\b',
            r'\b(LINK|CHAINLINK)\b',
            r'\b(LTC|LITECOIN)\b',
            r'\b(BCH|BITCOIN CASH)\b',
            r'\b(XLM|STELLAR)\b',
            r'\b(EOS)\b',
            r'\b(TRX|TRON)\b',
            r'\b(XRP|RIPPLE)\b',
            r'\b(SOL|SOLANA)\b',
            r'\b(AVAX|AVALANCHE)\b',
            r'\b(MATIC|POLYGON)\b'
        ]
        
        symbol_map = {
            'BTC': 'BTCUSDT', 'BITCOIN': 'BTCUSDT',
            'ETH': 'ETHUSDT', 'ETHEREUM': 'ETHUSDT',
            'BNB': 'BNBUSDT', 'BINANCE': 'BNBUSDT',
            'ADA': 'ADAUSDT', 'CARDANO': 'ADAUSDT',
            'DOT': 'DOTUSDT', 'POLKADOT': 'DOTUSDT',
            'LINK': 'LINKUSDT', 'CHAINLINK': 'LINKUSDT',
            'LTC': 'LTCUSDT', 'LITECOIN': 'LTCUSDT',
            'BCH': 'BCHUSDT', 'BITCOIN CASH': 'BCHUSDT',
            'XLM': 'XLMUSDT', 'STELLAR': 'XLMUSDT',
            'EOS': 'EOSUSDT',
            'TRX': 'TRXUSDT', 'TRON': 'TRXUSDT',
            'XRP': 'XRPUSDT', 'RIPPLE': 'XRPUSDT',
            'SOL': 'SOLUSDT', 'SOLANA': 'SOLUSDT',
            'AVAX': 'AVAXUSDT', 'AVALANCHE': 'AVAXUSDT',
            'MATIC': 'MATICUSDT', 'POLYGON': 'MATICUSDT'
        }
        
        for pattern in symbol_patterns:
            match = re.search(pattern, text_upper)
            if match:
                found_symbol = match.group(1)
                return symbol_map.get(found_symbol, f"{found_symbol}USDT")
        
        return None
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize trading symbol to standard format"""
        symbol = symbol.upper()
        
        # Add USDT if not present
        if not symbol.endswith('USDT') and not symbol.endswith('BUSD'):
            symbol += 'USDT'
        
        return symbol
    
    def validate_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parsed signal for completeness and correctness
        
        Args:
            signal: Parsed signal dictionary
            
        Returns:
            Validation result with status and errors
        """
        errors = []
        warnings = []
        
        try:
            # Required fields validation
            if 'action' not in signal:
                errors.append("Missing trading action (BUY/SELL)")
            elif signal['action'] not in ['BUY', 'SELL', 'LONG', 'SHORT']:
                errors.append(f"Invalid action: {signal['action']}")
            
            if 'symbol' not in signal:
                errors.append("Missing trading symbol")
            elif not self._is_valid_symbol(signal['symbol']):
                warnings.append(f"Unsupported symbol: {signal['symbol']}")
            
            # Price validation
            if 'price' in signal:
                try:
                    price = float(signal['price'])
                    if price <= 0:
                        errors.append("Price must be positive")
                except (ValueError, TypeError):
                    errors.append("Invalid price format")
            
            # Stop loss validation
            if 'stop_loss' in signal:
                try:
                    sl = float(signal['stop_loss'])
                    if sl <= 0:
                        errors.append("Stop loss must be positive")
                    elif 'price' in signal:
                        price = float(signal['price'])
                        action = signal.get('action', '').upper()
                        
                        if action in ['BUY', 'LONG'] and sl >= price:
                            warnings.append("Stop loss should be below entry price for long positions")
                        elif action in ['SELL', 'SHORT'] and sl <= price:
                            warnings.append("Stop loss should be above entry price for short positions")
                            
                except (ValueError, TypeError):
                    errors.append("Invalid stop loss format")
            
            # Take profit validation
            if 'take_profit' in signal:
                try:
                    tp = float(signal['take_profit'])
                    if tp <= 0:
                        errors.append("Take profit must be positive")
                    elif 'price' in signal:
                        price = float(signal['price'])
                        action = signal.get('action', '').upper()
                        
                        if action in ['BUY', 'LONG'] and tp <= price:
                            warnings.append("Take profit should be above entry price for long positions")
                        elif action in ['SELL', 'SHORT'] and tp >= price:
                            warnings.append("Take profit should be below entry price for short positions")
                            
                except (ValueError, TypeError):
                    errors.append("Invalid take profit format")
            
            # Quantity validation
            if 'quantity' in signal:
                try:
                    qty = float(signal['quantity'])
                    if qty <= 0:
                        errors.append("Quantity must be positive")
                except (ValueError, TypeError):
                    errors.append("Invalid quantity format")
            
            # Leverage validation
            if 'leverage' in signal:
                try:
                    leverage = int(signal['leverage'])
                    if leverage < 1 or leverage > 125:
                        warnings.append("Leverage should be between 1 and 125")
                except (ValueError, TypeError):
                    errors.append("Invalid leverage format")
            
            is_valid = len(errors) == 0
            
            return {
                'valid': is_valid,
                'errors': errors,
                'warnings': warnings,
                'completeness_score': self._calculate_completeness_score(signal)
            }
            
        except Exception as e:
            self.logger.error(f"Error validating signal: {e}")
            return {
                'valid': False,
                'errors': [f"Validation error: {str(e)}"],
                'warnings': [],
                'completeness_score': 0
            }
    
    def _is_valid_symbol(self, symbol: str) -> bool:
        """Check if symbol is in supported list"""
        supported_symbols = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'DOTUSDT',
            'LINKUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT', 'EOSUSDT',
            'TRXUSDT', 'XRPUSDT', 'SOLUSDT', 'AVAXUSDT', 'MATICUSDT'
        ]
        return symbol in supported_symbols
    
    def _calculate_completeness_score(self, signal: Dict[str, Any]) -> float:
        """Calculate signal completeness score (0-100)"""
        required_fields = ['action', 'symbol']
        optional_fields = ['price', 'stop_loss', 'take_profit', 'quantity', 'leverage']
        
        score = 0
        
        # Required fields (60% of score)
        required_present = sum(1 for field in required_fields if field in signal)
        score += (required_present / len(required_fields)) * 60
        
        # Optional fields (40% of score)
        optional_present = sum(1 for field in optional_fields if field in signal)
        score += (optional_present / len(optional_fields)) * 40
        
        return round(score, 1)
    
    def get_signal_examples(self) -> List[str]:
        """Get list of valid signal format examples"""
        return [
            "BUY BTCUSDT at 45000",
            "SELL ETHUSDT 50% at 3200",
            "LONG BTC SL: 44000 TP: 48000",
            "SHORT ETH quantity: 0.5 entry: 3180",
            "Entry: 45000, SL: 44000, TP: 48000",
            "BUY BTCUSDT leverage: 10x at 45000",
            "SELL ADAUSDT at 1.25 quantity: 1000"
        ]
