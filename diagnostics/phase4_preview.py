"""Preview phase 4 widgets with temporary examples; never starts a worker."""

import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtWidgets import QApplication  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from desktop.manager import RecordingManager  # noqa: E402
from desktop.theme import apply_theme  # noqa: E402
from desktop.window import MainWindow  # noqa: E402
from desktop.dialogs import ChannelDialog  # noqa: E402
from desktop.schedule_dialog import ScheduleDialog  # noqa: E402


def main():
    app = QApplication([])
    apply_theme(app)
    now = time.time()
    rule = dict(
        kind="once", start=int(now // 60 * 60) + 600, end=int(now // 60 * 60) + 4200
    )
    weekly = dict(kind="weekly", days=[0, 2, 4], start_minute=1320, end_minute=120)
    store = DesktopStore(":memory:")
    store.save_channel(
        "sacngockhang_official",
        3600,
        None,
        True,
        mode="scheduled",
        schedules=[rule, weekly],
    )
    store.save_channel("ungthaimenuochoa", None, None, False)
    window = MainWindow(store, RecordingManager(store))
    window.timer.stop()
    for width, height in ((1440, 900), (1100, 720)):
        window.resize(width, height)
        window.show()
        for index, name in enumerate(
            ("overview", "channels", "schedules", "history", "settings")
        ):
            window.navigate(index)
            app.processEvents()
            window.grab().save(str(ROOT / "diagnostics" / f"phase4-{name}-{width}.png"))
    window.hide()
    window.tray.hide()
    for name, dialog in (
        ("channel", ChannelDialog(initial=store.list_channels()[0])),
        ("once", ScheduleDialog(initial=rule)),
        ("weekly", ScheduleDialog(initial=weekly)),
    ):
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(ROOT / "diagnostics" / f"phase4-dialog-{name}.png"))
        dialog.reject()
    store.close()


if __name__ == "__main__":
    main()
