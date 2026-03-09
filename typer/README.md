# SyntaxSurge — умная печать кода

Программа анализирует исходный код, строит карту структуры и печатает его в целевое окно нелинейно: сначала скелет (сигнатуры, заглушки), затем заполнение блоков и вставка импортов. Поддерживается имитация человеческой скорости и ритма печати (задержки, усталость, биграммы, паузы).

Платформа: Windows (SendInput, Unicode).

---

## Структура проекта

```
SyntaxSurge/
  typer/           # Модуль печати
    __init__.py
    windows_typer.py   # Низкоуровневый ввод, конфиг, задержки
    code_mapper.py     # Разбор кода в карту
    code_printer.py    # Печать по карте (скелет, заполнение, импорты)
    active_window.py   # Определение активного окна: браузер / Блокнот / IDE
    cursor_bridge.py   # Мост для позиции курсора из браузера (общий для всех редакторов)
    editors/           # Поддержка веб-редакторов (каждый сайт — своя папка)
      hh_ru/           # HH.ru (Monaco) — userscript_hh_ru.user.js
      yandex_code/     # Yandex.Code (Ace) — userscript_yandex_code.user.js
    map/               # Каталог карт (JSON), внутри модуля
    log/               # Каталог логов печати, внутри модуля
  run.py           # Консольный запуск
  tests/           # Тестовые файлы
```

---

## Запуск

Из корня проекта:

```bash
python run.py <путь к файлу>
```

Примеры:

```bash
python run.py tests/test_snippet_a.py
python run.py my_script.py
```

Что происходит:

1. Создаётся карта кода и сохраняется в `typer/map/<имя_файла>_map.json`.
2. В консоли выводится обратный отсчёт; за это время нужно переключиться в окно редактора.
3. Код печатается по карте: скелет, заполнение блоков, вставка импортов.
4. Лог сессии записывается в `typer/log/typer_log.log`.

Каталоги `typer/map/` и `typer/log/` создаются автоматически при первом запуске.

**Поддерживаемые языки:** Python (`.py`), SQL (`.sql`), Markdown с блоками кода. Для SQL используется `SqlCodeMapBuilder` — последовательная печать без скелета.

### Где и когда показывается активное окно (куда курсор)

- **Куда выводит:** в тот же терминал, из которого запущен `run.py`.
- **Когда:** один раз в начале ШАГ 2 (ПЕЧАТЬ), сразу после заголовка «ШАГ 2: ПЕЧАТЬ» и перед обратным отсчётом. Строка вида:  
  `Куда попадёт печать (окно в фокусе сейчас): IDE | Cursor - file.py`  
  или `Браузер | Google Chrome`, `Блокнот | Untitled - Notepad`.

Чтобы видеть активное окно постоянно (обновление раз в секунду), в отдельном терминале запустите:
```bash
python -m typer.active_window --watch
```
Выход: Ctrl+C.

### Позиция курсора в браузере (HH.ru, Yandex.Code)

Редакторы на HH.ru (assessment) — Monaco; на Yandex.Code — Ace. Чтобы программа видела текущую позицию курсора (строка, столбец):

1. **Мост** — при запуске `run.py` или GUI автоматически поднимается локальный HTTP-сервер на порту 8765 (`typer.cursor_bridge`). Он принимает POST с `{line, column}` и отдаёт последнюю позицию по GET `/cursor`.

2. **Userscript** — установите Tampermonkey/Violentmonkey и добавьте скрипт:
   - HH.ru: `typer/editors/hh_ru/userscript_hh_ru.user.js` (Monaco)
   - Yandex.Code: `typer/editors/yandex_code/userscript_yandex_code.user.js` (Ace)
   Скрипт находит редактор и при движении курсора отправляет позицию на `http://127.0.0.1:8765/cursor`.

3. **Результат:** в GUI в блоке «Статус» отображаются позиция курсора (Ace: строка N, столбец M) и **содержимое текущей строки** (обновление раз в 400 мс). При старте печати в режиме браузера в консоль/GUI также выводится текущая позиция перед обратным отсчётом.
4. **Содержимое строки:** мост хранит последнюю полученную строку (`cursor_bridge.get_line_content()`). Её можно использовать в `code_printer` при печати в браузере: перед вводом сверять текущую строку из моста с ожидаемой (например, что мы на пустой строке или на строке с `pass`) и при расхождении корректировать позицию или пропускать шаг.

