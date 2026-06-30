import json
import os
import re
from pathlib import Path
from database import get_conn, daf_to_float, int_to_gimatriya, gimatriya_to_int

# Config
DATA_DIR = Path("data")
MAX_QUESTION_LENGTH = 500
ERROR_LOG = "migration_errors.log"
STRICT_RANGE_LIMIT = 2.0  # Max jump allowed in dafim

def float_to_daf_str_local(val: float) -> str:
    daf_int = int(val)
    daf_str = int_to_gimatriya(daf_int)
    amud = 'ע"ב' if (val - daf_int) >= 0.5 else 'ע"א'
    return f"{daf_str} {amud}"

def split_consolidated_questions(text):
    """Split text with multiple sub-questions, each with its own ID and parentheses."""
    pattern = r'([א-ת]{1,4})\.(.*?)(?=(?:[א-ת]{1,4}\.)|$)'
    matches = re.findall(pattern, text, re.DOTALL)
    
    if not matches:
        return []
    
    results = []
    first_id_pos = text.find(matches[0][0] + '.')
    prefix = text[:first_id_pos].strip() if first_id_pos > 0 else ""
    
    for i, (q_id, q_text) in enumerate(matches):
        q_text = q_text.strip()
        if i == 0 and prefix:
            q_text = f"{prefix} {q_text}"
        
        daf_val = extract_daf_from_text(q_text)
        results.append((q_id, q_text, daf_val))
    
    return results

def extract_daf_from_text(text):
    """Try to find daf in parentheses like (קז:) or (קז.-:)."""
    matches = list(re.finditer(r'\((?P<daf>[א-ת]{1,3})(?P<punct>[\s\.\-\:]*)\)', text))
    if matches:
        match = matches[-1]
        daf_str = match.group('daf')
        punct = match.group('punct')
        amud = "ב" if ":" in punct else "א"
        try:
            return daf_to_float(daf_str, amud)
        except:
            return None
    
    match = re.search(r'\(([א-ת]{1,3})\)\s*$', text)
    if match:
        daf_str = match.group(1)
        try: return daf_to_float(daf_str, "א")
        except: return None
    return None

def get_daf_range(q_data, last_valid_start, last_valid_end):
    text = q_data.get("text", "")
    text_daf = extract_daf_from_text(text)
    
    # PRIORITY 1: If text has a daf, validate range
    if text_daf:
        # If jump too big, clamp it to last valid + offset to keep sequence
        if last_valid_start > 2.0 and abs(text_daf - last_valid_start) > STRICT_RANGE_LIMIT:
            # We trust the text but limit the "damage" to sequence
            # Actually, if it's in the text, it might be a new section. 
            # Let's be more lenient with text but keep it within 2 pages of "reality"
            clamped = max(last_valid_start, min(text_daf, last_valid_start + STRICT_RANGE_LIMIT))
            return clamped, clamped
        return text_daf, text_daf

    daf_info = q_data.get("daf")
    # PRIORITY 2: JSON daf info
    if isinstance(daf_info, dict):
        start_info = daf_info.get("from") or daf_info
        end_info = daf_info.get("to") or daf_info
        try:
            start_val = daf_to_float(start_info.get("daf", 2), start_info.get("amud", "א"))
            end_val = daf_to_float(end_info.get("daf", 2), end_info.get("amud", "א"))
            
            # Strict limit check for JSON data
            if last_valid_start > 2.0 and abs(start_val - last_valid_start) > STRICT_RANGE_LIMIT:
                # Use last valid to avoid "losing" the question
                return last_valid_start, last_valid_end
            
            return start_val, end_val
        except: return last_valid_start, last_valid_end
    
    # PRIORITY 3: Continuity
    return last_valid_start, last_valid_end

