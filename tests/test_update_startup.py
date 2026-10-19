import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.mark.parametrize("failure", ["store", "window"])
def test_initialization_failure_never_acknowledges_update(
    tmp_path, monkeypatch, failure
):
    from desktop import app as launcher, licensing, store, window
    from license_server.app import create_app

    application = QApplication.instance() or QApplication([])
    assert application
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TIKTOK_RECORDER_DATA", str(tmp_path / "data"))
    ack = tmp_path / "ack.json"
    monkeypatch.setattr("sys.argv", ["LiveStudio.exe", "--update-ack", str(ack)])
    server = create_app(tmp_path / "server", testing=True)
    monkeypatch.setattr(
        licensing,
        "load_config",
        lambda: dict(
            version=1,
            server_url="http://127.0.0.1",
            public_key=server.extensions["license_signer"].public_key,
        ),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("Initialization failed")

    if failure == "store":
        monkeypatch.setattr(store, "DesktopStore", fail)
    else:
        monkeypatch.setattr(window, "MainWindow", fail)
    from desktop.license_dialog import LicenseDialog

    monkeypatch.setattr(LicenseDialog, "exec", lambda self: True)
    with pytest.raises(RuntimeError, match="Initialization failed"):
        launcher.main()
    assert not ack.exists()
