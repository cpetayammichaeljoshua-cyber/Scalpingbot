#!/usr/bin/env python3
"""
Market Microstructure Enhancer
Integrates advanced market depth analysis into signal pipeline
Boosts signal confidence with DOM depth, tape, and footprint analysis
"""

import logging
import asyncio
from typing import Dict, Any, Optional
import pandas as pd

from SignalMaestro.advanced_market_depth_analyzer import (
    get_market_depth_analyzer,
    DOMDepthSignal,
    TapePattern,
    FootprintType
)


class MarketMicrostructureEnhancer:
    """Enhance trading signals with market microstructure analysis"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.depth_analyzer = get_market_depth_analyzer()
        
        # Confidence boost thresholds
        self.dom_boost_threshold = 60.0  # Minimum DOM strength for boost
        self.tape_boost_threshold = 40.0  # Minimum tape momentum for boost
        self.footprint_boost_threshold = 50.0  # Minimum footprint strength
        
        self.logger.info("✅ Market Microstructure Enhancer initialized")
    
    async def enhance_signal(self, base_signal: Dict[str, Any], 
                            depth: Dict[str, Any],
                            trades: list,
                            ohlcv: pd.DataFrame,
                            current_price: float) -> Dict[str, Any]:
        """
        Enhance trading signal with market microstructure analysis
        
        Returns enhanced signal with:
        - Adjusted confidence
        - Microstructure validation
        - Additional reasoning
        """
        try:
            # Get market depth analysis
            market_signal = await self.depth_analyzer.get_market_depth_signal(
                depth, trades, ohlcv, current_price
            )
            
            # Extract components
            dom_metrics = market_signal.get('dom_metrics', {})
            tape_analysis = market_signal.get('tape_analysis', {})
            footprint = market_signal.get('footprint', {})
            
            # Calculate confidence boost
            confidence_boost = 0.0
            reasoning = []
            
            # DOM depth boost
            dom_strength = dom_metrics.get('strength', 0.0)
            if dom_strength > self.dom_boost_threshold:
                if market_signal['direction'] == base_signal.get('direction', 'NEUTRAL'):
                    dom_boost = (dom_strength / 100.0) * 15  # Up to +15% from DOM
                    confidence_boost += dom_boost
                    reasoning.append(f"DOM {market_signal['direction']}: +{dom_boost:.1f}%")
            
            # Tape momentum boost
            tape_momentum = tape_analysis.get('momentum', 0.0)
            tape_direction = "BUY" if tape_momentum > 0 else "SELL"
            if abs(tape_momentum) > self.tape_boost_threshold:
                if tape_direction == base_signal.get('direction', 'NEUTRAL'):
                    tape_boost = (abs(tape_momentum) / 100.0) * 12  # Up to +12% from tape
                    confidence_boost += tape_boost
                    reasoning.append(f"Tape {tape_direction}: +{tape_boost:.1f}%")
            
            # Footprint boost
            footprint_strength = footprint.get('strength', 0.0)
            if footprint_strength > self.footprint_boost_threshold:
                footprint_type = footprint.get('type', '')
                if (footprint_type == 'ABSORPTION' and base_signal.get('direction') == 'BUY') or \
                   (footprint_type == 'DISTRIBUTION' and base_signal.get('direction') == 'SELL'):
                    footprint_boost = (footprint_strength / 100.0) * 10  # Up to +10% from footprint
                    confidence_boost += footprint_boost
                    reasoning.append(f"Footprint {footprint_type}: +{footprint_boost:.1f}%")
            
            # Validation check: Direction alignment
            direction_alignment = market_signal['direction'] == base_signal.get('direction')
            if direction_alignment:
                reasoning.append("✅ Direction aligned with market microstructure")
            else:
                reasoning.append("⚠️ Direction divergence from microstructure")
                confidence_boost = max(confidence_boost - 10, -20)  # Penalty for divergence
            
            # Calculate final confidence
            base_confidence = base_signal.get('confidence', 50.0)
            enhanced_confidence = min(base_confidence + confidence_boost, 100.0)
            enhanced_confidence = max(enhanced_confidence, 10.0)  # Floor at 10%
            
            # Create enhanced signal
            enhanced_signal = base_signal.copy()
            enhanced_signal['confidence'] = float(enhanced_confidence)
            enhanced_signal['microstructure_boost'] = float(confidence_boost)
            enhanced_signal['microstructure_reasoning'] = reasoning
            enhanced_signal['dom_analysis'] = dom_metrics
            enhanced_signal['tape_analysis'] = tape_analysis
            enhanced_signal['footprint_analysis'] = footprint
            enhanced_signal['microstructure_confidence'] = float(market_signal.get('confidence', 0.0))
            
            return enhanced_signal
            
        except Exception as e:
            self.logger.error(f"❌ Signal enhancement error: {e}")
            # Return signal unchanged if analysis fails
            base_signal['microstructure_boost'] = 0.0
            base_signal['microstructure_reasoning'] = [f"Analysis failed: {str(e)}"]
            return base_signal
    
    async def get_microstructure_alert(self, depth: Dict[str, Any],
                                       trades: list,
                                       ohlcv: pd.DataFrame,
                                       current_price: float) -> Dict[str, Any]:
        """
        Get standalone microstructure alert (for monitoring)
        Can be used independently of signal generation
        """
        try:
            return await self.depth_analyzer.get_market_depth_signal(
                depth, trades, ohlcv, current_price
            )
        except Exception as e:
            self.logger.error(f"❌ Microstructure alert error: {e}")
            return {"direction": "NEUTRAL", "confidence": 0.0}


# Global instance
_enhancer = None

def get_market_microstructure_enhancer() -> MarketMicrostructureEnhancer:
    """Get or create enhancer instance"""
    global _enhancer
    if _enhancer is None:
        _enhancer = MarketMicrostructureEnhancer()
    return _enhancer
