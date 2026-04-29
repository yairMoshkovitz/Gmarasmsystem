from database import get_conn
conn = get_conn()
subs = conn.execute("SELECT * FROM subscriptions").fetchall()
print(f"Total Subscriptions: {len(subs)}")
for s in subs:
    print(dict(s))
conn.close()
