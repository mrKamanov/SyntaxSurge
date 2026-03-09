#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Удаление markdown-ограничителей кода (```) и подсветка синтаксиса для области ответа ИИ.
"""
import re
from typing import Tuple, Optional, List

from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import QRegularExpression


def _is_code_fence(line: str) -> bool:
    """Строка — открывающий или закрывающий забор кода (``` или ''' или ```python и т.д.)."""
    s = line.strip()
    if s.startswith("```"):
        return len(s) == 3 or s[3:4].isspace() or s[3:4].isalpha()
    if s.startswith("'''"):
        return len(s) == 3 or s[3:4].isspace() or s[3:4].isalpha()
    return False


def normalize_assistant_answer(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """
    Нормализует ответ помощника: объединяет одиночные маркеры со следующей строкой,
    убирает лишние пустые строки, удаляет строки-заборы кода (```python, ```).
    Возвращает (текст, список диапазонов строк кода (start, end) для подсветки синтаксиса).
    """
    code_ranges: List[Tuple[int, int]] = []
    if not text or not text.strip():
        return (text, code_ranges)
    lines = text.split("\n")
    result = []
    i = 0
    bullet_chars = ("*", "-", "•")
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Забор кода: не выводим, запоминаем диапазон строк кода
        if _is_code_fence(line):
            if not result or (code_ranges and result[-1].strip() != ""):
                pass  # открывающий ```
            start_line = len(result)
            i += 1
            while i < len(lines) and not _is_code_fence(lines[i]):
                result.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # пропустить закрывающий ```
            end_line = len(result) - 1
            if end_line >= start_line:
                code_ranges.append((start_line, end_line))
            continue
        # Строка — только маркер списка
        if stripped in bullet_chars and len(stripped) <= 2:
            if i + 1 < len(lines) and lines[i + 1].strip():
                result.append("• " + lines[i + 1].strip())
                i += 2
                continue
        result.append(line)
        i += 1
    # Убрать подряд идущие пустые строки и пересчитать индексы блоков кода
    out = []
    old_to_new: List[int] = []
    prev_empty = False
    for idx, line in enumerate(result):
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        out.append(line)
        old_to_new.append(idx)
        prev_empty = is_empty
    new_ranges: List[Tuple[int, int]] = []
    for (a, b) in code_ranges:
        new_start = next((i for i, old in enumerate(old_to_new) if old >= a), None)
        new_end = next((i for i in range(len(old_to_new) - 1, -1, -1) if old_to_new[i] <= b), None)
        if new_start is not None and new_end is not None and new_start <= new_end:
            new_ranges.append((new_start, new_end))
    return ("\n".join(out).strip(), new_ranges)


def strip_code_fences(text: str) -> Tuple[str, Optional[str]]:
    """
    Убирает обёртку ```lang и ``` из текста. Возвращает (очищенный_текст, язык или None).
    """
    if not text or not text.strip():
        return (text, None)
    text = text.strip()
    lang = None
    # Открывающий забор: ```python или ``` или ```py
    if text.startswith("```"):
        first_line, _, rest = text.partition("\n")
        lang_part = first_line[3:].strip().lower()
        if lang_part:
            lang = lang_part.split()[0]  # "python" из "python something"
        if rest.rstrip().endswith("```"):
            rest = rest[: rest.rstrip().rfind("```")].strip()
        return (rest.strip(), lang)
    return (text, None)


# Цвета в стиле тёмной темы (читаемо на тёмном фоне)
class PythonHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса Python для QPlainTextEdit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._formats = {}
        # Ключевые слова
        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor("#FF79C6"))  # розовый
        kw_format.setFontWeight(QFont.Weight.Bold)
        self._formats["keyword"] = kw_format
        # Строки
        str_format = QTextCharFormat()
        str_format.setForeground(QColor("#F1FA8C"))  # жёлто-зелёный
        self._formats["string"] = str_format
        # Комментарии
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6272A4"))  # приглушённый
        comment_format.setFontItalic(True)
        self._formats["comment"] = comment_format
        # Числа
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#BD93F9"))  # фиолетовый
        self._formats["number"] = number_format
        # Имена функций
        func_format = QTextCharFormat()
        func_format.setForeground(QColor("#50FA7B"))  # зелёный
        self._formats["function"] = func_format
        # Дефолт (операторы и т.д.) — без отдельного формата

        keywords = (
            "and as assert async await break class continue def del elif else "
            "except False finally for from global if import in is lambda None "
            "nonlocal not or pass raise return True try while with yield"
        ).split()
        self._keyword_pattern = QRegularExpression(
            "\\b(" + "|".join(re.escape(k) for k in keywords) + ")\\b"
        )
        self._string_single = QRegularExpression("'(?:[^'\\\\]|\\\\.)*'")
        self._string_double = QRegularExpression('"(?:[^"\\\\]|\\\\.)*"')
        self._string_triple = QRegularExpression('"""[^"]*"""|\'\'\'[^\']*\'\'\'')
        self._comment = QRegularExpression("#[^\n]*")
        self._number = QRegularExpression("\\b[0-9]+\\.?[0-9]*\\b")
        self._function = QRegularExpression("\\b([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?=\\()")

    def highlightBlock(self, text: str):
        if not text:
            return
        # Тройные строки (в начале блока)
        it = self._string_triple.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._formats["string"])
        # Обычные строки
        for pattern in (self._string_double, self._string_single):
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), self._formats["string"])
        # Комментарии
        it = self._comment.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._formats["comment"])
        # Ключевые слова
        it = self._keyword_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._formats["keyword"])
        # Числа
        it = self._number.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._formats["number"])
        # Вызовы функций (имя перед скобкой)
        it = self._function.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._formats["function"])


