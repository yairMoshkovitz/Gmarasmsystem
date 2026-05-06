import sqlite3
import json
import os

DB_PATH = "gemara_sms.db"

def sync_templates():
    if not os.path.exists(DB_PATH):
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Load JSON templates
        template_path = "sms_templates.json"
        if not os.path.exists(template_path):
            print("JSON templates not found.")
            return
            
        with open(template_path, "r", encoding="utf-8") as f:
            json_templates = json.load(f)
            
        print(f"Syncing {len(json_templates)} templates to database...")
        
        for key, content in json_templates.items():
            # Update if exists, insert if not
            cur.execute("""
                INSERT INTO sms_templates (key, content) 
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET content=excluded.content
            """, (key, content))
            
        conn.commit()
        print("Sync completed successfully.")
        
    except Exception as e:
        conn.rollback()
        print(f"Sync failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    sync_templates()
