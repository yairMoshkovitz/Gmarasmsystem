"""
test_interface.py - Terminal interface for testing the question system
"""
import sys
import os
from database import get_conn, load_questions, float_to_daf_str
from questions_engine import select_questions_for_range, format_question_sms

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    conn = get_conn()
    tractates = conn.execute("SELECT id, name, total_dafim FROM tractates").fetchall()
    conn.close()

    if not tractates:
        print("No tractates found in database. Please run database.py first.")
        return

    while True:
        clear_screen()
        print("=== Gemara SMS Question System Tester ===")
        print("\nSelect a tractate:")
        for idx, t in enumerate(tractates):
            try:
                print(f"{idx + 1}. {t['name']} (Total Dafim: {t['total_dafim']})")
            except UnicodeEncodeError:
                print(f"{idx + 1}. [Tractate ID {t['id']}] (Total Dafim: {t['total_dafim']})")
        
        print("q. Quit")
        
        choice = input("\nEnter choice: ").strip().lower()
        if choice == 'q':
            break
        
        try:
            t_idx = int(choice) - 1
            if 0 <= t_idx < len(tractates):
                test_tractate(tractates[t_idx])
            else:
                print("Invalid choice.")
                input("Press Enter to continue...")
        except ValueError:
            print("Invalid input.")
            input("Press Enter to continue...")

def test_tractate(tractate):
    current_daf = 2.0
    dafim_per_day = 1.0
    
    while True:
        clear_screen()
        try:
            print(f"--- Testing Tractate: {tractate['name']} ---")
        except UnicodeEncodeError:
            print(f"--- Testing Tractate ID: {tractate['id']} ---")
            
        print(f"Current Position: {float_to_daf_str(current_daf)}")
        print(f"Learning Rate: {dafim_per_day} daf/day")
        print("\nOptions:")
        print("1. Get today's questions")
        print("2. Advance one day")
        print("3. Set current daf")
        print("4. Set dafim per day")
        print("b. Back to main menu")
        
        choice = input("\nEnter choice: ").strip().lower()
        
        if choice == '1':
            questions = select_questions_for_range(
                tractate['id'], 
                current_daf, 
                dafim_per_day, 
                count=2,
                already_sent=[]
            )
            print("\n--- Selected Questions ---")
            if not questions:
                print("No questions found for this range.")
            for i, q in enumerate(questions):
                sms = format_question_sms(q, i + 1, tractate['name'])
                try:
                    print(f"\nSMS {i+1}:\n{sms}")
                except UnicodeEncodeError:
                    # Fallback for terminal encoding issues
                    print(f"\nSMS {i+1} (Encoded):\n{sms.encode('ascii', 'replace').decode()}")
            input("\nPress Enter to continue...")
            
        elif choice == '2':
            current_daf += dafim_per_day
            print(f"Advanced to {float_to_daf_str(current_daf)}")
            
        elif choice == '3':
            try:
                new_daf = float(input("Enter daf number (e.g. 2.0 for 2a, 2.5 for 2b): "))
                current_daf = new_daf
            except ValueError:
                print("Invalid number.")
                input("Press Enter...")
                
        elif choice == '4':
            try:
                new_rate = float(input("Enter dafim per day (e.g. 1.0 or 0.5): "))
                dafim_per_day = new_rate
            except ValueError:
                print("Invalid number.")
                input("Press Enter...")
                
        elif choice == 'b':
            break

if __name__ == "__main__":
    main()
