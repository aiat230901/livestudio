"""HTTPS hosting entry point; the desktop recorder stays on the customer's PC."""

import argparse
import base64
import io
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from license_server.app import create_app


def export_bootstrap(directory):
    directory = Path(directory)
    if not (directory / "license.sqlite3").is_file():
        raise ValueError("Không tìm thấy database nguồn.")
    archive = io.BytesIO()
    with sqlite3.connect(directory / "license.sqlite3") as source:
        snapshot = sqlite3.connect(":memory:")
        try:
            source.backup(snapshot)
            snapshot.execute("DELETE FROM sessions")
            snapshot.execute("DELETE FROM rate_limits")
            snapshot.commit()
            data = snapshot.serialize()
        finally:
            snapshot.close()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("license.sqlite3", data)
        bundle.writestr("secrets.json", (directory / "secrets.json").read_bytes())
    return base64.b64encode(archive.getvalue()).decode("ascii")


def restore_bootstrap(directory, encoded):
    if not encoded or len(encoded) > 16 * 1024 * 1024:
        raise ValueError(
            "Cần LIVE_STUDIO_BOOTSTRAP_BACKUP chứa backup từ máy quản trị."
        )
    try:
        payload = base64.b64decode(encoded, validate=True)
        with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
            if sorted(bundle.namelist()) != ["license.sqlite3", "secrets.json"]:
                raise ValueError("Invalid backup files")
            if sum(info.file_size for info in bundle.infolist()) > 32 * 1024 * 1024:
                raise ValueError("Backup too large")
            files = {name: bundle.read(name) for name in bundle.namelist()}
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary)
            for name, data in files.items():
                (staging / name).write_bytes(data)
            app = create_app(staging, local=False)
            service = app.extensions["license_service"]
            if not service.has_admin():
                raise ValueError("Backup needs an existing admin")
            with service.connection(write=True) as db:
                db.execute("DELETE FROM sessions")
                db.execute("DELETE FROM rate_limits")
            directory.mkdir(parents=True, exist_ok=True)
            # Secrets first: an interrupted restore must fail rather than rotate keys.
            for name in ("secrets.json", "license.sqlite3"):
                target = directory / name
                with target.open("xb") as stream:
                    with (staging / name).open("rb") as source:
                        shutil.copyfileobj(source, stream)
                target.chmod(0o600)
    except Exception as error:
        raise ValueError(
            "Không khôi phục được backup; kiểm tra tệp và thư mục dữ liệu."
        ) from error


def hosted_app():
    hosts = os.environ.get("LIVE_STUDIO_TRUSTED_HOSTS", "")
    if not hosts.strip() or any(
        not host.strip() or ":" in host or "/" in host or "*" in host
        for host in hosts.split(",")
    ):
        raise ValueError(
            "LIVE_STUDIO_TRUSTED_HOSTS cần tên miền, không có https:// hoặc đường dẫn."
        )
    configured = os.environ.get("LIVE_STUDIO_LICENSE_DATA", "")
    if not configured or not Path(configured).is_absolute():
        raise ValueError(
            "LIVE_STUDIO_LICENSE_DATA cần đường dẫn tuyệt đối đến thư mục được giữ qua deploy."
        )
    directory = Path(configured)
    if not (directory / "license.sqlite3").exists():
        if (directory / "secrets.json").exists():
            raise ValueError(
                "Dữ liệu khôi phục chưa đầy đủ; cần khôi phục backup, không tạo khóa ký mới."
            )
        restore_bootstrap(directory, os.environ.get("LIVE_STUDIO_BOOTSTRAP_BACKUP", ""))
    app = create_app(directory, local=False)
    if not app.extensions["license_service"].has_admin():
        raise ValueError(
            "Database chưa có admin. Cần khôi phục backup từ máy quản trị."
        )
    app.config["TRUSTED_HOSTS"] = [host.strip() for host in hosts.split(",")] + [
        "localhost",
        "127.0.0.1",
        "[::1]",
    ]
    return app


def http_server(app, host, port, *, https=False):
    from waitress import create_server
    from license_server.releases import CHUNK_SIZE

    return create_server(
        app,
        host=host,
        port=port,
        threads=4,
        url_scheme="https" if https else "http",
        max_request_body_size=CHUNK_SIZE + 1,
        connection_limit=40,
        ident="LiveStudioLicense",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Máy chủ giấy phép Live Studio trên hosting HTTPS"
    )
    parser.add_argument("--export-bootstrap", type=Path, metavar="PRIVATE_FILE")
    parser.add_argument("--data-dir", type=Path, default=Path(".license-server"))
    args = parser.parse_args()
    if args.export_bootstrap:
        content = export_bootstrap(args.data_dir)
        with args.export_bootstrap.open("x", encoding="ascii") as stream:
            stream.write(content)
        args.export_bootstrap.chmod(0o600)
        print(
            "Private backup exported. Paste only into the hosting secret LIVE_STUDIO_BOOTSTRAP_BACKUP."
        )
        return
    port = int(os.environ.get("PORT", "3000"))
    if not 1024 <= port <= 65535:
        raise ValueError("PORT phải từ 1024 đến 65535.")
    app = hosted_app()
    print(f"Live Studio license server listening on 0.0.0.0:{port}", flush=True)
    server = http_server(app, "0.0.0.0", port, https=True)
    try:
        server.run()
    finally:
        server.close()


if __name__ == "__main__":
    main()
