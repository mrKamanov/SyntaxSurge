#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Mapper - Создаёт карту кода из файла
Используется ПЕРЕД печатью
"""

import re
import json
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class ElementType(Enum):
    SHEBANG = "shebang"
    ENCODING = "encoding"
    DOCSTRING = "docstring"
    IMPORT = "import"
    CONSTANT = "constant"
    CLASS_DEF = "class_def"
    FUNC_DEF = "func_def"
    METHOD_DEF = "method_def"
    DECORATOR = "decorator"
    BODY_LINE = "body_line"
    MAIN_BLOCK = "main_block"
    BLANK = "blank"
    COMMENT = "comment"
    OTHER = "other"


@dataclass
class CodeElement:
    type: ElementType
    content: str
    line_number: int
    indent: int
    name: Optional[str] = None
    body_lines: List[str] = field(default_factory=list)
    decorators: List["CodeElement"] = field(default_factory=list)
    body_start_line: int = 0
    body_end_line: int = 0
    parent_name: Optional[str] = None


@dataclass
class CodeMap:
    language: str
    total_lines: int
    total_chars: int
    elements: List[CodeElement] = field(default_factory=list)
    imports: List[CodeElement] = field(default_factory=list)
    constants: List[CodeElement] = field(default_factory=list)
    classes: List[CodeElement] = field(default_factory=list)
    functions: List[CodeElement] = field(default_factory=list)
    main_block: Optional[CodeElement] = None
    print_plan: List[Dict] = field(default_factory=list)


class CodeMapBuilder:
    """Строит карту кода"""
    
    def build_from_file(self, filepath: str, language: str = "python") -> CodeMap:
        """Создаёт карту из файла"""
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        if filepath.endswith('.md'):
            code = self._extract_code_from_markdown(code)
        return self.build_from_string(code, language)
    
    def _extract_code_from_markdown(self, markdown: str) -> str:
        pattern = r'```(?:python|py)?\s*\n(.*?)```'
        matches = re.findall(pattern, markdown, re.DOTALL)
        if matches:
            return matches[0].strip()
        return markdown
    
    def build_from_string(self, code: str, language: str = "python") -> CodeMap:
        lines = code.split('\n')
        code_map = CodeMap(
            language=language,
            total_lines=len(lines),
            total_chars=len(code)
        )
        i = 0
        current_class = None
        pending_decorators: List[CodeElement] = []
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            indent = len(line) - len(line.lstrip()) if line.strip() else 0
            element = None
            if pending_decorators and stripped and (not stripped.startswith('@')) and (not stripped.startswith('class ')) and (not stripped.startswith('def ')):
                pending_decorators = []
            if not stripped:
                element = CodeElement(type=ElementType.BLANK, content=line, line_number=i + 1, indent=0)
            elif stripped.startswith('#!'):
                element = CodeElement(type=ElementType.SHEBANG, content=line, line_number=i + 1, indent=0)
            elif stripped.startswith('# -*-') or stripped.startswith('# coding'):
                element = CodeElement(type=ElementType.ENCODING, content=line, line_number=i + 1, indent=0)
            elif stripped.startswith('#'):
                element = CodeElement(type=ElementType.COMMENT, content=line, line_number=i + 1, indent=indent)
            elif stripped.startswith(('import ', 'from ')):
                element = CodeElement(type=ElementType.IMPORT, content=line, line_number=i + 1, indent=indent)
                code_map.imports.append(element)
            elif stripped.startswith('@'):
                element = CodeElement(type=ElementType.DECORATOR, content=line, line_number=i + 1, indent=indent)
                pending_decorators.append(element)
            elif stripped.startswith('class '):
                match = re.search(r'class\s+(\w+)', stripped)
                class_name = match.group(1) if match else 'Unknown'
                element = CodeElement(type=ElementType.CLASS_DEF, content=line, line_number=i + 1, indent=indent, name=class_name, body_start_line=i + 2)
                if pending_decorators:
                    element.decorators = pending_decorators
                    pending_decorators = []
                body_lines, end_line = self._collect_body(lines, i + 1, indent)
                element.body_lines = body_lines
                element.body_end_line = end_line
                code_map.classes.append(element)
                current_class = class_name
                i = end_line
                continue
            elif stripped.startswith('def ') or stripped.startswith('async def '):
                match = re.search(r'def\s+(\w+)', stripped)
                func_name = match.group(1) if match else 'Unknown'
                is_method = indent > 0
                element = CodeElement(type=ElementType.METHOD_DEF if is_method else ElementType.FUNC_DEF, content=line, line_number=i + 1, indent=indent, name=func_name, parent_name=current_class if is_method else None, body_start_line=i + 2)
                if pending_decorators:
                    element.decorators = pending_decorators
                    pending_decorators = []
                body_lines, end_line = self._collect_body(lines, i + 1, indent)
                element.body_lines = body_lines
                element.body_end_line = end_line
                if not is_method:
                    code_map.functions.append(element)
                i = end_line
                continue
            elif stripped.startswith('if __name__'):
                element = CodeElement(type=ElementType.MAIN_BLOCK, content=line, line_number=i + 1, indent=indent)
                body_lines, end_line = self._collect_body(lines, i + 1, indent)
                element.body_lines = body_lines
                element.body_end_line = end_line
                code_map.main_block = element
                i = end_line
                continue
            elif '=' in stripped:
                var_name = stripped.split('=')[0].strip()
                if var_name and var_name.isupper() and var_name.replace('_', '').isalnum():
                    element = CodeElement(type=ElementType.CONSTANT, content=line, line_number=i + 1, indent=indent)
                    code_map.constants.append(element)
                else:
                    element = CodeElement(type=ElementType.OTHER, content=line, line_number=i + 1, indent=indent)
            else:
                element = CodeElement(type=ElementType.OTHER, content=line, line_number=i + 1, indent=indent)
            if element:
                code_map.elements.append(element)
            i += 1
        code_map.print_plan = self._build_print_plan(code_map)
        return code_map
    
    def _collect_body(self, lines: List[str], start_idx: int, base_indent: int) -> Tuple[List[str], int]:
        body = []
        end_idx = start_idx
        for i in range(start_idx, len(lines)):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                body.append(line)
                end_idx = i
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            body.append(line)
            end_idx = i
        return body, end_idx
    
    def _build_print_plan(self, code_map: CodeMap) -> List[Dict]:
        plan = []
        skeleton_line = 1
        total_blocks = len(code_map.classes) + len(code_map.functions)
        use_skeleton_mode = total_blocks > 2
        has_shebang_or_encoding = any(e.type in [ElementType.SHEBANG, ElementType.ENCODING] for e in code_map.elements)
        first_class_line = code_map.classes[0].line_number if code_map.classes else None
        first_func_line = code_map.functions[0].line_number if code_map.functions else None
        first_block_line = min(filter(None, [first_class_line, first_func_line])) if (first_class_line or first_func_line) else None
        import_lines = [e.line_number for e in code_map.elements if e.type == ElementType.IMPORT]
        first_import_line = min(import_lines) if import_lines else None
        is_full_code = has_shebang_or_encoding or (first_import_line is not None and first_block_line is not None and first_import_line < first_block_line)
        print(f"  Всего блоков: {total_blocks}")
        print(f"  Режим: {'СКЕЛЕТНЫЙ (с pass)' if use_skeleton_mode else 'ПРЯМОЙ (без pass)'}")
        print(f"  Тип кода: {'ПОЛНЫЙ' if is_full_code else 'КУСОЧЕК'}")
        header_elems = [e for e in code_map.elements if e.type in [ElementType.SHEBANG, ElementType.ENCODING]]
        header_elems.sort(key=lambda e: e.line_number)
        header_lines = 0
        for elem in header_elems:
            plan.append({'phase': 'skeleton', 'action': 'type_line', 'content': elem.content, 'original_line': elem.line_number, 'skeleton_line': skeleton_line})
            skeleton_line += 1
            header_lines += 1
        all_functions = [f for f in code_map.functions if f.type != ElementType.METHOD_DEF]
        other_module = [e for e in code_map.elements if e.type == ElementType.OTHER and e.indent == 0]
        ordered: List[Tuple[int, str, Any]] = []
        for e in code_map.constants:
            if e.indent == 0:
                ordered.append((e.line_number, 'constant', e))
        for e in other_module:
            ordered.append((e.line_number, 'other', e))
        for cls in code_map.classes:
            ordered.append((cls.line_number, 'class', cls))
        for func in all_functions:
            ordered.append((func.line_number, 'function', func))
        if code_map.main_block:
            ordered.append((code_map.main_block.line_number, 'main', code_map.main_block))
        ordered.sort(key=lambda x: x[0])
        for idx, (line_no, kind, item) in enumerate(ordered):
            if kind == 'constant' or kind == 'other':
                plan.append({'phase': 'skeleton', 'action': 'type_line', 'content': item.content, 'original_line': item.line_number, 'skeleton_line': skeleton_line})
                skeleton_line += 1
            else:
                block = item
                has_real_body = block.body_lines and any(line.strip() and line.strip() != 'pass' for line in block.body_lines)
                block_type = kind if kind != 'main' else 'main'
                block_name = block.name if kind != 'main' else '__main__'
                plan.append({'phase': 'skeleton', 'action': 'type_block_skeleton', 'type': block_type, 'name': block_name, 'signature': block.content, 'indent': block.indent, 'original_line': block.line_number, 'skeleton_line': skeleton_line, 'body_lines': block.body_lines if has_real_body else [], 'has_body': has_real_body, 'use_skeleton_mode': use_skeleton_mode, 'decorators': [dec.content for dec in getattr(block, 'decorators', [])]})
                skeleton_line += 1
                if not use_skeleton_mode and has_real_body:
                    for idx, body_line in enumerate(block.body_lines):
                        plan.append({'phase': 'skeleton', 'action': 'type_line', 'content': body_line, 'original_line': block.body_start_line + idx, 'skeleton_line': skeleton_line})
                        skeleton_line += 1
                elif not has_real_body:
                    plan.append({'phase': 'skeleton', 'action': 'type_line', 'content': '', 'skeleton_line': skeleton_line})
                    skeleton_line += 1
                if use_skeleton_mode and has_real_body:
                    skeleton_line += 1
            has_next = idx < len(ordered) - 1
            if has_next:
                plan.append({'phase': 'skeleton', 'action': 'type_line', 'content': '', 'skeleton_line': skeleton_line})
                skeleton_line += 1
        return plan
    
    def save_map(self, code_map: CodeMap, filepath: str):
        header_lines = len([e for e in code_map.elements if e.type in [ElementType.SHEBANG, ElementType.ENCODING]])
        data = {
            'language': code_map.language,
            'total_lines': code_map.total_lines,
            'total_chars': code_map.total_chars,
            'header_lines': header_lines,
            'imports': [{'content': e.content, 'line': e.line_number} for e in code_map.imports],
            'constants': [{'content': e.content, 'line': e.line_number} for e in code_map.constants],
            'classes': [{'name': e.name, 'line': e.line_number, 'body_lines': e.body_lines, 'decorators': [d.content for d in getattr(e, 'decorators', [])]} for e in code_map.classes],
            'functions': [{'name': e.name, 'line': e.line_number, 'body_lines': e.body_lines, 'decorators': [d.content for d in getattr(e, 'decorators', [])]} for e in code_map.functions],
            'main_block': {'line': code_map.main_block.line_number, 'body_lines': code_map.main_block.body_lines} if code_map.main_block else None,
            'print_plan': code_map.print_plan
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Карта сохранена: {filepath}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Использование: python -m typer.code_mapper <filepath> [output.json]")
        sys.exit(1)
    filepath = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else filepath.replace('.py', '_map.json')
    builder = CodeMapBuilder()
    code_map = builder.build_from_file(filepath)
    print(f"Язык: {code_map.language}")
    print(f"Строк: {code_map.total_lines}")
    print(f"Классов: {len(code_map.classes)}")
    print(f"Функций: {len(code_map.functions)}")
    builder.save_map(code_map, output)
