# SyntaxSurge

**SyntaxSurge** — десктопное приложение для умной печати кода с AI-помощником. Поддерживает Python, SQL, скриншоты, OCR и голосовой ввод.

Платформа: **Windows** (SendInput, Unicode).

---

## Возможности

| Функция | Описание |
|---------|----------|
| **Печать кода** | Анализ кода → карта структуры → печать в редактор (скелет, затем заполнение) |
| **AI-ответы** | Запросы к OpenAI-совместимым API (OpenRouter, OpenAI, Gemini, Ollama и др.) |
| **Скриншот → код** | Захват экрана + OCR + AI: задание с собеседования → готовый код |
| **Помощник** | Голосовой ввод (sherpa-onnx) + диалог по ролям → краткие ответы |
| **Код-ревью** | Отправка кода в API → ревью уровня сеньора |
| **Подсказки** | При печати — построчные подсказки от AI (кэшируются) |

---

## Быстрый старт

### Установка

```bash
git clone <repo>
cd SyntaxSurge
pip install -r requirements.txt
```

### Запуск

```bash
# Главное окно (полный функционал)
python run_gui.py

# Или напрямую
python gui/main_window.py

# Облегчённый интерфейс (только печать из файла)
python gui_typer.py

# Консольный режим
python run.py tests/1.py
```

---

## Печать в редакторы

SyntaxSurge печатает в активное окно. Поддерживаются:

| Цель | Требование |
|------|------------|
| **VS Code / Cursor** | Расширение [SyntaxSurge Bridge](vscode-extension/README.md) |
| **PyCharm** | Плагин [SyntaxSurge](pycharm-plugin/README.md) |
| **HH.ru** (assessment, тесты) | Userscript [HH.ru](typer/editors/hh_ru/README.md) |
| **Yandex.Code** | Userscript [Yandex.Code](typer/editors/yandex_code/) |
| **Блокнот** | Без доп. настроек |

Мост курсора: `http://127.0.0.1:8765/cursor` — запускается автоматически при старте приложения.

---

## Структура проекта

```
SyntaxSurge/
├── gui/                 # Главное окно (PySide6)
│   ├── main_window.py   # Точка входа
│   └── ...
├── typer/               # Модуль печати кода
│   ├── editors/         # Userscripts для веб-редакторов
│   │   ├── hh_ru/      # HH.ru (Monaco)
│   │   └── yandex_code/ # Yandex.Code (Ace)
│   ├── map/            # Карты печати (JSON)
│   └── log/            # Логи сессий
├── vscode-extension/   # Расширение для VS Code/Cursor
├── pycharm-plugin/     # Плагин для PyCharm
├── run_gui.py          # Запуск главного окна
├── gui_typer.py        # Облегчённый интерфейс
├── run.py              # Консольный запуск
└── requirements.txt
```

---

## Документация

- [Установка и настройка](docs/INSTALL.md)
- [Руководство пользователя](docs/USAGE.md)
- [Настройка API](docs/API.md)
- [Печать кода (typer)](typer/README.md)
- [HH.ru userscript](typer/editors/hh_ru/README.md)
- [VS Code расширение](vscode-extension/README.md)
- [PyCharm плагин](pycharm-plugin/README.md)

---

## Требования

- Python 3.8+
- Windows
- См. [requirements.txt](requirements.txt)

---

## Лицензия

По усмотрению правообладателя.
