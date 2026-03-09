# -*- coding: utf-8 -*-
"""
SQL Code Mapper — создаёт карту SQL-кода для печати.
Формат совместим с CodePrinter: print_plan содержит только type_line.
"""

import json
import re
from typing import List, Dict, Any


class SqlCodeMapBuilder:
    """Строит карту SQL-кода для печати."""

    def build_from_file(self, filepath: str) -> Dict[str, Any]:
        """Создаёт карту из файла."""
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        if filepath.lower().endswith(".md"):
            code = self._extract_sql_from_markdown(code)
        return self.build_from_string(code)

    def _extract_sql_from_markdown(self, markdown: str) -> str:
        """Извлекает SQL из блока ```sql в Markdown."""
        pattern = r"```(?:sql)?\s*\n(.*?)```"
        matches = re.findall(pattern, markdown, re.DOTALL | re.IGNORECASE)
        if matches:
            return matches[0].strip()
        return markdown

    def build_from_string(self, code: str) -> Dict[str, Any]:
        """Создаёт карту из строки SQL."""
        lines = code.split("\n")
        total_lines = len(lines)
        total_chars = len(code)
        print_plan: List[Dict[str, Any]] = []
        skeleton_line = 1

        for i, line in enumerate(lines):
            original_line = i + 1
            print_plan.append({
                "phase": "skeleton",
                "action": "type_line",
                "content": line,
                "original_line": original_line,
                "skeleton_line": skeleton_line,
            })
            skeleton_line += 1

        return {
            "language": "sql",
            "total_lines": total_lines,
            "total_chars": total_chars,
            "header_lines": 0,
            "imports": [],
            "constants": [],
            "classes": [],
            "functions": [],
            "main_block": None,
            "print_plan": print_plan,
        }

    def save_map(self, data: Dict[str, Any], filepath: str) -> None:
        """Сохраняет карту в JSON."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Карта SQL сохранена: {filepath}")
