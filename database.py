import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "events.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER UNIQUE,
        name TEXT,
        time TEXT,
        category TEXT,
        participant_limit INTEGER,
        author_id INTEGER,
        closed INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        event_id INTEGER,
        user_id INTEGER,
        UNIQUE(event_id, user_id)
    )
    """)

    conn.commit()
    conn.close()
