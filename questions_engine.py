"""
questions_engine.py - Selects relevant questions based on current daf position
"""
from database import get_conn, load_questions, daf_to_float
import random


def get_daf_range_for_question(q: dict) -> tuple[float, float]:
    """
    Parse the daf range a question covers.
    Returns (start_float, end_float).
    """
    daf_info = q.get("daf") or {}
    if not daf_info:
        return (2.0, 2.0)

    if isinstance(daf_info, dict):
        # Check if it has from/to structure
        if "from" in daf_info and "to" in daf_info:
            frm = daf_info["from"]
            to = daf_info["to"]
            start = daf_to_float(frm.get("daf", 2), frm.get("amud"))
            end = daf_to_float(to.get("daf", 2), to.get("amud"))
            return (start, end)
        else:
            # Single daf
            d = daf_info.get("daf", 2)
            amud = daf_info.get("amud")
            val = daf_to_float(d, amud)
            # If no amud, covers both sides
            if amud is None:
                return (val, val + 0.5)
            return (val, val)
    return (2.0, 2.0)


def select_questions_for_range(
    tractate_id: int,
    current_daf: float,
    dafim_per_day: float,
    count: int = 2,
    already_sent: list[str] = None,
) -> list[dict]:
    """
    Select `count` questions that fall within today's learning range.

    Range = [current_daf, current_daf + dafim_per_day)
    Prefers questions not yet sent; falls back to any in range.
    """
    all_questions = load_questions(tractate_id)
    if not all_questions:
        return []

    already_sent = set(already_sent or [])
    end_daf = current_daf + dafim_per_day

    # Filter questions that overlap with today's range
    in_range = []
    for q in all_questions:
        q_start, q_end = get_daf_range_for_question(q)
        # Overlap: question starts before our end AND question ends after our start
        if q_start < end_daf and q_end >= current_daf:
            in_range.append(q)

    if not in_range:
        # Fallback: questions closest to current position
        def proximity(q):
            s, e = get_daf_range_for_question(q)
            return abs(s - current_daf)
        in_range = sorted(all_questions, key=proximity)[:max(count * 3, 6)]

    # Prefer unsent questions
    unsent = [q for q in in_range if q["id"] not in already_sent]
    pool = unsent if len(unsent) >= count else in_range

    # Random sample
    if len(pool) <= count:
        return pool
    return random.sample(pool, count)


def get_already_sent_ids(user_id: int, subscription_id: int) -> list[str]:
    """Return question IDs already sent to this user for this subscription."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT question_id FROM sent_questions WHERE user_id=? AND subscription_id=?",
        (user_id, subscription_id),
    ).fetchall()
    conn.close()
    return [r["question_id"] for r in rows]


def format_question_sms(q: dict, index: int, tractate_name: str) -> str:
    """Format a question as an SMS message."""
    daf_info = q.get("daf") or {}
    daf_str = ""
    if isinstance(daf_info, dict):
        if "from" in daf_info:
            frm = daf_info["from"]
            to = daf_info.get("to", frm)
            daf_str = f"(דף {frm.get('daf','')} - דף {to.get('daf','')})"
        elif daf_info.get("daf"):
            amud = daf_info.get("amud", "")
            amud_str = f" עמ' {amud}" if amud else ""
            daf_str = f"(דף {daf_info['daf']}{amud_str})"

    header = f"📚 {tractate_name} {daf_str}\nשאלה {index}:"
    message = f"{header}\n{q['text']}"
    
    # Cost saving: Clean up English characters and excessive whitespace
    # We want "Hebrew only" content for the SMS body as requested.
    # Keep numbers, Hebrew, and basic punctuation.
    cleaned_message = "".join([c for c in message if not ('a' <= c.lower() <= 'z')])
    # Remove multiple spaces
    cleaned_message = " ".join(cleaned_message.split())
    
    return cleaned_message
