import os
from database import get_conn

def clean_database():
    """
    Cleans the database from invalid values, specifically focusing on the age column.
    Ensures age is a valid integer or NULL.
    """
    print("Starting database cleanup...")
    conn = get_conn()
    
    try:
        # 1. Clean Age column in users table
        is_postgres = bool(os.environ.get("DATABASE_URL"))
        
        if is_postgres:
            # Postgres specific cleanup
            conn.execute("""
                UPDATE users 
                SET age = NULL 
                WHERE age IS NOT NULL AND (age < 0 OR age > 120)
            """)
        else:
            # SQLite specific cleanup
            conn.execute("""
                UPDATE users 
                SET age = NULL 
                WHERE age IS NOT NULL AND (typeof(age) != 'integer' OR age < 0 OR age > 120)
            """)
            
        conn.commit()
        print("Age column cleaned.")
        
        # 2. Remove whitespace from phone numbers
        conn.execute("UPDATE users SET phone = TRIM(phone)")
        conn.commit()
        print("Phone numbers trimmed.")

        # 3. Delete users with NO age AND NO city (as requested)
        cursor = conn.execute("DELETE FROM users WHERE (age IS NULL OR age = '') AND (city IS NULL OR city = '')")
        conn.commit()
        deleted_count = cursor.rowcount if hasattr(cursor, 'rowcount') else "some"
        print(f"Deleted {deleted_count} users with missing age and city.")

    except Exception as e:
        print(f"Error during cleanup: {e}")
    finally:
        conn.close()
        print("Cleanup finished.")

if __name__ == "__main__":
    clean_database()
