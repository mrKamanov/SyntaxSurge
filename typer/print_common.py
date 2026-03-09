# -*- coding: utf-8 -*-
"""
Общая логика печати: константы и чистые хелперы, используемые всеми целями (Яндекс, VS Code, блокнот).
"""

# Виртуальные коды клавиш Windows
VK_UP = 0x26
VK_DOWN = 0x28
VK_END = 0x23
VK_HOME = 0x24
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_ESCAPE = 0x1B
VK_LEFT = 0x25
VK_RIGHT = 0x27

# Длина строки «новая строка» из моста (пустая или только пробелы)
MAX_NEW_LINE_CONTENT_LEN = 12


def looks_like_new_line(line_content: str, max_len: int = MAX_NEW_LINE_CONTENT_LEN) -> bool:
    """По содержимому строки из моста: пустая или только пробелы/табы и не длинная — считаем новую строку после Enter."""
    if line_content is None:
        return False
    s = line_content.strip()
    if s:
        return False
    return len(line_content) <= max_len


def context_matches(
    ctx,
    expected_line: int,
    expected_col_1based: int,
    expected_line_content: str = None,
    expected_line_above: str = None,
    expected_line_below: str = None,
) -> bool:
    """Проверяет: позиция и опционально текущая строка, строка выше, строка ниже."""
    if ctx is None:
        return False
    if ctx.line != expected_line or ctx.column != expected_col_1based:
        return False
    if expected_line_content is not None:
        if (ctx.line_content or "").strip() != expected_line_content.strip():
            return False
    if expected_line_above is not None:
        if (ctx.line_above or "").strip() != expected_line_above.strip():
            return False
    if expected_line_below is not None:
        if (ctx.line_below or "").strip() != expected_line_below.strip():
            return False
    return True


def is_block_start_line(line: str) -> bool:
    """Строка — начало блока (class/def/async def)."""
    s = (line or "").strip()
    return s.startswith("class ") or s.startswith("def ") or s.startswith("async def ")


def analyze_position_for_pass_search(ctx, pass_line_content: str, signature: str) -> str:
    """
    По контексту моста определяем, где мы относительно искомой строки с pass.
    Возвращает: "found", "on_signature", "other_block", "unknown".
    """
    if ctx is None:
        return "unknown"
    content = (ctx.line_content or "").strip()
    above = (ctx.line_above or "").strip()
    sig = (signature or "").strip()
    if not sig:
        if content == (pass_line_content or "").strip():
            return "found"
        if is_block_start_line(content):
            return "other_block"
        return "unknown"
    if content == (pass_line_content or "").strip() and above == sig:
        return "found"
    if content == sig:
        return "on_signature"
    if is_block_start_line(content):
        return "other_block"
    return "unknown"
