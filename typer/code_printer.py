#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Printer - Печатает код используя КАРТУ
Загружает карту из JSON и печатает нелинейно.
Общая логика здесь; нюансы по целям (Яндекс, VS Code, блокнот) — в print_target_*.py.
"""

import time
import random
import json
import threading
from typing import Optional, Callable
import traceback
from datetime import datetime
from .windows_typer import WindowsTyper, TypingConfig
from .active_window import get_active_window_type, WindowType
from . import cursor_bridge
from .print_common import (
    VK_UP, VK_DOWN, VK_END, VK_HOME, VK_BACK, VK_DELETE, VK_ESCAPE, VK_RIGHT,
    looks_like_new_line, context_matches, is_block_start_line, analyze_position_for_pass_search,
)
from .print_target_browser import BrowserPrintTarget
from .print_target_vscode import VSCodePrintTarget
from .print_target_pycharm import PyCharmPrintTarget
from .print_target_notepad import NotepadPrintTarget
from . import LOG_FILE as _DEFAULT_LOG_FILE


class CodePrinter:
    """Печатает код используя карту"""
    
    def __init__(self, base_speed: float = 6.0, log_file: str = None, pause_event: threading.Event = None, paused_now: list = None, abort_event: threading.Event = None, on_block_start: Optional[Callable[[str, str], None]] = None, on_body_line_start: Optional[Callable[[str, int, str], None]] = None, on_line_start: Optional[Callable[[int, str], None]] = None):
        self.on_block_start = on_block_start
        self.on_body_line_start = on_body_line_start
        self.on_line_start = on_line_start
        config = TypingConfig(
            base_speed=base_speed,
            enable_typos=False,
            pause_thinking=(1.5, 3.0),
            pause_after_block=(0.3, 0.7),
            pause_event=pause_event,
            paused_now=paused_now,
            abort_event=abort_event,
        )
        self.typer = WindowsTyper(config, log_file=log_file)
        self.current_line = 1
        self.current_column = 0  # Текущая колонка в строке
        self.print_plan = []
        
        # Счетчик напечатанных строк для точного отслеживания позиции
        self.lines_typed_count = 0  # Сколько строк реально напечатано
        
        # Состояние для логирования
        self.last_char = None  # Последний напечатанный символ
        self.last_action = "Инициализация"  # Последнее действие
        self.blocks_info = []  # Информация о блоках (для расчета расстояний)
        self.current_block_index = -1  # Индекс текущего блока
        self.total_lines = 0  # Общее количество строк в файле
        self.total_chars = 0  # Общее количество символов в файле (включая пробелы)
        self._browser_sync_first_done = False  # первый sync в браузере — даём мосту время получить позицию
        self._target = None  # целевой адаптер (Browser / VSCode / PyCharm / Notepad), задаётся в print_from_map
        
        # Файл для логирования (один файл — перезаписывается при каждом запуске)
        if log_file is None:
            log_file = _DEFAULT_LOG_FILE
        self.log_file = log_file
        
        # Инициализируем лог-файл
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== ЛОГ АВТОПЕЧАТИ ===\n")
            f.write(f"Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"{'='*60}\n")
            f.write(f"ТЕКУЩЕЕ СОСТОЯНИЕ (обновляется в реальном времени)\n")
            f.write(f"{'='*60}\n")
            f.write(f"Позиция курсора: строка {self.current_line}, колонка {self.current_column}\n")
            f.write(f"Последний напечатанный символ: -\n")
            f.write(f"Последнее действие: {self.last_action}\n")
            f.write(f"Напечатано строк: {self.lines_typed_count} / {self.total_lines}\n")
            f.write(f"Напечатано символов: 0 / {self.total_chars}\n")
            f.write(f"Расстояния между блоками: -\n")
            f.write(f"Позиции блоков: -\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"ДЕТАЛЬНЫЙ ЛОГ ДЕЙСТВИЙ:\n")
            f.write(f"{'='*60}\n")
        
        self._log_action("INIT", f"Инициализация CodePrinter. Начальная позиция: строка {self.current_line}, колонка {self.current_column}")

    def _sleep(self, sec: float) -> None:
        """Сон с учётом паузы (делегирует в typer)."""
        self.typer._sleep(sec)

    def _send_vk_atomic(self, vk_code: int, dwell_sec: float = 0.02) -> None:
        """Отправить виртуальную клавишу атомарно (без паузы между key_down и key_up), чтобы не терять символ/действие."""
        self.typer._wait_while_paused()
        self.typer._send_virtual_key(vk_code, key_up=False)
        time.sleep(dwell_sec)
        self.typer._send_virtual_key(vk_code, key_up=True)

    def _update_status_section(self):
        """Обновляет секцию состояния в начале файла"""
        try:
            # Читаем весь файл
            with open(self.log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем ПЕРВУЮ секцию состояния (после заголовка)
            # Структура: заголовок -> пустая строка -> разделитель -> "ТЕКУЩЕЕ СОСТОЯНИЕ" -> содержимое -> разделитель -> пустая строка -> "ДЕТАЛЬНЫЙ ЛОГ"
            lines = content.split('\n')
            
            status_start = -1
            status_end = -1
            
            # Ищем ПЕРВУЮ строку "ТЕКУЩЕЕ СОСТОЯНИЕ" в файле (должна быть только одна)
            for i, line in enumerate(lines):
                if 'ТЕКУЩЕЕ СОСТОЯНИЕ' in line:
                    # Проверяем, что это действительно секция состояния (есть разделитель перед и после)
                    # Ищем разделитель перед (должен быть на строке i-1)
                    if i > 0 and lines[i-1].strip() == '=' * 60:
                        status_start = i - 1  # Начинаем с разделителя
                    else:
                        status_start = i  # Или начинаем с самой строки
                    
                    # Ищем разделитель после содержимого секции.
                    # Раньше мы ограничивали окно поиска, но теперь секция может быть длиннее (например, "Позиции блоков").
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() == '=' * 60:
                            # Проверяем, что это действительно конец секции состояния:
                            # после разделителя должна быть пустая строка или "ДЕТАЛЬНЫЙ ЛОГ"
                            if j + 1 < len(lines):
                                next_line = lines[j + 1].strip()
                                if (not next_line) or ('ДЕТАЛЬНЫЙ ЛОГ' in next_line):
                                    status_end = j
                                    break
                                # Если следующая строка снова "ТЕКУЩЕЕ СОСТОЯНИЕ" - это дубликат, пропускаем
                                if 'ТЕКУЩЕЕ СОСТОЯНИЕ' in next_line:
                                    continue
                            else:
                                status_end = j
                                break
                    break
            
            if status_start == -1 or status_end == -1 or status_end <= status_start:
                return  # Не нашли секцию, пропускаем обновление
            
            # Проверяем границы
            if status_start < 0 or status_end >= len(lines):
                return  # Выход за границы
            
            # Формируем информацию о расстояниях между блоками
            blocks_distances = []
            if len(self.blocks_info) > 1:
                for i in range(len(self.blocks_info) - 1):
                    # Проверяем, что индексы в допустимых пределах
                    if i >= len(self.blocks_info) or i + 1 >= len(self.blocks_info):
                        break
                    current_block_line = self.blocks_info[i].get('end_line', 0)
                    next_block_line = self.blocks_info[i + 1].get('start_line', 0)
                    distance = next_block_line - current_block_line
                    blocks_distances.append(f"Блок {i+1}→{i+2}: {distance} строк")
            
            distances_str = ", ".join(blocks_distances) if blocks_distances else "-"
            
            # Формируем информацию о позициях блоков
            blocks_positions = []
            for i, block in enumerate(self.blocks_info):
                block_name = block.get('name', f'Блок {i+1}')
                block_type = block.get('type', 'unknown')
                start_line = block.get('start_line', None)
                end_line = block.get('end_line', None)
                
                if start_line is not None:
                    if end_line is not None:
                        blocks_positions.append(f"{block_type} '{block_name}': строки {start_line}-{end_line}")
                    else:
                        blocks_positions.append(f"{block_type} '{block_name}': начинается на строке {start_line} (еще не завершен)")
                else:
                    blocks_positions.append(f"{block_type} '{block_name}': позиция не определена")
            
            blocks_positions_str = "\n".join(blocks_positions) if blocks_positions else "-"
            
            # Формируем новую секцию состояния
            last_char_repr = repr(self.last_char) if self.last_char else "-"
            if self.last_char and len(last_char_repr) > 20:
                last_char_repr = last_char_repr[:17] + "..."
            
            # Подсчитываем напечатанные символы (из статистики typer)
            chars_typed = self.typer.stats.get('chars_typed', 0)
            
            new_status = [
                f"{'='*60}",
                f"ТЕКУЩЕЕ СОСТОЯНИЕ (обновляется в реальном времени)",
                f"{'='*60}",
                f"Позиция курсора: строка {self.current_line}, колонка {self.current_column}",
                f"Последний напечатанный символ: {last_char_repr}",
                f"Последнее действие: {self.last_action}",
                f"Напечатано строк: {self.lines_typed_count} / {self.total_lines}",
                f"Напечатано символов: {chars_typed} / {self.total_chars}",
                f"Расстояния между блоками: {distances_str}",
                f"Позиции блоков:",
                blocks_positions_str,
                f"{'='*60}",
                f""  # Пустая строка
            ]
            
            # Заменяем секцию состояния
            # Проверяем, что status_end + 1 не выходит за границы
            end_index = status_end + 1
            if end_index > len(lines):
                end_index = len(lines)
            
            # Собираем новый файл: начало до секции + новая секция + остаток после секции
            # Проверяем границы перед срезом
            if status_start < 0:
                status_start = 0  # Исправляем отрицательный индекс
            if status_start > len(lines):
                return  # Некорректный индекс начала
            if end_index < 0:
                end_index = 0  # Исправляем отрицательный индекс
            if end_index > len(lines):
                end_index = len(lines)  # Исправляем индекс, выходящий за границы
            
            # Безопасное создание нового списка строк
            try:
                before_section = lines[:status_start] if status_start > 0 else []
                after_section = lines[end_index:] if end_index < len(lines) else []
                new_lines = before_section + new_status + after_section
            except (IndexError, ValueError) as e:
                # Если что-то пошло не так при создании списка - пропускаем обновление
                return
            
            # Дополнительная проверка: если после секции идут дубликаты секции состояния, удаляем их
            # Ищем и удаляем все последующие секции "ТЕКУЩЕЕ СОСТОЯНИЕ" до "ДЕТАЛЬНЫЙ ЛОГ"
            cleaned_lines = []
            skip_until_detail = False
            found_first_status = False
            
            for idx, line in enumerate(new_lines):
                if 'ДЕТАЛЬНЫЙ ЛОГ' in line:
                    skip_until_detail = False
                    cleaned_lines.append(line)
                elif skip_until_detail:
                    continue  # Пропускаем дубликаты секции состояния
                elif 'ТЕКУЩЕЕ СОСТОЯНИЕ' in line:
                    if not found_first_status:
                        # Это первая (наша) секция состояния - оставляем её
                        found_first_status = True
                        cleaned_lines.append(line)
                    else:
                        # Это дубликат - пропускаем до "ДЕТАЛЬНЫЙ ЛОГ"
                        skip_until_detail = True
                        continue
                else:
                    cleaned_lines.append(line)
            
            new_lines = cleaned_lines
            
            # Записываем обратно
            with open(self.log_file, 'w', encoding='utf-8') as f:
                # Объединяем строки с переносами, так как split('\n') удаляет \n
                f.write('\n'.join(new_lines))
                # Добавляем перенос в конце, если его нет
                if new_lines and not new_lines[-1].endswith('\n'):
                    f.write('\n')
        except Exception as e:
            # Игнорируем ошибки обновления статуса, чтобы не прерывать работу
            # Но логируем для отладки
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n[ОШИБКА ОБНОВЛЕНИЯ СТАТУСА] {str(e)}\n")
            except:
                pass
    
    def _log_action(self, action_type: str, message: str):
        """Логирует действие в файл и обновляет состояние"""
        try:
            self.last_action = f"[{action_type}] {message}"
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            log_entry = f"[{timestamp}] [{action_type}] Позиция: строка {self.current_line}, колонка {self.current_column} | {message}\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            # Обновляем секцию состояния (не слишком часто, чтобы не замедлять)
            if action_type in ['TYPE_CHAR_END', 'TYPE_LINE_END', 'POSITION_UPDATE', 'BLOCK_SIGNATURE_DONE', 'PASS_DONE', 'PRINT_END']:
                self._update_status_section()
        except Exception as e:
            print(f"⚠️ Ошибка записи в лог: {e}")
    
    def _navigate_up(self, count: int):
        """Перемещается вверх через стрелки: разная скорость шагов, замедление перед целью"""
        self._log_action("NAVIGATE", f"Навигация ВВЕРХ на {count} строк(и)")
        for i in range(count):
            steps_left = count - i - 1
            if steps_left < 2:
                delay = random.uniform(0.12, 0.24)
            else:
                delay = random.uniform(0.03, 0.08)
            self._log_action("KEY_PRESS", f"Нажатие UP — шаг {i+1}/{count}, пауза {delay:.2f}")
            self._send_vk_atomic(VK_UP, 0.01)
            self._sleep(delay)
            self.current_line -= 1
            self._log_action("POSITION_UPDATE", f"Позиция после ВВЕРХ: строка {self.current_line}")
    
    def _navigate_down(self, count: int):
        """Перемещается вниз через стрелки: разная скорость шагов, замедление перед целью"""
        self._log_action("NAVIGATE", f"Навигация ВНИЗ на {count} строк(и)")
        for i in range(count):
            steps_left = count - i - 1
            if steps_left < 2:
                delay = random.uniform(0.12, 0.24)
            else:
                delay = random.uniform(0.03, 0.08)
            self._log_action("KEY_PRESS", f"Нажатие DOWN — шаг {i+1}/{count}, пауза {delay:.2f}")
            self._send_vk_atomic(VK_DOWN, 0.01)
            self._sleep(delay)
            self.current_line += 1
            self._log_action("POSITION_UPDATE", f"Позиция после ВНИЗ: строка {self.current_line}")
    
    def _insert_line_above(self, content: str):
        """Вставляет строку выше текущей. Курсор после вставки — на следующей строке.
        Надёжный способ: переход на предыдущую строку, End, Enter (в редакторах так
        гарантированно создаётся новая строка, а не печать на текущей).
        Для первой строки — Home, Enter.
        """
        target_line = self.current_line
        if target_line <= 1:
            self._send_vk_atomic(VK_HOME, 0.02)
            self._sleep(0.03)
            self.typer.press_enter()
        else:
            self._navigate_up(1)
            self._send_vk_atomic(VK_END, 0.01)
            self._sleep(0.03)
            self.typer.press_enter()
        self._sleep(0.08)  # Даём редактору время создать новую строку до начала печати
        self.current_line = target_line  # мы теперь на новой пустой строке с этим номером
        self.current_column = 0
        self.typer.type_line(content, add_newline=True)
        self.last_char = '\n'
        self.lines_typed_count += 1
        self.current_line = target_line + 1
        self.current_column = 0
        self._ensure_start_of_line_after_newline()
        if self._target:
            self._target.update_position_from_bridge(self)

    def _use_bridge_sync(self):
        if self._target is None:
            return False
        return self._target.use_bridge_sync(self)

    def _is_editor_file_python(self) -> bool:
        if self._target is None:
            return False
        return self._target.is_editor_file_python(self)

    def _should_dismiss_ide_popup(self) -> bool:
        """Закрывать IntelliSense перед Enter (Python, SQL и др.)."""
        if self._target is None:
            return False
        fn = getattr(self._target, "should_dismiss_ide_popup", None)
        return fn(self) if fn else self._target.is_editor_file_python(self)

    def _ensure_start_of_line_after_newline(self):
        if self._target is None:
            return
        self._target.ensure_start_of_line_after_newline(self)

    def _align_cursor_after_newline_for_pass(self, expected_line: int, max_rounds: int = 8):
        if self._target:
            self._target.align_cursor_after_newline_for_pass(self, expected_line, max_rounds)

    def _get_cursor_from_bridge(self, retries: int = 4, sleep_sec: float = 0.18):
        if self._target is None:
            return None
        return self._target.get_cursor_from_bridge(self, retries, sleep_sec)

    def _get_context_from_bridge(self, retries: int = None, sleep_sec: float = None):
        if self._target is None:
            return None
        return self._target.get_context_from_bridge(self, retries, sleep_sec)

    def _update_position_from_bridge(self, retries: int = 5, sleep_sec: float = 0.22):
        if self._target:
            self._target.update_position_from_bridge(self, retries, sleep_sec)

    def _sync_from_bridge_then_home(self, expected_line_above: str = None):
        if self._target:
            self._target.sync_from_bridge_then_home(self, expected_line_above)

    def _clear_line_if_accumulated_whitespace(self, min_len: int = 4):
        if self._target:
            self._target.clear_line_if_accumulated_whitespace(self, min_len)

    def _fix_prev_line_indent_if_needed(self, expected_prev_line: str):
        if self._target:
            self._target.fix_prev_line_indent_if_needed(self, expected_prev_line)

    def _ensure_on_correct_line_before_fill(self, body_line: str, prev_line: str = None):
        if self._target:
            self._target.ensure_on_correct_line_before_fill(self, body_line, prev_line)

    def _context_matches(
        self,
        ctx,
        expected_line: int,
        expected_col_1based: int,
        expected_line_content: str = None,
        expected_line_above: str = None,
        expected_line_below: str = None,
    ) -> bool:
        return context_matches(ctx, expected_line, expected_col_1based,
                              expected_line_content=expected_line_content,
                              expected_line_above=expected_line_above,
                              expected_line_below=expected_line_below)

    def _wait_for_bridge_position(self, max_wait_sec: float = 2.8):
        if self._target is None:
            return True
        return self._target.wait_for_bridge_position(self, max_wait_sec)

    def _do_cursor_correction(self, actual_line: int, actual_col: int, expected_line: int, expected_col_1based: int):
        if self._target:
            self._target.do_cursor_correction(self, actual_line, actual_col, expected_line, expected_col_1based)

    def _sync_cursor_from_bridge(
        self,
        expected_line_content: str = None,
        expected_line_above: str = None,
        expected_line_below: str = None,
        max_verify_rounds: int = 3,
    ):
        if self._target:
            self._target.sync_cursor_from_bridge(
                self,
                expected_line_content=expected_line_content,
                expected_line_above=expected_line_above,
                expected_line_below=expected_line_below,
                max_verify_rounds=max_verify_rounds,
            )

    def _ensure_cursor_synced(
        self,
        expected_line_content: str = None,
        expected_line_above: str = None,
        expected_line_below: str = None,
    ):
        if self._target:
            self._target.ensure_cursor_synced(
                self,
                expected_line_content=expected_line_content,
                expected_line_above=expected_line_above,
                expected_line_below=expected_line_below,
            )

    def _verify_on_pass_line_from_bridge(
        self, pass_line_content: str, expected_signature_above: str = None
    ) -> bool:
        if self._target is None:
            return True
        return self._target.verify_on_pass_line_from_bridge(self, pass_line_content, expected_signature_above)

    def _search_pass_line_by_blocks(
        self,
        block_name: str,
        pass_line_content: str,
        expected_signature_above: str,
        current_pass_line: int,
    ) -> bool:
        """
        Ищем строку с pass, шагая вниз/вверх до границы блока (class/def).
        По контексту понимаем: нашли pass, стоим на сигнатуре нашего блока (pass ниже),
        наткнулись на другой блок — тогда знаем, куда двигаться. Возвращает True, если нашли и обновили current_line.
        """
        sig = (expected_signature_above or "").strip()
        max_steps = 50

        def step_down():
            self._send_vk_atomic(VK_DOWN, 0.02)
            self._sleep(0.35)

        def step_up():
            self._send_vk_atomic(VK_UP, 0.02)
            self._sleep(0.35)

        def get_ctx():
            self._sleep(0.2)
            return self._get_context_from_bridge() or cursor_bridge.get_cursor_context()

        def update_current_line():
            pos = cursor_bridge.get_cursor()
            if pos:
                self.current_line = pos[0]
                self.current_column = 0

        # Поиск вниз: пока не наткнёмся на "found", "on_signature" или "other_block"
        for step in range(max_steps):
            step_down()
            ctx = get_ctx()
            kind = analyze_position_for_pass_search(ctx, pass_line_content, sig)
            if kind == "found":
                update_current_line()
                self._log_action("FILL_FIND", f"Строка с pass найдена (поиск вниз, шаг {step + 1}), строка {self.current_line}")
                print(f"    Найдена строка с pass (поиск вниз), продолжаем заполнение.")
                return True
            if kind == "on_signature":
                step_down()
                self._sleep(0.4)
                if self._verify_on_pass_line_from_bridge(pass_line_content, expected_signature_above):
                    update_current_line()
                    self._log_action("FILL_FIND", "Строка с pass найдена: были на сигнатуре, шаг вниз.")
                    print(f"    Найдена строка с pass (под сигнатурой), продолжаем заполнение.")
                    return True
                return False
            if kind == "other_block":
                step_up()
                self._sleep(0.4)
                if self._verify_on_pass_line_from_bridge(pass_line_content, expected_signature_above):
                    update_current_line()
                    self._log_action("FILL_FIND", f"Строка с pass найдена: за другим блоком, шаг назад вверх, строка {self.current_line}")
                    print(f"    Найдена строка с pass (за другим блоком), продолжаем заполнение.")
                    return True
                return False

        # Поиск вверх: возвращаемся и шагаем вверх до границы блока
        for _ in range(max_steps):
            step_up()
            self._sleep(0.05)
        self._sleep(0.35)
        for step in range(max_steps):
            step_up()
            ctx = get_ctx()
            kind = analyze_position_for_pass_search(ctx, pass_line_content, sig)
            if kind == "found":
                update_current_line()
                self._log_action("FILL_FIND", f"Строка с pass найдена (поиск вверх, шаг {step + 1}), строка {self.current_line}")
                print(f"    Найдена строка с pass (поиск вверх), продолжаем заполнение.")
                return True
            if kind == "on_signature":
                step_down()
                self._sleep(0.4)
                if self._verify_on_pass_line_from_bridge(pass_line_content, expected_signature_above):
                    update_current_line()
                    self._log_action("FILL_FIND", "Строка с pass найдена (вверх): на сигнатуре, шаг вниз.")
                    print(f"    Найдена строка с pass (вверх + под сигнатурой), продолжаем заполнение.")
                    return True
                return False
            if kind == "other_block":
                step_down()
                self._sleep(0.4)
                for down_step in range(max_steps):
                    ctx = get_ctx()
                    k = analyze_position_for_pass_search(ctx, pass_line_content, sig)
                    if k == "found":
                        update_current_line()
                        self._log_action("FILL_FIND", f"Строка с pass найдена (вверх: за другим блоком, спуск шаг {down_step + 1}).")
                        print(f"    Найдена строка с pass (другой блок выше, спуск), продолжаем заполнение.")
                        return True
                    if k == "on_signature":
                        step_down()
                        self._sleep(0.4)
                        if self._verify_on_pass_line_from_bridge(pass_line_content, expected_signature_above):
                            update_current_line()
                            self._log_action("FILL_FIND", "Строка с pass найдена (спуск от блока выше: под сигнатурой).")
                            print(f"    Найдена строка с pass (спуск от блока выше), продолжаем заполнение.")
                            return True
                        return False
                    if k == "other_block":
                        step_up()
                        self._sleep(0.4)
                        if self._verify_on_pass_line_from_bridge(pass_line_content, expected_signature_above):
                            update_current_line()
                            self._log_action("FILL_FIND", "Строка с pass найдена (спуск: за другим блоком, шаг назад вверх).")
                            print(f"    Найдена строка с pass (между блоками), продолжаем заполнение.")
                            return True
                        return False
                    step_down()
                    self._sleep(0.35)

        return False

    def load_map(self, map_file: str):
        """Загружает карту из JSON"""
        with open(map_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.print_plan = data['print_plan']
        self.header_lines = data.get('header_lines', 0)  # Строк в шапке (shebang, encoding) — после них вставляем импорты
        self.imports_from_map = data.get('imports', [])  # Список {'content': ..., 'line': ...}; печатаются после заполнения
        
        # Сохраняем общую информацию о файле
        self.total_lines = data.get('total_lines', 0)
        self.total_chars = data.get('total_chars', 0)
        
        # Обновляем секцию состояния с общей информацией
        self._update_status_section()
        
        print(f"Карта загружена: {map_file}")
        print(f"  Язык: {data['language']}")
        print(f"  Строк: {self.total_lines}")
        print(f"  Символов: {self.total_chars}")
        print(f"  План: {len(self.print_plan)} шагов")
    
    def print_from_map(self, initial_delay: int = 5, browser_mode: bool = None):
        """
        Печатает код по карте.
        browser_mode: None — автоопределение по активному окну (браузер/блокнот·IDE);
                      True — принудительно режим браузера (Yandex.Code и т.п.);
                      False — режим блокнота/IDE.
        В режиме браузера: удаление строки «pass» — 5 Backspace; отступ удаляется одним Backspace за уровень.
        """
        self._log_action("PRINT_START", f"Начало печати по карте. Задержка перед стартом: {initial_delay} сек")
        
        print("\n" + "=" * 60)
        print("ПЕЧАТЬ ПО КАРТЕ")
        print("=" * 60)
        
        skeleton_steps = [s for s in self.print_plan if s['phase'] == 'skeleton']
        
        print(f"ФАЗА 1 (скелет): {len(skeleton_steps)} шагов")
        print(f"ФАЗА 2 (заполнение): будет определена после скелета")
        
        self._log_action("PRINT_INFO", f"ФАЗА 1 (скелет): {len(skeleton_steps)} шагов. ФАЗА 2 (заполнение): будет определена после скелета")
        
        print(f"\nНачало через {initial_delay} сек...")
        print("Переключитесь на редактор!")
        
        for i in range(initial_delay, 0, -1):
            print(f"{i}...")
            self._log_action("COUNTDOWN", f"Обратный отсчет: {i} сек")
            self._sleep(1)
        
        # Режим браузера: автоопределение по активному окну (если не задан явно)
        if browser_mode is None:
            self._browser_mode = get_active_window_type() == WindowType.BROWSER
        else:
            self._browser_mode = browser_mode
        # В IDE ждём источник моста (vscode/pycharm), чтобы не печатать как в блокнот при лаге плагина
        if get_active_window_type() == WindowType.IDE:
            for _ in range(10):
                src = cursor_bridge.get_source()
                if src in ("vscode", "pycharm"):
                    break
                self._sleep(0.2)
        if self._browser_mode:
            self._browser_sync_first_done = False
            self._target = BrowserPrintTarget()
        elif get_active_window_type() == WindowType.IDE and cursor_bridge.get_source() == "vscode":
            self._target = VSCodePrintTarget()
        elif get_active_window_type() == WindowType.IDE and cursor_bridge.get_source() == "pycharm":
            self._target = PyCharmPrintTarget()
        else:
            self._target = NotepadPrintTarget()
        if self._browser_mode:
            mode_label = "браузер (Yandex.Code и т.п.)"
        elif self._target.__class__.__name__ == "PyCharmPrintTarget":
            mode_label = "PyCharm (мост)"
        elif self._target.__class__.__name__ == "VSCodePrintTarget":
            mode_label = "VS Code / Cursor (мост)"
        else:
            mode_label = "блокнот/IDE"
        print(f"\nПЕЧАТЬ! Режим: {mode_label}")
        if self._use_bridge_sync():
            pos = cursor_bridge.get_cursor()
            if pos:
                print(f"  Позиция в редакторе: строка {pos[0]}, столбец {pos[1]}")
                self._log_action("CURSOR_FROM_BRIDGE", f"Позиция в редакторе: строка {pos[0]}, столбец {pos[1]}")
            if not self._wait_for_bridge_position(max_wait_sec=2.8):
                print("  Внимание: мост не прислал позицию — убедитесь, что вкладка с редактором открыта и userscript/расширение работает.")
        self._log_action("PRINT_BEGIN", f"ПЕЧАТЬ НАЧАЛАСЬ! Режим: {mode_label}. Позиция: строка {self.current_line}, колонка {self.current_column}")
        
        start_time = time.time()
        
        try:
            # ═══════════════════════════════════════
            # ФАЗА 1: СКЕЛЕТ
            # ═══════════════════════════════════════
            
            print("\n--- ФАЗА 1: СКЕЛЕТ ---")
            
            # Находим информацию о skeleton phase из карты
            skeleton_info = None
            for step in self.print_plan:
                if step.get('action') == 'skeleton_phase_info':
                    skeleton_info = step
                    break
            
            for step in self.print_plan:
                self.typer.dismiss_ide_popup_before_enter = self._should_dismiss_ide_popup()
                if step['phase'] != 'skeleton':
                    continue
                
                if step['action'] == 'skeleton_phase_info':
                    # Пропускаем информационный шаг
                    continue
                
                if step['action'] == 'type_line':
                    content = step['content']
                    skeleton_line = step.get('skeleton_line', self.current_line)
                    original_line = step.get('original_line')
                    if self.on_line_start and original_line is not None:
                        try:
                            self.on_line_start(original_line, content)
                        except Exception:
                            pass
                    # Показываем номер строки из карты, на которой мы печатаем
                    print(f"  Строка {skeleton_line}: {content[:50]}..." if len(content) > 50 else f"  Строка {skeleton_line}: {content}")
                    
                    self._ensure_cursor_synced()
                    self._log_action("TYPE_LINE_START", f"Начало печати строки. Содержимое: '{content}' (длина: {len(content)} символов)")
                    
                    # Печатаем в реальный редактор (куда курсор пользователя)
                    self.typer.type_line(content, add_newline=True)
                    # Последний реально напечатанный символ при add_newline=True — Enter
                    self.last_char = '\n'
                    self._ensure_start_of_line_after_newline()
                    if self._use_bridge_sync():
                        self._update_position_from_bridge()
                    
                    # Увеличиваем счетчик напечатанных строк
                    self.lines_typed_count += 1
                    
                    # Обновляем позицию курсора математически
                    # Используем skeleton_line из карты для точности
                    old_line = self.current_line
                    # После печати строки с add_newline=True курсор всегда на следующей строке
                    self.current_line = skeleton_line + 1
                    self.current_column = 0
                    self._log_action("TYPE_LINE_END", f"Строка напечатана. Позиция: {old_line} → {self.current_line}, колонка: {self.current_column}")
                    self._update_status_section()
                
                elif step['action'] == 'type_block_skeleton':
                    name = step['name']
                    block_type = step['type']
                    use_skeleton_mode = step.get('use_skeleton_mode', False)
                    has_body = step.get('has_body', False)
                    
                    self.current_block_index += 1
                    if self.on_block_start:
                        try:
                            self.on_block_start(name, block_type)
                        except Exception:
                            pass
                    
                    # Пауза "думает"
                    think_time = random.uniform(1.5, 3.0)
                    print(f"  [думает о {block_type} {name}] {think_time:.1f} сек")
                    self._log_action("THINKING", f"Пауза 'думает' перед блоком {block_type} '{name}': {think_time:.2f} сек")
                    self._sleep(think_time)
                    self.typer.notify_thinking_pause()
                    
                    # Декораторы — печатаем на этапе скелета; подсказку не меняем (показываем блок)
                    orig_line = step.get('original_line')
                    decorators_list = step.get('decorators', [])
                    for dec in decorators_list:
                        self._ensure_cursor_synced()
                        self._log_action("TYPE_DECORATOR", f"Печать декоратора для {block_type} '{name}': {str(dec)[:50]}...")
                        self.typer.type_line(dec, add_newline=True)
                        self.last_char = '\n'
                        self._ensure_start_of_line_after_newline()
                        if self._use_bridge_sync():
                            self._update_position_from_bridge()
                        self.lines_typed_count += 1
                        self.current_line += 1
                        self.current_column = 0
                        self._sleep(random.uniform(0.05, 0.15))
                    
                    # Начало блока — строка с сигнатурой (после декораторов)
                    block_start_line = self.current_line
                    self.blocks_info.append({
                        'name': name,
                        'type': block_type,
                        'start_line': block_start_line,
                        'end_line': None,  # Будет установлено позже
                        'signature': step.get('signature', ''),  # Для проверки контекста при заполнении (строка выше = сигнатура)
                        'body_lines': step.get('body_lines', []),  # Тело блока для заполнения
                        'indent': step.get('indent', 0),  # Отступ блока
                        'use_skeleton_mode': use_skeleton_mode,  # Нужно ли заполнять
                        'has_body': has_body,  # Есть ли тело для заполнения
                        'decorators': step.get('decorators', []),  # Уже напечатаны в скелете
                        'original_line': step.get('original_line'),  # Номер строки в исходном коде (для подсказок)
                    })
                    
                    # Сигнатура (уже на нужной строке после декораторов); подсказка — по блоку (уже показана в block_changed)
                    signature = step['signature']
                    print(f"  Строка {block_start_line}: {signature}")
                    
                    self._ensure_cursor_synced()
                    self._log_action("TYPE_BLOCK_SIGNATURE", f"Печать сигнатуры блока {block_type} '{name}': '{signature}'")
                    
                    self.typer.type_line(signature, add_newline=True)
                    self.last_char = '\n'
                    old_line = block_start_line
                    # Ожидаемая позиция: следующая строка, начало (чтобы печатать pass)
                    self.current_line = block_start_line + 1
                    self.current_column = 0
                    # В браузере: проверяем позицию по мосту; если не там — жмём стрелку или Backspace, проверяем снова
                    self._align_cursor_after_newline_for_pass(expected_line=block_start_line + 1)
                    if self._use_bridge_sync():
                        self._update_position_from_bridge()
                    self.lines_typed_count += 1
                    step['actual_skeleton_line'] = block_start_line
                    self._log_action("BLOCK_SIGNATURE_DONE", f"Сигнатура напечатана. Позиция: {old_line} → {self.current_line}")
                    self._update_status_section()
                    
                    # Если скелетный режим И есть тело - печатаем pass (заглушка)
                    # Подсказку по строке тела не показываем: построчные подсказки только на фазе заполнения
                    if use_skeleton_mode and has_body:
                        indent_str = ' ' * (step['indent'] + 4)
                        pass_line = indent_str + 'pass'
                        pass_skeleton_line = block_start_line + 1
                        print(f"  Строка {pass_skeleton_line}: {pass_line}")
                        self._log_action("TYPE_PASS", f"Печать 'pass' для блока '{name}': '{pass_line}' (отступ: {step['indent'] + 4} пробелов)")
                        
                        # Печатаем в реальный редактор (куда курсор пользователя)
                        self.typer.type_line(pass_line, add_newline=True)
                        # add_newline=True => последний символ Enter
                        self.last_char = '\n'
                        self._ensure_start_of_line_after_newline()
                        old_line = self.current_line
                        if self._use_bridge_sync():
                            if getattr(self, '_browser_mode', False):
                                self._sleep(0.28)
                            self._update_position_from_bridge()
                            # Не делаем +=1: мост уже дал правильную строку (пустая после pass).
                            # Иначе получалось 10 вместо 9 и синхронизация делала DOWN+HOME несколько раз («танцы» курсора).
                        else:
                            self.current_line += 1  # После pass курсор на следующей строке
                            self.current_column = 0
                        self.lines_typed_count += 1  # Увеличиваем счетчик
                        step['pass_line_number'] = self.current_line - 1  # pass на строке перед текущей
                        step['pass_line_length'] = len(pass_line)
                        self._log_action("PASS_DONE", f"'pass' напечатан. Позиция: {old_line} → {self.current_line}")
                        self._update_status_section()
                        
                        # Обновляем информацию о конце блока (элемент уже создан выше)
                        block_end_line = self.current_line - 1
                        if self.current_block_index >= 0 and self.current_block_index < len(self.blocks_info):
                            self.blocks_info[self.current_block_index]['end_line'] = block_end_line
                    elif has_body:
                        # Прямой режим - тело уже будет напечатано следующим шагом (type_line)
                        # Сигнатура уже напечатана с add_newline=True, так что курсор уже на новой строке
                        # Следующая type_line (из body_lines) напечатается на правильной строке
                        step['body_target_line'] = self.current_line
                        self._log_action("BLOCK_DIRECT_MODE", f"Прямой режим для блока '{name}'. Тело будет напечатано следующим шагом")
                    else:
                        # Нет тела - просто пустая строка
                        self._log_action("PRESS_ENTER", f"Нажатие Enter для пустой строки после блока '{name}'")
                        self.typer.press_enter()
                        # Для пустой строки просто увеличиваем позицию (press_enter переводит курсор на следующую строку)
                        old_line = self.current_line
                        self.current_line += 1
                        self.current_column = 0
                        self._log_action("EMPTY_LINE_DONE", f"Пустая строка добавлена. Позиция: {old_line} → {self.current_line}")
                        
                        # Обновляем информацию о конце блока (элемент уже создан выше)
                        block_end_line = self.current_line - 1
                        if self.current_block_index >= 0 and self.current_block_index < len(self.blocks_info):
                            self.blocks_info[self.current_block_index]['end_line'] = block_end_line
                    
                    self._sleep(random.uniform(0.2, 0.5))
            
            print(f"\n  Скелет готов: {self.current_line - 1} строк")
            # ═══════════════════════════════════════
            # ФАЗА 2: ЗАПОЛНЕНИЕ БЛОКОВ
            # ═══════════════════════════════════════
            
            # Оригинальные позиции и учёт добавленных строк для ВСЕХ блоков (нужны для фазы вставки)
            original_positions = [{'start_line': b['start_line'], 'end_line': b['end_line']} for b in self.blocks_info]
            lines_added_per_block = [0] * len(self.blocks_info)
            
            # Блоки для заполнения — с индексами в blocks_info
            blocks_to_fill = [
                (i, block) for i, block in enumerate(self.blocks_info)
                if block.get('use_skeleton_mode', False) and block.get('has_body', False) and block.get('end_line') is not None
            ]
            
            if blocks_to_fill:
                print(f"\n--- ФАЗА 2: ЗАПОЛНЕНИЕ БЛОКОВ ---")
                print(f"  Блоков для заполнения: {len(blocks_to_fill)}")
                self._log_action("FILL_PHASE_START", f"Начало фазы заполнения. Блоков для заполнения: {len(blocks_to_fill)}")
                
                total_offset = 0
                
                for idx, (block_idx, block) in enumerate(blocks_to_fill):
                    block_name = block['name']
                    block_type = block['type']
                    body_lines = block['body_lines']
                    
                    if not body_lines:
                        continue
                    
                    original_start = original_positions[block_idx]['start_line']
                    original_end = original_positions[block_idx]['end_line']
                    
                    # Без моста (блокнот): позиции считаем только по смещениям от скелета.
                    # current_pass_line = строка pass в текущем файле = original_end + total_offset.
                    current_pass_line = original_end + total_offset
                    gap_signature_to_pass = original_end - original_start
                    current_start = current_pass_line - gap_signature_to_pass
                    
                    print(f"\n  [{idx + 1}/{len(blocks_to_fill)}] Заполнение {block_type} '{block_name}'")
                    print(f"    Оригинальная позиция: строки {original_start}-{original_end}")
                    print(f"    Текущая позиция (с учетом смещений): строки {current_start}-{current_pass_line}")
                    print(f"    Тело: {len(body_lines)} строк")
                    
                    # Пауза "думает"
                    think_time = random.uniform(1.5, 3.0)
                    print(f"    [думает о теле {block_type} {block_name}] {think_time:.1f} сек")
                    self._log_action("FILL_THINKING", f"Пауза 'думает' перед заполнением {block_type} '{block_name}': {think_time:.2f} сек")
                    self._sleep(think_time)
                    self.typer.notify_thinking_pause()
                    
                    # Сверка позиции через мост (как в VS Code), чтобы не теряться после предыдущего блока
                    if self._use_bridge_sync():
                        self._update_position_from_bridge(retries=5, sleep_sec=0.25)
                        print(f"    Навигация к строке {current_pass_line} (текущая позиция по мосту: {self.current_line})")
                    else:
                        # Без моста: короткая пауза, чтобы редактор успел обработать предыдущие нажатия, затем навигация стрелками
                        self._sleep(0.18)
                        if self.current_line != current_pass_line:
                            distance = current_pass_line - self.current_line
                            print(f"    Навигация к строке {current_pass_line} (текущая позиция: {self.current_line}, расстояние: {distance})")
                            if distance > 0:
                                self._navigate_down(distance)
                            else:
                                self._navigate_up(abs(distance))
                    self._log_action("FILL_NAVIGATE", f"Навигация к строке с pass: {current_pass_line}" + (" (по мосту)" if self._use_bridge_sync() else ""))
                    
                    pass_line_content = " " * (block["indent"] + 4) + "pass"
                    expected_signature_above = (block.get("signature") or "").strip() or None

                    # Навигация к строке с pass — делегируем целевой среде (Яндекс / VS Code / блокнот)
                    on_pass = self._target.navigate_to_pass_line_for_fill(
                        self, block_name, pass_line_content, expected_signature_above,
                        current_pass_line, current_start, original_start, original_end,
                    )
                    if not on_pass:
                        print(f"    ОСТАНОВ: строка с pass не найдена по контексту. Блок '{block_name}' пропущен.")
                        self._log_action(
                            "FILL_ABORT_WRONG_LINE",
                            f"Поиск строки с pass для '{block_name}' не удался. Заполнение блока пропущено."
                        )
                        self.current_line = current_pass_line + 1
                        self.current_column = 0
                        continue

                    # Строгая проверка по мосту: мы на строке pass и строка выше = сигнатура. Иначе не трогать Backspace.
                    if self._use_bridge_sync():
                        if not self._target.refresh_bridge_then_verify_on_pass(
                            self, pass_line_content, expected_signature_above
                        ):
                            print(f"    ОСТАНОВ: после перехода позиция не совпала с pass (мост). Блок '{block_name}' пропущен.")
                            self._log_action(
                                "FILL_ABORT_VERIFY_PASS",
                                f"Проверка pass для '{block_name}' не прошла (мост). Backspace не выполнен."
                            )
                            self.current_line = current_pass_line + 1
                            self.current_column = 0
                            continue

                    # Переходим в конец строки (чтобы курсор был после "pass")
                    self._log_action("NAVIGATE_TO_END", f"Переход в конец строки {self.current_line} перед удалением pass")
                    self._send_vk_atomic(VK_END, 0.01)
                    self._sleep(0.05)
                    self.current_column = 999  # Устанавливаем большое значение, так как мы в конце строки
                    
                    # Финальная проверка перед Backspace: обновить мост, затем убедиться, что на строке именно pass.
                    if self._use_bridge_sync():
                        self._target.refresh_bridge_position(self)
                        self._sleep(0.2)
                        ctx = cursor_bridge.get_cursor_context()
                        if ctx and (ctx.line_content or "").strip() != pass_line_content.strip():
                            print(f"    ОСТАНОВ перед удалением: на строке не pass (получено: {repr((ctx.line_content or '')[:50])}). Блок '{block_name}' пропущен.")
                            self._log_action(
                                "FILL_ABORT_SAFETY",
                                f"Перед DELETE_PASS контекст не pass для '{block_name}': line_content={repr((ctx.line_content or '')[:40])}. Backspace и тело пропущены."
                            )
                            self.current_line = current_pass_line + 1
                            self.current_column = 0
                            continue

                    # Удаляем pass (Backspace несколько раз)
                    # Браузер и VS Code: 1 Backspace = 4 пробела (уровень отступа), 4 Backspace на "pass". Итого: 5 + (indent//4).
                    # Блокнот: по символам (indent + 4 пробела + "pass").
                    indent = block['indent']
                    backspace_count = self._target.backspaces_for_pass(self, indent)
                    print(f"    Удаление 'pass' ({backspace_count} Backspace) на строке {self.current_line}")
                    self._log_action("DELETE_PASS", f"Удаление 'pass' для блока '{block_name}': {backspace_count} Backspace. Позиция: строка {self.current_line}, колонка {self.current_column}")
                    
                    for _ in range(backspace_count):
                        self.typer.press_backspace()
                        self._sleep(random.uniform(0.05, 0.15))
                    
                    # В начало строки, чтобы первая строка тела не получила лишний отступ
                    self._sleep(0.05)
                    self._send_vk_atomic(VK_HOME, 0.02)
                    self._sleep(0.05)
                    self.current_column = 0
                    
                    # Печатаем тело блока
                    print(f"    Печать тела ({len(body_lines)} строк)")
                    self._log_action("FILL_BODY_START", f"Начало печати тела блока '{block_name}': {len(body_lines)} строк")
                    
                    body_start_line = self.current_line
                    block_orig_line = block.get('original_line')
                    for idx, body_line in enumerate(body_lines):
                        if self.on_line_start and block_orig_line is not None:
                            try:
                                self.on_line_start(block_orig_line + 1 + idx, body_line)
                            except Exception:
                                pass
                        if self.on_body_line_start:
                            try:
                                self.on_body_line_start(block_name, idx, body_line)
                            except Exception:
                                pass
                        self.typer.dismiss_ide_popup_before_enter = self._should_dismiss_ide_popup()
                        prev_line = body_lines[idx - 1] if idx > 0 else None
                        expected_line = body_start_line + idx
                        ok = self._target.before_fill_line_verify(self, expected_line, body_start_line, idx, prev_line, block)
                        if not ok:
                            self._log_action("FILL_VERIFY_RETRY", f"Проверка строки {expected_line} не совпала по контексту, печатаем с текущей позиции")
                        self._sync_from_bridge_then_home(expected_line_above=prev_line)
                        self._fix_prev_line_indent_if_needed(prev_line)
                        # Очищаем пустую строку с автоотступом только в VS Code (в браузере не трогаем — риск стереть следующий блок)
                        if not self._target.is_browser_mode(self):
                            self._clear_line_if_accumulated_whitespace(min_len=4)
                        if not self._target.is_browser_mode(self):
                            self._ensure_on_correct_line_before_fill(body_line, prev_line=prev_line)
                        self._log_action("FILL_LINE_START", f"Печать строки тела: '{body_line[:50]}...'")
                        r = body_line.rstrip()
                        if r and r[-1] in '{[(':
                            self.typer.type_line(body_line, add_newline=False)
                            self._sleep(0.05)
                            self._target.body_line_after_type_open_brace(self, r, body_line)
                        else:
                            # Печатаем без trailing spaces, иначе в редакторе появятся лишние пробелы (например после """)
                            line_to_type = r if r else body_line
                            if hasattr(self._target, 'remove_docstring_auto_close_after_type'):
                                self.typer.type_line(line_to_type, add_newline=True, before_newline_callback=lambda: self._target.remove_docstring_auto_close_after_type(self, line_to_type))
                            else:
                                self.typer.type_line(line_to_type, add_newline=True)
                        self.last_char = '\n'
                        self.lines_typed_count += 1
                        self.current_line += 1
                        self.current_column = 0
                        # После Enter курсор с автоотступом; Home — в начало строки.
                        self._ensure_start_of_line_after_newline()
                        self._target.after_fill_line_delay(self)
                        self._log_action("FILL_LINE_END", f"Строка тела напечатана. Позиция: {self.current_line}")
                    
                    # Обновляем информацию о конце блока
                    # Без моста (блокнот): позицию считаем строго по математике.
                    # Консервативно считаем, что курсор на последней напечатанной строке (не на следующей),
                    # т.к. последний Enter мог не создать новую строку — иначе навигация попадает на сигнатуру вместо pass.
                    if self._use_bridge_sync():
                        body_end_line = self.current_line - 1
                    else:
                        self._sleep(0.28)
                        body_end_line = body_start_line + len(body_lines) - 1
                        self.current_line = body_end_line  # курсор на последней строке тела (консервативно)
                    block['end_line'] = body_end_line
                    
                    # Рассчитываем смещение для следующих блоков
                    body_lines_count = body_end_line - body_start_line + 1
                    lines_added = body_lines_count - 1  # Заменяем 1 строку pass на body_lines_count строк
                    total_offset += lines_added
                    lines_added_per_block[block_idx] = lines_added
                    
                    print(f"    Заполнение завершено: строки {body_start_line}-{body_end_line}")
                    print(f"    Добавлено строк: {lines_added}, общее смещение: {total_offset}")
                    self._log_action("FILL_BODY_DONE", f"Тело блока '{block_name}' напечатано. Позиция: {body_start_line} → {body_end_line}, добавлено строк: {lines_added}")
                    
                    self._update_status_section()
                    self._sleep(random.uniform(0.3, 0.7))
                
                print(f"\n  Заполнение завершено: {len(blocks_to_fill)} блоков")
                self._log_action("FILL_PHASE_END", f"Фаза заполнения завершена. Заполнено блоков: {len(blocks_to_fill)}")
            else:
                print("  Заполнение блоков не требуется (нет блоков с телом в скелетном режиме)")
            
            # ═══════════════════════════════════════
            # ФАЗА 3: ИМПОРТЫ — только после заполнения блоков (декораторы уже напечатаны в скелете)
            # ═══════════════════════════════════════
            imports_to_insert = getattr(self, 'imports_from_map', [])
            header_lines = getattr(self, 'header_lines', 0)
            num_imports = len(imports_to_insert)
            
            if num_imports > 0:
                print(f"\n--- ФАЗА 3: ИМПОРТЫ (после заполнения блоков) ---")
                self._log_action("INSERT_PHASE_START", f"Вставка импортов ({num_imports})")
                # Целевая строка для первого импорта — сразу после шапки (shebang, encoding)
                insert_line = header_lines + 1
                # Сначала переходим в начало файла (строка 1), затем спускаемся на header_lines
                if self.current_line > 1:
                    self._navigate_up(self.current_line - 1)
                    self.current_line = 1
                    # Без моста (блокнот): один лишний Up и пауза, чтобы гарантированно оказаться на строке 1
                    # (при длинной навигации вверх один Up мог не сработать — тогда Down(2) ведёт на строку 4 и импорты попадают после констант)
                    if not self._use_bridge_sync():
                        self._sleep(0.12)
                        self._navigate_up(1)
                        self._sleep(0.08)
                        self.current_line = 1
                if header_lines > 0:
                    self._navigate_down(header_lines)
                    self.current_line = header_lines + 1
                for imp in imports_to_insert:
                    text = imp.get('content', imp) if isinstance(imp, dict) else imp
                    if self.current_line != insert_line:
                        dist = insert_line - self.current_line
                        if dist > 0:
                            self._navigate_down(dist)
                        else:
                            self._navigate_up(abs(dist))
                    self._log_action("INSERT_IMPORT", f"Вставка импорта на строку {insert_line}: {str(text)[:50]}...")
                    self._insert_line_above(text)
                    insert_line += 1
                print(f"  Вставлено импортов: {num_imports}")
                self._log_action("INSERT_PHASE_END", "Фаза вставки импортов завершена")
            # Финальная фиксация статуса (чтобы “Позиция/символ/строки” точно совпадали)
            self._log_action("PRINT_END", f"Печать завершена. Итоговая позиция: строка {self.current_line}, колонка {self.current_column}")
        
        except KeyboardInterrupt:
            print("\n\nПрервано пользователем!")
        finally:
            elapsed = time.time() - start_time
            print(f"\nВремя: {elapsed:.1f} сек")
            print(f"Символов: {self.typer.stats['chars_typed']}")
            print(f"Строк: {self.typer.stats['lines_typed']}")


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Использование: python code_printer.py <map_file.json>")
        print("\nПример:")
        print("  1. Создай карту: python code_mapper.py my_code.py")
        print("  2. Печатай:      python code_printer.py my_code_map.json")
        sys.exit(1)
    
    map_file = sys.argv[1]
    
    printer = CodePrinter(base_speed=5)
    printer.load_map(map_file)
    printer.print_from_map(initial_delay=5)


if __name__ == "__main__":
    main()
