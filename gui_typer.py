#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI Auto Typer - Простой интерфейс для автопечати кода
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import time
from datetime import datetime
from typer import (
    CodeMapBuilder,
    CodePrinter,
    SqlCodeMapBuilder,
    detect_from_filepath,
    detect_from_content,
    MAP_DIR,
    LOG_DIR,
    LOG_FILE,
    prune_map_dir,
    get_active_window_display,
    get_active_window_type,
    ActiveWindowType as WindowType,
)
from typer.cursor_bridge import (
    start as cursor_bridge_start,
    get_cursor as cursor_bridge_get_cursor,
    get_three_lines as cursor_bridge_get_three_lines,
    get_source as cursor_bridge_get_source,
    get_file_extension as cursor_bridge_get_file_extension,
    get_language_id as cursor_bridge_get_language_id,
)


class AutoTyperGUI:
    """Графический интерфейс для автопечати кода"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Code Typer")
        self.root.geometry("520x580")
        self.root.minsize(480, 520)
        self.root.resizable(True, True)
        self.root.configure(bg="#ecf0f1")
        
        # Переменные
        self.selected_file = tk.StringVar()
        self.map_file = tk.StringVar()
        self.is_running = False
        self.typer_thread = None
        self._active_window_after_id = None  # таймер обновления активного окна
        self._ace_display_after_id = None    # таймер обновления позиции/строки Ace (чаще)
        
        # Создаём UI
        self._create_ui()
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Запуск периодического обновления активного окна (раз в секунду)
        self.root.after(500, self._update_active_window)
        # Позиция и содержимое строки из моста (VS Code, PyCharm, Yandex.Code) — обновляем раз в 400 мс
        self.root.after(400, self._update_ace_display)
        # Мост для позиции курсора: расширение (VS Code/PyCharm) или userscript (Yandex.Code) шлёт сюда позицию и контекст
        prune_map_dir(MAP_DIR)
        cursor_bridge_start()
    
    def _create_ui(self):
        """Создаёт интерфейс"""
        
        # ─────────────────────────────────────
        # Заголовок
        # ─────────────────────────────────────
        
        header_frame = tk.Frame(self.root, bg="#2c3e50", height=52)
        header_frame.pack(side=tk.TOP, fill=tk.X)
        header_frame.pack_propagate(False)
        tk.Label(
            header_frame,
            text="Auto Code Typer",
            font=("Arial", 16, "bold"),
            bg="#2c3e50",
            fg="white"
        ).pack(pady=10)
        
        # Панель кнопок — pack внизу окна сразу, чтобы контент не «отъел» место
        button_bar = tk.Frame(self.root, bg="#ecf0f1", padx=20, pady=12)
        button_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.start_btn = tk.Button(
            button_bar,
            text="СТАРТ",
            command=self._start_typing,
            font=("Arial", 12, "bold"),
            bg="#27ae60",
            fg="white",
            relief=tk.FLAT,
            padx=24,
            pady=10,
            cursor="hand2",
            state=tk.NORMAL,
            activebackground="#229954",
            activeforeground="white"
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8), fill=tk.X, expand=True)
        
        self.stop_btn = tk.Button(
            button_bar,
            text="СТОП",
            command=self._stop_typing,
            font=("Arial", 12, "bold"),
            bg="#e74c3c",
            fg="white",
            relief=tk.FLAT,
            padx=24,
            pady=10,
            cursor="hand2",
            state=tk.DISABLED,
            activebackground="#c0392b",
            activeforeground="white"
        )
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Основной контент — между заголовком и кнопками
        main_frame = tk.Frame(self.root, bg="#ecf0f1", padx=20, pady=12)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Выбор файла
        file_frame = tk.LabelFrame(
            main_frame,
            text=" Файл ",
            font=("Arial", 9, "bold"),
            bg="#ecf0f1",
            padx=8,
            pady=6
        )
        file_frame.pack(fill=tk.X, pady=(0, 8))
        
        # Путь к файлу
        file_entry = tk.Entry(
            file_frame,
            textvariable=self.selected_file,
            font=("Arial", 10),
            state="readonly",
            width=50
        )
        file_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        
        browse_btn = tk.Button(
            file_frame,
            text="Выбрать…",
            command=self._browse_file,
            font=("Arial", 9),
            bg="#3498db",
            fg="white",
            relief=tk.FLAT,
            padx=12,
            pady=2,
            cursor="hand2"
        )
        browse_btn.pack(side=tk.RIGHT)
        
        # Настройки
        settings_frame = tk.LabelFrame(
            main_frame,
            text=" Настройки ",
            font=("Arial", 9, "bold"),
            bg="#ecf0f1",
            padx=8,
            pady=6
        )
        settings_frame.pack(fill=tk.X, pady=(0, 8))
        
        speed_frame = tk.Frame(settings_frame, bg="#ecf0f1")
        speed_frame.pack(fill=tk.X, pady=2)
        tk.Label(speed_frame, text="Скорость:", font=("Arial", 9), bg="#ecf0f1").pack(side=tk.LEFT, padx=(0, 6))
        self.speed_var = tk.IntVar(value=5)
        speed_scale = tk.Scale(
            speed_frame,
            from_=1,
            to=15,
            orient=tk.HORIZONTAL,
            variable=self.speed_var,
            length=180,
            font=("Arial", 8)
        )
        speed_scale.pack(side=tk.LEFT)
        self.speed_label = tk.Label(speed_frame, text="5 сим/с", font=("Arial", 9), fg="#7f8c8d", bg="#ecf0f1")
        self.speed_label.pack(side=tk.LEFT, padx=(6, 0))
        speed_scale.config(command=self._update_speed_label)
        
        delay_frame = tk.Frame(settings_frame, bg="#ecf0f1")
        delay_frame.pack(fill=tk.X, pady=2)
        tk.Label(delay_frame, text="Задержка перед стартом:", font=("Arial", 9), bg="#ecf0f1").pack(side=tk.LEFT, padx=(0, 6))
        self.delay_var = tk.IntVar(value=5)
        tk.Spinbox(delay_frame, from_=0, to=30, textvariable=self.delay_var, width=4, font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Label(delay_frame, text="сек", font=("Arial", 9), bg="#ecf0f1").pack(side=tk.LEFT, padx=(4, 0))
        
        # Статус
        status_frame = tk.LabelFrame(
            main_frame,
            text=" Статус ",
            font=("Arial", 9, "bold"),
            bg="#ecf0f1",
            padx=8,
            pady=6
        )
        status_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.status_label = tk.Label(
            status_frame,
            text="Выберите файл и нажмите СТАРТ.",
            font=("Arial", 9),
            fg="#27ae60",
            anchor="w",
            bg="#ecf0f1"
        )
        self.status_label.pack(fill=tk.X)
        
        self.active_window_label = tk.Label(
            status_frame,
            text="Куда печатать: —",
            font=("Arial", 8),
            fg="#7f8c8d",
            anchor="w",
            bg="#ecf0f1"
        )
        self.active_window_label.pack(fill=tk.X, pady=(2, 0))
        
        self.cursor_position_label = tk.Label(
            status_frame,
            text="Курсор: —",
            font=("Arial", 8),
            fg="#95a5a6",
            anchor="w",
            bg="#ecf0f1"
        )
        self.cursor_position_label.pack(fill=tk.X, pady=(1, 0))
        
        self.line_content_label = tk.Label(
            status_frame,
            text="Строка: —",
            font=("Arial", 8),
            fg="#7f8c8d",
            anchor="w",
            bg="#ecf0f1"
        )
        self.line_content_label.pack(fill=tk.X, pady=(1, 0))
        self.line_above_label = tk.Label(
            status_frame,
            text="Выше: —",
            font=("Arial", 8),
            fg="#95a5a6",
            anchor="w",
            bg="#ecf0f1"
        )
        self.line_above_label.pack(fill=tk.X, pady=(1, 0))
        self.line_below_label = tk.Label(
            status_frame,
            text="Ниже: —",
            font=("Arial", 8),
            fg="#95a5a6",
            anchor="w",
            bg="#ecf0f1"
        )
        self.line_below_label.pack(fill=tk.X, pady=(1, 0))
        
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=400)
        self.progress.pack(fill=tk.X, pady=(6, 0))
    
    def _update_speed_label(self, value):
        """Обновляет label скорости"""
        self.speed_label.config(text=f"{int(value)} сим/с")
    
    def _browse_file(self):
        """Выбор файла"""
        filepath = filedialog.askopenfilename(
            title="Выберите файл с кодом",
            filetypes=[
                ("Все файлы", "*.*"),
                ("Python", "*.py"),
                ("JavaScript", "*.js"),
                ("Text", "*.txt"),
                ("Markdown", "*.md")
            ]
        )
        
        if filepath:
            self.selected_file.set(filepath)
            self.status_label.config(
                text=f"Выбран файл: {os.path.basename(filepath)}",
                fg="#3498db"
            )
    
    def _start_typing(self):
        """Запускает печать"""
        
        if not self.selected_file.get():
            messagebox.showerror(
                "Ошибка",
                "Выберите файл для печати!"
            )
            return
        
        if not os.path.exists(self.selected_file.get()):
            messagebox.showerror(
                "Ошибка",
                "Файл не найден!"
            )
            return
        
        # Блокируем UI
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start(10)
        
        self.status_label.config(
            text="Создание карты кода...",
            fg="#f39c12"
        )
        self.root.update()
        
        # Запускаем в отдельном потоке
        self.typer_thread = threading.Thread(
            target=self._typing_worker,
            daemon=True
        )
        self.typer_thread.start()
    
    def _typing_worker(self):
        """Рабочий поток для печати"""
        
        try:
            filepath = self.selected_file.get()
            os.makedirs(MAP_DIR, exist_ok=True)
            os.makedirs(LOG_DIR, exist_ok=True)
            base_name = os.path.basename(filepath).replace(".py", "").replace(".sql", "").replace(".txt", "").replace(".md", "")
            map_file = os.path.join(MAP_DIR, f"{base_name}_map.json")
            log_file = LOG_FILE
            
            # Шаг 1: Определить язык → выбрать маппер
            lang = detect_from_filepath(filepath)
            if filepath.lower().endswith(".md"):
                with open(filepath, "r", encoding="utf-8") as f:
                    lang = detect_from_content(f.read(), filepath)
            
            # Шаг 2: Создание карты нужным маппером
            self.root.after(0, lambda: self.status_label.config(
                text="Создание карты кода...",
                fg="#f39c12"
            ))
            
            if lang == "sql":
                builder = SqlCodeMapBuilder()
                code_map_data = builder.build_from_file(filepath)
                builder.save_map(code_map_data, map_file)
                status_text = f"Карта SQL создана! Строк: {code_map_data['total_lines']}"
            else:
                builder = CodeMapBuilder()
                code_map = builder.build_from_file(filepath)
                builder.save_map(code_map, map_file)
                status_text = f"Карта создана! Классов: {len(code_map.classes)}, Функций: {len(code_map.functions)}"
            
            self.root.after(0, lambda t=status_text: self.status_label.config(
                text=t,
                fg="#3498db"
            ))
            
            # Шаг 2: Печать — показываем, куда попадёт печать (активное окно сейчас)
            delay = self.delay_var.get()
            try:
                active_display = get_active_window_display()
            except Exception:
                active_display = "—"
            self.root.after(0, lambda d=active_display: self.active_window_label.config(
                text=f"Куда печатать: {d}",
                fg="#2c3e50"
            ))
            
            self.root.after(0, lambda: self.status_label.config(
                text=f"Начало через {delay} сек... Переключитесь в нужное окно!",
                fg="#e67e22"
            ))
            
            # Обратный отсчёт. За 2 секунды до старта определяем, куда печатать (браузер или IDE/блокнот)
            browser_mode = None
            for i in range(delay, 0, -1):
                if not self.is_running:
                    return
                self.root.after(0, lambda i=i: self.status_label.config(
                    text=f"Начало через {i} сек...",
                    fg="#e67e22"
                ))
                time.sleep(1)
                # Когда до старта осталось 2 секунды — фиксируем активное окно
                if i == 2:
                    try:
                        wtype = get_active_window_type()
                        browser_mode = (wtype == WindowType.BROWSER)
                        where = get_active_window_display()
                        self.root.after(0, lambda w=where, b=browser_mode: self.active_window_label.config(
                            text=f"Куда печатать: {w} ({'браузер' if b else 'блокнот/IDE'})",
                            fg="#2c3e50"
                        ))
                    except Exception:
                        pass
            
            if not self.is_running:
                return
            
            self.root.after(0, lambda: self.status_label.config(
                text="Печать!",
                fg="#27ae60"
            ))
            
            printer = CodePrinter(base_speed=self.speed_var.get(), log_file=log_file)
            printer.load_map(map_file)
            printer.print_from_map(initial_delay=0, browser_mode=browser_mode)
            
            if self.is_running:
                self.root.after(0, lambda: self.status_label.config(
                    text="Печать завершена!",
                    fg="#27ae60"
                ))
        
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(
                "Ошибка",
                f"Произошла ошибка:\n{str(e)}"
            ))
            self.root.after(0, lambda: self.status_label.config(
                text="Ошибка при печати",
                fg="#e74c3c"
            ))
        
        finally:
            # Разблокируем UI
            self.root.after(0, self._reset_ui)
    
    def _stop_typing(self):
        """Останавливает печать"""
        self.is_running = False
        self.status_label.config(
            text="Остановка...",
            fg="#e74c3c"
        )
        # UI сбросится в _reset_ui

    def _reset_ui(self):
        """Сбрасывает UI в исходное состояние"""
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress.stop()
        
        if not self.status_label.cget("text").startswith("Ошибка"):
            self.status_label.config(
                text="Готово. Можно снова нажать СТАРТ.",
                fg="#27ae60"
            )
        self.active_window_label.config(text="Куда печатать: —", fg="#7f8c8d")
    
    def _update_active_window(self):
        """Обновляет строку «Куда попадёт печать» и позицию курсора Ace (если userscript шлёт в мост)."""
        if not self.root.winfo_exists():
            return
        try:
            display = get_active_window_display()
            self.active_window_label.config(
                text=f"Куда печатать: {display}",
                fg="#2c3e50"
            )
        except Exception:
            pass
        if self.root.winfo_exists():
            self._active_window_after_id = self.root.after(1000, self._update_active_window)

    def _update_ace_display(self):
        """Обновляет позицию курсора и три строки контекста (выше, текущая, ниже) из моста (VS Code, PyCharm, Yandex.Code)."""
        if not self.root.winfo_exists():
            return
        def _short(s, max_len=55):
            if s is None or s == "":
                return "—"
            t = s.strip()
            return (t[: max_len - 3] + "…") if len(t) > max_len else t
        try:
            pos = cursor_bridge_get_cursor()
            line_above, line_content, line_below = cursor_bridge_get_three_lines()
            source = cursor_bridge_get_source()
            ext = (cursor_bridge_get_file_extension() or "").strip()
            lang = (cursor_bridge_get_language_id() or "").strip()
            format_part = ""
            if ext or lang:
                format_part = "  ·  " + ", ".join(x for x in [ext or None, lang or None] if x)
            source_label = {
                "yandex": "Yandex.Code",
                "hh": "HH.ru",
                "vscode": "VS Code / Cursor",
                "pycharm": "PyCharm",
            }.get(source or "", "Браузер")
            if pos and (pos[0] != 0 or pos[1] != 0):
                self.cursor_position_label.config(
                    text=f"{source_label}: строка {pos[0]}, столбец {pos[1]}{format_part}",
                    fg="#27ae60"
                )
            elif source and pos and pos[0] == 0 and pos[1] == 0:
                self.cursor_position_label.config(
                    text=f"{source_label}: (ожидание редактора){format_part}",
                    fg="#95a5a6"
                )
            else:
                self.cursor_position_label.config(
                    text=f"{source_label}: —{format_part}",
                    fg="#95a5a6"
                )
            self.line_content_label.config(text=f"Строка: {_short(line_content)}", fg="#2c3e50")
            self.line_above_label.config(text=f"Выше: {_short(line_above)}", fg="#95a5a6")
            self.line_below_label.config(text=f"Ниже: {_short(line_below)}", fg="#95a5a6")
        except Exception:
            self.cursor_position_label.config(text="Курсор: —", fg="#95a5a6")
            self.line_content_label.config(text="Строка: —", fg="#7f8c8d")
            self.line_above_label.config(text="Выше: —", fg="#95a5a6")
            self.line_below_label.config(text="Ниже: —", fg="#95a5a6")
        if self.root.winfo_exists():
            self._ace_display_after_id = self.root.after(400, self._update_ace_display)
    
    def _on_close(self):
        """Обработка закрытия окна"""
        if self._active_window_after_id is not None:
            try:
                self.root.after_cancel(self._active_window_after_id)
            except Exception:
                pass
            self._active_window_after_id = None
        if self._ace_display_after_id is not None:
            try:
                self.root.after_cancel(self._ace_display_after_id)
            except Exception:
                pass
            self._ace_display_after_id = None
        if self.is_running:
            if messagebox.askokcancel(
                "Подтверждение",
                "Печать выполняется. Закрыть окно?"
            ):
                self.is_running = False
                self.root.destroy()
        else:
            self.root.destroy()


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

def main():
    root = tk.Tk()
    app = AutoTyperGUI(root)
    
    # Центрируем окно
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    root.mainloop()


if __name__ == "__main__":
    main()

