import os
from threading import Event
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from desktop.license_dialog import LicenseController, LicenseDialog  # noqa: E402
from desktop.licensing import LicenseClient  # noqa: E402
from desktop.theme import apply_theme  # noqa: E402
from license_server.app import create_app  # noqa: E402


def wait_for(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_activation_dialog_keeps_qt_responsive_and_accepts_only_valid_license(tmp_path):
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    server = create_app(tmp_path / "server", testing=True)
    service = server.extensions["license_service"]
    signer = server.extensions["license_signer"]
    key = service.create_keys(1, 1, "", "owner")[0]
    release = Event()

    def request(action, payload):
        assert release.wait(3)
        return service.activate(payload["key"], payload["device_id"], signer)

    client = LicenseClient(
        tmp_path / "client",
        dict(version=1, server_url="http://127.0.0.1", public_key=signer.public_key),
        device="test_device_012345678901234567890123456789",
        seal=lambda data, **kwargs: data,
        request=request,
    )
    controller = LicenseController(client)
    dialog = LicenseDialog(controller)
    try:
        wait_for(app, lambda: controller.future is None)
        dialog.key.setText(key["key"])
        dialog.activate_key()
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        wait_for(app, lambda: bool(heartbeat))
        assert controller.future is not None and not controller.allowed()
        assert dialog.key.text() == "" and not dialog.activate.isEnabled()
        release.set()
        wait_for(app, lambda: dialog.result() == QDialog.DialogCode.Accepted)
        assert controller.allowed()
        assert "Hết hạn" in controller.summary()
    finally:
        release.set()
        dialog.reject()
        controller.close()
