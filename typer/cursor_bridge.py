#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мост для позиции курсора Ace Editor в браузере (Yandex.Code и др.).
Локальный HTTP-сервер принимает POST с {line, column} от userscript,
отдаёт GET /cursor для проверки нашей навигации.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Tuple, NamedTuple
from urllib.parse import urlparse


class CursorContext(NamedTuple):
    """Позиция курсора (1-based), три строки контекста и тип файла из редактора."""
    line: int
    column: int
    line_above: str
    line_content: str
    line_below: str
    language_id: str = ""
    file_extension: str = ""


# Последняя известная позиция: (line, column), 1-based; None если не получена
_cursor: Optional[Tuple[int, int]] = None
# Текст текущей строки и соседних (из Ace / Monaco)
_line_content: Optional[str] = None
_line_above: Optional[str] = None
_line_below: Optional[str] = None
# Источник последнего POST: "yandex" | "vscode" | None (для подписи в GUI)
_source: Optional[str] = None
# Опционально: время отправки от клиента (для теста задержки моста)
_sent_at: Optional[float] = None
# Язык и расширение файла (из VS Code: languageId, .py / .md и т.д.)
_language_id: str = ""
_file_extension: str = ""
# Полное содержимое редактора (из Yandex Ace: при каждом движении курсора). Для позиционирования и сравнения.
_full_content: Optional[str] = None
_lock = threading.Lock()

# Порт по умолчанию (можно задать через CURSOR_BRIDGE_PORT)
DEFAULT_PORT = 8765
# Отладка: вывод в консоль при получении POST (для gui_typer — смотри терминал)
_DEBUG = True


class _CursorHandler(BaseHTTPRequestHandler):
    """Обработчик: POST /cursor — сохранить, GET /cursor — вернуть позицию. CORS для браузера."""

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/cursor":
            with _lock:
                if _cursor is not None or _source is not None:
                    line = _cursor[0] if _cursor is not None else 0
                    col = _cursor[1] if _cursor is not None else 0
                    out = {
                        "line": line,
                        "column": col,
                        "line_content": _line_content if _line_content is not None else "",
                        "line_above": _line_above if _line_above is not None else "",
                        "line_below": _line_below if _line_below is not None else "",
                        "source": _source if _source is not None else "",
                        "language_id": _language_id,
                        "file_extension": _file_extension,
                    }
                    if _sent_at is not None:
                        out["sent_at"] = _sent_at
                    self._send_json(out)
                else:
                    self._send_json({"error": "no cursor yet"}, 404)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/cursor":
            self.send_response(404)
            self.end_headers()
            return
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "no body"}, 400)
            return
        try:
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            line = int(data.get("line", 0))
            column = int(data.get("column", 0))
            def _str(v):
                return str(v) if v is not None and not isinstance(v, str) else (v if isinstance(v, str) else None)
            line_content = _str(data.get("lineContent") or data.get("line_content"))
            line_above = _str(data.get("lineAbove") or data.get("line_above"))
            line_below = _str(data.get("lineBelow") or data.get("line_below"))
            source = _str(data.get("source")) or None
            if source is not None and source.strip() == "":
                source = None
            sent_at = data.get("sent_at")
            if sent_at is not None:
                try:
                    sent_at = float(sent_at)
                except (TypeError, ValueError):
                    sent_at = None
            language_id = _str(data.get("languageId") or data.get("language_id")) or ""
            file_extension = _str(data.get("fileExtension") or data.get("file_extension")) or ""
            full_content = _str(data.get("fullContent") or data.get("full_content"))
            with _lock:
                global _cursor, _line_content, _line_above, _line_below, _source, _sent_at, _language_id, _file_extension, _full_content
                _cursor = (line, column)
                _line_content = line_content
                _line_above = line_above
                _line_below = line_below
                _source = source
                _sent_at = sent_at
                _language_id = language_id if isinstance(language_id, str) else ""
                _file_extension = file_extension if isinstance(file_extension, str) else ""
                _full_content = full_content if isinstance(full_content, str) else None
            if _DEBUG:
                print(f"[cursor_bridge] POST от {source or '?'}: строка {line}, столб {column}, lineContent={repr((line_content or '')[:40])}...")
            self._send_json({"ok": True, "line": line, "column": column})
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def log_message(self, format, *args):
        pass  # отключаем лог каждого запроса


_server: Optional[HTTPServer] = None
_thread: Optional[threading.Thread] = None


def start(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> bool:
    """Запускает мост в фоновом потоке. Возвращает True при успехе."""
    global _server, _thread
    with _lock:
        if _server is not None:
            return True
    try:
        _server = HTTPServer((host, port), _CursorHandler)
        _thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _thread.start()
        return True
    except Exception:
        return False


def stop():
    """Останавливает мост."""
    global _server, _thread
    if _server is not None:
        _server.shutdown()
        _server = None
    _thread = None


def get_cursor() -> Optional[Tuple[int, int]]:
    """Возвращает последнюю позицию (line, column), 1-based, или None."""
    with _lock:
        return _cursor


def get_line_content() -> Optional[str]:
    """Возвращает текст текущей строки (из Ace), или None."""
    with _lock:
        return _line_content


def get_line_above() -> Optional[str]:
    """Возвращает текст строки выше курсора, или None."""
    with _lock:
        return _line_above


def get_line_below() -> Optional[str]:
    """Возвращает текст строки ниже курсора, или None."""
    with _lock:
        return _line_below


def get_three_lines() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Возвращает (строка_выше, текущая_строка, строка_ниже)."""
    with _lock:
        return (_line_above, _line_content, _line_below)


def get_source() -> Optional[str]:
    """Возвращает источник последнего POST: 'yandex', 'vscode' или None."""
    with _lock:
        return _source


def get_language_id() -> str:
    """Язык файла в редакторе (VS Code: python, markdown и т.д.)."""
    with _lock:
        return _language_id


def get_file_extension() -> str:
    """Расширение файла в редакторе (например .py, .md)."""
    with _lock:
        return _file_extension


def get_document_content() -> Optional[str]:
    """Полное содержимое редактора (из Yandex Ace при движении курсора). None если не передавалось (VS Code и др.)."""
    with _lock:
        return _full_content


def get_cursor_context() -> Optional[CursorContext]:
    """Атомарно возвращает позицию, три строки контекста и тип файла из моста (одним lock)."""
    with _lock:
        if _cursor is None:
            return None
        return CursorContext(
            line=_cursor[0],
            column=_cursor[1],
            line_above=_line_above if _line_above is not None else "",
            line_content=_line_content if _line_content is not None else "",
            line_below=_line_below if _line_below is not None else "",
            language_id=_language_id,
            file_extension=_file_extension,
        )


def get_cursor_via_http(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> Optional[Tuple[int, int]]:
    """Запрашивает позицию по HTTP (если мост запущен). Для проверки из другого процесса."""
    try:
        import urllib.request
        req = urllib.request.Request(f"http://{host}:{port}/cursor")
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data["line"], data["column"])
    except Exception:
        return None


__all__ = [
    "CursorContext",
    "DEFAULT_PORT",
    "start",
    "stop",
    "get_cursor",
    "get_line_content",
    "get_line_above",
    "get_line_below",
    "get_three_lines",
    "get_cursor_context",
    "get_document_content",
    "get_source",
    "get_language_id",
    "get_file_extension",
    "get_cursor_via_http",
]
