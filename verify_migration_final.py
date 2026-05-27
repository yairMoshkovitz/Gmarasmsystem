import sqlite3
import os

def check_results():
    db_path = "gemara_sms.db"
    if not os.path.exists(db_path):
        print("DB not found!")
        return

    conn = sqlite3.connect(db_path)
    ids = ('עז','עח','עט','פ','פא','פב','פג','פד')
    query = f"SELECT external_id, start_daf FROM questions WHERE tractate_id=560 AND external_id IN {ids} ORDER BY id ASC"
    
    print("Results for tractate 560 (נדרים):")
    cursor = conn.execute(query)
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Daf: {row[1]}")
    conn.close()

if __name__ == "__main__":
    check_results()
