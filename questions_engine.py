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
    max_questions: int = 2
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
        SELECT id, external_id, question_text as text, start_daf, end_daf
        FROM questions
        WHERE tractate_id = ?
        AND start_daf <= ? AND end_daf >= ?
    """
    params = [tractate_id, end_f, start_f]
    
    if already_sent_ids:
        query += f" AND external_id NOT IN ({placeholders})"
        params.extend(already_sent_ids)
        
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    eligible = [dict(row) for row in rows]
    random.shuffle(eligible)
    return eligible[:max_questions]


@log_function_entry
def get_already_sent_ids(user_id: int, subscription_id: int) -> list[str]:
    """Get list of question IDs already sent to this subscription."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT question_id FROM sent_questions WHERE user_id=? AND subscription_id=?",
        (user_id, subscription_id)
    ).fetchall()
    conn.close()
    return [str(row["question_id"]) for row in rows]


@log_function_entry
def format_question_sms(q: dict, index: int, tractate_name: str, is_last: bool = False) -> str:
    """Format a question into an SMS message using template."""
    # Use start_daf from DB if available, else fallback
    q_start = q.get("start_daf")
    if q_start is None:
        q_start, _ = get_daf_range_for_question(q)
        
    daf_str = float_to_daf_str(q_start)
    
    template_name = "question_format_last" if is_last else "question_format"
    
    return get_template(
        template_name,
        tractate=tractate_name,
        daf=daf_str,
        question=q.get("text") or q.get("question") or ""
    )
