import os
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QByteArray
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
    QPolygon,
)
from PySide6.QtSvg import QSvgRenderer


def nav_icon(index):
    shapes = (
        '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
        '<rect x="2" y="5" width="14" height="14" rx="3"/><path d="m16 10 6-4v12l-6-4"/>',
        '<path d="M14 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9z"/>'
        '<path d="M14 2v7h7M7 13h10M7 17h7"/>',
        '<path d="m9.5 3-.6 2a8 8 0 0 0-1.4.8L5.5 5 3 9.3l1.5 1.5a8 8 0 0 0 0 2.4L3 14.7 5.5 19l2-.8a8 8 0 0 0 1.4.8l.6 2h5l.6-2a8 8 0 0 0 1.4-.8l2 .8 2.5-4.3-1.5-1.5a8 8 0 0 0 0-2.4L21 9.3 18.5 5l-2 .8a8 8 0 0 0-1.4-.8l-.6-2z"/>'
        '<circle cx="12" cy="12" r="3"/>',
        '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2M8 18h2"/>',
    )
    icon = QIcon()
    for state, color in ((QIcon.State.Off, "#475569"), (QIcon.State.On, "#2563EB")):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{shapes[index]}</svg>'
        pixmap = QPixmap(72, 72)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(3)
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active):
            icon.addPixmap(pixmap, mode, state)
    return icon


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2563EB"))
    painter.drawRoundedRect(0, 0, 64, 64, 16, 16)
    painter.setBrush(QColor("white"))
    painter.drawRoundedRect(13, 20, 28, 25, 5, 5)
    painter.drawPolygon(
        QPolygon([QPoint(x, y) for x, y in [(44, 25), (54, 20), (54, 44), (44, 39)]])
    )
    painter.end()
    return QIcon(pixmap)


def apply_theme(app):
    # The Qt offscreen backend does not enumerate Windows system fonts.
    if not QFontDatabase.families():
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(app_icon())
    app.setStyleSheet(
        """
        QWidget { color: #111827; font-family: "Segoe UI"; font-size: 14px; }
        QMainWindow, QDialog, QWidget#page { background: #F6F8FC; }
        QFrame#sidebar { background: #F8FAFD; border-right: 1px solid #E2E8F0; }
        QFrame#card { background: white; border: 1px solid #E2E8F0; border-radius: 12px; }
        QFrame#hero { background: #EAF2FF; border: 1px solid #CADDFF; border-radius: 14px; }
        QLabel { background: transparent; }
        QLabel#muted { color: #718096; }
        QLabel#brand { color: #2563EB; font-size: 15px; font-weight: 700; }
        QLabel#title { font-size: 28px; font-weight: 700; }
        QLabel#heading { font-size: 19px; font-weight: 650; }
        QLabel#number { font-size: 30px; font-weight: 700; }
        QLabel#error { color: #B91C1C; }
        QPushButton { background: white; border: 1px solid #DCE3EE; border-radius: 8px; padding: 9px 15px; font-weight: 600; }
        QPushButton:hover { background: #EFF5FF; border-color: #AFC8FF; }
        QPushButton:disabled { color: #9CA3AF; background: #F1F5F9; }
        QPushButton#primary { background: #2563EB; color: white; border: 1px solid #2563EB; }
        QPushButton#primary:hover { background: #1D4ED8; }
        QPushButton#primary:disabled { color: #94A3B8; background: #E2E8F0; border-color: #E2E8F0; }
        QPushButton#nav { text-align: left; padding: 12px 14px; min-height: 24px; border: 1px solid transparent; background: transparent; color: #334155; font-size: 15px; font-weight: 700; }
        QPushButton#nav:hover { background: #EEF3FB; color: #1E293B; }
        QPushButton#nav:checked { color: #2563EB; background: #EAF2FF; }
        QPushButton#nav:focus { border-color: #AFC8FF; }
        QLineEdit, QSpinBox, QDateTimeEdit, QComboBox { background: white; border: 1px solid #DCE3EE; border-radius: 7px; padding: 8px; min-height: 22px; }
        QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus, QComboBox:focus { border: 1px solid #2563EB; }
        QComboBox { padding-right: 36px; }
        QComboBox::drop-down, QDateTimeEdit::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 28px; border-left: 1px solid #DCE3EE; border-top-right-radius: 7px; border-bottom-right-radius: 7px; background: #EFF4FB; }
        QComboBox::down-arrow, QDateTimeEdit::down-arrow { image: url("__SPIN_DOWN__"); width: 12px; height: 12px; }
        QComboBox QAbstractItemView { background: white; color: #111827; selection-background-color: #EAF2FF; selection-color: #1D4ED8; }
        QListWidget { background: white; border: 1px solid #DCE3EE; border-radius: 7px; padding: 4px; }
        QListWidget::item { padding: 5px; }
        QListWidget::item:selected { background: #EAF2FF; color: #1D4ED8; }
        QAbstractSpinBox { padding-right: 36px; selection-background-color: #DBEAFE; selection-color: #111827; }
        QAbstractSpinBox:disabled { color: #64748B; background: #F1F5F9; }
        QAbstractSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 28px; height: 20px; border-left: 1px solid #DCE3EE; border-bottom: 1px solid #DCE3EE; border-top-right-radius: 7px; background: #EFF4FB; }
        QAbstractSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 28px; height: 20px; border-left: 1px solid #DCE3EE; border-bottom-right-radius: 7px; background: #EFF4FB; }
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background: #DBEAFE; }
        QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed { background: #BFDBFE; }
        QAbstractSpinBox::up-button:disabled, QAbstractSpinBox::down-button:disabled { background: #E9EEF5; }
        QAbstractSpinBox::up-arrow { image: url("__SPIN_UP__"); width: 12px; height: 12px; }
        QAbstractSpinBox::down-arrow { image: url("__SPIN_DOWN__"); width: 12px; height: 12px; }
        QTableWidget { background: white; alternate-background-color: #F9FBFE; border: 1px solid #E2E8F0; border-radius: 10px; gridline-color: #EDF1F7; selection-background-color: #EAF2FF; selection-color: #111827; }
        QHeaderView::section { background: #F8FAFD; border: 0; border-bottom: 1px solid #E2E8F0; color: #64748B; padding: 12px 8px; font-weight: 600; }
        QTableWidget::item { padding: 8px; border-bottom: 1px solid #EFF2F7; }
        QCheckBox { spacing: 8px; }
        QCheckBox::indicator { width: 18px; height: 18px; }
        QToolTip { background: white; color: #111827; border: 1px solid #CBD5E1; }
        QStatusBar { background: white; color: #64748B; border-top: 1px solid #E2E8F0; }
    """.replace(
            "__SPIN_UP__",
            (Path(__file__).parent / "assets" / "chevron-up.svg").as_posix(),
        ).replace(
            "__SPIN_DOWN__",
            (Path(__file__).parent / "assets" / "chevron-down.svg").as_posix(),
        )
    )
