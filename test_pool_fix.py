
import os
import threading
from database import get_conn, init_db

def test_connection_pool():
    print("Testing connection pool closure and reuse...")
    
    # 1. Test basic connection and close
    conn = get_conn()
    print("Got connection 1")
    conn.execute("SELECT 1")
    conn.close()
    print("Closed connection 1 (should be returned to pool if Postgres)")

    # 2. Test concurrent connections to ensure we don't leak
    def worker(i):
        try:
            c = get_conn()
            # print(f"Thread {i} got connection")
            c.execute("SELECT 1")
            c.close()
            # print(f"Thread {i} closed connection")
        except Exception as e:
            print(f"Thread {i} failed: {e}")

    threads = []
    for i in range(50): # More than maxconn (20) to see if it waits or handles properly
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
    
    print("Concurrent test finished. Check logs for 'connection pool exhausted'.")

if __name__ == "__main__":
    # Ensure DATABASE_URL is set if testing Postgres, otherwise it tests SQLite (which is also good to verify no regressions)
    test_connection_pool()
