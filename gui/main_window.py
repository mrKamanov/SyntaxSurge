#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SyntaxSurge — главное окно в стиле glassmorphism.
Зависимость: PySide6 (pip install PySide6)
На Windows включается размытие фона (DWM).
Стили вынесены в gui.styles.
"""

import sys
import os
import re
import tempfile
import threading
from typing import Optional

# При прямом запуске gui/main_window.py корень проекта не в path — добавляем
if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from typer.map_cleanup import prune_map_dir
        from typer import MAP_DIR
        prune_map_dir(MAP_DIR)
    except Exception:
        pass

import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QSystemTrayIcon,
    QMenu,
    QTabWidget,
    QComboBox,
    QFormLayout,
    QScrollArea,
    QSlider,
    QPlainTextEdit,
    QTextEdit,
    QStyle,
)
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QSettings, QTimer, QEvent, QObject, Signal, QPropertyAnimation, QEasingCurve, QThread, QBuffer, QByteArray, QIODevice, QProcess
from PySide6.QtGui import QColor, QFont, QAction, QKeySequence, QPalette, QShortcut, QPainter, QPainterPath, QPen, QIcon, QImage

# Подавить предупреждение Qt о SetProcessDpiAwarenessContext на Windows (не влияет на работу приложения)
_qt_original_message_handler = None
def _qt_message_handler(mode, context, message):
    msg = message if isinstance(message, str) else str(message)
    if "SetProcessDpiAwarenessContext" in msg or ("qt.qpa.window" in msg and "DPI" in msg):
        return
    if _qt_original_message_handler:
        _qt_original_message_handler(mode, context, message)
from PySide6.QtCore import qInstallMessageHandler
_qt_original_message_handler = qInstallMessageHandler(_qt_message_handler)

from gui.styles import get_stylesheet, DEFAULT_GLASS_OPACITY, COMBO_POPUP_STYLE
from gui import app_icons
from gui.checkbox_style import GlassCheckBox
from gui.hotkey_edit import HotkeyEdit
from gui.code_display import strip_code_fences, normalize_assistant_answer, PythonHighlighter, AssistantTranscriptHighlighter, AssistantAnswerHighlighter, markdown_review_to_html, response_to_html
from gui.tip_overlay import TipOverlay, DEFAULT_TIP_OVERLAY_OPACITY
from gui.screenshot_overlay import ScreenshotOverlay
from gui.main_window_constants import (
    ASSISTANT_SEND_PROMPT,
    SCREENSHOT_TASK_PROMPT,
    WINDOW_WIDTH_BASE,
    WINDOW_HEIGHT_FRACTION,
    TITLE,
    PEEK_WIDTH,
    PIN_ANIM_DURATION,
    MOUSE_BUTTONS,
    MOUSE_BUTTON_KEYS,
    MOUSE_MODS,
    MOUSE_MOD_KEYS,
)
from gui.main_window_workers import (
    ApiRequestWorker,
    ScreenshotSendWorker,
    OCRWorker,
    TipsRequestWorker,
    CodeReviewWorker,
    TyperWorker,
    _normalize_content_key,
    _parse_block_tips,
    pip_install_rapidocr_command,
)
from gui import audio_devices
from api_config import (
    API_AUTH_OPTIONS,
    AUTH_VALUES,
    PRESETS,
    apply_preset_to_slot,
    auth_index_from_value,
    auth_value_from_index,
)

try:
    from typer import (
        CodeMapBuilder,
        CodePrinter,
        TyperAborted,
        MAP_DIR,
        LOG_DIR,
        prune_map_dir,
        get_active_window_type,
        get_active_window_display,
        ActiveWindowType as WindowType,
    )
    from typer.cursor_bridge import start as cursor_bridge_start, get_source as cursor_bridge_get_source
    _typer_available = True
except ImportError:
    _typer_available = False
    get_active_window_type = None
    get_active_window_display = None
    cursor_bridge_get_source = None
    WindowType = None

try:
    import pyautogui
    _pyautogui_available = True
except ImportError:
    _pyautogui_available = False

try:
    from api_client import chat_completion, chat_completion_with_image
except ImportError:
    chat_completion = None
    chat_completion_with_image = None

try:
    from gui import assistant_speech as _assistant_speech_module
    _assistant_speech_available = _assistant_speech_module.is_available()
except Exception:
    _assistant_speech_available = False
    _assistant_speech_module = None

def _clamp_pos_to_screen(pos: QPoint, size, screen=None) -> QPoint:
    """Ограничить позицию окна областью экрана, чтобы не терять окно за краем."""
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return pos
    r = screen.availableGeometry()
    x = max(r.x(), min(pos.x(), r.right() - size.width() + 1))
    y = max(r.y(), min(pos.y(), r.bottom() - size.height() + 1))
    return QPoint(x, y)


def _config_path():
    """Путь к файлу настроек. Без Qt — только os, чтобы работало до создания приложения."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    dir_path = os.path.join(base, "SyntaxSurge")
    try:
        os.makedirs(dir_path, exist_ok=True)
    except OSError:
        dir_path = os.path.expanduser("~")
    return os.path.join(dir_path, "settings.ini")


def _open_settings():
    """QSettings с форматом INI и фиксированным путём к файлу."""
    path = _config_path()
    fmt = getattr(QSettings.Format, "IniFormat", None) or getattr(QSettings, "IniFormat", 1)
    return QSettings(path, fmt)


try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


class MouseShortcutEmitter(QObject):
    """Слушает глобальные нажатия мыши (pynput) и вызывает действие при совпадении комбо."""
    action_triggered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bindings = []
        self._mods = {"ctrl": False, "alt": False, "shift": False}
        self._listener_key = None
        self._listener_mouse = None
        self._running = False

    def start(self):
        if not PYNPUT_AVAILABLE or self._running:
            return
        self._running = True
        def on_press(key):
            try:
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._mods["ctrl"] = True
                elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._mods["alt"] = True
                elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self._mods["shift"] = True
            except Exception:
                pass
        def on_release(key):
            try:
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._mods["ctrl"] = False
                elif key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._mods["alt"] = False
                elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self._mods["shift"] = False
            except Exception:
                pass
        def on_click(x, y, button, pressed):
            if not pressed:
                return
            btn_key = "none"
            if button == mouse.Button.middle:
                btn_key = "middle"
            elif button == mouse.Button.x1:
                btn_key = "x1"
            elif button == mouse.Button.x2:
                btn_key = "x2"
            mod_key = "none"
            if self._mods["ctrl"]:
                mod_key = "ctrl"
            elif self._mods["alt"]:
                mod_key = "alt"
            elif self._mods["shift"]:
                mod_key = "shift"
            for name, b, m in self._bindings:
                if b != "none" and b == btn_key and m == mod_key:
                    self.action_triggered.emit(name)
                    return
        try:
            self._listener_key = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener_mouse = mouse.Listener(on_click=on_click)
            self._listener_key.start()
            self._listener_mouse.start()
        except Exception:
            self._running = False

    def set_bindings(self, bindings):
        self._bindings = list(bindings) if bindings else []

    def stop(self):
        self._running = False
        try:
            if self._listener_mouse:
                self._listener_mouse.stop()
                self._listener_mouse = None
            if self._listener_key:
                self._listener_key.stop()
                self._listener_key = None
        except Exception:
            pass


def enable_blur_behind(hwnd: int) -> bool:
    """Включает размытие фона окна (Windows 10+). hwnd — winId() главного виджета."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        WCA_ACCENT_POLICY = 19
        ACCENT_ENABLE_BLURBEHIND = 3

        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", wintypes.DWORD),
                ("AccentFlags", wintypes.DWORD),
                ("GradientColor", wintypes.DWORD),
                ("AnimationId", wintypes.DWORD),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attrib", wintypes.DWORD),
                ("pData", ctypes.c_void_p),
                ("dataSize", ctypes.c_size_t),
            ]

        SetWindowCompositionAttribute = user32.SetWindowCompositionAttribute
        SetWindowCompositionAttribute.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA),
        ]
        SetWindowCompositionAttribute.restype = wintypes.BOOL

        accent = ACCENT_POLICY(ACCENT_ENABLE_BLURBEHIND, 0, 0, 0)
        data = WINDOWCOMPOSITIONATTRIBDATA(
            WCA_ACCENT_POLICY,
            ctypes.byref(accent),
            ctypes.sizeof(accent),
        )
        return bool(SetWindowCompositionAttribute(ctypes.c_void_p(hwnd), ctypes.byref(data)))
    except Exception:
        return False


from gui.window_capture import (
    set_window_exclude_from_capture,
    set_window_include_in_capture,
    apply_tooltip_windows_exclude_from_capture,
)

# Цвет кривых у заголовка (бирюзовый)
TITLE_CURVES_COLOR = "#00D4CC"


class TitleCurvesOverlay(QWidget):
    """Рисует две бирюзовые кривые между «Syntax» и оранжевой плашкой «Surge» (под и над)."""
    def __init__(self, parent: QWidget, syntax_label: QLabel, surge_label: QLabel):
        super().__init__(parent)
        self._syntax = syntax_label
        self._surge = surge_label
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def resizeEvent(self, event):
        self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        super().resizeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        r1 = self._syntax.geometry()
        r2 = self._surge.geometry()
        if r1.isNull() or r2.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        pen = QPen(QColor(TITLE_CURVES_COLOR))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        dot_r = 3
        # Кривая снизу: от области под "x" в Syntax до верхнего правого угла плашки
        start_low = (r1.x() + int(r1.width() * 0.82), r1.y() + r1.height() + 2)
        end_low = (r2.x() + r2.width() - 6, r2.y() + 6)
        ctrl1_low = (start_low[0] + 25, start_low[1] + 18)
        ctrl2_low = (end_low[0] - 25, end_low[1] - 18)
        path_low = QPainterPath()
        path_low.moveTo(start_low[0], start_low[1])
        path_low.cubicTo(ctrl1_low[0], ctrl1_low[1], ctrl2_low[0], ctrl2_low[1], end_low[0], end_low[1])
        painter.drawPath(path_low)
        painter.setBrush(QColor(TITLE_CURVES_COLOR))
        painter.drawEllipse(start_low[0] - dot_r, start_low[1] - dot_r, dot_r * 2, dot_r * 2)
        painter.drawEllipse(end_low[0] - dot_r, end_low[1] - dot_r, dot_r * 2, dot_r * 2)
        # Кривая сверху: от области над "t" в Syntax до нижнего правого угла плашки
        start_high = (r1.x() + int(r1.width() * 0.18), r1.y() - 2)
        end_high = (r2.x() + r2.width() - 6, r2.y() + r2.height() - 6)
        ctrl1_high = (start_high[0] - 20, start_high[1] - 18)
        ctrl2_high = (end_high[0] - 20, end_high[1] + 18)
        path_high = QPainterPath()
        path_high.moveTo(start_high[0], start_high[1])
        path_high.cubicTo(ctrl1_high[0], ctrl1_high[1], ctrl2_high[0], ctrl2_high[1], end_high[0], end_high[1])
        painter.drawPath(path_high)
        painter.drawEllipse(start_high[0] - dot_r, start_high[1] - dot_r, dot_r * 2, dot_r * 2)
        painter.drawEllipse(end_high[0] - dot_r, end_high[1] - dot_r, dot_r * 2, dot_r * 2)
        painter.end()


# Высота поля задания на главной: компактная и при фокусе (многострочный ввод)
TASK_EDIT_HEIGHT_COLLAPSED = 40
TASK_EDIT_HEIGHT_EXPANDED = 200


class ExpandableTaskEdit(QPlainTextEdit):
    """Поле задания для ИИ: пока не выбрано — строго одна строка по высоте, при клике расширяется для многострочного ввода."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glassInput")
        self._collapse()

    def _collapse(self):
        self.setMinimumHeight(TASK_EDIT_HEIGHT_COLLAPSED)
        self.setMaximumHeight(TASK_EDIT_HEIGHT_COLLAPSED)

    def _expand(self):
        self.setMinimumHeight(TASK_EDIT_HEIGHT_EXPANDED)
        self.setMaximumHeight(350)

    def focusInEvent(self, event):
        self._expand()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._collapse()
        super().focusOutEvent(event)


# Высота поля промпта: компактная и при фокусе (развёрнутая)
PROMPT_EDIT_HEIGHT_COLLAPSED = 52
PROMPT_EDIT_HEIGHT_EXPANDED = 220


