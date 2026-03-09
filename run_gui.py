#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Запуск графического интерфейса SyntaxSurge (окно в стиле glass). Запускайте из корня проекта: python run_gui.py"""

import sys
import os

# В frozen-режиме (exe): sys._MEIPASS в PATH для sounddevice (PortAudio DLL и зависимости)
if getattr(sys, "frozen", False) and sys.platform == "win32":
    _path = os.environ.get("PATH", "")
    _path = _path.split(os.pathsep) if _path else []
    _meipass = sys._MEIPASS
    if _meipass not in _path:
        _path.insert(0, _meipass)
    _pa_bin = os.path.join(_meipass, "_sounddevice_data", "portaudio-binaries")
    if os.path.isdir(_pa_bin) and _pa_bin not in _path:
        _path.insert(0, _pa_bin)
    os.environ["PATH"] = os.pathsep.join(_path)

if __name__ == "__main__":
    # В frozen-режиме (exe) OCR-субпроцесс вызывается как: SyntaxSurge.exe -m gui.ocr_subprocess <path>
    if getattr(sys, "frozen", False) and len(sys.argv) >= 4 and sys.argv[1] == "-m" and sys.argv[2] == "gui.ocr_subprocess":
        sys.argv = [sys.argv[0], sys.argv[3]]  # ocr_subprocess.main() ожидает path в argv[1]
        from gui.ocr_subprocess import main as ocr_main
        ocr_main()
    else:
        from gui.main_window import main
        main()
