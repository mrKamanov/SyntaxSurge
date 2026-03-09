@echo off
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
    echo Сначала выполните: setup_venv.bat
    exit /b 1
)
.venv\Scripts\python.exe run_gui.py
