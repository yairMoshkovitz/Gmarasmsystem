
import sys
from scheduler import format_sub_status
from database import get_conn, daf_to_float
from tests.helpers import create_user_with_subscription

def reproduce():
    phone = "0511111111"
    # Registration: ברכות ב ע"א עד יד ע"ב, קצב 8 דפים ליום
    tractate = "ברכות"
    start_daf = "ב ע\"א" # 2.0
    end_daf = "יד ע\"ב"  # 14.5
    dafim_per_day = 8.0
    
    user_id, sub_id = create_user_with_subscription(phone, "BugRepro", tractate)
    
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET start_daf=?, end_daf=?, current_daf=?, dafim_per_day=? WHERE id=?",
                 (daf_to_float("ב", "ע\"א"), daf_to_float("יד", "ע\"ב"), daf_to_float("ב", "ע\"א"), dafim_per_day, sub_id))
    conn.commit()
    
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub_id,)).fetchone()
    sub_dict = dict(sub)
    conn.close()

    print("\n--- Test Scenario 1: rate 8.0, current 2.0, end 14.5 ---")
    
    print(f"Sub: {sub_dict['tractate_name']} {sub_dict['start_daf']} to {sub_dict['end_daf']}, rate: {sub_dict['dafim_per_day']}")
    
    status = format_sub_status(sub_dict)
    print("\nGenerated Status Message:")
    print("-" * 20)
    print(status)
    print("-" * 20)
    
    # User's log says:
    # ברכות (ב ע"א - טו ע"א): הלימוד מחר יהיה י ע"א עד טו ע"א
    # Expected for 8 pages:
    # 2.0 study today (2.0 to 9.5)
    # Tomorrow: 10.0 to 14.5 (since it ends at 14.5)
    
    if "טו ע\"א" in status:
        print("\n❌ BUG REPRODUCED: Found 'טו ע\"א' (15.0) in status while end_daf is 14.5 (יד ע\"ב)")
    else:
        print("\n✅ Bug not reproduced with Scenario 1.")

    print("\n--- Test Scenario 2: rate 6.0, current 12.0, end 14.5 ---")
    sub_dict["current_daf"] = 12.0
    sub_dict["dafim_per_day"] = 6.0
    sub_dict["end_daf"] = 14.5
    status = format_sub_status(sub_dict)
    print("\nGenerated Status Message:")
    print("-" * 20)
    print(status)
    print("-" * 20)
    if "יח ע\"א" in status:
         print("\n❌ BUG REPRODUCED: Found 'יח ע\"א' (18.0) in status while end_daf is 14.5 (יד ע\"ב)")
    else:
        print("\n✅ Bug not reproduced with Scenario 2.")

    print("\n--- Test Scenario 3: rate 8.0, current 10.0, end 14.5 (Should show Tomorrow Finish) ---")
    sub_dict["current_daf"] = 10.0 # Just finished Daf 10 to 17? No, current is 10.0
    # Wait, if current is 10, next_start is 18... No.
    # If today's study was 2.0 to 9.5 (current was 2.0).
    # Then next_start is 10.0.
    sub_dict["current_daf"] = 2.0
    sub_dict["dafim_per_day"] = 8.0
    sub_dict["end_daf"] = 14.5
    status = format_sub_status(sub_dict)
    print("\nGenerated Status Message:")
    print("-" * 20)
    print(status)
    print("-" * 20)
    if "יח ע\"א" in status:
         print("\n❌ BUG REPRODUCED: Found 'יח ע\"א' (18.0) in status while end_daf is 14.5 (יד ע\"ב)")
    else:
        print("\n✅ Bug not reproduced with Scenario 2.")

if __name__ == "__main__":
    reproduce()
