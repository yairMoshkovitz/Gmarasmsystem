"""
questions_engine.py - Question selection and formatting
"""
import json
import random
from database import get_conn, daf_to_float, float_to_daf_str
from registration import get_template
from logging_config import get_logger, log_function_entry

logger = get_logger(__name__)

@log_function_entry
def get_daf_range_for_question(q: dict) -> tuple[float, float]:
    """Extract start and end daf as floats from a question dict."""
    daf_info = q.get("daf")
    if not daf_info:
        return (0.0, 0.0)

    if isinstance(daf_info, dict):
        start_info = daf_info.get("from") or daf_info
        end_info = daf_info.get("to") or daf_info
        
        start_val = daf_to_float(start_info.get("daf"), start_info.get("amud"))
        end_val = daf_to_float(end_info.get("daf"), end_info.get("amud"))
        return (start_val, end_val)
    elif isinstance(daf_info, str):
        val = daf_to_float(daf_info)
        return (val, val)
    return (0.0, 0.0)


@log_function_entry
def select_questions_for_range(
    tractate_id: int, start_f: float, end_f: float, already_sent_ids: list,
    max_questions: int = 2, question_type_pref: str = 'all'
) -> list:
    """Filter questions that overlap with the given daf range and haven't been sent."""
    conn = get_conn()
    
    # query explanation:
    # 1. tractate_id filter
    # 2. Overlap check: max(start_f, q_start) <= min(end_f, q_end)
    #    translated to SQL: q_start <= end_f AND q_end >= start_f
    # 3. ID filter
    
    placeholders = ",".join(["?"] * len(already_sent_ids))
    query = f"""
        SELECT id, external_id, question_text as text, question_type, start_daf, end_daf
        FROM questions
        WHERE tractate_id = ?
        AND start_daf <= ? AND end_daf >= ?
    """
    
    # Debug: show what we are filtering
    if already_sent_ids:
        logger.debug(f"Filtering out already sent questions: {already_sent_ids}")

    params = [tractate_id, end_f, start_f]
    
    if question_type_pref == 'rashi_only':
        # Escape % for Postgres if necessary, but database.py might handle it.
        # Actually, let's use a placeholder to be safe and avoid % issues.
        query += " AND (question_type IS NULL OR question_type NOT LIKE ?)"
        params.append('%תוס%')
    
    if already_sent_ids:
        query += f" AND external_id NOT IN ({placeholders})"
        params.extend(already_sent_ids)
        
    rows = conn.execute(query, params).fetchall()
    conn.close()

    eligible = [dict(row) for row in rows]
    
    if eligible:
        logger.info(f"Found {len(eligible)} eligible questions for tractate {tractate_id} in range {start_f}-{end_f}")
        for q in eligible:
            logger.debug(f"  - Question: DB_ID={q['id']}, EXT_ID={q['external_id']}, Type={q['question_type']}, Text={q['text'][:30]}...")
    else:
        logger.info(f"No eligible questions found for tractate {tractate_id} in range {start_f}-{end_f}")

    random.shuffle(eligible)
    return eligible[:max_questions]


@log_function_entry
def get_already_sent_ids(user_id: int, subscription_id: int) -> list[str]:
    """Get list of question IDs already sent to this subscription."""
    conn = get_conn()
    # We need both the question_id (which might be external_id now) AND we should check
    # if it was an internal ID before the fix.
    rows = conn.execute(
        "SELECT question_id FROM sent_questions WHERE user_id=? AND subscription_id=?",
        (user_id, subscription_id)
    ).fetchall()
    conn.close()
    
    ids = []
    for row in rows:
        val = row["question_id"]
        if val:
            ids.append(str(val).strip())
    
    return ids


@log_function_entry
def format_question_sms(q: dict, index: int, tractate_name: str, is_last: bool = False) -> str:
    """Format a question into an SMS message using template."""
    # Use start_daf from DB if available, else fallback
    q_start = q.get("start_daf")
    if q_start is None:
        q_start, _ = get_daf_range_for_question(q)
        
    daf_str = float_to_daf_str(q_start)
    
    template_name = "question_format_last" if is_last else "question_format"
    
    q_type = q.get("question_type", "")
    label = f"[{q_type}] " if q_type else ""
    question_text = label + (q.get("text") or q.get("question") or "")

    return get_template(
        template_name,
        tractate=tractate_name,
        daf=daf_str,
        question=question_text
    )