class AssistantTranscriptHighlighter(QSyntaxHighlighter):
    """Подсветка ролей в диалоге: «Вы» и «Собеседник» разными цветами."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fmt_user = QTextCharFormat()
        self._fmt_user.setForeground(QColor("#4FC3F7"))  # светло-голубой
        self._fmt_user.setFontWeight(QFont.Weight.Bold)
        self._fmt_interlocutor = QTextCharFormat()
        self._fmt_interlocutor.setForeground(QColor("#FFB74D"))  # янтарный
        self._fmt_interlocutor.setFontWeight(QFont.Weight.Bold)
        self._pat_user = QRegularExpression("^Вы:\\s*")
        self._pat_interlocutor = QRegularExpression("^Собеседник:\\s*")

    def highlightBlock(self, text: str):
        if not text.strip():
            return
        m = self._pat_user.match(text)
        if m.hasMatch():
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt_user)
            return
        m = self._pat_interlocutor.match(text)
        if m.hasMatch():
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt_interlocutor)


class AssistantAnswerHighlighter(QSyntaxHighlighter):
    """Подсветка ответа помощника: заголовки, списки, код (без отображения ```)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._code_block_ranges: List[Tuple[int, int]] = []
        # Заголовки (# ## ###)
        self._fmt_header = QTextCharFormat()
        self._fmt_header.setForeground(QColor("#8BE9FD"))
        self._fmt_header.setFontWeight(QFont.Weight.Bold)
        # Нумерованный список (1. 2. 1) 2))
        self._fmt_numbered = QTextCharFormat()
        self._fmt_numbered.setForeground(QColor("#50FA7B"))
        # Маркированный список (- * •)
        self._fmt_bullet = QTextCharFormat()
        self._fmt_bullet.setForeground(QColor("#FFB86C"))
        # Подпись-метка **Задача:** **Ответ:** — выделяем цветом как у заголовков
        self._fmt_label = QTextCharFormat()
        self._fmt_label.setForeground(QColor("#8BE9FD"))
        self._fmt_label.setFontWeight(QFont.Weight.Bold)
        # Жирный **текст** (остальной жирный не-метка)
        self._fmt_bold = QTextCharFormat()
        self._fmt_bold.setFontWeight(QFont.Weight.Bold)
        self._fmt_bold.setForeground(QColor("#F8F8F2"))
        # Инлайн-код `код`
        self._fmt_code = QTextCharFormat()
        self._fmt_code.setForeground(QColor("#50FA7B"))
        self._pat_header = QRegularExpression("^#{1,6}\\s+.+")
        self._pat_numbered = QRegularExpression("^\\s*(\\d+[.)])\\s+")
        self._pat_bullet = QRegularExpression("^\\s*[-*•]\\s+")
        self._pat_label = QRegularExpression("\\*\\*[^*]+:\\s*\\*\\*")
        self._pat_bold = QRegularExpression("\\*\\*[^*]+\\*\\*")
        self._pat_code = QRegularExpression("`[^`]+`")
        # Форматы для блоков кода (Python-подсветка)
        self._py_kw = QTextCharFormat()
        self._py_kw.setForeground(QColor("#FF79C6"))
        self._py_kw.setFontWeight(QFont.Weight.Bold)
        self._py_str = QTextCharFormat()
        self._py_str.setForeground(QColor("#F1FA8C"))
        self._py_comment = QTextCharFormat()
        self._py_comment.setForeground(QColor("#6272A4"))
        self._py_comment.setFontItalic(True)
        self._py_num = QTextCharFormat()
        self._py_num.setForeground(QColor("#BD93F9"))
        self._py_func = QTextCharFormat()
        self._py_func.setForeground(QColor("#50FA7B"))
        _kw = "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield"
        self._py_keyword_re = QRegularExpression("\\b(" + "|".join(re.escape(w) for w in _kw.split()) + ")\\b")
        self._py_str_s = QRegularExpression("'(?:[^'\\\\]|\\\\.)*'")
        self._py_str_d = QRegularExpression('"(?:[^"\\\\]|\\\\.)*"')
        self._py_comment_re = QRegularExpression("#[^\n]*")
        self._py_number_re = QRegularExpression("\\b[0-9]+\\.?[0-9]*\\b")
        self._py_func_re = QRegularExpression("\\b([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?=\\()")

    def set_code_block_ranges(self, ranges: List[Tuple[int, int]]) -> None:
        """Диапазоны строк (start, end) включительно — блоки кода с подсветкой синтаксиса."""
        self._code_block_ranges = list(ranges)

    def _highlight_python_block(self, text: str) -> None:
        """Подсветка одной строки как Python."""
        for pattern, fmt in (
            (self._py_str_d, self._py_str),
            (self._py_str_s, self._py_str),
            (self._py_comment_re, self._py_comment),
            (self._py_keyword_re, self._py_kw),
            (self._py_number_re, self._py_num),
            (self._py_func_re, self._py_func),
        ):
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

    def highlightBlock(self, text: str):
        if not text.strip():
            return
        block_num = self.currentBlock().blockNumber()
        in_code = any(start <= block_num <= end for start, end in self._code_block_ranges)
        if in_code:
            self._highlight_python_block(text)
            return
        # Заголовки
        m = self._pat_header.match(text)
        if m.hasMatch():
            self.setFormat(0, len(text), self._fmt_header)
            return
        # Нумерованный список
        m = self._pat_numbered.match(text)
        if m.hasMatch():
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self._fmt_numbered)
        # Маркированный список
        m = self._pat_bullet.match(text)
        if m.hasMatch():
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt_bullet)
        # Жирный **...** в строке
        it = self._pat_bold.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt_bold)
        # Подписи **Задача:** **Ответ:** — поверх жирного акцентный цвет (как заголовки)
        it = self._pat_label.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt_label)
        # Инлайн-код `...`
        it = self._pat_code.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt_code)


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# Подсветка кода для любых языков (Pygments) или только Python (встроенная)
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
    from pygments.util import ClassNotFound

    _PYGMENTS_AVAILABLE = True
    _CODE_FORMATTER = HtmlFormatter(
        noclasses=True,
        style="monokai",
        full=False,
        cssstyles="margin:0;",
    )
