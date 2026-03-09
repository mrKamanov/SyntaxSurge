# -*- coding: utf-8 -*-
"""
Единое поле ввода горячей клавиши: клик — затем нажатие клавиш или кнопки мыши
(с модификатором) записывается в одно значение.
"""

from PySide6.QtWidgets import QLineEdit, QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QKeyEvent, QMouseEvent

# Совпадает с main_window: индексы 1,2,3 = Средняя, Боковая 1, Боковая 2
MOUSE_BUTTON_LABELS = ["", "Средняя", "Боковая 1", "Боковая 2"]
# Модификатор мыши: 0=—, 1=Ctrl, 2=Alt, 3=Shift
MOUSE_MOD_LABELS = ["", "Ctrl", "Alt", "Shift"]

# Qt -> наш индекс кнопки (0 = не использовать); в PySide6 используем .value
_QT_BUTTON_TO_INDEX = {
    Qt.MouseButton.MiddleButton.value: 1,
    Qt.MouseButton.BackButton.value: 2,     # Боковая 1
    Qt.MouseButton.ForwardButton.value: 3,  # Боковая 2
}


def _modifiers_to_index(mods) -> int:
    try:
        v = mods.value if hasattr(mods, "value") else int(mods)
    except (TypeError, ValueError):
        return 0
    if v & Qt.KeyboardModifier.ControlModifier.value:
        return 1
    if v & Qt.KeyboardModifier.AltModifier.value:
        return 2
    if v & Qt.KeyboardModifier.ShiftModifier.value:
        return 3
    return 0


class HotkeyEdit(QLineEdit):
    """Одно поле: кликаешь, нажимаешь клавиши или кнопку мыши — записывается одна комбинация."""

    valueChanged = Signal()

    def __init__(self, mouse_only_no_mod: bool = False, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Кликните и нажмите клавиши или кнопку мыши…")
        self._mouse_only_no_mod = mouse_only_no_mod  # для паузы: только кнопка мыши
        self._key_sequence = QKeySequence()
        self._mouse_btn_index = 0  # 0 = не задано, 1–3 = Средняя, Боковая 1, Боковая 2
        self._mouse_mod_index = 0   # 0 = нет, 1 = Ctrl, 2 = Alt, 3 = Shift
        self._update_display()

    def _set_frame_highlight(self, on: bool):
        """Включить/выключить оранжевую подсветку родительского фрейма (Qt не поддерживает :focus-within)."""
        parent = self.parent()
        if isinstance(parent, QFrame):
            parent.setProperty("hotkeyActive", on)
            style = parent.style()
            style.unpolish(parent)
            style.polish(parent)
            parent.update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._set_frame_highlight(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._set_frame_highlight(False)

    def _update_display(self):
        if not self._key_sequence.isEmpty():
            self.setText(self._key_sequence.toString())
            return
        if self._mouse_btn_index > 0:
            parts = [MOUSE_BUTTON_LABELS[self._mouse_btn_index]]
            if not self._mouse_only_no_mod and self._mouse_mod_index > 0:
                parts.append(MOUSE_MOD_LABELS[self._mouse_mod_index])
            self.setText(" + ".join(parts))
            return
        self.clear()

    def keySequence(self) -> QKeySequence:
        return QKeySequence(self._key_sequence)

    def setKeySequence(self, seq: QKeySequence):
        self._key_sequence = QKeySequence(seq) if seq else QKeySequence()
        self._mouse_btn_index = 0
        self._mouse_mod_index = 0
        self._update_display()

    def getMouseButtonIndex(self) -> int:
        return self._mouse_btn_index

    def getMouseModifierIndex(self) -> int:
        return self._mouse_mod_index

    def setMouse(self, button_index: int, mod_index: int):
        self._key_sequence = QKeySequence()
        self._mouse_btn_index = max(0, min(3, button_index))
        self._mouse_mod_index = 0 if self._mouse_only_no_mod else max(0, min(3, mod_index))
        self._update_display()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        key_val = key.value if hasattr(key, "value") else key
        if key_val in (Qt.Key.Key_Control.value, Qt.Key.Key_Shift.value, Qt.Key.Key_Alt.value,
                       Qt.Key.Key_Meta.value, Qt.Key.Key_AltGr.value):
            return
        mods = event.modifiers()
        mods_val = mods.value if hasattr(mods, "value") else mods
        seq = QKeySequence(mods_val | key_val)
        if not seq.isEmpty():
            self._key_sequence = seq
            self._mouse_btn_index = 0
            self._mouse_mod_index = 0
            self._update_display()
            self.valueChanged.emit()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        btn = event.button()
        btn_val = btn.value if hasattr(btn, "value") else int(btn)
        idx = _QT_BUTTON_TO_INDEX.get(btn_val, 0)
        if idx == 0:
            super().mousePressEvent(event)
            return
        mod_idx = 0 if self._mouse_only_no_mod else _modifiers_to_index(event.modifiers())
        self._key_sequence = QKeySequence()
        self._mouse_btn_index = idx
        self._mouse_mod_index = mod_idx
        self._update_display()
        self.valueChanged.emit()
        event.accept()
