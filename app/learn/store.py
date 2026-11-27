"""SQLite storage: users, sessions, invites, enrollments, progress, questions."""
import sqlite3
import time
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL DEFAULT '',
    pw_hash     TEXT,                       -- NULL until the invite is used
    is_admin    INTEGER NOT NULL DEFAULT 0,
    totp_secret TEXT,
    totp_step   INTEGER NOT NULL DEFAULT 0, -- last accepted TOTP step (no replay)
    disabled    INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    last_login  INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf        TEXT NOT NULL,
    stage       TEXT NOT NULL DEFAULT 'ok', -- 'totp' = password ok, waiting for the code
    expires_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (            -- for the account-sharing signals
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    at          INTEGER NOT NULL,
    kind        TEXT NOT NULL,              -- login | evicted | takeover | blocked
    ip          TEXT NOT NULL DEFAULT '',
    device      TEXT NOT NULL DEFAULT ''    -- e.g. "Chrome on Windows"
);
CREATE INDEX IF NOT EXISTS events_user_at ON events (user_id, at);
CREATE TABLE IF NOT EXISTS playback (           -- one video at a time per account
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    session     TEXT NOT NULL,              -- token_hash of the session that plays
    device      TEXT NOT NULL DEFAULT '',
    updated_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course      TEXT NOT NULL,              -- course folder name
    expires_at  INTEGER,                    -- NULL = no end date
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (user_id, course)
);
CREATE TABLE IF NOT EXISTS progress (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course      TEXT NOT NULL,
    lesson      TEXT NOT NULL,              -- path of the video inside the course folder
    position    REAL NOT NULL DEFAULT 0,
    duration    REAL NOT NULL DEFAULT 0,
    completed   INTEGER NOT NULL DEFAULT 0,
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (user_id, course, lesson)
);
CREATE TABLE IF NOT EXISTS durations (         -- video lengths read from the MP4 headers
    course      TEXT NOT NULL,
    path        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    mtime       INTEGER NOT NULL,
    seconds     REAL,                       -- NULL = header unreadable
    PRIMARY KEY (course, path)
);
CREATE TABLE IF NOT EXISTS questions (         -- asked under a video, answered by the trainer
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course       TEXT NOT NULL,
    lesson       TEXT NOT NULL,             -- path of the video inside the course folder
    lesson_id    TEXT NOT NULL,
    course_title TEXT NOT NULL DEFAULT '',  -- titles when asked (shown even if the files move)
    lesson_title TEXT NOT NULL DEFAULT '',
    position     REAL NOT NULL DEFAULT 0,   -- video time (s) when the question was asked
    body         TEXT NOT NULL,
    created_at   INTEGER NOT NULL,
    trainer_mail TEXT NOT NULL DEFAULT '',  -- '' sending | sent | off | error: ...
    answer       TEXT,
    answered_at  INTEGER,
    answer_mail  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS questions_user ON questions (user_id, course, lesson);
CREATE INDEX IF NOT EXISTS questions_open ON questions (answered_at, created_at);
"""


def connect():
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextmanager
def db():
    con = connect()
    try:
        with con:
            yield con
    finally:
        con.close()


# Columns added after the first release: (table, column, definition).
MIGRATIONS = [
    ("sessions", "created_at", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "last_seen", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "ip", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "device", "TEXT NOT NULL DEFAULT ''"),
]


def init():
    with db() as c:
        c.executescript(SCHEMA)
        for table, col, definition in MIGRATIONS:
            if col not in {r["name"] for r in c.execute("PRAGMA table_info(%s)" % table)}:
                c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, definition))


def now():
    return int(time.time())


# --- users ---------------------------------------------------------------------
def user_by_email(c, email):
    return c.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def user_by_id(c, uid):
    return c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def create_user(c, email, name="", is_admin=False, pw_hash=None, totp_secret=None):
    cur = c.execute(
        "INSERT INTO users (email, name, is_admin, pw_hash, totp_secret, created_at) VALUES (?,?,?,?,?,?)",
        (email.strip().lower(), name.strip(), int(is_admin), pw_hash, totp_secret, now()))
    return cur.lastrowid


def students(c):
    return c.execute("SELECT * FROM users WHERE is_admin = 0 ORDER BY email").fetchall()


# --- enrollments ---------------------------------------------------------------
def enrollments(c, uid):
    return c.execute("SELECT * FROM enrollments WHERE user_id = ? ORDER BY course", (uid,)).fetchall()


def active_courses(c, uid):
    """Course folder names this user may watch right now."""
    rows = c.execute("SELECT course FROM enrollments WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)",
                     (uid, now())).fetchall()
    return {r["course"] for r in rows}


def set_enrollment(c, uid, course, expires_at):
    c.execute("INSERT INTO enrollments (user_id, course, expires_at, created_at) VALUES (?,?,?,?) "
              "ON CONFLICT (user_id, course) DO UPDATE SET expires_at = excluded.expires_at",
              (uid, course, expires_at, now()))


def remove_enrollment(c, uid, course):
    c.execute("DELETE FROM enrollments WHERE user_id = ? AND course = ?", (uid, course))


# --- progress ------------------------------------------------------------------
def progress_map(c, uid, course):
    rows = c.execute("SELECT * FROM progress WHERE user_id = ? AND course = ?", (uid, course)).fetchall()
    return {r["lesson"]: r for r in rows}


def save_progress(c, uid, course, lesson, position, duration, completed):
    c.execute(
        "INSERT INTO progress (user_id, course, lesson, position, duration, completed, updated_at) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT (user_id, course, lesson) DO UPDATE SET "
        "position = excluded.position, duration = excluded.duration, "
        "completed = MAX(progress.completed, excluded.completed), updated_at = excluded.updated_at",
        (uid, course, lesson, position, duration, int(completed), now()))


def set_completed(c, uid, course, lesson, completed):
    """The student ticks or unticks a lesson by hand."""
    c.execute(
        "INSERT INTO progress (user_id, course, lesson, completed, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT (user_id, course, lesson) DO UPDATE SET completed = excluded.completed",
        (uid, course, lesson, int(completed), now()))


def last_watched(c, uid, course):
    return c.execute("SELECT lesson FROM progress WHERE user_id = ? AND course = ? ORDER BY updated_at DESC LIMIT 1",
                     (uid, course)).fetchone()


# --- sessions and invites ------------------------------------------------------
def purge_expired(c):
    t = now()
    c.execute("DELETE FROM sessions WHERE expires_at < ?", (t,))
    c.execute("DELETE FROM invites WHERE expires_at < ?", (t,))
    c.execute("DELETE FROM events WHERE at < ?", (t - 90 * 86400,))   # keep 90 days


# --- questions -----------------------------------------------------------------
def add_question(c, uid, course, lesson, lesson_id, course_title, lesson_title, position, body):
    cur = c.execute(
        "INSERT INTO questions (user_id, course, lesson, lesson_id, course_title, lesson_title, position, body, "
        "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, course, lesson, lesson_id, course_title, lesson_title, position, body, now()))
    return cur.lastrowid


def question(c, qid):
    return c.execute("SELECT q.*, u.email, u.name FROM questions q JOIN users u ON u.id = q.user_id "
                     "WHERE q.id = ?", (qid,)).fetchone()


def my_questions(c, uid, course, lesson):
    return c.execute("SELECT * FROM questions WHERE user_id = ? AND course = ? AND lesson = ? ORDER BY created_at DESC",
                     (uid, course, lesson)).fetchall()


def questions(c, which="open"):
    where = {"open": "WHERE q.answered_at IS NULL", "answered": "WHERE q.answered_at IS NOT NULL"}.get(which, "")
    order = "q.created_at ASC" if which == "open" else "q.created_at DESC"
    return c.execute("SELECT q.*, u.email, u.name FROM questions q JOIN users u ON u.id = q.user_id %s ORDER BY %s"
                     % (where, order)).fetchall()


def open_question_count(c):
    return c.execute("SELECT COUNT(*) FROM questions WHERE answered_at IS NULL").fetchone()[0]


def recent_question_count(c, uid, seconds=3600):
    return c.execute("SELECT COUNT(*) FROM questions WHERE user_id = ? AND created_at > ?",
                     (uid, now() - seconds)).fetchone()[0]


def set_question_mail(qid, column, status):
    """Called from the mail thread: its own connection."""
    assert column in ("trainer_mail", "answer_mail")
    with db() as c:
        c.execute("UPDATE questions SET %s = ? WHERE id = ?" % column, (status, qid))