except ImportError:
    _PYGMENTS_AVAILABLE = False
    ClassNotFound = Exception  # noqa: F811

# Алиасы языков для Pygments (```sql -> SqlLexer, ```js -> JavaScriptLexer)
_LEXER_ALIASES = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "bash": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "yaml": "yaml",
    "md": "markdown",
    "rb": "ruby",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "kt": "kotlin",
    "c": "c",
    "cpp": "cpp",
    "h": "c",
    "cs": "csharp",
    "php": "php",
    "r": "r",
    "swift": "swift",
    "scala": "scala",
    "sql": "sql",
    "html": "html",
    "xml": "xml",
    "css": "css",
    "scss": "scss",
    "json": "json",
}


_CODE_BLOCK_PRE_STYLE = (
    "background:rgba(40,42,54,0.95);color:#f8f8f2;padding:10px;"
    "border-radius:6px;border:1px solid rgba(255,184,108,0.3);"
    "overflow:auto;font-family:Consolas,monospace;font-size:12px;margin:8px 0;"
)


def _code_block_to_html(code: str, lang: str) -> str:
    """
    Подсветка блока кода для любого языка. Если установлен Pygments — используем его
    (Python, SQL, JS, HTML, и т.д.). Иначе — только встроенная подсветка для Python.
    """
    lang = (lang or "").strip().lower()
    lexer_name = _LEXER_ALIASES.get(lang, lang) if lang else None

    if _PYGMENTS_AVAILABLE and lexer_name:
        try:
            lexer = get_lexer_by_name(lexer_name, stripall=True)
            inner = highlight(code, lexer, _CODE_FORMATTER)
            return f'<div style="{_CODE_BLOCK_PRE_STYLE}">{inner}</div>'
        except ClassNotFound:
            pass
    if _PYGMENTS_AVAILABLE and not lexer_name:
        try:
            lexer = guess_lexer(code)
            inner = highlight(code, lexer, _CODE_FORMATTER)
            return f'<div style="{_CODE_BLOCK_PRE_STYLE}">{inner}</div>'
        except Exception:
            pass

    if lang in ("python", "py"):
        code_html = _python_code_to_html(code)
    else:
        code_html = _escape_html(code).replace("\n", "<br>\n")
    return (
        f'<pre style="{_CODE_BLOCK_PRE_STYLE}">'
        f"{code_html}"
        "</pre>"
    )


