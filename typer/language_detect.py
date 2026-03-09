# -*- coding: utf-8 -*-
"""
Определение языка кода по расширению файла или по содержимому.
"""

import re
from typing import Literal

Language = Literal["python", "sql"]

_SQL_KEYWORDS = (
    r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\s",
    r"^\s*(FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON)\s",
    r"^\s*(GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET)\s",
    r"^\s*(VALUES|INTO|SET)\s",
    r"^\s*(TABLE|VIEW|INDEX|DATABASE|SCHEMA)\s",
    r"^\s*(UNION|EXCEPT|INTERSECT)\s",
    r"^\s*(WITH|AS|CASE|WHEN|THEN|ELSE|END)\s",
    r"^\s*(AND|OR|NOT|IN|EXISTS|BETWEEN|LIKE)\s",
    r"^\s*--",
)
_SQL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SQL_KEYWORDS]

_PYTHON_PATTERNS = [
    re.compile(r"^\s*(def|class|import|from)\s"),
    re.compile(r"^\s*(if|else|elif|for|while|with|try|except)\s*:"),
    re.compile(r"^\s*@\w+"),
    re.compile(r"^\s*#\s*-\*-"),
    re.compile(r"^\s*print\s*\("),
]


def detect_from_filepath(filepath: str) -> Language:
    """Определяет язык по расширению файла."""
    if not filepath:
        return "python"
    path_lower = filepath.lower().strip()
    if path_lower.endswith(".sql"):
        return "sql"
    if any(path_lower.endswith(ext) for ext in (".py", ".pyw", ".pyi")):
        return "python"
    return "python"


def detect_from_content(text: str, filepath: str = "") -> Language:
    """Определяет язык по содержимому текста."""
    if filepath and detect_from_filepath(filepath) == "sql":
        return "sql"

    lines = (text or "").strip().split("\n")
    sql_score = 0
    python_score = 0

    for line in lines[:50]:
        stripped = line.strip()
        if not stripped:
            continue
        for pat in _SQL_PATTERNS:
            if pat.search(stripped):
                sql_score += 1
                break
        for pat in _PYTHON_PATTERNS:
            if pat.search(stripped):
                python_score += 1
                break

    if sql_score > python_score:
        return "sql"
    return "python"
