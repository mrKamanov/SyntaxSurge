# -*- coding: utf-8 -*-
"""
Яндекс (Yandex.Code, Ace Editor) — база для логики печати.
Разработка с нуля: только мост (позиция, контекст, полный документ) и отправка клавиш.
Логику позиционирования, проверок и заполнения блоков будем добавлять по шагам.
"""

import time
from . import cursor_bridge
from .print_common import (
    VK_UP, VK_DOWN, VK_HOME, VK_END, VK_DELETE, VK_ESCAPE,
)

# --- Данные из моста (userscript шлёт при движении курсора) ---
# cursor_bridge.get_cursor()       → (line, column) 1-based
# cursor_bridge.get_cursor_context() → line, column, line_above, line_content, line_below
# cursor_bridge.get_document_content() → полный текст файла (только при source=yandex)
# cursor_bridge.get_source()       → "yandex" | "vscode" | None


def _find_pass_line_in_document(
    full_content: str,
    expected_signature_above: str,
    pass_line_content: str,
) -> int | None:
    """По полному документу из моста находит номер строки (1-based) с pass после сигнатуры.
    Ищет строку, где line_above совпадает с expected_signature_above, а текущая — с pass_line_content.
    Возвращает None, если не найдено."""
    if not full_content or not (expected_signature_above or "").strip():
        return None
    lines = full_content.splitlines()
    sig = (expected_signature_above or "").strip()
    pass_stripped = (pass_line_content or "").strip()
    for i in range(1, len(lines)):
        if (lines[i - 1].strip() == sig and lines[i].strip() == pass_stripped):
            return i + 1  # 1-based
    return None


