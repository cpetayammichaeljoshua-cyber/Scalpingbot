#!/usr/bin/env python3
"""
Enhanced Error Handler for Console Output Optimization
Dynamically handles and suppresses errors to maintain clean console output
"""

import warnings
import logging
import sys
from functools import wraps

# Global warning suppression
warnings.filterwarnings('ignore')

class EnhancedErrorHandler:
    """Enhanced error handler with comprehensive suppression"""
    
    def __init__(self):
        self.setup_global_suppression()
    
    def setup_global_suppression(self):
        """Setup global error and warning suppression"""
        # Suppress all warnings
        warnings.filterwarnings('ignore')
        
        # Configure logging
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        logging.getLogger('requests').setLevel(logging.ERROR)
        logging.getLogger('aiohttp').setLevel(logging.ERROR)
        
        # Pandas suppression
        try:
            import pandas as pd
            pd.set_option('mode.chained_assignment', None)
            pd.options.mode.copy_on_write = True
        except ImportError:
            pass
        
        # Numpy suppression
        try:
            import numpy as np
            np.seterr(all='ignore')
        except ImportError:
            pass
    
    def suppress_function_errors(self, func):
        """Decorator to suppress function errors"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    return func(*args, **kwargs)
            except Exception as e:
                # Log critical errors only
                if 'critical' in str(e).lower():
                    logging.error(f"Critical error in {func.__name__}: {e}")
                return None
        return wrapper

# Global instance
enhanced_error_handler = EnhancedErrorHandler()

# Export decorator
suppress_errors = enhanced_error_handler.suppress_function_errors
