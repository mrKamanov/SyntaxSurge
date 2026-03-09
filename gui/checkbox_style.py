# -*- coding: utf-8 -*-
"""
Ярко-оранжевая галочка в отмеченном чекбоксе.
При setStyleSheet на окне Qt рисует индикатор сам и наш QProxyStyle не вызывается,
поэтому галочку рисуем в виджете: GlassCheckBox переопределяет paintEvent.
"""
from PySide6.QtWidgets import QProxyStyle, QStyle, QCheckBox, QStyleOptionButton
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath

CHECK_ORANGE = "#FF9900"


def draw_checkmark(painter: QPainter, rect: QRect):
    """
    Рисует ярко-оранжевую галочку строго внутри rect.
    Отступ от краёв и толщина линии масштабируются под размер области,
    чтобы галочка помещалась и в маленьком, и в крупном индикаторе.
    """
    w, h = rect.width(), rect.height()
    if w < 6 or h < 6:
        return
    # Отступ не меньше 3px и не меньше 28% от меньшей стороны — галочка всегда внутри
    side = min(w, h)
    margin = max(3, int(side * 0.28))
    inner_w = w - 2 * margin
    inner_h = h - 2 * margin
    if inner_w < 2 or inner_h < 2:
        return
    # Форма галочки в долях от внутреннего прямоугольника (0..1), с небольшим отступом от краёв формы
    pad = 0.12
    x1 = rect.x() + margin + inner_w * (0.15 + pad)
    y1 = rect.y() + margin + inner_h * (0.55)
    x2 = rect.x() + margin + inner_w * (0.40)
    y2 = rect.y() + margin + inner_h * (0.82)
    x3 = rect.x() + margin + inner_w * (0.92 - pad)
    y3 = rect.y() + margin + inner_h * (0.22)
    path = QPainterPath()
    path.moveTo(x1, y1)
    path.lineTo(x2, y2)
    path.lineTo(x3, y3)
    # Толщина пера: тоньше при маленьком индикаторе, чтобы не заполнять область
    pen_width = max(1, side // 10)
    pen = QPen(QColor(CHECK_ORANGE))
    pen.setWidth(pen_width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()


class GlassCheckBox(QCheckBox):
    """
    Чекбокс, который после стандартной отрисовки (в т.ч. из стилей) дорисовывает
    оранжевую галочку в индикаторе. Обходит перекрытие стилями из setStyleSheet.
    """
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        ind_rect = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, opt, self
        )
        if ind_rect.isValid():
            painter = QPainter(self)
            draw_checkmark(painter, ind_rect)
            painter.end()


class CheckboxWithCheckStyle(QProxyStyle):
    """После отрисовки индикатора чекбокса (стили/базовый стиль) рисуем оранжевую галочку, если checked."""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            super().drawPrimitive(element, option, painter, widget)
            # Дорисовываем галочку, если отмечено
            if option.state & QStyle.StateFlag.State_On:
                r = option.rect
                if r.width() >= 10 and r.height() >= 10:
                    draw_checkmark(painter, r)
            return
        super().drawPrimitive(element, option, painter, widget)
