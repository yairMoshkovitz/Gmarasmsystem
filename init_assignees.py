import sqlite3
conn = sqlite3.connect('gemara_sms.db')
conn.execute('CREATE TABLE IF NOT EXISTS assignees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, is_active INTEGER DEFAULT 1)')
for name in ['דוד', 'משה', 'יאיר']:
    conn.execute("INSERT OR IGNORE INTO assignees (name) VALUES (?)", (name,))
conn.commit()
conn.close()
print("Assignees initialized.")
