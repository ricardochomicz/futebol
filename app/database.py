import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
 group_id TEXT NOT NULL, player_id TEXT NOT NULL, name TEXT NOT NULL,
 PRIMARY KEY(group_id, player_id));
CREATE TABLE IF NOT EXISTS matches (
 id INTEGER PRIMARY KEY, group_id TEXT NOT NULL, starts_at TEXT NOT NULL,
 capacity INTEGER NOT NULL CHECK(capacity > 0), price INTEGER NOT NULL CHECK(price >= 0),
 status TEXT NOT NULL CHECK(status IN ('open','closed','finished')));
CREATE UNIQUE INDEX IF NOT EXISTS active_match ON matches(group_id) WHERE status != 'finished';
CREATE TABLE IF NOT EXISTS registrations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL REFERENCES matches(id),
 player_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('confirmed','waiting','cancelled')),
 payment TEXT NOT NULL DEFAULT 'pending' CHECK(payment IN ('pending','declared','paid')),
 attended INTEGER CHECK(attended IN (0,1)), UNIQUE(match_id, player_id));
"""


@contextmanager
def transaction(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        connection.executescript(SCHEMA)
        # Serialize capacity checks and queue promotion across workers.
        connection.execute('BEGIN IMMEDIATE')
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
