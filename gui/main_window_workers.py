# -*- coding: utf-8 -*-
"""Воркеры для главного окна: API-запросы, OCR, подсказки, код-ревью, печать."""

import os
import sys
import threading

from PySide6.QtCore import QObject, Signal

try:
    from api_client import chat_completion, chat_completion_with_image
except ImportError:
    chat_completion = None
    chat_completion_with_image = None

try:
    from typer import (
        CodeMapBuilder,
        CodePrinter,
        TyperAborted,
        SqlCodeMapBuilder,
        detect_from_content,
        MAP_DIR,
        LOG_DIR,
        LOG_FILE,
    )
    _typer_available = True
except ImportError:
    _typer_available = False
    detect_from_content = None
    SqlCodeMapBuilder = None
    TyperAborted = Exception
    MAP_DIR = ""
    LOG_DIR = ""
    LOG_FILE = ""


def _normalize_content_key(s: str, max_len: int = 50) -> str:
    """Нормализация начала строки кода для поиска подсказки по содержимому."""
    t = " ".join(s.strip().split())[:max_len].strip()
    return t


def _parse_block_tips(text: str) -> dict:
    """Парсит ответ API: подсказки по номерам строк, по началу строки и по блокам."""
    tips = {}
    block_name = None
    tip_lines = []
    line_index = None
    current_line_num = None
    current_content = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("BLOCK:"):
            if block_name is not None and tip_lines:
                key = f"{block_name.strip()}:{line_index}" if line_index is not None else block_name.strip()
                tips[key] = " ".join(tip_lines).strip()
            if current_line_num is not None and tip_lines:
                tip_text = " ".join(tip_lines).strip()
                tips[str(current_line_num)] = tip_text
                if current_content is not None:
                    tips["content:" + _normalize_content_key(current_content)] = tip_text
            block_name = stripped[6:].strip()
            tip_lines = []
            line_index = None
            current_line_num = None
            current_content = None
        elif stripped.upper().startswith("LINE:"):
            if block_name is not None and tip_lines:
                key = f"{block_name.strip()}:{line_index}" if line_index is not None else block_name.strip()
                tips[key] = " ".join(tip_lines).strip()
            if current_line_num is not None and tip_lines:
                tip_text = " ".join(tip_lines).strip()
                tips[str(current_line_num)] = tip_text
                if current_content is not None:
                    tips["content:" + _normalize_content_key(current_content)] = tip_text
            rest = stripped[5:].strip()
            try:
                num = int(rest.split()[0])
                if num >= 1 and num <= 10000:
                    current_line_num = num
                    block_name = None
                    line_index = None
                else:
                    line_index = num
                    current_line_num = None
            except (ValueError, IndexError):
                line_index = len([k for k in tips if block_name and k.startswith(block_name + ":")]) if block_name else 0
                current_line_num = None
            tip_lines = []
            current_content = None
        elif stripped.upper().startswith("CONTENT:"):
            current_content = stripped[8:].strip()
        elif stripped.upper().startswith("TIP:"):
            tip_lines.append(stripped[4:].strip())
        elif stripped:
            tip_lines.append(stripped)
    if block_name is not None and tip_lines:
        key = f"{block_name.strip()}:{line_index}" if line_index is not None else block_name.strip()
        tips[key] = " ".join(tip_lines).strip()
    if current_line_num is not None and tip_lines:
        tip_text = " ".join(tip_lines).strip()
        tips[str(current_line_num)] = tip_text
        if current_content is not None:
            tips["content:" + _normalize_content_key(current_content)] = tip_text
    return tips


def pip_install_rapidocr_command() -> str:
    """Команда установки rapidocr для копирования в терминал (PowerShell на Windows — с &)."""
    exe = sys.executable
    if os.name == "nt":
        return f'& "{exe}" -m pip install rapidocr onnxruntime'
    return f'"{exe}" -m pip install rapidocr onnxruntime'


