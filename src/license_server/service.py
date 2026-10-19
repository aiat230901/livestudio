import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from license_server.leases import device_hash

KEY_PATTERN = re.compile(r"LVS-(?:[A-Z2-7]{4}-){7}[A-Z2-7]{4}")


class LicenseError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise LicenseError("invalid_input", f"{label} phải từ {low} đến {high}.")
    return value


def text(value, maximum, label):
    if not isinstance(value, str) or len(value) > maximum:
        raise LicenseError("invalid_input", f"{label} không hợp lệ hoặc quá dài.")
    return value.strip()


def validate_password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise LicenseError("invalid_password", "Mật khẩu cần từ 12 đến 128 ký tự.")


class LicenseService:
    def __init__(self, path, clock=None):
        self.path, self.clock = Path(path), clock or time.time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS admins(username TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS licenses(
                    id TEXT PRIMARY KEY, key_hash TEXT UNIQUE NOT NULL, key_hint TEXT NOT NULL,
                    note TEXT NOT NULL, duration_days INTEGER NOT NULL, created_at REAL NOT NULL,
                    activated_at REAL, expires_at REAL, device_hash TEXT, token_hash TEXT,
                    binding_version INTEGER NOT NULL DEFAULT 0, blocked INTEGER NOT NULL DEFAULT 0,
                    last_check REAL);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, license_id TEXT, detail TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS audit_license ON audit(license_id, id);
                CREATE TABLE IF NOT EXISTS rate_limits(bucket TEXT PRIMARY KEY, started REAL NOT NULL, hits INTEGER NOT NULL);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(licenses)")}
            if "archived" not in columns:
                db.execute(
                    "ALTER TABLE licenses ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
                )
            audit_columns = {row[1] for row in db.execute("PRAGMA table_info(audit)")}
            if "key_hint" not in audit_columns:
                db.execute("ALTER TABLE audit ADD COLUMN key_hint TEXT")
            db.execute(
                "UPDATE audit SET key_hint=(SELECT key_hint FROM licenses WHERE id=audit.license_id) WHERE key_hint IS NULL AND license_id IS NOT NULL"
            )
            db.execute("CREATE INDEX IF NOT EXISTS audit_time ON audit(at)")

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.create_function(
            "fold",
            1,
            lambda value: unicodedata.normalize("NFC", value).casefold(),
            deterministic=True,
        )
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def _audit(self, db, actor, action, license_id=None, **detail):
        db.execute(
            "INSERT INTO audit(at, actor, action, license_id, detail, key_hint) VALUES (?, ?, ?, ?, ?, (SELECT key_hint FROM licenses WHERE id=?))",
            (
                self.clock(),
                actor,
                action,
                license_id,
                json.dumps(detail, ensure_ascii=False),
                license_id,
            ),
        )

    def has_admin(self):
        with self.connection() as db:
            return db.execute("SELECT 1 FROM admins LIMIT 1").fetchone() is not None

    def setup_admin(self, username, password):
        username = text(username, 32, "Tên đăng nhập")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            raise LicenseError(
                "invalid_input",
                "Tên đăng nhập gồm 3–32 chữ, số, dấu chấm, gạch ngang hoặc gạch dưới.",
            )
        validate_password(password)
        hashed = generate_password_hash(password)
        with self.connection(write=True) as db:
            if db.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
                raise LicenseError("setup_closed", "Tài khoản admin đã được tạo.", 409)
            db.execute("INSERT INTO admins VALUES (?, ?)", (username, hashed))
            self._audit(db, username, "admin_setup")

    def login(self, username, password):
        username = text(username, 32, "Tên đăng nhập")
        if not isinstance(password, str) or len(password) > 128:
            raise LicenseError(
                "invalid_login", "Tên đăng nhập hoặc mật khẩu không đúng.", 401
            )
        with self.connection() as db:
            row = db.execute(
                "SELECT password_hash FROM admins WHERE username=?", (username,)
            ).fetchone()
        # Do the same password work for an unknown username.
        hashed = row["password_hash"] if row else "scrypt:32768:8:1$dummy$" + "0" * 128
        valid = check_password_hash(hashed, password)
        if not row or not valid:
            raise LicenseError(
                "invalid_login", "Tên đăng nhập hoặc mật khẩu không đúng.", 401
            )
        token = secrets.token_urlsafe(32)
        with self.connection(write=True) as db:
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (self.clock(),))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (digest(token), username, self.clock() + 8 * 3600),
            )
            self._audit(db, username, "login")
        return token

    def session_user(self, token):
        if not isinstance(token, str) or len(token) > 128:
            return None
        with self.connection() as db:
            row = db.execute(
                "SELECT username FROM sessions WHERE token_hash=? AND expires_at>?",
                (digest(token), self.clock()),
            ).fetchone()
        return row["username"] if row else None

    def logout(self, token):
        with self.connection(write=True) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

    def change_password(self, username, current, new):
        validate_password(new)
        with self.connection() as db:
            row = db.execute(
                "SELECT password_hash FROM admins WHERE username=?", (username,)
            ).fetchone()
        if (
            not row
            or not isinstance(current, str)
            or len(current) > 128
            or not check_password_hash(row["password_hash"], current)
        ):
            raise LicenseError("invalid_password", "Mật khẩu hiện tại không đúng.", 403)
        self.reset_password(username, new)

    def reset_password(self, username, password):
        validate_password(password)
        hashed = generate_password_hash(password)
        with self.connection(write=True) as db:
            if not db.execute(
                "SELECT 1 FROM admins WHERE username=?", (username,)
            ).fetchone():
                raise LicenseError("not_found", "Không tìm thấy tài khoản.", 404)
            db.execute(
                "UPDATE admins SET password_hash=? WHERE username=?", (hashed, username)
            )
            db.execute("DELETE FROM sessions WHERE username=?", (username,))
            self._audit(db, username, "password_changed")

    def rate_limit(self, bucket, limit, seconds):
        now = self.clock()
        with self.connection(write=True) as db:
            db.execute("DELETE FROM rate_limits WHERE started<?", (now - 86400,))
            row = db.execute(
                "SELECT * FROM rate_limits WHERE bucket=?", (bucket,)
            ).fetchone()
            if row and now - row["started"] < seconds:
                allowed = row["hits"] < limit
                db.execute(
                    "UPDATE rate_limits SET hits=hits+1 WHERE bucket=?", (bucket,)
                )
            else:
                allowed = True
                db.execute(
                    "INSERT OR REPLACE INTO rate_limits VALUES (?, ?, 1)", (bucket, now)
                )
        if not allowed:
            raise LicenseError(
                "rate_limited", "Quá nhiều lần thử. Vui lòng thử lại sau.", 429
            )

    def _row(self, db, license_id):
        row = db.execute("SELECT * FROM licenses WHERE id=?", (license_id,)).fetchone()
        if not row:
            raise LicenseError("not_found", "Không tìm thấy key.", 404)
        return dict(row)

    def public(self, row):
        result = {
            key: row[key]
            for key in (
                "id",
                "key_hint",
                "note",
                "duration_days",
                "created_at",
                "activated_at",
                "expires_at",
                "last_check",
                "blocked",
                "binding_version",
                "archived",
            )
        }
        result["device_hint"] = row["device_hash"][-12:] if row["device_hash"] else None
        result["status"] = (
            "archived"
            if row["archived"]
            else "blocked"
            if row["blocked"]
            else "pending"
            if row["activated_at"] is None
            else "expired"
            if row["expires_at"] <= self.clock()
            else "active"
        )
        return result

    def get_license(self, license_id):
        with self.connection() as db:
            return self.public(self._row(db, license_id))

    @staticmethod
    def client_license(row):
        return {
            key: row[key]
            for key in ("id", "activated_at", "expires_at", "binding_version")
        }

    def create_keys(self, days, quantity, note, actor):
        integer(days, 1, 3650, "Số ngày")
        integer(quantity, 1, 100, "Số lượng")
        note = text(note, 1000, "Ghi chú")
        result = []
        with self.connection(write=True) as db:
            for _ in range(quantity):
                raw = base64.b32encode(secrets.token_bytes(20)).decode()
                key = "LVS-" + "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))
                license_id, hint = uuid4().hex, "LVS-" + raw[:4] + "-…-" + raw[-4:]
                db.execute(
                    "INSERT INTO licenses(id,key_hash,key_hint,note,duration_days,created_at) VALUES(?,?,?,?,?,?)",
                    (license_id, digest(key), hint, note, days, self.clock()),
                )
                self._audit(db, actor, "key_created", license_id, duration_days=days)
                result.append(dict(id=license_id, key=key, key_hint=hint))
        return result

    def _valid(self, row):
        if row["archived"]:
            raise LicenseError("archived", "Key đã được lưu trữ và ngừng sử dụng.", 403)
        if row["blocked"]:
            raise LicenseError("blocked", "Key đã bị khóa.", 403)
        if row["expires_at"] is not None and row["expires_at"] <= self.clock():
            raise LicenseError("expired", "Key đã hết hạn.", 410)

    def _device(self, value):
        value = text(value, 256, "Mã thiết bị")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value):
            raise LicenseError(
                "invalid_input",
                "Mã thiết bị cần 32–256 chữ, số, gạch dưới hoặc gạch ngang.",
            )
        return device_hash(value)

    def activate(self, key, device_id, signer=None):
        key = text(key, 80, "Key").upper()
        if not KEY_PATTERN.fullmatch(key):
            raise LicenseError("invalid_key", "Key không hợp lệ.", 404)
        device = self._device(device_id)
        token = secrets.token_urlsafe(32)
        with self.connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM licenses WHERE key_hash=?", (digest(key),)
            ).fetchone()
            if not row:
                raise LicenseError("invalid_key", "Key không hợp lệ.", 404)
            row = dict(row)
            self._valid(row)
            now = self.clock()
            if row["device_hash"] and not hmac.compare_digest(
                row["device_hash"], device
            ):
                raise LicenseError(
                    "device_mismatch",
                    "Key đang được kích hoạt trên thiết bị khác.",
                    409,
                )
            if row["activated_at"] is None:
                row["activated_at"], row["expires_at"] = (
                    now,
                    now + row["duration_days"] * 86400,
                )
            row["device_hash"] = device
            db.execute(
                "UPDATE licenses SET activated_at=?, expires_at=?, device_hash=?, token_hash=?, last_check=? WHERE id=?",
                (
                    row["activated_at"],
                    row["expires_at"],
                    device,
                    digest(token),
                    now,
                    row["id"],
                ),
            )
            row["last_check"] = now
            self._audit(db, "client", "activated", row["id"], device_hint=device[-12:])
            result = dict(license=self.client_license(row), activation_token=token)
            if signer:
                result["lease"] = signer.issue(row, now)
            return result

    def check(self, license_id, device_id, token, signer=None):
        license_id = text(license_id, 64, "Mã key")
        device = self._device(device_id)
        token = text(token, 128, "Mã kích hoạt")
        with self.connection(write=True) as db:
            row = self._row(db, license_id)
            self._valid(row)
            now = self.clock()
            if not row["device_hash"] or not row["token_hash"]:
                raise LicenseError(
                    "activation_revoked",
                    "Liên kết thiết bị đã được reset. Cần kích hoạt lại.",
                    409,
                )
            if not hmac.compare_digest(row["device_hash"], device):
                raise LicenseError(
                    "device_mismatch", "Giấy phép thuộc thiết bị khác.", 409
                )
            if not hmac.compare_digest(row["token_hash"], digest(token)):
                raise LicenseError(
                    "activation_revoked",
                    "Mã kích hoạt đã được thay thế. Cần kích hoạt lại.",
                    409,
                )
            db.execute("UPDATE licenses SET last_check=? WHERE id=?", (now, license_id))
            row["last_check"] = now
            result = dict(license=self.client_license(row))
            if signer:
                result["lease"] = signer.issue(row, now)
            return result

    def set_blocked(self, license_id, blocked, actor):
        if type(blocked) is not bool:
            raise LicenseError("invalid_input", "Trạng thái khóa không hợp lệ.")
        with self.connection(write=True) as db:
            row = self._row(db, license_id)
            if row["archived"]:
                raise LicenseError(
                    "archived",
                    "Hãy khôi phục key trước khi thay đổi trạng thái khóa.",
                    409,
                )
            db.execute(
                "UPDATE licenses SET blocked=? WHERE id=?", (blocked, license_id)
            )
            self._audit(db, actor, "blocked" if blocked else "unblocked", license_id)

    def set_archived(self, license_id, archived, actor):
        if type(archived) is not bool:
            raise LicenseError("invalid_input", "Trạng thái lưu trữ không hợp lệ.")
        with self.connection(write=True) as db:
            row = self._row(db, license_id)
            if row["activated_at"] is None:
                raise LicenseError(
                    "never_activated",
                    "Key chưa kích hoạt có thể khóa hoặc xóa vĩnh viễn.",
                    409,
                )
            # Restoring retains the block, so restoring alone never grants access.
            db.execute(
                "UPDATE licenses SET archived=?,blocked=1 WHERE id=?",
                (archived, license_id),
            )
            self._audit(db, actor, "archived" if archived else "restored", license_id)

    def delete_unused(self, license_id, actor):
        with self.connection(write=True) as db:
            row = self._row(db, license_id)
            if row["activated_at"] is not None:
                raise LicenseError(
                    "already_activated",
                    "Key đã từng kích hoạt chỉ được lưu trữ, không xóa vĩnh viễn.",
                    409,
                )
            self._audit(db, actor, "key_deleted", license_id)
            db.execute("DELETE FROM licenses WHERE id=?", (license_id,))

    def audit_cleanup_preview(self):
        cutoff = self.clock() - 180 * 86400
        with self.connection() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM audit WHERE at<?", (cutoff,)
            ).fetchone()[0]
        return dict(cutoff=cutoff, count=count, retention_days=180)

    def clean_audit(self, cutoff, actor):
        if (
            type(cutoff) not in (int, float)
            or not 0 < cutoff <= self.clock() - 180 * 86400
        ):
            raise LicenseError("invalid_input", "Chỉ được dọn lịch sử cũ hơn 180 ngày.")
        with self.connection(write=True) as db:
            count = db.execute("DELETE FROM audit WHERE at<?", (cutoff,)).rowcount
            self._audit(db, actor, "audit_cleaned", count=count, cutoff=cutoff)
        # SQLite reuses freed pages for new records; no blocking VACUUM on the live server.
        return count

    def export_audit(self):
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,at,actor,action,license_id,key_hint,detail FROM audit ORDER BY id"
            ).fetchall()
        return [dict(dict(row), detail=json.loads(row["detail"])) for row in rows]

    def reset_device(self, license_id, actor):
        with self.connection(write=True) as db:
            self._row(db, license_id)
            db.execute(
                "UPDATE licenses SET device_hash=NULL,token_hash=NULL,binding_version=binding_version+1 WHERE id=?",
                (license_id,),
            )
            self._audit(db, actor, "device_reset", license_id)

    def renew(self, license_id, days, actor):
        integer(days, 1, 3650, "Số ngày gia hạn")
        with self.connection(write=True) as db:
            row = self._row(db, license_id)
            if row["activated_at"] is None:
                db.execute(
                    "UPDATE licenses SET duration_days=duration_days+? WHERE id=?",
                    (days, license_id),
                )
            else:
                expires = max(row["expires_at"], self.clock()) + days * 86400
                db.execute(
                    "UPDATE licenses SET expires_at=? WHERE id=?", (expires, license_id)
                )
            self._audit(db, actor, "renewed", license_id, days=days)

    def set_note(self, license_id, note, actor):
        note = text(note, 1000, "Ghi chú")
        with self.connection(write=True) as db:
            self._row(db, license_id)
            db.execute("UPDATE licenses SET note=? WHERE id=?", (note, license_id))
            self._audit(db, actor, "note_changed", license_id)

    def list_keys(self, query="", status="", page=1):
        query = text(query, 120, "Tìm kiếm")
        query = unicodedata.normalize("NFC", query).casefold()
        integer(page, 1, 100000, "Trang")
        if status not in ("", "active", "pending", "expired", "blocked", "archived"):
            raise LicenseError("invalid_input", "Bộ lọc không hợp lệ.")
        now = self.clock()
        state_sql = "CASE WHEN archived=1 THEN 'archived' WHEN blocked=1 THEN 'blocked' WHEN activated_at IS NULL THEN 'pending' WHEN expires_at<=? THEN 'expired' ELSE 'active' END"
        pattern = (
            "%"
            + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        where = "(fold(note) LIKE ? ESCAPE '\\' OR fold(key_hint) LIKE ? ESCAPE '\\' OR id=?) AND ((?='' AND archived=0) OR state=?)"
        params = (now, pattern, pattern, query, status, status)
        with self.connection() as db:
            base = f"SELECT *, {state_sql} AS state FROM licenses"
            count = db.execute(
                f"SELECT COUNT(*) FROM ({base}) WHERE {where}", params
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM ({base}) WHERE {where} ORDER BY created_at DESC,id LIMIT 20 OFFSET ?",
                (*params, (page - 1) * 20),
            ).fetchall()
            stats = {
                r["state"]: r["n"]
                for r in db.execute(
                    f"SELECT state,COUNT(*) n FROM ({base}) GROUP BY state", (now,)
                )
            }
        return dict(
            items=[self.public(row) for row in rows],
            total=count,
            page=page,
            pages=max(1, (count + 19) // 20),
            stats=dict(total=sum(stats.values()), **stats),
        )

    def audit(self, license_id=None, page=1):
        integer(page, 1, 100000, "Trang")
        with self.connection() as db:
            where = "WHERE a.license_id=?" if license_id else ""
            args = (license_id,) if license_id else ()
            rows = db.execute(
                f"SELECT a.id,a.at,a.actor,a.action,a.license_id,a.detail,COALESCE(a.key_hint,l.key_hint) AS key_hint FROM audit a LEFT JOIN licenses l ON l.id=a.license_id {where} ORDER BY a.id DESC LIMIT 50 OFFSET ?",
                (*args, (page - 1) * 50),
            ).fetchall()
        return [dict(dict(row), detail=json.loads(row["detail"])) for row in rows]
