import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "events.db"

class EventDB:
    @staticmethod
    def create_event(message_id, name, time, category, limit, author_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO events (message_id, name, time, category, participant_limit, author_id, closed) VALUES (?, ?, ?, ?, ?, ?, 0)",
                  (message_id, name, time, category, limit, author_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_event_by_message(message_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM participants WHERE event_id = (SELECT id FROM events WHERE message_id = ?)", (message_id,))
        c.execute("DELETE FROM events WHERE message_id = ?", (message_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_event_by_message(message_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, message_id, name, time, category, participant_limit, author_id, closed FROM events WHERE message_id = ?", (message_id,))
        row = c.fetchone()
        conn.close()
        return row

    @staticmethod
    def add_participant(message_id, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # get event_id
        c.execute("SELECT id, participant_limit, closed FROM events WHERE message_id = ?", (message_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "event_not_found"
        event_id, limit, closed = row
        if closed:
            conn.close()
            return False, "closed"
        c.execute("SELECT COUNT(*) FROM participants WHERE event_id = ?", (event_id,))
        count = c.fetchone()[0]
        if limit and count >= limit:
            conn.close()
            return False, "full"
        try:
            c.execute("INSERT INTO participants (event_id, user_id) VALUES (?, ?)", (event_id, user_id))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return False, "already"
        conn.close()
        return True, "ok"

    @staticmethod
    def remove_participant(message_id, user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM events WHERE message_id = ?", (message_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False
        event_id = row[0]
        c.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def get_participants(message_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM events WHERE message_id = ?", (message_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return []
        event_id = row[0]
        c.execute("SELECT user_id FROM participants WHERE event_id = ?", (event_id,))
        users = [r[0] for r in c.fetchall()]
        conn.close()
        return users

    @staticmethod
    def close_event(message_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE events SET closed = 1 WHERE message_id = ?", (message_id,))
        conn.commit()
        conn.close()
