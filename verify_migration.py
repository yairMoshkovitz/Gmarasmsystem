import sqlite3
from database import get_conn, float_to_daf_str

def test_split_question():
    conn = get_conn()
    print("Checking for split questions in Tractate חולין...")
    
    # Get tractate_id for חולין
    row = conn.execute("SELECT id FROM tractates WHERE name = 'חולין'").fetchone()
    if not row:
        print("Tractate חולין not found.")
        return
    tractate_id = row[0]
    
    # Check questions for external_id 'שיא' to 'שיט'
    # Since we split 'שי', we expect to find them as separate rows
    ids_to_check = ['שי', 'שיא', 'שיב', 'שיג', 'שיד', 'שטו', 'שטז', 'שיז', 'שיח', 'שיט']
    placeholders = ",".join(["?"] * len(ids_to_check))
    
    rows = conn.execute(f"""
        SELECT external_id, question_text, start_daf 
        FROM questions 
        WHERE tractate_id = ? AND external_id IN ({placeholders})
        ORDER BY id
    """, [tractate_id] + ids_to_check).fetchall()
    
    print(f"Found {len(rows)} split parts:")
    for r in rows:
        text_preview = r['question_text'][:50] + "..." if len(r['question_text']) > 50 else r['question_text']
        print(f"ID: {r['external_id']} | Daf: {float_to_daf_str(r['start_daf'])} | Text: {text_preview}")

    # Check reversed range fix for question 'א'
    row_a = conn.execute("SELECT start_daf, end_daf FROM questions WHERE tractate_id = ? AND external_id = 'א'", (tractate_id,)).fetchone()
    if row_a:
        print(f"\nQuestion 'א' range: {row_a['start_daf']} to {row_a['end_daf']} (Expected 2.0 to 2.5)")

    conn.close()

if __name__ == "__main__":
    test_split_question()
