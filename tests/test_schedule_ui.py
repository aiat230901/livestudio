import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QTime  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from desktop.dialogs import ChannelDialog  # noqa: E402
from desktop.schedule_dialog import ScheduleDialog  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from desktop.manager import RecordingManager  # noqa: E402
from desktop.window import MainWindow  # noqa: E402
from desktop.theme import apply_theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def test_weekly_validation_and_overnight(app):
    dialog = ScheduleDialog()
    dialog.kind.setCurrentIndex(1)
    for day in dialog.days:
        day.setChecked(False)
    dialog.accept()
    assert dialog.result() == 0 and dialog.error.text()
    dialog.days[0].setChecked(True)
    dialog.weekly_start.setTime(QTime(22, 0))
    dialog.weekly_end.setTime(QTime(22, 0))
    dialog.accept()
    assert dialog.result() == 0
    dialog.weekly_end.setTime(QTime(2, 0))
    dialog.accept()
    assert dialog.value == dict(
        kind="weekly", days=[0], start_minute=1320, end_minute=120
    )


def test_once_widget_is_explicitly_utc7_and_rejects_reversed_range(app):
    initial = dict(kind="once", start=1792414800, end=1792418400)
    dialog = ScheduleDialog(initial=initial)
    assert dialog.once_start.dateTime().offsetFromUtc() == 25200
    assert dialog.once_start.dateTime().toSecsSinceEpoch() == initial["start"]
    dialog.once_end.setDateTime(dialog.once_start.dateTime())
    dialog.accept()
    assert dialog.result() == 0 and dialog.error.text()
    dialog.once_end.setDateTime(dialog.once_start.dateTime().addSecs(3600))
    dialog.accept()
    assert dialog.value == initial


def test_channel_requires_schedule_and_cancel_does_not_modify_original(app):
    dialog = ChannelDialog()
    dialog.user.setText("channel")
    dialog.mode.setCurrentIndex(1)
    dialog.accept()
    assert dialog.result() == 0 and "khung giờ" in dialog.error.text()
    rule = dict(kind="weekly", days=[0], start_minute=1320, end_minute=120)
    dialog.schedule_editor.schedules.append(rule)
    dialog.accept()
    assert dialog.value["mode"] == "scheduled"
    initial = dict(dialog.value)
    editor = ChannelDialog(initial=initial)
    editor.schedule_editor.schedules[0]["days"].append(1)
    editor.reject()
    assert initial["schedules"][0]["days"] == [0]


def test_schedule_page_add_edit_delete_keeps_other_channel_and_budget(
    app, tmp_path, monkeypatch
):
    import desktop.schedule_page as module

    store = DesktopStore(tmp_path / "ui.db")
    store.save_channel("one", 3600, str(tmp_path), False)
    store.save_channel("two", None, None, False)
    store.save_session("one", "room", 10, 3610, "active")
    manager = RecordingManager(store, clock=lambda: 100)
    window = MainWindow(store, manager)
    window.timer.stop()
    page = window.schedule_page
    value = dict(kind="once", start=200, end=300)

    class Dialog:
        accepted = False

        def __init__(self, *args):
            self.value = value.copy()

        def exec(self):
            return self.accepted

    monkeypatch.setattr(module, "ScheduleDialog", Dialog)
    page.add_rule()
    assert store.list_channels()[0]["mode"] == "continuous"
    Dialog.accepted = True
    page.add_rule()
    assert page.table.rowCount() == 1
    one, two = store.list_channels()
    assert one["mode"] == "scheduled" and two["mode"] == "continuous"
    assert one["duration_seconds"] == 3600 and one["output"] == str(tmp_path)
    page.table.selectRow(0)
    value["end"] = 400
    page.edit_rule()
    assert store.list_channels()[0]["schedules"][0]["end"] == 400
    assert page.selected() == ("one", 0)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    page.delete_rule()
    assert page.table.rowCount() == 0
    assert store.list_channels()[0]["mode"] == "scheduled"
    assert store.get_session("one", "room")["deadline_utc"] == 3610
    window.tray.hide()
    window.deleteLater()
    store.close()
