# -*- coding: utf-8 -*-
"""Устройства ввода/вывода звука и статус моделей помощника."""

import os
import re

try:
    import sounddevice as sd
    sounddevice_available = True
except ImportError:
    sounddevice_available = False
    sd = None

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSISTANT_MODELS_DIR = os.path.join(_PROJECT_ROOT, "models")
ASSISTANT_MODEL_FILES = ("encoder.chunk64.onnx", "decoder.chunk64.onnx", "joiner.chunk64.onnx")


def _normalize_device_name(name: str) -> str:
    """Нормализует имя устройства для дедупликации: убирает пути к драйверам, лишние скобки."""
    if not name or not name.strip():
        return ""
    s = name.strip()
    s = re.sub(r"\s*\(@[^)]*\)", "", s)
    s = re.sub(r"\s*\([^)]*\\[^)]*\.sys[^)]*\)", "", s)
    s = re.sub(r"\s*\([^)]*#\d+[^)]*\)", "", s)
    s = " ".join(s.split())
    return s.strip().lower()


def _device_base_key(name: str) -> str:
    """Базовый ключ для дедупликации: убрать всё в скобках, хвостовые цифры."""
    if not name or not name.strip():
        return ""
    s = name.strip()
    for _ in range(20):
        prev = s
        s = re.sub(r"\([^()]*\)", "", s)
        if s == prev:
            break
    s = re.sub(r"\s+\d+\s*$", "", s)
    s = " ".join(s.split()).strip().lower()
    return s


def _is_generic_device_name(name: str, normalized: str) -> bool:
    """Отсекает слишком общие названия."""
    if not normalized or len(normalized) < 2:
        return True
    generic = (
        "input ()", "output ()", "наушники ()", "динамики ()", "головной телефон ()",
        "первичный звуковой драйвер", "первичный драйвер записи", "переназначение звуковых",
    )
    n = normalized.lower()
    for g in generic:
        if g in n or n == g.rstrip(" ()"):
            return True
    if re.match(r"^(input|output)\s*$", n):
        return True
    return False


def get_input_audio_devices():
    """Список устройств ввода: [(отображаемое_имя, индекс), ...]."""
    if not sounddevice_available or sd is None:
        return []
    try:
        default_idx = None
        try:
            d = sd.default.device
            default_idx = int(d[0]) if isinstance(d, (list, tuple)) else int(d)
        except (TypeError, IndexError, ValueError):
            pass
        all_inputs = []
        for i in range(64):
            try:
                dev = sd.query_devices(i)
                if not isinstance(dev, dict) or dev.get("max_input_channels", 0) <= 0:
                    continue
                name = (dev.get("name") or f"Устройство {i}").strip()
                all_inputs.append((i, name))
            except (OSError, Exception):
                break
        result = []
        used_idx = set()
        if default_idx is not None:
            for i, name in all_inputs:
                if i == default_idx:
                    result.append(("Микрофон по умолчанию (активный)", i))
                    used_idx.add(i)
                    break
        _builtin_keywords = ("array", "internal", "встроен", "realtek hd audio", "microphone array")
        for i, name in all_inputs:
            if i in used_idx:
                continue
            name_lower = name.lower()
            if any(kw in name_lower for kw in _builtin_keywords):
                result.append(("Встроенный микрофон", i))
                used_idx.add(i)
                break
        _stereo_keywords = ("stereo mix", "стерео микшер", "what u hear", "wave out mix")
        for i, name in all_inputs:
            if i in used_idx:
                continue
            if any(kw in name.lower() for kw in _stereo_keywords):
                result.append(("Стерео микшер (захват с ПК)", i))
                used_idx.add(i)
                break
        return result
    except Exception:
        return []


def get_output_audio_devices():
    """Список устройств вывода: [(имя, индекс), ...]."""
    if not sounddevice_available or sd is None:
        return []
    try:
        default_idx = None
        try:
            d = sd.default.device
            default_idx = int(d[1]) if isinstance(d, (list, tuple)) and len(d) > 1 else (int(d) if isinstance(d, (list, tuple)) else int(d))
        except (TypeError, IndexError, ValueError):
            pass
        seen = set()
        devices = []
        for i in range(64):
            try:
                dev = sd.query_devices(i)
                if not isinstance(dev, dict) or dev.get("max_output_channels", 0) <= 0:
                    continue
                name = dev.get("name", f"Устройство {i}").strip()
                norm = _normalize_device_name(name)
                if _is_generic_device_name(name, norm):
                    continue
                base = _device_base_key(name)
                if base and base in seen:
                    continue
                if base:
                    seen.add(base)
                display = re.sub(r"\s*\(@[^)]*\)", "", name)
                display = re.sub(r"\s*\([^)]*\\[^)]*\.sys[^)]*\)", "", display)
                display = " ".join(display.split()).strip() or name
                if len(display) > 50:
                    display = display[:47] + "…"
                devices.append((display, i))
            except (OSError, Exception):
                break
        if default_idx is not None and devices:
            for j, (disp, idx) in enumerate(devices):
                if idx == default_idx:
                    devices.insert(0, (disp + " (по умолчанию)", idx))
                    devices.pop(j + 1)
                    break
        return devices
    except Exception:
        return []


def get_assistant_models_status():
    """(путь_к_папке, всё_найдено, список_недостающих_имён)."""
    missing = []
    for name in ASSISTANT_MODEL_FILES:
        if not os.path.isfile(os.path.join(ASSISTANT_MODELS_DIR, name)):
            missing.append(name)
    return ASSISTANT_MODELS_DIR, len(missing) == 0, missing
