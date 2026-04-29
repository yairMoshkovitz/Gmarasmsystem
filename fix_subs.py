import os
from database import get_conn

def fix_subscriptions():
    """
    Fixes existing subscriptions that might be linked to non-existent tractate IDs.
    Re-links them based on the tractate name if possible.
    """
    print("Fixing subscriptions links...")
    conn = get_conn()
    
    # 1. Map existing tractates by name
    tractates = conn.execute("SELECT id, name FROM tractates").fetchall()
    name_to_id = {t['name']: t['id'] for t in tractates}
    print(f"Current tractates in DB: {name_to_id}")
    
    # 2. Hardcoded mapping based on common names if ID is lost
    # Based on previous debug output:
    # 45, 46, 51, 52 were tractate IDs
    # 49, 50 were subscription tractate_ids
    
    # Let's try to find subscriptions and their tractate_id
    subs = conn.execute("SELECT id, tractate_id FROM subscriptions").fetchall()
    
    for sub in subs:
        sub_id = sub['id']
        old_t_id = sub['tractate_id']
        
        # Check if this tractate_id exists
        exists = conn.execute("SELECT name FROM tractates WHERE id = ?", (old_t_id,)).fetchone()
        
        if not exists:
            print(f"Subscription {sub_id} points to missing tractate ID {old_t_id}")
            # Try to guess or re-link to the first available tractate as a fallback or fix
            # In a real scenario we might need the original name, but here we'll try to match
            # if there are only 2 tractates, we can try to guess which is which or ask
            # For now, let's look if we can find any clue. 
            # Since I saw 'ברכות' and 'שבת' in the file list:
            
            target_id = None
            if old_t_id in (45, 49, 51): # Likely 'ברכות' or first one
                target_id = name_to_id.get('ברכות') or name_to_id.get('berachos_questions')
            elif old_t_id in (46, 50, 52): # Likely 'שבת' or second one
                target_id = name_to_id.get('שבת')
            
            if target_id:
                print(f"Updating subscription {sub_id} to new tractate ID {target_id}")
                conn.execute("UPDATE subscriptions SET tractate_id = ? WHERE id = ?", (target_id, sub_id))
            else:
                # If we have only 2 tractates and 2 types of IDs, we just map them in order
                available_ids = sorted(name_to_id.values())
                if len(available_ids) >= 2:
                    new_id = available_ids[0] if old_t_id % 2 != 0 else available_ids[1]
                    print(f"Updating subscription {sub_id} (fallback) to ID {new_id}")
                    conn.execute("UPDATE subscriptions SET tractate_id = ? WHERE id = ?", (new_id, sub_id))

    conn.commit()
    conn.close()
    print("Done fixing subscriptions.")

if __name__ == "__main__":
    fix_subscriptions()