Файлы userscript: `typer/editors/hh_ru/` (HH.ru), `typer/editors/yandex_code/` (Yandex.Code). После установки откройте страницу с задачей и убедитесь, что в фокусе редактор кода — тогда позиция начнёт обновляться.

**Если позиция не видна — проверь по шагам:**

1. **Мост запущен?** Должно быть открыто окно GUI (`python gui_typer.py`) или запущен `run.py`. Без этого порт 8765 не слушает и браузер некуда слать позицию. Проверка: в браузере открой `http://127.0.0.1:8765/cursor` — должна открыться страница с JSON (`{"error":"no cursor yet"}` или `{"line":N,"column":M}`).
2. **Скрипт включён для этого сайта?** В Tampermonkey убедись, что скрипт включён и в списке совпадений есть твой URL (HH.ru: `https://assessment.hh.ru/*`, Yandex: `https://code.yandex-team.ru/*`).
3. **Редактор уже загружен?** Открой страницу с задачей, дождись загрузки редактора, кликни в область кода и подвигай курсор. Позиция уходит только когда скрипт находит редактор.
4. **Консоль (F12).** В userscript включён режим отладки. Открой F12 → Console. Должно появиться `[HH.ru→мост] Monaco Editor подключён` или `[Ace→мост] Загружен`. Если сообщений нет — скрипт не выполняется: проверь Tampermonkey (скрипт включён, URL в списке).
5. **Редактор во фрейме.** Если сообщение `[Ace→мост] Загружен` есть, но «Ace найден» не появляется при клике в редактор — редактор, скорее всего, в **iframe**. В консоли над списком сообщений есть выпадающий список контекста (часто «top»). Переключи его на другой фрейм (тот, где рисуется код) и обнови страницу: в логе для этого фрейма должно появиться `[Ace→мост] Загружен` и при клике в код — `Ace найден`. Tampermonkey по умолчанию запускает скрипт и во фреймах с тем же доменом; если фрейм с редактором другой — скрипт туда не попадёт.

### VS Code / Cursor (расширение SyntaxSurge Bridge)

Чтобы при печати в VS Code или Cursor программа получала позицию курсора и контекст строк (как в браузере), установи расширение **SyntaxSurge Bridge** из папки `vscode-extension/` в корне проекта.

1. Открой папку `vscode-extension` в VS Code/Cursor, выполни `npm install` и `npm run compile`.
2. Запусти расширение (F5) или собери `.vsix` (`vsce package`) и установи через «Install from VSIX».
3. Мост тот же (порт 8765). Расширение отправляет `source: "vscode"`; в GUI отображается «VS Code / Cursor», при печати в IDE с установленным расширением используется синхронизация по мосту (коррекция позиции по данным из редактора).

Подробнее: `vscode-extension/README.md`.

---

## Модуль typer

Публичный API:

```python
from typer import (
    CodeMapBuilder, CodePrinter, WindowsTyper, TypingConfig,
    MAP_DIR, LOG_DIR,
    get_active_window, get_active_window_type,
    is_cursor_in_ide, is_cursor_in_browser, is_cursor_in_notepad,
    ActiveWindowType, ActiveWindowInfo,
)
```

`MAP_DIR` и `LOG_DIR` — абсолютные пути к каталогам `typer/map/` и `typer/log/` (карты и логи хранятся внутри модуля).

### CodeMapBuilder

Строит карту кода из файла или строки.

- `build_from_file(filepath, language="python")` — возвращает `CodeMap`.
- `build_from_string(code, language="python")` — то же из строки.
- `save_map(code_map, filepath)` — сохраняет карту в JSON.

Для `.md` файлов код извлекается из первого блока ` ```python ` / ` ```py `.

### CodePrinter

Печатает код по загруженной карте.

- `__init__(base_speed=6.0, log_file=None)` — при `log_file=None` лог не ведётся.
- `load_map(map_file)` — загружает карту из JSON.
- `print_from_map(initial_delay=5, browser_mode=None)` — выполняет печать (обратный отсчёт в секундах).  
  `browser_mode`: `None` — автоопределение по активному окну (браузер/блокнот·IDE); `True` — принудительно режим браузера; `False` — режим блокнота/IDE.

