#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный скрипт - создаёт карту и печатает код
"""

import os
import sys
from typer import CodeMapBuilder, CodePrinter, SqlCodeMapBuilder, detect_from_filepath, detect_from_content, MAP_DIR, LOG_DIR, LOG_FILE, prune_map_dir, get_active_window_display
from typer.cursor_bridge import start as cursor_bridge_start


def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("УМНАЯ ПЕЧАТЬ КОДА")
        print("=" * 60)
        print()
        print("Использование:")
        print("  python run.py <filepath.py>")
        print()
        print("Что делает:")
        print("  1. Анализирует код -> создаёт карту (typer/map/<name>_map.json)")
        print("  2. Печатает код нелинейно (скелет -> детали)")
        print()
        print("Пример:")
        print("  python run.py my_code.py")
        print()
        print("Активное окно (куда курсор / куда попадёт печать):")
        print("  Выводится в этот же терминал один раз перед обратным отсчётом (в ШАГ 2).")
        print("  Отдельная команда для просмотра:")
        print("    python -m typer.active_window        # один раз в терминал")
        print("    python -m typer.active_window --watch   # обновлять каждую секунду в терминале")
        print()
        sys.exit(1)
    
    filepath = sys.argv[1]
    prune_map_dir(MAP_DIR)
    os.makedirs(MAP_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    base_name = os.path.basename(filepath).replace(".py", "").replace(".sql", "").replace(".txt", "").replace(".md", "")
    map_file = os.path.join(MAP_DIR, f"{base_name}_map.json")
    log_file = LOG_FILE
    
    # 1. Определить язык
    lang = detect_from_filepath(filepath)
    if filepath.lower().endswith(".md"):
        with open(filepath, "r", encoding="utf-8") as f:
            lang = detect_from_content(f.read(), filepath)
    
    print("=" * 60)
    print("ШАГ 1: СОЗДАНИЕ КАРТЫ")
    print("=" * 60)
    
    # 2. Использовать маппер для этого языка
    if lang == "sql":
        builder = SqlCodeMapBuilder()
        code_map_data = builder.build_from_file(filepath)
        print(f"  Язык: {code_map_data['language']}")
        print(f"  Строк: {code_map_data['total_lines']}")
        print(f"  План: {len(code_map_data['print_plan'])} шагов")
        builder.save_map(code_map_data, map_file)
    else:
        builder = CodeMapBuilder()
        code_map = builder.build_from_file(filepath)
        print(f"  Язык: {code_map.language}")
        print(f"  Строк: {code_map.total_lines}")
        print(f"  Классов: {len(code_map.classes)}")
        print(f"  Функций: {len(code_map.functions)}")
        builder.save_map(code_map, map_file)
    
    print("\n" + "=" * 60)
    print("ШАГ 2: ПЕЧАТЬ")
    print("=" * 60)
    cursor_bridge_start()  # мост: userscript (Yandex.Code) или расширение (VS Code) шлют сюда позицию
    print("  Куда попадёт печать (окно в фокусе сейчас):", get_active_window_display())
    print()
    
    # Один принтер: в браузере использует мост (Ace), в VS Code — мост если расширение шлёт, иначе Home после Enter
    printer = CodePrinter(base_speed=5, log_file=log_file)
    printer.load_map(map_file)
    printer.print_from_map(initial_delay=5)


if __name__ == "__main__":
    main()

