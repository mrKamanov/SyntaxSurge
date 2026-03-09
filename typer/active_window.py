#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Определение активного окна: браузер, Блокнот или IDE.
Использует Windows API (user32, kernel32) через ctypes.
"""

import os
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum


# Константы Windows API
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Сообщения Edit (стандартный Блокнот) и Rich Edit (новый Win11)
EM_GETSEL = 0x00B0
EM_LINEFROMCHAR = 0x00C9
EM_LINEINDEX = 0x00BB
EM_EXGETSEL = 0x0434
EM_EXLINEFROMCHAR = 0x0442
EM_GETTEXTLENGTHEX = 0x045E
EM_GETTEXTEX = 0x045C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
GTL_DEFAULT = 0
GT_DEFAULT = 0
CP_UNICODE = 1200


class _CHARRANGE(ctypes.Structure):
    _fields_ = [("cpMin", ctypes.c_long), ("cpMax", ctypes.c_long)]


class _GETTEXTLENGTHEX(ctypes.Structure):
    _fields_ = [("flags", wintypes.DWORD), ("codepage", wintypes.UINT)]


class _GETTEXTEX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("codepage", wintypes.UINT),
        ("lpDefaultChar", ctypes.c_void_p),
        ("lpUsedDefChar", ctypes.c_void_p),
    ]


class WindowType(Enum):
    """Тип активного окна по содержимому/процессу."""
    IDE = "ide"
    BROWSER = "browser"
    NOTEPAD = "notepad"
    UNKNOWN = "unknown"


@dataclass
class ActiveWindowInfo:
    """Информация об активном (на переднем плане) окне."""
    window_type: WindowType
    title: str
    process_name: str
    process_path: str = ""


def _get_foreground_hwnd() -> int:
    """Дескриптор окна на переднем плане (0 при ошибке)."""
    return user32.GetForegroundWindow()


def _get_window_text(hwnd: int) -> str:
    """Текст заголовка окна."""
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value or ""


def _get_window_process_id(hwnd: int) -> int:
    """Идентификатор процесса, владеющего окном (0 при ошибке)."""
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _get_process_image_path(pid: int) -> str:
    """Полный путь к исполняемому файлу процесса (пустая строка при ошибке)."""
    if not pid:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(261)
        size = wintypes.DWORD(261)  # размер в символах (TCHAR)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _classify_window(title: str, process_name: str) -> WindowType:
    """
    Классификация по заголовку окна и имени процесса.
    IDE, браузер, Блокнот или неизвестно.
    """
    title_lower = title.lower()
    proc_lower = process_name.lower()

    # IDE: редакторы кода
    ide_markers = (
        "visual studio code",
        "vs code",
        "cursor",
        "pyCharm",
        "pycharm",
        "jetbrains",
        "intellij",
        "phpstorm",
        "webstorm",
        "rider",
        "code - ",
        " - visual studio",
        "sublime text",
        "vim ",
        "neovim",
    )
    for m in ide_markers:
        if m in title_lower:
            return WindowType.IDE
    if proc_lower in (
        "code.exe", "cursor.exe", "pycharm64.exe", "idea64.exe",
        "devenv.exe", "sublime_text.exe", "notepad++.exe",
    ):
        return WindowType.IDE

    # Блокнот (системный Notepad; заголовок может быть "Notepad" или "Блокнот")
    if "notepad" in title_lower or "блокнот" in title_lower or proc_lower.endswith("notepad.exe"):
        return WindowType.NOTEPAD

    # Браузеры
    browser_markers = (
        "chrome", " - google chrome",
        "edge", " - microsoft edge",
        "firefox", " - mozilla firefox",
        "opera", "brave", "yandex",
        " - chromium",
    )
    for m in browser_markers:
        if m in title_lower:
            return WindowType.BROWSER
    if any(x in proc_lower for x in (
        "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe",
        "brave.exe", "browser.exe",
    )):
        return WindowType.BROWSER

    return WindowType.UNKNOWN


def get_foreground_hwnd() -> int:
    """Дескриптор окна на переднем плане (0 при ошибке). Для проверки потери фокуса при печати."""
    return _get_foreground_hwnd()


def get_active_window() -> ActiveWindowInfo:
    """
    Возвращает информацию об окне, которое сейчас в фокусе
    (куда попадёт ввод с клавиатуры).
    """
    hwnd = _get_foreground_hwnd()
    title = _get_window_text(hwnd)
    pid = _get_window_process_id(hwnd)
    path = _get_process_image_path(pid)
    process_name = os.path.basename(path) if path else ""
    window_type = _classify_window(title, process_name)
    return ActiveWindowInfo(
        window_type=window_type,
        title=title,
        process_name=process_name,
        process_path=path,
    )


def get_active_window_type() -> WindowType:
    """Только тип активного окна: IDE, BROWSER, NOTEPAD или UNKNOWN."""
    return get_active_window().window_type


def is_cursor_in_ide() -> bool:
    """Курсор (фокус ввода) в окне IDE."""
    return get_active_window_type() == WindowType.IDE


def is_cursor_in_browser() -> bool:
    """Курсор в окне браузера."""
    return get_active_window_type() == WindowType.BROWSER


def is_cursor_in_notepad() -> bool:
    """Курсор в Блокноте."""
    return get_active_window_type() == WindowType.NOTEPAD


def _get_notepad_edit_hwnd():
    """Дескриптор Edit-контроля Блокнота, если активное окно — классический Блокнот. Иначе 0."""
    hwnd = _get_foreground_hwnd()
    if not hwnd or get_active_window_type() != WindowType.NOTEPAD:
        return 0
    return user32.FindWindowExW(hwnd, None, "Edit", None) or 0


def _get_window_class_name(hwnd: int) -> str:
    """Имя класса окна (для поиска по классу)."""
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(260)
    if user32.GetClassNameW(hwnd, buf, 260) <= 0:
        return ""
    return buf.value or ""


def find_any_notepad_edit_hwnd() -> int:
    """
    Ищет любое открытое окно Блокнота (notepad.exe) с Edit-контролем.
    Возвращает дескриптор Edit (hwnd) или 0. Не требует, чтобы Блокнот был в фокусе.
    Способы: (1) FindWindowW("Notepad"), (2) EnumWindows + класс "Notepad", (3) EnumWindows + процесс notepad.exe.
    """
    def _richedit_len(hwnd):
        gt = _GETTEXTLENGTHEX(flags=GTL_DEFAULT, codepage=CP_UNICODE)
        n = user32.SendMessageW(hwnd, EM_GETTEXTLENGTHEX, 0, ctypes.byref(gt))
        return max(0, n) if n is not None and n >= 0 else 0

    # Ищем дочерний контрол с текстом; если несколько — с макс. длиной (EM_GETTEXTLENGTHEX для Rich Edit)
    def _find_text_child(parent):
        candidates = []
        for class_name in ("Edit", "RichEditD2DPT", "NotepadTextBox"):
            child = 0
            while True:
                child = user32.FindWindowExW(parent, child, class_name, None)
                if not child:
                    break
                length = user32.SendMessageW(child, WM_GETTEXTLENGTH, 0, 0)
                length = length if length and length > 0 else 0
                if length == 0:
                    length = _richedit_len(child)
                sel_end = -1
                if length == 0:
                    cr = _CHARRANGE()
                    user32.SendMessageW(child, EM_EXGETSEL, 0, ctypes.byref(cr))
                    if cr.cpMax >= 0:
                        sel_end = cr.cpMax
                candidates.append((child, length, sel_end))
        if not candidates:
            return 0
        best = max(candidates, key=lambda t: (t[1], t[2]))
        return best[0]

    # 1) Классический / новый Блокнот: класс окна "Notepad"
    notepad_hwnd = user32.FindWindowW("Notepad", None)
    if notepad_hwnd:
        edit_hwnd = _find_text_child(notepad_hwnd)
        if edit_hwnd:
            return edit_hwnd

    result = [0]

    def enum_by_class(hwnd, _lparam):
        if not hwnd or result[0]:
            return True
        if _get_window_class_name(hwnd) != "Notepad":
            return True
        child = _find_text_child(hwnd)
        if child:
            result[0] = child
            return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_by_class), 0)
    if result[0]:
        return result[0]

    def enum_by_process(hwnd, _lparam):
        if not hwnd or result[0]:
            return True
        pid = _get_window_process_id(hwnd)
        if not pid:
            return True
        path = _get_process_image_path(pid)
        if not path or not path.lower().endswith("notepad.exe"):
            return True
        child = _find_text_child(hwnd)
        if child:
            result[0] = child
            return False
        return True

    result[0] = 0
    user32.EnumWindows(WNDENUMPROC(enum_by_process), 0)
    return result[0]


def _get_notepad_cursor_from_edit_hwnd(hwnd_edit: int) -> Optional[Tuple[int, int]]:
    """Позиция курсора по дескриптору Edit/Rich Edit. 1-based (строка, столбец)."""
    if not hwnd_edit:
        return None
    caret = None
    cr = _CHARRANGE()
    user32.SendMessageW(hwnd_edit, EM_EXGETSEL, 0, ctypes.byref(cr))
    if cr.cpMax >= 0 and cr.cpMax < 0x7FFFFFFF:
        caret = cr.cpMax
    if caret is None:
        start = wintypes.DWORD()
        end = wintypes.DWORD()
        user32.SendMessageW(hwnd_edit, EM_GETSEL, ctypes.byref(start), ctypes.byref(end))
        caret = end.value
    if caret is None or caret < 0:
        return None
    line_0 = user32.SendMessageW(hwnd_edit, EM_EXLINEFROMCHAR, 0, caret)
    if line_0 < 0:
        line_0 = user32.SendMessageW(hwnd_edit, EM_LINEFROMCHAR, caret, 0)
    if line_0 < 0:
        return None
    line_start = user32.SendMessageW(hwnd_edit, EM_LINEINDEX, line_0, 0)
    if line_start < 0:
        return None
    col_0 = caret - line_start
    return (line_0 + 1, col_0 + 1)


def _get_notepad_full_content_from_edit_hwnd(hwnd_edit: int) -> Optional[str]:
    """Полный текст по дескриптору Edit или Rich Edit (WM_GETTEXT / EM_GETTEXTEX)."""
    if not hwnd_edit:
        return None
    length = user32.SendMessageW(hwnd_edit, WM_GETTEXTLENGTH, 0, 0)
    if length is None or length <= 0:
        gt = _GETTEXTLENGTHEX(flags=GTL_DEFAULT, codepage=CP_UNICODE)
        length = user32.SendMessageW(hwnd_edit, EM_GETTEXTLENGTHEX, 0, ctypes.byref(gt))
        length = max(0, length) if length is not None and length >= 0 else 0
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(hwnd_edit, WM_GETTEXT, length + 1, ctypes.byref(buf))
    text = buf.value or ""
    if text:
        return text.replace("\r\n", "\n").replace("\r", "\n")
    n_bytes = (length + 1) * 2
    block_size = ctypes.sizeof(_GETTEXTEX) + n_bytes
    block = (ctypes.c_char * block_size)()
    gex = _GETTEXTEX.from_buffer(block)
    gex.cb = n_bytes
    gex.flags = GT_DEFAULT
    gex.codepage = CP_UNICODE
    gex.lpDefaultChar = None
    gex.lpUsedDefChar = None
    user32.SendMessageW(hwnd_edit, EM_GETTEXTEX, 0, ctypes.byref(block))
    raw = bytes(block[ctypes.sizeof(_GETTEXTEX) : ctypes.sizeof(_GETTEXTEX) + n_bytes])
    try:
        text = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
    except Exception:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def get_notepad_cursor() -> Optional[Tuple[int, int]]:
    """
    Позиция курсора в Блокноте (строка и колонка, 1-based), если активное окно —
    классический Блокнот с Edit-контролем. Иначе None.
    Работает только с notepad.exe (стандартный Win32 Edit); новый Notepad (UWP) не поддерживается.
    """
    return _get_notepad_cursor_from_edit_hwnd(_get_notepad_edit_hwnd())


def get_notepad_full_content() -> Optional[str]:
    """
    Полное содержимое окна Блокнота (весь текст), если активное окно —
    классический Блокнот с Edit-контролем. Иначе None. Переводы строк — \\n.
    """
    return _get_notepad_full_content_from_edit_hwnd(_get_notepad_edit_hwnd())


def get_notepad_cursor_any() -> Optional[Tuple[int, int]]:
    """
    Позиция курсора в любом открытом окне Блокнота (не обязательно в фокусе).
    Для отображения в GUI, когда фокус у окна приложения.
    """
    return _get_notepad_cursor_from_edit_hwnd(find_any_notepad_edit_hwnd())


def get_notepad_full_content_any() -> Optional[str]:
    """
    Полное содержимое любого открытого окна Блокнота (не обязательно в фокусе).
    """
    return _get_notepad_full_content_from_edit_hwnd(find_any_notepad_edit_hwnd())


# Названия типов для вывода в терминал
_TYPE_LABELS = {
    WindowType.IDE: "IDE",
    WindowType.BROWSER: "Браузер",
    WindowType.NOTEPAD: "Блокнот",
    WindowType.UNKNOWN: "Другое",
}


def get_active_window_display() -> str:
    """
    Одна строка для вывода в терминал: тип окна и заголовок.
    Пример: "IDE | Cursor - file.py" или "Браузер | Google Chrome"
    """
    info = get_active_window()
    label = _TYPE_LABELS.get(info.window_type, "Другое")
    title = (info.title or "(без заголовка)").strip()
    if not title:
        title = info.process_name or "(неизвестно)"
    return f"{label} | {title}"


# Экспорт для типов
__all__ = [
    "WindowType",
    "ActiveWindowInfo",
    "get_foreground_hwnd",
    "get_active_window",
    "get_active_window_type",
    "get_active_window_display",
    "is_cursor_in_ide",
    "is_cursor_in_browser",
    "is_cursor_in_notepad",
    "get_notepad_cursor",
    "get_notepad_full_content",
    "find_any_notepad_edit_hwnd",
    "get_notepad_cursor_any",
    "get_notepad_full_content_any",
]


if __name__ == "__main__":
    import argparse
    import time
    parser = argparse.ArgumentParser(description="Показать активное окно (куда попадёт ввод).")
    parser.add_argument(
        "-w", "--watch",
        action="store_true",
        help="Обновлять каждую секунду (Ctrl+C для выхода)",
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        metavar="SEC",
        help="Интервал обновления в секундах (при --watch), по умолчанию 1",
    )
    args = parser.parse_args()
    if args.watch:
        try:
            while True:
                line = get_active_window_display()
                print(f"\r  Активное окно: {line}   ", end="", flush=True)
                time.sleep(max(0.1, args.interval))
        except KeyboardInterrupt:
            print()
    else:
        print("Активное окно:", get_active_window_display())