def backspaces_for_pass(indent: int) -> int:
    """Сколько раз нажать Backspace чтобы удалить строку с pass. Для Ace уточним при настройке."""
    return (indent // 4) + 5


class BrowserPrintTarget:
    """База: браузер (Yandex.Code). Минимум для печати по карте — мост + клавиши."""

    def use_bridge_sync(self, printer) -> bool:
        return True

    def is_browser_mode(self, printer) -> bool:
        return True

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

    # --- После Enter: курсор на новой строке. Привести в начало строки. ---
    # В Ace после Enter курсор может оказаться на следующей существующей строке (след. блок),
    # а не на новой пустой. Если текущая строка не пустая — жмём Enter, чтобы вставить новую строку.
    def ensure_start_of_line_after_newline(self, printer):
        time.sleep(0.2)
        ctx = cursor_bridge.get_cursor_context()
        if ctx:
            printer.current_line = ctx.line
            printer.current_column = (ctx.column - 1) if ctx.column else 0
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)
        printer.current_column = 0
        time.sleep(0.12)
        ctx2 = cursor_bridge.get_cursor_context()
        if ctx2 and ctx2.line_content and ctx2.line_content.strip():
            # Строка не пустая — мы на следующем блоке (class/def), а не на новой строке. Вставить новую.
            printer.typer.press_enter()
            time.sleep(0.15)
            pos = cursor_bridge.get_cursor()
            if pos:
                printer.current_line = pos[0]
                printer.current_column = (pos[1] - 1) if pos[1] else 0

    def backspace_to_column_one(self, printer, current_col_1based: int):
        if current_col_1based <= 1:
            return
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)
        printer.current_column = 0

    # --- После печати сигнатуры блока: выровнять курсор на строку с pass. ---
    def align_cursor_after_newline_for_pass(self, printer, expected_line: int, max_rounds: int = 8):
        time.sleep(0.3)
        for _ in range(max_rounds):
            pos = cursor_bridge.get_cursor()
            if pos and pos[0] == expected_line:
                printer.current_line = pos[0]
                printer.current_column = (pos[1] - 1) if pos[1] else 0
                return
            if pos:
                delta = expected_line - pos[0]
                for _ in range(abs(delta)):
                    if delta > 0:
                        printer.typer._send_virtual_key(VK_DOWN, key_up=False)
                        time.sleep(0.02)
                        printer.typer._send_virtual_key(VK_DOWN, key_up=True)
                    else:
                        printer.typer._send_virtual_key(VK_UP, key_up=False)
                        time.sleep(0.02)
                        printer.typer._send_virtual_key(VK_UP, key_up=True)
                    time.sleep(0.04)
            time.sleep(0.2)
        pos = cursor_bridge.get_cursor()
        if pos:
            printer.current_line = pos[0]
            printer.current_column = (pos[1] - 1) if pos[1] else 0

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
        for _ in range(retries):
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
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)
        printer.current_column = 0

    def clear_line_if_accumulated_whitespace(self, printer, min_len: int = 4):
        ctx = self.get_context_from_bridge(printer, retries=2, sleep_sec=0.08)
        if ctx is None or not ctx.line_content:
            return
        content = ctx.line_content
        if content.strip() != "" or len(content) < min_len:
            return
        for _ in range(len(content)):
            printer.typer._send_virtual_key(VK_DELETE, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DELETE, key_up=True)
            time.sleep(0.02)
        printer.current_column = 0

    def fix_prev_line_indent_if_needed(self, printer, expected_prev_line: str):
        pass

    def ensure_on_correct_line_before_fill(self, printer, body_line: str, prev_line: str = None):
        pass

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
        time.sleep(0.2)
        ctx = self.get_context_from_bridge(printer)
        if ctx is None:
            return False
        if (ctx.line_content or "").strip() != (pass_line_content or "").strip():
            return False
        if expected_signature_above and (expected_signature_above or "").strip():
            if (ctx.line_above or "").strip() != (expected_signature_above or "").strip():
                return False
        return True

    def refresh_bridge_position(self, printer):
        time.sleep(0.2)

    def refresh_bridge_then_verify_on_pass(
        self, printer, pass_line_content: str, expected_signature_above: str = None
    ) -> bool:
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
        """Перейти на строку с pass: по документу из моста находим точный номер строки, затем синхронизируем и проверяем."""
        # Сначала берём актуальную позицию с моста
        self.update_position_from_bridge(printer, retries=3, sleep_sec=0.2)
        target_line = current_pass_line
        full = cursor_bridge.get_document_content()
        if full and (expected_signature_above or "").strip():
            found = _find_pass_line_in_document(full, expected_signature_above, pass_line_content)
            if found is not None:
                target_line = found
                print(f"    Строка с pass для '{block_name}' найдена по документу моста: {target_line}")
                if hasattr(printer, "_log_action"):
                    printer._log_action("FILL_PASS_FROM_DOC", f"Строка с pass для '{block_name}' найдена по документу: {target_line}")
        printer.current_line = target_line
        printer.current_column = 0
        self.ensure_cursor_synced(
            printer,
            expected_line_content=pass_line_content,
            expected_line_above=expected_signature_above,
        )
        return self.verify_on_pass_line_from_bridge(printer, pass_line_content, expected_signature_above)

    def do_cursor_correction(
        self,
        printer,
        actual_line: int,
        actual_col: int,
        expected_line: int,
        expected_col_1based: int,
    ):
        from .print_common import VK_RIGHT
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
        max_verify_rounds: int = 2,
    ):
        """Сверить позицию с мостом; при расхождении — одна коррекция (UP/DOWN, Home)."""
        expected_line = printer.current_line
        expected_col = printer.current_column + 1
        ctx = self.get_context_from_bridge(printer, retries=3, sleep_sec=0.15)
        if ctx is None:
            return
        if ctx.line == expected_line and ctx.column == expected_col:
            printer.current_line = ctx.line
            printer.current_column = ctx.column - 1
            return
        self.do_cursor_correction(printer, ctx.line, ctx.column, expected_line, expected_col)
        time.sleep(0.2)
        ctx2 = cursor_bridge.get_cursor_context()
        if ctx2:
            printer.current_line = ctx2.line
            printer.current_column = ctx2.column - 1

    def wait_for_bridge_position(self, printer, max_wait_sec: float = 2.8) -> bool:
        deadline = time.monotonic() + max_wait_sec
        while time.monotonic() < deadline:
            pos = self.get_cursor_from_bridge(printer, retries=2, sleep_sec=0.15)
            if pos is not None:
                return True
            time.sleep(0.25)
        return False

    def body_line_after_type_open_brace(self, printer, r: str, body_line: str):
        """Yandex/Ace: после { редактор подставляет один символ }; убираем только его (1× Delete)."""
        if r[-1] == '{':
            printer.typer.press_enter()
            time.sleep(0.08)
            printer.typer._send_virtual_key(VK_DELETE, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_DELETE, key_up=True)
            time.sleep(0.02)
        else:
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

    def before_fill_line_verify(
        self, printer, expected_line: int, body_start_line: int, idx: int, prev_line: str, block: dict
    ) -> bool:
        return True

    def after_fill_line_delay(self, printer):
        time.sleep(0.10)
