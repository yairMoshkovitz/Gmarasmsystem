from database import get_conn

def clear_registrations():
    print("Connecting to database...")
    conn = get_conn()
    try:
        print("Clearing subscriptions table...")
        conn.execute("DELETE FROM subscriptions")
        
        print("Clearing sent_questions table...")
        conn.execute("DELETE FROM sent_questions")
        
        conn.commit()
        print("✅ All registrations and sent questions have been cleared successfully.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clear_registrations()
