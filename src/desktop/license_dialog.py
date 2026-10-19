from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
)

from desktop.scheduling import VN_TZ


class LicenseController(QObject):
    """One network task at a time; Qt and recording control stay on the UI thread."""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="license")
        self.future = None
        self.error = None
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.submit()

    def submit(self, key=None):
        if self.future is not None:
            return False
        self.future = self.executor.submit(
            self.client.refresh if key is None else self.client.activate,
            *(() if key is None else (key,)),
        )
        return True

    def poll(self):
        if self.future is not None and self.future.done():
            try:
                self.future.result()
                self.error = None
            except Exception:
                self.error = "Không đọc/lưu được giấy phép an toàn. Kiểm tra quyền thư mục và thử lại."
                self.client.next_attempt = self.client.monotonic() + 60
            self.future = None
        if self.future is None and self.client.monotonic() >= self.client.next_attempt:
            self.submit()
        if self.future is None and self.error is None:
            try:
                self.client.checkpoint()
            except OSError:
                self.error = (
                    "Không lưu được giấy phép an toàn. Kiểm tra quyền ghi thư mục."
                )

    def allowed(self):
        return not self.error and self.client.allowed()

    def summary(self):
        message = self.error or self.client.message
        if self.allowed():
            expiry = datetime.fromtimestamp(
                self.client.claims["expires_at"], VN_TZ
            ).strftime("%d/%m/%Y %H:%M")
            message += "\nHết hạn: " + expiry + " (giờ Việt Nam)"
        return message

    def close(self):
        self.timer.stop()
        self.executor.shutdown(wait=True, cancel_futures=True)


class LicenseDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Kích hoạt Live Studio")
        self.setMinimumWidth(560)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        title = QLabel("Kích hoạt trên máy tính này")
        title.setObjectName("heading")
        layout.addWidget(title)
        hint = QLabel(
            "Nhập key bạn nhận từ nhà cung cấp. Mỗi key liên kết một máy tính; thời hạn bắt đầu từ lần kích hoạt đầu tiên."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.key = QLineEdit()
        self.key.setPlaceholderText("LVS-XXXX-XXXX-…")
        self.key.setMaxLength(80)
        self.key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        layout.addWidget(self.key)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.check = QPushButton("Kiểm tra lại")
        self.check.clicked.connect(lambda: controller.submit())
        actions.addWidget(self.check)
        actions.addStretch()
        cancel = QPushButton("Đóng")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.activate = QPushButton("Kích hoạt")
        self.activate.setObjectName("primary")
        self.activate.clicked.connect(self.activate_key)
        actions.addWidget(self.activate)
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)
        self.finished.connect(self.timer.stop)
        self.refresh()

    def activate_key(self):
        if self.key.text().strip() and self.controller.submit(self.key.text()):
            self.key.clear()
            self.refresh()

    def refresh(self):
        busy = self.controller.future is not None
        self.key.setEnabled(not busy)
        self.activate.setEnabled(not busy)
        self.check.setEnabled(not busy)
        self.status.setText(
            "Đang xác thực với máy chủ…" if busy else self.controller.summary()
        )
        if not busy and self.controller.allowed():
            self.accept()
