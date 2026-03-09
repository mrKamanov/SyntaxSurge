#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Исключение окна из захвата экрана (трансляция) — Windows 10 2004+."""
import sys
import os

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

def _enumerate_process_windows(pid: int):
    """Перечислить HWND всех окон, принадлежащих процессу pid."""
    result = []
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
        )

        @WNDENUMPROC
        def enum_cb(hwnd, lparam):
            if not user32.IsWindow(hwnd):
                return True
            wpid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value != pid:
                return True
            result.append(int(hwnd))
            return True

        user32.EnumWindows(enum_cb, 0)
    except Exception:
        pass
    return result


def apply_tooltip_windows_exclude_from_capture(exclude: bool):
    """Скрыть/вернуть от захвата все окна процесса (подсказки, выпадающие списки и т.д.)."""
    if sys.platform != "win32":
        return
    try:
        pid = os.getpid()
        for hwnd in _enumerate_process_windows(pid):
            try:
                if exclude:
                    set_window_exclude_from_capture(hwnd)
                else:
                    set_window_include_in_capture(hwnd)
            except Exception:
                pass
    except Exception:
        pass


def set_window_exclude_from_capture(hwnd: int) -> bool:
    """Окно видно на экране, но не попадает в захват/трансляцию (Windows 10 2004+)."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        SetWindowDisplayAffinity = user32.SetWindowDisplayAffinity
        SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        SetWindowDisplayAffinity.restype = wintypes.BOOL
        return bool(SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


def set_window_include_in_capture(hwnd: int) -> bool:
    """Вернуть окно в захват экрана (отменить исключение)."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        WDA_NONE = 0
        SetWindowDisplayAffinity = user32.SetWindowDisplayAffinity
        SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        SetWindowDisplayAffinity.restype = wintypes.BOOL
        return bool(SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_NONE))
    except Exception:
        return False
