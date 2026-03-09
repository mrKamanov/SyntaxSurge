# -*- coding: utf-8 -*-
"""
Цель печати: PyCharm с плагином (мост).
Синхронизация по мосту. В PyCharm 1 Backspace = 1 символ (не 4 пробела как в VS Code),
поэтому для перехода в начало строки всегда используем Home, не Backspace — иначе удалится часть текста (например «ss» у pass).
"""

import time
from . import cursor_bridge
from .print_common import (
    VK_UP, VK_DOWN, VK_HOME, VK_END, VK_DELETE, VK_ESCAPE,
    looks_like_new_line, context_matches,
)

MAX_BACKSPACE_LEVELS = 4
MAX_INDENT_COLUMN = 12
BRIDGE_WAIT_AFTER_ENTER_SEC = 0.15
BRIDGE_WAIT_RECHECK_SEC = 0.12
BRIDGE_WAIT_EXTRA_FOR_PYTHON_SEC = 0.08
# Ожидание ответа моста при переходе на новую строку (PyCharm может отдавать с задержкой)
BRIDGE_WAIT_FOR_NEW_LINE_SEC = 0.18
BRIDGE_WAIT_FOR_NEW_LINE_MAX_ROUNDS = 12  # ~2.2 сек макс


def backspaces_for_pass(indent: int) -> int:
    """PyCharm: 1 Backspace = 4 пробела, для 'pass' — 4 Backspace. Строка: (indent+4) пробелов + 'pass'.
    Итого: (indent+4)//4 для пробелов + 4 для 'pass'. При 4 пробелах → 1+4=5; при 8 пробелах → 2+4=6."""
    spaces_before_pass = indent + 4
    return (spaces_before_pass // 4) + 4


class PyCharmPrintTarget:
    """Адаптер целевой среды: PyCharm с плагином SyntaxSurge Bridge (мост)."""

    def use_bridge_sync(self, printer) -> bool:
        return True

    def is_browser_mode(self, printer) -> bool:
        return False

    def is_editor_file_python(self, printer) -> bool:
        ext = (cursor_bridge.get_file_extension() or "").lower()
        lid = (cursor_bridge.get_language_id() or "").lower()
        return ext == ".py" or lid == "python"

    def should_dismiss_ide_popup(self, printer) -> bool:
        ext = (cursor_bridge.get_file_extension() or "").lower()
        lid = (cursor_bridge.get_language_id() or "").lower()
        return ext in (".py", ".sql") or lid in ("python", "sql")

    def backspaces_for_pass(self, printer, indent: int) -> int:
        return backspaces_for_pass(indent)

    def ensure_start_of_line_after_newline(self, printer):
        """После Enter переводим курсор в начало строки. Дожидаемся ответа моста о новой строке, затем только Home."""
        time.sleep(BRIDGE_WAIT_AFTER_ENTER_SEC)
        if self.is_editor_file_python(printer):
            time.sleep(BRIDGE_WAIT_EXTRA_FOR_PYTHON_SEC)
        # Ожидание: мост должен показать новую строку (курсор уже на следующей строке, контент пустой/пробелы)
        expected_new_line = printer.current_line + 1
        ctx = None
        for _ in range(BRIDGE_WAIT_FOR_NEW_LINE_MAX_ROUNDS):
            ctx = cursor_bridge.get_cursor_context()
            if ctx is not None and ctx.line == expected_new_line and looks_like_new_line(ctx.line_content):
                printer.current_line = ctx.line
                printer.current_column = ctx.column - 1
                break
            # Если мост вернул предыдущую строку (pass, def...) — лаг, ждём обновления
            if ctx is not None:
                line_stripped = (ctx.line_content or "").strip()
                if line_stripped and ("pass" in line_stripped or line_stripped.startswith("def ") or line_stripped.startswith("class ")):
                    time.sleep(BRIDGE_WAIT_FOR_NEW_LINE_SEC)
                    continue
            time.sleep(BRIDGE_WAIT_FOR_NEW_LINE_SEC)
        # Если за цикл не получили контекст новой строки — берём последний только если мост уже на новой строке
        if ctx is not None and printer.current_line != expected_new_line:
            if ctx.line >= expected_new_line and looks_like_new_line(ctx.line_content):
                printer.current_line = ctx.line
                printer.current_column = ctx.column - 1
        # Всегда только Home: в PyCharm Backspace = 1 символ
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)
        printer.current_column = 0
        time.sleep(0.10)

    def backspace_to_column_one(self, printer, current_col_1based: int):
        """В PyCharm всегда Home: Backspace удаляет по 1 символу."""
        if current_col_1based <= 1:
            return
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)
        printer.current_column = 0

    def align_cursor_after_newline_for_pass(self, printer, expected_line: int, max_rounds: int = 8):
        """Дожидаемся, пока мост покажет ожидаемую строку (после Enter от сигнатуры)."""
        expected_col = 1
        for _ in range(max_rounds):
            time.sleep(0.52)  # даём мосту время обновиться после Enter
            ctx = cursor_bridge.get_cursor_context()
            if ctx is None:
                continue
            if ctx.line == expected_line and ctx.column == expected_col:
                printer.current_line = ctx.line
                printer.current_column = ctx.column - 1
                return
            if ctx.line == expected_line and ctx.column != expected_col:
                time.sleep(0.35)
                ctx2 = cursor_bridge.get_cursor_context()
                if ctx2 and ctx2.line == expected_line and ctx2.column == expected_col:
                    printer.current_line = ctx2.line
                    printer.current_column = ctx2.column - 1
                    return
                # В PyCharm всегда Home (Backspace = 1 символ)
                printer.typer._send_virtual_key(VK_HOME, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_HOME, key_up=True)
                time.sleep(0.04)
                printer.current_column = 0
                time.sleep(0.40)
                continue
            if ctx.line < expected_line:
                printer.typer._send_virtual_key(VK_DOWN, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_DOWN, key_up=True)
                time.sleep(0.35)
                continue
            if ctx.line > expected_line:
                printer.typer._send_virtual_key(VK_UP, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_UP, key_up=True)
                time.sleep(0.35)
                continue
        ctx = cursor_bridge.get_cursor_context()
        if ctx:
            printer.current_line = ctx.line
            printer.current_column = ctx.column - 1

    def get_cursor_from_bridge(self, printer, retries: int = 4, sleep_sec: float = 0.18):
        for _ in range(retries):
            time.sleep(sleep_sec)
            pos = cursor_bridge.get_cursor()
            if pos is not None:
                return pos
        return None

    def get_context_from_bridge(self, printer, retries=None, sleep_sec=None):
        r = retries if retries is not None else 4
        s = sleep_sec if sleep_sec is not None else 0.18
        for _ in range(r):
            time.sleep(s)
            ctx = cursor_bridge.get_cursor_context()
            if ctx is not None:
                return ctx
        return None

    def update_position_from_bridge(self, printer, retries: int = 5, sleep_sec: float = 0.22):
        for attempt in range(retries):
            time.sleep(sleep_sec)
            ctx = cursor_bridge.get_cursor_context()
            if ctx is not None:
                printer.current_line = ctx.line
                printer.current_column = ctx.column - 1
                return

    def sync_from_bridge_then_home(self, printer, expected_line_above: str = None):
        ctx = self.get_context_from_bridge(printer, retries=3, sleep_sec=0.12)
        if ctx is None:
            return
        printer.current_line = ctx.line
        printer.current_column = ctx.column - 1
        if expected_line_above and expected_line_above.strip():
            if (ctx.line_above or "").strip() != expected_line_above.strip():
                time.sleep(0.15)
                ctx2 = cursor_bridge.get_cursor_context()
                if ctx2:
                    ctx = ctx2
                    printer.current_line = ctx.line
                    printer.current_column = ctx.column - 1
        if printer.current_column > 0:
            printer.typer._send_virtual_key(VK_HOME, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_HOME, key_up=True)
            time.sleep(0.04)
            printer.current_column = 0

    def clear_line_if_accumulated_whitespace(self, printer, min_len: int = 4):
        """Очищаем строку только если на ней реально есть заметный отступ (9+ пробелов).
        На пустой строке или при 4/8 пробелах не трогаем: мост может ошибаться, а Delete на пустой
        строке тянет следующую и стирает 'def ' у сигнатуры."""
        ctx = self.get_context_from_bridge(printer, retries=2, sleep_sec=0.08)
        if ctx is None or not ctx.line_content:
            return
        content = ctx.line_content
        if content.strip() != "":
            return
        # Не очищаем короткий «пустой» отступ: пустая строка или 4/8 пробелов (типичная пустая строка между блоками)
        if len(content) <= 8:
            return
        n = len(content)
        for _ in range(n):
            printer.typer._send_virtual_key(VK_DELETE, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DELETE, key_up=True)
            time.sleep(0.02)
        printer.current_column = 0

    def fix_prev_line_indent_if_needed(self, printer, expected_prev_line: str):
        if not expected_prev_line or not expected_prev_line.strip():
            return
        ctx = self.get_context_from_bridge(printer, retries=2, sleep_sec=0.08)
        if ctx is None or not ctx.line_above:
            return
        actual = ctx.line_above
        expected = expected_prev_line
        if actual.strip() != expected.strip():
            return
        expected_indent = len(expected) - len(expected.lstrip())
        actual_indent = len(actual) - len(actual.lstrip())
        if actual_indent == expected_indent:
            return
        line_before_up = ctx.line
        printer.typer._send_virtual_key(VK_UP, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_UP, key_up=True)
        time.sleep(0.08)
        # Проверяем, что Up сработал: при лаге моста курсор может остаться на той же строке — тогда не печатаем пробелы
        ctx_after = cursor_bridge.get_cursor_context()
        if ctx_after is not None and ctx_after.line >= line_before_up:
            time.sleep(0.06)
            printer.typer._send_virtual_key(VK_DOWN, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DOWN, key_up=True)
            time.sleep(0.04)
            return
        printer.current_line -= 1
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.02)
        printer.current_column = 0
        if actual_indent > expected_indent:
            for _ in range(actual_indent - expected_indent):
                printer.typer._send_virtual_key(VK_DELETE, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_DELETE, key_up=True)
                time.sleep(0.02)
        else:
            printer.typer.type_line(" " * (expected_indent - actual_indent), add_newline=False)
            printer.current_column = expected_indent
        printer.typer._send_virtual_key(VK_DOWN, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_DOWN, key_up=True)
        time.sleep(0.04)
        printer.current_line += 1
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        printer.current_column = 0
        printer._log_action("FIX_INDENT", f"Исправлен отступ: было {actual_indent}, стало {expected_indent}")

    def ensure_on_correct_line_before_fill(self, printer, body_line: str, prev_line: str = None):
        if prev_line is not None and prev_line.strip() == "}":
            time.sleep(0.06)
            printer.typer._send_virtual_key(VK_DOWN, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DOWN, key_up=True)
            time.sleep(0.04)
            printer.current_line += 1
            printer.typer._send_virtual_key(VK_HOME, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_HOME, key_up=True)
            time.sleep(0.04)
            printer.current_column = 0
            printer._log_action("FILL_LINE_SKIP_DOWN", "После '}' — переход вниз")
            return
        ctx = self.get_context_from_bridge(printer, retries=2, sleep_sec=0.08)
        if ctx is None or not ctx.line_content:
            return
        current = (ctx.line_content or "").strip()
        expected = (body_line or "").strip()
        if not current or current == expected:
            return
        printer.typer._send_virtual_key(VK_DOWN, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_DOWN, key_up=True)
        time.sleep(0.04)
        printer.current_line += 1
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)
        printer.current_column = 0
        printer._log_action("FILL_LINE_SKIP_DOWN", "Текущая строка не совпадает — переход вниз")

    def ensure_cursor_synced(
        self,
        printer,
        expected_line_content: str = None,
        expected_line_above: str = None,
        expected_line_below: str = None,
    ):
        self.sync_cursor_from_bridge(
            printer,
            expected_line_content=expected_line_content,
            expected_line_above=expected_line_above,
            expected_line_below=expected_line_below,
        )

    def verify_on_pass_line_from_bridge(
        self, printer, pass_line_content: str, expected_signature_above: str = None
    ) -> bool:
        time.sleep(0.25)
        ctx = self.get_context_from_bridge(printer)
        if ctx is None:
            return False
        actual = (ctx.line_content or "").strip()
        expected_pass = pass_line_content.strip()
        if actual != expected_pass:
            return False
        if expected_signature_above and expected_signature_above.strip():
            if (ctx.line_above or "").strip() != expected_signature_above.strip():
                return False
        return True

    def refresh_bridge_position(self, printer):
        """Пауза перед проверкой по мосту."""
        time.sleep(0.2)

    def refresh_bridge_then_verify_on_pass(
        self, printer, pass_line_content: str, expected_signature_above: str = None
    ) -> bool:
        """Обновить мост, проверить: на строке pass и строка выше = сигнатура."""
        self.refresh_bridge_position(printer)
        return self.verify_on_pass_line_from_bridge(printer, pass_line_content, expected_signature_above)

    def navigate_to_pass_line_for_fill(
        self,
        printer,
        block_name: str,
        pass_line_content: str,
        expected_signature_above: str,
        current_pass_line: int,
        current_start: int,
        original_start: int,
        original_end: int,
    ) -> bool:
        printer.current_line = current_pass_line
        printer.current_column = 0
        self.ensure_cursor_synced(
            printer,
            expected_line_content=pass_line_content,
            expected_line_above=expected_signature_above,
        )
        on_pass = self.verify_on_pass_line_from_bridge(printer, pass_line_content, expected_signature_above)
        if not on_pass:
            time.sleep(0.45)
            printer.typer._send_virtual_key(VK_DOWN, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DOWN, key_up=True)
            time.sleep(0.5)
            on_pass = self.verify_on_pass_line_from_bridge(printer, pass_line_content, expected_signature_above)
            if on_pass:
                pos = cursor_bridge.get_cursor()
                if pos:
                    printer.current_line = pos[0]
                printer._log_action("FILL_FIX", f"После сдвига вниз контекст совпал, строка {printer.current_line}")
            else:
                printer.typer._send_virtual_key(VK_UP, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_UP, key_up=True)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_UP, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_UP, key_up=True)
                time.sleep(0.5)
                on_pass = self.verify_on_pass_line_from_bridge(printer, pass_line_content, expected_signature_above)
                if on_pass:
                    pos = cursor_bridge.get_cursor()
                    if pos:
                        printer.current_line = pos[0]
                    printer._log_action("FILL_FIX", f"После сдвига вверх контекст совпал, строка {printer.current_line}")
        if not on_pass:
            found = printer._search_pass_line_by_blocks(
                block_name=block_name,
                pass_line_content=pass_line_content,
                expected_signature_above=expected_signature_above,
                current_pass_line=current_pass_line,
            )
            return found
        return True

    def do_cursor_correction(
        self,
        printer,
        actual_line: int,
        actual_col: int,
        expected_line: int,
        expected_col_1based: int,
    ):
        if actual_line < expected_line:
            for _ in range(expected_line - actual_line):
                printer.typer._send_virtual_key(VK_DOWN, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_DOWN, key_up=True)
                time.sleep(0.04)
        elif actual_line > expected_line:
            for _ in range(actual_line - expected_line):
                printer.typer._send_virtual_key(VK_UP, key_up=False)
                time.sleep(0.02)
                printer.typer._send_virtual_key(VK_UP, key_up=True)
                time.sleep(0.04)
        time.sleep(0.06)
        if expected_col_1based <= 1:
            self.backspace_to_column_one(printer, actual_col)
        else:
            printer.typer._send_virtual_key(VK_HOME, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_HOME, key_up=True)
            time.sleep(0.03)
            for _ in range(expected_col_1based - 1):
                from .print_common import VK_RIGHT
                printer.typer._send_virtual_key(VK_RIGHT, key_up=False)
                time.sleep(0.01)
                printer.typer._send_virtual_key(VK_RIGHT, key_up=True)
                time.sleep(0.02)

    def sync_cursor_from_bridge(
        self,
        printer,
        expected_line_content: str = None,
        expected_line_above: str = None,
        expected_line_below: str = None,
        max_verify_rounds: int = 3,
    ):
        if not getattr(printer, '_browser_sync_first_done', True):
            time.sleep(0.25)
            printer._browser_sync_first_done = True
        expected_line = printer.current_line
        expected_col_1based = printer.current_column + 1
        for round_no in range(max_verify_rounds):
            ctx = self.get_context_from_bridge(printer)
            if ctx is None:
                time.sleep(0.35)
                ctx = cursor_bridge.get_cursor_context()
            if ctx is None:
                printer._log_action("CURSOR_SYNC", "Контекст из моста недоступен")
                return
            if self.is_editor_file_python(printer) and ctx.line < expected_line and (ctx.line_content or "").strip():
                for _ in range(2):
                    time.sleep(0.22)
                    ctx2 = self.get_context_from_bridge(printer)
                    if ctx2 and ctx2.line >= expected_line:
                        ctx = ctx2
                        break
                    if ctx2:
                        ctx = ctx2
                if context_matches(ctx, expected_line, expected_col_1based,
                                  expected_line_content=expected_line_content,
                                  expected_line_above=expected_line_above,
                                  expected_line_below=expected_line_below):
                    return
            if context_matches(ctx, expected_line, expected_col_1based,
                             expected_line_content=expected_line_content,
                             expected_line_above=expected_line_above,
                             expected_line_below=expected_line_below):
                if round_no > 0:
                    printer._log_action("CURSOR_SYNC_DONE", f"Строка {ctx.line}, колонка {ctx.column}")
                return
            printer._log_action("CURSOR_SYNC", f"Расхождение (раунд {round_no + 1}): мост {ctx.line}:{ctx.column}")
            self.do_cursor_correction(printer, ctx.line, ctx.column, expected_line, expected_col_1based)
            time.sleep(0.45)
        for _ in range(8):
            ctx2 = cursor_bridge.get_cursor_context()
            if ctx2:
                printer.current_line = ctx2.line
                printer.current_column = ctx2.column - 1
                printer._log_action("CURSOR_SYNC_DONE", f"Строка {printer.current_line}, колонка {printer.current_column}")
                break
            time.sleep(0.18)

    def wait_for_bridge_position(self, printer, max_wait_sec: float = 2.8) -> bool:
        deadline = time.monotonic() + max_wait_sec
        while time.monotonic() < deadline:
            pos = self.get_cursor_from_bridge(printer, retries=3, sleep_sec=0.15)
            if pos is not None:
                printer._log_action("CURSOR_SYNC", f"Мост готов, позиция: {pos[0]}:{pos[1]}")
                return True
            time.sleep(0.25)
        printer._log_action("CURSOR_SYNC", "Позиция из моста недоступна после ожидания")
        return False

    def body_line_after_type_open_brace(self, printer, r: str, body_line: str):
        # Как в VS Code: 1× Delete, для .py Escape, затем Enter
        printer.typer._send_virtual_key(VK_DELETE, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_DELETE, key_up=True)
        time.sleep(0.02)
        if self.is_editor_file_python(printer):
            printer.typer._send_virtual_key(VK_ESCAPE, key_up=False)
            time.sleep(0.03)
            printer.typer._send_virtual_key(VK_ESCAPE, key_up=True)
            time.sleep(0.05)
        printer.typer.press_enter()

    def remove_docstring_auto_close_after_type(self, printer, line_to_type: str):
        """PyCharm при вводе открывающих кавычек сразу вставляет закрывающие. Удаляем лишние: Delete."""
        r = line_to_type.rstrip()
        deletes = 0
        if '"""' in line_to_type:
            deletes += 3
        if "'''" in line_to_type:
            deletes += 3
        if r.endswith('"') and line_to_type.count('"') % 2 == 1:
            deletes += 1
        if r.endswith("'") and line_to_type.count("'") % 2 == 1:
            deletes += 1
        for _ in range(deletes):
            printer.typer._send_virtual_key(VK_DELETE, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DELETE, key_up=True)
            time.sleep(0.02)

    def before_fill_line_verify(
        self, printer, expected_line: int, body_start_line: int, idx: int, prev_line: str, block: dict
    ) -> bool:
        return True

    def after_fill_line_delay(self, printer):
        time.sleep(0.10)
        if self.is_editor_file_python(printer):
            time.sleep(0.05)
