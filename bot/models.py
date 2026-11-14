import json
from bot.db import get_db, fetchone, fetchall, execute
from bot.config import OWNER_IDS, TECH_ADMIN_IDS, STATUS_ROLES

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    role TEXT NOT NULL DEFAULT 'member',
    has_vip INTEGER NOT NULL DEFAULT 0,
    has_blat INTEGER NOT NULL DEFAULT 0,
    has_partner INTEGER NOT NULL DEFAULT 0,
    demoted_before INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rules (
    code TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    duration_sec INTEGER,
    duration_text TEXT,
    critical INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    recurrence_action TEXT,
    recurrence_sec INTEGER,
    recurrence_text TEXT,
    special TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    chat_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    target_id INTEGER,
    action TEXT NOT NULL,
    rule_code TEXT,
    reason TEXT,
    duration_sec INTEGER,
    chat_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    rule_code TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pending_deletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    delete_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_fsm (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    expire_at TEXT NOT NULL
);
"""

async def init_db():
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()
    await db.close()
    for oid in OWNER_IDS:
        await execute("INSERT INTO users (telegram_id, role) VALUES (?, 'owner') "
                      "ON CONFLICT(telegram_id) DO UPDATE SET role='owner'", (oid,))
    for tid in TECH_ADMIN_IDS:
        await execute("INSERT INTO users (telegram_id, role) VALUES (?, 'tech_admin') "
                      "ON CONFLICT(telegram_id) DO UPDATE SET role='tech_admin'", (tid,))

async def get_user(tg_id):
    row = await fetchone("SELECT * FROM users WHERE telegram_id=?", (tg_id,))
    if not row:
        await execute("INSERT INTO users (telegram_id, role) VALUES (?, 'member')", (tg_id,))
        row = await fetchone("SELECT * FROM users WHERE telegram_id=?", (tg_id,))
    return row

async def set_user_role(tg_id, new_role):
    user = await get_user(tg_id)
    # статусная роль — ставим флаг
    if new_role in STATUS_ROLES:
        await execute(f"UPDATE users SET has_{new_role}=1 WHERE telegram_id=?", (tg_id,))
    # снятие с должности — возврат статуса по флагу
    if new_role == "member":
        if user["has_blat"]:
            new_role = "blat"
        elif user["has_partner"]:
            new_role = "partner"
        elif user["has_vip"]:
            new_role = "vip"
    await execute("UPDATE users SET role=?, updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                  (new_role, tg_id))

async def update_username(tg_id, username):
    await get_user(tg_id)
    await execute("UPDATE users SET username=? WHERE telegram_id=?", (username, tg_id))

async def get_rule(code):
    return await fetchone("SELECT * FROM rules WHERE code=?", (code,))

async def get_all_rules():
    return await fetchall("SELECT * FROM rules ORDER BY code")

async def add_rule(code, text, duration_sec, duration_text, critical, recurrence_action, recurrence_sec, recurrence_text, special=None):
    await execute(
        """INSERT OR REPLACE INTO rules
           (code, text, duration_sec, duration_text, critical, active,
            recurrence_action, recurrence_sec, recurrence_text, special)
           VALUES (?, ?, ?, ?, ?, COALESCE((SELECT active FROM rules WHERE code=?), 1), ?, ?, ?, ?)""",
        (code, text, duration_sec, duration_text, critical, code,
         recurrence_action, recurrence_sec, recurrence_text, special))

async def set_rule_active(code, active):
    await execute("UPDATE rules SET active=? WHERE code=?", (active, code))

async def set_rule_critical(code, critical):
    await execute("UPDATE rules SET critical=? WHERE code=?", (critical, code))

async def delete_rule(code):
    await execute("DELETE FROM rules WHERE code=?", (code,))

async def add_warn(user_id, moderator_id, reason, chat_id=None):
    await execute("INSERT INTO warns (user_id, moderator_id, reason, chat_id) VALUES (?, ?, ?, ?)",
                  (user_id, moderator_id, reason, chat_id))

async def count_warns(user_id, days=None):
    if days:
        row = await fetchone(
            "SELECT COUNT(*) as c FROM warns WHERE user_id=? AND created_at > datetime('now', ?)",
            (user_id, f"-{days} days"))
    else:
        row = await fetchone("SELECT COUNT(*) as c FROM warns WHERE user_id=?", (user_id,))
    return row["c"] if row else 0

async def count_warns_chat(user_id, chat_id, days=None):
    if days:
        row = await fetchone(
            "SELECT COUNT(*) as c FROM warns WHERE user_id=? AND chat_id=? AND created_at > datetime('now', ?)",
            (user_id, chat_id, f"-{days} days"))
    else:
        row = await fetchone("SELECT COUNT(*) as c FROM warns WHERE user_id=? AND chat_id=?",
                             (user_id, chat_id))
    return row["c"] if row else 0

async def get_warns(user_id, days=30):
    return await fetchall(
        "SELECT * FROM warns WHERE user_id=? AND created_at > datetime('now', ?) ORDER BY created_at DESC",
        (user_id, f"-{days} days"))

async def clear_warns(user_id):
    await execute("DELETE FROM warns WHERE user_id=?", (user_id,))

async def add_log(actor_id, target_id, action, rule_code=None, reason=None, duration_sec=None, chat_id=None):
    await execute(
        "INSERT INTO logs (actor_id, target_id, action, rule_code, reason, duration_sec, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (actor_id, target_id, action, rule_code, reason, duration_sec, chat_id))

async def has_recurrence(user_id, rule_code, chat_id=None, days=30):
    if chat_id:
        row = await fetchone(
            """SELECT id FROM logs
               WHERE target_id=? AND rule_code=? AND chat_id=?
                 AND action IN ('mute','warn','kick','ban')
                 AND created_at > datetime('now', ?)
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, rule_code, chat_id, f"-{days} days"))
    else:
        row = await fetchone(
            """SELECT id FROM logs
               WHERE target_id=? AND rule_code=?
                 AND action IN ('mute','warn','kick','ban')
                 AND created_at > datetime('now', ?)
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, rule_code, f"-{days} days"))
    return row is not None

async def create_application(applicant_id, target_id, chat_id, action, rule_code, reason):
    await execute(
        "INSERT INTO applications (applicant_id, target_id, chat_id, action, rule_code, reason) VALUES (?, ?, ?, ?, ?, ?)",
        (applicant_id, target_id, chat_id, action, rule_code, reason))
    row = await fetchone("SELECT last_insert_rowid() as id")
    return row["id"]

async def get_application(app_id):
    return await fetchone("SELECT * FROM applications WHERE id=?", (app_id,))

async def set_application_status(app_id, status, reviewed_by):
    await execute("UPDATE applications SET status=?, reviewed_by=? WHERE id=?", (status, reviewed_by, app_id))

async def schedule_delete(chat_id, message_id, delete_at):
    await execute("INSERT INTO pending_deletes (chat_id, message_id, delete_at) VALUES (?, ?, ?)",
                  (chat_id, message_id, delete_at))

async def get_due_deletes():
    return await fetchall("SELECT * FROM pending_deletes WHERE delete_at <= datetime('now')")

async def delete_pending(pk):
    await execute("DELETE FROM pending_deletes WHERE id=?", (pk,))

async def save_pending_fsm(kind, user_id, chat_id, payload, expire_at):
    await execute("INSERT INTO pending_fsm (kind, user_id, chat_id, payload, expire_at) VALUES (?, ?, ?, ?, ?)",
                  (kind, user_id, chat_id, json.dumps(payload), expire_at))

async def get_expired_fsm(kind):
    return await fetchall("SELECT * FROM pending_fsm WHERE kind=? AND expire_at <= datetime('now')", (kind,))

async def get_active_fsm(kind, user_id):
    return await fetchone("SELECT * FROM pending_fsm WHERE kind=? AND user_id=? ORDER BY id DESC LIMIT 1",
                          (kind, user_id))

async def delete_fsm(pk):
    await execute("DELETE FROM pending_fsm WHERE id=?", (pk,))