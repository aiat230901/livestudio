import io
import json
import zipfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.leases import encode
from tests.test_releases import signed


def package(tmp_path, extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        files = {
            "LiveStudio/LiveStudio.exe": b"new exe",
            "LiveStudio/LiveStudioUpdater.exe": b"helper",
            "LiveStudio/.livestudio-package.json": json.dumps(
                dict(product="LiveStudio", version="1.0.1")
            ).encode(),
        }
        files.update(extra or {})
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            info.filename = name
            bundle.writestr(info, data)
    path = tmp_path / "update.zip"
    path.write_bytes(buffer.getvalue())
    key = Ed25519PrivateKey.generate()
    return (
        path,
        signed(key, buffer.getvalue()),
        encode(key.public_key().public_bytes_raw()),
    )


def target_folder(tmp_path):
    target = tmp_path / "Installed tool"
    target.mkdir()
    (target / "LiveStudio.exe").write_bytes(b"old exe")
    (target / ".livestudio-package.json").write_text(
        json.dumps(dict(product="LiveStudio", version="1.0.0"))
    )
    return target


def test_replace_preserves_previous_folder_and_rolls_back_failed_startup(tmp_path):
    from desktop.updates import install_package

    archive, envelope, public = package(tmp_path)
    target = target_folder(tmp_path)
    unrelated = tmp_path / "state.db"
    unrelated.write_bytes(b"customer settings")
    backup = install_package(archive, envelope, public, target, lambda path: True)
    assert (target / "LiveStudio.exe").read_bytes() == b"new exe"
    assert (backup / "LiveStudio.exe").read_bytes() == b"old exe"
    assert unrelated.read_bytes() == b"customer settings"


def test_failed_new_exe_restores_previous_install(tmp_path):
    from desktop.updates import install_package

    archive, envelope, public = package(tmp_path)
    target = target_folder(tmp_path)
    with pytest.raises(ValueError, match="khôi phục"):
        install_package(archive, envelope, public, target, lambda path: False)
    assert (target / "LiveStudio.exe").read_bytes() == b"old exe"


def test_update_refuses_to_move_customer_files_inside_program_folder(tmp_path):
    from desktop.updates import install_package

    archive, envelope, public = package(tmp_path)
    target = target_folder(tmp_path)
    (target / ".livestudio-package.json").write_text(
        json.dumps(
            dict(product="LiveStudio", version="1.0.0", files=["LiveStudio.exe"])
        )
    )
    (target / "my-video.mp4").write_bytes(b"customer video")
    with pytest.raises(ValueError, match="tệp riêng"):
        install_package(archive, envelope, public, target, lambda path: True)
    assert (target / "my-video.mp4").read_bytes() == b"customer video"
    assert (target / "LiveStudio.exe").read_bytes() == b"old exe"


@pytest.mark.parametrize(
    "name",
    [
        "LiveStudio/../outside",
        "LiveStudio/C:/bad",
        "LiveStudio/CON.txt",
        "LiveStudio/x\\bad",
        "LiveStudio/test.",
        "LiveStudio/livestudio.EXE",
        "/LiveStudio/absolute",
    ],
)
def test_malicious_zip_never_changes_install(tmp_path, name):
    from desktop.updates import install_package

    archive, envelope, public = package(tmp_path, {name: b"bad"})
    target = target_folder(tmp_path)
    with pytest.raises(ValueError):
        install_package(archive, envelope, public, target, lambda path: True)
    assert (target / "LiveStudio.exe").read_bytes() == b"old exe"


def test_tampered_package_and_unmarked_folder_are_rejected(tmp_path):
    from desktop.updates import install_package

    archive, envelope, public = package(tmp_path)
    target = target_folder(tmp_path)
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError):
        install_package(archive, envelope, public, target, lambda path: True)
    assert (target / "LiveStudio.exe").read_bytes() == b"old exe"
    (target / ".livestudio-package.json").unlink()
    with pytest.raises(ValueError):
        install_package(archive, envelope, public, target, lambda path: True)


def test_real_http_update_check_and_download_verify_hash(tmp_path, monkeypatch):
    import base64
    from threading import Thread
    from werkzeug.serving import make_server
    from desktop.updates import check_update, download_update
    from license_server.app import create_app

    key = Ed25519PrivateKey.generate()
    public = encode(key.public_key().public_bytes_raw())
    monkeypatch.setenv("LIVE_STUDIO_UPDATE_PUBLIC_KEY", public)
    app = create_app(tmp_path / "server", testing=True)
    service = app.extensions["license_service"]
    service.setup_admin("owner", "test-password-123")
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(sid=service.login("owner", "test-password-123"), csrf="csrf")
    data = b"package" * 1000
    envelope = signed(key, data)
    header = base64.b64encode(json.dumps(envelope).encode()).decode()
    assert (
        client.post(
            "/api/admin/releases",
            headers={"X-CSRF-Token": "csrf", "X-Release-Manifest": header},
            data=data,
        ).status_code
        == 200
    )
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = dict(
        server_url=f"http://127.0.0.1:{server.server_port}",
        update_public_key=public,
        version="1.0.0",
    )
    try:
        assert check_update(config) == envelope
        progress = []
        work = download_update(config, envelope, tmp_path / "client", progress.append)
        assert (work / "release.zip").read_bytes() == data
        assert progress[-1] == 100
        from threading import Event

        cancel = Event()
        cancel.set()
        with pytest.raises(ValueError, match="hủy"):
            download_update(config, envelope, tmp_path / "cancelled", cancel=cancel)
        assert not list((tmp_path / "cancelled").rglob("*.zip"))
        config["version"] = "1.0.1"
        assert check_update(config) is None
        config["version"] = "1.0.0"
        (
            tmp_path / "server/releases" / (envelope["payload"]["sha256"] + ".zip")
        ).write_bytes(b"corrupted")
        with pytest.raises(ValueError):
            download_update(config, envelope, tmp_path / "bad-client")
        assert not list((tmp_path / "bad-client").rglob("*.zip"))
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
