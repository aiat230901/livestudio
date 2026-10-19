import base64
import io
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
import requests

from license_server.app import create_app


def test_hosted_restore_preserves_keys_and_admin_without_overwriting(
    tmp_path, monkeypatch
):
    from license_server.hosting import export_bootstrap, hosted_app

    original = create_app(tmp_path / "original", testing=True)
    service = original.extensions["license_service"]
    service.setup_admin("owner", "test-password-123")
    service.login("owner", "test-password-123")
    service.create_keys(60, 1, "Existing customer", "owner")
    public_key = original.extensions["license_signer"].public_key
    monkeypatch.setenv("LIVE_STUDIO_LICENSE_DATA", str(tmp_path / "hosted"))
    monkeypatch.setenv("LIVE_STUDIO_TRUSTED_HOSTS", "studio.example.com")
    monkeypatch.setenv(
        "LIVE_STUDIO_BOOTSTRAP_BACKUP", export_bootstrap(tmp_path / "original")
    )
    app = hosted_app()
    restored = app.extensions["license_service"]
    assert restored.has_admin()
    assert restored.login("owner", "test-password-123")
    assert app.extensions["license_signer"].public_key == public_key
    assert app.config["SESSION_COOKIE_SECURE"] is True
    with restored.connection() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
        assert (
            db.execute("SELECT note FROM licenses").fetchone()[0] == "Existing customer"
        )
    client = app.test_client()
    assert (
        client.get("/health", base_url="https://studio.example.com").status_code == 200
    )
    assert client.get("/health", base_url="http://127.0.0.1:3000").status_code == 200
    assert client.get("/health", base_url="https://evil.example.com").status_code == 400
    assert (
        client.get("/setup", base_url="https://studio.example.com").status_code == 403
    )
    restored.create_keys(30, 1, "Created on hosting", "owner")
    monkeypatch.setenv("LIVE_STUDIO_BOOTSTRAP_BACKUP", "obsolete-invalid-backup")
    again = hosted_app()
    with again.extensions["license_service"].connection() as db:
        assert db.execute("SELECT count(*) FROM licenses").fetchone()[0] == 2


def test_hosted_start_requires_configuration_before_creating_data(
    tmp_path, monkeypatch
):
    from license_server.hosting import hosted_app

    directory = tmp_path / "hosted"
    monkeypatch.setenv("LIVE_STUDIO_LICENSE_DATA", str(directory))
    monkeypatch.delenv("LIVE_STUDIO_TRUSTED_HOSTS", raising=False)
    with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
        hosted_app()
    assert not directory.exists()


@pytest.mark.parametrize("bad", ["not-base64", "unexpected-file", "missing-file"])
def test_restore_rejects_bad_backup_without_creating_database(
    tmp_path, monkeypatch, bad
):
    from license_server.hosting import hosted_app

    if bad != "not-base64":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr(
                "../secrets.json" if bad == "unexpected-file" else "secrets.json", "{}"
            )
        bad = base64.b64encode(buffer.getvalue()).decode()
    directory = tmp_path / "hosted"
    monkeypatch.setenv("LIVE_STUDIO_LICENSE_DATA", str(directory))
    monkeypatch.setenv("LIVE_STUDIO_TRUSTED_HOSTS", "studio.example.com")
    monkeypatch.setenv("LIVE_STUDIO_BOOTSTRAP_BACKUP", bad)
    with pytest.raises(ValueError, match="backup"):
        hosted_app()
    assert not (directory / "license.sqlite3").exists()


@pytest.mark.skipif(
    os.environ.get("LIVE_STUDIO_TEST_DOCKER") != "1",
    reason="Docker smoke test runs in hosting CI",
)
def test_container_serves_http_and_restarts_with_persistent_data(tmp_path):
    from license_server.hosting import export_bootstrap

    assert shutil.which("docker"), "Docker is required for the hosting CI check"
    original = create_app(tmp_path / "original", testing=True)
    original.extensions["license_service"].setup_admin("owner", "test-password-123")
    encoded = export_bootstrap(tmp_path / "original")
    data = tmp_path / "data"
    data.mkdir()
    root = Path(__file__).resolve().parents[1]

    def docker(*args):
        return subprocess.run(
            ["docker", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=240,
        ).stdout.strip()

    docker("build", "-t", "live-studio-hosting-test", ".")
    container = docker(
        "run",
        "-d",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-p",
        "127.0.0.1::3000",
        "-v",
        f"{data}:/app/data",
        "-e",
        "LIVE_STUDIO_TRUSTED_HOSTS=studio.example.com",
        "-e",
        f"LIVE_STUDIO_BOOTSTRAP_BACKUP={encoded}",
        "live-studio-hosting-test",
    )
    try:
        address = docker("port", container, "3000/tcp").splitlines()[0]
        url = "http://" + address

        def health():
            for _ in range(40):
                try:
                    response = requests.get(url + "/health", timeout=1)
                    if response.status_code == 200:
                        return response.json()
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            pytest.fail(
                "Container did not become healthy: " + docker("logs", container)
            )

        assert health()["service"] == "live-studio-license"
        assert requests.get(url + "/setup", timeout=3).status_code == 403
        assert requests.get(url + "/api/admin/licenses", timeout=3).status_code == 401
        signing_key = (data / "secrets.json").read_bytes()
        docker("restart", container)
        # Docker may assign a different ephemeral host port after a restart.
        url = "http://" + docker("port", container, "3000/tcp").splitlines()[0]
        assert health()["status"] == "ok"
        assert (data / "secrets.json").read_bytes() == signing_key
    finally:
        docker("rm", "-f", container)
