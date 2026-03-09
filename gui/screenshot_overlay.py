# -*- coding: utf-8 -*-
"""
Полноэкранный оверлей для выбора области скриншота мышью.
После выделения — на том же экране превью и две кнопки «Отправить» / «Распознать текст».
"""

from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Qt, QPoint, QRect, Signal, QSize
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen, QGuiApplication, QImage


PREVIEW_MAX = 480
BTN_GAP = 12
BTN_Y_OFFSET = 20


class ScreenshotOverlay(QWidget):
    """Полный экран: затемнённый снимок, выделение области мышью. После отпускания — превью и кнопки на том же оверлее."""

    send_clicked = Signal(object)      # QImage
    recognize_clicked = Signal(object)   # QImage

    def __init__(self, full_pixmap: QPixmap, screen_geometry: QRect, parent=None):
        super().__init__(parent)
        self._pixmap = full_pixmap
        self._screen_geometry = screen_geometry
        self._start = None
        self._current = None
        self._result_mode = False
        self._captured_image = None
        self._preview_rect = QRect()
        self._send_btn = None
        self._recognize_btn = None
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def _selection_rect(self):
        if self._start is None or self._current is None:
            return QRect()
        return QRect(self._start, self._current).normalized()

    def _scaled_preview_rect(self) -> QRect:
        """Прямоугольник для отрисовки превью по центру экрана (макс. PREVIEW_MAX по длинной стороне)."""
        if self._captured_image is None or self._captured_image.isNull():
            return QRect()
        w, h = self._captured_image.width(), self._captured_image.height()
        if w <= 0 or h <= 0:
            return QRect()
        if w >= h:
            tw = min(w, PREVIEW_MAX)
            th = max(1, h * tw // w)
        else:
            th = min(h, PREVIEW_MAX)
            tw = max(1, w * th // h)
        cx = self.width() // 2
        cy = self.height() // 2
        return QRect(cx - tw // 2, cy - th // 2, tw, th)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self.rect(), self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 140))

        if self._result_mode and self._captured_image is not None and not self._captured_image.isNull():
            self._preview_rect = self._scaled_preview_rect()
            if not self._preview_rect.isEmpty():
                scaled = QPixmap.fromImage(self._captured_image).scaled(
                    self._preview_rect.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                p.drawPixmap(self._preview_rect, scaled)
                p.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.SolidLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(self._preview_rect.adjusted(0, 0, -1, -1))
        else:
            rect = self._selection_rect()
            if not rect.isEmpty():
                src = self._rect_to_pixmap(rect)
                p.drawPixmap(rect, self._pixmap, src)
                p.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.SolidLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.end()

    def _rect_to_pixmap(self, widget_rect: QRect) -> QRect:
        if self._pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return QRect()
        x = widget_rect.x() * self._pixmap.width() // self.width()
        y = widget_rect.y() * self._pixmap.height() // self.height()
        w = max(1, widget_rect.width() * self._pixmap.width() // self.width())
        h = max(1, widget_rect.height() * self._pixmap.height() // self.height())
        return QRect(x, y, w, h)

    def _create_buttons(self):
        if self._send_btn is not None:
            return
        self._send_btn = QPushButton("Отправить", self)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(
            "background: rgba(255, 184, 108, 0.5); color: #fff; border: 1px solid rgba(255, 184, 108, 0.7);"
            " border-radius: 8px; padding: 10px 24px; font-size: 13px;"
        )
        self._send_btn.clicked.connect(self._on_send)
        self._recognize_btn = QPushButton("Распознать текст", self)
        self._recognize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recognize_btn.setStyleSheet(
            "background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.95);"
            " border: 1px solid rgba(255,255,255,0.3); border-radius: 8px; padding: 10px 24px; font-size: 13px;"
        )
        self._recognize_btn.clicked.connect(self._on_recognize)

    def _update_buttons_geometry(self):
        if self._send_btn is None or self._recognize_btn is None:
            return
        pr = self._preview_rect
        if pr.isEmpty():
            pr = QRect(self.width() // 2 - 100, self.height() // 2 - 60, 200, 120)
        by = pr.bottom() + BTN_Y_OFFSET
        self._send_btn.adjustSize()
        self._recognize_btn.adjustSize()
        sw, sh = self._send_btn.size().width(), self._send_btn.size().height()
        rw, rh = self._recognize_btn.size().width(), self._recognize_btn.size().height()
        total = sw + BTN_GAP + rw
        left = (self.width() - total) // 2
        self._send_btn.setGeometry(left, by, sw, sh)
        self._recognize_btn.setGeometry(left + sw + BTN_GAP, by, rw, rh)

    def _on_send(self):
        if self._captured_image is not None and not self._captured_image.isNull():
            self.send_clicked.emit(self._captured_image)
        self.close()

    def _on_recognize(self):
        if self._captured_image is not None and not self._captured_image.isNull():
            self.recognize_clicked.emit(self._captured_image)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._result_mode:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._current = self._start
            self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._result_mode:
            event.accept()
            return
        if self._start is not None:
            self._current = event.position().toPoint()
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            event.accept()
            return
        if self._result_mode:
            event.accept()
            return
        rect = self._selection_rect()
        min_side = 8
        if rect.width() >= min_side and rect.height() >= min_side:
            src_rect = self._rect_to_pixmap(rect)
            img = self._pixmap.copy(src_rect).toImage()
            if not img.isNull():
                cb = QGuiApplication.clipboard()
                if cb:
                    cb.setImage(img)
                self._captured_image = img
                self._result_mode = True
                self._create_buttons()
                self.update()
                self._preview_rect = self._scaled_preview_rect()
                self._update_buttons_geometry()
                self._send_btn.show()
                self._recognize_btn.show()
        self._start = None
        self._current = None
        event.accept()
