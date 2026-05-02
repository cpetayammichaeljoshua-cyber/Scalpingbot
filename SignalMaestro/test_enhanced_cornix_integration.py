#!/usr/bin/env python3
"""
Test script for Enhanced Cornix Integration
Tests all functionality including retry logic, error handling, and signal validation
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from enhanced_cornix_integration import EnhancedCornixIntegration

# Setup logging for testing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_cornix_integration.log')
    ]
)

logger = logging.getLogger(__name__)

async def test_configuration_validation():
    """Test configuration validation"""
    logger.info("🧪 Testing configuration validation...")
    
    cornix = EnhancedCornixIntegration()
    
    # Test basic configuration check
    config_result = cornix._check_configuration()
    logger.info(f"Configuration check result: {config_result}")
    
    # Test comprehensive validation
    validation_result = await cornix.validate_webhook_configuration()
    logger.info(f"Webhook validation result: {validation_result}")
    
    return validation_result

async def test_signal_validation():
    """Test signal validation logic"""
    logger.info("🧪 Testing signal validation...")
    
    cornix = EnhancedCornixIntegration()
    
    # Test valid signal
    valid_signal = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'entry': 45000.0,
        'stop_loss': 44000.0,
        'take_profits': [46000.0, 47000.0, 48000.0],
        'leverage': 10
    }
    
    validation_result = cornix._validate_advanced_signal(valid_signal)
    logger.info(f"Valid signal validation: {validation_result}")
    assert validation_result['valid'], f"Valid signal should pass validation: {validation_result['error']}"
    
    # Test invalid signal (missing fields)
    invalid_signal = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG'
        # Missing required fields
    }
    
    validation_result = cornix._validate_advanced_signal(invalid_signal)
    logger.info(f"Invalid signal validation: {validation_result}")
    assert not validation_result['valid'], "Invalid signal should fail validation"
    
    # Test invalid price relationships
    invalid_prices_signal = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'entry': 45000.0,
        'stop_loss': 46000.0,  # Invalid: SL should be below entry for LONG
        'take_profits': [44000.0],  # Invalid: TP should be above entry for LONG
        'leverage': 10
    }
    
    validation_result = cornix._validate_advanced_signal(invalid_prices_signal)
    logger.info(f"Invalid price relationships validation: {validation_result}")
    assert not validation_result['valid'], "Invalid price relationships should fail validation"
    
    logger.info("✅ Signal validation tests passed!")

async def test_connection():
    """Test connection functionality"""
    logger.info("🧪 Testing connection functionality...")
    
    cornix = EnhancedCornixIntegration()
    
    # Test connection
    connection_result = await cornix.test_connection()
    logger.info(f"Connection test result: {connection_result}")
    
    # Get health status
    health_status = cornix.get_health_status()
    logger.info(f"Health status: {health_status}")
    
    # Get statistics
    stats = cornix.get_connection_statistics()
    logger.info(f"Connection statistics: {stats}")
    
    return connection_result

async def test_error_handling():
    """Test error handling and categorization"""
    logger.info("🧪 Testing error handling...")
    
    cornix = EnhancedCornixIntegration()
    
    # Test retryable error detection
    assert cornix._is_retryable_error(500, "Internal server error"), "500 should be retryable"
    assert cornix._is_retryable_error(503, "Service unavailable"), "503 should be retryable"
    assert not cornix._is_retryable_error(400, "Bad request"), "400 should not be retryable"
    assert not cornix._is_retryable_error(401, "Unauthorized"), "401 should not be retryable"
    
    # Test error categorization
    error_detail = cornix._categorize_http_error(404)
    logger.info(f"404 error categorization: {error_detail}")
    assert error_detail['category'] == 'config_error', "404 should be categorized as config_error"
    
    error_detail = cornix._categorize_http_error(429)
    logger.info(f"429 error categorization: {error_detail}")
    assert error_detail['category'] == 'rate_limit', "429 should be categorized as rate_limit"
    
    logger.info("✅ Error handling tests passed!")

async def test_advanced_signal():
    """Test sending advanced signal (if webhook is configured)"""
    logger.info("🧪 Testing advanced signal sending...")
    
    cornix = EnhancedCornixIntegration()
    
    # Only test if webhook is configured
    if not cornix.webhook_url:
        logger.warning("⚠️ Webhook URL not configured - skipping live signal test")
        return {'success': False, 'reason': 'no_webhook_configured'}
    
    # Test with realistic signal
    test_signal = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'entry': 45000.0,
        'stop_loss': 44000.0,
        'take_profits': [46000.0, 47000.0, 48000.0],
        'leverage': 10,
        'strategy': 'Test Strategy',
        'ml_enhanced': True,
        'real_trade_executed': False,
        'message': f'Test signal sent at {datetime.utcnow().isoformat()}'
    }
    
    result = await cornix.send_advanced_signal(test_signal)
    logger.info(f"Advanced signal result: {result}")
    
    return result

async def test_test_signal():
    """Test the built-in test signal functionality"""
    logger.info("🧪 Testing built-in test signal...")
    
    cornix = EnhancedCornixIntegration()
    
    if not cornix.webhook_url:
        logger.warning("⚠️ Webhook URL not configured - skipping test signal")
        return {'success': False, 'reason': 'no_webhook_configured'}
    
    result = await cornix.send_test_signal()
    logger.info(f"Test signal result: {result}")
    
    return result

async def run_comprehensive_test():
    """Run comprehensive test suite"""
    logger.info("🚀 Starting comprehensive Cornix integration test...")
    
    test_results = {}
    
    try:
        # Test 1: Configuration validation
        test_results['configuration'] = await test_configuration_validation()
        
        # Test 2: Signal validation
        await test_signal_validation()
        test_results['signal_validation'] = {'success': True}
        
        # Test 3: Error handling
        await test_error_handling()
        test_results['error_handling'] = {'success': True}
        
        # Test 4: Connection testing
        test_results['connection'] = await test_connection()
        
        # Test 5: Advanced signal (only if configured)
        test_results['advanced_signal'] = await test_advanced_signal()
        
        # Test 6: Test signal (only if configured)
        test_results['test_signal'] = await test_test_signal()
        
        # Summary
        logger.info("📊 Test Results Summary:")
        for test_name, result in test_results.items():
            status = "✅ PASSED" if result.get('success', False) else "❌ FAILED"
            if result.get('reason') == 'no_webhook_configured':
                status = "⚠️ SKIPPED (No webhook configured)"
            logger.info(f"   {test_name}: {status}")
        
        # Overall status
        critical_tests = ['configuration', 'signal_validation', 'error_handling']
        critical_passed = all(test_results.get(test, {}).get('success', False) for test in critical_tests)
        
        if critical_passed:
            logger.info("🎉 All critical tests passed! Cornix integration is properly fixed.")
        else:
            logger.error("💥 Some critical tests failed. Check the logs above.")
        
        return test_results
        
    except Exception as e:
        logger.error(f"💥 Test suite failed with exception: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'error': str(e)}

async def main():
    """Main test function"""
    try:
        logger.info("="*60)
        logger.info("🧪 ENHANCED CORNIX INTEGRATION TEST SUITE")
        logger.info("="*60)
        
        results = await run_comprehensive_test()
        
        logger.info("="*60)
        logger.info("📋 Final Test Report:")
        
        # Ensure results is a dictionary
        if not isinstance(results, dict):
            logger.error(f"Unexpected results type: {type(results)}")
            results = {}
            
        logger.info(f"   Configuration Status: {results.get('configuration', {}).get('overall_status', 'unknown')}")
        logger.info(f"   Signal Validation: {'✅ Working' if results.get('signal_validation', {}).get('success') else '❌ Failed'}")
        logger.info(f"   Error Handling: {'✅ Working' if results.get('error_handling', {}).get('success') else '❌ Failed'}")
        logger.info(f"   Connection Test: {'✅ Working' if results.get('connection', {}).get('success') else '❌ Failed'}")
        
        webhook_configured = results.get('configuration', {}).get('webhook_url', {}).get('configured', False)
        if webhook_configured:
            logger.info(f"   Live Signal Test: {'✅ Working' if results.get('advanced_signal', {}).get('success') else '❌ Failed'}")
        else:
            logger.info("   Live Signal Test: ⚠️ Skipped (Configure CORNIX_WEBHOOK_URL to test)")
        
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Main test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())