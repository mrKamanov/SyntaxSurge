# -*- coding: utf-8 -*-
"""
Модуль печати (typing) для приложения.
Карта кода, оркестрация печати, низкоуровневый ввод.
"""

import os

# Пути — определяем до импорта code_printer (он импортирует LOG_FILE)
_typer_dir = os.path.dirname(os.path.abspath(__file__))
MAP_DIR = os.path.join(_typer_dir, "map")
LOG_DIR = os.path.join(_typer_dir, "log")
LOG_FILE = os.path.join(LOG_DIR, "typer_log.log")

from typer.code_mapper import CodeMapBuilder, CodeMap, CodeElement, ElementType
from typer.code_printer import CodePrinter
from typer.windows_typer import WindowsTyper, TypingConfig, TyperAborted
from typer.sql_mapper import SqlCodeMapBuilder
from typer.language_detect import detect_from_filepath, detect_from_content
from typer.map_cleanup import prune_map_dir
from typer.active_window import (
    WindowType as ActiveWindowType,
    ActiveWindowInfo,
    get_active_window,
    get_active_window_type,
    get_active_window_display,
    is_cursor_in_ide,
    is_cursor_in_browser,
    is_cursor_in_notepad,
)

__all__ = [
    "CodeMapBuilder",
    "CodeMap",
    "CodeElement",
    "ElementType",
    "CodePrinter",
    "SqlCodeMapBuilder",
    "detect_from_filepath",
    "detect_from_content",
    "WindowsTyper",
    "TypingConfig",
    "TyperAborted",
    "MAP_DIR",
    "LOG_DIR",
    "LOG_FILE",
    "ActiveWindowType",
    "ActiveWindowInfo",
    "get_active_window",
    "get_active_window_type",
    "get_active_window_display",
    "is_cursor_in_ide",
    "is_cursor_in_browser",
    "is_cursor_in_notepad",
    "prune_map_dir",
]
