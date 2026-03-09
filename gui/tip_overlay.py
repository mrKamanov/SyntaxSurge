#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Окно-подсказка, следующее за курсором мыши.
Показывает краткую подсказку по текущему блоку кода во время автопечати.
"""
import sys
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import QCursor, QFont, QPainter, QColor, QPen, QBrush

try:
    from gui.window_capture import set_window_exclude_from_capture, set_window_include_in_capture
except ImportError:
    set_window_exclude_from_capture = None
    set_window_include_in_capture = None

DEFAULT_TIP_OVERLAY_OPACITY = 242  # 0–255, по умолчанию почти непрозрачный
BORDER_RADIUS = 8


class TipOverlay(QWidget):
    """Плавающее окно с подсказкой, привязанное к курсору."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TipOverlay")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._exclude_from_capture = False
        self._background_opacity = DEFAULT_TIP_OVERLAY_OPACITY
        self._tip_visible = True  # чекбокс «Отображать подсказку»: при False окно делаем невидимым через setWindowOpacity(0)
        self.setStyleSheet("TipOverlay QLabel { color: #E8E8E8; background: transparent; font-size: 12px; line-height: 1.4; }")
        lo = QVBoxLayout(self)
        lo.setContentsMargins(12, 10, 12, 10)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(320)
        self.label.setMinimumWidth(200)
        self.label.setFont(QFont("Segoe UI", 11))
        lo.addWidget(self.label)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._follow_cursor)
        self._offset = QPoint(24, 24)
    
    def set_tip(self, text: str):
        self.label.setText(text or "")
        self.adjustSize()
    
    def set_background_opacity(self, value: int):
        """Прозрачность только фона подложки (0–255). Текст остаётся непрозрачным."""
        self._background_opacity = max(0, min(255, value))
        self.update()

    def paintEvent(self, event):
        """Рисуем фон вручную с учётом прозрачности — на Windows стиль фона у frameless-окна иначе не применяется."""
        alpha = max(0, min(255, self._background_opacity))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.rect()
        bg = QColor(28, 28, 35, alpha)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(QColor(255, 184, 108, 102), 1))
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), BORDER_RADIUS, BORDER_RADIUS)
    
    def set_tip_visible(self, visible: bool):
        """Включение/выключение подсказки без hide: полная прозрачность окна (0) или показ (1)."""
        self._tip_visible = bool(visible)
        self.setWindowOpacity(1.0 if self._tip_visible else 0.0)
    
    def set_exclude_from_capture(self, exclude: bool):
        """Скрыть окно подсказки от захвата экрана (трансляция). Один чекбокс в настройках управляет основным окном и окном подсказки."""
        self._exclude_from_capture = bool(exclude)
        if self.isVisible() and sys.platform == "win32" and set_window_exclude_from_capture and set_window_include_in_capture:
            hwnd = int(self.winId())
            if self._exclude_from_capture:
                set_window_exclude_from_capture(hwnd)
            else:
                set_window_include_in_capture(hwnd)
    
    def showEvent(self, event):
        super().showEvent(event)
        if self._exclude_from_capture and sys.platform == "win32" and set_window_exclude_from_capture:
            try:
                set_window_exclude_from_capture(int(self.winId()))
            except Exception:
                pass
    
    def show_overlay(self):
        self.show()
        self.setWindowOpacity(1.0 if self._tip_visible else 0.0)
        self._timer.start(100)
    
    def hide_overlay(self):
        self._timer.stop()
        self.hide()
    
    def _follow_cursor(self):
        pos = QCursor.pos()
        x = pos.x() + self._offset.x()
        y = pos.y() + self._offset.y()
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            w, h = self.width(), self.height()
            x = min(max(x, rect.x()), rect.right() - w)
            y = min(max(y, rect.y()), rect.bottom() - h)
        self.move(x, y)
