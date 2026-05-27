
from database import get_conn

def diagnose():
    conn = get_conn()
    try:
        # Check specific tractate
        t = conn.execute("SELECT id, name FROM tractates WHERE id = 59").fetchone()
        if t:
            print(f"Tractate ID 59 is: {t['name']}")
            count = conn.execute("SELECT COUNT(*) as count FROM questions WHERE tractate_id = 59").fetchone()
            print(f"Total questions for this tractate: {count['count']}")
            
            # Check daf 12 specifically
            q_daf_12 = conn.execute("SELECT COUNT(*) as count FROM questions WHERE tractate_id = 59 AND start_daf <= 12.99 AND end_daf >= 12.0").fetchone()
            print(f"Questions overlapping Daf 12: {q_daf_12['count']}")
            
            if q_daf_12['count'] == 0:
                print("Looking for any questions in this tractate to see their daf range...")
                sample = conn.execute("SELECT start_daf, end_daf FROM questions WHERE tractate_id = 59 LIMIT 5").fetchall()
                for s in sample:
                    print(f"  Found range: {s['start_daf']} - {s['end_daf']}")
        else:
            print("Tractate ID 59 NOT FOUND!")
            # List all tractates
            all_t = conn.execute("SELECT id, name FROM tractates").fetchall()
            for row in all_t:
                print(f"  ID {row['id']}: {row['name']}")
                
    except Exception as e:
        print(f"Diagnosis failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    diagnose()
