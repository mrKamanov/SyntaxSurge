# -*- coding: utf-8 -*-
"""
Пути приложения в обычном и frozen-режиме (PyInstaller exe).
"""
import os
import sys


def is_frozen() -> bool:
    """True, если приложение запущено из exe (PyInstaller)."""
    return getattr(sys, "frozen", False)


def get_resource_base() -> str:
    """Базовый путь к ресурсам (иконки и т.п.). В frozen — sys._MEIPASS."""
    if is_frozen():
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def get_data_base() -> str:
    """Базовый путь для записываемых данных (map, log, cache). В frozen — рядом с exe."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
