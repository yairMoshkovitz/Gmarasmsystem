from questions_engine import select_questions_for_range
from database import get_conn, float_to_daf_str

def run_retrieval_test():
    conn = get_conn()
    print("--- Database Question Retrieval Test ---")
    
    # 1. Get a tractate (e.g., חולין)
    row = conn.execute("SELECT id, name FROM tractates WHERE name = 'חולין'").fetchone()
    if not row:
        print("Tractate 'חולין' not found in DB.")
        return
    
    t_id, t_name = row[0], row[1]
    print(f"Testing for tractate: {t_name} (ID: {t_id})")

    # 2. Test retrieval for a specific range where we expect questions
    # Daf 49 (מט) where we fixed the split questions
    start_f = 19
    end_f = 19.5
    already_sent = [] # simulate fresh user
    
    print(f"\nSearching for questions in range: {float_to_daf_str(start_f)} to {float_to_daf_str(end_f)}")
    
    selected = select_questions_for_range(t_id, start_f, end_f, already_sent, max_questions=5)
    
    print(f"Found {len(selected)} questions:")
    for i, q in enumerate(selected, 1):
        print(f"  {i}. [ID: {q.get('external_id')}] {q['text'][:100]}...")
        if q.get('start_daf'):
            print(f"     Found on Daf: {float_to_daf_str(q['start_daf'])}")

    # 3. Verify 'already_sent' logic
    if selected:
        first_id = selected[0].get('external_id')
        print(f"\nSimulating that we already sent Question ID: {first_id}")
        new_selection = select_questions_for_range(t_id, start_f, end_f, [first_id], max_questions=5)
        
        ids_in_new = [q.get('external_id') for q in new_selection]
        if first_id not in ids_in_new:
            print(f"✅ Success: Question {first_id} was correctly excluded from the new selection.")
        else:
            print(f"❌ Error: Question {first_id} was found in selection despite being in already_sent list.")

    conn.close()

if __name__ == "__main__":
    run_retrieval_test()
