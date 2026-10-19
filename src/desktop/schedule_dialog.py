from datetime import datetime

from PySide6.QtCore import QDateTime, QTime, QTimeZone
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.scheduling import DAY_NAMES, VN_TZ, describe_schedule, normalize_schedule


class ScheduleDialog(QDialog):
    def __init__(self, parent=None, initial=None):
        super().__init__(parent)
        self.setWindowTitle("Sửa khung giờ" if initial else "Thêm khung giờ ghi")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        timezone = QLabel("Giờ Việt Nam · UTC+7")
        timezone.setObjectName("brand")
        layout.addWidget(timezone)
        self.kind = QComboBox()
        self.kind.addItem("Một lần", "once")
        self.kind.addItem("Lặp hằng tuần", "weekly")
        layout.addWidget(self.kind)
        self.pages = QStackedWidget()
        once_page = QWidget()
        once_form = QFormLayout(once_page)
        start = int(datetime.now(VN_TZ).timestamp() // 60 * 60) + 300
        zone = QTimeZone(7 * 3600)
        self.once_start, self.once_end = QDateTimeEdit(), QDateTimeEdit()
        for widget, timestamp in (
            (self.once_start, start),
            (self.once_end, start + 3600),
        ):
            widget.setTimeZone(zone)
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd/MM/yyyy HH:mm")
            widget.setDateTime(QDateTime.fromSecsSinceEpoch(timestamp, zone))
        once_form.addRow("Bắt đầu", self.once_start)
        once_form.addRow("Kết thúc", self.once_end)
        self.pages.addWidget(once_page)
        weekly_page = QWidget()
        weekly_form = QFormLayout(weekly_page)
        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for index, name in enumerate(DAY_NAMES):
            check = QCheckBox(name)
            check.setChecked(index == datetime.now(VN_TZ).weekday())
            self.days.append(check)
            days_layout.addWidget(check)
        weekly_form.addRow("Ngày bắt đầu", days_widget)
        self.weekly_start = QTimeEdit(QTime(9, 0))
        self.weekly_end = QTimeEdit(QTime(10, 0))
        for widget in (self.weekly_start, self.weekly_end):
            widget.setDisplayFormat("HH:mm")
        weekly_form.addRow("Bắt đầu", self.weekly_start)
        weekly_form.addRow("Kết thúc", self.weekly_end)
        hint = QLabel(
            "Ví dụ 22:00–02:00: kết thúc vào hôm sau.\nNgày được chọn là ngày bắt đầu; giờ bắt đầu và kết thúc phải khác nhau."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        weekly_form.addRow(hint)
        self.pages.addWidget(weekly_page)
        self.kind.currentIndexChanged.connect(self.pages.setCurrentIndex)
        layout.addWidget(self.pages)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("error")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox()
        buttons.addButton("Hủy", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton(
            "Lưu khung giờ", QDialogButtonBox.ButtonRole.AcceptRole
        ).setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if initial:
            rule = normalize_schedule(initial)
            if rule["kind"] == "once":
                self.once_start.setDateTime(
                    QDateTime.fromSecsSinceEpoch(int(rule["start"]), zone)
                )
                self.once_end.setDateTime(
                    QDateTime.fromSecsSinceEpoch(int(rule["end"]), zone)
                )
            else:
                self.kind.setCurrentIndex(1)
                for index, check in enumerate(self.days):
                    check.setChecked(index in rule["days"])
                self.weekly_start.setTime(
                    QTime(rule["start_minute"] // 60, rule["start_minute"] % 60)
                )
                self.weekly_end.setTime(
                    QTime(rule["end_minute"] // 60, rule["end_minute"] % 60)
                )

    def accept(self):
        if self.kind.currentData() == "once":
            rule = dict(
                kind="once",
                start=self.once_start.dateTime().toSecsSinceEpoch(),
                end=self.once_end.dateTime().toSecsSinceEpoch(),
            )
        else:
            start, end = self.weekly_start.time(), self.weekly_end.time()
            rule = dict(
                kind="weekly",
                days=[i for i, check in enumerate(self.days) if check.isChecked()],
                start_minute=start.hour() * 60 + start.minute(),
                end_minute=end.hour() * 60 + end.minute(),
            )
        try:
            self.value = normalize_schedule(rule)
        except ValueError as ex:
            self.error.setText(str(ex))
            return
        super().accept()


class ScheduleListEditor(QWidget):
    def __init__(self, parent=None, initial=None):
        super().__init__(parent)
        self.schedules = [normalize_schedule(rule) for rule in (initial or [])]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Các khung giờ · Việt Nam UTC+7"))
        self.list = QListWidget()
        self.list.setMinimumHeight(80)
        self.list.setMaximumHeight(110)
        self.list.itemDoubleClicked.connect(self.edit_rule)
        layout.addWidget(self.list)
        buttons = QHBoxLayout()
        for text, callback in (
            ("+ Thêm khung giờ", self.add_rule),
            ("Sửa", self.edit_rule),
            ("Xóa", self.delete_rule),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        hint = QLabel(
            "Khung giờ trùng hoặc tiếp giáp được ghép liên tục. Máy cần bật và tool đang chạy."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.refresh()

    def refresh(self):
        self.list.clear()
        self.list.addItems([describe_schedule(rule) for rule in self.schedules])

    def add_rule(self):
        dialog = ScheduleDialog(self)
        if dialog.exec():
            self.schedules.append(dialog.value)
            self.refresh()

    def edit_rule(self, *_):
        row = self.list.currentRow()
        if row >= 0:
            dialog = ScheduleDialog(self, self.schedules[row])
            if dialog.exec():
                self.schedules[row] = dialog.value
                self.refresh()
                self.list.setCurrentRow(row)

    def delete_rule(self):
        row = self.list.currentRow()
        if row >= 0:
            del self.schedules[row]
            self.refresh()
