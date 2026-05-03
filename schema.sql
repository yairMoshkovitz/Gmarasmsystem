-- Gemara SMS Learning System Schema

CREATE TABLE IF NOT EXISTS tractates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- e.g. "שבת"
    json_path TEXT NOT NULL,            -- path to questions JSON
    total_dafim INTEGER NOT NULL DEFAULT 157
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    last_name TEXT,
    city TEXT,
    age INTEGER,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    last_response_at TIMESTAMP,         -- last time user responded
    inactive_notified INTEGER DEFAULT 0 -- whether we warned them
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    tractate_id INTEGER NOT NULL REFERENCES tractates(id),
    start_daf INTEGER NOT NULL DEFAULT 2,  -- starting daf (usually 2)
    end_daf INTEGER NOT NULL,              -- ending daf
    current_daf REAL NOT NULL DEFAULT 2.0, -- current position (2.0=2a, 2.5=2b)
    dafim_per_day REAL NOT NULL DEFAULT 1.0, -- 0.5, 1, 2 etc
    send_hour INTEGER NOT NULL DEFAULT 8,   -- hour to send (0-23)
    is_active INTEGER DEFAULT 1,
    pause_until DATE,                      -- date until which the subscription is paused
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sent_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
    question_id TEXT NOT NULL,           -- question "id" from JSON (א, ב, ...)
    question_text TEXT NOT NULL,
    daf_from TEXT,
    daf_to TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    response_text TEXT
);

CREATE TABLE IF NOT EXISTS sms_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    phone TEXT NOT NULL,
    direction TEXT NOT NULL,             -- 'out' or 'in'
    message TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sms_templates (
    key TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
