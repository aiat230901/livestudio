from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("cryptography")
pytest.importorskip("flask")
from license_server.service import LicenseError, LicenseService  # noqa: E402
from license_server.leases import verify_lease  # noqa: E402


@pytest.fixture
def service(tmp_path):
    clock = [1000000.0]
    service = LicenseService(tmp_path / "license.db", clock=lambda: clock[0])
    service.test_clock = clock
    return service


def test_creation_activation_and_same_device_do_not_reset_expiry(service):
    created = service.create_keys(30, 1, "Khách đầu tiên", "admin")[0]
    before = service.get_license(created["id"])
    assert before["activated_at"] is None and before["expires_at"] is None
    activated = service.activate(
        created["key"], "device_A_012345678901234567890123456789"
    )
    expiry = activated["license"]["expires_at"]
    assert expiry == 1000000 + 30 * 86400
    service.test_clock[0] += 86400
    again = service.activate(created["key"], "device_A_012345678901234567890123456789")
    assert again["license"]["expires_at"] == expiry
    with pytest.raises(LicenseError) as ex:
        service.activate(created["key"], "device_B_012345678901234567890123456789")
    assert ex.value.code == "device_mismatch"


def test_concurrent_two_device_activation_has_only_one_winner(service):
    key = service.create_keys(7, 1, "", "admin")[0]["key"]

    def attempt(device):
        try:
            return service.activate(key, device)["license"]["id"]
        except LicenseError as ex:
            return ex.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                attempt,
                [
                    "device_A_012345678901234567890123456789",
                    "device_B_012345678901234567890123456789",
                ],
            )
        )
    assert results.count("device_mismatch") == 1


def test_reset_block_and_renewal(service):
    created = service.create_keys(2, 1, "", "admin")[0]
    device = "device_A_012345678901234567890123456789"
    activated = service.activate(created["key"], device)
    expiry = activated["license"]["expires_at"]
    service.set_blocked(created["id"], True, "admin")
    with pytest.raises(LicenseError, match="khóa"):
        service.check(created["id"], device, activated["activation_token"])
    service.set_blocked(created["id"], False, "admin")
    service.renew(created["id"], 3, "admin")
    assert service.get_license(created["id"])["expires_at"] == expiry + 3 * 86400
    service.reset_device(created["id"], "admin")
    with pytest.raises(LicenseError) as ex:
        service.check(created["id"], device, activated["activation_token"])
    assert ex.value.code == "activation_revoked"
    service.test_clock[0] = expiry + 10 * 86400
    service.renew(created["id"], 7, "admin")
    assert (
        service.get_license(created["id"])["expires_at"]
        == service.test_clock[0] + 7 * 86400
    )


def test_unactivated_renewal_extends_plan_without_starting_clock(service):
    created = service.create_keys(7, 1, "", "admin")[0]
    service.renew(created["id"], 3, "admin")
    row = service.get_license(created["id"])
    assert row["duration_days"] == 10 and row["expires_at"] is None


def test_signed_lease_tamper_device_and_offline_expiry(service):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from license_server.leases import LicenseSigner

    signer = LicenseSigner(Ed25519PrivateKey.generate().private_bytes_raw())
    created = service.create_keys(7, 1, "private admin note", "admin")[0]
    device = "device_A_012345678901234567890123456789"
    result = service.activate(created["key"], device, signer)
    assert "note" not in result["license"]
    claims = verify_lease(
        result["lease"], signer.public_key, device, now=service.clock()
    )
    assert claims["offline_until"] == service.clock() + 86400
    with pytest.raises(ValueError):
        verify_lease(
            result["lease"], signer.public_key, device, now=claims["offline_until"]
        )
    with pytest.raises(ValueError):
        verify_lease(
            result["lease"], signer.public_key, device + "other", now=service.clock()
        )
    token = result["lease"].split(".")
    token[1] = ("B" if token[1][0] != "B" else "A") + token[1][1:]
    with pytest.raises(ValueError):
        verify_lease(".".join(token), signer.public_key, device, now=service.clock())


def test_expired_key_cannot_use_grace_to_extend_expiry(service):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from license_server.leases import LicenseSigner

    signer = LicenseSigner(Ed25519PrivateKey.generate().private_bytes_raw())
    created = service.create_keys(1, 1, "", "admin")[0]
    device = "device_A_012345678901234567890123456789"
    activated = service.activate(created["key"], device, signer)
    service.test_clock[0] += 86000
    refreshed = service.check(
        created["id"], device, activated["activation_token"], signer
    )
    claims = verify_lease(
        refreshed["lease"], signer.public_key, device, now=service.clock()
    )
    assert claims["offline_until"] == activated["license"]["expires_at"]
    service.test_clock[0] += 400
    with pytest.raises(LicenseError) as ex:
        service.check(created["id"], device, activated["activation_token"], signer)
    assert ex.value.code == "expired"
    with pytest.raises(ValueError):
        verify_lease(refreshed["lease"], signer.public_key, device, now=service.clock())


def test_database_and_audit_never_contain_raw_credentials(service):
    created = service.create_keys(7, 1, "", "admin")[0]
    device = "device_A_012345678901234567890123456789"
    result = service.activate(created["key"], device)
    with service.connection() as db:
        dump = "\n".join(db.iterdump())
    for secret in (created["key"], device, result["activation_token"]):
        assert secret not in dump
    assert len(service.audit(created["id"])) == 2


@pytest.mark.parametrize(
    "days,quantity,note",
    [(0, 1, ""), (1, 101, ""), (True, 1, ""), (1, True, ""), (1, 1, "x" * 1001)],
)
def test_invalid_admin_input_is_atomic(service, days, quantity, note):
    with pytest.raises(LicenseError):
        service.create_keys(days, quantity, note, "admin")
    assert service.list_keys()["total"] == 0


def test_search_vietnamese_casefold_literal_wildcards_and_filters(service):
    created = service.create_keys(30, 1, "Khách NGỌC _100%", "admin")[0]
    assert service.list_keys("ngọc")["total"] == 1
    assert service.list_keys("_100%")["total"] == 1
    assert service.list_keys("_200%")["total"] == 0
    assert service.list_keys(status="active")["total"] == 0
    service.set_blocked(created["id"], True, "admin")
    assert service.list_keys(status="blocked")["total"] == 1
    assert service.list_keys(status="pending")["total"] == 0
