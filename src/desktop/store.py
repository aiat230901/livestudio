import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from desktop.scheduling import normalize_schedule


def normalize_username(value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in (
            "tiktok.com",
            "www.tiktok.com",
        ):
            raise ValueError("Hãy nhập username hoặc link hồ sơ TikTok hợp lệ.")
        match = re.fullmatch(r"/@([^/]+)(?:/live)?/?", parsed.path)
        if not match:
            raise ValueError("Link phải dẫn đến hồ sơ hoặc livestream TikTok.")
        value = match[1]
    value = value.removeprefix("@").lower()
    if not re.fullmatch(r"[a-z0-9_][a-z0-9_.]{0,23}", value) or value.endswith("."):
        raise ValueError(
            "Username chỉ gồm chữ, số, dấu chấm và gạch dưới (tối đa 24 ký tự)."
        )
    return value


class DesktopStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS channels (
                username TEXT PRIMARY KEY, duration_seconds INTEGER,
                output TEXT, enabled INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS sessions (
                username TEXT, room_id TEXT, started_utc REAL, deadline_utc REAL,
                state TEXT, PRIMARY KEY(username, room_id));
            CREATE TABLE IF NOT EXISTS recordings (id INTEGER PRIMARY KEY, data TEXT);
        """)
        columns = {
            row["name"] for row in self.db.execute("PRAGMA table_info(channels)")
        }
        with self.db:
            if "mode" not in columns:
                self.db.execute(
                    "ALTER TABLE channels ADD COLUMN mode TEXT NOT NULL DEFAULT 'continuous'"
                )
            if "schedules" not in columns:
                self.db.execute(
                    "ALTER TABLE channels ADD COLUMN schedules TEXT NOT NULL DEFAULT '[]'"
                )

    def close(self):
        self.db.close()

    def save_channel(
        self,
        user,
        duration_seconds=None,
        output=None,
        enabled=True,
        mode=None,
        schedules=None,
    ):
        user = normalize_username(user)
        if duration_seconds is not None and (
            type(duration_seconds) is not int or duration_seconds <= 0
        ):
            raise ValueError("Thời lượng phải là số nguyên dương hoặc không giới hạn.")
        previous = self.db.execute(
            "SELECT mode, schedules FROM channels WHERE username=?", (user,)
        ).fetchone()
        mode = (
            mode
            if mode is not None
            else (previous["mode"] if previous else "continuous")
        )
        if mode not in ("continuous", "scheduled"):
            raise ValueError("Chế độ theo dõi không hợp lệ.")
        if schedules is None:
            schedules = json.loads(previous["schedules"]) if previous else []
        if not isinstance(schedules, list):
            raise ValueError("Danh sách lịch không hợp lệ.")
        schedules = [normalize_schedule(rule) for rule in schedules]
        with self.db:
            self.db.execute(
                """INSERT INTO channels(username, duration_seconds, output, enabled, mode, schedules)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(username) DO UPDATE SET
                duration_seconds=excluded.duration_seconds, output=excluded.output,
                enabled=excluded.enabled, mode=excluded.mode, schedules=excluded.schedules""",
                (
                    user,
                    duration_seconds,
                    output or None,
                    bool(enabled),
                    mode,
                    json.dumps(schedules),
                ),
            )
        return self._channel_dict(
            self.db.execute(
                "SELECT * FROM channels WHERE username=?", (user,)
            ).fetchone()
        )

    def list_channels(self):
        return [
            self._channel_dict(row)
            for row in self.db.execute("SELECT * FROM channels ORDER BY username")
        ]

    @staticmethod
    def _channel_dict(row):
        channel = dict(row)
        channel["schedules"] = json.loads(channel["schedules"])
        return channel

    def delete_channel(self, user):
        with self.db:
            self.db.execute("DELETE FROM channels WHERE username=?", (user,))

    def get_setting(self, name, default=None):
        row = self.db.execute(
            "SELECT value FROM settings WHERE name=?", (name,)
        ).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, name, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES (?, ?)",
                (name, json.dumps(value)),
            )

    def get_session(self, user, room_id):
        row = self.db.execute(
            "SELECT * FROM sessions WHERE username=? AND room_id=?",
            (user, str(room_id)),
        ).fetchone()
        return dict(row) if row else None

    def save_session(self, user, room_id, started_utc, deadline_utc, state):
        if state not in ("active", "completed", "stopped"):
            raise ValueError("Invalid session state")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?)",
                (user, str(room_id), started_utc, deadline_utc, state),
            )

    def add_recording(self, record):
        with self.db:
            self.db.execute(
                "INSERT INTO recordings(data) VALUES (?)", (json.dumps(record),)
            )

    def list_recordings(self):
        return [
            dict(json.loads(row["data"]), id=row["id"])
            for row in self.db.execute("SELECT * FROM recordings ORDER BY id DESC")
        ]
