"""Native Windows Qt smoke check; no network or startup registration."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["TIKTOK_RECORDER_DATA"] = str(ROOT / "diagnostics" / "phase3-gui-data")
from PySide6.QtCore import QLockFile, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402
from desktop import app as desktop_app  # noqa: E402
from desktop.dialogs import ChannelDialog  # noqa: E402
from desktop.schedule_dialog import ScheduleDialog  # noqa: E402


def main():
    original_exec = QApplication.exec
    report = {}

    def run_loop(self):
        def check():
            try:
                window = next(
                    w
                    for w in self.topLevelWidgets()
                    if w.__class__.__name__ == "MainWindow"
                )
                lock = QLockFile(
                    str(Path(os.environ["TIKTOK_RECORDER_DATA"]) / "application.lock")
                )
                report["second_instance_blocked"] = not lock.tryLock(0)
                window.timer.stop()
                window.nav[1].setFocus()
                QTest.keyClick(window.nav[1], Qt.Key.Key_Space)
                report["keyboard_navigation"] = window.pages.currentIndex() == 1
                window.navigate(0)
                window.grab().save(
                    str(ROOT / "diagnostics" / "phase3-native-window.png")
                )
                report["native_visible"] = window.isVisible()
                report["tray_available"] = QSystemTrayIcon.isSystemTrayAvailable()
                if window.tray.isVisible():
                    window.close()
                    report["close_to_tray"] = not window.isVisible()
                    window.restore()
                    report["restore_from_tray"] = window.isVisible()
                dialog = ChannelDialog(window)
                dialog.show()
                self.processEvents()
                dialog.grab().save(
                    str(ROOT / "diagnostics" / "ui-polish-native-unlimited.png")
                )
                dialog.unlimited.setChecked(False)
                dialog.minutes.setValue(30)
                self.processEvents()
                dialog.grab().save(
                    str(ROOT / "diagnostics" / "ui-polish-native-limited.png")
                )
                dialog.reject()
                window.navigate(2)
                self.processEvents()
                window.grab().save(
                    str(ROOT / "diagnostics" / "phase4-native-schedules.png")
                )
                scheduled = ScheduleDialog(window)
                scheduled.show()
                self.processEvents()
                report["schedule_utc7"] = (
                    scheduled.once_start.dateTime().offsetFromUtc() == 25200
                )
                scheduled.grab().save(
                    str(ROOT / "diagnostics" / "phase4-native-once.png")
                )
                scheduled.kind.setCurrentIndex(1)
                self.processEvents()
                scheduled.grab().save(
                    str(ROOT / "diagnostics" / "phase4-native-weekly.png")
                )
                scheduled.reject()
                window.request_exit()
                report["graceful_exit"] = window.exiting and not window.manager.jobs
            except Exception as ex:
                report["error"] = repr(ex)
                self.quit()

        QTimer.singleShot(700, check)
        return original_exec()

    QApplication.exec = run_loop
    code = desktop_app.main()
    (ROOT / "diagnostics" / "phase3-gui-smoke.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))
    return code if all(report.values()) and "error" not in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
