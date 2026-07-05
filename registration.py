"""
registration.py - User registration and subscription management
"""
from database import get_conn, daf_to_float, float_to_daf_str
from sms_service import send_sms
from datetime import datetime
import json
import os
from logging_config import get_logger, log_function_entry

logger = get_logger(__name__)

_template_cache = {}

# Comprehensive list of all Shas tractates
ALL_SHAS_TRACTATES = [
    # Zeraim
    "ברכות", "פאה", "דמאי", "כלאים", "שביעית", "תרומות", "מעשרות", "מעשר שני", "חלה", "ערלה", "ביכורים",
    # Moed
    "שבת", "עירובין", "פסחים", "שקלים", "יומא", "סוכה", "ביצה", "ראש השנה", "תענית", "מגילה", "מועד קטן", "חגיגה",
    # Nashim
    "יבמות", "כתובות", "נדרים", "נזיר", "סוטה", "גיטין", "קידושין",
    # Nezikin
    "בבא קמא", "בבא מציעא", "בבא בתרא", "סנהדרין", "מכות", "שבועות", "עדיות", "עבודה זרה", "אבות", "הוריות",
    # Kodashim
    "זבחים", "מנחות", "חולין", "בכורות", "ערכין", "תמורה", "כריתות", "מעילה", "תמיד", "מידות", "קינים",
    # Tahorot
    "כלים", "אהלות", "נגעים", "פרה", "טהרות", "מקואות", "נדה", "מכשירין", "זבים", "טבול יום", "ידיים", "עוקצים"
]

