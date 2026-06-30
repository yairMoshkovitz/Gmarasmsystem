"""
test_debug_logging.py - Test script to verify DEBUG logging is working
"""
from logging_config import get_logger, log_function_entry

logger = get_logger(__name__)

@log_function_entry
def test_function_1(param1, param2):
    """Test function with parameters"""
    logger.debug("Inside test_function_1")
    result = param1 + param2
    logger.info(f"Result: {result}")
    return result

@log_function_entry
def test_function_2(name="Test"):
    """Test function with default parameter"""
    logger.debug(f"Processing name: {name}")
    return f"Hello, {name}!"

@log_function_entry
def test_nested_calls():
    """Test nested function calls"""
    logger.debug("Starting nested calls test")
    result1 = test_function_1(5, 10)
    result2 = test_function_2("World")
    logger.debug(f"Nested results: {result1}, {result2}")
    return result1, result2

@log_function_entry
def test_exception_handling():
    """Test exception logging"""
    logger.debug("Testing exception handling")
    try:
        result = 10 / 0
    except ZeroDivisionError as e:
        logger.error(f"Caught expected error: {e}")
        return "Error handled"
    return "No error"

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("Starting DEBUG Logging Test")
    logger.info("=" * 80)
    
    # Test 1: Simple function call
    logger.info("\n--- Test 1: Simple function call ---")
    test_function_1(3, 7)
    
    # Test 2: Function with default parameter
    logger.info("\n--- Test 2: Function with default parameter ---")
    test_function_2()
    
    # Test 3: Nested function calls
    logger.info("\n--- Test 3: Nested function calls ---")
    test_nested_calls()
    
    # Test 4: Exception handling
    logger.info("\n--- Test 4: Exception handling ---")
    test_exception_handling()
    
    logger.info("\n" + "=" * 80)
    logger.info("DEBUG Logging Test Completed Successfully!")
    logger.info("=" * 80)
    
    print("\n✅ If you see detailed DEBUG logs above with function entry/exit messages,")
    print("   the logging configuration is working correctly!")
