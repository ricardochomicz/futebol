import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
 group_id TEXT NOT NULL, player_id TEXT NOT NULL, name TEXT NOT NULL, invited_by TEXT,
 PRIMARY KEY(group_id, player_id));
CREATE TABLE IF NOT EXISTS matches (
 id INTEGER PRIMARY KEY, group_id TEXT NOT NULL, starts_at TEXT NOT NULL,
 capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 18),
 price INTEGER NOT NULL CHECK(price >= 0),
 goalkeeper_capacity INTEGER NOT NULL DEFAULT 2
    CHECK(goalkeeper_capacity BETWEEN 0 AND 2),
 status TEXT NOT NULL CHECK(status IN ('open','closed','finished')));
CREATE UNIQUE INDEX IF NOT EXISTS active_match ON matches(group_id) WHERE status != 'finished';
CREATE TABLE IF NOT EXISTS registrations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL REFERENCES matches(id),
 player_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('confirmed','waiting','cancelled')),
 role TEXT NOT NULL DEFAULT 'line'
    CHECK(role IN ('line', 'goalkeeper')),
exempt INTEGER NOT NULL DEFAULT 0
    CHECK(exempt IN (0, 1)),
 payment TEXT NOT NULL DEFAULT 'pending' CHECK(payment IN ('pending','declared','paid')),
 attended INTEGER CHECK(attended IN (0,1)), UNIQUE(match_id, player_id));
 CREATE TABLE IF NOT EXISTS memberships (
    group_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    month TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount >= 0),
    payment TEXT NOT NULL DEFAULT 'pending' CHECK(payment IN ('pending','declared','paid')),
    PRIMARY KEY(group_id, player_id, month),
    FOREIGN KEY(group_id, player_id) REFERENCES players(group_id, player_id)
);
 CREATE TABLE IF NOT EXISTS processed_messages (
    group_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    text TEXT NOT NULL,
    reply TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(group_id, message_id)
);
"""


def migrate(connection):
    player_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(players)")
    }
    if "invited_by" not in player_columns:
        connection.execute("ALTER TABLE players ADD COLUMN invited_by TEXT")

    match_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(matches)")
    }

    registration_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(registrations)")
    }

    if "goalkeeper_capacity" not in match_columns:
        connection.execute("""
            ALTER TABLE matches
            ADD COLUMN goalkeeper_capacity INTEGER NOT NULL DEFAULT 2
                CHECK(goalkeeper_capacity BETWEEN 0 AND 2)
            """)

    if "role" not in registration_columns:
        connection.execute("""
            ALTER TABLE registrations
            ADD COLUMN role TEXT NOT NULL DEFAULT 'line'
                CHECK(role IN ('line', 'goalkeeper'))
            """)

    if "exempt" not in registration_columns:
        connection.execute("""
            ALTER TABLE registrations
            ADD COLUMN exempt INTEGER NOT NULL DEFAULT 0
                CHECK(exempt IN (0, 1))
            """)


@contextmanager
def transaction(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript(SCHEMA)
        # Serialize capacity checks and queue promotion across workers.
        connection.execute("BEGIN IMMEDIATE")
        migrate(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
