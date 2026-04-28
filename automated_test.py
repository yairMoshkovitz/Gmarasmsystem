"""
automated_test.py - Non-interactive test script to verify the question selection logic
"""
from database import get_conn, float_to_daf_str
from questions_engine import select_questions_for_range, format_question_sms
import sys

def run_test():
    conn = get_conn()
    tractates = conn.execute("SELECT id, name, total_dafim FROM tractates").fetchall()
    conn.close()

    if not tractates:
        print("Error: No tractates found. Run database.py first.")
        return

    # Use Berachos (or the first tractate found)
    t = tractates[0]
    print(f"Testing Tractate: {t['name']} (ID: {t['id']})")

    # Test cases: (current_daf, dafim_per_day)
    test_cases = [
        (2.0, 1.0),   # Daf 2
        (3.0, 0.5),   # Daf 3a
        (10.0, 1.0),  # Daf 10
    ]

    for daf, rate in test_cases:
        print(f"\n--- Testing Range: {float_to_daf_str(daf)} to {float_to_daf_str(daf + rate)} ---")
        questions = select_questions_for_range(
            t['id'],
            daf,
            rate,
            count=2,
            already_sent=[]
        )
        
        if not questions:
            print("  Result: No questions found.")
        else:
            print(f"  Result: Found {len(questions)} questions.")
            for i, q in enumerate(questions):
                sms = format_question_sms(q, i + 1, t['name'])
                # Only print first line to avoid encoding issues in large output
                first_line = sms.split('\n')[0]
                try:
                    print(f"    Q{i+1}: {first_line}...")
                except UnicodeEncodeError:
                    print(f"    Q{i+1}: [Hebrew Content]...")

    print("\n✅ Automated test completed.")

if __name__ == "__main__":
    run_test()