# Цвета подсветки Python (как у PythonHighlighter) для HTML
_PY_KW_COLOR = "#FF79C6"
_PY_STR_COLOR = "#F1FA8C"
_PY_COMMENT_COLOR = "#6272A4"
_PY_NUMBER_COLOR = "#BD93F9"
_PY_FUNC_COLOR = "#50FA7B"


def _python_code_to_html(code: str) -> str:
    """Преобразует исходный код Python в HTML с подсветкой синтаксиса (те же цвета, что у PythonHighlighter)."""
    import re as re_mod
    lines = code.split("\n")
    keywords = set(
        "and as assert async await break class continue def del elif else "
        "except False finally for from global if import in is lambda None "
        "nonlocal not or pass raise return True try while with yield".split()
    )
    kw_re = re_mod.compile(r"\b(" + "|".join(re_mod.escape(k) for k in keywords) + r")\b")
    str_single = re_mod.compile(r"'(?:[^'\\]|\\.)*'")
    str_double = re_mod.compile(r'"(?:[^"\\]|\\.)*"')
    str_triple = re_mod.compile(r'"""[^"]*"""|\'\'\'[^\']*\'\'\'')
    comment_re = re_mod.compile(r"#[^\n]*")
    number_re = re_mod.compile(r"\b[0-9]+\.?[0-9]*\b")
    func_re = re_mod.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?=\()")

    def highlight_line(line: str) -> str:
        out: List[Tuple[int, int, str]] = []  # (start, end, color)
        # Тройные строки
        for m in str_triple.finditer(line):
            out.append((m.start(), m.end(), _PY_STR_COLOR))
        for m in str_double.finditer(line):
            out.append((m.start(), m.end(), _PY_STR_COLOR))
        for m in str_single.finditer(line):
            out.append((m.start(), m.end(), _PY_STR_COLOR))
        for m in comment_re.finditer(line):
            out.append((m.start(), m.end(), _PY_COMMENT_COLOR))
        for m in kw_re.finditer(line):
            out.append((m.start(), m.end(), _PY_KW_COLOR))
        for m in number_re.finditer(line):
            out.append((m.start(), m.end(), _PY_NUMBER_COLOR))
        for m in func_re.finditer(line):
            out.append((m.start(), m.end(), _PY_FUNC_COLOR))
        out.sort(key=lambda x: (x[0], -x[1]))
        # Merge overlapping: keep first (smaller start wins)
        merged: List[Tuple[int, int, str]] = []
        for start, end, color in out:
            if merged and start < merged[-1][1]:
                continue
            merged.append((start, end, color))
        # Build string with spans
        result = []
        pos = 0
        for start, end, color in merged:
            if start > pos:
                result.append(_escape_html(line[pos:start]))
            result.append(f'<span style="color:{color}">{_escape_html(line[start:end])}</span>')
            pos = end
        if pos < len(line):
            result.append(_escape_html(line[pos:]))
        return "".join(result)

    html_lines = [highlight_line(ln) for ln in lines]
    return "<br>\n".join(html_lines)


