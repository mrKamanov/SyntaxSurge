# -*- coding: utf-8 -*-
"""
Очистка папки typer/map при запуске приложения: оставляем только N последних карт по дате изменения.
"""

import os
import glob


def prune_map_dir(map_dir: str, keep_max: int = 5) -> int:
    """
    Удаляет старые карты, оставляя не более keep_max самых новых по mtime.
    Возвращает количество удалённых файлов.
    """
    if not os.path.isdir(map_dir):
        return 0
    pattern = os.path.join(map_dir, "*_map.json")
    files = glob.glob(pattern)
    if len(files) <= keep_max:
        return 0
    files_with_mtime = [(f, os.path.getmtime(f)) for f in files]
    files_with_mtime.sort(key=lambda x: x[1], reverse=True)
    to_remove = [f for f, _ in files_with_mtime[keep_max:]]
    removed = 0
    for path in to_remove:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed
