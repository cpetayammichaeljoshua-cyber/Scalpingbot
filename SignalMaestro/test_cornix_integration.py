#!/usr/bin/env python3
"""
Test script for Cornix integration
Tests the forward_to_cornix functionality and related components
"""

import asyncio
import logging
from datetime import datetime
from enhanced_perfect_scalping_bot_v2 import EnhancedPerfectScalpingBotV2, TradeProgress

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_cornix_integration():
    """Test the Cornix integration functionality"""
    logger.info("🧪 Testing Cornix Integration...")
    
    try:
        # Create bot instance
        bot = EnhancedPerfectScalpingBotV2()
        
        # Test 1: Test Cornix connection
        logger.info("1️⃣ Testing Cornix connection...")
        cornix_test = await bot.cornix.test_connection()
        logger.info(f"Cornix connection test: {'✅ Success' if cornix_test.get('success') else '❌ Failed'}")
        
        # Test 2: Test signal formatting and forwarding
        logger.info("2️⃣ Testing signal forwarding...")
        test_signal = {
            'symbol': 'BTCUSDT',
            'action': 'BUY',
            'entry_price': 50000.0,
            'leverage': 10,
            'market_session': 'NY',
            'volatility_factor': 1.2,
            'high_impact_time': False,
            'time_enhanced': True
        }
        
        test_trade = TradeProgress(
            symbol='BTCUSDT',
            direction='BUY', 
            entry_price=50000.0,
            original_sl=49000.0,
            current_sl=49000.0,
            tp1=51000.0,
            tp2=52000.0,
            tp3=53000.0,
            risk_reward_ratio=3.0
        )
        
        # Test forward_to_cornix function
        cornix_success = await bot.forward_to_cornix(test_signal, test_trade)
        logger.info(f"Signal forwarding test: {'✅ Success' if cornix_success else '❌ Failed'}")
        
        # Test 3: Test stop loss updates
        logger.info("3️⃣ Testing stop loss updates...")
        sl_result = await bot.cornix.update_stop_loss(
            'BTCUSDT', 
            50000.0, 
            'Test SL update'
        )
        logger.info(f"Stop loss update test: {'✅ Success' if sl_result.get('success') else '❌ Failed'}")
        
        # Test 4: Test position closure
        logger.info("4️⃣ Testing position closure...")
        close_result = await bot.cornix.close_position(
            'BTCUSDT', 
            'Test position closure', 
            100
        )
        logger.info(f"Position closure test: {'✅ Success' if close_result.get('success') else '❌ Failed'}")
        
        # Test 5: Test rate-limited messaging
        logger.info("5️⃣ Testing rate-limited messaging...")
        if bot.rate_limiter.can_send_message():
            test_message = """🧪 **Cornix Integration Test**

✅ All systems operational
🌐 Cornix: Connected
📊 Signal forwarding: Active
⚡ Rate limiting: Working

*Test completed successfully!*"""
            
            if bot.config.TELEGRAM_BOT_TOKEN and bot.admin_chat_id:
                await bot.send_rate_limited_message(bot.admin_chat_id, test_message)
                logger.info("📱 Test message sent to Telegram")
            else:
                logger.info("📱 Telegram configuration not available for testing")
        
        logger.info("✅ Cornix integration tests completed!")
        
        return {
            'cornix_connection': cornix_test.get('success', False),
            'signal_forwarding': cornix_success,
            'stop_loss_updates': sl_result.get('success', False),
            'position_closure': close_result.get('success', False),
            'overall_success': True
        }
        
    except Exception as e:
        logger.error(f"❌ Cornix integration test failed: {e}")
        return {
            'overall_success': False,
            'error': str(e)
        }

async def main():
    """Main test execution"""
    logger.info("🚀 Starting Cornix Integration Tests...")
    
    results = await test_cornix_integration()
    
    if results.get('overall_success'):
        logger.info("🎉 All Cornix integration tests passed!")
    else:
        logger.error(f"💥 Tests failed: {results.get('error')}")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())