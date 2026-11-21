"""SQLite storage: users, sessions, invites, enrollments, progress."""
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


def init():
    with db() as c:
        c.executescript(SCHEMA)


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


def last_watched(c, uid, course):
    return c.execute("SELECT lesson FROM progress WHERE user_id = ? AND course = ? ORDER BY updated_at DESC LIMIT 1",
                     (uid, course)).fetchone()


# --- sessions and invites ------------------------------------------------------
def purge_expired(c):
    t = now()
    c.execute("DELETE FROM sessions WHERE expires_at < ?", (t,))
    c.execute("DELETE FROM invites WHERE expires_at < ?", (t,))
