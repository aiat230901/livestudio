from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.schedule_dialog import ScheduleDialog
from desktop.scheduling import describe_schedule, format_time, is_active, next_window


class SchedulePage(QWidget):
    def __init__(self, store, manager, on_change):
        super().__init__()
        self.store, self.manager, self.on_change = store, manager, on_change
        self._rows = None
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(20)
        title = QLabel("Lịch ghi")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel(
            "Giờ Việt Nam · UTC+7   |   Lịch một lần hoặc lặp theo ngày trong tuần."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Thêm lịch cho"))
        self.channel = QComboBox()
        self.channel.setMinimumWidth(220)
        toolbar.addWidget(self.channel, 1)
        self.add_button = QPushButton("+ Thêm lịch")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self.add_rule)
        toolbar.addWidget(self.add_button)
        layout.addLayout(toolbar)
        hint = QLabel(
            "Thêm lịch sẽ chuyển kênh sang Theo lịch. Bật theo dõi kênh để lịch tự chạy.\nCác khung giờ trùng hoặc tiếp giáp được ghi liên tục, không tạo bản ghi trùng.\nGiới hạn mỗi phiên vẫn tính cả khoảng nghỉ giữa các lịch."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Kênh", "Loại lịch", "Khung giờ (UTC+7)", "Trạng thái"]
        )
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        for col, width in enumerate((190, 115, 340, 150)):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.edit_button, self.delete_button = (
            QPushButton("Sửa lịch"),
            QPushButton("Xóa lịch"),
        )
        self.edit_button.clicked.connect(self.edit_rule)
        self.delete_button.clicked.connect(self.delete_rule)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.empty = QLabel("Chưa có lịch. Chọn một kênh ở trên rồi bấm Thêm lịch.")
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.channel.currentIndexChanged.connect(self.update_actions)

    def selected(self):
        rows = self.table.selectionModel().selectedRows()
        return (
            tuple(self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole))
            if rows
            else None
        )

    def update_actions(self):
        user = self.channel.currentData()
        self.add_button.setEnabled(bool(user) and user not in self.manager.jobs)
        selected = self.selected()
        idle = bool(selected) and selected[0] not in self.manager.jobs
        self.edit_button.setEnabled(idle)
        self.delete_button.setEnabled(idle)

    def idle_channel(self, user):
        if user in self.manager.jobs:
            QMessageBox.information(
                self,
                "Kênh đang có tác vụ",
                "Kênh vừa bắt đầu kiểm tra hoặc ghi. Hãy dừng tác vụ rồi sửa lịch để tránh cắt video đang ghi.",
            )
            return None
        return next(
            (c for c in self.store.list_channels() if c["username"] == user), None
        )

    def save(self, channel, schedules, activate=False):
        self.store.save_channel(
            channel["username"],
            channel["duration_seconds"],
            channel["output"],
            channel["enabled"],
            mode="scheduled" if activate else channel["mode"],
            schedules=schedules,
        )
        self.on_change()

    def add_rule(self):
        user = self.channel.currentData()
        if not user or not self.idle_channel(user):
            return
        dialog = ScheduleDialog(self)
        if dialog.exec() and (channel := self.idle_channel(user)):
            self.save(channel, channel["schedules"] + [dialog.value], activate=True)

    def edit_rule(self):
        selected = self.selected()
        if not selected:
            return
        user, index = selected
        channel = self.idle_channel(user)
        if not channel:
            return
        dialog = ScheduleDialog(self, channel["schedules"][index])
        if dialog.exec() and (channel := self.idle_channel(user)):
            schedules = channel["schedules"][:]
            schedules[index] = dialog.value
            self.save(channel, schedules)

    def delete_rule(self):
        selected = self.selected()
        if not selected:
            return
        user, index = selected
        channel = self.idle_channel(user)
        if (
            channel
            and QMessageBox.question(
                self,
                "Xóa lịch?",
                "Xóa khung giờ này? Nếu hết lịch, kênh sẽ chờ bạn thêm lịch mới.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.save(
                channel,
                [rule for i, rule in enumerate(channel["schedules"]) if i != index],
            )

    def refresh(self):
        channels = self.store.list_channels()
        options = [
            (
                "@"
                + c["username"]
                + (" · Theo lịch" if c["mode"] == "scheduled" else " · Liên tục"),
                c["username"],
            )
            for c in channels
        ]
        if options != [
            (self.channel.itemText(i), self.channel.itemData(i))
            for i in range(self.channel.count())
        ]:
            selected = self.channel.currentData()
            self.channel.blockSignals(True)
            self.channel.clear()
            for text, user in options:
                self.channel.addItem(text, user)
            if selected:
                self.channel.setCurrentIndex(max(0, self.channel.findData(selected)))
            self.channel.blockSignals(False)
        now = self.manager.clock()
        rows = []
        for channel in channels:
            for index, rule in enumerate(channel["schedules"]):
                window = next_window([rule], now)
                if not channel["enabled"]:
                    state = "Đã tắt theo dõi"
                elif channel["mode"] == "continuous":
                    state = "Đang dùng Liên tục"
                elif is_active(window, now):
                    state = "Trong khung giờ"
                else:
                    state = "Từ " + format_time(window[0]) if window else "Đã hết lịch"
                rows.append((channel["username"], index, rule, state))
        if rows != self._rows:
            selected = self.selected()
            self.table.setRowCount(len(rows))
            for row, (user, index, rule, state) in enumerate(rows):
                values = (
                    "@" + user,
                    "Một lần" if rule["kind"] == "once" else "Lặp hằng tuần",
                    describe_schedule(rule),
                    state,
                )
                for col, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    item.setData(Qt.ItemDataRole.UserRole, (user, index))
                    self.table.setItem(row, col, item)
                if selected == (user, index):
                    self.table.selectRow(row)
            self._rows = rows
        self.empty.setVisible(not rows)
        self.update_actions()