CODE_REVIEW_PROMPT = """Ты — опытный разработчик (уровень сеньора). Проведи код-ревью приведённого ниже кода.

Структура ответа (обязательно соблюдай):

## 1. Общая оценка
Кратко (2–4 предложения): что делает код, насколько он корректен, читаем и поддерживаем. Общая оценка по шкале «принять с правками / принять / нужна доработка».

## 2. Сильные стороны
Список того, что сделано хорошо (архитектура, именование, разбиение на функции и т.д.).

## 3. Замечания и риски
Конкретные проблемы: баги, уязвимости, плохая читаемость, нарушение стиля (PEP 8 и т.п.), дублирование, магические числа. Для каждого замечания укажи фрагмент или номер строки, если применимо.

## 4. Рекомендации
Что улучшить в первую очередь: типизация, обработка ошибок, тесты, разбиение на модули и т.д.

## 5. Варианты кода
Для 1–3 мест, где есть смысл показать альтернативу, приведи короткий вариант «как можно лучше». Каждый вариант — в отдельном блоке кода с подписью, например:

**Вариант: обработка ввода**
```python
# твой вариант кода
```

**Вариант: структура функции X**
```python
# твой вариант
```

Пиши на том же языке, что и код (если код на русском в комментариях — ответ на русском). Код в блоках ``` оставляй с подсветкой синтаксиса (указывай язык после ```). Будь конкретным и полезным, без воды.

Код для ревью:
```
"""


class ApiRequestWorker(QObject):
    """Воркер: запрос к API в отдельном потоке."""
    finished = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, model: str, auth_type: str, user_message: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.auth_type = auth_type
        self.user_message = user_message

    def run(self):
        if not chat_completion:
            self.finished.emit(False, "Модуль api_client не найден. Установите openai: pip install openai")
            return
        messages = [{"role": "user", "content": self.user_message}]
        success, text = chat_completion(
            self.base_url, self.api_key, self.model, self.auth_type, messages
        )
        self.finished.emit(success, text)


class ScreenshotSendWorker(QObject):
    """Воркер: отправка скриншота (изображение + промпт) в API с vision."""
    finished = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, model: str, auth_type: str, prompt_text: str, image_base64: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.auth_type = auth_type
        self.prompt_text = prompt_text
        self.image_base64 = image_base64

    def run(self):
        if not chat_completion_with_image:
            self.finished.emit(False, "Модуль api_client не найден или не поддерживает отправку изображений. Установите openai: pip install openai")
            return
        success, text = chat_completion_with_image(
            self.base_url, self.api_key, self.model, self.auth_type,
            self.prompt_text, self.image_base64, "image/png"
        )
        self.finished.emit(success, text)


class OCRWorker(QObject):
    """Воркер: распознавание текста через RapidOCR (русский + английский)."""
    finished = Signal(bool, str)

    def __init__(self, image_path: str):
        super().__init__()
        self._image_path = image_path

    def _extract_text(self, result) -> str:
        if result is None:
            return ""
        txts = getattr(result, "txts", None)
        if txts is not None:
            return "\n".join(t.strip() for t in txts if t and str(t).strip())
        if isinstance(result, (list, tuple)) and len(result) >= 1:
            data = result[0]
            if data is None:
                return ""
            if isinstance(data, (list, tuple)):
                parts = [str(item[1]).strip() for item in data if isinstance(item, (list, tuple)) and len(item) >= 2]
                return "\n".join(p for p in parts if p)
            if hasattr(data, "txts") and data.txts:
                return "\n".join(t.strip() for t in data.txts if t and str(t).strip())
        if isinstance(result, (list, tuple)) and result:
            parts = [str(item[1]).strip() for item in result if isinstance(item, (list, tuple)) and len(item) >= 2]
            return "\n".join(p for p in parts if p)
        return ""

    def run(self):
        try:
            from rapidocr import RapidOCR, LangRec  # type: ignore[import-untyped]
        except ImportError as e:
            self.finished.emit(False, "Установите RapidOCR для распознавания текста:\npip install rapidocr onnxruntime\n\n" + str(e))
            return
        try:
            try:
                engine = RapidOCR(params={"Rec.lang_type": LangRec.CYRILLIC})
            except Exception:
                engine = RapidOCR()
            if not os.path.isfile(self._image_path):
                self.finished.emit(False, "Временный файл изображения не найден.")
                return
            result = engine(self._image_path)
            text = self._extract_text(result)
            self.finished.emit(True, text or "(Текст не распознан)")
        except BaseException as e:
            self.finished.emit(False, f"Ошибка OCR: {type(e).__name__}: {e}")


