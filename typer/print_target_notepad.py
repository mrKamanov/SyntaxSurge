# -*- coding: utf-8 -*-
"""
Цель печати: Блокнот / IDE без моста.
Позиция только по счётчикам (current_line/current_column), удаление "pass" посимвольно.
Синхронизации по мосту нет — для стабильности добавлены консервативные паузы после Enter
и перед Home, чтобы приложение успело обработать нажатия.
"""

import time
from .active_window import get_active_window_type, WindowType, get_notepad_cursor, get_notepad_full_content
from .cursor_bridge import CursorContext

VK_HOME = 0x24
VK_DELETE = 0x2E
VK_ESCAPE = 0x1B


def backspaces_for_pass(indent: int) -> int:
    """В блокноте/IDE без моста: посимвольное удаление (отступ + 4 пробела + 'pass')."""
    return indent + 4 + 4


class NotepadPrintTarget:
    """Адаптер целевой среды: Блокнот или IDE без расширения (нет моста)."""

    def use_bridge_sync(self, printer) -> bool:
        return False

    def is_browser_mode(self, printer) -> bool:
        return False

    def is_editor_file_python(self, printer) -> bool:
        return False

    def should_dismiss_ide_popup(self, printer) -> bool:
        return False  # Блокнот без IntelliSense

    def backspaces_for_pass(self, printer, indent: int) -> int:
        return backspaces_for_pass(indent)

    def ensure_start_of_line_after_newline(self, printer):
        # Блокнот/IDE без моста: даём приложению обработать Enter, затем Home
        wt = get_active_window_type()
        if wt == WindowType.NOTEPAD:
            time.sleep(0.22)  # Блокнот медленнее реагирует — стабилизация позиции
        elif wt == WindowType.IDE:
            time.sleep(0.12)
        printer.typer._send_virtual_key(VK_HOME, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_HOME, key_up=True)
        time.sleep(0.04)

    def backspace_to_column_one(self, printer, current_col_1based: int):
        # Не используем колонку из моста — просто Home
        if current_col_1based > 1:
            printer.typer._send_virtual_key(VK_HOME, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_HOME, key_up=True)
            time.sleep(0.04)
        printer.current_column = 0

    def align_cursor_after_newline_for_pass(self, printer, expected_line: int, max_rounds: int = 8):
        # Без моста позицию не проверяем; даём приложению обработать Enter перед печатью pass
        time.sleep(0.15)

    def get_cursor_from_bridge(self, printer, retries: int = 4, sleep_sec: float = 0.18):
        """В Блокноте: позиция читается из Edit-контроля (Win32), не из HTTP-моста."""
        if get_active_window_type() != WindowType.NOTEPAD:
            return None
        return get_notepad_cursor()

    def get_context_from_bridge(self, printer, retries=None, sleep_sec=None):
        """В Блокноте: контекст (строка выше, текущая, ниже) и позиция из Edit-контроля."""
        if get_active_window_type() != WindowType.NOTEPAD:
            return None
        pos = get_notepad_cursor()
        full = get_notepad_full_content()
        if pos is None or full is None:
            return None
        line_1, col_1 = pos
        lines = full.split("\n")
        line_above = lines[line_1 - 2] if line_1 >= 2 else ""
        line_content = lines[line_1 - 1] if 1 <= line_1 <= len(lines) else ""
        line_below = lines[line_1] if line_1 < len(lines) else ""
        return CursorContext(
            line=line_1,
            column=col_1,
            line_above=line_above,
            line_content=line_content,
            line_below=line_below,
            language_id="",
            file_extension="",
        )

    def update_position_from_bridge(self, printer, retries: int = 5, sleep_sec: float = 0.22):
        """В Блокноте: синхронизируем current_line/current_column из Edit-контроля."""
        if get_active_window_type() != WindowType.NOTEPAD:
            return
        pos = get_notepad_cursor()
        if pos is not None:
            printer.current_line = pos[0]
            printer.current_column = (pos[1] - 1) if pos[1] else 0

    def sync_from_bridge_then_home(self, printer, expected_line_above: str = None):
        pass

    def clear_line_if_accumulated_whitespace(self, printer, min_len: int = 4):
        pass

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
        pass

    def verify_on_pass_line_from_bridge(
        self, printer, pass_line_content: str, expected_signature_above: str = None
    ) -> bool:
        return True

    def refresh_bridge_position(self, printer):
        pass

    def refresh_bridge_then_verify_on_pass(
        self, printer, pass_line_content: str, expected_signature_above: str = None
    ) -> bool:
        return True

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
        # Просто выставляем позицию по счётчикам
        printer.current_line = current_pass_line
        printer.current_column = 0
        return True

    def do_cursor_correction(
        self,
        printer,
        actual_line: int,
        actual_col: int,
        expected_line: int,
        expected_col_1based: int,
    ):
        # Навигация стрелками и в начало строки (без моста)
        from .print_common import VK_UP, VK_DOWN, VK_HOME
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
            printer.typer._send_virtual_key(VK_HOME, key_up=False)
            time.sleep(0.02)
            printer.typer._send_virtual_key(VK_HOME, key_up=True)
            time.sleep(0.04)
        printer.current_column = 0

    def sync_cursor_from_bridge(
        self,
        printer,
        expected_line_content: str = None,
        expected_line_above: str = None,
        expected_line_below: str = None,
        max_verify_rounds: int = 3,
    ):
        pass

    def wait_for_bridge_position(self, printer, max_wait_sec: float = 2.8) -> bool:
        return True

    def body_line_after_type_open_brace(self, printer, r: str, body_line: str):
        # Блокнот: по умолчанию 1 Delete, Enter (как в VS Code для [ и ( )
        printer.typer._send_virtual_key(VK_DELETE, key_up=False)
        time.sleep(0.02)
        printer.typer._send_virtual_key(VK_DELETE, key_up=True)
        time.sleep(0.02)
        printer.typer.press_enter()

    def before_fill_line_verify(self, printer, expected_line: int, body_start_line: int, idx: int, prev_line: str, block: dict) -> bool:
        """Перед печатью строки тела: нужно ли проверять позицию по мосту. Для блокнота — нет."""
        return True

    def after_fill_line_delay(self, printer):
        # Небольшая пауза между строками тела — чтобы блокнот успел обработать Enter
        time.sleep(0.08)
