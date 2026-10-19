from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from desktop.store import normalize_username
from desktop.schedule_dialog import ScheduleListEditor


class FolderField(QWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText("Dùng thư mục chung / username")
        layout.addWidget(self.edit)
        button = QPushButton("Chọn…")
        button.clicked.connect(self.choose)
        layout.addWidget(button)

    def choose(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu video", self.edit.text() or str(Path.home())
        )
        if folder:
            self.edit.setText(folder)


class ChannelDialog(QDialog):
    def __init__(self, parent=None, initial=None):
        super().__init__(parent)
        initial = initial or {}
        self.setWindowTitle("Sửa kênh" if initial else "Thêm kênh TikTok")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.user = QLineEdit(initial.get("username", ""))
        self.user.setPlaceholderText("@username hoặc https://www.tiktok.com/@username")
        self.user.setReadOnly(bool(initial))
        form.addRow("Kênh TikTok", self.user)
        self.mode = QComboBox()
        self.mode.addItem("Liên tục", "continuous")
        self.mode.addItem("Theo lịch", "scheduled")
        self.mode.setCurrentIndex(1 if initial.get("mode") == "scheduled" else 0)
        form.addRow("Chế độ theo dõi", self.mode)
        self.unlimited = QCheckBox("Không giới hạn thời lượng")
        duration = initial.get("duration_seconds")
        self.unlimited.setChecked(duration is None)
        form.addRow("", self.unlimited)
        time_row = QWidget()
        time_layout = QHBoxLayout(time_row)
        time_layout.setContentsMargins(0, 0, 0, 0)
        self.hours = QSpinBox()
        self.hours.setRange(0, 999)
        self.hours.setSuffix(" giờ")
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 59)
        self.minutes.setSuffix(" phút")
        self.hours.setValue((duration or 0) // 3600)
        self.minutes.setValue(((duration or 0) % 3600) // 60)
        time_layout.addWidget(self.hours)
        time_layout.addWidget(self.minutes)
        self.unlimited.toggled.connect(lambda checked: time_row.setEnabled(not checked))
        time_row.setEnabled(not self.unlimited.isChecked())
        form.addRow("Tối đa mỗi phiên", time_row)
        self.folder = FolderField(initial.get("output") or "")
        form.addRow("Thư mục riêng", self.folder)
        self.enabled = QCheckBox("Bật theo dõi kênh này")
        self.enabled.setChecked(bool(initial.get("enabled", True)))
        form.addRow("", self.enabled)
        layout.addLayout(form)
        self.schedule_editor = ScheduleListEditor(self, initial.get("schedules"))
        self.schedule_editor.setVisible(self.mode.currentData() == "scheduled")
        self.mode.currentIndexChanged.connect(
            lambda: self.schedule_editor.setVisible(
                self.mode.currentData() == "scheduled"
            )
        )
        layout.addWidget(self.schedule_editor)
        hint = QLabel(
            "Hết thời lượng sẽ chờ phiên live mới. Live kết thúc sớm vẫn lưu phần đã ghi.\nThay đổi áp dụng từ lần ghi tiếp theo; không đặt lại hạn mức phiên hiện tại."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("error")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox()
        buttons.addButton("Hủy", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton(
            "Lưu kênh", QDialogButtonBox.ButtonRole.AcceptRole
        ).setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            user = normalize_username(self.user.text())
            duration = (
                None
                if self.unlimited.isChecked()
                else self.hours.value() * 3600 + self.minutes.value() * 60
            )
            if duration == 0:
                raise ValueError("Hãy chọn thời lượng từ 1 phút trở lên.")
            output = self.folder.edit.text().strip() or None
            if output and not Path(output).is_absolute():
                raise ValueError("Hãy chọn đường dẫn thư mục đầy đủ.")
            if (
                self.mode.currentData() == "scheduled"
                and not self.schedule_editor.schedules
            ):
                raise ValueError("Hãy thêm ít nhất một khung giờ hoặc chọn Liên tục.")
            self.value = dict(
                username=user,
                duration_seconds=duration,
                output=output,
                enabled=self.enabled.isChecked(),
                mode=self.mode.currentData(),
                schedules=self.schedule_editor.schedules,
            )
        except ValueError as ex:
            self.error.setText(str(ex))
            return
        super().accept()


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt ứng dụng")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.folder = FolderField(settings["output"])
        form.addRow("Thư mục chung", self.folder)
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setSuffix(" phút")
        self.interval.setValue(settings["interval"] // 60)
        form.addRow("Kiểm tra kênh mỗi", self.interval)
        self.notifications = QCheckBox("Thông báo khi hoàn tất bản ghi")
        self.notifications.setChecked(settings["notifications"])
        form.addRow("", self.notifications)
        self.startup = QCheckBox("Mở tool cùng Windows")
        self.startup.setChecked(settings["startup"])
        form.addRow("", self.startup)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("error")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        folder = self.folder.edit.text().strip()
        if not folder or not Path(folder).is_absolute():
            self.error.setText("Hãy chọn đường dẫn thư mục đầy đủ.")
            return
        self.value = dict(
            output=folder,
            interval=self.interval.value() * 60,
            notifications=self.notifications.isChecked(),
            startup=self.startup.isChecked(),
        )
        super().accept()
