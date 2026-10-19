import json
import sys
from threading import Thread

import pytest
from werkzeug.serving import make_server

from desktop.licensing import (
    LicenseClient,
    LicenseDenied,
    ServerUnavailable,
    device_identity,
    load_config,
    protect_data,
)
from license_server.app import create_app

DEVICE = "test_device_012345678901234567890123456789"


def plaintext_seal(data, decrypt=False):
    return data


@pytest.fixture
def world(tmp_path):
    clock = [2_000_000_000]
    app = create_app(tmp_path / "server", testing=True, clock=lambda: clock[0])
    service = app.extensions["license_service"]
    signer = app.extensions["license_signer"]
    key = service.create_keys(7, 1, "", "owner")[0]
    config = dict(
        version=1, server_url="http://127.0.0.1:8765", public_key=signer.public_key
    )

    def request(action, data):
        try:
            if action == "activate":
                return service.activate(data["key"], data["device_id"], signer)
            return service.check(
                data["license_id"], data["device_id"], data["activation_token"], signer
            )
        except Exception as ex:
            raise LicenseDenied(str(ex)) from ex

    def client(folder="client", device=DEVICE):
        return LicenseClient(
            tmp_path / folder,
            config,
            device=device,
            wall=lambda: clock[0],
            monotonic=lambda: clock[0],
            seal=plaintext_seal,
            request=request,
        )

    return clock, service, key, client, request, config


def offline(*args):
    raise ServerUnavailable("offline")


def test_activation_one_device_restart_and_signed_cache(world):
    clock, service, key, factory, request, config = world
    client = factory()
    assert not client.allowed()
    assert client.activate(key["key"])
    assert client.allowed()
    assert key["key"] not in client.path.read_text()
    assert not factory("second", DEVICE + "B").activate(key["key"])
    restarted = factory()
    assert not restarted.allowed()  # Startup always checks the server first.
    assert restarted.refresh()
    assert restarted.claims["expires_at"] == client.claims["expires_at"]
    clock[0] += 901
    assert restarted.refresh()


def test_block_denial_persists_across_offline_restart_then_unblock(world):
    _, service, key, factory, _, _ = world
    client = factory()
    assert client.activate(key["key"])
    service.set_blocked(key["id"], True, "owner")
    assert not client.refresh()
    assert "lease" not in json.loads(client.path.read_text())
    restarted = factory()
    restarted.request = offline
    assert not restarted.refresh()
    service.set_blocked(key["id"], False, "owner")
    assert factory().refresh()


def test_offline_has_hard_24_hour_cap_and_does_not_renew_itself(world):
    clock, _, key, factory, _, _ = world
    client = factory()
    assert client.activate(key["key"])
    deadline = client.claims["offline_until"]
    clock[0] += 900
    client.request = offline
    assert client.refresh() and client.mode == "offline"
    client.checkpoint()
    clock[0] = deadline - 1
    restarted = factory()
    restarted.request = offline
    assert restarted.refresh()
    clock[0] = deadline
    assert not restarted.allowed()
    assert not restarted.refresh()


def test_expiry_renewal_reset_archive_and_restore(world):
    clock, service, key, factory, _, _ = world
    client = factory()
    assert client.activate(key["key"])
    original_expiry = client.claims["expires_at"]
    service.reset_device(key["id"], "owner")
    assert not client.refresh()
    replacement = factory("replacement", DEVICE + "B")
    assert replacement.activate(key["key"])
    assert replacement.claims["expires_at"] == original_expiry
    service.set_archived(key["id"], True, "owner")
    assert not replacement.refresh()
    service.set_archived(key["id"], False, "owner")
    assert not replacement.refresh()
    service.set_blocked(key["id"], False, "owner")
    assert replacement.refresh()
    clock[0] = original_expiry
    assert not replacement.allowed()
    assert not replacement.refresh()
    service.renew(key["id"], 2, "owner")
    assert replacement.refresh()


def test_clock_rollback_online_reanchors_but_offline_cannot_bypass(world):
    clock, _, key, factory, _, _ = world
    client = factory()
    assert client.activate(key["key"])
    clock[0] += 600
    client.checkpoint()
    clock[0] -= 3600
    assert not client.allowed()
    restarted = factory()
    restarted.request = offline
    assert not restarted.refresh()


def test_tampered_or_wrong_server_lease_is_rejected_without_offline_fallback(world):
    _, _, key, factory, request, _ = world
    client = factory()
    assert client.activate(key["key"])

    def tamper(action, payload):
        result = request(action, payload)
        parts = result["lease"].split(".")
        parts[2] = "A" + parts[2][1:] if parts[2][0] != "A" else "B" + parts[2][1:]
        result["lease"] = ".".join(parts)
        return result

    client.request = tamper
    assert not client.refresh()
    assert client.mode == "denied" and "lease" not in client.state


def test_config_requires_pinned_key_and_secure_remote_transport(tmp_path, world):
    config = world[-1]
    path = tmp_path / "config.json"
    for url in (
        "http://remote.example",
        "https://user:pass@example.com",
        "https://example.com/?token=x",
        "file:///tmp/license",
    ):
        path.write_text(json.dumps(dict(config, server_url=url)))
        with pytest.raises(LicenseDenied):
            load_config(path)
    for url in ("http://127.0.0.1:8765", "https://licenses.example"):
        path.write_text(json.dumps(dict(config, server_url=url)))
        assert load_config(path)["public_key"] == config["public_key"]


@pytest.mark.parametrize("invalid", [[], "bad", {"wall": float("nan")}, {"wall": None}])
def test_corrupt_cached_state_never_grants_access(world, invalid):
    _, _, _, factory, _, config = world
    client = factory()
    if isinstance(invalid, dict):
        invalid["config"] = client.fingerprint
    client.path.parent.mkdir(parents=True)
    client.path.write_text(json.dumps(invalid))
    restarted = factory()
    restarted.request = offline
    assert not restarted.allowed() and not restarted.refresh()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_windows_dpapi_roundtrip_and_stable_machine_identity():
    secret = b"test-only-activation-token"
    encrypted = protect_data(secret)
    assert secret not in encrypted and protect_data(encrypted, decrypt=True) == secret
    assert len(device_identity()) == 64 and device_identity() == device_identity()
    with pytest.raises(OSError):
        protect_data(b"invalid encrypted blob", decrypt=True)


def test_real_http_client_blocks_and_never_falls_back_on_explicit_denial(tmp_path):
    app = create_app(tmp_path / "server", testing=True)
    service = app.extensions["license_service"]
    key = service.create_keys(1, 1, "", "owner")[0]
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = LicenseClient(
            tmp_path / "client",
            dict(
                version=1,
                server_url=f"http://127.0.0.1:{server.server_port}",
                public_key=app.extensions["license_signer"].public_key,
            ),
            device=DEVICE,
            seal=plaintext_seal,
        )
        assert client.activate(key["key"])
        assert client.refresh()
        service.set_blocked(key["id"], True, "owner")
        assert not client.refresh()
        assert "khóa" in client.message
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
