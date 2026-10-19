import argparse
import getpass
import json
import logging
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from license_server import API_REVISION
from license_server.app import create_app
from license_server.service import LicenseError


def main():
    parser = argparse.ArgumentParser(description="Trang quản trị Live Studio cục bộ")
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parents[2] / ".license-server"),
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--open", action="store_true", help="Mở trang admin trên trình duyệt"
    )
    parser.add_argument(
        "--reset-password",
        metavar="USERNAME",
        help="Đặt lại mật khẩu admin trực tiếp trên máy chủ",
    )
    parser.add_argument(
        "--revoke-sessions",
        action="store_true",
        help="Thu hồi phiên admin sau khi khôi phục backup",
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Cổng phải từ 1024 đến 65535.")
    url = f"http://127.0.0.1:{args.port}"
    if not args.reset_password and not args.revoke_sessions:
        try:
            with urllib.request.urlopen(url + "/health", timeout=1) as response:
                health = json.load(response)
                if health.get("service") == "live-studio-license":
                    if health.get("api_revision") != API_REVISION:
                        print(
                            "Máy chủ đang chạy bản cũ. Nhấn Ctrl+C trong cửa sổ máy chủ cũ, rồi mở lại Mo_Admin.bat. Key và tài khoản vẫn được giữ.",
                            flush=True,
                        )
                        return 1
                    print("Máy chủ đã chạy: " + url)
                    if args.open:
                        webbrowser.open(url)
                    return 0
        except (urllib.error.URLError, ValueError, OSError):
            pass
    app = create_app(args.data_dir)
    service = app.extensions["license_service"]
    if args.reset_password:
        password = getpass.getpass("Mật khẩu mới (tối thiểu 12 ký tự): ")
        confirm = getpass.getpass("Nhập lại mật khẩu: ")
        if password != confirm:
            print("Hai mật khẩu không khớp.")
            return 1
        try:
            service.reset_password(args.reset_password, password)
        except LicenseError as ex:
            print(str(ex))
            return 1
        print("Đã đổi mật khẩu và đăng xuất các phiên admin.")
        return 0
    if args.revoke_sessions:
        with service.connection(write=True) as db:
            db.execute("DELETE FROM sessions")
            service._audit(db, "server-owner", "sessions_revoked")
        print("Đã thu hồi các phiên admin cũ.")
        return 0
    from license_server.hosting import http_server

    try:
        server = http_server(app, "127.0.0.1", args.port)
    except OSError:
        print(f"Cổng {args.port} đang được dùng. Hãy chọn cổng khác bằng --port.")
        return 1
    print("Live Studio Admin: " + url, flush=True)
    # This file contains only the public verification key, never server secrets.
    config_path = Path(__file__).resolve().parents[2] / "license-client.json"
    config_path.write_text(
        json.dumps(
            dict(
                version=1,
                server_url=url,
                public_key=app.extensions["license_signer"].public_key,
            )
        ),
        encoding="utf-8",
    )
    print("Dừng máy chủ bằng Ctrl+C. Đóng trình duyệt không dừng máy chủ.", flush=True)
    if args.open:
        webbrowser.open(url)
    logging.basicConfig(level=logging.WARNING)
    try:
        server.run()
    except KeyboardInterrupt:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