class ExpandablePromptEdit(QPlainTextEdit):
    """Поле ввода промпта: компактное по умолчанию, при клике/фокусе разворачивается для удобного просмотра и редактирования."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glassPromptEdit")
        self.setMinimumHeight(PROMPT_EDIT_HEIGHT_COLLAPSED)
        self.setMaximumHeight(400)

    def focusInEvent(self, event):
        self.setMinimumHeight(PROMPT_EDIT_HEIGHT_EXPANDED)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.setMinimumHeight(PROMPT_EDIT_HEIGHT_COLLAPSED)
        super().focusOutEvent(event)


class TitleBlockContainer(QWidget):
    """Контейнер заголовка: Syntax, Surge в плашке, кривые, косая черта. Оверлей с кривыми подгоняется при resize."""
    def __init__(self):
        super().__init__()
        row = QHBoxLayout(self)
        row.setAlignment(Qt.AlignCenter)
        row.setSpacing(0)
        self._syntax = QLabel("Syntax")
        self._syntax.setObjectName("glassTitleMain")
        self._surge = QLabel("Surge /")
        self._surge.setObjectName("glassTitleAccent")
        for lbl in (self._syntax, self._surge):
            lbl.setMinimumHeight(44)
            font = QFont()
            font.setPointSize(28)
            font.setWeight(QFont.Weight.Black)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
            lbl.setFont(font)
        row.addStretch(1)
        row.addWidget(self._syntax)
        row.addWidget(self._surge)
        row.addStretch(1)
        self._overlay = TitleCurvesOverlay(self, self._syntax, self._surge)
        self._overlay.lower()

    def resizeEvent(self, event):
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)


class GlassMainWindow(QMainWindow):
    """Главное окно в стиле «стекло»: размытие, скругления, тёмная тема, акценты."""
    assistant_text_signal = Signal(str, bool, str)  # text, is_final, role
    assistant_finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        screen = QApplication.primaryScreen().availableGeometry()
        w = max(WINDOW_WIDTH_BASE, int(screen.width() * 0.32))
        h = int(screen.height() * WINDOW_HEIGHT_FRACTION)
        self.setFixedSize(w, h)
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        central = QWidget(self)
        central.setObjectName("centralContainer")
        self.setCentralWidget(central)
        # Контейнер прозрачный; стеклянный фон только у right_panel, чтобы полоска под сайдбаром была прозрачной
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_left_sidebar()
        root_layout.addWidget(sidebar)

        right_panel = QWidget()
        right_panel.setObjectName("glassFrame")
        layout = QVBoxLayout(right_panel)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(12)

        # Верхняя панель: кнопки «Свернуть в трей», «Приклеить», «Закрыть»
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        _icon_size_title = QSize(20, 20)
        _title_icon_color = "#E8E8EC"  # светлая иконка на тёмной шапке
        self.tray_btn = QPushButton()
        self.tray_btn.setIcon(app_icons.icon_with_color(app_icons.TITLE_TRAY, _title_icon_color))
        self.tray_btn.setIconSize(_icon_size_title)
        self.tray_btn.setObjectName("glassTitleBtn")
        self.tray_btn.setFixedSize(32, 28)
        self.tray_btn.setToolTip("Свернуть в трей")
        self.tray_btn.clicked.connect(self._minimize_to_tray)
        self.pin_btn = QPushButton()
        self.pin_btn.setIcon(app_icons.icon_with_color(app_icons.TITLE_PIN_OFF, _title_icon_color))
        self.pin_btn.setIconSize(_icon_size_title)
        self.pin_btn.setObjectName("glassTitleBtn")
        self.pin_btn.setFixedSize(32, 28)
        self.pin_btn.setToolTip("Приклеить к краю экрана")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(False)
        self.pin_btn.clicked.connect(self._on_pin_toggle)
        self.close_btn = QPushButton()
        self.close_btn.setIcon(app_icons.icon_with_color(app_icons.TITLE_CLOSE, _title_icon_color))
        self.close_btn.setIconSize(_icon_size_title)
        self.close_btn.setObjectName("glassCloseBtn")
        self.close_btn.setFixedSize(32, 28)
        self.close_btn.setToolTip("Закрыть")
        self.close_btn.clicked.connect(self._quit_app)
        top_bar.addWidget(self.tray_btn)
        top_bar.addWidget(self.pin_btn)
        top_bar.addWidget(self.close_btn)
        layout.addLayout(top_bar)

        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("glassMainTabs")
        self.main_tabs.addTab(self._build_main_page(), "Главная")
        self.main_tabs.addTab(self._build_settings_page(), "Настройки")
        self.main_tabs.addTab(self._build_api_page(), "API")
        self.main_tabs.addTab(self._build_prompt_page(), "Промпт")
        self.main_tabs.addTab(self._build_assistant_page(), "Помощник")
        layout.addWidget(self.main_tabs, 1)

        root_layout.addWidget(right_panel, 1)

        self.setStyleSheet(get_stylesheet())
        self._apply_combo_popup_style()

        # Тень только у стеклянной панели (область под сайдбаром без тени и без фона)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(100, 80, 180, 90))
        shadow.setOffset(0, 4)
        right_panel.setGraphicsEffect(shadow)

        self._setup_tray()
        self._pinned = False
        self._normal_pos = None
        self._pin_collapse_timer = QTimer(self)
        self._pin_collapse_timer.setSingleShot(True)
        self._pin_collapse_timer.timeout.connect(self._do_pin_collapse)
        self._pin_allow_collapse = True  # после выезда 300 ms не реагируем на leave — убирает мелькание
        self._pin_expand_guard_timer = QTimer(self)
        self._pin_expand_guard_timer.setSingleShot(True)
        self._pin_expand_guard_timer.timeout.connect(self._pin_allow_collapse_on)
        self._pin_anim = None
        self._keyboard_shortcuts = []
        self._typer_pause_event = threading.Event()
        self._typer_paused_now = [False]
        self._typer_abort_event = threading.Event()
        self._typer_tips = {}
        self._cached_tips_text = None  # текст ответа, для которого уже получены подсказки (не слать в API повторно)
        self._typer_current_block = None
        self._typer_current_line_index = None
        self._tip_overlay = TipOverlay()
        self._load_settings()
        self._update_all_shortcuts()
        if _typer_available:
            prune_map_dir(MAP_DIR)
            cursor_bridge_start()
        self._typer_dest_timer = QTimer(self)
        self._typer_dest_timer.timeout.connect(self._update_typer_destination_indicator)
        self._typer_dest_timer.start(1500)
        self._update_typer_destination_indicator()
        self._mouse_emitter = MouseShortcutEmitter(self)
        self._mouse_emitter.action_triggered.connect(self._on_mouse_action)
        self._mouse_emitter.start()
        self._mouse_emitter.set_bindings(self._get_mouse_bindings())
        self.assistant_text_signal.connect(self._append_assistant_text)
        self.assistant_finished_signal.connect(self._on_assistant_thread_finished)

    def _get_hotkey_edit_for_action(self, action_key: str) -> HotkeyEdit:
        attr = "key_move_window" if action_key == "pin" else f"key_{action_key}"
        return getattr(self, attr)

    def _get_hotkey_display(self, action_key: str) -> str:
        """Текущая строка горячей клавиши для действия (как в поле настроек) или пустая."""
        he = self._get_hotkey_edit_for_action(action_key)
        return (he.text() or "").strip()

    def _tooltip_with_hotkey(self, base_tooltip: str, action_key: str) -> str:
        """Подсказка с добавлением текущей горячей клавиши, если задана."""
        hotkey = self._get_hotkey_display(action_key)
        if not hotkey:
            return base_tooltip
        return f"{base_tooltip}\nГорячая клавиша: {hotkey}"

    def _update_all_hotkey_tooltips(self):
        """Обновить подсказки кнопок с учётом текущих назначений горячих клавиш."""
        if getattr(self, "tray_btn", None):
            self.tray_btn.setToolTip(self._tooltip_with_hotkey("Свернуть в трей", "hide"))
        if getattr(self, "pin_btn", None):
            self.pin_btn.setToolTip(self._tooltip_with_hotkey("Приклеить к краю экрана", "pin"))
        if getattr(self, "type_response_btn", None) and _typer_available:
            self.type_response_btn.setToolTip(self._tooltip_with_hotkey("Печатать ответ в активное окно (редактор/браузер)", "start_typer"))
        if getattr(self, "_sidebar_typer_btn", None):
            self._sidebar_typer_btn.setToolTip(self._tooltip_with_hotkey("Печать ответа", "start_typer"))
        if getattr(self, "_sidebar_pause_btn", None):
            self._sidebar_pause_btn.setToolTip(self._tooltip_with_hotkey("Пауза печати", "pause"))
        if getattr(self, "_sidebar_screenshot_btn", None):
            self._sidebar_screenshot_btn.setToolTip(self._tooltip_with_hotkey("Скриншот", "screenshot"))
        if getattr(self, "_sidebar_get_answer_btn", None):
            self._sidebar_get_answer_btn.setToolTip(self._tooltip_with_hotkey("Получить ответ", "get_answer"))
        if getattr(self, "_sidebar_assistant_start_btn", None):
            self._sidebar_assistant_start_btn.setToolTip(self._tooltip_with_hotkey("Старт распознавания", "assistant_start"))
        if getattr(self, "_sidebar_assistant_send_btn", None):
            self._sidebar_assistant_send_btn.setToolTip(self._tooltip_with_hotkey("Отправить (Помощник)", "assistant_send"))
        if getattr(self, "assistant_start_btn", None) and _assistant_speech_available:
            self.assistant_start_btn.setToolTip(self._tooltip_with_hotkey("Старт распознавания", "assistant_start"))
        if getattr(self, "assistant_send_btn", None):
            self.assistant_send_btn.setToolTip(self._tooltip_with_hotkey("Отправить (Помощник)", "assistant_send"))

    def _get_hotkey_binding(self, edit: HotkeyEdit):
        """Возвращает (\"key\", строка) или (\"mouse\", btn_index, mod_index) или None если пусто."""
        if not edit.keySequence().isEmpty():
            return ("key", edit.keySequence().toString())
        if edit.getMouseButtonIndex() > 0:
            return ("mouse", edit.getMouseButtonIndex(), edit.getMouseModifierIndex())
        return None

    def _on_hotkey_edited(self, changed_edit: HotkeyEdit):
        """При дубликате сбрасывает комбинацию у других полей, у текущего оставляет новое назначение."""
        binding = self._get_hotkey_binding(changed_edit)
        if binding is None:
            self._save_settings()
            return
        for key in ("hide", "show", "screenshot", "get_answer", "start_typer", "pin", "pause", "assistant_start", "assistant_send"):
            other = self._get_hotkey_edit_for_action(key)
            if other is changed_edit:
                continue
            other_b = self._get_hotkey_binding(other)
            if other_b and other_b == binding:
                other.blockSignals(True)
                other.setKeySequence(QKeySequence())
                other.setMouse(0, 0)
                other.blockSignals(False)
        self._save_settings()

    def _get_mouse_bindings(self):
        out = []
        for key in ("hide", "show", "screenshot", "get_answer", "start_typer", "pin", "pause", "assistant_start", "assistant_send"):
            he = self._get_hotkey_edit_for_action(key)
            bi = he.getMouseButtonIndex()
            mi = 0 if key == "pause" else he.getMouseModifierIndex()
            if bi <= 0:
                continue
            out.append((key, MOUSE_BUTTON_KEYS[bi], MOUSE_MOD_KEYS[mi]))
        return out

    def _on_mouse_action(self, action_name: str):
        if action_name == "hide":
            self._minimize_to_tray()
        elif action_name == "show":
            self._restore_from_tray()
        elif action_name == "screenshot":
            self._on_screenshot()
        elif action_name == "get_answer":
            self._on_get_answer_shortcut()
        elif action_name == "start_typer":
            self._on_start_or_stop_typer()
        elif action_name == "pin":
            self._on_pin_toggle()
        elif action_name == "pause":
            self._on_pause_shortcut()
        elif action_name == "assistant_start":
            self._on_assistant_start_shortcut()
        elif action_name == "assistant_send":
            self._on_assistant_send_shortcut()

    def _build_main_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("glassScrollContent")
        lo = QVBoxLayout(page)
        lo.setContentsMargins(0, 4, 0, 0)
        lo.setSpacing(14)
        title_block = TitleBlockContainer()
        lo.addWidget(title_block)
        autotype_row = QHBoxLayout()
        autotype_label = QLabel("Автопечать")
        autotype_label.setObjectName("glassLabel")
        self.autotype_toggle = GlassCheckBox()
        self.autotype_toggle.setObjectName("glassToggle")
        self.autotype_toggle.setChecked(False)
        self.autotype_toggle.setFixedSize(48, 26)
        self.autotype_toggle.toggled.connect(self._on_autotype_toggled)
        autotype_row.addWidget(autotype_label)
        autotype_row.addStretch()
        autotype_row.addWidget(self.autotype_toggle)
        lo.addLayout(autotype_row)
        self.task_edit = ExpandableTaskEdit()
        self.task_edit.setPlaceholderText("Вставьте задание...")
        lo.addWidget(self.task_edit)
        self.send_btn = QPushButton("Отправить ИИ")
        self.send_btn.setObjectName("glassPrimaryButton")
        self.send_btn.setMinimumHeight(44)
        self.send_btn.clicked.connect(self._on_send_clicked)
        lo.addWidget(self.send_btn)
        response_label = QLabel("Ответ ИИ")
        response_label.setObjectName("glassSectionTitle")
        lo.addWidget(response_label)
        # Индикатор «куда пойдёт печать» (цвет через палитру; WA_StyledBackground=False — стили не трогают фон)
        self.typer_dest_bar = QWidget()
        self.typer_dest_bar.setObjectName("typerDestBar")
        self.typer_dest_bar.setFixedHeight(8)
        self.typer_dest_bar.setMinimumWidth(60)
        self.typer_dest_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.typer_dest_bar.setAutoFillBackground(True)
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#546E7A"))
        self.typer_dest_bar.setPalette(pal)
        self.typer_dest_label = QLabel("Печать: —")
        self.typer_dest_label.setObjectName("glassLabel")
        self.typer_dest_label.setStyleSheet("font-size: 11px; color: rgba(200,200,210,0.9);")
        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)
        dest_row.addWidget(self.typer_dest_bar)
        dest_row.addWidget(self.typer_dest_label)
        dest_row.addStretch()
        self.type_response_btn = QPushButton()
        self.type_response_btn.setObjectName("glassPrimaryButton")
        self.type_response_btn.setFixedSize(44, 44)
        self.type_response_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PLAY)))
        self.type_response_btn.setIconSize(QSize(20, 20))
        self.type_response_btn.setToolTip("Печатать ответ в активное окно (редактор/браузер)")
        self.type_response_btn.clicked.connect(self._start_typer_from_response)
        if not _typer_available:
            self.type_response_btn.setEnabled(False)
            self.type_response_btn.setToolTip("Модуль typer не найден.")
        dest_row.addWidget(self.type_response_btn)
        lo.addLayout(dest_row)
        self.response_tabs = QTabWidget()
        self.response_tabs.setObjectName("glassTabs")
        # Вкладка «Ответ» — текст ответа ИИ
        response_tab = QWidget()
        response_tab_lo = QVBoxLayout(response_tab)
        response_tab_lo.setContentsMargins(0, 0, 0, 0)
        self.response_edit = QTextEdit()
        self.response_edit.setObjectName("glassResponseArea")
        self.response_edit.setReadOnly(True)
        self.response_edit.setPlaceholderText("Здесь будет отображаться ответ... (с подсветкой Python, SQL, JS и др.)")
        self.response_edit.setMinimumHeight(140)
        self.response_edit.setMinimumWidth(200)
        self.response_edit.setAcceptRichText(True)
        self._response_raw_text = None
        response_tab_lo.addWidget(self.response_edit)
        self.response_tabs.addTab(response_tab, "Ответ")
        # Вкладка «Подсказки» — разбор кода (построчные подсказки и блоки), заполняется при получении подсказок от API
        tips_tab = QWidget()
        tips_tab_lo = QVBoxLayout(tips_tab)
        tips_tab_lo.setContentsMargins(0, 0, 0, 0)
        self.tips_review_edit = QPlainTextEdit()
        self.tips_review_edit.setObjectName("glassResponseArea")
        self.tips_review_edit.setReadOnly(True)
        self.tips_review_edit.setPlaceholderText("Подсказки по коду появятся здесь после запуска печати (разбор приходит от API).")
        self.tips_review_edit.setMinimumHeight(140)
        self.tips_review_edit.setMinimumWidth(200)
        tips_tab_lo.addWidget(self.tips_review_edit)
        self.response_tabs.addTab(tips_tab, "Подсказки")
        # Вкладка «Ревью» — код-ревью от сеньора: оценка, советы, варианты кода
        review_tab = QWidget()
        review_tab_lo = QVBoxLayout(review_tab)
        review_tab_lo.setContentsMargins(0, 0, 0, 0)
        review_header = QHBoxLayout()
        self.get_review_btn = QPushButton()
        self.get_review_btn.setObjectName("glassPrimaryButton")
        self.get_review_btn.setFixedSize(44, 44)
        self.get_review_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_GET_ANSWER)))
        self.get_review_btn.setIconSize(QSize(20, 20))
        self.get_review_btn.setToolTip("Получить ревью кода (ответ из вкладки «Ответ») — уровень сеньора, советы и варианты")
        self.get_review_btn.clicked.connect(self._on_get_review_clicked)
        review_header.addWidget(self.get_review_btn)
        review_header.addWidget(QLabel("Получить ревью"))
        review_header.addStretch()
        review_tab_lo.addLayout(review_header)
        self.review_edit = QTextEdit()
        self.review_edit.setObjectName("glassResponseArea")
        self.review_edit.setReadOnly(True)
        self.review_edit.setPlaceholderText("Нажмите «Получить ревью» — код из вкладки «Ответ» будет отправлен в API. Появится структурированное ревью в формате Markdown: заголовки, списки, блоки кода.")
        self.review_edit.setMinimumHeight(140)
        self.review_edit.setMinimumWidth(200)
        self.review_edit.setAcceptRichText(True)
        review_tab_lo.addWidget(self.review_edit)
        self.response_tabs.addTab(review_tab, "Ревью")
        lo.addWidget(self.response_tabs, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("glassScroll")
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setObjectName("glassScrollContent")
        lo = QVBoxLayout(inner)
        lo.setSpacing(20)

        # Секция: Горячие клавиши — клик по полю и нажатие нужной комбинации
        hotkey_title = QLabel("Горячие клавиши")
        hotkey_title.setObjectName("glassSectionTitle")
        lo.addWidget(hotkey_title)
        hotkey_hint = QLabel("Задайте комбинацию клавиш (клик по полю → нажмите клавиши) и/или кнопку мыши с модификатором. По умолчанию ничего не назначено.")
        hotkey_hint.setObjectName("glassLabel")
        hotkey_hint.setWordWrap(True)
        hotkey_hint.setStyleSheet("color: rgba(200,200,210,0.8); font-size: 12px; margin-bottom: 8px;")
        lo.addWidget(hotkey_hint)

        def _hl(text):
            l = QLabel(text)
            l.setObjectName("glassLabel")
            return l

        def _apply_hotkey_edit_palette(edit: HotkeyEdit):
            color = QColor(200, 200, 210)
            pal = edit.palette()
            pal.setColor(QPalette.ColorRole.Text, color)
            pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, color)
            pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, color)
            edit.setPalette(pal)

        _hotkey_label_min_width = 260

        def _hotkey_row(hotkey_edit: HotkeyEdit, label_text: str, _action_key: str):
            hotkey_edit.setObjectName("glassInput")
            hotkey_edit.valueChanged.connect(lambda he=hotkey_edit: self._on_hotkey_edited(he))
            hotkey_edit.setMinimumWidth(200)
            _apply_hotkey_edit_palette(hotkey_edit)
            row = QFrame()
            row.setObjectName("glassKeyEditFrame")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.setSpacing(8)
            row_layout.addWidget(hotkey_edit)
            row_layout.addStretch()
            lbl = _hl(label_text)
            lbl.setMinimumWidth(_hotkey_label_min_width)
            return lbl, row

        form_hk = QFormLayout()
        form_hk.setSpacing(8)
        form_hk.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.key_hide = HotkeyEdit()
        l1, r1 = _hotkey_row(self.key_hide, "Скрыть окно", "hide")
        form_hk.addRow(l1, r1)
        self.key_show = HotkeyEdit()
        l2, r2 = _hotkey_row(self.key_show, "Показать окно", "show")
        form_hk.addRow(l2, r2)
        self.key_screenshot = HotkeyEdit()
        l3, r3 = _hotkey_row(self.key_screenshot, "Скриншот", "screenshot")
        form_hk.addRow(l3, r3)
        self.key_get_answer = HotkeyEdit()
        l4, r4 = _hotkey_row(self.key_get_answer, "Получить ответ", "get_answer")
        form_hk.addRow(l4, r4)
        self.key_start_typer = HotkeyEdit()
        l4b, r4b = _hotkey_row(self.key_start_typer, "Печать ответа", "start_typer")
        form_hk.addRow(l4b, r4b)
        self.key_move_window = HotkeyEdit()
        l5, r5 = _hotkey_row(self.key_move_window, "Приклеить к краю", "pin")
        form_hk.addRow(l5, r5)
        self.key_pause = HotkeyEdit(mouse_only_no_mod=True)
        self.key_pause.setPlaceholderText("Кликните и нажмите кнопку мыши (для паузы — только мышь)")
        l6, r6 = _hotkey_row(self.key_pause, "Пауза печати", "pause")
        form_hk.addRow(l6, r6)
        self.key_assistant_start = HotkeyEdit()
        l7, r7 = _hotkey_row(self.key_assistant_start, "Старт распознавания (Помощник)", "assistant_start")
        form_hk.addRow(l7, r7)
        self.key_assistant_send = HotkeyEdit()
        l8, r8 = _hotkey_row(self.key_assistant_send, "Отправить (Помощник)", "assistant_send")
        form_hk.addRow(l8, r8)
        lo.addLayout(form_hk)
        hotkey_reset_btn = QPushButton("Сбросить все горячие клавиши")
        hotkey_reset_btn.setObjectName("glassLabel")
        hotkey_reset_btn.setStyleSheet("color: rgba(200,200,210,0.9); font-size: 12px; padding: 6px 12px; background: transparent; border: 1px solid rgba(255,255,255,0.25); border-radius: 6px;")
        hotkey_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hotkey_reset_btn.setToolTip("Очистить все назначения (клавиши и мышь). Назначайте заново сами.")
        hotkey_reset_btn.clicked.connect(self._reset_all_hotkeys)
        lo.addWidget(hotkey_reset_btn)

        # Секция: Приватность
        priv_title = QLabel("Приватность")
        priv_title.setObjectName("glassSectionTitle")
        lo.addWidget(priv_title)
        self.check_hide_from_capture = GlassCheckBox("Скрыть окно от захвата экрана")
        self.check_hide_from_capture.setObjectName("glassToggle")
        self.check_hide_from_capture.setToolTip("Основное окно, окно подсказки и всплывающие подсказки не будут попадать в захват экрана (трансляция).")
        self.check_hide_from_capture.toggled.connect(self._save_settings)
        self.check_hide_from_capture.toggled.connect(self._apply_hide_from_capture)
        lo.addWidget(self.check_hide_from_capture)

        # Секция: Окно
        win_title = QLabel("Окно")
        win_title.setObjectName("glassSectionTitle")
        lo.addWidget(win_title)
        self.check_always_on_top = GlassCheckBox("Окно поверх всех окон")
        self.check_always_on_top.setObjectName("glassToggle")
        self.check_always_on_top.toggled.connect(self._on_always_on_top_toggled)
        lo.addWidget(self.check_always_on_top)

        # Прозрачность окна
        opacity_label = QLabel("Прозрачность окна")
        opacity_label.setObjectName("glassLabel")
        lo.addWidget(opacity_label)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(150, 255)
        self.opacity_slider.setValue(DEFAULT_GLASS_OPACITY)
        self.opacity_slider.setMinimumWidth(120)
        self.opacity_slider.setMaximumWidth(120)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        lo.addWidget(self.opacity_slider)

        # Окно подсказки (при автопечати)
        tip_title = QLabel("Окно подсказки")
        tip_title.setObjectName("glassSectionTitle")
        lo.addWidget(tip_title)
        self.check_show_tip = GlassCheckBox("Отображать подсказку")
        self.check_show_tip.setObjectName("glassToggle")
        self.check_show_tip.setChecked(True)
        self.check_show_tip.toggled.connect(self._on_show_tip_toggled)
        self.check_show_tip.toggled.connect(self._save_settings)
        lo.addWidget(self.check_show_tip)
        tip_opacity_label = QLabel("Прозрачность фона окна подсказки")
        tip_opacity_label.setObjectName("glassLabel")
        lo.addWidget(tip_opacity_label)
        self.tip_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.tip_opacity_slider.setRange(100, 255)
        self.tip_opacity_slider.setValue(DEFAULT_TIP_OVERLAY_OPACITY)
        self.tip_opacity_slider.setMinimumWidth(120)
        self.tip_opacity_slider.setMaximumWidth(120)
        self.tip_opacity_slider.valueChanged.connect(self._on_tip_opacity_changed)
        lo.addWidget(self.tip_opacity_slider)

        # Секция: Язык — переключатель RU / EN в стиле приложения
        lang_title = QLabel("Язык")
        lang_title.setObjectName("glassSectionTitle")
        lo.addWidget(lang_title)
        lang_row = QHBoxLayout()
        self.lang_ru_btn = QPushButton("RU")
        self.lang_ru_btn.setObjectName("glassLangSwitch")
        self.lang_ru_btn.setCheckable(True)
        self.lang_ru_btn.setChecked(True)
        self.lang_ru_btn.clicked.connect(self._on_lang_ru)
        self.lang_en_btn = QPushButton("EN")
        self.lang_en_btn.setObjectName("glassLangSwitch")
        self.lang_en_btn.setCheckable(True)
        self.lang_en_btn.clicked.connect(self._on_lang_en)
        lang_row.addWidget(self.lang_ru_btn)
        lang_row.addWidget(self.lang_en_btn)
        lang_row.addStretch()
        lo.addLayout(lang_row)

        # Секция: Помощник — микрофон и голос собеседника (звук для вкладки «Помощник»)
        assistant_title = QLabel("Помощник (источники звука)")
        assistant_title.setObjectName("glassSectionTitle")
        lo.addWidget(assistant_title)
        assistant_hint = QLabel("Микрофон — ваш голос. Голос собеседника — захват с ПК (напр. Стерео микшер для звонков). Одно устройство нельзя выбрать в обоих полях.")
        assistant_hint.setObjectName("glassLabel")
        assistant_hint.setWordWrap(True)
        assistant_hint.setStyleSheet("color: rgba(200,200,210,0.8); font-size: 12px; margin-bottom: 6px;")
        lo.addWidget(assistant_hint)
        input_devices = audio_devices.get_input_audio_devices()
        form_asst = QFormLayout()
        form_asst.setSpacing(10)
        self.assistant_mic_combo = QComboBox()
        self.assistant_mic_combo.setObjectName("glassCombo")
        self.assistant_mic_combo.setMinimumWidth(220)
        self.assistant_mic_combo.addItem("— не использовать", -1)
        if input_devices:
            for name, idx in input_devices:
                self.assistant_mic_combo.addItem(name, idx)
            self.assistant_mic_combo.currentIndexChanged.connect(self._on_assistant_mic_combo_changed)
        else:
            if not audio_devices.sounddevice_available:
                self.assistant_mic_combo.addItem("— устройств не найдено (установите sounddevice)", -1)
            self.assistant_mic_combo.setEnabled(False)
        self.assistant_interlocutor_combo = QComboBox()
        self.assistant_interlocutor_combo.setObjectName("glassCombo")
        self.assistant_interlocutor_combo.setMinimumWidth(220)
        self.assistant_interlocutor_combo.setToolTip(
            "Захват звука с ПК (YouTube, звонки): в Windows включите «Стерео микшер» в Параметры → Звук → Устройства ввода."
        )
        self.assistant_interlocutor_combo.addItem("— не использовать", -1)
        if input_devices:
            for name, idx in input_devices:
                self.assistant_interlocutor_combo.addItem(name, idx)
            self.assistant_interlocutor_combo.currentIndexChanged.connect(self._on_assistant_interlocutor_combo_changed)
        form_asst.addRow(_hl("Микрофон (ваш голос):"), self.assistant_mic_combo)
        form_asst.addRow(_hl("Голос собеседника (захват с ПК):"), self.assistant_interlocutor_combo)
        lo.addLayout(form_asst)

        lo.addStretch(1)
        scroll.setWidget(inner)
        page_lo = QVBoxLayout(page)
        page_lo.setContentsMargins(0, 0, 0, 0)
        page_lo.addWidget(scroll)
        return page

    def _build_api_page(self) -> QWidget:
        w = QWidget()
        w.setObjectName("glassScrollContent")
        lo = QVBoxLayout(w)
        api_title = QLabel("API")
        api_title.setObjectName("glassSectionTitle")
        lo.addWidget(api_title)
        api_hint = QLabel(
            "Выберите провайдера для быстрой настройки или настройте вручную. "
            "OpenRouter, OpenAI, Gemini, Ollama, LM Studio — совместимы с форматом OpenAI."
        )
        api_hint.setObjectName("glassLabel")
        api_hint.setWordWrap(True)
        api_hint.setStyleSheet("color: rgba(200,200,210,0.85); font-size: 12px; margin-bottom: 6px;")
        lo.addWidget(api_hint)
        # Три слота API
        self._api_slot_name = ["API 1", "API 2", "API 3"]
        self._api_slot_key = ["", "", ""]
        self._api_slot_url = ["", "", ""]
        self._api_slot_model = ["", "", ""]
        self._api_slot_auth = [AUTH_VALUES[0], AUTH_VALUES[0], AUTH_VALUES[0]]
        self._api_active_index = 0
        self._api_for_main_index = 0
        self._api_for_assistant_index = 0
        self._api_for_screenshots_index = 0

        def _api_label(txt):
            l = QLabel(txt)
            l.setObjectName("glassLabel")
            return l

        usage_hint = QLabel("Какой API для каких запросов использовать (можно один и тот же слот для всего):")
        usage_hint.setObjectName("glassLabel")
        usage_hint.setWordWrap(True)
        usage_hint.setStyleSheet("color: rgba(200,200,210,0.85); font-size: 12px; margin-bottom: 4px;")
        lo.addWidget(usage_hint)
        usage_form = QFormLayout()
        usage_form.setSpacing(8)
        self.api_for_main_combo = QComboBox()
        self.api_for_main_combo.setObjectName("glassCombo")
        self.api_for_main_combo.setMinimumWidth(200)
        for i in range(3):
            self.api_for_main_combo.addItem(f"API {i + 1}", i)
        self.api_for_main_combo.currentIndexChanged.connect(self._save_settings)
        usage_form.addRow(_api_label("Для вкладки «Главная»:"), self.api_for_main_combo)
        self.api_for_assistant_combo = QComboBox()
        self.api_for_assistant_combo.setObjectName("glassCombo")
        self.api_for_assistant_combo.setMinimumWidth(200)
        for i in range(3):
            self.api_for_assistant_combo.addItem(f"API {i + 1}", i)
        self.api_for_assistant_combo.currentIndexChanged.connect(self._save_settings)
        usage_form.addRow(_api_label("Для вкладки «Помощник»:"), self.api_for_assistant_combo)
        self.api_for_screenshots_combo = QComboBox()
        self.api_for_screenshots_combo.setObjectName("glassCombo")
        self.api_for_screenshots_combo.setMinimumWidth(200)
        for i in range(3):
            self.api_for_screenshots_combo.addItem(f"API {i + 1}", i)
        self.api_for_screenshots_combo.currentIndexChanged.connect(self._save_settings)
        usage_form.addRow(_api_label("Для скриншотов:"), self.api_for_screenshots_combo)
        lo.addLayout(usage_form)

        active_label = QLabel("Редактировать слот (выберите, чтобы изменить название, ключ, URL, модель):")
        active_label.setObjectName("glassLabel")
        lo.addWidget(active_label)
        api_switch_row = QHBoxLayout()
        self.api_btn_1 = QPushButton("1")
        self.api_btn_1.setObjectName("glassLangSwitch")
        self.api_btn_1.setCheckable(True)
        self.api_btn_1.setChecked(True)
        self.api_btn_1.setMinimumWidth(72)
        self.api_btn_1.clicked.connect(lambda: self._on_api_slot_clicked(0))
        self.api_btn_2 = QPushButton("2")
        self.api_btn_2.setObjectName("glassLangSwitch")
        self.api_btn_2.setCheckable(True)
        self.api_btn_2.setMinimumWidth(72)
        self.api_btn_2.clicked.connect(lambda: self._on_api_slot_clicked(1))
        self.api_btn_3 = QPushButton("3")
        self.api_btn_3.setObjectName("glassLangSwitch")
        self.api_btn_3.setCheckable(True)
        self.api_btn_3.setMinimumWidth(72)
        self.api_btn_3.clicked.connect(lambda: self._on_api_slot_clicked(2))
        api_switch_row.addWidget(self.api_btn_1)
        api_switch_row.addWidget(self.api_btn_2)
        api_switch_row.addWidget(self.api_btn_3)
        api_switch_row.addStretch()
        lo.addLayout(api_switch_row)

        form = QFormLayout()
        form.setSpacing(12)
        self.api_provider_combo = QComboBox()
        self.api_provider_combo.setObjectName("glassCombo")
        self.api_provider_combo.addItem("— Вручную")
        for p in PRESETS:
            self.api_provider_combo.addItem(p["name"], p["id"])
        self.api_provider_combo.currentIndexChanged.connect(self._on_api_provider_changed)
        form.addRow(_api_label("Провайдер:"), self.api_provider_combo)

        self.api_name_edit = QLineEdit()
        self.api_name_edit.setObjectName("glassInput")
        self.api_name_edit.setPlaceholderText("Например: OpenAI, OpenRouter, Ollama")
        self.api_name_edit.textChanged.connect(self._on_api_name_changed)
        form.addRow(_api_label("Название:"), self.api_name_edit)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setObjectName("glassInput")
        self.api_key_edit.setPlaceholderText("Ключ с сайта провайдера (для Ollama/LM Studio можно пусто)")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.textChanged.connect(self._save_settings)
        form.addRow(_api_label("API-ключ:"), self.api_key_edit)
        self.api_url_edit = QLineEdit()
        self.api_url_edit.setObjectName("glassInput")
        self.api_url_edit.setPlaceholderText("URL из пресета или свой")
        self.api_url_edit.textChanged.connect(self._save_settings)
        form.addRow(_api_label("URL API:"), self.api_url_edit)
        self.api_model_edit = QLineEdit()
        self.api_model_edit.setObjectName("glassInput")
        self.api_model_edit.setPlaceholderText("Модель из списка провайдера")
        self.api_model_edit.textChanged.connect(self._save_settings)
        form.addRow(_api_label("Модель:"), self.api_model_edit)
        self.api_auth_combo = QComboBox()
        self.api_auth_combo.addItems(API_AUTH_OPTIONS)
        self.api_auth_combo.setObjectName("glassCombo")
        self.api_auth_combo.currentIndexChanged.connect(self._on_api_auth_changed)
        form.addRow(_api_label("Авторизация:"), self.api_auth_combo)
        lo.addLayout(form)
        lo.addStretch(1)
        return w

    def _build_prompt_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("glassScroll")
        scroll.setStyleSheet("background: transparent;")
        scroll.viewport().setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setObjectName("glassScrollContent")
        lo = QVBoxLayout(inner)
        lo.setSpacing(16)
        prompt_title = QLabel("Промпт")
        prompt_title.setObjectName("glassSectionTitle")
        lo.addWidget(prompt_title)
        prompt_hint = QLabel("Шаблоны для запросов к ИИ. Кликните по полю — оно развернётся для удобного просмотра и редактирования.")
        prompt_hint.setObjectName("glassLabel")
        prompt_hint.setWordWrap(True)
        prompt_hint.setStyleSheet("color: rgba(200,200,210,0.85); font-size: 12px; margin-bottom: 6px;")
        lo.addWidget(prompt_hint)
        active_hint = QLabel("Активный промпт (один) используется по горячей клавише «Получить ответ»: выделите текст в любом приложении (IDE, браузер и т.д.), нажмите горячую клавишу — в ИИ уйдёт активный промпт + выделенный текст.")
        active_hint.setObjectName("glassLabel")
        active_hint.setWordWrap(True)
        active_hint.setStyleSheet("color: rgba(200,200,210,0.85); font-size: 11px; margin-bottom: 4px;")
        lo.addWidget(active_hint)
        self.prompt_edits = []
        self.prompt_active_checkboxes = []
        self.prompt_active_index = -1  # 0..5 или -1 если ни один не выбран
        for i in range(6):
            row = QHBoxLayout()
            lbl = QLabel(f"Промпт {i + 1}")
            lbl.setObjectName("glassLabel")
            row.addWidget(lbl)
            chk = GlassCheckBox("Активный")
            chk.setObjectName("glassLabel")
            chk.setChecked(False)
            chk.toggled.connect(lambda checked, idx=i: self._on_prompt_active_toggled(idx, checked))
            self.prompt_active_checkboxes.append(chk)
            row.addWidget(chk)
            row.addStretch(1)
            lo.addLayout(row)
            edit = ExpandablePromptEdit()
            edit.setPlaceholderText(f"Введите текст промпта {i + 1}...")
            edit.textChanged.connect(self._save_settings)
            self.prompt_edits.append(edit)
            lo.addWidget(edit)
        assistant_prompt_title = QLabel("Промпт для помощника")
        assistant_prompt_title.setObjectName("glassSectionTitle")
        lo.addWidget(assistant_prompt_title)
        assistant_prompt_hint = QLabel("Используется только во вкладке «Помощник» при нажатии «Отправить»: к диалогу добавляется этот промпт. Редактируйте при необходимости.")
        assistant_prompt_hint.setObjectName("glassLabel")
        assistant_prompt_hint.setWordWrap(True)
        assistant_prompt_hint.setStyleSheet("color: rgba(200,200,210,0.85); font-size: 12px; margin-bottom: 6px;")
        lo.addWidget(assistant_prompt_hint)
        assistant_prompt_reset_row = QHBoxLayout()
        assistant_prompt_reset_btn = QPushButton("Вернуть стандартный промпт")
        assistant_prompt_reset_btn.setObjectName("glassLabel")
        assistant_prompt_reset_btn.setStyleSheet("color: rgba(200,200,210,0.9); font-size: 12px; padding: 6px 12px; background: transparent; border: 1px solid rgba(255,255,255,0.25); border-radius: 6px;")
        assistant_prompt_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        assistant_prompt_reset_btn.setToolTip("Подставить промпт, встроенный в приложение (как при первом запуске)")
        assistant_prompt_reset_btn.clicked.connect(self._on_assistant_prompt_reset)
        assistant_prompt_reset_row.addWidget(assistant_prompt_reset_btn)
        assistant_prompt_reset_row.addStretch()
        lo.addLayout(assistant_prompt_reset_row)
        self.assistant_prompt_edit = ExpandablePromptEdit()
        self.assistant_prompt_edit.setPlainText(ASSISTANT_SEND_PROMPT)
        self.assistant_prompt_edit.setPlaceholderText("Текст промпта для анализа диалога (по умолчанию — встроенный шаблон).")
        self.assistant_prompt_edit.textChanged.connect(self._save_settings)
        lo.addWidget(self.assistant_prompt_edit)

        screenshot_prompt_title = QLabel("Промпт для скриншота")
        screenshot_prompt_title.setObjectName("glassSectionTitle")
        lo.addWidget(screenshot_prompt_title)
        screenshot_prompt_hint = QLabel("Используется при отправке скриншота в API: на изображении задание с собеседования — ответ должен быть только чистым кодом без комментариев. Редактируйте при необходимости.")
        screenshot_prompt_hint.setObjectName("glassLabel")
        screenshot_prompt_hint.setWordWrap(True)
        screenshot_prompt_hint.setStyleSheet("color: rgba(200,200,210,0.85); font-size: 12px; margin-bottom: 6px;")
        lo.addWidget(screenshot_prompt_hint)
        screenshot_prompt_reset_row = QHBoxLayout()
        screenshot_prompt_reset_btn = QPushButton("Вернуть стандартный промпт")
        screenshot_prompt_reset_btn.setObjectName("glassLabel")
        screenshot_prompt_reset_btn.setStyleSheet("color: rgba(200,200,210,0.9); font-size: 12px; padding: 6px 12px; background: transparent; border: 1px solid rgba(255,255,255,0.25); border-radius: 6px;")
        screenshot_prompt_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        screenshot_prompt_reset_btn.setToolTip("Подставить промпт, встроенный в приложение")
        screenshot_prompt_reset_btn.clicked.connect(self._on_screenshot_prompt_reset)
        screenshot_prompt_reset_row.addWidget(screenshot_prompt_reset_btn)
        screenshot_prompt_reset_row.addStretch()
        lo.addLayout(screenshot_prompt_reset_row)
        self.screenshot_prompt_edit = ExpandablePromptEdit()
        self.screenshot_prompt_edit.setPlainText(SCREENSHOT_TASK_PROMPT)
        self.screenshot_prompt_edit.setPlaceholderText("Промпт для запроса по скриншоту с заданием (по умолчанию — встроенный шаблон).")
        self.screenshot_prompt_edit.textChanged.connect(self._save_settings)
        lo.addWidget(self.screenshot_prompt_edit)

        lo.addStretch(1)
        scroll.setWidget(inner)
        page_lo = QVBoxLayout(page)
        page_lo.setContentsMargins(0, 0, 0, 0)
        page_lo.addWidget(scroll)
        return page

    def _build_assistant_page(self) -> QWidget:
        """Вкладка «Помощник»: микрофон, источник для собеседника, окно распознанного текста. Без скролла страницы — скролл только у текста."""
        page = QWidget()
        lo = QVBoxLayout(page)
        lo.setSpacing(16)

        assistant_title = QLabel("Помощник")
        assistant_title.setObjectName("glassSectionTitle")
        lo.addWidget(assistant_title)
        answer_row = QHBoxLayout()
        answer_label = QLabel("Ответ:")
        answer_label.setObjectName("glassSectionTitle")
        answer_row.addWidget(answer_label)
        self.assistant_send_btn = QPushButton()
        self.assistant_send_btn.setFixedSize(44, 44)
        self.assistant_send_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_SEND)))
        self.assistant_send_btn.setIconSize(QSize(20, 20))
        self.assistant_send_btn.setObjectName("glassAssistantButton")
        self.assistant_send_btn.setStyleSheet(
            "QPushButton { background-color: #FF9900; color: #000000; border: 2px solid #CC7A00; "
            "border-radius: 10px; padding: 6px; outline: none; }"
            "QPushButton:hover { background-color: #FFB833; border-color: #CC7A00; outline: none; }"
            "QPushButton:pressed { background-color: #E68A00; outline: none; }"
            "QPushButton:focus { outline: none; border-color: #CC7A00; }"
            "QPushButton:disabled { background-color: #4A4A4A; color: #AAAAAA; border-color: #555555; }"
        )
        self.assistant_send_btn.clicked.connect(self._on_assistant_send_clicked)
        answer_row.addWidget(self.assistant_send_btn)
        self.assistant_answer_float_btn = QPushButton("Вынести ответ")
        self.assistant_answer_float_btn.setObjectName("glassLabel")
        self.assistant_answer_float_btn.setStyleSheet("color: rgba(200,200,210,0.9); font-size: 12px; padding: 6px 12px; background: transparent; border: 1px solid rgba(255,255,255,0.25); border-radius: 6px;")
        self.assistant_answer_float_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.assistant_answer_float_btn.setToolTip("Вынести область ответа в отдельное окно и разместить где удобно")
        self.assistant_answer_float_btn.clicked.connect(self._on_assistant_answer_float)
        answer_row.addWidget(self.assistant_answer_float_btn)
        answer_row.addStretch()
        lo.addLayout(answer_row)
        job_label = QLabel("Должность (для контекста собеседования):")
        job_label.setObjectName("glassLabel")
        lo.addWidget(job_label)
        self.assistant_job_edit = QLineEdit()
        self.assistant_job_edit.setObjectName("glassInput")
        self.assistant_job_edit.setPlaceholderText("Например: Python-разработчик, менеджер проектов")
        self.assistant_job_edit.textChanged.connect(self._save_settings)
        lo.addWidget(self.assistant_job_edit)
        self.assistant_answer_edit = QPlainTextEdit()
        self.assistant_answer_edit.setObjectName("glassResponseArea")
        self.assistant_answer_edit.setPlaceholderText("Здесь появится ответ по диалогу...")
        self.assistant_answer_edit.setMinimumHeight(120)
        self.assistant_answer_edit.setMinimumWidth(280)
        self.assistant_answer_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        doc = self.assistant_answer_edit.document()
        doc.setDocumentMargin(10)
        self._assistant_answer_highlighter = AssistantAnswerHighlighter(doc)
        lo.addWidget(self.assistant_answer_edit)

        # Окно распознанного текста — кнопки сразу над областью текста
        rec_label = QLabel("Распознанный текст:")
        rec_label.setObjectName("glassSectionTitle")
        lo.addWidget(rec_label)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.assistant_start_btn = QPushButton("▶  Старт распознавания")
        self.assistant_start_btn.setObjectName("glassAssistantButton")
        self.assistant_start_btn.setMinimumHeight(44)
        self.assistant_start_btn.setMinimumWidth(200)
        self._apply_assistant_button_style(self.assistant_start_btn, is_stop=False)
        self.assistant_start_btn.clicked.connect(self._on_assistant_start_clicked)
        if not _assistant_speech_available:
            self.assistant_start_btn.setEnabled(False)
            self.assistant_start_btn.setToolTip("Установите sherpa-onnx и sounddevice: pip install sherpa-onnx sounddevice")
        self.assistant_stop_btn = QPushButton("■  Стоп")
        self.assistant_stop_btn.setObjectName("glassAssistantButton")
        self.assistant_stop_btn.setMinimumHeight(44)
        self.assistant_stop_btn.setMinimumWidth(110)
        self._apply_assistant_button_style(self.assistant_stop_btn, is_stop=True)
        self.assistant_stop_btn.setEnabled(False)
        self.assistant_stop_btn.clicked.connect(self._on_assistant_stop_clicked)
        self.assistant_mute_btn = QPushButton()
        self.assistant_mute_btn.setObjectName("glassAssistantButton")
        self.assistant_mute_btn.setFixedSize(44, 44)
        self.assistant_mute_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_VOLUME)))
        self.assistant_mute_btn.setIconSize(QSize(20, 20))
        self.assistant_mute_btn.setStyleSheet(
            "QPushButton { background-color: #FF9900; color: #000000; border: 2px solid #CC7A00; "
            "border-radius: 10px; padding: 6px; outline: none; }"
            "QPushButton:hover { background-color: #FFB833; border-color: #CC7A00; outline: none; }"
            "QPushButton:pressed { background-color: #E68A00; outline: none; }"
            "QPushButton:focus { outline: none; border-color: #CC7A00; }"
            "QPushButton:disabled { background-color: #4A4A4A; color: #AAAAAA; border-color: #555555; }"
        )
        self.assistant_mute_btn.setEnabled(False)
        self.assistant_mute_btn.setCheckable(True)
        self.assistant_mute_btn.setChecked(False)
        self.assistant_mute_btn.clicked.connect(self._on_assistant_mute_clicked)
        self.assistant_clear_btn = QPushButton()
        self.assistant_clear_btn.setFixedSize(44, 44)
        self.assistant_clear_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_CLEAR)))
        self.assistant_clear_btn.setIconSize(QSize(20, 20))
        self.assistant_clear_btn.setObjectName("glassAssistantButton")
        self.assistant_clear_btn.setStyleSheet(
            "QPushButton { background-color: #FF9900; color: #000000; border: 2px solid #CC7A00; "
            "border-radius: 10px; padding: 6px; outline: none; }"
            "QPushButton:hover { background-color: #FFB833; border-color: #CC7A00; outline: none; }"
            "QPushButton:pressed { background-color: #E68A00; outline: none; }"
            "QPushButton:focus { outline: none; border-color: #CC7A00; }"
            "QPushButton:disabled { background-color: #4A4A4A; color: #AAAAAA; border-color: #555555; }"
        )
        self.assistant_clear_btn.clicked.connect(self._on_assistant_clear_clicked)
        btn_row.addWidget(self.assistant_start_btn)
        btn_row.addWidget(self.assistant_stop_btn)
        btn_row.addWidget(self.assistant_mute_btn)
        btn_row.addWidget(self.assistant_clear_btn)
        btn_row.addStretch()
        lo.addLayout(btn_row)
        self._assistant_btn_row = btn_row
        self.assistant_transcript_edit = QPlainTextEdit()
        self.assistant_transcript_edit.setObjectName("glassResponseArea")
        self.assistant_transcript_edit.setReadOnly(True)
        self.assistant_transcript_edit.setPlaceholderText("Диалог: «Вы» — с микрофона, «Собеседник» — с ПК (напр. Стерео микшер при звонке).")
        self.assistant_transcript_edit.setMinimumHeight(200)
        self.assistant_transcript_edit.setMinimumWidth(280)
        self._assistant_transcript_highlighter = AssistantTranscriptHighlighter(self.assistant_transcript_edit.document())
        lo.addWidget(self.assistant_transcript_edit, 1)
        # Поток и событие остановки распознавания (инициализируем при первом старте)
        self._assistant_stop_event = None
        self._assistant_thread = None
        self._assistant_page = page
        self._assistant_answer_float_window = None

        return page

    def _on_assistant_answer_float(self):
        """Вынести область «Ответ» в отдельное окно."""
        if getattr(self, "_assistant_answer_float_window", None) is not None:
            return
        page = getattr(self, "_assistant_page", None)
        if page is None or not getattr(self, "assistant_answer_edit", None):
            return
        lo_page = page.layout()
        idx = lo_page.indexOf(self.assistant_answer_edit)
        if idx < 0:
            return
        self._assistant_answer_float_index = idx
        float_win = QWidget(self, Qt.WindowType.Window)
        float_win.setWindowTitle("Ответ (Помощник)")
        float_win.setObjectName("glassFrame")
        float_win.setStyleSheet(get_stylesheet())
        float_win.setMinimumSize(320, 200)
        float_win.resize(420, 320)
        float_lo = QVBoxLayout(float_win)
        float_lo.setContentsMargins(12, 12, 12, 12)

        # Прозрачность окна
        opacity_row = QHBoxLayout()
        opacity_label = QLabel("Прозрачность")
        opacity_label.setObjectName("glassLabel")
        opacity_label.setStyleSheet("color: rgba(200,200,210,0.9); font-size: 12px;")
        opacity_row.addWidget(opacity_label)
        float_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        float_opacity_slider.setRange(100, 255)
        s = _open_settings()
        float_opacity_slider.setValue(max(100, min(255, s.value("assistant_float_opacity", DEFAULT_GLASS_OPACITY, type=int))))
        float_opacity_slider.setMinimumWidth(100)
        float_opacity_slider.setMaximumWidth(100)
        float_win.setWindowOpacity(float_opacity_slider.value() / 255.0)

        def _on_float_opacity(v):
            float_win.setWindowOpacity(v / 255.0)
            _open_settings().setValue("assistant_float_opacity", v)

        float_opacity_slider.valueChanged.connect(_on_float_opacity)
        opacity_row.addWidget(float_opacity_slider)
        opacity_row.addStretch()
        float_lo.addLayout(opacity_row)

        float_lo.addWidget(self.assistant_answer_edit)

        # Все кнопки под областью ответа: одна строка иконок (Старт, Стоп, Мьют, Очистить, Отправить, Вернуть)
        _icon_size_float = QSize(20, 20)
        _float_btn_style = (
            "QPushButton { background-color: #FF9900; color: #000000; border: 2px solid #CC7A00; "
            "border-radius: 10px; padding: 6px; outline: none; }"
            "QPushButton:hover { background-color: #FFB833; border-color: #CC7A00; outline: none; }"
            "QPushButton:pressed { background-color: #E68A00; outline: none; }"
            "QPushButton:focus { outline: none; border-color: #CC7A00; }"
            "QPushButton:disabled { background-color: #4A4A4A; color: #AAAAAA; border-color: #555555; }"
        )
        _float_btn_style_return = (
            "QPushButton { background: transparent; color: rgba(200,200,210,0.9); border: 1px solid rgba(255,255,255,0.3); "
            "border-radius: 10px; padding: 6px; outline: none; }"
            "QPushButton:hover { background-color: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.4); }"
            "QPushButton:pressed { background-color: rgba(255,255,255,0.15); }"
        )
        btn_row_main = getattr(self, "_assistant_btn_row", None)
        if btn_row_main is not None:
            for btn in (self.assistant_start_btn, self.assistant_stop_btn, self.assistant_mute_btn, self.assistant_clear_btn):
                btn_row_main.removeWidget(btn)
            self._assistant_start_btn_orig_text = self.assistant_start_btn.text()
            self._assistant_stop_btn_orig_text = self.assistant_stop_btn.text()
            self.assistant_start_btn.setText("")
            self.assistant_start_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PLAY)))
            self.assistant_start_btn.setIconSize(_icon_size_float)
            self.assistant_start_btn.setFixedSize(44, 44)
            self.assistant_start_btn.setMinimumWidth(0)
            self.assistant_start_btn.setMinimumHeight(0)
            self.assistant_stop_btn.setText("")
            self.assistant_stop_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_STOP)))
            self.assistant_stop_btn.setIconSize(_icon_size_float)
            self.assistant_stop_btn.setFixedSize(44, 44)
            self.assistant_stop_btn.setMinimumWidth(0)
            self.assistant_stop_btn.setMinimumHeight(0)
            self.assistant_mute_btn.setIconSize(_icon_size_float)
            self.assistant_clear_btn.setIconSize(_icon_size_float)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        if btn_row_main is not None:
            bottom_row.addWidget(self.assistant_start_btn)
            bottom_row.addWidget(self.assistant_stop_btn)
            bottom_row.addWidget(self.assistant_mute_btn)
            bottom_row.addWidget(self.assistant_clear_btn)
        btn_send_float = QPushButton()
        btn_send_float.setFixedSize(44, 44)
        btn_send_float.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_SEND)))
        btn_send_float.setIconSize(_icon_size_float)
        btn_send_float.setObjectName("glassAssistantButton")
        btn_send_float.setStyleSheet(_float_btn_style)
        btn_send_float.setToolTip(self._tooltip_with_hotkey("Отправить (Помощник)", "assistant_send"))
        btn_send_float.clicked.connect(self._on_assistant_send_clicked)
        bottom_row.addWidget(btn_send_float)
        btn_return = QPushButton()
        btn_return.setFixedSize(44, 44)
        btn_return.setIcon(app_icons.icon_with_color(app_icons.TITLE_PIN_OFF, "#E8E8EC"))
        btn_return.setIconSize(_icon_size_float)
        btn_return.setStyleSheet(_float_btn_style_return)
        btn_return.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_return.setToolTip("Вернуть в окно приложения")
        btn_return.clicked.connect(lambda: self._on_assistant_answer_return(close_window=True))
        bottom_row.addWidget(btn_return)
        bottom_row.addStretch()
        float_lo.addLayout(bottom_row)
        if btn_row_main is not None:
            self._assistant_float_btn_row = bottom_row
        self._assistant_answer_float_window = float_win

        def _on_float_close(event):
            self._on_assistant_answer_return(close_window=False)
            event.accept()

        float_win.closeEvent = _on_float_close
        if getattr(self, "assistant_answer_float_btn", None) is not None:
            self.assistant_answer_float_btn.setText("Ответ вынесен")
            self.assistant_answer_float_btn.setEnabled(False)
        float_win.show()

    def _on_assistant_answer_return(self, close_window: bool = True):
        """Вернуть область «Ответ» и кнопки Помощника на вкладку."""
        float_win = getattr(self, "_assistant_answer_float_window", None)
        if float_win is None or not getattr(self, "assistant_answer_edit", None):
            return
        page = getattr(self, "_assistant_page", None)
        if page is None:
            if close_window:
                float_win.close()
            self._assistant_answer_float_window = None
            return
        # Вернуть кнопки Старт/Стоп/Мьют/Очистить на вкладку (восстановить текст и размеры как на вкладке)
        btn_row_main = getattr(self, "_assistant_btn_row", None)
        float_btn_row = getattr(self, "_assistant_float_btn_row", None)
        if btn_row_main is not None and float_btn_row is not None:
            for btn in (self.assistant_start_btn, self.assistant_stop_btn, self.assistant_mute_btn, self.assistant_clear_btn):
                float_btn_row.removeWidget(btn)
            self.assistant_start_btn.setIcon(QIcon())
            self.assistant_start_btn.setText(getattr(self, "_assistant_start_btn_orig_text", "▶  Старт распознавания"))
            self.assistant_start_btn.setMinimumWidth(200)
            self.assistant_start_btn.setMinimumHeight(44)
            self.assistant_start_btn.setMaximumSize(16777215, 16777215)
            self.assistant_stop_btn.setIcon(QIcon())
            self.assistant_stop_btn.setText(getattr(self, "_assistant_stop_btn_orig_text", "■  Стоп"))
            self.assistant_stop_btn.setMinimumWidth(110)
            self.assistant_stop_btn.setMinimumHeight(44)
            self.assistant_stop_btn.setMaximumSize(16777215, 16777215)
            btn_row_main.insertWidget(1, self.assistant_start_btn)
            btn_row_main.insertWidget(2, self.assistant_stop_btn)
            btn_row_main.insertWidget(3, self.assistant_mute_btn)
            btn_row_main.insertWidget(4, self.assistant_clear_btn)
        idx = getattr(self, "_assistant_answer_float_index", 0)
        lo_page = page.layout()
        self.assistant_answer_edit.setParent(page)
        lo_page.insertWidget(idx, self.assistant_answer_edit)
        self._assistant_answer_float_window = None
        if getattr(self, "assistant_answer_float_btn", None) is not None:
            self.assistant_answer_float_btn.setText("Вынести ответ")
            self.assistant_answer_float_btn.setEnabled(True)
        if close_window:
            float_win.close()

    def _apply_assistant_button_style(self, btn: QPushButton, is_stop: bool = False):
        """Явные цвета для кнопок Помощника: светлый фон, тёмный текст (обход конфликта со стилями)."""
        if is_stop:
            btn.setStyleSheet(
                "QPushButton { background-color: #FF9900; color: #000000; border: 2px solid #CC7A00; "
                "border-radius: 10px; font-weight: 800; font-size: 14px; padding: 10px 16px; }"
                "QPushButton:hover { background-color: #FFB833; }"
                "QPushButton:pressed { background-color: #E68A00; }"
                "QPushButton:disabled { background-color: #4A4A4A; color: #AAAAAA; border-color: #555555; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background-color: #FF9900; color: #000000; border: 2px solid #CC7A00; "
                "border-radius: 10px; font-weight: 800; font-size: 14px; padding: 10px 16px; }"
                "QPushButton:hover { background-color: #FFB833; }"
                "QPushButton:pressed { background-color: #E68A00; }"
                "QPushButton:disabled { background-color: #4A4A4A; color: #AAAAAA; border-color: #555555; }"
            )

    # Стили кнопок левой колонки: Главная — зелёные, Помощник — оранжевые
    _SIDEBAR_MAIN_CSS = (
        "QPushButton { background-color: #2E7D32; color: #fff; border: 2px solid #1B5E20; border-radius: 10px; padding: 6px; }"
        "QPushButton:hover { background-color: #388E3C; border-color: #1B5E20; }"
        "QPushButton:pressed { background-color: #1B5E20; }"
        "QPushButton:disabled { background-color: #4A4A4A; color: #888; border-color: #555; }"
    )
    _SIDEBAR_ASSISTANT_CSS = (
        "QPushButton { background-color: #FF9900; color: #000; border: 2px solid #CC7A00; border-radius: 10px; padding: 8px; }"
        "QPushButton:hover { background-color: #FFB833; border-color: #CC7A00; }"
        "QPushButton:pressed { background-color: #E68A00; }"
        "QPushButton:disabled { background-color: #4A4A4A; color: #888; border-color: #555; }"
    )

    def _build_left_sidebar(self) -> QWidget:
        """Левая колонка: сверху кнопки Главной (зелёные), ниже — Помощника (оранжевые). Компактные, без надписей."""
        panel = QFrame()
        panel.setObjectName("glassSidebar")
        panel.setFixedWidth(52)
        panel.setStyleSheet(
            "#glassSidebar { background: transparent; border: none; }"
        )
        lo = QVBoxLayout(panel)
        lo.setContentsMargins(4, 8, 4, 8)
        lo.setSpacing(6)

        _icon_size_sidebar = QSize(20, 20)
        SIZE = 44

        # —— Главная (5 кнопок) ——
        btn_send = QPushButton()
        btn_send.setFixedSize(SIZE, SIZE)
        btn_send.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_SEND)))
        btn_send.setIconSize(_icon_size_sidebar)
        btn_send.setToolTip("Отправить ИИ")
        btn_send.setStyleSheet(self._SIDEBAR_MAIN_CSS)
        btn_send.clicked.connect(self._on_sidebar_send_main)
        lo.addWidget(btn_send)

        btn_type = QPushButton()
        btn_type.setFixedSize(SIZE, SIZE)
        btn_type.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PLAY)))
        btn_type.setIconSize(_icon_size_sidebar)
        btn_type.setToolTip("Печать ответа")
        btn_type.setStyleSheet(self._SIDEBAR_MAIN_CSS)
        btn_type.clicked.connect(self._on_start_or_stop_typer)
        if not _typer_available:
            btn_type.setEnabled(False)
        self._sidebar_typer_btn = btn_type
        lo.addWidget(btn_type)

        btn_pause = QPushButton()
        btn_pause.setFixedSize(SIZE, SIZE)
        btn_pause.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PAUSE)))
        btn_pause.setIconSize(_icon_size_sidebar)
        btn_pause.setToolTip("Пауза печати")
        btn_pause.setStyleSheet(self._SIDEBAR_MAIN_CSS)
        btn_pause.clicked.connect(self._on_pause_shortcut)
        self._sidebar_pause_btn = btn_pause
        lo.addWidget(btn_pause)

        btn_screenshot = QPushButton()
        btn_screenshot.setFixedSize(SIZE, SIZE)
        btn_screenshot.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_SCREENSHOT)))
        btn_screenshot.setIconSize(_icon_size_sidebar)
        btn_screenshot.setToolTip("Скриншот")
        btn_screenshot.setStyleSheet(self._SIDEBAR_MAIN_CSS)
        btn_screenshot.clicked.connect(self._on_screenshot)
        self._sidebar_screenshot_btn = btn_screenshot
        lo.addWidget(btn_screenshot)

        btn_get_answer = QPushButton()
        btn_get_answer.setFixedSize(SIZE, SIZE)
        btn_get_answer.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_GET_ANSWER)))
        btn_get_answer.setIconSize(_icon_size_sidebar)
        btn_get_answer.setToolTip("Получить ответ")
        btn_get_answer.setStyleSheet(self._SIDEBAR_MAIN_CSS)
        btn_get_answer.clicked.connect(self._on_get_answer_shortcut)
        self._sidebar_get_answer_btn = btn_get_answer
        lo.addWidget(btn_get_answer)

        lo.addSpacing(10)

        # —— Помощник (5 кнопок) ——
        btn_start = QPushButton()
        btn_start.setFixedSize(SIZE, SIZE)
        btn_start.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PLAY)))
        btn_start.setIconSize(_icon_size_sidebar)
        btn_start.setToolTip("Старт распознавания")
        btn_start.setStyleSheet(self._SIDEBAR_ASSISTANT_CSS)
        btn_start.clicked.connect(self._on_assistant_start_clicked)
        if not _assistant_speech_available:
            btn_start.setEnabled(False)
        self._sidebar_assistant_start_btn = btn_start
        lo.addWidget(btn_start)

        btn_stop = QPushButton()
        btn_stop.setFixedSize(SIZE, SIZE)
        btn_stop.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_STOP)))
        btn_stop.setIconSize(_icon_size_sidebar)
        btn_stop.setToolTip("Стоп")
        btn_stop.setStyleSheet(self._SIDEBAR_ASSISTANT_CSS)
        btn_stop.clicked.connect(self._on_assistant_stop_clicked)
        btn_stop.setEnabled(False)
        self._sidebar_assistant_stop_btn = btn_stop
        lo.addWidget(btn_stop)

        btn_mute = QPushButton()
        btn_mute.setFixedSize(SIZE, SIZE)
        btn_mute.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_VOLUME)))
        btn_mute.setIconSize(_icon_size_sidebar)
        btn_mute.setToolTip("Мьют")
        btn_mute.setStyleSheet(self._SIDEBAR_ASSISTANT_CSS)
        btn_mute.setCheckable(True)
        btn_mute.clicked.connect(self._on_assistant_mute_clicked)
        btn_mute.setEnabled(False)
        self._sidebar_assistant_mute_btn = btn_mute
        lo.addWidget(btn_mute)

        btn_clear = QPushButton()
        btn_clear.setFixedSize(SIZE, SIZE)
        btn_clear.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_CLEAR)))
        btn_clear.setIconSize(_icon_size_sidebar)
        btn_clear.setToolTip("Очистить")
        btn_clear.setStyleSheet(self._SIDEBAR_ASSISTANT_CSS)
        btn_clear.clicked.connect(self._on_assistant_clear_clicked)
        lo.addWidget(btn_clear)

        btn_send_asst = QPushButton()
        btn_send_asst.setFixedSize(SIZE, SIZE)
        btn_send_asst.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_SEND)))
        btn_send_asst.setIconSize(_icon_size_sidebar)
        btn_send_asst.setToolTip("Отправить (Помощник)")
        btn_send_asst.setStyleSheet(self._SIDEBAR_ASSISTANT_CSS)
        btn_send_asst.clicked.connect(self._on_assistant_send_clicked)
        self._sidebar_assistant_send_btn = btn_send_asst
        lo.addWidget(btn_send_asst)

        lo.addStretch()
        return panel

    def _on_sidebar_send_main(self):
        """Сайдбар: переключить на Главную и отправить запрос ИИ."""
        self._restore_from_tray()
        self.main_tabs.setCurrentIndex(0)
        self._on_send_clicked()

    def _sync_sidebar_assistant(self):
        """Синхронизировать состояние кнопок помощника в сайдбаре с кнопками на вкладке."""
        for src, dst in [
            ("assistant_start_btn", "_sidebar_assistant_start_btn"),
            ("assistant_stop_btn", "_sidebar_assistant_stop_btn"),
            ("assistant_mute_btn", "_sidebar_assistant_mute_btn"),
            ("assistant_send_btn", "_sidebar_assistant_send_btn"),
        ]:
            s = getattr(self, src, None)
            d = getattr(self, dst, None)
            if s is not None and d is not None:
                d.setEnabled(s.isEnabled())
        if getattr(self, "assistant_mute_btn", None) is not None and getattr(self, "_sidebar_assistant_mute_btn", None) is not None:
            self._sidebar_assistant_mute_btn.blockSignals(True)
            self._sidebar_assistant_mute_btn.setChecked(self.assistant_mute_btn.isChecked())
            icon_name = app_icons.SIDEBAR_VOLUME_MUTE if self.assistant_mute_btn.isChecked() else app_icons.SIDEBAR_VOLUME
            self._sidebar_assistant_mute_btn.setIcon(QIcon(app_icons.icon_path(icon_name)))
            self._sidebar_assistant_mute_btn.blockSignals(False)

    def _sync_sidebar_typer(self):
        """Синхронизировать иконку печати в сайдбаре с кнопкой на главной."""
        sb = getattr(self, "_sidebar_typer_btn", None)
        if sb is None:
            return
        sb.setEnabled(getattr(self, "type_response_btn", None) and self.type_response_btn.isEnabled())
        # Иконка Play/Stop по состоянию тайпера
        if getattr(self, "_typer_thread", None) and self._typer_thread.isRunning():
            sb.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_STOP)))
        else:
            sb.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PLAY)))

    def _on_assistant_mic_combo_changed(self):
        """Не разрешать одно и то же устройство в микрофоне и в голосе собеседника: при совпадении сбрасываем собеседника."""
        mic_id = self.assistant_mic_combo.currentData()
        if mic_id is None:
            mic_id = -1
        mic_id = int(mic_id)
        if mic_id < 0:
            return
        inter_id = self.assistant_interlocutor_combo.currentData()
        if inter_id is not None and int(inter_id) == mic_id:
            self.assistant_interlocutor_combo.setCurrentIndex(0)
        self._save_settings()

    def _on_assistant_interlocutor_combo_changed(self):
        """Не разрешать одно и то же устройство в микрофоне и в голосе собеседника: при совпадении сбрасываем микрофон."""
        inter_id = self.assistant_interlocutor_combo.currentData()
        if inter_id is None:
            inter_id = -1
        inter_id = int(inter_id)
        if inter_id < 0:
            return
        mic_id = self.assistant_mic_combo.currentData()
        if mic_id is not None and int(mic_id) == inter_id:
            self.assistant_mic_combo.setCurrentIndex(0)
        self._save_settings()

    def _on_assistant_start_clicked(self):
        """Запуск распознавания: один или два потока (микрофон и/или голос собеседника с ПК)."""
        if not _assistant_speech_available or not _assistant_speech_module:
            return
        mic_id = self.assistant_mic_combo.currentData()
        if mic_id is None:
            mic_id = -1
        mic_id = int(mic_id)
        interlocutor_id = self.assistant_interlocutor_combo.currentData()
        if interlocutor_id is None:
            interlocutor_id = -1
        interlocutor_id = int(interlocutor_id)
        if mic_id < 0 and interlocutor_id < 0:
            self.assistant_transcript_edit.setPlainText("Выберите хотя бы один источник: микрофон или голос собеседника.")
            return
        models_ok, _ = _assistant_speech_module.check_models(audio_devices.ASSISTANT_MODELS_DIR)
        if not models_ok:
            self.assistant_transcript_edit.setPlainText("Не найдены файлы модели в папке models/ (encoder, decoder, joiner, tokens.txt).")
            return

        self.assistant_transcript_edit.clear()
        self._assistant_committed_text = ""
        self._assistant_partial_user = ""
        self._assistant_partial_interlocutor = ""
        self.assistant_start_btn.setEnabled(False)
        self.assistant_stop_btn.setEnabled(True)
        self._assistant_stop_event = threading.Event()
        self._assistant_mute_user_event = threading.Event()  # set = мой микрофон выключен
        self.assistant_mute_btn.setChecked(False)
        self._assistant_mute_user_event.clear()
        self.assistant_mute_btn.setEnabled(mic_id >= 0)
        self.assistant_mute_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_VOLUME)))

        def on_text(text: str, is_final: bool, role: str):
            self.assistant_text_signal.emit(text, is_final, role)

        # Один recognizer на оба потока — иначе "cannot load module more than once per process" (onnxruntime)
        shared_recognizer = None
        try:
            shared_recognizer = _assistant_speech_module.create_recognizer(audio_devices.ASSISTANT_MODELS_DIR)
        except Exception as e:
            self.assistant_text_signal.emit(f"Ошибка загрузки модели: {e}", True, "user")
            return

        def run_user():
            _assistant_speech_module.run_recognition_loop(
                audio_devices.ASSISTANT_MODELS_DIR,
                mic_id,
                on_text=on_text,
                stop_event=self._assistant_stop_event,
                role="user",
                mute_event=self._assistant_mute_user_event,
                shared_recognizer=shared_recognizer,
            )

        def run_interlocutor():
            # Стерео микшер на Windows обычно 44.1 kHz, стерео — иначе звук с ПК может не захватываться
            _assistant_speech_module.run_recognition_loop(
                audio_devices.ASSISTANT_MODELS_DIR,
                interlocutor_id,
                on_text=on_text,
                stop_event=self._assistant_stop_event,
                role="interlocutor",
                input_sample_rate=44100,
                channels=2,
                shared_recognizer=shared_recognizer,
            )

        def run_orchestrator():
            threads = []
            if mic_id >= 0:
                t1 = threading.Thread(target=run_user, daemon=True)
                t1.start()
                threads.append(t1)
            if interlocutor_id >= 0:
                t2 = threading.Thread(target=run_interlocutor, daemon=True)
                t2.start()
                threads.append(t2)
            for t in threads:
                t.join()
            self.assistant_finished_signal.emit()

        self._assistant_thread = threading.Thread(target=run_orchestrator, daemon=True)
        self._assistant_thread.start()
        self._sync_sidebar_assistant()

    def _on_assistant_mute_clicked(self):
        """Вкл/выкл мой микрофон во время распознавания (только ваш голос, не собеседника)."""
        if not getattr(self, "_assistant_mute_user_event", None):
            return
        checked = self.assistant_mute_btn.isChecked()
        if checked:
            self._assistant_mute_user_event.set()
            self.assistant_mute_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_VOLUME_MUTE)))
        else:
            self._assistant_mute_user_event.clear()
            self.assistant_mute_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_VOLUME)))
        self._sync_sidebar_assistant()

    def _on_assistant_clear_clicked(self):
        """Очистить поле с распознанным текстом; распознавание продолжается, новые результаты выводятся как обычно."""
        if not getattr(self, "assistant_transcript_edit", None):
            return
        self.assistant_transcript_edit.clear()
        self._assistant_committed_text = ""
        self._assistant_partial_user = ""
        self._assistant_partial_interlocutor = ""

    def _on_assistant_send_clicked(self):
        """Промпт (с должностью) + текущий транскрипт → активное API; ответ в «Ответ», транскрипт очищается."""
        if not getattr(self, "assistant_transcript_edit", None) or not getattr(self, "assistant_answer_edit", None):
            return
        transcript = self.assistant_transcript_edit.toPlainText().strip()
        if not transcript:
            self.assistant_answer_edit.setPlainText("Нет распознанного текста. Запустите распознавание и наговорите диалог.")
            return
        job = (self.assistant_job_edit.text().strip() if getattr(self, "assistant_job_edit", None) else "")
        job_prefix = ("Я сейчас нахожусь на собеседовании на должность «" + job + "», помоги с ответами.\n\n") if job else ""
        prompt_text = (self.assistant_prompt_edit.toPlainText().strip() if getattr(self, "assistant_prompt_edit", None) else "") or ASSISTANT_SEND_PROMPT
        message = job_prefix + prompt_text + "\n\n---\n\nДиалог:\n" + transcript
        self._send_request_with_text(message, response_target="assistant")

    def _on_assistant_stop_clicked(self):
        """Остановка распознавания речи."""
        if self._assistant_stop_event:
            self._assistant_stop_event.set()

    def _on_assistant_thread_finished(self):
        """Вызывается в main thread по завершении потока распознавания."""
        if getattr(self, "_assistant_thread", None):
            self._assistant_thread = None
        if getattr(self, "assistant_start_btn", None):
            self.assistant_start_btn.setEnabled(True)
        if getattr(self, "assistant_stop_btn", None):
            self.assistant_stop_btn.setEnabled(False)
        if getattr(self, "assistant_mute_btn", None):
            self.assistant_mute_btn.setEnabled(False)
            self.assistant_mute_btn.setChecked(False)
            self.assistant_mute_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_VOLUME)))
        if getattr(self, "_assistant_mute_user_event", None):
            self._assistant_mute_user_event.clear()
        self._sync_sidebar_assistant()

    def _append_assistant_text(self, text: str, is_final: bool, role: str):
        """Добавляет распознанный текст в диалог: «Вы» (микрофон) и «Собеседник» (захват с ПК)."""
        if not getattr(self, "assistant_transcript_edit", None):
            return
        committed = getattr(self, "_assistant_committed_text", "")
        partial_user = getattr(self, "_assistant_partial_user", "")
        partial_interlocutor = getattr(self, "_assistant_partial_interlocutor", "")
        edit = self.assistant_transcript_edit
        label_user = "Вы: "
        label_interlocutor = "Собеседник: "

        # Сохранить позицию скролла: после обновления текста восстановить её, чтобы можно было листать независимо от диктовки
        vbar = edit.verticalScrollBar()
        old_value = vbar.value()
        old_max = vbar.maximum()

        # Финальный результат уже содержит полную фразу — не добавляем partial, иначе дублируется (приветпривет)
        if role == "user":
            if is_final:
                self._assistant_committed_text = committed + label_user + (text or "").strip() + "\n"
                self._assistant_partial_user = ""
            else:
                self._assistant_partial_user = text or ""
        else:
            if is_final:
                self._assistant_committed_text = committed + label_interlocutor + (text or "").strip() + "\n"
                self._assistant_partial_interlocutor = ""
            else:
                self._assistant_partial_interlocutor = text or ""

        committed = getattr(self, "_assistant_committed_text", "")
        pu = getattr(self, "_assistant_partial_user", "")
        pi = getattr(self, "_assistant_partial_interlocutor", "")
        display = committed
        if pu:
            display += label_user + pu + "\n"
        if pi:
            display += label_interlocutor + pi
        edit.setPlainText(display)

        # Всегда восстанавливать скролл по сохранённой позиции — окно не дёргается, можно листать во время диктовки
        vbar = edit.verticalScrollBar()
        new_max = vbar.maximum()
        if old_max > 0 and new_max > 0:
            vbar.setValue(int(round(new_max * old_value / old_max)))

    def _on_assistant_prompt_reset(self):
        """Вернуть промпт помощника к встроенному в приложение (стандартному)."""
        if getattr(self, "assistant_prompt_edit", None) is None:
            return
        self.assistant_prompt_edit.blockSignals(True)
        self.assistant_prompt_edit.setPlainText(ASSISTANT_SEND_PROMPT)
        self.assistant_prompt_edit.blockSignals(False)
        self._save_settings()

    def _on_screenshot_prompt_reset(self):
        """Вернуть промпт для скриншота к встроенному в приложение (стандартному)."""
        if getattr(self, "screenshot_prompt_edit", None) is None:
            return
        self.screenshot_prompt_edit.blockSignals(True)
        self.screenshot_prompt_edit.setPlainText(SCREENSHOT_TASK_PROMPT)
        self.screenshot_prompt_edit.blockSignals(False)
        self._save_settings()

    def _on_prompt_active_toggled(self, index: int, checked: bool):
        """Только один промпт может быть активным."""
        if checked:
            self.prompt_active_index = index
            for j, cb in enumerate(self.prompt_active_checkboxes):
                if j != index:
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
        else:
            if self.prompt_active_index == index:
                self.prompt_active_index = -1
        self._save_settings()

    def _get_active_prompt_text(self) -> str:
        """Текст активного промпта или пустая строка."""
        if 0 <= self.prompt_active_index < len(self.prompt_edits):
            return self.prompt_edits[self.prompt_active_index].toPlainText().strip()
        return ""

    def _get_selected_text_from_focus(self) -> str:
        """Выделенный текст в виджете, имеющем фокус (QPlainTextEdit, QLineEdit и т.д.)."""
        w = QApplication.focusWidget()
        if w is None:
            return ""
        if hasattr(w, "textCursor") and w.textCursor().hasSelection():
            return w.textCursor().selection().toPlainText()
        if hasattr(w, "selectedText"):
            return w.selectedText()
        return ""

    def _send_request_with_text(self, text: str, response_target: str = "main"):
        """Отправить запрос к API. response_target: «main» — ответ в response_edit (Главная), «assistant» — в assistant_answer_edit и очистка транскрипта."""
        if not text.strip():
            return
        if response_target == "assistant":
            slot = getattr(self, "_api_for_assistant_index", 0)
        elif response_target == "screenshots":
            slot = getattr(self, "_api_for_screenshots_index", 0)
        else:
            slot = getattr(self, "_api_for_main_index", 0)
        base_url, api_key, model, auth_type = self._get_api_params_for(slot)
        if not base_url or not model:
            if response_target == "assistant" and getattr(self, "assistant_answer_edit", None):
                self.assistant_answer_edit.setPlainText("Укажите URL API и модель на вкладке API.")
            else:
                self._response_raw_text = None
                self._cached_tips_text = None
                self.response_edit.setPlainText("Укажите URL API и модель на вкладке API.")
            return
        self._api_response_target = response_target
        if response_target == "assistant":
            if getattr(self, "assistant_answer_edit", None):
                self.assistant_answer_edit.setPlainText("Отправка запроса...")
            if getattr(self, "assistant_send_btn", None):
                self.assistant_send_btn.setEnabled(False)
                self._sync_sidebar_assistant()
        else:
            self.response_edit.setPlainText("Отправка запроса...")
            self.send_btn.setEnabled(False)
        worker = ApiRequestWorker(base_url, api_key, model, auth_type, text.strip())
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_api_response, Qt.ConnectionType.QueuedConnection)
        self._api_thread = thread
        self._api_worker = worker
        thread.start()

    def _on_api_provider_changed(self, index: int):
        """При выборе провайдера из списка — подставить URL, модель, авторизацию в текущий слот."""
        if index <= 0:
            return
        preset_id = self.api_provider_combo.currentData()
        if not preset_id:
            return
        data = apply_preset_to_slot(preset_id)
        if not data:
            return
        self._api_slot_name[self._api_active_index] = data.get("name", self._api_slot_name[self._api_active_index])
        self._api_slot_url[self._api_active_index] = data.get("base_url", "")
        self._api_slot_model[self._api_active_index] = data.get("model", "")
        self._api_slot_auth[self._api_active_index] = data.get("auth", AUTH_VALUES[0])
        self.api_name_edit.blockSignals(True)
        self.api_url_edit.blockSignals(True)
        self.api_model_edit.blockSignals(True)
        self.api_auth_combo.blockSignals(True)
        self.api_name_edit.setText(self._api_slot_name[self._api_active_index])
        self.api_url_edit.setText(self._api_slot_url[self._api_active_index])
        self.api_model_edit.setText(self._api_slot_model[self._api_active_index])
        self.api_auth_combo.setCurrentIndex(auth_index_from_value(self._api_slot_auth[self._api_active_index]))
        self.api_name_edit.blockSignals(False)
        self.api_url_edit.blockSignals(False)
        self.api_model_edit.blockSignals(False)
        self.api_auth_combo.blockSignals(False)
        self._update_api_button_labels()
        self._save_settings()

    def _on_api_name_changed(self, text: str):
        self._api_slot_name[self._api_active_index] = text.strip() or f"API {self._api_active_index + 1}"
        self._update_api_button_labels()
        self._save_settings()

    def _on_api_auth_changed(self, index: int):
        self._api_slot_auth[self._api_active_index] = auth_value_from_index(index)
        self._save_settings()

    def _apply_combo_popup_style(self):
        """Применяет тёмный стиль к выпадающим спискам комбобоксов (в т.ч. на Windows)."""
        popup_frame_style = """
            QFrame { border: none; background-color: rgba(24, 24, 28, 0.98); }
        """
        for combo in self.findChildren(QComboBox):
            if combo.objectName() == "glassCombo":
                v = combo.view()
                v.setStyleSheet(COMBO_POPUP_STYLE)
                parent = v.parent()
                if parent is not None:
                    parent.setStyleSheet(popup_frame_style)

    def _get_api_params_for(self, slot_index: int):
        """Возвращает (base_url, api_key, model, auth_type) для слота 0..2."""
        i = max(0, min(2, slot_index))
        return (
            (self._api_slot_url[i] or "").strip(),
            (self._api_slot_key[i] or "").strip(),
            (self._api_slot_model[i] or "").strip(),
            self._api_slot_auth[i] if i < len(self._api_slot_auth) else AUTH_VALUES[0],
        )

    def _update_api_button_labels(self):
        for i, btn in enumerate([self.api_btn_1, self.api_btn_2, self.api_btn_3]):
            name = (self._api_slot_name[i] or f"API {i+1}").strip()
            btn.setText(name[:12] + "…" if len(name) > 12 else name)
        for i in range(3):
            name = (self._api_slot_name[i] or f"API {i+1}").strip()
            if getattr(self, "api_for_main_combo", None) is not None and i < self.api_for_main_combo.count():
                self.api_for_main_combo.setItemText(i, name)
            if getattr(self, "api_for_assistant_combo", None) is not None and i < self.api_for_assistant_combo.count():
                self.api_for_assistant_combo.setItemText(i, name)
            if getattr(self, "api_for_screenshots_combo", None) is not None and i < self.api_for_screenshots_combo.count():
                self.api_for_screenshots_combo.setItemText(i, name)

    def _on_api_slot_clicked(self, index: int):
        if index == self._api_active_index:
            return
        self._api_slot_name[self._api_active_index] = self.api_name_edit.text().strip() or f"API {self._api_active_index + 1}"
        self._api_slot_key[self._api_active_index] = self.api_key_edit.text()
        self._api_slot_url[self._api_active_index] = self.api_url_edit.text()
        self._api_slot_model[self._api_active_index] = self.api_model_edit.text()
        self._api_slot_auth[self._api_active_index] = auth_value_from_index(self.api_auth_combo.currentIndex())
        self._api_active_index = index
        self.api_name_edit.blockSignals(True)
        self.api_key_edit.blockSignals(True)
        self.api_url_edit.blockSignals(True)
        self.api_model_edit.blockSignals(True)
        self.api_auth_combo.blockSignals(True)
        self.api_name_edit.setText(self._api_slot_name[index])
        self.api_key_edit.setText(self._api_slot_key[index])
        self.api_url_edit.setText(self._api_slot_url[index])
        self.api_model_edit.setText(self._api_slot_model[index])
        self.api_auth_combo.setCurrentIndex(auth_index_from_value(self._api_slot_auth[index]))
        self.api_name_edit.blockSignals(False)
        self.api_key_edit.blockSignals(False)
        self.api_url_edit.blockSignals(False)
        self.api_model_edit.blockSignals(False)
        self.api_auth_combo.blockSignals(False)
        self.api_btn_1.setChecked(index == 0)
        self.api_btn_2.setChecked(index == 1)
        self.api_btn_3.setChecked(index == 2)
        self._update_api_button_labels()
        self._save_settings()

    def _update_all_shortcuts(self):
        """Создаёт или обновляет все горячие клавиши (клавиатура)."""
        spec = [
            (self.key_hide, self._minimize_to_tray),
            (self.key_show, self._restore_from_tray),
            (self.key_screenshot, self._on_screenshot),
            (self.key_get_answer, self._on_get_answer_shortcut),
            (self.key_start_typer, self._on_start_or_stop_typer),
            (self.key_move_window, self._on_pin_toggle),
            (self.key_pause, self._on_pause_shortcut),
            (self.key_assistant_start, self._on_assistant_start_shortcut),
            (self.key_assistant_send, self._on_assistant_send_shortcut),
        ]
        while len(self._keyboard_shortcuts) < len(spec):
            sh = QShortcut(self)
            sh.activated.connect(spec[len(self._keyboard_shortcuts)][1])
            self._keyboard_shortcuts.append(sh)
        for i, (key_edit, _) in enumerate(spec):
            shortcut = self._keyboard_shortcuts[i]
            seq = key_edit.keySequence()
            if seq.isEmpty():
                shortcut.setEnabled(False)
            else:
                shortcut.setKey(seq)
                shortcut.setEnabled(True)

    def _on_pin_toggle(self):
        """Приклеить к правому краю / отклеить."""
        if self._pinned:
            # Отлипаем: возврат на сохранённую позицию (всегда в пределах экрана)
            self._pinned = False
            screen = self.screen() or QApplication.primaryScreen()
            if self._normal_pos is not None:
                pos = _clamp_pos_to_screen(self._normal_pos, self.size(), screen)
            else:
                # На случай сбоя: ставим окно в центр экрана
                if screen is not None:
                    r = screen.availableGeometry()
                    pos = QPoint(r.x() + (r.width() - self.width()) // 2, r.y() + (r.height() - self.height()) // 2)
                else:
                    pos = self.pos()
            self.move(pos)
            self.show()
            self.raise_()
            self._normal_pos = None
            if getattr(self, "pin_btn", None):
                self.pin_btn.setChecked(False)
                self.pin_btn.setIcon(app_icons.icon_with_color(app_icons.TITLE_PIN_OFF, "#E8E8EC"))
            return
        screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        # Сохраняем текущую позицию, ограниченную экраном — иначе после многих циклов окно может «уехать»
        self._normal_pos = _clamp_pos_to_screen(self.pos(), self.size(), screen)
        y = max(rect.y(), min(self.y(), rect.bottom() - self.height() + 1))
        self.move(rect.right() - PEEK_WIDTH, y)
        self._pinned = True
        if getattr(self, "pin_btn", None):
            self.pin_btn.setChecked(True)
            self.pin_btn.setIcon(app_icons.icon_with_color(app_icons.TITLE_PIN, "#E8E8EC"))
        self.show()
        self.raise_()

    def _pin_collapse(self):
        """Свернуть приклеенное окно в полоску у правого края."""
        self._do_pin_collapse()

    def _pin_stop_anim(self):
        if getattr(self, "_pin_anim", None) is not None:
            self._pin_anim.stop()
            self._pin_anim = None

    def _do_pin_collapse(self):
        """Плавно закатить приклеенное окно к правому краю."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        self._pin_stop_anim()
        rect = screen.availableGeometry()
        y = max(rect.y(), min(self.y(), rect.bottom() - self.height() + 1))
        w, h = self.width(), self.height()
        start_rect = self.geometry()
        end_rect = QRect(rect.right() - PEEK_WIDTH, y, w, h)
        self._pin_anim = QPropertyAnimation(self, b"geometry")
        self._pin_anim.setDuration(PIN_ANIM_DURATION)
        self._pin_anim.setStartValue(start_rect)
        self._pin_anim.setEndValue(end_rect)
        self._pin_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._pin_anim.finished.connect(lambda: setattr(self, "_pin_anim", None))
        self._pin_anim.start()

    def _pin_allow_collapse_on(self):
        self._pin_allow_collapse = True

    def _pin_expand(self):
        """Плавно выкатить приклеенное окно по наведению."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        self._pin_allow_collapse = False
        self._pin_expand_guard_timer.stop()
        self._pin_expand_guard_timer.start(320)
        self._pin_stop_anim()
        rect = screen.availableGeometry()
        y = max(rect.y(), min(self.y(), rect.bottom() - self.height() + 1))
        w, h = self.width(), self.height()
        start_rect = self.geometry()
        end_rect = QRect(rect.right() - w, y, w, h)
        self._pin_anim = QPropertyAnimation(self, b"geometry")
        self._pin_anim.setDuration(PIN_ANIM_DURATION)
        self._pin_anim.setStartValue(start_rect)
        self._pin_anim.setEndValue(end_rect)
        self._pin_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pin_anim.finished.connect(lambda: setattr(self, "_pin_anim", None))
        self._pin_anim.finished.connect(self.raise_)
        self._pin_anim.start()

    def _apply_always_on_top(self, on_top: bool):
        flags = self.windowFlags()
        if on_top:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _on_always_on_top_toggled(self, checked: bool):
        self._apply_always_on_top(checked)
        self._save_settings()

    def _on_opacity_changed(self, value: int):
        self.setStyleSheet(get_stylesheet(value))
        self._apply_combo_popup_style()
        self._save_settings()

    def _on_tip_opacity_changed(self, value: int):
        if getattr(self, "_tip_overlay", None) is not None:
            self._tip_overlay.set_background_opacity(value)
        self._save_settings()

    def _on_show_tip_toggled(self, checked: bool):
        """Не скрываем окно, а делаем его полностью прозрачным (opacity 0) / снова видимым (opacity 1)."""
        if getattr(self, "_tip_overlay", None) is not None:
            self._tip_overlay.set_tip_visible(checked)

    def _on_lang_ru(self):
        self.lang_ru_btn.setChecked(True)
        self.lang_en_btn.setChecked(False)
        self._save_settings()

    def _on_lang_en(self):
        self.lang_en_btn.setChecked(True)
        self.lang_ru_btn.setChecked(False)
        self._save_settings()

    def _apply_hide_from_capture(self):
        """Скрыть от захвата экрана (трансляция) — основное окно, окно подсказки и всплывающие подсказки."""
        if sys.platform != "win32":
            return
        hwnd = int(self.winId())
        hide = self.check_hide_from_capture.isChecked()
        if hide:
            set_window_exclude_from_capture(hwnd)
        else:
            set_window_include_in_capture(hwnd)
        if getattr(self, "_tip_overlay", None) is not None:
            self._tip_overlay.set_exclude_from_capture(hide)
        # Всплывающие подсказки и прочие окна процесса — скрывать от захвата только при включённой галочке
        if hide:
            apply_tooltip_windows_exclude_from_capture(True)
            if getattr(self, "_tooltip_capture_timer", None) is None:
                self._tooltip_capture_timer = QTimer(self)
                self._tooltip_capture_timer.setSingleShot(False)
                self._tooltip_capture_timer.timeout.connect(
                    lambda: apply_tooltip_windows_exclude_from_capture(True)
                )
            self._tooltip_capture_timer.start(150)
        else:
            if getattr(self, "_tooltip_capture_timer", None) is not None:
                self._tooltip_capture_timer.stop()
            # Не вызывать include для всех окон — иначе служебные (QTrayIconMessageWindow и др.) начинают отображаться на экране

    def _load_settings(self):
        self._loading_settings = True
        try:
            s = _open_settings()
            for key in ("hide", "show", "screenshot", "get_answer", "start_typer", "pin", "pause", "assistant_start", "assistant_send"):
                he = self._get_hotkey_edit_for_action(key)
                settings_key = "hotkey_move" if key == "pin" else f"hotkey_{key}"
                hotkey_str = "" if key == "pause" else (s.value(settings_key, "", type=str) or "")
                if hotkey_str.strip():
                    he.setKeySequence(QKeySequence(hotkey_str))
                else:
                    bi = max(0, min(3, s.value(f"mouse_btn_{key}", 0, type=int)))
                    mi = 0 if key == "pause" else max(0, min(3, s.value(f"mouse_mod_{key}", 0, type=int)))
                    he.setMouse(bi, mi)
            opacity = max(150, min(255, s.value("glass_opacity", DEFAULT_GLASS_OPACITY, type=int)))
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(opacity)
            self.opacity_slider.blockSignals(False)
            self.setStyleSheet(get_stylesheet(opacity))
            self._apply_combo_popup_style()
            self.check_hide_from_capture.setChecked(s.value("hide_from_capture", True, type=bool))
            self._apply_hide_from_capture()
            tip_opacity = max(100, min(255, s.value("tip_overlay_opacity", DEFAULT_TIP_OVERLAY_OPACITY, type=int)))
            if getattr(self, "tip_opacity_slider", None) is not None:
                self.tip_opacity_slider.blockSignals(True)
                self.tip_opacity_slider.setValue(tip_opacity)
                self.tip_opacity_slider.blockSignals(False)
            if getattr(self, "_tip_overlay", None) is not None:
                self._tip_overlay.set_background_opacity(tip_opacity)
            if getattr(self, "check_show_tip", None) is not None:
                self.check_show_tip.setChecked(s.value("show_tip", True, type=bool))
            if getattr(self, "_tip_overlay", None) is not None and getattr(self, "check_show_tip", None) is not None:
                self._tip_overlay.set_tip_visible(self.check_show_tip.isChecked())
            on_top = s.value("always_on_top", True, type=bool)
            self.check_always_on_top.setChecked(on_top)
            self._apply_always_on_top(on_top)
            lang_idx = s.value("lang_index", 0, type=int)
            self.lang_ru_btn.setChecked(lang_idx == 0)
            self.lang_en_btn.setChecked(lang_idx == 1)
            for i in range(3):
                self._api_slot_name[i] = s.value(f"api_name_{i+1}", f"API {i+1}", type=str) or f"API {i+1}"
                self._api_slot_key[i] = s.value(f"api_key_{i+1}", "", type=str)
                self._api_slot_url[i] = s.value(f"api_url_{i+1}", "", type=str)
                self._api_slot_model[i] = s.value(f"api_model_{i+1}", "", type=str)
                self._api_slot_auth[i] = s.value(f"api_auth_{i+1}", AUTH_VALUES[0], type=str) or AUTH_VALUES[0]
                if self._api_slot_auth[i] not in AUTH_VALUES:
                    self._api_slot_auth[i] = AUTH_VALUES[0]
            if not self._api_slot_key[0] and s.value("api_key", ""):
                self._api_slot_key[0] = s.value("api_key", "", type=str)
                self._api_slot_url[0] = s.value("api_url", "", type=str)
                self._api_slot_model[0] = s.value("api_model", "", type=str)
            self._api_active_index = max(0, min(2, s.value("api_active", 0, type=int)))
            self.api_name_edit.blockSignals(True)
            self.api_key_edit.blockSignals(True)
            self.api_url_edit.blockSignals(True)
            self.api_model_edit.blockSignals(True)
            self.api_auth_combo.blockSignals(True)
            self.api_name_edit.setText(self._api_slot_name[self._api_active_index])
            self.api_key_edit.setText(self._api_slot_key[self._api_active_index])
            self.api_url_edit.setText(self._api_slot_url[self._api_active_index])
            self.api_model_edit.setText(self._api_slot_model[self._api_active_index])
            self.api_auth_combo.setCurrentIndex(auth_index_from_value(self._api_slot_auth[self._api_active_index]))
            self.api_name_edit.blockSignals(False)
            self.api_key_edit.blockSignals(False)
            self.api_url_edit.blockSignals(False)
            self.api_model_edit.blockSignals(False)
            self.api_auth_combo.blockSignals(False)
            self.api_btn_1.setChecked(self._api_active_index == 0)
            self.api_btn_2.setChecked(self._api_active_index == 1)
            self.api_btn_3.setChecked(self._api_active_index == 2)
            self._update_api_button_labels()
            api_active = self._api_active_index
            self._api_for_main_index = max(0, min(2, s.value("api_for_main", api_active, type=int)))
            self._api_for_assistant_index = max(0, min(2, s.value("api_for_assistant", api_active, type=int)))
            self._api_for_screenshots_index = max(0, min(2, s.value("api_for_screenshots", api_active, type=int)))
            if getattr(self, "api_for_main_combo", None) is not None:
                self.api_for_main_combo.blockSignals(True)
                self.api_for_main_combo.setCurrentIndex(self._api_for_main_index)
                self.api_for_main_combo.blockSignals(False)
            if getattr(self, "api_for_assistant_combo", None) is not None:
                self.api_for_assistant_combo.blockSignals(True)
                self.api_for_assistant_combo.setCurrentIndex(self._api_for_assistant_index)
                self.api_for_assistant_combo.blockSignals(False)
            if getattr(self, "api_for_screenshots_combo", None) is not None:
                self.api_for_screenshots_combo.blockSignals(True)
                self.api_for_screenshots_combo.setCurrentIndex(self._api_for_screenshots_index)
                self.api_for_screenshots_combo.blockSignals(False)
            for i, edit in enumerate(getattr(self, "prompt_edits", [])):
                if i < 6:
                    edit.blockSignals(True)
                    edit.setPlainText(s.value(f"prompt_{i+1}", "", type=str) or "")
                    edit.blockSignals(False)
            if getattr(self, "assistant_prompt_edit", None) is not None:
                self.assistant_prompt_edit.blockSignals(True)
                self.assistant_prompt_edit.setPlainText(s.value("assistant_prompt_text", ASSISTANT_SEND_PROMPT, type=str) or ASSISTANT_SEND_PROMPT)
                self.assistant_prompt_edit.blockSignals(False)
            if getattr(self, "screenshot_prompt_edit", None) is not None:
                self.screenshot_prompt_edit.blockSignals(True)
                self.screenshot_prompt_edit.setPlainText(s.value("screenshot_prompt_text", SCREENSHOT_TASK_PROMPT, type=str) or SCREENSHOT_TASK_PROMPT)
                self.screenshot_prompt_edit.blockSignals(False)
            idx = s.value("prompt_active_index", -1, type=int)
            if 0 <= idx < len(getattr(self, "prompt_active_checkboxes", [])):
                self.prompt_active_index = idx
                for j, cb in enumerate(self.prompt_active_checkboxes):
                    cb.blockSignals(True)
                    cb.setChecked(j == idx)
                    cb.blockSignals(False)
            else:
                self.prompt_active_index = -1
            # Помощник: микрофон и голос собеседника (не разрешаем одно устройство в обоих)
            saved_mic = max(-1, s.value("assistant_mic_device_id", -1, type=int))
            saved_inter = max(-1, s.value("assistant_interlocutor_device_id", -1, type=int))
            if saved_mic >= 0 and saved_inter >= 0 and saved_mic == saved_inter:
                saved_inter = -1
            if getattr(self, "assistant_mic_combo", None) is not None and self.assistant_mic_combo.count() > 0:
                for i in range(self.assistant_mic_combo.count()):
                    if self.assistant_mic_combo.itemData(i) == saved_mic:
                        self.assistant_mic_combo.blockSignals(True)
                        self.assistant_mic_combo.setCurrentIndex(i)
                        self.assistant_mic_combo.blockSignals(False)
                        break
            if getattr(self, "assistant_interlocutor_combo", None) is not None and self.assistant_interlocutor_combo.count() > 0:
                for i in range(self.assistant_interlocutor_combo.count()):
                    if self.assistant_interlocutor_combo.itemData(i) == saved_inter:
                        self.assistant_interlocutor_combo.blockSignals(True)
                        self.assistant_interlocutor_combo.setCurrentIndex(i)
                        self.assistant_interlocutor_combo.blockSignals(False)
                        break
            if getattr(self, "assistant_job_edit", None) is not None:
                self.assistant_job_edit.blockSignals(True)
                self.assistant_job_edit.setText(s.value("assistant_job_position", "", type=str) or "")
                self.assistant_job_edit.blockSignals(False)
            geom = s.value("geometry")
            if geom is not None:
                self.restoreGeometry(geom)
                # Не давать окну быть уже минимальной ширины (вкладки и контент должны помещаться)
                r = self.geometry()
                if r.width() < WINDOW_WIDTH_BASE:
                    self.setGeometry(r.x(), r.y(), WINDOW_WIDTH_BASE, r.height())
            self._update_all_hotkey_tooltips()
        finally:
            self._loading_settings = False

    def _reset_all_hotkeys(self):
        """Сбросить все горячие клавиши — пользователь назначает сам в полях."""
        for key in ("hide", "show", "screenshot", "get_answer", "start_typer", "pin", "pause", "assistant_start", "assistant_send"):
            he = self._get_hotkey_edit_for_action(key)
            he.blockSignals(True)
            he.setKeySequence(QKeySequence())
            he.setMouse(0, 0)
            he.blockSignals(False)
        self._save_settings()

    def _save_settings(self):
        if getattr(self, "_loading_settings", False):
            return
        s = _open_settings()
        s.setValue("hotkey_hide", self.key_hide.keySequence().toString())
        s.setValue("hotkey_show", self.key_show.keySequence().toString())
        s.setValue("hotkey_screenshot", self.key_screenshot.keySequence().toString())
        s.setValue("hotkey_get_answer", self.key_get_answer.keySequence().toString())
        s.setValue("hotkey_start_typer", self.key_start_typer.keySequence().toString())
        s.setValue("hotkey_move", self.key_move_window.keySequence().toString())
        s.setValue("hotkey_pause", "")
        s.setValue("hotkey_assistant_start", self.key_assistant_start.keySequence().toString())
        s.setValue("hotkey_assistant_send", self.key_assistant_send.keySequence().toString())
        for key in ("hide", "show", "screenshot", "get_answer", "start_typer", "pin", "pause", "assistant_start", "assistant_send"):
            he = self._get_hotkey_edit_for_action(key)
            s.setValue(f"mouse_btn_{key}", he.getMouseButtonIndex())
            s.setValue(f"mouse_mod_{key}", 0 if key == "pause" else he.getMouseModifierIndex())
        self._update_all_shortcuts()
        if getattr(self, "_mouse_emitter", None):
            self._mouse_emitter.set_bindings(self._get_mouse_bindings())
        s.setValue("glass_opacity", self.opacity_slider.value())
        s.setValue("hide_from_capture", self.check_hide_from_capture.isChecked())
        if getattr(self, "tip_opacity_slider", None) is not None:
            s.setValue("tip_overlay_opacity", self.tip_opacity_slider.value())
        if getattr(self, "check_show_tip", None) is not None:
            s.setValue("show_tip", self.check_show_tip.isChecked())
        s.setValue("always_on_top", self.check_always_on_top.isChecked())
        s.setValue("lang_index", 1 if self.lang_en_btn.isChecked() else 0)
        self._api_slot_name[self._api_active_index] = self.api_name_edit.text().strip() or f"API {self._api_active_index + 1}"
        self._api_slot_key[self._api_active_index] = self.api_key_edit.text()
        self._api_slot_url[self._api_active_index] = self.api_url_edit.text()
        self._api_slot_model[self._api_active_index] = self.api_model_edit.text()
        self._api_slot_auth[self._api_active_index] = auth_value_from_index(self.api_auth_combo.currentIndex())
        for i in range(3):
            s.setValue(f"api_name_{i+1}", self._api_slot_name[i])
            s.setValue(f"api_key_{i+1}", self._api_slot_key[i])
            s.setValue(f"api_url_{i+1}", self._api_slot_url[i])
            s.setValue(f"api_model_{i+1}", self._api_slot_model[i])
            s.setValue(f"api_auth_{i+1}", self._api_slot_auth[i])
        s.setValue("api_active", self._api_active_index)
        if getattr(self, "api_for_main_combo", None) is not None:
            self._api_for_main_index = self.api_for_main_combo.currentIndex()
        if getattr(self, "api_for_assistant_combo", None) is not None:
            self._api_for_assistant_index = self.api_for_assistant_combo.currentIndex()
        if getattr(self, "api_for_screenshots_combo", None) is not None:
            self._api_for_screenshots_index = self.api_for_screenshots_combo.currentIndex()
        s.setValue("api_for_main", self._api_for_main_index)
        s.setValue("api_for_assistant", self._api_for_assistant_index)
        s.setValue("api_for_screenshots", self._api_for_screenshots_index)
        for i, edit in enumerate(getattr(self, "prompt_edits", [])):
            if i < 6:
                s.setValue(f"prompt_{i+1}", edit.toPlainText())
        s.setValue("prompt_active_index", self.prompt_active_index)
        if getattr(self, "assistant_prompt_edit", None) is not None:
            s.setValue("assistant_prompt_text", self.assistant_prompt_edit.toPlainText())
        if getattr(self, "screenshot_prompt_edit", None) is not None:
            s.setValue("screenshot_prompt_text", self.screenshot_prompt_edit.toPlainText())
        if getattr(self, "assistant_mic_combo", None) is not None and self.assistant_mic_combo.currentIndex() >= 0:
            mic_id = self.assistant_mic_combo.currentData()
            if mic_id is not None:
                s.setValue("assistant_mic_device_id", int(mic_id))
        if getattr(self, "assistant_interlocutor_combo", None) is not None and self.assistant_interlocutor_combo.currentIndex() >= 0:
            inter_id = self.assistant_interlocutor_combo.currentData()
            if inter_id is not None:
                s.setValue("assistant_interlocutor_device_id", int(inter_id))
        if getattr(self, "assistant_job_edit", None) is not None:
            s.setValue("assistant_job_position", self.assistant_job_edit.text().strip())
        s.setValue("geometry", self.saveGeometry())
        s.sync()
        self._update_all_hotkey_tooltips()

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip(TITLE)
        if self.windowIcon().isNull():
            self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        else:
            self.tray_icon.setIcon(self.windowIcon())
        menu = QMenu()
        restore = QAction("Развернуть", self)
        restore.triggered.connect(self._restore_from_tray)
        menu.addAction(restore)
        menu.addSeparator()
        quit_act = QAction("Выход", self)
        quit_act.triggered.connect(self._quit_app)
        menu.addAction(quit_act)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _minimize_to_tray(self):
        self.tray_icon.show()
        self.hide()

    def _restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(80, self._apply_glass_effect)

    def _quit_app(self):
        self._save_settings()
        self.tray_icon.hide()
        QApplication.quit()

    def _on_autotype_toggled(self, checked: bool):
        """Включено: после успешного ответа ИИ текст будет автоматически напечатан в активное окно."""
        pass

    def _update_typer_destination_indicator(self):
        """Обновляет цвет и подпись индикатора «куда пойдёт печать» по активному окну и мосту."""
        bar = getattr(self, "typer_dest_bar", None)
        label = getattr(self, "typer_dest_label", None)
        if not bar or not label:
            return
        def set_bar_color(hex_color: str):
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor(hex_color))
            bar.setPalette(pal)
        if not _typer_available:
            set_bar_color("#546E7A")
            label.setText("Печать: недоступна")
            return
        try:
            wtype = get_active_window_type()
            source = cursor_bridge_get_source() if cursor_bridge_get_source else None
        except Exception:
            set_bar_color("#546E7A")
            label.setText("Печать: —")
            return
        if wtype == WindowType.IDE and source == "vscode":
            set_bar_color("#007ACC")
            label.setText("Печать → VS Code / Cursor")
        elif wtype == WindowType.IDE and source == "pycharm":
            set_bar_color("#E8B91E")
            label.setText("Печать → PyCharm")
        elif wtype == WindowType.BROWSER:
            set_bar_color("#4CAF50")
            label.setText("Печать → Браузер" + (" (HH.ru)" if source == "hh" else " (Yandex.Code)" if source == "yandex" else ""))
        elif wtype == WindowType.NOTEPAD or (wtype == WindowType.IDE and not source):
            set_bar_color("#78909C")
            label.setText("Печать → Блокнот / редактор")
        else:
            set_bar_color("#78909C")
            label.setText("Печать → Активное окно")
        self._sync_sidebar_typer()

    def _start_typer_from_response(self):
        """Запускает печать текста из «Ответ ИИ» в активное окно (через typer + мост курсора)."""
        if not _typer_available:
            return
        text = (getattr(self, "_response_raw_text", None) or self.response_edit.toPlainText() or "").strip()
        if not text:
            self._response_raw_text = ""
            self.response_edit.setPlainText("Нет текста для печати. Сначала получите ответ ИИ.")
            return
        self.type_response_btn.setEnabled(False)
        self.type_response_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_STOP)))
        self.type_response_btn.setToolTip("Печать идёт… Нажмите горячую клавишу «Печать», чтобы прервать.")
        self.type_response_btn.setProperty("typingActive", True)
        self._sync_sidebar_typer()
        if getattr(self, "typer_dest_label", None):
            self.typer_dest_label.setText("Печать: идёт…")
        self._typer_pause_event.clear()
        self._typer_abort_event.clear()
        use_cached_tips = getattr(self, "_cached_tips_text", None) == text and getattr(self, "_typer_tips", None)
        if not use_cached_tips:
            self._typer_tips = {}
            self._update_tips_tab({})
        if getattr(self, "_typer_paused_now", None) is not None:
            self._typer_paused_now[0] = False
        worker = TyperWorker(response_text=text, initial_delay=5, base_speed=6.0, pause_event=self._typer_pause_event, paused_now=self._typer_paused_now, abort_event=self._typer_abort_event)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_typer_finished, Qt.ConnectionType.QueuedConnection)
        worker.block_changed.connect(self._on_typer_block_changed, Qt.ConnectionType.QueuedConnection)
        worker.body_line_changed.connect(self._on_typer_body_line_changed, Qt.ConnectionType.QueuedConnection)
        worker.line_changed.connect(self._on_typer_line_changed, Qt.ConnectionType.QueuedConnection)
        self._typer_thread = thread
        self._typer_worker = worker
        thread.start()
        if use_cached_tips:
            self._update_tips_tab(self._typer_tips)
        self._tip_overlay.set_tip("Загрузка подсказок…" if not use_cached_tips else "")
        if getattr(self, "check_show_tip", None) is not None:
            self._tip_overlay.set_tip_visible(self.check_show_tip.isChecked())
        self._tip_overlay.show_overlay()
        if not use_cached_tips:
            base_url, api_key, model, auth_type = self._get_api_params_for(getattr(self, "_api_for_main_index", 0))
            if base_url and model and chat_completion:
                self._typer_tips_request_text = text
                tips_worker = TipsRequestWorker(base_url, api_key, model, auth_type, text)
                tips_thread = QThread(self)
                tips_worker.moveToThread(tips_thread)
                tips_thread.started.connect(tips_worker.run)
                tips_worker.finished.connect(self._on_tips_received, Qt.ConnectionType.QueuedConnection)
                self._tips_thread = tips_thread
                self._tips_worker = tips_worker
                tips_thread.start()
            else:
                self._typer_tips_request_text = None
        else:
            self._tip_overlay.set_tip("")

    def _on_get_review_clicked(self):
        """Отправить код из вкладки «Ответ» в API для код-ревью (сеньор), результат — во вкладку «Ревью»."""
        code = (getattr(self, "_response_raw_text", None) or self.response_edit.toPlainText() or "").strip()
        if not code:
            if getattr(self, "review_edit", None) is not None:
                self.review_edit.setPlainText("Нет кода для ревью. Сначала получите ответ ИИ и вставьте код во вкладку «Ответ».")
            return
        base_url, api_key, model, auth_type = self._get_api_params_for(getattr(self, "_api_for_main_index", 0))
        if not base_url or not model:
            if getattr(self, "review_edit", None) is not None:
                self.review_edit.setPlainText("Укажите URL API и модель на вкладке API.")
            return
        if getattr(self, "review_edit", None) is not None:
            self.review_edit.setPlainText("Отправка запроса на ревью...")
        if getattr(self, "get_review_btn", None) is not None:
            self.get_review_btn.setEnabled(False)
        worker = CodeReviewWorker(base_url, api_key, model, auth_type, code)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_review_received, Qt.ConnectionType.QueuedConnection)
        self._review_thread = thread
        self._review_worker = worker
        thread.start()

    def _on_review_received(self, success: bool, text: str):
        """Результат запроса код-ревью — вывести во вкладку «Ревью» в HTML с подсветкой кода."""
        if getattr(self, "review_edit", None) is not None:
            if success:
                html = markdown_review_to_html(text)
                self.review_edit.setHtml(html)
            else:
                self.review_edit.setPlainText(f"Ошибка: {text}")
        if getattr(self, "get_review_btn", None) is not None:
            self.get_review_btn.setEnabled(True)
        if getattr(self, "_review_thread", None) is not None:
            self._review_thread.quit()
            self._review_thread.wait(2000)

    def _on_typer_block_changed(self, block_name: str, block_type: str):
        """Тайпер вошёл в новый блок — показываем описание: что этот блок делает в целом."""
        self._typer_current_block = block_name
        self._typer_current_line_index = None
        tip = self._tip_for_block_or_line(block_name, None)
        self._tip_overlay.set_tip(tip if tip else "")

    def _on_typer_body_line_changed(self, block_name: str, line_index: int, line_content: str):
        """Тайпер печатает строку тела на фазе заполнения — подсказка по строке (без префикса «Строка N»)."""
        if not line_content.strip():
            return
        self._typer_current_block = block_name
        self._typer_current_line_index = line_index
        tip = self._tip_for_block_or_line(block_name, line_index)
        if not tip:
            tips = getattr(self, "_typer_tips", None) or {}
            src_line = getattr(self, "_typer_current_source_line", None)
            if src_line is not None:
                tip = tips.get(str(src_line))
            if not tip:
                tip = tips.get("content:" + _normalize_content_key(line_content))
        if tip:
            self._tip_overlay.set_tip(tip)
        else:
            preview = (line_content.strip()[:50] + "…") if len(line_content.strip()) > 50 else line_content.strip()
            self._tip_overlay.set_tip(preview if preview else "")

    def _on_typer_line_changed(self, source_line: int, line_content: str):
        """Тайпер печатает строку — подсказка по номеру строки (LINE: N) или по началу строки (content), иначе превью."""
        if not line_content.strip():
            return
        self._typer_current_source_line = source_line
        tips = getattr(self, "_typer_tips", None) or {}
        tip = tips.get(str(source_line))
        if not tip:
            tip = tips.get("content:" + _normalize_content_key(line_content))
        if tip:
            self._tip_overlay.set_tip(tip)
            return
        preview = (line_content.strip()[:50] + "…") if len(line_content.strip()) > 50 else line_content.strip()
        self._tip_overlay.set_tip(preview if preview else "")

    def _tip_for_block_or_line(self, block_name: str, line_index: Optional[int]) -> str:
        """Подсказка для блока или для строки тела (line_index 0, 1, ...)."""
        if line_index is not None:
            key = f"{block_name}:{line_index}"
            tip = self._typer_tips.get(key)
            if tip:
                return tip
        tip = self._typer_tips.get(block_name)
        if tip:
            return tip
        bn_lower = block_name.lower()
        for k, v in self._typer_tips.items():
            if not k or not v:
                continue
            if ":" in k:
                pref, _ = k.split(":", 1)
                if pref.strip().lower() == bn_lower and line_index is not None:
                    return v
            elif k.strip().lower() == bn_lower:
                return v
        return ""

    def _format_tips_for_review(self, tips: dict) -> str:
        """Форматирует словарь подсказок для вкладки «Подсказки» (разбор кода)."""
        if not tips:
            return "Подсказок пока нет. Запустите печать — они подгрузятся от API."
        lines = []
        # Строки по номеру (1, 2, 3, ...)
        line_keys = sorted((k for k in tips if k.isdigit()), key=int)
        if line_keys:
            lines.append("─── По строкам ───")
            for k in line_keys:
                lines.append(f"  Строка {k}: {tips[k]}")
            lines.append("")
        # Блоки (имя без : и не число)
        block_keys = sorted(k for k in tips if not k.startswith("content:") and ":" not in k and not k.isdigit())
        if block_keys:
            lines.append("─── Блоки (класс/функция) ───")
            for k in block_keys:
                name = k.strip()
                lines.append(f"  {name}")
                lines.append(f"    {tips[k]}")
            lines.append("")
        # Строки тела блока (block_name:0, block_name:1, ...)
        body_keys = sorted((k for k in tips if ":" in k and not k.startswith("content:") and not k.isdigit()), key=lambda x: (x.split(":")[0], int(x.split(":")[1]) if x.split(":")[1].isdigit() else 0))
        if body_keys:
            lines.append("─── Строки тела блоков ───")
            for k in body_keys:
                part1, part2 = k.split(":", 1)
                lines.append(f"  {part1}, строка {part2}: {tips[k]}")
        return "\n".join(lines)

    def _update_tips_tab(self, tips: dict):
        """Обновляет текст во вкладке «Подсказки»."""
        if getattr(self, "tips_review_edit", None) is None:
            return
        self.tips_review_edit.setPlainText(self._format_tips_for_review(tips))

    def _on_tips_received(self, tips: dict):
        """Подсказки от API получены — сохраняем, обновляем вкладку «Подсказки» и оверлей под текущий блок/строку."""
        self._typer_tips = tips
        self._cached_tips_text = getattr(self, "_typer_tips_request_text", None)
        self._update_tips_tab(tips)
        cur_src_line = getattr(self, "_typer_current_source_line", None)
        if cur_src_line is not None:
            tip = tips.get(str(cur_src_line))
            if tip:
                self._tip_overlay.set_tip(tip)
                return
        cur_block = getattr(self, "_typer_current_block", None)
        cur_line = getattr(self, "_typer_current_line_index", None)
        if cur_block:
            tip = self._tip_for_block_or_line(cur_block, cur_line)
            if tip:
                self._tip_overlay.set_tip(tip)

    def _on_typer_finished(self):
        """Печать завершена или прервана — разблокируем кнопку и восстанавливаем вид."""
        self._tip_overlay.hide_overlay()
        if getattr(self, "_typer_abort_event", None) is not None:
            self._typer_abort_event.clear()
        if getattr(self, "_typer_thread", None):
            self._typer_thread.quit()
            self._typer_thread.wait(2000)
        tips_th = getattr(self, "_tips_thread", None)
        if tips_th is not None and tips_th.isRunning():
            tips_th.quit()
            tips_th.wait(2000)
        if getattr(self, "type_response_btn", None):
            self.type_response_btn.setEnabled(True)
            self.type_response_btn.setIcon(QIcon(app_icons.icon_path(app_icons.SIDEBAR_PLAY)))
            self.type_response_btn.setToolTip("Печатать ответ в активное окно (редактор/браузер)")
            self.type_response_btn.setProperty("typingActive", False)
            sty = self.type_response_btn.style()
            sty.unpolish(self.type_response_btn)
            sty.polish(self.type_response_btn)
        self._sync_sidebar_typer()
        self._update_typer_destination_indicator()

    def _on_send_clicked(self):
        text = self.task_edit.toPlainText().strip()
        if not text:
            self._response_raw_text = None
            self._cached_tips_text = None
            self.response_edit.setPlainText("Введите запрос в поле выше.")
            return
        self._send_request_with_text(text)

    def _on_api_response(self, success: bool, result_text: str):
        """Вызывается в главном потоке по завершении запроса к API."""
        if getattr(self, "_api_thread", None):
            self._api_thread.quit()
            self._api_thread.wait(5000)
        text, _ = strip_code_fences(result_text)
        target = getattr(self, "_api_response_target", "main")
        if target == "assistant":
            if getattr(self, "assistant_answer_edit", None):
                normalized_text, code_ranges = normalize_assistant_answer(text)
                self.assistant_answer_edit.setPlainText(normalized_text)
                if getattr(self, "_assistant_answer_highlighter", None) is not None:
                    self._assistant_answer_highlighter.set_code_block_ranges(code_ranges)
                    self._assistant_answer_highlighter.rehighlight()
            if getattr(self, "assistant_send_btn", None):
                self.assistant_send_btn.setEnabled(True)
                self._sync_sidebar_assistant()
            # Очистить область распознанного текста после отправки
            if getattr(self, "assistant_transcript_edit", None):
                self.assistant_transcript_edit.clear()
            self._assistant_committed_text = ""
            self._assistant_partial_user = ""
            self._assistant_partial_interlocutor = ""
        else:
            self._response_raw_text = text
            self._cached_tips_text = None
            self.response_edit.setHtml(response_to_html(result_text))
            self.send_btn.setEnabled(True)
            if success and self.autotype_toggle.isChecked() and text.strip():
                QTimer.singleShot(1500, self._start_typer_from_response)

    def _on_screenshot(self):
        """Скриншот: выделение области мышью, по отпускании — диалог с превью и кнопками «Отправить» / «Распознать текст»."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.geometry()
        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            return
        overlay = ScreenshotOverlay(pixmap, geom, self)
        overlay.send_clicked.connect(self._on_screenshot_send_clicked)
        overlay.recognize_clicked.connect(self._on_screenshot_recognize_clicked)
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()

    def _image_to_base64(self, image: QImage) -> str:
        """Конвертирует QImage в base64-строку (PNG)."""
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        return bytes(buf.data().toBase64()).decode("ascii")

    def _on_screenshot_send_clicked(self, image: QImage):
        """Отправить скриншот и промпт в API для скриншотов, ответ вывести на вкладке «Главная»."""
        prompt_text = (self.screenshot_prompt_edit.toPlainText().strip() if getattr(self, "screenshot_prompt_edit", None) else "") or SCREENSHOT_TASK_PROMPT
        slot = getattr(self, "_api_for_screenshots_index", 0)
        base_url, api_key, model, auth_type = self._get_api_params_for(slot)
        if not base_url or not model:
            self.response_edit.setPlainText("Укажите URL API и модель для скриншотов на вкладке API.")
            self.main_tabs.setCurrentIndex(0)
            return
        image_base64 = self._image_to_base64(image)
        self.main_tabs.setCurrentIndex(0)
        self.response_edit.setPlainText("Отправка скриншота в API...")
        self.send_btn.setEnabled(False)
        worker = ScreenshotSendWorker(base_url, api_key, model, auth_type, prompt_text, image_base64)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_screenshot_api_finished, Qt.ConnectionType.QueuedConnection)
        self._screenshot_thread = thread
        self._screenshot_worker = worker
        thread.start()

    def _on_screenshot_api_finished(self, success: bool, text: str):
        """Результат запроса по скриншоту: вывести в response_edit на Главной."""
        self.send_btn.setEnabled(True)
        self._response_raw_text = text
        self._cached_tips_text = None
        self.response_edit.setHtml(response_to_html(text)) if success else self.response_edit.setPlainText(text)

    def _on_screenshot_recognize_clicked(self, image: QImage):
        """Распознать текст на скриншоте через RapidOCR в отдельном процессе (русский + английский)."""
        if image.isNull():
            return
        try:
            fd, path = tempfile.mkstemp(suffix=".png")
            try:
                os.close(fd)
                if not image.save(path, "PNG"):
                    self.response_edit.setPlainText("Не удалось сохранить изображение во временный файл.")
                    self.main_tabs.setCurrentIndex(0)
                    return
            except Exception as e:
                self.response_edit.setPlainText(f"Ошибка сохранения: {e}")
                self.main_tabs.setCurrentIndex(0)
                return
            self.main_tabs.setCurrentIndex(0)
            self.response_edit.setPlainText("Распознавание текста...")
            self.send_btn.setEnabled(False)
            from runtime_paths import get_data_base, is_frozen
            project_root = get_data_base() if is_frozen() else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            process = QProcess(self)
            process.setWorkingDirectory(project_root)
            process.finished.connect(
                lambda exit_code, status: self._on_ocr_process_finished(process, path, exit_code, status)
            )
            self._ocr_process = process

            def on_ocr_error():
                self.send_btn.setEnabled(True)
                pip_cmd = pip_install_rapidocr_command()
                self.response_edit.setPlainText("Не удалось запустить процесс OCR.\n\nУстановите в терминале (PowerShell):\n" + pip_cmd)
                try:
                    if path and os.path.isfile(path):
                        os.unlink(path)
                except Exception:
                    pass

            process.errorOccurred.connect(on_ocr_error)
            process.start(sys.executable, ["-m", "gui.ocr_subprocess", path])
        except BaseException as e:
            self.send_btn.setEnabled(True)
            self.response_edit.setPlainText(f"Ошибка запуска OCR: {type(e).__name__}: {e}")
            self.main_tabs.setCurrentIndex(0)

    def _on_ocr_process_finished(self, process: QProcess, temp_path: str, exit_code: int, exit_status: QProcess.ExitStatus):
        """По завершении процесса OCR: прочитать вывод, удалить файл, показать результат."""
        try:
            if temp_path and os.path.isfile(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass
        try:
            self.send_btn.setEnabled(True)
            raw_out = process.readAllStandardOutput().data()
            raw_err = process.readAllStandardError().data()
            out = raw_out.decode("utf-8", errors="replace").strip()
            err = raw_err.decode("utf-8", errors="replace").strip()
            if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
                ocr_text = out or "(Текст не распознан)"
                self._response_raw_text = ocr_text
                self._cached_tips_text = None
                self.response_edit.setPlainText(ocr_text)
                # Отправить распознанный текст в API с выбранным промптом главной (как «Получить ответ»)
                if getattr(self, "task_edit", None) is not None:
                    self.task_edit.setPlainText(ocr_text)
                active_prompt = self._get_active_prompt_text()
                message = (active_prompt + "\n\n" + ocr_text) if active_prompt else ocr_text
                self._send_request_with_text(message, response_target="main")
            else:
                pip_cmd = pip_install_rapidocr_command()
                msg = err or f"Процесс OCR завершился с кодом {exit_code}."
                self.response_edit.setPlainText(
                    msg + "\n\nУстановите пакеты (PowerShell):\n" + pip_cmd
                )
        except Exception:
            self.response_edit.setPlainText("Ошибка при чтении результата OCR.")

    def _on_start_or_stop_typer(self):
        """Горячая клавиша «Печать»: запуск печати ответа или прерывание (повторное нажатие)."""
        thread = getattr(self, "_typer_thread", None)
        if thread is not None and thread.isRunning():
            if getattr(self, "_typer_abort_event", None) is not None:
                self._typer_abort_event.set()
            return
        self._start_typer_from_response()

    def _on_pause_shortcut(self):
        """Пауза: ставим запрос; Продолжить — только когда тайпер реально остановился (paused_now). Повторные нажатия до остановки игнорируем."""
        if not getattr(self, "_typer_thread", None) or not self._typer_thread.isRunning():
            return
        event = getattr(self, "_typer_pause_event", None)
        paused_now = getattr(self, "_typer_paused_now", None)
        if event is None:
            return
        if event.is_set():
            if paused_now is not None and paused_now[0]:
                event.clear()
        else:
            event.set()

    def _on_assistant_start_shortcut(self):
        """Горячая клавиша / мышь: переключение на вкладку «Помощник» и старт распознавания."""
        self._restore_from_tray()
        self.main_tabs.setCurrentIndex(4)  # Помощник
        if getattr(self, "assistant_start_btn", None) and self.assistant_start_btn.isEnabled():
            self._on_assistant_start_clicked()

    def _on_assistant_send_shortcut(self):
        """Горячая клавиша / мышь: переключение на вкладку «Помощник» и отправка запроса."""
        self._restore_from_tray()
        self.main_tabs.setCurrentIndex(4)  # Помощник
        if getattr(self, "assistant_send_btn", None) and self.assistant_send_btn.isEnabled():
            self._on_assistant_send_clicked()

    def _on_get_answer_shortcut(self):
        """По горячей клавише: читаем буфер (пользователь сам нажимает Ctrl+C), активный промпт + текст → API."""
        clipboard = QApplication.clipboard()
        selected = (clipboard.text() or "").strip()
        self._restore_from_tray()
        self.main_tabs.setCurrentIndex(0)
        if not selected:
            self._response_raw_text = None
            self._cached_tips_text = None
            self.response_edit.setPlainText(
                "Скопируйте текст (Ctrl+C), затем нажмите горячую клавишу «Получить ответ» — запрос уйдёт с этим текстом."
            )
            return
        active_prompt = self._get_active_prompt_text()
        message = (active_prompt + "\n\n" + selected) if active_prompt else selected
        self._send_request_with_text(message)

    def closeEvent(self, event):
        self._save_settings()
        if getattr(self, "_mouse_emitter", None):
            self._mouse_emitter.stop()
        if getattr(self, "_assistant_stop_event", None):
            self._assistant_stop_event.set()
        if getattr(self, "_assistant_thread", None) and self._assistant_thread.is_alive():
            self._assistant_thread.join(timeout=1.0)
        super().closeEvent(event)

    def _apply_glass_effect(self):
        """Применить размытие и захват — вызывается при показе и при активации окна."""
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            hwnd = int(self.winId())
            enable_blur_behind(hwnd)
            if self.check_hide_from_capture.isChecked():
                set_window_exclude_from_capture(hwnd)
        except Exception:
            pass

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange or event.type() == QEvent.Type.ActivationChange:
            QTimer.singleShot(30, self._apply_glass_effect)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self._apply_glass_effect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        try:
            if getattr(self, "_pinned", False):
                self._pin_collapse_timer.stop()
                self._pin_expand()
        except Exception:
            pass
        super().enterEvent(event)

    def leaveEvent(self, event):
        try:
            if getattr(self, "_pinned", False) and getattr(self, "_pin_allow_collapse", True):
                self._pin_collapse_timer.start(380)
        except Exception:
            pass
        super().leaveEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from gui.checkbox_style import CheckboxWithCheckStyle
    app.setStyle(CheckboxWithCheckStyle(app.style()))
    w = GlassMainWindow()
    w.tray_icon.show()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
