from datetime import datetime
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.dialogs import ChannelDialog, SettingsDialog
from desktop.manager import REASONS
from desktop.theme import app_icon, nav_icon
from desktop.schedule_page import SchedulePage
from desktop.scheduling import VN_TZ


def label(text, name=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName("primary")
    item.clicked.connect(callback)
    return item


def duration_text(seconds):
    if seconds is None:
        return "Không giới hạn"
    return f"{int(seconds) // 3600:02d}:{int(seconds) % 3600 // 60:02d}:{int(seconds) % 60:02d}"


def table(headers):
    item = QTableWidget(0, len(headers))
    item.setHorizontalHeaderLabels(headers)
    item.verticalHeader().hide()
    item.verticalHeader().setDefaultSectionSize(52)
    item.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    item.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    item.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    item.setAlternatingRowColors(True)
    item.setShowGrid(False)
    item.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    item.horizontalHeader().setStretchLastSection(True)
    item.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    return item


class MainWindow(QMainWindow):
    def __init__(self, store, manager, licensing=None):
        super().__init__()
        self.store, self.manager = store, manager
        self.licensing = licensing
        self.exiting = False
        self._channel_rows = None
        self._history_rows = None
        self._notified = {r["id"] for r in store.list_recordings()}
        self.setWindowTitle("Live Studio • TikTok Recorder")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 680)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(222)
        nav_layout = QVBoxLayout(sidebar)
        nav_layout.setContentsMargins(20, 30, 20, 22)
        nav_layout.setSpacing(10)
        nav_layout.addWidget(label("LIVE STUDIO", "brand"))
        nav_layout.addSpacing(25)
        nav_layout.addWidget(label("WORKSPACE", "muted"))
        self.nav = []
        self.pages = QStackedWidget()
        for index, text in enumerate(
            ("Tổng quan", "Kênh theo dõi", "Lịch ghi", "Lịch sử video", "Cài đặt")
        ):
            nav = QPushButton(text)
            nav.setIcon(nav_icon((0, 1, 4, 2, 3)[index]))
            nav.setIconSize(QSize(22, 22))
            nav.setObjectName("nav")
            nav.setCheckable(True)
            nav.clicked.connect(lambda checked=False, i=index: self.navigate(i))
            self.nav.append(nav)
            nav_layout.addWidget(nav)
        nav_layout.addStretch()
        footer = label(
            "BẢN THỬ NỘI BỘ\n\nVideo lưu trên máy của bạn.\nGiữ tool chạy để theo dõi live.",
            "muted",
        )
        footer.setWordWrap(True)
        nav_layout.addWidget(footer)
        if self.licensing:
            self.license_notice = label("")
            self.license_notice.setWordWrap(True)
            nav_layout.addWidget(self.license_notice)
            self._last_license_allowed = True
        nav_layout.addSpacing(18)
        nav_layout.addWidget(button("Thoát ứng dụng", self.request_exit))
        shell.addWidget(sidebar)
        shell.addWidget(self.pages, 1)
        self.build_overview()
        self.build_channels()
        self.schedule_page = SchedulePage(store, manager, self.refresh)
        self.pages.addWidget(self.schedule_page)
        self.build_history()
        self.build_settings()
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Live Studio · đang theo dõi TikTok")
        menu = QMenu(self)
        menu.addAction("Mở Live Studio", self.restore)
        menu.addAction("Thoát ứng dụng", self.request_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self.restore()
                if reason
                in (
                    QSystemTrayIcon.ActivationReason.Trigger,
                    QSystemTrayIcon.ActivationReason.DoubleClick,
                )
                else None
            )
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start()
        self.navigate(0)
        self.refresh()

    def page(self, title, subtitle):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(20)
        layout.addWidget(label(title, "title"))
        layout.addWidget(label(subtitle, "muted"))
        self.pages.addWidget(page)
        return layout

    def build_overview(self):
        layout = self.page(
            "Không bỏ lỡ phiên live nào",
            "Theo dõi nhiều kênh và lưu lại những phiên livestream bạn cần.",
        )
        hero = QFrame()
        hero.setObjectName("hero")
        row = QHBoxLayout(hero)
        row.setContentsMargins(26, 24, 26, 24)
        text = QVBoxLayout()
        text.addWidget(label("TIKTOK LIVE RECORDER", "brand"))
        text.addWidget(label("Kênh lên live. Video được lưu.", "heading"))
        sub = label(
            "Theo dõi liên tục hoặc đặt lịch riêng cho từng kênh.\nMP4 • Ưu tiên chất lượng cao nhất truy cập được",
            "muted",
        )
        sub.setWordWrap(True)
        text.addWidget(sub)
        row.addLayout(text, 1)
        row.addWidget(button("+  Thêm kênh", self.add_channel, True))
        layout.addWidget(hero)
        stats = QHBoxLayout()
        self.stat_values = []
        for title in ("Kênh đã thêm", "Đang theo dõi", "Đang ghi", "Video hôm nay"):
            card = QFrame()
            card.setObjectName("card")
            inner = QVBoxLayout(card)
            inner.setContentsMargins(20, 18, 20, 18)
            inner.addWidget(label(title, "muted"))
            value = label("0", "number")
            self.stat_values.append(value)
            inner.addWidget(value)
            stats.addWidget(card)
        layout.addLayout(stats)
        row = QHBoxLayout()
        row.addWidget(label("Hoạt động gần đây", "heading"))
        row.addStretch()
        row.addWidget(button("Quản lý kênh  →", lambda: self.navigate(1)))
        layout.addLayout(row)
        self.activity = table(["Kênh", "Trạng thái", "Đã nhận"])
        layout.addWidget(self.activity, 1)
        self.empty = label(
            "Thêm kênh đầu tiên để bắt đầu. Bạn có thể nhập @username hoặc link hồ sơ TikTok.",
            "muted",
        )
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)

    def build_channels(self):
        layout = self.page(
            "Kênh theo dõi",
            "Liên tục hoặc theo lịch · Các khung giờ hiển thị theo giờ Việt Nam UTC+7.",
        )
        tools = QHBoxLayout()
        tools.addWidget(button("+ Thêm kênh", self.add_channel, True))
        tools.addWidget(button("Bật tất cả", lambda: self.toggle_all(True)))
        tools.addWidget(button("Tắt tất cả", lambda: self.toggle_all(False)))
        tools.addStretch()
        layout.addLayout(tools)
        self.channels = table(
            [
                "Bật",
                "Kênh TikTok",
                "Chế độ / lịch",
                "Trạng thái",
                "Tối đa / phiên",
                "Tiến độ",
            ]
        )
        self.channels.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.channels.verticalHeader().setDefaultSectionSize(64)
        for col, width in enumerate((40, 190, 160, 160, 110, 140)):
            self.channels.setColumnWidth(col, width)
        self.channels.itemChanged.connect(self.channel_checked)
        layout.addWidget(self.channels, 1)
        actions = QHBoxLayout()
        self.channel_actions = []
        for title, callback in [
            ("Ghi ngay", self.record_selected),
            ("Dừng ghi", self.stop_selected),
            ("Sửa kênh", self.edit_channel),
            ("Mở thư mục", self.open_channel_folder),
            ("Xóa kênh", self.delete_channel),
        ]:
            item = button(title, callback, title == "Ghi ngay")
            self.channel_actions.append(item)
            actions.addWidget(item)
        actions.addStretch()
        layout.addLayout(actions)
        self.channels.itemSelectionChanged.connect(self.update_actions)
        hint = label(
            "Ghi ngay bỏ qua lịch, vẫn giữ hạn mức phiên. Dừng ghi bỏ qua phần còn lại của phiên đó.\nMáy tính cần bật, có mạng và không ở chế độ ngủ.",
            "muted",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def build_history(self):
        layout = self.page(
            "Lịch sử video", "Các bản ghi và lý do kết thúc được lưu trên máy của bạn."
        )
        self.history = table(
            ["Kênh", "Bắt đầu", "Độ dài", "Chất lượng", "Dung lượng", "Kết quả"]
        )
        layout.addWidget(self.history, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Mở video", lambda: self.open_history(False), True))
        actions.addWidget(button("Mở thư mục", lambda: self.open_history(True)))
        actions.addStretch()
        layout.addLayout(actions)
        self.history_empty = label(
            "Chưa có bản ghi. Video hoàn tất sẽ xuất hiện tại đây.", "muted"
        )
        layout.addWidget(self.history_empty)

    def build_settings(self):
        layout = self.page(
            "Cài đặt", "Thiết lập một lần và lưu cho những lần sử dụng sau."
        )
        card = QFrame()
        card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(26, 26, 26, 26)
        inner.setSpacing(20)
        inner.addWidget(label("Tùy chọn ghi và theo dõi", "heading"))
        self.settings_summary = label("")
        self.settings_summary.setWordWrap(True)
        inner.addWidget(self.settings_summary)
        inner.addWidget(
            button("Chỉnh sửa cài đặt", self.edit_settings, True),
            alignment=Qt.AlignmentFlag.AlignLeft,
        )
        layout.addWidget(card)
        if self.licensing:
            self.license_summary = label("")
            self.license_summary.setWordWrap(True)
            layout.addWidget(self.license_summary)
            layout.addWidget(
                button("Kiểm tra / kích hoạt giấy phép", self.open_license),
                alignment=Qt.AlignmentFlag.AlignLeft,
            )
        hint = label(
            "Video được đóng gói sang MP4, giữ nguyên chất lượng nguồn khi codec tương thích.\n\nBấm X để thu xuống khay hệ thống. Chọn “Thoát ứng dụng” để dừng và lưu video an toàn.",
            "muted",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)

    def open_license(self):
        from desktop.license_dialog import LicenseDialog

        self.licensing.submit()
        LicenseDialog(self.licensing, self).exec()
        self.refresh()

    def selected_user(self):
        selected = self.channels.selectionModel().selectedRows()
        row = selected[0].row() if selected else -1
        return self.channels.item(row, 1).text().removeprefix("@") if row >= 0 else None

    def update_actions(self):
        user = self.selected_user()
        job = self.manager.jobs.get(user)
        for index, action in enumerate(self.channel_actions):
            action.setEnabled(
                bool(user)
                and (index != 0 or self.manager.license_guard())
                and (
                    index == 3 or (index == 1 and bool(job)) or (index != 1 and not job)
                )
            )

    def add_channel(self):
        dialog = ChannelDialog(self)
        if dialog.exec():
            value = dialog.value
            if any(
                c["username"] == value["username"] for c in self.store.list_channels()
            ):
                QMessageBox.information(
                    self,
                    "Kênh đã có",
                    "Kênh này đã có trong danh sách. Chọn Sửa kênh để thay đổi.",
                )
                return
            self.store.save_channel(value.pop("username"), **value)
            self.refresh()

    def edit_channel(self):
        user = self.selected_user()
        if not user or user in self.manager.jobs:
            return
        channel = next(c for c in self.store.list_channels() if c["username"] == user)
        dialog = ChannelDialog(self, channel)
        if dialog.exec():
            if user in self.manager.jobs:
                QMessageBox.information(
                    self,
                    "Kênh đang có tác vụ",
                    "Kênh vừa bắt đầu kiểm tra hoặc ghi. Hãy dừng tác vụ trước khi sửa.",
                )
                return
            value = dialog.value
            self.store.save_channel(value.pop("username"), **value)
            self.refresh()

    def delete_channel(self):
        user = self.selected_user()
        if (
            user
            and user not in self.manager.jobs
            and QMessageBox.question(
                self,
                "Xóa kênh?",
                f"Bỏ @{user} khỏi danh sách? Video đã lưu vẫn được giữ.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.store.delete_channel(user)
            self.refresh()

    def record_selected(self):
        if user := self.selected_user():
            self.manager.record_now(user)
            self.refresh()

    def stop_selected(self):
        if user := self.selected_user():
            self.manager.stop_recording(user)
            self.refresh()

    def toggle_all(self, enabled):
        for channel in self.store.list_channels():
            self.manager.enable(channel["username"], enabled)
        self.refresh()

    def channel_checked(self, item):
        if item.column() == 0:
            user = self.channels.item(item.row(), 1).text().removeprefix("@")
            self.manager.enable(user, item.checkState() == Qt.CheckState.Checked)
            self.refresh()

    def open_path(self, path):
        if not path or not Path(path).exists():
            QMessageBox.information(
                self, "Chưa có tệp", "Chưa có tệp hoặc thư mục này trên máy."
            )
        elif not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(Path(path).resolve()))
        ):
            QMessageBox.warning(
                self, "Không mở được", "Windows chưa có ứng dụng phù hợp để mở tệp này."
            )

    def open_channel_folder(self):
        user = self.selected_user()
        if user:
            channel = next(
                c for c in self.store.list_channels() if c["username"] == user
            )
            self.open_path(self.manager.output_for(channel))

    def open_history(self, folder):
        row = self.history.currentRow()
        records = self.store.list_recordings()
        if row >= 0 and row < len(records):
            path = records[row].get("path")
            self.open_path(str(Path(path).parent) if path and folder else path)

    def settings(self):
        defaults = dict(
            output=str(Path.home() / "Videos" / "TikTok Live"),
            interval=120,
            notifications=True,
            startup=False,
        )
        return {
            key: self.store.get_setting(key, default)
            for key, default in defaults.items()
        }

    def edit_settings(self):
        previous = self.settings()
        dialog = SettingsDialog(self, previous)
        if dialog.exec():
            try:
                if dialog.value["startup"] != previous["startup"]:
                    from desktop.app import set_startup

                    set_startup(dialog.value["startup"])
                for key, value in dialog.value.items():
                    self.store.set_setting(key, value)
                self.refresh()
            except OSError as ex:
                QMessageBox.warning(self, "Không lưu được cài đặt", str(ex))

    def refresh(self):
        snapshot = self.manager.snapshot()
        rows = list(snapshot.values())
        for channel in rows:
            job = self.manager.jobs.get(channel["username"])
            channel["elapsed"] = (
                int(time.time() - job["launched"])
                if job and job["spec"]["kind"] == "record"
                else None
            )
        records = self.store.list_recordings()
        today = datetime.now(VN_TZ).date()
        counts = (
            len(rows),
            sum(bool(c["enabled"]) for c in rows),
            sum(j["spec"]["kind"] == "record" for j in self.manager.jobs.values()),
            sum(
                bool(r.get("path"))
                and r["reason"] != "conversion_error"
                and datetime.fromtimestamp(r["ended_utc"], VN_TZ).date() == today
                for r in records
            ),
        )
        for value, count in zip(self.stat_values, counts):
            value.setText(str(count))
        if rows != self._channel_rows:
            selected = self.selected_user()
            self.channels.blockSignals(True)
            self.channels.setRowCount(len(rows))
            self.activity.setRowCount(len(rows))
            for row, channel in enumerate(rows):
                status = channel["status"]
                size = f"{channel.get('bytes_written', 0) / 1024**2:.1f} MB"
                progress = size + (
                    " · " + duration_text(channel["elapsed"])
                    if channel["elapsed"] is not None
                    else ""
                )
                values = [
                    "",
                    "@" + channel["username"],
                    channel["schedule_text"]
                    if channel["mode"] == "continuous"
                    else "Theo lịch\n" + channel["schedule_text"],
                    status,
                    duration_text(channel["duration_seconds"]),
                    progress,
                ]
                for col, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    if col == 0:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(
                            Qt.CheckState.Checked
                            if channel["enabled"]
                            else Qt.CheckState.Unchecked
                        )
                    if col == 3:
                        item.setForeground(
                            QColor("#2563EB" if status == "Đang ghi" else "#64748B")
                        )
                    item.setToolTip(
                        channel.get("message") or channel.get("error") or text
                    )
                    self.channels.setItem(row, col, item)
                for col, text in enumerate(("@" + channel["username"], status, size)):
                    self.activity.setItem(row, col, QTableWidgetItem(text))
                if selected == channel["username"]:
                    self.channels.selectRow(row)
            self.channels.blockSignals(False)
            self._channel_rows = rows
        if records != self._history_rows:
            self.history.setRowCount(len(records))
            for row, record in enumerate(records):
                values = (
                    "@" + record["username"],
                    datetime.fromtimestamp(record["started_utc"], VN_TZ).strftime(
                        "%d/%m %H:%M"
                    ),
                    duration_text(record.get("media_duration", 0)),
                    record.get("resolution", "—"),
                    f"{record.get('bytes_written', 0) / 1024**2:.1f} MB",
                    REASONS.get(record["reason"], record["reason"]),
                )
                for col, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setToolTip(
                        record.get("error")
                        or (
                            (
                                record.get("resolution", "")
                                + "\n"
                                + (record.get("path") or "")
                            ).strip()
                        )
                        or text
                    )
                    self.history.setItem(row, col, item)
                if record["id"] not in self._notified:
                    self._notified.add(record["id"])
                    if (
                        self.store.get_setting("notifications", True)
                        and self.tray.isVisible()
                    ):
                        self.tray.showMessage(
                            "Live Studio · @" + record["username"], values[-1]
                        )
            self._history_rows = records
        self.empty.setVisible(not rows)
        self.history_empty.setVisible(not records)
        self.schedule_page.refresh()
        settings = self.settings()
        self.settings_summary.setText(
            f"Thư mục chung\n{settings['output']}\n\nKiểm tra mỗi {settings['interval'] // 60} phút\n\nThông báo: {'Bật' if settings['notifications'] else 'Tắt'}   •   Mở cùng Windows: {'Bật' if settings['startup'] else 'Tắt'}"
        )
        self.statusBar().showMessage(
            "Đang dừng và lưu các bản ghi…"
            if self.exiting
            else f"Giờ Việt Nam UTC+7  •  Kiểm tra mỗi {settings['interval'] // 60} phút  •  Video lưu trên máy tính"
        )
        if self.licensing:
            self.license_summary.setText(self.licensing.summary())
            allowed = self.licensing.allowed()
            self.license_notice.setText(
                "Giấy phép: " + ("Hợp lệ" if allowed else "Cần xác thực")
            )
            if not allowed:
                self.statusBar().showMessage(
                    "Ghi livestream đã tạm dừng · "
                    + self.licensing.summary().replace("\n", " · ")
                )
                if self._last_license_allowed and self.tray.isVisible():
                    self.tray.showMessage(
                        "Live Studio · Giấy phép", self.licensing.summary()
                    )
            self._last_license_allowed = allowed
        self.update_actions()

    def on_tick(self):
        try:
            self.manager.tick()
            self.refresh()
            if self.exiting and not self.manager.jobs:
                self.timer.stop()
                self.tray.hide()
                self.close()
                from PySide6.QtWidgets import QApplication

                QApplication.instance().quit()
        except Exception as ex:
            self.timer.stop()
            QMessageBox.critical(self, "Lỗi ứng dụng", f"{type(ex).__name__}: {ex}")

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def request_exit(self):
        if self.exiting:
            return
        if (
            self.manager.jobs
            and QMessageBox.question(
                self,
                "Dừng và thoát?",
                "Tool sẽ dừng theo dõi, hoàn tất video đang ghi rồi thoát. Tiếp tục?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.exiting = True
        self.manager.shutdown()
        self.centralWidget().setEnabled(False)
        self.on_tick()

    def closeEvent(self, event):
        if self.exiting and not self.manager.jobs:
            event.accept()
        elif self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self.request_exit()
