import os
import time
from concurrent.futures import Future
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget  # noqa: E402


def wait_for(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_slow_update_check_keeps_qt_responsive(monkeypatch):
    from desktop import update_dialog

    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.exiting = False
    release = Event()

    def network(config):
        assert release.wait(3)
        return None

    monkeypatch.setattr(update_dialog, "check_update", network)
    controller = update_dialog.UpdateController(window, QVBoxLayout(window))
    try:
        controller.check(True)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        wait_for(app, lambda: bool(heartbeat))
        assert controller.future is not None and not controller.future.done()
        release.set()
        wait_for(app, lambda: controller.future is None)
        assert controller.button.isEnabled()
    finally:
        release.set()
        controller.close()
        window.close()


def test_approved_update_waits_for_recording_workers_before_exit(tmp_path, monkeypatch):
    from desktop.window import MainWindow
    from tests.test_desktop_manager import setup, deliver

    app = QApplication.instance() or QApplication([])
    assert app
    store, manager = setup(tmp_path)
    manager.tick()
    deliver(manager, "one", "probe_done", room_id="room1")
    window = MainWindow(store, manager)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    controller = window.updates
    future = Future()
    future.set_result(tmp_path / "update")
    controller.future, controller.action = future, "download"
    try:
        controller.poll()
        assert window.exiting and manager.closing
        assert window.pending_update == tmp_path / "update"
        assert len(manager.jobs) == 2
        assert all(job["stop"].is_set() for job in manager.jobs.values())
        assert not window.centralWidget().isEnabled()
        deliver(
            manager,
            "one",
            "record_done",
            path=None,
            reason="user_stop",
            bytes_written=0,
        )
        assert len(manager.jobs) == 1
        deliver(manager, "two", "probe_done", room_id=None)
        window.on_tick()
        assert not manager.jobs
    finally:
        controller.close()
        window.timer.stop()
        window.tray.hide()
        window.hide()
        store.close()
