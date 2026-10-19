"""Render the real Qt widgets, without network or user configuration changes."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PySide6.QtWidgets import QApplication  # noqa: E402
from desktop.manager import RecordingManager  # noqa: E402
from desktop.store import DesktopStore  # noqa: E402
from desktop.theme import apply_theme  # noqa: E402
from desktop.window import MainWindow  # noqa: E402
from desktop.dialogs import ChannelDialog, SettingsDialog  # noqa: E402


def main():
    app = QApplication([])
    apply_theme(app)
    store = DesktopStore(":memory:")
    for user in ("sacngockhang_official", "ungthaimenuochoa"):
        store.save_channel(user, 3600, None, False)
    manager = RecordingManager(store)
    window = MainWindow(store, manager)
    window.timer.stop()
    for width, height in ((1440, 900), (1100, 720)):
        window.resize(width, height)
        window.show()
        for index, name in enumerate(
            ("overview", "channels", "schedules", "history", "settings")
        ):
            window.navigate(index)
            app.processEvents()
            window.grab().save(str(ROOT / "diagnostics" / f"phase3-{name}-{width}.png"))
    window.tray.hide()
    window.hide()
    dialog = ChannelDialog()
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(ROOT / "diagnostics" / "phase3-add-channel-unlimited.png"))
    dialog.unlimited.setChecked(False)
    dialog.minutes.setValue(30)
    app.processEvents()
    dialog.grab().save(str(ROOT / "diagnostics" / "phase3-add-channel-limited.png"))
    dialog.reject()
    settings = SettingsDialog(None, window.settings())
    settings.show()
    app.processEvents()
    settings.grab().save(str(ROOT / "diagnostics" / "phase3-settings-dialog.png"))
    settings.reject()
    store.close()


if __name__ == "__main__":
    main()
