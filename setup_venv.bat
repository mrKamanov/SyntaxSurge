@echo off
chcp 65001 >nul
echo Создание виртуального окружения для SyntaxSurge...
echo.

if exist ".venv\Scripts\activate.bat" (
    echo Окружение .venv уже существует. Обновление зависимостей...
    call .venv\Scripts\activate.bat
    pip install -r requirements_install.txt
    echo.
    echo Запуск: run.bat или python run_gui.py
    exit /b 0
)

python -m venv .venv
if %ERRORLEVEL% neq 0 (
    echo Ошибка создания venv. Убедитесь, что python в PATH.
    exit /b 1
)

call .venv\Scripts\activate.bat
pip install -r requirements_install.txt

if %ERRORLEVEL% equ 0 (
    echo.
    echo Готово. Окружение: .venv
    echo Активация: .venv\Scripts\activate
    echo Запуск: python run_gui.py
) else (
    echo Ошибка установки зависимостей.
    exit /b 1
)
