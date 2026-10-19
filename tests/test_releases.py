import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.app import create_app
from license_server.leases import encode


def test_real_waitress_accepts_exact_full_chunk_and_rejects_oversized_body(
    tmp_path, monkeypatch
):
    from threading import Thread
    import requests
    from license_server.hosting import http_server
    from license_server.releases import CHUNK_SIZE

    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "LIVE_STUDIO_UPDATE_PUBLIC_KEY", encode(key.public_key().public_bytes_raw())
    )
    app = create_app(tmp_path, testing=True)
    service = app.extensions["license_service"]
    service.setup_admin("owner", "test-password-123")
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(sid=service.login("owner", "test-password-123"), csrf="csrf")
    cookie = client.get_cookie("live_studio_admin").value
    data = b"x" * (CHUNK_SIZE + 31)
    envelope = signed(key, data)
    headers = {
        "Cookie": "live_studio_admin=" + cookie,
        "X-CSRF-Token": "csrf",
        "X-Release-Manifest": base64.b64encode(json.dumps(envelope).encode()).decode(),
    }
    server = http_server(app, "127.0.0.1", 0)
    server.adj.asyncore_loop_timeout = 0.1
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.effective_port}"
    try:
        assert (
            requests.post(
                url + "/api/admin/releases",
                headers=headers,
                data=data[:CHUNK_SIZE],
                timeout=5,
            ).status_code
            == 200
        )
        headers["X-Upload-Offset"] = str(CHUNK_SIZE)
        response = requests.post(
            url + "/api/admin/releases",
            headers=headers,
            data=data[CHUNK_SIZE:],
            timeout=5,
        )
        assert response.status_code == 200 and response.json()["done"]
        assert (
            requests.post(
                url + "/login", data=b"x" * (CHUNK_SIZE + 1), timeout=5
            ).status_code
            == 413
        )
    finally:
        server.close()
        thread.join(timeout=2)


def test_chunked_upload_is_published_only_after_hash_verification(
    tmp_path, monkeypatch
):
    from license_server.releases import CHUNK_SIZE

    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "LIVE_STUDIO_UPDATE_PUBLIC_KEY", encode(key.public_key().public_bytes_raw())
    )
    app = create_app(tmp_path, testing=True)
    service = app.extensions["license_service"]
    service.setup_admin("owner", "test-password-123")
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(sid=service.login("owner", "test-password-123"), csrf="csrf")
    data = b"x" * (CHUNK_SIZE * 2 + 123)
    envelope = signed(key, data)
    headers = {
        "X-CSRF-Token": "csrf",
        "X-Release-Manifest": base64.b64encode(json.dumps(envelope).encode()).decode(),
    }
    assert (
        client.post("/api/admin/releases", headers=headers, data=data).status_code
        == 413
    )
    headers["X-Upload-Offset"] = "1"
    assert (
        client.post("/api/admin/releases", headers=headers, data=b"x").status_code
        == 409
    )
    for offset in range(0, len(data), CHUNK_SIZE):
        headers["X-Upload-Offset"] = str(offset)
        response = client.post(
            "/api/admin/releases",
            headers=headers,
            data=data[offset : offset + CHUNK_SIZE],
        )
        assert response.status_code == 200
        if offset + CHUNK_SIZE < len(data):
            assert not response.json["done"]
            assert client.get("/api/releases/latest").status_code == 404
        else:
            assert response.json["done"]
    assert client.get("/api/releases/latest").json == envelope


def signed(key, data=b"test package", version="1.0.1"):
    payload = dict(
        format=1,
        platform="windows-x64",
        version=version,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        notes="Bản mới",
    )
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return dict(
        payload=payload, signature=encode(key.sign(b"LIVE-STUDIO-UPDATE-V1." + raw))
    )


def test_manifest_rejects_tampering_and_wrong_key():
    from license_server.releases import verify_manifest, version_tuple

    key = Ed25519PrivateKey.generate()
    public = encode(key.public_key().public_bytes_raw())
    envelope = signed(key)
    assert verify_manifest(envelope, public)["version"] == "1.0.1"
    assert version_tuple("1.10.0") > version_tuple("1.9.9")
    envelope["payload"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        verify_manifest(envelope, public)
    for version in ("../1", "01.0.0", "1.0", "1.0.0.1"):
        with pytest.raises(ValueError):
            version_tuple(version)


def test_release_upload_requires_admin_csrf_signature_and_complete_bytes(
    tmp_path, monkeypatch
):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "LIVE_STUDIO_UPDATE_PUBLIC_KEY", encode(key.public_key().public_bytes_raw())
    )
    app = create_app(tmp_path, testing=True)
    service = app.extensions["license_service"]
    service.setup_admin("owner", "test-password-123")
    client = app.test_client()
    envelope = signed(key)
    header = base64.b64encode(json.dumps(envelope).encode()).decode()
    assert client.post("/api/admin/releases", data=b"test package").status_code == 401
    with client.session_transaction() as session:
        session.update(sid=service.login("owner", "test-password-123"), csrf="csrf")
    assert (
        client.post(
            "/api/admin/releases",
            headers={"X-Release-Manifest": header},
            data=b"test package",
        ).status_code
        == 403
    )
    headers = {
        "X-CSRF-Token": "csrf",
        "X-Release-Manifest": header,
        "Content-Type": "application/octet-stream",
    }
    assert (
        client.post(
            "/api/admin/releases", headers=headers, data=b"bad package!"
        ).status_code
        == 400
    )
    assert client.get("/api/releases/latest").status_code == 404
    # Larger than the old global 16 KiB body limit.
    data = b"package" * 10000
    envelope = signed(key, data)
    headers["X-Release-Manifest"] = base64.b64encode(
        json.dumps(envelope).encode()
    ).decode()
    assert (
        client.post("/api/admin/releases", headers=headers, data=data).status_code
        == 200
    )
    public_client = app.test_client()
    assert public_client.get("/api/releases/latest").json == envelope
    assert (
        public_client.get(
            "/api/releases/download/" + envelope["payload"]["sha256"] + ".zip"
        ).data
        == data
    )
    old = signed(key, b"old", "1.0.0")
    headers["X-Release-Manifest"] = base64.b64encode(json.dumps(old).encode()).decode()
    assert (
        client.post("/api/admin/releases", headers=headers, data=b"old").status_code
        == 409
    )
    assert public_client.get("/api/releases/latest").json == envelope
