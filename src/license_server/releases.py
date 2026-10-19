"""Signed Windows release protocol shared by the server and desktop updater."""

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from threading import Lock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from license_server.leases import decode

MAX_PACKAGE = 512 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
DOMAIN = b"LIVE-STUDIO-UPDATE-V1."


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})", value
    ):
        raise ValueError("Phiên bản cần có dạng 1.0.0.")
    return tuple(int(part) for part in value.split("."))


def manifest_bytes(payload):
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def verify_manifest(envelope, public_key):
    try:
        payload = envelope["payload"]
        if set(payload) != {"format", "platform", "version", "sha256", "size", "notes"}:
            raise ValueError()
        version_tuple(payload["version"])
        if (
            type(payload["format"]) is not int
            or payload["format"] != 1
            or payload["platform"] != "windows-x64"
            or not re.fullmatch(r"[0-9a-f]{64}", payload["sha256"])
            or type(payload["size"]) is not int
            or not 1 <= payload["size"] <= MAX_PACKAGE
            or not isinstance(payload["notes"], str)
            or len(payload["notes"]) > 4000
        ):
            raise ValueError()
        Ed25519PublicKey.from_public_bytes(decode(public_key)).verify(
            decode(envelope["signature"]), DOMAIN + manifest_bytes(payload)
        )
        return payload
    except Exception as error:
        raise ValueError(
            "Bản cập nhật không có chữ ký hợp lệ hoặc thông tin không đúng."
        ) from error


def register_releases(app, directory, service):
    from flask import g, jsonify, request, send_file
    from license_server.service import LicenseError

    folder = Path(directory) / "releases"
    guard = Lock()

    def public_key():
        key = os.environ.get("LIVE_STUDIO_UPDATE_PUBLIC_KEY", "")
        if not key:
            raise LicenseError(
                "update_not_configured",
                "Cần khai báo LIVE_STUDIO_UPDATE_PUBLIC_KEY trên hosting.",
                503,
            )
        try:
            Ed25519PublicKey.from_public_bytes(decode(key))
        except Exception as error:
            raise LicenseError(
                "update_not_configured", "Khóa công khai cập nhật không hợp lệ.", 503
            ) from error
        return key

    def latest():
        path = folder / "latest.json"
        if not path.exists():
            return None
        envelope = json.loads(path.read_text(encoding="utf-8"))
        verify_manifest(envelope, public_key())
        return envelope

    @app.get("/api/releases/latest")
    def release_latest():
        envelope = latest()
        if envelope is None:
            raise LicenseError("no_release", "Chưa có bản phát hành.", 404)
        return jsonify(envelope)

    @app.get("/api/admin/releases")
    def release_status():
        public_key()
        return jsonify(latest=latest())

    @app.get("/api/releases/download/<digest>.zip")
    def release_download(digest):
        if (
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not (folder / (digest + ".zip")).is_file()
        ):
            raise LicenseError("not_found", "Không tìm thấy bản phát hành.", 404)
        return send_file(
            folder / (digest + ".zip"),
            as_attachment=True,
            download_name="LiveStudio-Windows-x64.zip",
            conditional=True,
        )

    @app.post("/api/admin/releases")
    def release_upload():
        try:
            header = request.headers.get("X-Release-Manifest", "")
            if len(header) > 32768:
                raise ValueError()
            envelope = json.loads(base64.b64decode(header, validate=True))
            payload = verify_manifest(envelope, public_key())
        except (ValueError, KeyError, TypeError) as error:
            raise LicenseError(
                "invalid_release",
                "Tệp thông tin hoặc chữ ký bản phát hành không hợp lệ.",
            ) from error
        from werkzeug.exceptions import RequestEntityTooLarge

        if request.content_length is not None and request.content_length > CHUNK_SIZE:
            raise RequestEntityTooLarge()
        try:
            offset = int(request.headers.get("X-Upload-Offset", "0"))
        except ValueError as error:
            raise LicenseError(
                "invalid_release", "Vị trí tải lên không hợp lệ."
            ) from error
        count = request.content_length
        if count is None or count < 1 or offset < 0 or offset + count > payload["size"]:
            raise LicenseError(
                "invalid_release", "Dung lượng phần tải lên không hợp lệ."
            )
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / (payload["sha256"] + ".upload")
        with guard:
            current = latest()
            if current and version_tuple(
                current["payload"]["version"]
            ) >= version_tuple(payload["version"]):
                raise LicenseError(
                    "old_release", "Bản phát hành phải mới hơn bản hiện tại.", 409
                )
            existing = temporary.stat().st_size if temporary.exists() else 0
            if offset and offset != existing:
                raise LicenseError(
                    "upload_offset",
                    "Phần tải lên không nối tiếp. Hãy chọn tải lại.",
                    409,
                )
            content = request.get_data()
            if len(content) != count:
                raise LicenseError("invalid_release", "Phần tải lên bị thiếu.")
            with temporary.open("wb" if offset == 0 else "ab") as stream:
                stream.write(content)
            received = offset + count
            if received < payload["size"]:
                return jsonify(done=False, received=received)
            with temporary.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != payload["sha256"]:
                temporary.unlink()
                raise LicenseError(
                    "invalid_release", "ZIP sai mã kiểm tra; bản hiện tại được giữ."
                )
            os.replace(temporary, folder / (payload["sha256"] + ".zip"))
            pointer = folder / "latest.json.tmp"
            pointer.write_text(json.dumps(envelope), encoding="utf-8")
            os.replace(pointer, folder / "latest.json")
            with service.connection(write=True) as db:
                service._audit(
                    db, g.admin, "release_published", version=payload["version"]
                )
        return jsonify(done=True, version=payload["version"])
