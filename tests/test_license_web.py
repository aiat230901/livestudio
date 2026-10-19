import io
import re
import zipfile

import pytest

pytest.importorskip("flask")
pytest.importorskip("cryptography")
from license_server.app import create_app  # noqa: E402

PASSWORD = "Test-only-long-password-42"
DEVICE = "test_device_012345678901234567890123456789"


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "server", testing=True)


def csrf(client, path="/login"):
    response = client.get(path, follow_redirects=True)
    return re.search(rb'name="csrf-token" content="([^"]+)"', response.data)[1].decode()


def login(client):
    token = csrf(client, "/setup")
    client.post(
        "/setup",
        data=dict(csrf=token, username="owner", password=PASSWORD, confirm=PASSWORD),
    )
    token = csrf(client)
    assert (
        client.post(
            "/login", data=dict(csrf=token, username="owner", password=PASSWORD)
        ).status_code
        == 302
    )
    return {"X-CSRF-Token": csrf(client, "/admin")}


def test_admin_routes_are_protected_and_csrf_required(app):
    client = app.test_client()
    for path in [
        "/api/admin/licenses",
        "/api/admin/audit",
        "/api/admin/backup",
        "/api/admin/licenses/fake",
    ]:
        assert client.get(path).status_code == 401
    for path in [
        "/api/admin/licenses",
        "/api/admin/licenses/fake/renew",
        "/api/admin/licenses/fake/block",
        "/api/admin/licenses/fake/reset-device",
        "/api/admin/password",
    ]:
        assert client.post(path, json={}).status_code == 401
    headers = login(client)
    assert (
        client.post("/api/admin/licenses", json=dict(days=30, quantity=1)).status_code
        == 403
    )
    created = client.post(
        "/api/admin/licenses",
        headers=headers,
        json=dict(days=30, quantity=2, note="Khách thử"),
    )
    assert created.status_code == 201 and len(created.json["created"]) == 2
    assert client.get("/api/admin/licenses").json["total"] == 2
    assert (
        client.post(
            "/setup",
            data=dict(
                csrf=headers["X-CSRF-Token"],
                username="other",
                password=PASSWORD,
                confirm=PASSWORD,
            ),
        ).status_code
        == 302
    )


def test_activate_check_block_reset_via_http(app):
    client = app.test_client()
    headers = login(client)
    created = client.post(
        "/api/admin/licenses",
        headers=headers,
        json=dict(days=7, quantity=1, note="private note"),
    ).json["created"][0]
    public = app.test_client()
    active = public.post(
        "/api/license/activate", json=dict(key=created["key"], device_id=DEVICE)
    )
    assert active.status_code == 200 and "lease" in active.json
    assert "private note" not in active.get_data(as_text=True)
    check = dict(
        license_id=created["id"],
        device_id=DEVICE,
        activation_token=active.json["activation_token"],
    )
    assert public.post("/api/license/check", json=check).status_code == 200
    client.post(f"/api/admin/licenses/{created['id']}/block", headers=headers, json={})
    assert (
        public.post("/api/license/check", json=check).json["error"]["code"] == "blocked"
    )
    client.post(
        f"/api/admin/licenses/{created['id']}/unblock", headers=headers, json={}
    )
    client.post(
        f"/api/admin/licenses/{created['id']}/reset-device", headers=headers, json={}
    )
    assert (
        public.post("/api/license/check", json=check).json["error"]["code"]
        == "activation_revoked"
    )
    next_device = public.post(
        "/api/license/activate", json=dict(key=created["key"], device_id=DEVICE + "B")
    )
    assert next_device.status_code == 200
    assert (
        next_device.json["license"]["expires_at"]
        == active.json["license"]["expires_at"]
    )


def test_logout_and_password_change_revoke_sessions(app):
    client = app.test_client()
    headers = login(client)
    stolen = client.get_cookie("live_studio_admin").value
    assert (
        client.post("/logout", data=dict(csrf=headers["X-CSRF-Token"])).status_code
        == 302
    )
    attacker = app.test_client()
    attacker.set_cookie("live_studio_admin", stolen)
    assert attacker.get("/api/admin/licenses").status_code == 401
    headers = login(client)
    stolen = client.get_cookie("live_studio_admin").value
    assert (
        client.post(
            "/api/admin/password",
            headers=headers,
            json=dict(current=PASSWORD, new=PASSWORD + "new", confirm=PASSWORD + "new"),
        ).status_code
        == 200
    )
    attacker.set_cookie("live_studio_admin", stolen)
    assert attacker.get("/api/admin/licenses").status_code == 401


