"""
logging_config.py - Centralized logging configuration for DEBUG mode
"""
import logging
import functools
import sys
import os

# Get log level from environment or default to INFO
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# Configure logging
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Create a logger instance
logger = logging.getLogger('QA-SMS')
logger.setLevel(log_level)


def log_function_entry(func):
    """
    Decorator to automatically log function entry with parameters.
    Usage: @log_function_entry
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        module_name = func.__module__
        
        # Format arguments for logging
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        
        # Truncate long signatures
        if len(signature) > 200:
            signature = signature[:200] + "..."
        
        # Only log if level is DEBUG to save bandwidth/rate limits
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"→ ENTERING {module_name}.{func_name}({signature})")
        
        try:
            result = func(*args, **kwargs)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"← EXITING {module_name}.{func_name}() - Success")
            return result
        except Exception as e:
            logger.error(f"✗ EXCEPTION in {module_name}.{func_name}(): {e}", exc_info=True)
            raise
    
    return wrapper


def get_logger(name=None):
    """
    Get a logger instance for a specific module.
    Usage: logger = get_logger(__name__)
    """
    if name:
        return logging.getLogger(f'QA-SMS.{name}')
    return logger
