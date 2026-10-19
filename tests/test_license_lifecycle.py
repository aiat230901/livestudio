import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from license_server.service import LicenseError, LicenseService
from tests.test_license_web import login

DEVICE = "test_device_012345678901234567890123456789"


def test_unused_delete_preserves_hints_and_never_reactivates(tmp_path):
    service = LicenseService(tmp_path / "db")
    created = service.create_keys(30, 1, "customer", "owner")[0]
    service.set_blocked(created["id"], True, "owner")
    service.delete_unused(created["id"], "owner")
    assert service.list_keys()["total"] == 0
    with pytest.raises(LicenseError):
        service.activate(created["key"], DEVICE)
    audit = service.audit(created["id"])
    assert audit[0]["action"] == "key_deleted"
    assert all(row["key_hint"] == created["key_hint"] for row in audit)
    assert created["key"] not in json.dumps(service.export_audit())


def test_delete_racing_activation_has_only_one_winner(tmp_path):
    service = LicenseService(tmp_path / "race.db")
    created = service.create_keys(30, 1, "", "owner")[0]

    def operation(kind):
        try:
            if kind == "activate":
                service.activate(created["key"], DEVICE)
            else:
                service.delete_unused(created["id"], "owner")
            return kind
        except LicenseError as ex:
            return ex.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(operation, ("activate", "delete")))
    assert result in (["activate", "already_activated"], ["invalid_key", "delete"])


def test_archive_restore_requires_explicit_unblock_and_preserves_expiry(tmp_path):
    service = LicenseService(tmp_path / "db")
    created = service.create_keys(30, 1, "", "owner")[0]
    active = service.activate(created["key"], DEVICE)
    expiry = active["license"]["expires_at"]
    with pytest.raises(LicenseError) as error:
        service.delete_unused(created["id"], "owner")
    assert error.value.code == "already_activated"
    service.set_archived(created["id"], True, "owner")
    assert service.list_keys()["items"] == []
    assert service.list_keys(status="archived")["total"] == 1
    for operation in (
        lambda: service.check(created["id"], DEVICE, active["activation_token"]),
        lambda: service.activate(created["key"], DEVICE),
        lambda: service.set_blocked(created["id"], False, "owner"),
    ):
        with pytest.raises(LicenseError):
            operation()
    service.set_archived(created["id"], False, "owner")
    assert service.get_license(created["id"])["status"] == "blocked"
    service.set_blocked(created["id"], False, "owner")
    assert (
        service.check(created["id"], DEVICE, active["activation_token"])["license"][
            "expires_at"
        ]
        == expiry
    )


def test_cleanup_only_old_rows_and_records_itself(tmp_path):
    clock = [2_000_000_000]
    service = LicenseService(tmp_path / "db", clock=lambda: clock[0])
    key = service.create_keys(30, 1, "", "owner")[0]
    clock[0] += 181 * 86400
    service.set_note(key["id"], "keep me", "owner")
    preview = service.audit_cleanup_preview()
    assert preview["count"] == 1
    for value in (clock[0], float("nan"), True, None):
        with pytest.raises(LicenseError):
            service.clean_audit(value, "owner")
    assert service.clean_audit(preview["cutoff"], "owner") == 1
    assert {row["action"] for row in service.audit()} == {
        "audit_cleaned",
        "note_changed",
    }
    assert service.get_license(key["id"])["note"] == "keep me"
    assert service.audit_cleanup_preview()["count"] == 0


def test_old_schema_migrates_without_losing_data(tmp_path):
    service = LicenseService(tmp_path / "db")
    key = service.create_keys(7, 1, "preserve", "owner")[0]
    with sqlite3.connect(service.path) as db:
        db.execute("ALTER TABLE licenses DROP COLUMN archived")
        db.execute("ALTER TABLE audit DROP COLUMN key_hint")
    migrated = LicenseService(service.path)
    assert migrated.get_license(key["id"])["archived"] == 0
    assert migrated.audit()[0]["key_hint"] == key["key_hint"]


def test_new_admin_routes_require_auth_and_csrf_and_export_public_only(tmp_path):
    from license_server.app import create_app

    app = create_app(tmp_path / "server", testing=True)
    client = app.test_client()
    for route in ("audit/cleanup-preview", "audit/export", "client-config"):
        assert client.get("/api/admin/" + route).status_code == 401
    for route in (
        "audit/cleanup",
        "licenses/fake/archive",
        "licenses/fake/restore",
        "licenses/fake/delete",
    ):
        assert client.post("/api/admin/" + route, json={}).status_code == 401
    headers = login(client)
    for route in (
        "audit/cleanup",
        "licenses/fake/archive",
        "licenses/fake/restore",
        "licenses/fake/delete",
    ):
        assert client.post("/api/admin/" + route, json={}).status_code == 403
    created = client.post(
        "/api/admin/licenses", json=dict(days=30, quantity=1), headers=headers
    ).json["created"][0]
    assert client.post(
        f"/api/admin/licenses/{created['id']}/delete", json={}, headers=headers
    ).json["deleted"]
    assert (
        client.get("/api/admin/audit").json["items"][0]["key_hint"]
        == created["key_hint"]
    )
    assert client.get("/api/admin/audit/export").json[0]["action"] == "admin_setup"
    preview = client.get("/api/admin/audit/cleanup-preview").json
    assert (
        client.post(
            "/api/admin/audit/cleanup",
            json=dict(cutoff=preview["cutoff"]),
            headers=headers,
        ).json["deleted"]
        == 0
    )
    config = client.get("/api/admin/client-config").json
    assert set(config) == {"version", "server_url", "public_key"}
    assert config["public_key"] == app.extensions["license_signer"].public_key