def test_backup_restore_preserves_data_and_signing_key(app, tmp_path):
    client = app.test_client()
    headers = login(client)
    client.post(
        "/api/admin/licenses",
        headers=headers,
        json=dict(days=3, quantity=1, note="Giữ dữ liệu"),
    )
    public = client.get("/api/license/public-key").json
    response = client.get("/api/admin/backup")
    assert response.status_code == 200 and response.headers[
        "Content-Disposition"
    ].startswith("attachment;")
    restored_dir = tmp_path / "restored"
    restored_dir.mkdir()
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert set(archive.namelist()) == {
            "license.sqlite3",
            "secrets.json",
            "RESTORE.txt",
        }
        for name in ("license.sqlite3", "secrets.json"):
            (restored_dir / name).write_bytes(archive.read(name))
    restored = create_app(restored_dir, testing=True)
    assert restored.test_client().get("/api/license/public-key").json == public
    assert restored.extensions["license_service"].list_keys()["total"] == 1


def test_limits_headers_escaping_and_unknown_host(app):
    client = app.test_client()
    headers = login(client)
    result = client.post(
        "/api/admin/licenses",
        headers=headers,
        json=dict(days=7, quantity=1, note="<script>alert(1)</script>"),
    )
    assert result.status_code == 201
    assert "<script>alert(1)</script>" not in client.get("/admin").get_data(
        as_text=True
    )
    assert client.get("/admin").headers["X-Frame-Options"] == "DENY"
    assert (
        "script-src 'self'" in client.get("/admin").headers["Content-Security-Policy"]
    )
    assert (
        client.get("/admin", headers={"Host": "untrusted.example"}).status_code == 400
    )
    assert (
        client.post(
            "/api/admin/licenses",
            headers=headers,
            data=b"x" * 20000,
            content_type="application/json",
        ).status_code
        == 413
    )
    for _ in range(10):
        client.post(
            "/login",
            data=dict(csrf=headers["X-CSRF-Token"], username="wrong", password="wrong"),
        )
    assert (
        client.post(
            "/login",
            data=dict(csrf=headers["X-CSRF-Token"], username="wrong", password="wrong"),
        ).status_code
        == 429
    )


def test_bad_csrf_and_private_paths_are_rejected(app):
    client = app.test_client()
    login(client)
    assert (
        client.post(
            "/api/admin/licenses", headers={"X-CSRF-Token": "không-hợp-lệ"}, json={}
        ).status_code
        == 403
    )
    for path in (
        "/secrets.json",
        "/license.sqlite3",
        "/.license-server/secrets.json",
        "/static/../secrets.json",
    ):
        assert client.get(path).status_code == 404


def test_password_whitespace_is_preserved_and_setup_cannot_be_claimed_twice(app):
    service = app.extensions["license_service"]
    password = "  A password with spaces  "
    service.setup_admin("owner", password)
    assert service.session_user(service.login("owner", password)) == "owner"
    from license_server.service import LicenseError

    with pytest.raises(LicenseError):
        service.setup_admin("second", password)


def test_secure_deployment_cookie_and_public_setup_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_STUDIO_TRUSTED_HOSTS", "licenses.example")
    app = create_app(tmp_path / "secure", testing=True, local=False)
    app.extensions["license_service"].setup_admin("owner", PASSWORD)
    client = app.test_client()
    response = client.get("/login", base_url="https://licenses.example")
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")
    assert client.get("/setup", base_url="https://licenses.example").status_code == 403


def test_existing_database_never_silently_replaces_missing_signing_key(app):
    path = app.extensions["license_service"].path.parent
    (path / "secrets.json").unlink()
    with pytest.raises(ValueError, match="secrets.json"):
        create_app(path, testing=True)
