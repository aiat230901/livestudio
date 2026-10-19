"""HTTP check of the owned QA server; generated test credentials stay in memory."""

import io
import json
import re
import secrets
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from license_server.leases import verify_lease  # noqa: E402


def main():
    url = "http://127.0.0.1:8766"
    admin = requests.Session()
    setup = admin.get(url + "/setup", timeout=10)
    if setup.url.endswith("/login"):
        raise RuntimeError(
            "QA data already has an admin; use a fresh QA directory and port, never overwrite credentials."
        )
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', setup.text)[1]
    password = secrets.token_urlsafe(24)
    result = admin.post(
        url + "/setup",
        data=dict(csrf=csrf, username="qa_owner", password=password, confirm=password),
        timeout=10,
    )
    result.raise_for_status()
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', result.text)[1]
    result = admin.post(
        url + "/login",
        data=dict(csrf=csrf, username="qa_owner", password=password),
        timeout=10,
    )
    result.raise_for_status()
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', result.text)[1]
    admin.headers["X-CSRF-Token"] = csrf
    result = admin.post(
        url + "/api/admin/licenses",
        json=dict(days=7, quantity=2, note="Kiểm tra HTTP riêng"),
        timeout=10,
    )
    assert result.status_code == 201
    created = result.json()["created"]
    public = requests.Session()
    device = secrets.token_hex(32)
    active = public.post(
        url + "/api/license/activate",
        json=dict(key=created[0]["key"], device_id=device),
        timeout=10,
    )
    active.raise_for_status()
    active = active.json()
    public_key = public.get(url + "/api/license/public-key", timeout=10).json()[
        "public_key"
    ]
    assert (
        verify_lease(active["lease"], public_key, device)["license_id"]
        == created[0]["id"]
    )
    check = dict(
        license_id=created[0]["id"],
        device_id=device,
        activation_token=active["activation_token"],
    )
    assert (
        public.post(url + "/api/license/check", json=check, timeout=10).status_code
        == 200
    )
    assert (
        public.post(
            url + "/api/license/activate",
            json=dict(key=created[0]["key"], device_id=secrets.token_hex(32)),
            timeout=10,
        ).status_code
        == 409
    )
    expiry = active["license"]["expires_at"]
    for action in ("block", "unblock", "reset-device"):
        result = admin.post(
            url + f"/api/admin/licenses/{created[0]['id']}/{action}",
            json={},
            timeout=10,
        )
        result.raise_for_status()
        if action == "block":
            assert (
                public.post(url + "/api/license/check", json=check, timeout=10).json()[
                    "error"
                ]["code"]
                == "blocked"
            )
    assert (
        public.post(url + "/api/license/check", json=check, timeout=10).json()["error"][
            "code"
        ]
        == "activation_revoked"
    )
    result = public.post(
        url + "/api/license/activate",
        json=dict(key=created[0]["key"], device_id=secrets.token_hex(32)),
        timeout=10,
    )
    assert result.json()["license"]["expires_at"] == expiry
    result = admin.get(url + "/api/admin/backup", timeout=10)
    result.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(result.content)) as bundle:
        assert set(bundle.namelist()) == {
            "license.sqlite3",
            "secrets.json",
            "RESTORE.txt",
        }
    assert admin.get(url + "/api/admin/audit", timeout=10).json()["items"]
    result = admin.post(url + "/logout", data=dict(csrf=csrf), timeout=10)
    result.raise_for_status()
    assert admin.get(url + "/api/admin/licenses", timeout=10).status_code == 401
    report = dict(
        server="127.0.0.1:8766",
        setup_login=True,
        create_multiple_keys=True,
        activate_and_verify_signature=True,
        second_device_rejected=True,
        block_unblock=True,
        reset_revokes_old_activation=True,
        reset_preserves_expiry=True,
        backup_archive=True,
        audit=True,
        logout_revokes=True,
        browser_visual_check=False,
        browser_reason="No enabled browser surface in this session",
    )
    (ROOT / "diagnostics" / "phase5-http-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
