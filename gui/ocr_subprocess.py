# -*- coding: utf-8 -*-
"""
Скрипт для запуска OCR в отдельном процессе (чтобы падение onnxruntime не роняло основное приложение).
Запуск: python -m gui.ocr_subprocess <путь_к_изображению>
Вывод: распознанный текст в stdout (UTF-8), ошибки в stderr, код выхода 0 = успех, 1 = ошибка.
"""
from __future__ import annotations

import re
import sys
import os

# Частые ошибки OCR (кириллица): неверно распознанное слово → правильное.
# Можно дополнять по мере появления типичных ошибок.
_OCR_FIX_WORDS: dict[str, str] = {
    "ОНЖОНЕОВ": "возможно",
    "онжонеов": "возможно",
    "возмолсно": "возможно",
    "вожможно": "возможно",
    "напримео": "например",
    "канфигурациии": "конфигурации",
}


def _fix_ocr_word_errors(text: str) -> str:
    """Заменяет известные типичные ошибки OCR по словам (целое слово)."""
    def replace_word(match: re.Match) -> str:
        w = match.group(0)
        return _OCR_FIX_WORDS.get(w, _OCR_FIX_WORDS.get(w.lower(), w))
    # Слова (последовательность букв) — заменяем только если есть в словаре
    return re.sub(r"[а-яА-ЯёЁa-zA-Z0-9]+", replace_word, text)


def _is_block_start(line: str) -> bool:
    """Строка начинает новый блок (заголовок, маркер списка) — не склеивать с предыдущим."""
    s = line.strip()
    if not s:
        return True
    if s.startswith("##"):
        return True
    # Один символ * или ** — маркер списка, новая строка
    if s == "*" or s == "**":
        return True
    return False


def _merge_ocr_lines(raw: str) -> str:
    """Склеивает построчный вывод OCR (слово на строку) в читаемые предложения и абзацы."""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return raw
    out = []
    i = 0
    while i < len(lines):
        parts = [lines[i]]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if _is_block_start(nxt):
                break
            prev = parts[-1]
            # Конец предложения — новая строка вывода
            if prev.endswith((".", "!", "?", ":")) and len(prev) > 2:
                break
            if len(prev) > 55:
                break
            parts.append(nxt)
            i += 1
        out.append(" ".join(parts))
    return "\n".join(out)


def _format_by_boxes(result) -> str | None:
    """
    Форматирует вывод по координатам боксов: строки как на изображении,
    абзацы при большом вертикальном отступе. Возвращает None при недоступных boxes.
    """
    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    if boxes is None or txts is None or len(txts) == 0:
        return None
    n = len(txts)
    try:
        n_boxes = getattr(boxes, "shape", (0,))[0] if hasattr(boxes, "shape") else len(boxes)
        if n_boxes != n:
            return None
    except Exception:
        return None

    def _ys(pts):
        if hasattr(pts, "__getitem__") and len(pts) >= 4:
            return [float(pts[k][1]) for k in range(4)]
        return []
    def _coords(pts):
        xs = [float(pts[k][0]) for k in range(4)] if hasattr(pts, "__getitem__") and len(pts) >= 4 else [0.0]
        ys = _ys(pts)
        return (sum(xs) / 4, sum(ys) / 4) if xs and ys else (0.0, 0.0)

    line_heights = []
    for i in range(n):
        pts = boxes[i]
        ys = _ys(pts)
        if ys:
            line_heights.append(max(ys) - min(ys))
    line_heights.sort()
    median_h = line_heights[len(line_heights) // 2] if line_heights else 20.0
    same_line_threshold = max(median_h * 0.55, 5.0)
    paragraph_gap = median_h * 1.4

    items = []
    for i in range(n):
        pts = boxes[i]
        cx, cy = _coords(pts)
        text = (txts[i] or "").strip()
        if not text:
            continue
        items.append((cy, cx, text))
    items.sort(key=lambda x: (x[0], x[1]))

    lines = []
    i = 0
    while i < len(items):
        cy0 = items[i][0]
        line_items = []
        while i < len(items) and abs(items[i][0] - cy0) <= same_line_threshold:
            line_items.append((items[i][1], items[i][2]))
            i += 1
        line_items.sort(key=lambda x: x[0])
        line_text = " ".join(t for _, t in line_items)
        lines.append((cy0, line_text))

    out = []
    for j, (cy, line_text) in enumerate(lines):
        if j > 0 and cy - lines[j - 1][0] > paragraph_gap:
            out.append("")
        out.append(line_text)
    return "\n".join(out)


def _extract_text(result) -> str:
    if result is None:
        return ""
    txts = getattr(result, "txts", None)
    if txts is not None:
        return "\n".join(t.strip() for t in txts if t and str(t).strip())
    if isinstance(result, (list, tuple)) and len(result) >= 1:
        data = result[0]
        if data is None:
            return ""
        if isinstance(data, (list, tuple)):
            parts = []
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    parts.append(str(item[1]).strip())
                elif isinstance(item, str):
                    parts.append(item.strip())
            return "\n".join(p for p in parts if p)
        if hasattr(data, "txts") and data.txts:
            return "\n".join(t.strip() for t in data.txts if t and str(t).strip())
    if isinstance(result, (list, tuple)) and result:
        parts = []
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                parts.append(str(item[1]).strip())
            elif isinstance(item, str):
                parts.append(item.strip())
        return "\n".join(p for p in parts if p)
    return ""


def run_ocr(image_path: str) -> str:
    try:
        import numpy  # noqa: F401 — инициализация до rapidocr (PyInstaller)
        from rapidocr import (  # type: ignore[import-untyped]
            RapidOCR,
            LangDet,
            LangRec,
            ModelType,
            OCRVersion,
        )
    except ImportError as e:
        cmd = f'"{sys.executable}" -m pip install rapidocr onnxruntime'
        raise SystemExit(f"No module named 'rapidocr'. Выполните в терминале:\n{cmd}\n\n{e}") from e
    # Детекция: мультиязычная (multi), чтобы корректно находить и русский, и латиницу.
    # Распознавание: кириллица + английский, модель SERVER для лучшего качества.
    try:
        engine = RapidOCR(
            params={
                "Det.lang_type": getattr(LangDet, "MULTI", LangDet.CH),
                "Det.ocr_version": OCRVersion.PPOCRV4,
                "Rec.lang_type": LangRec.CYRILLIC,
                "Rec.model_type": ModelType.SERVER,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
            }
        )
    except Exception:
        try:
            engine = RapidOCR(params={"Rec.lang_type": LangRec.CYRILLIC})
        except Exception:
            engine = RapidOCR()
    if not os.path.isfile(image_path):
        raise SystemExit("Файл изображения не найден")
    result = engine(image_path)
    # Сначала пробуем структурировать по координатам боксов (как на картинке)
    formatted = _format_by_boxes(result)
    if formatted is not None:
        text = formatted
    else:
        raw = _extract_text(result) or "(Текст не распознан)"
        text = _merge_ocr_lines(raw)
    return _fix_ocr_word_errors(text)


def main():
    if len(sys.argv) < 2:
        print("Использование: python -m gui.ocr_subprocess <путь_к_изображению>", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    try:
        text = run_ocr(path)
        # stdout в UTF-8 для корректного чтения в Qt
        if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
            sys.stdout.reconfigure(encoding="utf-8")
        print(text, end="")
        sys.exit(0)
    except SystemExit as e:
        if e.args:
            print(e.args[0], file=sys.stderr)
        sys.exit(1 if e.code is None else e.code)
    except Exception as e:
        print(f"Ошибка OCR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
