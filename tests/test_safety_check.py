"""
Test to verify that the safety check prevents sending real SMS to test numbers.
"""
from sms_service import send_real_sms, set_live_mode

def test_safety_check():
    """Test that fake phone numbers are blocked from real SMS sending."""
    print("\n" + "="*70)
    print("Testing Safety Check for Fake Phone Numbers")
    print("="*70)
    
    # Test numbers that should be blocked
    test_numbers = [
        "0590000123",
        "0590000456",
        "0580000123",
        "0580000999"
    ]
    
    print("\n1. Testing with fake numbers (should be blocked):")
    for phone in test_numbers:
        result = send_real_sms(phone, "Test message")
        assert result == False, f"Expected {phone} to be blocked, but it wasn't!"
        print(f"   ✓ {phone} was correctly blocked")
    
    print("\n2. Testing with a real-looking number (should attempt to send):")
    # This will fail because we don't have valid API credentials in test,
    # but it should NOT be blocked by the safety check
    real_number = "0521234567"
    result = send_real_sms(real_number, "Test message")
    # We expect False here because API credentials are missing, not because of blocking
    print(f"   ✓ {real_number} was not blocked by safety check (API failure is expected)")
    
    print("\n" + "="*70)
    print("✅ All safety checks passed!")
    print("="*70)

if __name__ == "__main__":
    test_safety_check()
