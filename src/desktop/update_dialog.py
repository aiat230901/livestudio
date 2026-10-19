import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from desktop.updates import bundled_config, check_update, download_update


class UpdateController:
    def __init__(self, window, layout):
        self.window = window
        self.config = bundled_config()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="updates")
        self.future = None
        self.action = None
        self.envelope = None
        self.progress = 0
        self.cancel = Event()
        self.silent = True
        self.label = QLabel("Phiên bản " + self.config["version"])
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.button = QPushButton("Kiểm tra cập nhật")
        self.button.clicked.connect(lambda: self.check(False))
        layout.addWidget(self.button)
        self.timer = QTimer(window)
        self.timer.timeout.connect(self.poll)
        self.timer.start(200)
        if not getattr(sys, "frozen", False):
            self.button.setEnabled(False)
            self.label.setText(self.label.text() + " · Bản phát triển")

    def check(self, silent):
        if self.future or self.window.exiting:
            return
        self.silent = silent
        self.action = "check"
        self.button.setEnabled(False)
        self.label.setText("Đang kiểm tra cập nhật…")
        self.future = self.pool.submit(check_update, self.config)

    def poll(self):
        if self.future is None:
            return
        if not self.future.done():
            if self.action == "download":
                self.label.setText(f"Đang tải bản cập nhật… {self.progress}%")
            return
        future, self.future = self.future, None
        self.button.setEnabled(True)
        try:
            result = future.result()
            if self.window.exiting:
                return
            if self.action == "check":
                self.label.setText("Phiên bản " + self.config["version"])
                if not result:
                    if not self.silent:
                        QMessageBox.information(
                            self.window,
                            "Cập nhật",
                            "Bạn đang dùng phiên bản mới nhất đã phát hành.",
                        )
                    return
                self.envelope = result
                payload = result["payload"]
                if (
                    QMessageBox.question(
                        self.window,
                        "Có bản cập nhật " + payload["version"],
                        payload["notes"]
                        + "\n\nTải xuống và cập nhật? Tool sẽ hoàn tất video đang ghi trước khi khởi động lại.",
                    )
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                # Check write access before downloading a large package.
                import tempfile

                with tempfile.TemporaryFile(dir=Path(sys.executable).parent.parent):
                    pass
                self.action = "download"
                self.progress = 0
                self.button.setEnabled(False)
                self.future = self.pool.submit(
                    download_update,
                    self.config,
                    result,
                    Path.cwd(),
                    self.set_progress,
                    self.cancel,
                )
            else:
                self.label.setText("Đã tải và xác minh bản cập nhật.")
                if (
                    QMessageBox.question(
                        self.window,
                        "Cập nhật và mở lại?",
                        "Dừng theo dõi, hoàn tất video đang ghi rồi cập nhật? Danh sách kênh và cài đặt được giữ.",
                    )
                    == QMessageBox.StandardButton.Yes
                ):
                    self.window.pending_update = result
                    self.window.exiting = True
                    self.window.manager.shutdown()
                    self.window.centralWidget().setEnabled(False)
                    self.window.on_tick()
        except Exception:
            self.label.setText(
                "Chưa cập nhật được. Kiểm tra kết nối và quyền ghi thư mục tool."
            )
            if not self.silent or self.action == "download":
                QMessageBox.warning(
                    self.window,
                    "Chưa cập nhật được",
                    "Không tải hoặc xác minh được bản cập nhật. Phiên bản hiện tại vẫn sử dụng được; hãy thử lại sau.",
                )

    def set_progress(self, percent):
        self.progress = percent

    def close(self):
        self.cancel.set()
        self.timer.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)


def launch_updater(work):
    target = Path(sys.executable).parent
    helper = Path(work) / "LiveStudioUpdater.exe"
    shutil.copyfile(target / "LiveStudioUpdater.exe", helper)
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(
        [
            str(helper),
            "--apply",
            str(work),
            "--target",
            str(target),
            "--pid",
            str(os.getpid()),
        ],
        cwd=work,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
