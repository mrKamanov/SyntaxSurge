@echo off
chcp 65001 >nul
echo Сборка SyntaxSurge через Miniconda...
echo.

where conda >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Ошибка: conda не найден. Установите Miniconda: https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)

if not exist ".conda-env-created" (
    echo Создание окружения syntaxsurge-build...
    conda env create -f environment.yml
    if %ERRORLEVEL% neq 0 (
        echo Ошибка создания окружения.
        exit /b 1
    )
    echo. > .conda-env-created
)

echo Сборка через conda run...
conda run -n syntaxsurge-build pyinstaller --clean SyntaxSurge.spec

if %ERRORLEVEL% equ 0 (
    echo.
    echo Готово. Exe: dist\SyntaxSurge.exe
    echo Запуск: dist\SyntaxSurge.exe
) else (
    echo Ошибка сборки.
    exit /b 1
)
