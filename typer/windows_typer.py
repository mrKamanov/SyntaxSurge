#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows Auto Typer - Автопечатальщик для Windows
Поддержка русского языка через SendInput + Unicode
"""

import ctypes
import time
import json
import random
import threading
from ctypes import wintypes
from typing import List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


# ═══════════════════════════════════════
# WINDOWS API КОНСТАНТЫ
# ═══════════════════════════════════════

# Типы ввода
INPUT_KEYBOARD = 1

# Флаги клавиатуры
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Виртуальные коды клавиш
VK_BACK = 0x08      # Backspace
VK_TAB = 0x09       # Tab
VK_RETURN = 0x0D    # Enter
VK_SHIFT = 0x10     # Shift
VK_CONTROL = 0x11   # Ctrl
VK_MENU = 0x12      # Alt
VK_ESCAPE = 0x1B    # Escape
VK_SPACE = 0x20     # Space
VK_LEFT = 0x25      # Left Arrow
VK_UP = 0x26        # Up Arrow
VK_RIGHT = 0x27     # Right Arrow
VK_DOWN = 0x28      # Down Arrow
VK_DELETE = 0x2E    # Delete


# ═══════════════════════════════════════
# WINDOWS API СТРУКТУРЫ
# ═══════════════════════════════════════

class KEYBDINPUT(ctypes.Structure):
    """Структура для клавиатурного ввода"""
    _fields_ = [
        ("wVk", wintypes.WORD),           # Виртуальный код клавиши
        ("wScan", wintypes.WORD),         # Скан-код
        ("dwFlags", wintypes.DWORD),      # Флаги
        ("time", wintypes.DWORD),         # Время
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))  # Доп. инфо
    ]


class MOUSEINPUT(ctypes.Structure):
    """Структура для мыши (нужна для union)"""
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]


class HARDWAREINPUT(ctypes.Structure):
    """Структура для hardware (нужна для union)"""
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]


class INPUT_UNION(ctypes.Union):
    """Union для разных типов ввода"""
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT)
    ]


class INPUT(ctypes.Structure):
    """Главная структура INPUT"""
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]


# ═══════════════════════════════════════
# WINDOWS API ФУНКЦИИ
# ═══════════════════════════════════════

# Загружаем SendInput из user32.dll
SendInput = ctypes.windll.user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
SendInput.restype = wintypes.UINT


# ═══════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════

@dataclass
class TypingConfig:
    """Настройки печати (ориентир: 40–70 слов/мин, ~1 токен/сек)"""
    # Скорость: 40–70 WPM ≈ 4–6 символов/сек (слово ~5 символов)
    base_speed: float = 5.0
    
    # Вариация скорости ±20–30%
    speed_variation: float = 0.25
    
    # Flight time (между клавишами): 50–400 мс, + по расстоянию (A–Z max)
    flight_time_range: tuple = (0.05, 0.40)
    
    # Dwell time (длительность нажатия): 40–200 мс, пробел длиннее
    dwell_time_ms: tuple = (50, 150)
    dwell_time_space_ms: tuple = (80, 200)  # пробел дольше
    dwell_time_mu_ms: float = 100.0
    dwell_time_sigma_ms: float = 25.0
    
    # Разная скорость по словам (множитель задержки)
    word_speed_range: tuple = (0.70, 1.30)
    # Короткие/частые ключевые слова печатаются быстрее (if, def, for, return и т.д.)
    fast_word_speed_range: tuple = (0.78, 0.92)
    
    # Пауза перед словом (inter-word): 200–600 мс, длиннее для размышлений
    pause_before_word: tuple = (0.20, 0.60)
    # Короткие паузы внутри слова (intra-word): 50–150 мс, вероятность 5%
    intra_word_pause_prob: float = 0.05
    intra_word_pause: tuple = (0.05, 0.15)
    
    # Пауза после точки: 500–2000 мс
    pause_after_period: tuple = (0.50, 2.0)
    
    # Ритмичность: вариабельность интервалов (CV 0.2–0.4), корреляция последовательных задержек ~0.1–0.3
    rhythm_cv: float = 0.30  # коэффициент вариации: delay += gauss(0, base * cv)
    rhythm_correlation: float = 0.2  # смесь с предыдущей задержкой
    
    # Мультифрактальность: паузы дольше в начале предложений (первые N символов)
    sentence_start_slowdown: float = 1.12
    sentence_start_chars: int = 2
    
    # Усталость: +0.1–2% за клавишу, max 1.5–2.0x; восстановление 0.001/сек во время пауз
    fatigue_enabled: bool = True
    fatigue_start_after_chars: int = 400
    fatigue_increase_per_key: float = 0.001  # 0.0005–0.002
    fatigue_max_slowdown: float = 1.5  # max множитель задержки (1.5–2.0x)
    fatigue_recovery_per_sec: float = 0.001  # во время пауз
    fatigue_recovery_per_thinking: float = 0.08  # фиксированно за паузу «думает»
    
    # Пауза "вчитался"
    pause_reading_prob: float = 0.14
    pause_reading: tuple = (0.2, 0.65)
    
    # Паузы (в секундах)
    pause_after_line: tuple = (0.1, 0.3)
    pause_after_block: tuple = (0.5, 1.5)
    pause_thinking: tuple = (1.0, 3.0)
    
    # Опечатки
    enable_typos: bool = True
    typo_probability: float = 0.03
    typo_fix_delay: tuple = (0.3, 0.8)
    
    # Backspace: +100–200 мс после нажатия
    backspace_extra_delay: tuple = (0.10, 0.20)
    # Повтор символа (double-press): вероятность 1%
    double_press_prob: float = 0.01
    # Чередование пальцев: 3+ подряд одной рукой — замедление 20% с вероятностью 5–10%
    finger_alternation_prob: float = 0.07
    finger_alternation_slowdown: float = 1.20
    # Асимметрия рук: правая быстрее на 10–15%, левая пауза дольше
    hand_asymmetry_right: float = 0.90
    hand_asymmetry_left: float = 1.08
    # Burstiness: кластеры 3–5 символов, пауза 300–800 мс между кластерами
    burst_size_range: tuple = (3, 6)
    burst_pause: tuple = (0.30, 0.80)
    # Биграммы/триграммы: частые пары быстрее (80–250 мс), редкие/дальние — медленнее
    digraph_fast_mult: float = 0.88
    digraph_slow_mult: float = 1.12
    
    human_factor: float = 1.0
    # Событие паузы: когда установлено (set), печать ждёт; clear() — продолжить
    pause_event: Optional[threading.Event] = field(default=None, repr=False)
    # Список из одного bool: [True] когда тайпер реально стоит в паузе (в цикле ожидания). GUI читает, чтобы не принимать повторные нажатия до остановки.
    paused_now: Optional[list] = field(default=None, repr=False)
    # Событие прерывания: когда set(), печать останавливается (raise TyperAborted).
    abort_event: Optional[threading.Event] = field(default=None, repr=False)


class TyperAborted(Exception):
    """Прерывание автопечати по запросу пользователя (повторное нажатие «Печать»)."""
    pass


# ═══════════════════════════════════════
# ГЛАВНЫЙ КЛАСС
# ═══════════════════════════════════════

class WindowsTyper:
    """
    Автопечатальщик для Windows
    Поддерживает Unicode (русский, украинский и т.д.)
    """
    
    def __init__(self, config: TypingConfig = None, log_file: str = None):
        self.config = config or TypingConfig()
        self._pause_event = getattr(self.config, 'pause_event', None)
        self._paused_now = getattr(self.config, 'paused_now', None)
        self._abort_event = getattr(self.config, 'abort_event', None)
        self._typing_line_no_pause = False  # True = не проверять паузу до конца строки
        self.stats = {
            'chars_typed': 0,
            'lines_typed': 0,
            'typos_made': 0,
            'time_elapsed': 0.0
        }
        self.log_file = log_file  # Файл для логирования (передается из CodePrinter)
        self.current_char_index = 0  # Индекс текущего символа в строке
        
        # Разная скорость по словам: множитель для текущего слова
        self._current_word_speed_factor = 1.0
        self._last_char_was_word = False
        
        # Усталость: 0 = бодрый, 1 = максимальное замедление
        self._fatigue = 0.0
        
        # Ритмичность: предыдущая задержка для корреляции
        self._last_delay: float = 0.20
        
        # Начало предложения: первые N символов чуть медленнее
        self._sentence_start_chars_remaining: int = 0
        
        # Расположение клавиш (QWERTY): множитель задержки — дальние/неудобные печатаются медленнее
        self._key_position_factor = {
            'a': 0.88, 's': 0.88, 'd': 0.90, 'f': 0.88, 'g': 0.90,
            'h': 0.88, 'j': 0.88, 'k': 0.90, 'l': 0.88,
            'q': 1.12, 'w': 0.98, 'e': 0.92, 'r': 0.94, 't': 0.96,
            'y': 0.96, 'u': 0.94, 'i': 0.92, 'o': 0.98, 'p': 1.10,
            'z': 1.08, 'x': 1.02, 'c': 0.98, 'v': 0.96, 'b': 1.02,
            'n': 0.98, 'm': 1.02,
            ' ': 0.90,
            '1': 1.18, '2': 1.14, '3': 1.12, '4': 1.10, '5': 1.10,
            '6': 1.10, '7': 1.10, '8': 1.12, '9': 1.14, '0': 1.18,
        }
        
        self._fast_words = frozenset({
            'if', 'in', 'is', 'or', 'as',
            'def', 'for', 'and', 'not', 'pass', 'try', 'else', 'from', 'with',
            'return', 'True', 'False', 'None', 'elif', 'class', 'while',
        })
        
        self._key_hand: dict = {}
        for k in '12345qwertasdfgzxcvb':
            self._key_hand[k] = 'left'
        for k in '67890yuiophjklnm':
            self._key_hand[k] = 'right'
        self._key_hand[' '] = 'right'
        self._last_typed_char: str = ''
        self._consecutive_same_hand: int = 0
        self._last_hand: Optional[str] = None
        self._burst_count: int = 0
        self._burst_target: int = 4
        
        self.nearby_keys = {
            'a': 'sqwz', 's': 'adwexz', 'd': 'sfwerc', 'f': 'dgrtvc',
            'g': 'fhtyb', 'h': 'gjyun', 'j': 'hkuim', 'k': 'jloim',
            'l': 'kop', 'q': 'wa', 'w': 'qase', 'e': 'wsdr',
            'r': 'edft', 't': 'rfgy', 'y': 'tghu', 'u': 'yhji',
            'i': 'ujko', 'o': 'iklp', 'p': 'ol', 'z': 'asx',
            'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb', 'b': 'vghn',
            'n': 'bhjm', 'm': 'njk',
            'а': 'пр', 'б': 'ью', 'в': 'ап', 'г': 'нш', 'д': 'лж',
            'е': 'нк', 'ж': 'дэ', 'з': 'щх', 'и': 'мт', 'й': 'цф',
            'к': 'ен', 'л': 'од', 'м': 'ис', 'н': 'гек', 'о': 'лр',
            'п': 'ав', 'р': 'оп', 'с': 'мч', 'т': 'иь', 'у': 'цк',
            'ф': 'йы', 'х': 'зъ', 'ц': 'уй', 'ч': 'сщ', 'ш': 'гщ',
            'щ': 'шзч', 'ы': 'фв', 'ь': 'тб', 'э': 'жъ', 'ю': 'бь',
            'я': 'чф',
        }
    
    def _log_action(self, action_type: str, message: str):
        if not self.log_file:
            return
        try:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            log_entry = f"[{timestamp}] [{action_type}] {message}\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception:
            pass
    
    def _send_unicode_char(self, char: str, key_up: bool = False):
        action = "KEY_UP" if key_up else "KEY_DOWN"
        char_repr = repr(char) if char.isprintable() or char in '\n\t' else f"\\x{ord(char):02x}"
        self._log_action(action, f"Unicode символ: {char_repr} (код: {ord(char)})")
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = 0
        inp.union.ki.wScan = ord(char)
        inp.union.ki.dwFlags = KEYEVENTF_UNICODE
        if key_up:
            inp.union.ki.dwFlags |= KEYEVENTF_KEYUP
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = None
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    
    def _send_virtual_key(self, vk_code: int, key_up: bool = False):
        vk_names = {
            VK_BACK: "BACKSPACE", VK_TAB: "TAB", VK_RETURN: "ENTER",
            VK_SHIFT: "SHIFT", VK_CONTROL: "CONTROL", VK_MENU: "ALT",
            VK_ESCAPE: "ESCAPE", VK_SPACE: "SPACE",
            VK_LEFT: "LEFT_ARROW", VK_UP: "UP_ARROW", VK_RIGHT: "RIGHT_ARROW",
            VK_DOWN: "DOWN_ARROW", VK_DELETE: "DELETE",
        }
        key_name = vk_names.get(vk_code, f"VK_{vk_code:02X}")
        action = "KEY_UP" if key_up else "KEY_DOWN"
        self._log_action(action, f"Виртуальная клавиша: {key_name} (код: 0x{vk_code:02X})")
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk_code
        inp.union.ki.wScan = 0
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = None
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    
    def _get_dwell_time_sec(self, char: str = '') -> float:
        if char == ' ':
            lo_ms, hi_ms = getattr(self.config, 'dwell_time_space_ms', (80, 200))
        else:
            lo_ms, hi_ms = getattr(self.config, 'dwell_time_ms', (50, 150))
        mu = (lo_ms + hi_ms) / 2.0
        sigma = (hi_ms - lo_ms) / 6.0
        ms = random.gauss(mu, sigma)
        ms = max(lo_ms, min(hi_ms, ms))
        return ms / 1000.0

    def _check_abort(self) -> None:
        if self._abort_event and self._abort_event.is_set():
            raise TyperAborted()

    def _wait_while_paused(self) -> None:
        """Ждать, пока пауза не снимется. Во время печати строки (_typing_line_no_pause) не ждём — пауза сработает в конце строки."""
        if getattr(self, '_typing_line_no_pause', False):
            return
        self._check_abort()
        if not self._pause_event or not self._pause_event.is_set():
            return
        if self._paused_now is not None:
            self._paused_now[0] = True
        try:
            while self._pause_event and self._pause_event.is_set():
                self._check_abort()
                time.sleep(0.05)
        finally:
            if self._paused_now is not None:
                self._paused_now[0] = False

    def _sleep(self, sec: float) -> None:
        """Сон с учётом паузы и прерывания. Во время печати строки (_typing_line_no_pause) паузу не проверяем."""
        if getattr(self, '_typing_line_no_pause', False):
            elapsed = 0.0
            while elapsed < sec:
                self._check_abort()
                chunk = min(0.05, sec - elapsed)
                time.sleep(chunk)
                elapsed += chunk
            return
        self._check_abort()
        while self._pause_event and self._pause_event.is_set():
            self._check_abort()
            time.sleep(0.05)
        elapsed = 0.0
        while elapsed < sec:
            self._check_abort()
            if self._pause_event and self._pause_event.is_set():
                while self._pause_event and self._pause_event.is_set():
                    self._check_abort()
                    time.sleep(0.05)
            chunk = min(0.05, sec - elapsed)
            time.sleep(chunk)
            elapsed += chunk

    def press_key(self, char: str):
        """Отправка клавиши атомарно: между key_down и key_up пауза не проверяется, чтобы не потерять символ."""
        self._wait_while_paused()
        dwell = self._get_dwell_time_sec(char)
        special_keys = {'\n': VK_RETURN, '\t': VK_TAB, '\b': VK_BACK}
        if char in special_keys:
            vk = special_keys[char]
            self._send_virtual_key(vk, key_up=False)
            time.sleep(dwell)
            self._send_virtual_key(vk, key_up=True)
        else:
            self._send_unicode_char(char, key_up=False)
            time.sleep(dwell)
            self._send_unicode_char(char, key_up=True)
    
    def press_backspace(self, count: int = 1):
        for _ in range(count):
            self._wait_while_paused()
            self._send_virtual_key(VK_BACK, key_up=False)
            time.sleep(0.02)
            self._send_virtual_key(VK_BACK, key_up=True)
            self._sleep(0.05)
    
    def press_enter(self):
        """Enter атомарно: между key_down и key_up пауза не проверяется, чтобы не потерять переход на новую строку."""
        self._wait_while_paused()
        self._send_virtual_key(VK_RETURN, key_up=False)
        time.sleep(0.01)
        self._send_virtual_key(VK_RETURN, key_up=True)
    
    def _is_word_char(self, char: str) -> bool:
        return char.isalnum() or char == '_'
    
    def _extract_word_at(self, line: str, start: int) -> str:
        word = []
        for i in range(start, len(line)):
            c = line[i]
            if self._is_word_char(c):
                word.append(c)
            else:
                break
        return ''.join(word)
    
    def _calculate_delay(self, char: str, prev_char: str = '') -> float:
        base_delay = 1.0 / self.config.base_speed
        key_lower = char.lower() if len(char) == 1 else ''
        if key_lower in self._key_position_factor:
            base_delay *= self._key_position_factor[key_lower]
        else:
            slow_chars = {
                '{': 1.25, '}': 1.25, '[': 1.18, ']': 1.18,
                '(': 1.12, ')': 1.12, ':': 1.15, '=': 1.10,
                '@': 1.22, '#': 1.18, '$': 1.22, '%': 1.20,
                '.': 1.05, ',': 1.08, '_': 1.10, '!': 1.15,
                '?': 1.12, '"': 1.12, "'": 1.08, '\\': 1.15, '/': 1.12,
            }
            base_delay *= slow_chars.get(char, 1.08)
        base_delay *= self._current_word_speed_factor
        current_hand = self._key_hand.get(key_lower)
        if current_hand == 'right':
            base_delay *= getattr(self.config, 'hand_asymmetry_right', 0.90)
        elif current_hand == 'left':
            base_delay *= getattr(self.config, 'hand_asymmetry_left', 1.08)
        if prev_char:
            prev_hand = self._key_hand.get(prev_char.lower() if len(prev_char) == 1 else '')
            if current_hand and prev_hand:
                if current_hand == prev_hand:
                    base_delay *= getattr(self.config, 'digraph_slow_mult', 1.12)
                else:
                    base_delay *= getattr(self.config, 'digraph_fast_mult', 0.88)
        if (current_hand and self._last_hand == current_hand and
                self._consecutive_same_hand >= 3 and
                random.random() < getattr(self.config, 'finger_alternation_prob', 0.07)):
            base_delay *= getattr(self.config, 'finger_alternation_slowdown', 1.20)
        if getattr(self.config, 'fatigue_enabled', True) and self._fatigue > 0:
            cfg = self.config
            slowdown = 1.0 + self._fatigue * (getattr(cfg, 'fatigue_max_slowdown', 1.5) - 1.0)
            base_delay *= slowdown
        if self.config.speed_variation > 0:
            variation = random.uniform(-self.config.speed_variation, self.config.speed_variation)
            base_delay *= (1 + variation)
        base_delay *= self.config.human_factor
        if self._sentence_start_chars_remaining > 0:
            base_delay *= getattr(self.config, 'sentence_start_slowdown', 1.12)
        cv = getattr(self.config, 'rhythm_cv', 0.30)
        if cv > 0:
            noise = random.gauss(0, base_delay * cv)
            base_delay = max(0.02, base_delay + noise)
        rho = getattr(self.config, 'rhythm_correlation', 0.2)
        if rho > 0 and self._last_delay > 0:
            base_delay = (1 - rho) * base_delay + rho * self._last_delay
        self._last_delay = base_delay
        flight_lo, flight_hi = getattr(self.config, 'flight_time_range', (0.05, 0.40))
        base_delay = max(flight_lo, min(flight_hi, base_delay))
        return max(0.02, base_delay)
    
    def _recover_fatigue(self, pause_sec: float):
        if not getattr(self.config, 'fatigue_enabled', True) or pause_sec <= 0:
            return
        rate = getattr(self.config, 'fatigue_recovery_per_sec', 0.001)
        self._fatigue = max(0.0, self._fatigue - rate * pause_sec)
        self._log_action("FATIGUE_RECOVERY", f"Восстановление за {pause_sec:.2f} сек. Усталость: {self._fatigue:.2f}")
    
    def notify_thinking_pause(self):
        if not getattr(self.config, 'fatigue_enabled', True):
            return
        recovery = getattr(self.config, 'fatigue_recovery_per_thinking', 0.08)
        self._fatigue = max(0.0, self._fatigue - recovery)
        self._log_action("FATIGUE_RECOVERY", f"Восстановление после паузы. Усталость: {self._fatigue:.2f}")
    
    def _make_typo(self, char: str) -> Optional[str]:
        char_lower = char.lower()
        if char_lower in self.nearby_keys:
            nearby = self.nearby_keys[char_lower]
            typo = random.choice(nearby)
            return typo.upper() if char.isupper() else typo
        return None
    
    def _should_make_typo(self) -> bool:
        if not self.config.enable_typos:
            return False
        return random.random() < self.config.typo_probability
    
    def type_char(self, char: str, line: Optional[str] = None, char_index: Optional[int] = None):
        self._wait_while_paused()
        char_repr = repr(char) if char.isprintable() or char in '\n\t' else f"\\x{ord(char):02x}"
        self._log_action("TYPE_CHAR_START", f"Печать символа: {char_repr} (индекс в строке: {self.current_char_index})")
        if self._should_make_typo() and char.isalpha():
            typo = self._make_typo(char)
            if typo:
                self._log_action("TYPO", f"Сделана опечатка: '{char}' → '{typo}'")
                self.press_key(typo)
                pause_time = random.uniform(0.2, 0.5)
                self._log_action("PAUSE", f"Пауза после опечатки: {pause_time:.3f} сек")
                self._sleep(pause_time)
                self._log_action("BACKSPACE", "Удаление опечатки (Backspace)")
                self.press_backspace()
                bs_extra = random.uniform(*getattr(self.config, 'backspace_extra_delay', (0.10, 0.20)))
                self._sleep(bs_extra)
                fix_delay = random.uniform(*self.config.typo_fix_delay)
                self._log_action("PAUSE", f"Пауза после исправления: {fix_delay:.3f} сек")
                self._sleep(fix_delay)
                self.stats['typos_made'] += 1
        if self.current_char_index == 0:
            self._sentence_start_chars_remaining = getattr(self.config, 'sentence_start_chars', 2)
        is_word = self._is_word_char(char)
        if is_word and not self._last_char_was_word:
            pause_w = random.uniform(*getattr(self.config, 'pause_before_word', (0.20, 0.80)))
            self._log_action("PAUSE_BEFORE_WORD", f"Пауза перед словом: {pause_w:.2f} сек")
            self._sleep(pause_w)
            self._recover_fatigue(pause_w)
            if line is not None and char_index is not None:
                word = self._extract_word_at(line, char_index)
                if word and word in self._fast_words:
                    lo, hi = getattr(self.config, 'fast_word_speed_range', (0.78, 0.92))
                    self._current_word_speed_factor = random.uniform(lo, hi)
                    self._log_action("WORD_SPEED", f"Быстрое слово «{word}», множитель: {self._current_word_speed_factor:.2f}")
                else:
                    lo, hi = getattr(self.config, 'word_speed_range', (0.70, 1.30))
                    self._current_word_speed_factor = random.uniform(lo, hi)
                    self._log_action("WORD_SPEED", f"Новое слово, множитель: {self._current_word_speed_factor:.2f}")
            else:
                lo, hi = getattr(self.config, 'word_speed_range', (0.70, 1.30))
                self._current_word_speed_factor = random.uniform(lo, hi)
                self._log_action("WORD_SPEED", f"Новое слово, множитель: {self._current_word_speed_factor:.2f}")
        self._last_char_was_word = is_word
        if is_word and self._last_char_was_word:
            if random.random() < getattr(self.config, 'intra_word_pause_prob', 0.05):
                ip = random.uniform(*getattr(self.config, 'intra_word_pause', (0.05, 0.15)))
                self._log_action("INTRA_WORD_PAUSE", f"Пауза внутри слова: {ip:.2f} сек")
                self._sleep(ip)
        if getattr(self.config, 'fatigue_enabled', True):
            start = getattr(self.config, 'fatigue_start_after_chars', 400)
            if self.stats['chars_typed'] >= start:
                inc = getattr(self.config, 'fatigue_increase_per_key', 0.001)
                self._fatigue = min(1.0, self._fatigue + inc)
        delay = self._calculate_delay(char, prev_char=self._last_typed_char)
        self._sentence_start_chars_remaining = max(0, self._sentence_start_chars_remaining - 1)
        self._log_action("CHAR_DELAY", f"Задержка перед символом '{char_repr}': {delay:.3f} сек")
        self.press_key(char)
        self._sleep(delay)
        if ((char.isalnum() or char in ' _') and
                random.random() < getattr(self.config, 'double_press_prob', 0.01)):
            self._log_action("DOUBLE_PRESS", f"Повтор символа '{char_repr}', исправление Backspace")
            self.press_key(char)
            self.press_backspace()
            self._sleep(random.uniform(*getattr(self.config, 'backspace_extra_delay', (0.10, 0.20))))
        self._burst_count += 1
        if self._burst_count >= self._burst_target:
            burst_pause = random.uniform(*getattr(self.config, 'burst_pause', (0.30, 0.80)))
            self._log_action("BURST_PAUSE", f"Пауза после кластера: {burst_pause:.2f} сек")
            self._sleep(burst_pause)
            self._recover_fatigue(burst_pause)
            self._burst_count = 0
            lo, hi = getattr(self.config, 'burst_size_range', (3, 6))
            self._burst_target = random.randint(lo, hi)
        key_lower = char.lower() if len(char) == 1 else ''
        current_hand = self._key_hand.get(key_lower)
        if current_hand:
            if current_hand == self._last_hand:
                self._consecutive_same_hand += 1
            else:
                self._consecutive_same_hand = 1
            self._last_hand = current_hand
        else:
            self._consecutive_same_hand = 0
            self._last_hand = None
        self._last_typed_char = char
        if char == '.':
            pause_p = random.uniform(*getattr(self.config, 'pause_after_period', (0.50, 2.0)))
            self._log_action("PAUSE_AFTER_PERIOD", f"Пауза после точки: {pause_p:.2f} сек")
            self._sleep(pause_p)
            self._recover_fatigue(pause_p)
            self._sentence_start_chars_remaining = getattr(self.config, 'sentence_start_chars', 2)
        self.stats['chars_typed'] += 1
        self.current_char_index += 1
        self._log_action("TYPE_CHAR_END", f"Символ '{char_repr}' напечатан. Всего символов: {self.stats['chars_typed']}")
    
    def type_line(self, line: str, add_newline: bool = True, before_newline_callback: Optional[Callable[[], None]] = None):
        self._typing_line_no_pause = True
        try:
            self.current_char_index = 0
            self._last_char_was_word = False
            lo, hi = getattr(self.config, 'burst_size_range', (3, 6))
            self._burst_target = random.randint(lo, hi)
            self._burst_count = 0
            self._log_action("TYPE_LINE_START", f"Начало печати строки: '{line}' (длина: {len(line)} символов, add_newline={add_newline})")
            for i, char in enumerate(line):
                self.current_char_index = i
                self.type_char(char, line=line, char_index=i)
            if add_newline:
                if before_newline_callback is not None:
                    before_newline_callback()
                if getattr(self, "dismiss_ide_popup_before_enter", False):
                    self._log_action("PRESS_ESCAPE", "Закрытие окошка подсказок IDE перед Enter")
                    self._send_virtual_key(VK_ESCAPE, key_up=False)
                    time.sleep(0.03)
                    self._send_virtual_key(VK_ESCAPE, key_up=True)
                    self._sleep(0.05)
                self._log_action("PRESS_ENTER", "Нажатие Enter в конце строки")
                self.press_enter()
                pause_time = random.uniform(*self.config.pause_after_line)
                self._log_action("PAUSE", f"Пауза после строки: {pause_time:.3f} сек")
                self._sleep(pause_time)
                self._recover_fatigue(pause_time)
                prob = getattr(self.config, 'pause_reading_prob', 0.14)
                if prob > 0 and random.random() < prob:
                    reading = random.uniform(*getattr(self.config, 'pause_reading', (0.2, 0.65)))
                    self._log_action("PAUSE_READING", f"Пауза «вчитался»: {reading:.2f} сек")
                    self._sleep(reading)
                    self._recover_fatigue(reading)
            self.stats['lines_typed'] += 1
            self._log_action("TYPE_LINE_END", f"Строка напечатана. Всего строк: {self.stats['lines_typed']}")
        finally:
            self._typing_line_no_pause = False
            self._wait_while_paused()
    
    def type_text(self, text: str):
        lines = text.split('\n')
        for i, line in enumerate(lines):
            is_last = (i == len(lines) - 1)
            self.type_line(line, add_newline=not is_last)
    
    def type_from_map(self, map_file: str, initial_delay: int = 5):
        with open(map_file, 'r', encoding='utf-8') as f:
            code_map = json.load(f)
        print("=" * 60)
        print("WINDOWS AUTO TYPER")
        print("=" * 60)
        print(f"Язык: {code_map['language']}")
        print(f"Символов: {code_map['total_characters']}")
        print(f"Строк: {code_map['total_lines']}")
        print("=" * 60)
        print(f"\nНачало через {initial_delay} сек...")
        print("Переключитесь на целевое окно!")
        print("Для отмены: Ctrl+C")
        for i in range(initial_delay, 0, -1):
            print(f"{i}...")
            self._sleep(1)
        print("Печать!")
        start_time = time.time()
        current_line = 1
        try:
            symbols = code_map['symbols']
            if isinstance(symbols[0], list):
                for sym in symbols:
                    char, line, col = sym[0], sym[1], sym[2]
                    if line > current_line:
                        for _ in range(line - current_line):
                            self.press_enter()
                            self._sleep(random.uniform(*self.config.pause_after_line))
                        current_line = line
                    if char != '\n':
                        self.type_char(char)
            else:
                for sym in symbols:
                    char = sym['c']
                    line = sym['l']
                    if line > current_line:
                        for _ in range(line - current_line):
                            self.press_enter()
                            self._sleep(random.uniform(*self.config.pause_after_line))
                        current_line = line
                    if char != '\n':
                        self.type_char(char)
        except KeyboardInterrupt:
            print("\n\nПрервано пользователем!")
        finally:
            self.stats['time_elapsed'] = time.time() - start_time
            self._print_stats()
    
    def type_from_file(self, filepath: str, initial_delay: int = 5):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        print("=" * 60)
        print("WINDOWS AUTO TYPER")
        print("=" * 60)
        print(f"Файл: {filepath}")
        print(f"Символов: {len(content)}")
        print(f"Строк: {content.count(chr(10)) + 1}")
        print("=" * 60)
        print(f"\nНачало через {initial_delay} сек...")
        print("Переключитесь на целевое окно!")
        print("Для отмены: Ctrl+C")
        for i in range(initial_delay, 0, -1):
            print(f"{i}...")
            self._sleep(1)
        print("Печать!")
        start_time = time.time()
        try:
            self.type_text(content)
        except KeyboardInterrupt:
            print("\n\nПрервано пользователем!")
        finally:
            self.stats['time_elapsed'] = time.time() - start_time
            self._print_stats()
    
    def _print_stats(self):
        print("\n" + "=" * 60)
        print("СТАТИСТИКА")
        print("=" * 60)
        print(f"Напечатано символов: {self.stats['chars_typed']}")
        print(f"Напечатано строк: {self.stats['lines_typed']}")
        print(f"Опечаток сделано: {self.stats['typos_made']}")
        print(f"Время: {self.stats['time_elapsed']:.1f} сек")
        if self.stats['time_elapsed'] > 0:
            speed = self.stats['chars_typed'] / self.stats['time_elapsed']
            print(f"Скорость: {speed:.1f} символов/сек")
        print("=" * 60)


if __name__ == "__main__":
    def main():
        print("WINDOWS AUTO TYPER v1.0")
        print("Запуск модуля: используйте run.py или gui_typer.py")
    main()