План печати: скелет (шапка, константы, сигнатуры блоков с `pass` при необходимости), заполнение тел блоков, вставка импортов после шапки.

**Режим браузера** (Yandex.Code и др. веб-редакторы): определяется по активному окну или задаётся явно. В этом режиме при заполнении блоков строка «pass» удаляется 5 нажатиями Backspace (отступ — одним Backspace за уровень), а не посимвольно. Для блокнота/IDE поведение без изменений.

### WindowsTyper и TypingConfig

`WindowsTyper` — низкоуровневая печать символов и клавиш (Unicode, Enter, Backspace и т.д.) с учётом задержек. Используется внутри `CodePrinter`.

`TypingConfig` задаёт скорость, паузы, опечатки, усталость, биграммы, burst-паузы и прочие параметры. Передаётся в `WindowsTyper`; по умолчанию `CodePrinter` создаёт свой конфиг с отключёнными опечатками для стабильной скелетной печати.

### Определение активного окна (active_window)

Определяет, в каком приложении сейчас фокус ввода: браузер, Блокнот или IDE. Использует Windows API (GetForegroundWindow, GetWindowText, GetWindowThreadProcessId, QueryFullProcessImageName).

- `get_active_window()` — возвращает `ActiveWindowInfo`: тип окна (`window_type`: IDE / BROWSER / NOTEPAD / UNKNOWN), заголовок (`title`), имя процесса (`process_name`), путь к exe (`process_path`).
- `get_active_window_type()` — только тип: `ActiveWindowType.IDE`, `.BROWSER`, `.NOTEPAD` или `.UNKNOWN`.
- `is_cursor_in_ide()`, `is_cursor_in_browser()`, `is_cursor_in_notepad()` — булевы проверки.

Классификация по заголовку окна и имени процесса: IDE (VS Code, Cursor, PyCharm, JetBrains, Sublime, Notepad++ и т.д.), Блокнот (Notepad), браузер (Chrome, Edge, Firefox, Opera, Brave). При необходимости список маркеров можно расширить в `typer/active_window.py`.

- `get_active_window_display()` — одна строка для терминала, например: `"IDE | Cursor - file.py"` или `"Браузер | Google Chrome"`.

Показать в терминале, где сейчас курсор:
```bash
python -m typer.active_window           # один раз
python -m typer.active_window --watch   # обновлять каждую секунду (Ctrl+C — выход)
python -m typer.active_window -w -i 2  # обновлять раз в 2 секунды
```
При запуске `run.py` перед обратным отсчётом выводится строка «Активное окно: …».

Пример использования модуля без run.py:

```python
import os
from typer import CodeMapBuilder, CodePrinter, MAP_DIR, LOG_DIR

os.makedirs(MAP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

builder = CodeMapBuilder()
code_map = builder.build_from_file("script.py")
map_file = os.path.join(MAP_DIR, "script_map.json")
builder.save_map(code_map, map_file)

log_file = os.path.join(LOG_DIR, "session.log")
printer = CodePrinter(base_speed=5, log_file=log_file)
printer.load_map(map_file)
printer.print_from_map(initial_delay=5)
```

---

## Карты (typer/map/)

В каталоге `typer/map/` сохраняются JSON-карты с полями:

- `language`, `total_lines`, `total_chars`
- `header_lines` — число строк шапки (shebang, encoding)
- `imports`, `constants`, `classes`, `functions`, `main_block`
- `print_plan` — последовательность шагов печати (skeleton, заполнение, импорты)

Имя файла карты: `typer/map/<базовое_имя_исходника>_map.json`. Путь доступен через константу `MAP_DIR`.

---

## Логи (typer/log/)

В каталоге `typer/log/` записываются лог-файлы сессий печати:

- заголовок и время старта;
- блок «Текущее состояние» (позиция, последнее действие, счётчики);
- детальный лог действий (тип, сообщение, позиция).

Имя файла: `typer/log/typer_log_YYYYMMDD_HHMMSS.log`. Путь доступен через константу `LOG_DIR`. Если в `CodePrinter` передан `log_file=None`, запись в файл не выполняется.

---

## Требования

- Python 3.8+
- Windows (используется `ctypes` и `user32.SendInput`)

---

## Лицензия

По усмотрению правообладателя.
