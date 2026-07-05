
from database import get_conn
import os
import sys

def clean():
    print("--- Server Cleanup: Mock Questions ---")
    
    # Check if we are connected to a database
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        print(f"Connected to: Postgres")
    else:
        print(f"Connected to: Local SQLite")
        
    conn = get_conn()
    is_postgres = bool(database_url)
    
    # Patterns for mock data used in tests
    mock_patterns = ['ext_q%', 'single_q']
    
    total_deleted_q = 0
    total_deleted_sq = 0
    
    for pattern in mock_patterns:
        try:
            # 1. Clean from questions table
            query_q = "DELETE FROM questions WHERE external_id LIKE %s" if is_postgres else "DELETE FROM questions WHERE external_id LIKE ?"
            conn.execute(query_q, (pattern,))
            print(f"Sent delete command for pattern '{pattern}' to questions table.")
            
            # 2. Clean from sent_questions table
            query_sq = "DELETE FROM sent_questions WHERE question_id LIKE %s" if is_postgres else "DELETE FROM sent_questions WHERE question_id LIKE ?"
            conn.execute(query_sq, (pattern,))
            print(f"Sent delete command for pattern '{pattern}' to sent_questions table.")
            
        except Exception as e:
            print(f"Error cleaning pattern '{pattern}': {e}")

    try:
        conn.commit()
        print("Changes committed successfully.")
    except Exception as e:
        print(f"Error during commit: {e}")
        
    conn.close()
    print("Cleanup process finished.")

if __name__ == "__main__":
    clean()
