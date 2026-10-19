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
            executable = str(Path(sys.executable).with_name("pythonw.exe"))
            command = subprocess.list2cmdline([executable, "-m", "desktop.app"])
            winreg.SetValueEx(key, "TikTokLiveStudio", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "TikTokLiveStudio")
            except FileNotFoundError:
                pass


def main():
    multiprocessing.freeze_support()
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from desktop.theme import apply_theme

    app = QApplication(sys.argv)
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
    try:
        if not LicenseDialog(licensing).exec():
            return 0
        store = DesktopStore(data / "state.db")
        manager = RecordingManager(store, license_guard=licensing.allowed)
        window = MainWindow(store, manager, licensing)
        window.show()
        return app.exec()
    finally:
        if manager:
            manager.shutdown()
        if store:
            store.close()
        licensing.close()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