class TipsRequestWorker(QObject):
    """Воркер: запрос к API за подсказками по блокам кода."""
    finished = Signal(dict)

    def __init__(self, base_url: str, api_key: str, model: str, auth_type: str, code: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.auth_type = auth_type
        self.code = code

    def run(self):
        if not chat_completion:
            self.finished.emit({})
            return
        prompt = """Проанализируй код и выдай подсказки в двух частях. В коде каждая строка помечена номером слева (1|, 2|, …) — это номера строк исходного файла. В ответе для строк используй ИМЕННО эти номера в LINE: N.

ЧАСТЬ 1 — описание блоков (класс, функция, if __name__). Для каждого блока:
BLOCK: имя_блока
TIP: в одном предложении — что делает этот блок (класс/функция/точка входа), зачем нужен

ЧАСТЬ 2 — подсказки только для непустых строк. Пустые строки не указывай. Номер LINE — из пометки слева (N|) в коде. CONTENT — начало строки для точного сопоставления (до 50 символов, без ведущих пробелов):
LINE: номер_строки
CONTENT: начало строки из кода
TIP: коротко, что делает эта строка

Включи: импорты, константы, декораторы, def/class, каждую значимую строку внутри тел. LINE: N строго по номерам из кода.

Код (номера строк слева):
```
"""
        code_snippet = self.code[:12000]
        code_lines = code_snippet.split("\n")
        numbered = [f"{i + 1}| {line}" for i, line in enumerate(code_lines)]
        prompt += "\n".join(numbered)
        prompt += "\n```"
        messages = [{"role": "user", "content": prompt}]
        success, text = chat_completion(
            self.base_url, self.api_key, self.model, self.auth_type, messages, max_tokens=4096
        )
        tips = _parse_block_tips(text) if success else {}
        self.finished.emit(tips)


class CodeReviewWorker(QObject):
    """Воркер: отправка кода в API для код-ревью."""
    finished = Signal(bool, str)

    def __init__(self, base_url: str, api_key: str, model: str, auth_type: str, code: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.auth_type = auth_type
        self.code = code

    def run(self):
        if not chat_completion:
            self.finished.emit(False, "Модуль api_client не найден.")
            return
        prompt = CODE_REVIEW_PROMPT + self.code[:14000] + "\n```"
        messages = [{"role": "user", "content": prompt}]
        success, text = chat_completion(
            self.base_url, self.api_key, self.model, self.auth_type, messages, max_tokens=8192
        )
        self.finished.emit(success, text or "Пустой ответ от API.")


class TyperWorker(QObject):
    """Воркер: печать кода из ответа в активное окно."""
    finished = Signal()
    block_changed = Signal(str, str)
    body_line_changed = Signal(str, int, str)
    line_changed = Signal(int, str)

    def __init__(self, response_text: str, initial_delay: int = 5, base_speed: float = 6.0, pause_event: threading.Event = None, paused_now: list = None, abort_event: threading.Event = None):
        super().__init__()
        self.response_text = response_text
        self.initial_delay = initial_delay
        self.base_speed = base_speed
        self.pause_event = pause_event
        self.paused_now = paused_now
        self.abort_event = abort_event

    def run(self):
        if not _typer_available:
            self.finished.emit()
            return
        try:
            # 1. Определить язык по содержимому
            lang = detect_from_content(self.response_text) if detect_from_content else "python"
            os.makedirs(MAP_DIR, exist_ok=True)
            os.makedirs(LOG_DIR, exist_ok=True)
            map_file = os.path.join(MAP_DIR, "gui_response_map.json")
            log_file = LOG_FILE

            # 2. Использовать маппер для этого языка
            if lang == "sql":
                builder = SqlCodeMapBuilder()
                code_map_data = builder.build_from_string(self.response_text)
                builder.save_map(code_map_data, map_file)
            else:
                builder = CodeMapBuilder()
                code_map = builder.build_from_string(self.response_text, language="python")
                builder.save_map(code_map, map_file)
            on_block = lambda name, btype: self.block_changed.emit(name, btype)
            on_body_line = lambda name, idx, content: self.body_line_changed.emit(name, idx, content)
            on_line = lambda src_line, content: self.line_changed.emit(src_line, content)
            printer = CodePrinter(base_speed=self.base_speed, log_file=log_file, pause_event=self.pause_event, paused_now=self.paused_now, abort_event=self.abort_event, on_block_start=on_block, on_body_line_start=on_body_line, on_line_start=on_line)
            printer.load_map(map_file)
            printer.print_from_map(initial_delay=self.initial_delay, browser_mode=None)
        except TyperAborted:
            pass
        except Exception:
            pass
        self.finished.emit()
