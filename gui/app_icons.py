# -*- coding: utf-8 -*-
"""
Пути к иконкам кнопок приложения (папка gui/icons/app).
Иконки подобраны из Lucide, переименованы под действия и состояния.
"""
import os

from runtime_paths import get_resource_base, get_data_base, is_frozen

if is_frozen():
    _ICONS_DIR = os.path.join(get_resource_base(), "gui", "icons", "app")
    _ICONS_CACHE_DIR = os.path.join(get_data_base(), "cache", "gui", "icons", "app")
else:
    _ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons", "app")
    _ICONS_CACHE_DIR = _ICONS_DIR


def icon_dir() -> str:
    """Путь к папке gui/icons/app."""
    return _ICONS_DIR


def icon_path(name: str) -> str:
    """Полный путь к файлу иконки по имени (без .svg)."""
    return os.path.join(_ICONS_DIR, f"{name}.svg")


def icon_with_color(name: str, color_hex: str):
    """
    Загружает SVG-иконку, подставляет color_hex вместо currentColor (stroke/fill),
    возвращает QIcon. Нужно для кнопок на тёмном фоне (иначе иконка чёрная).
    """
    from PySide6.QtGui import QIcon, QPixmap, QPainter
    from PySide6.QtCore import Qt
    from PySide6.QtSvg import QSvgRenderer

    path = icon_path(name)
    if not os.path.isfile(path):
        return QIcon(path)  # fallback: обычная загрузка
    with open(path, "r", encoding="utf-8") as f:
        svg = f.read()
    # Lucide: stroke="currentColor", иногда fill="none" или fill="currentColor"
    svg = svg.replace("currentColor", color_hex)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    if not renderer.isValid():
        return QIcon(icon_path(name))
    from PySide6.QtCore import QSize
    size = renderer.defaultSize()
    if size.width() <= 0 or size.height() <= 0:
        size = QSize(24, 24)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    icon = QIcon(pixmap)
    return icon


# Имена иконок для кнопок (без .svg)
# Верхняя панель
TITLE_TRAY = "title_tray"           # свернуть в трей
TITLE_PIN = "title_pin"             # приклеить (состояние: приклеено)
TITLE_PIN_OFF = "title_pin_off"    # приклеить (состояние: отклеено)
TITLE_CLOSE = "title_close"         # закрыть

# Сайдбар — главная
SIDEBAR_SEND = "sidebar_send"             # отправить ИИ
SIDEBAR_PLAY = "sidebar_play"             # печать ответа
SIDEBAR_PAUSE = "sidebar_pause"           # пауза печати
SIDEBAR_SCREENSHOT = "sidebar_screenshot" # скриншот
SIDEBAR_GET_ANSWER = "sidebar_get_answer" # получить ответ

# Сайдбар — помощник
SIDEBAR_STOP = "sidebar_stop"       # стоп
SIDEBAR_VOLUME = "sidebar_volume"   # звук вкл
SIDEBAR_VOLUME_MUTE = "sidebar_volume_mute"  # мьют
SIDEBAR_CLEAR = "sidebar_clear"    # очистить
# отправка помощника — та же SIDEBAR_SEND


def ensure_check_orange_png(color_hex: str = "#FF9900", size: int = 20) -> str:
    """
    Рендерит оранжевую галочку в PNG для чекбокса. Создаёт check_orange.png
    в gui/icons/app и возвращает абсолютный путь. Если файл уже есть — возвращает путь.
    В frozen-режиме пишет в кэш рядом с exe.
    """
    png_name = "check_orange.png"
    png_path = os.path.join(_ICONS_CACHE_DIR, png_name)
    if os.path.isfile(png_path):
        return os.path.abspath(png_path)
    try:
        from PySide6.QtGui import QPixmap, QPainter
        from PySide6.QtCore import Qt, QSize
        from PySide6.QtSvg import QSvgRenderer
        _svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color_hex}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M20 6 9 17l-5-5"/></svg>'
        )
        renderer = QSvgRenderer(_svg.encode("utf-8"))
        if not renderer.isValid():
            return ""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, pixmap.rect())
        painter.end()
        os.makedirs(_ICONS_CACHE_DIR, exist_ok=True)
        pixmap.save(png_path)
        return os.path.abspath(png_path)
    except Exception:
        return ""
