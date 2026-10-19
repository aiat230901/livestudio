import multiprocessing
import os
import shutil
import subprocess
import sys
from pathlib import Path


def set_startup(enabled):
    if sys.platform != "win32":
        raise OSError("Chạy cùng Windows chỉ dùng được trên Windows.")
    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            command = subprocess.list2cmdline(
                [sys.executable]
                if getattr(sys, "frozen", False)
                else [
                    str(Path(sys.executable).with_name("pythonw.exe")),
                    "-m",
                    "desktop.app",
                ]
            )
            winreg.SetValueEx(key, "TikTokLiveStudio", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "TikTokLiveStudio")
            except FileNotFoundError:
                pass


def main():
    multiprocessing.freeze_support()
    if getattr(sys, "frozen", False):
        binaries = Path(sys.executable).parent / "bin"
        os.environ["PATH"] = str(binaries) + os.pathsep + os.environ.get("PATH", "")
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from desktop.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Live Studio")
    apply_theme(app)
    data = Path(
        os.environ.get(
            "TIKTOK_RECORDER_DATA",
            str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TikTokLiveStudio"),
        )
    )
    data.mkdir(parents=True, exist_ok=True)
    os.chdir(data)
    from desktop.manager import RecordingManager
    from desktop.store import DesktopStore
    from desktop.window import MainWindow
    from desktop.licensing import LicenseClient, LicenseDenied, load_config
    from desktop.license_dialog import LicenseController, LicenseDialog

    lock = QLockFile(str(data / "application.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(
            None,
            "Tool đang chạy",
            "Live Studio đang chạy. Hãy mở từ biểu tượng ở khay hệ thống.",
        )
        return 0
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        QMessageBox.critical(
            None,
            "Thiếu FFmpeg",
            "Cần FFmpeg và FFprobe trên PATH để chạy bản thử này. Xem docs/HUONG_DAN_BAN_THU.md.",
        )
        return 1
    try:
        client = LicenseClient(data, load_config())
    except (LicenseDenied, OSError) as ex:
        QMessageBox.critical(None, "Chưa cấu hình giấy phép", str(ex))
        lock.unlock()
        return 1
    app.setQuitOnLastWindowClosed(False)
    licensing = LicenseController(client)
    store = None
    manager = None
    window = None
    startup_timer = None
    activation_ready = False
    try:
        store = DesktopStore(data / "state.db")
        manager = RecordingManager(
            store, license_guard=lambda: activation_ready and licensing.allowed()
        )
        window = MainWindow(store, manager, licensing)
        window.show()
        if "--update-ack" in sys.argv:
            import json
            from desktop.updates import bundled_config

            ack = Path(sys.argv[sys.argv.index("--update-ack") + 1])
            startup_timer = QTimer(window)
            startup_timer.setSingleShot(True)
            startup_timer.timeout.connect(
                lambda: ack.write_text(
                    json.dumps(
                        dict(pid=os.getpid(), version=bundled_config()["version"])
                    ),
                    encoding="utf-8",
                )
            )
            startup_timer.start(0)
        if not LicenseDialog(licensing, window).exec():
            return 0
        activation_ready = True
        if getattr(sys, "frozen", False):
            QTimer.singleShot(2000, lambda: window.updates.check(True))
        return app.exec()
    finally:
        if startup_timer:
            startup_timer.stop()
        if manager:
            manager.shutdown()
        if store:
            store.close()
        licensing.close()
        lock.unlock()
        if window:
            window.timer.stop()
            window.tray.hide()
            window.updates.close()
            window.hide()
            if window.pending_update:
                from desktop.update_dialog import launch_updater

                try:
                    launch_updater(window.pending_update)
                except OSError:
                    QMessageBox.critical(
                        None,
                        "Chưa cập nhật được",
                        "Không mở được trình cập nhật. Bạn có thể mở lại tool hiện tại và thử lại.",
                    )


if __name__ == "__main__":
    raise SystemExit(main())