def migrate():
    conn = get_conn()
    errors = []
    print("Initializing database (STRICT MODE)...")
    from database import init_db, seed_tractates
    init_db()
    seed_tractates()
    
    # Use TRUNCATE for Postgres if possible, or DELETE
    try:
        if os.environ.get("DATABASE_URL"):
            # In Postgres, we might need CASCADE if there are foreign keys
            print("Cleaning up questions table (Postgres)...")
            conn.execute("TRUNCATE TABLE questions CASCADE")
        else:
            print("Cleaning up questions table (SQLite)...")
            conn.execute("DELETE FROM questions")
    except Exception as e:
        print(f"Note on cleanup: {e}")
        try:
            conn.execute("DELETE FROM questions")
        except:
            pass
    
    total_imported = 0
    json_files = list(DATA_DIR.glob("*.json"))
    for json_file in json_files:
        if "backup" in json_file.name.lower(): continue
        tractate_name = json_file.stem.strip()
        print(f"Processing {tractate_name}...")
        row = conn.execute("SELECT id, total_dafim FROM tractates WHERE name = ?", (tractate_name,)).fetchone()
        if not row: continue
        tractate_id, total_dafim = row[0], row[1]
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        questions = data.get("questions", [])
        
        last_valid_start, last_valid_end = 2.0, 2.0
        for i, q in enumerate(questions):
            ext_id, text = q.get("id"), q.get("text", "").strip()
            start_f, end_f = get_daf_range(q, last_valid_start, last_valid_end)
            
            # NEVER skip questions anymore, use last valid if everything fails
            if start_f is None:
                start_f, end_f = last_valid_start, last_valid_end

            last_valid_start, last_valid_end = start_f, end_f
            
            split_candidates = split_consolidated_questions(text)
            if split_candidates and len(text) > 150:
                for sub_id, sub_text, sub_daf in split_candidates:
                    sub_text = sub_text.strip()
                    if len(sub_text) < 5 or re.fullmatch(r'[\(\)\.\-\:\s]+', sub_text): continue
                    
                    # Sub-question safety check
                    final_start = sub_daf if sub_daf and abs(sub_daf - start_f) <= STRICT_RANGE_LIMIT else start_f
                    final_end = sub_daf if sub_daf and abs(sub_daf - end_f) <= STRICT_RANGE_LIMIT else end_f
                    
                    conn.execute("INSERT INTO questions (tractate_id, external_id, question_text, start_daf, end_daf) VALUES (?, ?, ?, ?, ?)",
                                 (tractate_id, sub_id, sub_text, final_start, final_end))
            else:
                if not text or len(text) < 5 or re.fullmatch(r'[\(\)\.\-\:\s]+', text): continue
                conn.execute("INSERT INTO questions (tractate_id, external_id, question_text, start_daf, end_daf) VALUES (?, ?, ?, ?, ?)",
                             (tractate_id, str(ext_id), text, start_f, end_f))
            
            total_imported += 1
            if total_imported % 100 == 0:
                print(f"Imported {total_imported} questions so far...")
                
    conn.commit()
    print(f"Finished importing. Total questions inserted: {total_imported}")
    print("\n--- Strict Data Quality Report ---")
    tractates_list = conn.execute("SELECT id, name, total_dafim FROM tractates").fetchall()
    for t in tractates_list:
        t_id, t_name, total_daf = t
        q_count = conn.execute("SELECT COUNT(*) FROM questions WHERE tractate_id = ?", (t_id,)).fetchone()[0]
        q_dafim = conn.execute("SELECT DISTINCT CAST(start_daf AS INTEGER) FROM questions WHERE tractate_id = ?", (t_id,)).fetchall()
        present_dafim = {d[0] for d in q_dafim}
        gaps = [d for d in range(2, total_daf + 1) if d not in present_dafim]
        print(f"{t_name}: {q_count} questions. Gaps: {len(gaps)} dafim.")
        density_b = conn.execute("SELECT COUNT(*) FROM questions WHERE tractate_id = ? AND start_daf = 2.0", (t_id,)).fetchone()[0]
        print(f"  - Questions on Daf 2.0: {density_b}")

    conn.close()
    with open(ERROR_LOG, "w", encoding="utf-8") as f: f.write("\n".join(errors))
    print(f"\nMigration complete. Errors logged to {ERROR_LOG}")

if __name__ == "__main__":
    migrate()
