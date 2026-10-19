import io
import json
import os
import secrets
import zipfile
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.exceptions import HTTPException, SecurityError

from license_server import API_REVISION
from license_server.leases import LicenseSigner, decode, encode
from license_server.service import LicenseError, LicenseService


def load_secrets(directory):
    path = directory / "secrets.json"
    if not path.exists():
        config = dict(
            version=1,
            session_secret=secrets.token_urlsafe(48),
            signing_key=encode(Ed25519PrivateKey.generate().private_bytes_raw()),
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(config, stream)
    config = json.loads(path.read_text(encoding="utf-8"))
    if (
        config.get("version") != 1
        or not isinstance(config.get("session_secret"), str)
        or len(config["session_secret"]) < 32
    ):
        raise ValueError(
            "Tệp bí mật của máy chủ không hợp lệ; không tự tạo lại để tránh mất giấy phép cũ."
        )
    LicenseSigner(decode(config["signing_key"]))
    return config


def create_app(data_dir=None, *, testing=False, clock=None, local=True):
    directory = Path(
        data_dir or os.environ.get("LIVE_STUDIO_LICENSE_DATA", ".license-server")
    ).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    existed = (directory / "license.sqlite3").exists()
    service = LicenseService(directory / "license.sqlite3", clock=clock)
    with service.connection(write=True):
        if existed and not (directory / "secrets.json").exists():
            raise ValueError(
                "Thiếu secrets.json của dữ liệu cũ. Hãy khôi phục từ bản sao lưu, không tạo khóa ký mới."
            )
        keys = load_secrets(directory)
    signer = LicenseSigner(decode(keys["signing_key"]))
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=keys["session_secret"],
        TESTING=testing,
        SESSION_COOKIE_NAME="live_studio_admin",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=not local,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=16384,
        TRUSTED_HOSTS=["127.0.0.1", "localhost", "[::1]"]
        if local
        else os.environ.get("LIVE_STUDIO_TRUSTED_HOSTS", "").split(","),
    )
    app.extensions["license_service"] = service
    app.extensions["license_signer"] = signer
    from license_server.releases import register_releases

    register_releases(app, directory, service)

    @app.before_request
    def protect():
        if request.path == "/api/admin/releases" and request.method == "POST":
            from license_server.releases import CHUNK_SIZE

            request.max_content_length = CHUNK_SIZE
        if request.routing_exception is not None:
            return None
        path = request.path
        admin = path == "/admin" or path.startswith("/api/admin/") or path == "/logout"
        if admin:
            g.admin = service.session_user(session.get("sid"))
            if not g.admin:
                if path.startswith("/api/"):
                    raise LicenseError("unauthorized", "Vui lòng đăng nhập lại.", 401)
                return redirect(url_for("login"))
        if path in ("/login", "/setup") or admin:
            if request.method == "POST":
                actual = request.headers.get("X-CSRF-Token") or request.form.get(
                    "csrf", ""
                )
                expected = session.get("csrf", "")
                if (
                    not actual
                    or not expected
                    or len(actual) > 128
                    or not actual.isascii()
                    or not secrets.compare_digest(actual, expected)
                ):
                    raise LicenseError(
                        "csrf", "Phiên biểu mẫu đã hết hạn. Hãy tải lại trang.", 403
                    )
            elif not session.get("csrf"):
                session["csrf"] = secrets.token_urlsafe(32)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if not local:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(LicenseError)
    def license_error(error):
        if request.path.startswith("/api/"):
            response = jsonify(error=dict(code=error.code, message=str(error)))
            response.status_code = error.status
            if error.status == 429:
                response.headers["Retry-After"] = "60"
            return response
        if request.path in ("/setup", "/login"):
            return render_template(
                "auth.html", setup=request.path == "/setup", error=str(error)
            ), error.status
        return render_template("error.html", message=str(error)), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        if isinstance(error, SecurityError):
            return "Yêu cầu máy chủ không hợp lệ.", 400
        if request.path.startswith("/api/"):
            return jsonify(
                error=dict(
                    code="http_error", message="Yêu cầu không hợp lệ hoặc quá lớn."
                )
            ), error.code
        return render_template(
            "error.html", message="Trang không tồn tại hoặc yêu cầu không hợp lệ."
        ), error.code

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise LicenseError("invalid_input", "Cần gửi dữ liệu JSON hợp lệ.")
        return data

    def limit(name, count, seconds):
        service.rate_limit(
            name + ":" + (request.remote_addr or "unknown"), count, seconds
        )

    @app.get("/health")
    def health():
        return jsonify(
            status="ok", service="live-studio-license", api_revision=API_REVISION
        )

    @app.get("/")
    def index():
        return redirect(
            url_for(
                "admin"
                if service.session_user(session.get("sid"))
                else "login"
                if service.has_admin()
                else "setup"
            )
        )

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if not local or request.remote_addr not in ("127.0.0.1", "::1"):
            raise LicenseError(
                "setup_local_only",
                "Chỉ tạo tài khoản lần đầu trên máy chủ cục bộ.",
                403,
            )
        if service.has_admin():
            return redirect(url_for("login"))
        if request.method == "POST":
            limit("setup", 10, 600)
            password = request.form.get("password", "")
            if password != request.form.get("confirm", ""):
                raise LicenseError("invalid_password", "Hai mật khẩu không khớp.")
            service.setup_admin(request.form.get("username", ""), password)
            session.clear()
            return redirect(url_for("login", ready=1))
        return render_template("auth.html", setup=True)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not service.has_admin():
            return redirect(url_for("setup"))
        if request.method == "POST":
            limit("login", 10, 600)
            token = service.login(
                request.form.get("username", ""), request.form.get("password", "")
            )
            session.clear()
            session.update(sid=token, csrf=secrets.token_urlsafe(32))
            session.permanent = True
            return redirect(url_for("admin"))
        return render_template("auth.html", setup=False)

    @app.post("/logout")
    def logout():
        service.logout(session.get("sid", ""))
        session.clear()
        return redirect(url_for("login"))

    @app.get("/admin")
    def admin():
        return render_template("admin.html", username=g.admin, local=local)

    @app.get("/api/admin/licenses")
    def list_licenses():
        try:
            page = int(request.args.get("page", "1"))
        except ValueError as ex:
            raise LicenseError("invalid_input", "Trang không hợp lệ.") from ex
        return jsonify(
            service.list_keys(
                request.args.get("q", ""), request.args.get("status", ""), page
            )
        )

    @app.post("/api/admin/licenses")
    def create_licenses():
        data = body()
        result = service.create_keys(
            data.get("days"), data.get("quantity"), data.get("note", ""), g.admin
        )
        return jsonify(created=result), 201

    @app.get("/api/admin/licenses/<license_id>")
    def license_details(license_id):
        return jsonify(
            license=service.get_license(license_id), audit=service.audit(license_id)
        )

    @app.post("/api/admin/licenses/<license_id>/<action>")
    def mutate(license_id, action):
        data = body()
        if action == "renew":
            service.renew(license_id, data.get("days"), g.admin)
        elif action in ("block", "unblock"):
            service.set_blocked(license_id, action == "block", g.admin)
        elif action == "reset-device":
            service.reset_device(license_id, g.admin)
        elif action == "note":
            service.set_note(license_id, data.get("note"), g.admin)
        elif action in ("archive", "restore"):
            service.set_archived(license_id, action == "archive", g.admin)
        elif action == "delete":
            service.delete_unused(license_id, g.admin)
            return jsonify(deleted=True)
        else:
            raise LicenseError("invalid_action", "Thao tác không hợp lệ.")
        return jsonify(license=service.get_license(license_id))

    @app.get("/api/admin/audit")
    def audit():
        try:
            page = int(request.args.get("page", "1"))
        except ValueError as ex:
            raise LicenseError("invalid_input", "Trang không hợp lệ.") from ex
        return jsonify(items=service.audit(page=page), page=page)

    @app.get("/api/admin/audit/cleanup-preview")
    def cleanup_preview():
        return jsonify(service.audit_cleanup_preview())

    @app.post("/api/admin/audit/cleanup")
    def cleanup():
        return jsonify(deleted=service.clean_audit(body().get("cutoff"), g.admin))

    @app.get("/api/admin/audit/export")
    def export_audit():
        data = json.dumps(service.export_audit(), ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        return send_file(
            io.BytesIO(data),
            mimetype="application/json",
            as_attachment=True,
            download_name="Live-Studio-History.json",
        )

    @app.get("/api/admin/client-config")
    def client_config():
        data = json.dumps(
            dict(
                version=1,
                server_url=request.host_url.rstrip("/"),
                public_key=signer.public_key,
            )
        ).encode()
        return send_file(
            io.BytesIO(data),
            mimetype="application/json",
            as_attachment=True,
            download_name="license-client.json",
        )

    @app.post("/api/admin/password")
    def password():
        limit("password", 10, 600)
        data = body()
        if data.get("new") != data.get("confirm"):
            raise LicenseError("invalid_password", "Hai mật khẩu mới không khớp.")
        service.change_password(g.admin, data.get("current"), data.get("new"))
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/admin/backup")
    def backup():
        with service.connection(write=True) as db:
            service._audit(db, g.admin, "backup_downloaded")
        import sqlite3

        snapshot = sqlite3.connect(":memory:")
        try:
            with service.connection() as db:
                db.backup(snapshot)
            data = snapshot.serialize()
        finally:
            snapshot.close()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("license.sqlite3", data)
            bundle.writestr("secrets.json", json.dumps(keys))
            bundle.writestr(
                "RESTORE.txt",
                "Private admin backup. Stop the server. Extract into a NEW private directory. Run python -m license_server --data-dir PATH. Never give this archive to customers. Sessions are invalidated on restore by the --revoke-sessions option.\n",
            )
        archive.seek(0)
        return send_file(
            archive,
            mimetype="application/zip",
            as_attachment=True,
            download_name="Live-Studio-Admin-Backup.zip",
        )

    @app.get("/api/license/public-key")
    def public_key():
        return jsonify(algorithm="Ed25519", public_key=signer.public_key)

    @app.post("/api/license/activate")
    def activate():
        limit("activate", 30, 60)
        data = body()
        return jsonify(service.activate(data.get("key"), data.get("device_id"), signer))

    @app.post("/api/license/check")
    def check():
        limit("check", 120, 60)
        data = body()
        return jsonify(
            service.check(
                data.get("license_id"),
                data.get("device_id"),
                data.get("activation_token"),
                signer,
            )
        )

    return app