def response_to_html(text: str) -> str:
    """
    Конвертирует ответ API в HTML с подсветкой: если есть блоки ```lang — как markdown с подсветкой;
    иначе весь текст считается одним блоком кода, язык определяется автоматически (Pygments guess_lexer).
    Используется для области «Ответ ИИ» (поддержка Python, SQL, JS и других языков).
    """
    if not text or not text.strip():
        return ""
    if "```" in text:
        return markdown_review_to_html(text)
    return _code_block_to_html(text.strip(), "")


def markdown_review_to_html(md: str) -> str:
    """
    Конвертирует markdown-ревью в HTML: заголовки, жирный, списки и блоки кода с подсветкой синтаксиса.
    Блоки ```python / ```py заменяются на HTML с подсветкой Python; остальные ```...``` — на <pre><code>.
    """
    if not md or not md.strip():
        return ""
    # Ищем все блоки ```lang\n...\n```
    pattern = re.compile(r"^```(\w*)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
    result = []
    last_end = 0
    for m in pattern.finditer(md):
        result.append(_md_simple_to_html(md[last_end : m.start()]))
        lang = (m.group(1) or "").strip()
        code_block = m.group(2).rstrip()
        result.append(_code_block_to_html(code_block, lang))
        last_end = m.end()
    result.append(_md_simple_to_html(md[last_end:]))
    return "".join(result)


def _md_simple_to_html(md: str) -> str:
    """Минимальная конвертация markdown в HTML: ##, ###, **, списки -, переносы."""
    if not md:
        return ""

    def line_to_html(line: str) -> str:
        # Жирный **...** в любом месте строки
        parts = re.split(r"(\*\*[^*]+\*\*)", line)
        buf = []
        for p in parts:
            if p.startswith("**") and p.endswith("**") and len(p) > 4:
                buf.append(f"<b style='color:#FFB86C;'>{_escape_html(p[2:-2])}</b>")
            else:
                buf.append(_escape_html(p))
        return "".join(buf)

    lines = md.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("## "):
            out.append(f"<h2 style='color:#E8E8E8;margin:12px 0 6px 0;'>{_escape_html(s[3:])}</h2>")
        elif s.startswith("### "):
            out.append(f"<h3 style='color:#E0E0E0;margin:10px 0 4px 0;font-size:14px;'>{_escape_html(s[4:])}</h3>")
        elif s.startswith("- ") or s.startswith("* "):
            out.append(f"<li style='margin:2px 0;'>{line_to_html(s[2:])}</li>")
        else:
            out.append(line_to_html(line) + "<br>")
    return "\n".join(out)