@log_function_entry
def get_template(template_name_pos=None, **kwargs):
    # Use a unique name for the first argument to avoid collisions with kwargs like 'name'
    template_name = kwargs.pop('template_name', template_name_pos)
    
    logger.info(f"📝 Loading template: '{template_name}' with params: {list(kwargs.keys())}")
    
    global _template_cache
    
    # 1. Check cache first
    template_content = _template_cache.get(template_name)
    
    if not template_content:
        try:
            # 2. Try DB
            conn = get_conn()
            row = conn.execute("SELECT content FROM sms_templates WHERE key = ?", (template_name,)).fetchone()
            conn.close()
            
            if row:
                template_content = row["content"]
                _template_cache[template_name] = template_content
                logger.debug(f"Template '{template_name}' loaded from DB")
            else:
                # 3. Fallback to JSON
                template_path = os.path.join(os.path.dirname(__file__), "sms_templates.json")
                if os.path.exists(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        templates = json.load(f)
                    template_content = templates.get(template_name, "")
                    if template_content:
                        _template_cache[template_name] = template_content
                        logger.debug(f"Template '{template_name}' loaded from JSON")
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {e}")
            print(f"Error loading template {template_name}: {e}")
            
    if not template_content:
        logger.warning(f"Template '{template_name}' not found!")
        return f"Template {template_name} not found"
        
    try:
        formatted_content = template_content.format(**kwargs)
        
        # Auto-append menu_footer for relevant templates
        footer_templates = [
            "ask_update_daf", "ask_pause_days", "ask_new_hour", 
            "unregistered_instructions", "registration_step_2_instructions",
            "choose_subscription_update_daf", "choose_subscription_pause",
            "choose_subscription_hour", "choose_subscription_unsubscribe",
            "choose_subscription_resume", "error_parsing_registration",
            "tractate_not_found", "tractate_not_supported"
        ]
        
        if template_name in footer_templates:
            footer = get_template("menu_footer")
            if footer and "Template menu_footer not found" not in footer:
                formatted_content += footer
        
        logger.debug(f"Template '{template_name}' formatted successfully (length: {len(formatted_content)})")
        return formatted_content
    except Exception as e:
        logger.error(f"Template {template_name} format error: {e}")
        return f"Template {template_name} format error: {e}"

@log_function_entry
def clear_template_cache():
    global _template_cache
    _template_cache = {}

@log_function_entry
def register_user(phone: str, name: str, last_name: str = None, city: str = None, age: int = None) -> int:
    """Register a new user. Returns user_id."""
    conn = get_conn()

    existing = conn.execute(
        "SELECT id FROM users WHERE phone=?", (phone,)
    ).fetchone()

    if existing:
        # Update details if provided
        if last_name or city or age:
            conn.execute(
                "UPDATE users SET name=?, last_name=?, city=?, age=? WHERE phone=?",
                (name, last_name, city, age, phone)
            )
            conn.commit()
        conn.close()
        return existing["id"]

    conn.execute(
        "INSERT INTO users (phone, name, last_name, city, age, last_response_at) VALUES (?,?,?,?,?,?)",
        (phone, name, last_name, city, age, datetime.now().isoformat()),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    try:
        print(f"Registered user: {name} ({phone}) -> ID {user_id}")
    except UnicodeEncodeError:
        print(f"Registered user ID {user_id}")
    return user_id


@log_function_entry
def get_all_tractates() -> list:
    """Return all registered tractates."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tractates ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@log_function_entry
def find_tractate_by_name(input_name: str):
    """
    Finds a tractate by name, supporting prefixes and 'מסכת' prefix.
    Checks against the full Shas list first.
    Returns (tractate_dict_or_name_str, matched_text, is_in_db) 
    """
    clean_input = input_name.strip().replace("מסכת ", "").replace("מסכת", "").strip()
    
    # 1. Check against full Shas list (Hardcoded)
    # Sort by length descending to match longer names first
    shas_list = sorted(ALL_SHAS_TRACTATES, key=len, reverse=True)
    
    matched_shas_name = None
    for name in shas_list:
        if clean_input.startswith(name):
            matched_shas_name = name
            break
            
    if not matched_shas_name:
        return None, None, False
        
    # 2. Check if it's in the DB
    db_tractates = get_all_tractates()
    db_match = next((t for t in db_tractates if t['name'].strip() == matched_shas_name), None)
    
    if db_match:
        return db_match, matched_shas_name, True
    else:
        return matched_shas_name, matched_shas_name, False

@log_function_entry
def subscribe(
    user_id: int,
    tractate_id: int,
    start_daf: float,      # Float value (e.g. 2.0, 2.5)
    end_daf: float,        # Float value
    rate: float,           # 0.5, 1, 2 etc
    hour: int,             # 0-23
    question_type: str = 'all' # 'all' or 'rashi_only'
) -> int:
    """Subscribe a user to a tractate learning schedule."""
    conn = get_conn()

    # Validate tractate
    tractate = conn.execute(
        "SELECT * FROM tractates WHERE id=?", (tractate_id,)
    ).fetchone()
    if not tractate:
        conn.close()
        raise ValueError(f"Tractate ID {tractate_id} not found.")

    # Check for existing subscription with same tractate and range
    existing = conn.execute(
        "SELECT id FROM subscriptions WHERE user_id=? AND tractate_id=? AND start_daf=? AND end_daf=? AND is_active=1",
        (user_id, tractate_id, int(start_daf), end_daf),
    ).fetchone()

    if existing:
        # Update existing instead of creating new
        conn.execute(
            "UPDATE subscriptions SET current_daf=?, dafim_per_day=?, send_hour=?, question_type=? WHERE id=?",
            (start_daf, rate, hour, question_type, existing["id"]),
        )
        sub_id = existing["id"]
    else:
        # Limit to 5 active subscriptions
        count = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id=? AND is_active=1", (user_id,)).fetchone()[0]
        if count >= 5:
            conn.close()
            raise ValueError("ניתן להירשם לעד 5 מסכתות במקביל.")

        conn.execute(
            """
            INSERT INTO subscriptions
              (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, question_type, is_active)
            VALUES (?,?,?,?,?,?,?,?,1)
            """,
            (user_id, tractate_id, int(start_daf), end_daf, start_daf, rate, hour, question_type),
        )
        sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    try:
        print(f"Subscription #{sub_id}: User {user_id} -> {tractate['name']} daf {start_daf}-{end_daf}")
    except:
        print(f"Subscription #{sub_id} created")
    return sub_id


@log_function_entry
def unsubscribe(user_id: int, tractate_id: int):
    """Deactivate a subscription."""
    conn = get_conn()
    conn.execute(
        "UPDATE subscriptions SET is_active=0 WHERE user_id=? AND tractate_id=?",
        (user_id, tractate_id),
    )
    conn.commit()
    conn.close()
    print(f"Unsubscribed user {user_id} from tractate {tractate_id}.")


@log_function_entry
def get_user_subscriptions(user_id: int) -> list:
    """Return active subscriptions for a user."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.*, t.name as tractate_name, u.phone, u.name
        FROM subscriptions s
        JOIN tractates t ON s.tractate_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.user_id=? AND s.is_active=1
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
