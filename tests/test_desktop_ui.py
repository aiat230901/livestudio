import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from desktop.manager import RecordingManager  # noqa: E402
from desktop.window import MainWindow  # noqa: E402
from desktop.dialogs import ChannelDialog  # noqa: E402
from desktop.theme import apply_theme  # noqa: E402
from desktop.dialogs import SettingsDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def test_dialog_validation_and_cancel(app):
    dialog = ChannelDialog()
    dialog.user.setText("../bad")
    dialog.accept()
    assert dialog.result() == 0
    assert dialog.error.text()
    dialog.user.setText("@valid")
    dialog.unlimited.setChecked(False)
    dialog.minutes.setValue(30)
    dialog.accept()
    assert dialog.value["duration_seconds"] == 1800
    assert dialog.value["username"] == "valid"


def test_time_arrows_click_and_disabled_state(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle, QStyleOptionSpinBox

    dialog = ChannelDialog()
    dialog.show()
    app.processEvents()
    assert not dialog.hours.isEnabled()
    dialog.unlimited.setChecked(False)
    assert dialog.hours.isEnabled()
    option = QStyleOptionSpinBox()
    dialog.hours.initStyleOption(option)
    for control, expected in (
        (QStyle.SubControl.SC_SpinBoxUp, 1),
        (QStyle.SubControl.SC_SpinBoxDown, 0),
    ):
        rect = dialog.hours.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option, control, dialog.hours
        )
        QTest.mouseClick(dialog.hours, Qt.MouseButton.LeftButton, pos=rect.center())
        assert dialog.hours.value() == expected
    dialog.unlimited.setChecked(True)
    assert not dialog.hours.isEnabled()
    dialog.reject()


def test_empty_and_real_stats(app, tmp_path):
    store = DesktopStore(tmp_path / "state.db")
    manager = RecordingManager(store)
    window = MainWindow(store, manager)
    window.timer.stop()
    assert "Thêm kênh" in window.empty.text()
    store.save_channel("channel", 1800, str(tmp_path), False)
    window.refresh()
    assert window.channels.rowCount() == 1
    assert window.stat_values[0].text() == "1"
    window.channels.selectRow(0)
    window.pages.setCurrentIndex(1)
    window.refresh()
    assert window.selected_user() == "channel"
    window.tray.hide()
    window.deleteLater()
    store.close()


def test_settings_round_trip_without_startup_side_effects(app, tmp_path):
    store = DesktopStore(tmp_path / "settings.db")
    initial = dict(
        output=str(tmp_path), interval=120, notifications=True, startup=False
    )
    dialog = SettingsDialog(None, initial)
    dialog.interval.setValue(5)
    dialog.folder.edit.setText(str(tmp_path / "Video có dấu"))
    dialog.accept()
    for key, value in dialog.value.items():
        store.set_setting(key, value)
    assert store.get_setting("interval") == 300
    assert store.get_setting("output").endswith("Video có dấu")
    assert store.get_setting("startup") is False
    store.close()


def test_add_cancel_duplicate_edit_delete_and_folder_picker(app, tmp_path, monkeypatch):
    import desktop.window as module
    from desktop.dialogs import FolderField
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    store = DesktopStore(tmp_path / "actions.db")
    manager = RecordingManager(store)
    window = MainWindow(store, manager)
    window.timer.stop()
    values = dict(
        username="new_channel", duration_seconds=600, output=None, enabled=False
    )

    class Dialog:
        accepted = False

        def __init__(self, *args):
            self.value = values.copy()

        def exec(self):
            return self.accepted

    monkeypatch.setattr(module, "ChannelDialog", Dialog)
    window.add_channel()
    assert not store.list_channels()
    Dialog.accepted = True
    window.add_channel()
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    window.add_channel()
    assert len(store.list_channels()) == 1
    window.channels.selectRow(0)
    values["duration_seconds"] = 1200
    window.edit_channel()
    assert store.list_channels()[0]["duration_seconds"] == 1200
    field = FolderField()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path)
    )
    field.choose()
    assert field.edit.text() == str(tmp_path)
    store.save_session("new_channel", "old_room", 10, 20, "completed")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    window.delete_channel()
    assert not store.list_channels()
    assert store.get_session("new_channel", "old_room")["state"] == "completed"
    window.tray.hide()
    window.deleteLater()
    store.close()
