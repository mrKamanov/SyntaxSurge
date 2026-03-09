#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Настройки API: пресеты провайдеров (OpenRouter, OpenAI, Google Gemini, Anthropic, GitHub, Ollama, LM Studio),
типы авторизации, применение пресета к слоту.
Все провайдеры — OpenAI-совместимый chat/completions (или совместимый слой).
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional

# --- Типы авторизации (значения для api_client и слотов) ---
AUTH_BEARER = "Bearer"
AUTH_X_API_KEY = "X-API-Key"
AUTH_NONE = "None"

AUTH_VALUES: List[str] = [AUTH_BEARER, AUTH_X_API_KEY, AUTH_NONE]

# Подписи для комбобокса в UI
API_AUTH_OPTIONS: List[str] = [
    "Authorization: Bearer",
    "X-API-Key",
    "Без ключа (Ollama)",
]

# --- Пресеты провайдеров (по документации) ---
PRESET_ID_MANUAL = ""

PRESETS: List[Dict[str, Any]] = [
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "auth": AUTH_BEARER,
        "model_hint": "openai/gpt-4o-mini, arcee-ai/trinity-large-preview:free",
        "hint": "Много моделей (OpenAI, Gemini, Claude…). Ключ: openrouter.ai/keys",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "auth": AUTH_BEARER,
        "model_hint": "gpt-4o-mini, gpt-4o, gpt-4-turbo",
        "hint": "Официальный API. Ключ: platform.openai.com/api-keys",
    },
    {
        "id": "gemini",
        "name": "Google Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "auth": AUTH_BEARER,
        "model_hint": "gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro",
        "hint": "Официальный API Google. Ключ: aistudio.google.com/apikey",
    },
    {
        "id": "gemini_openrouter",
        "name": "Google Gemini (OpenRouter)",
        "base_url": "https://openrouter.ai/api/v1",
        "auth": AUTH_BEARER,
        "model_hint": "google/gemini-2.0-flash-exp, google/gemini-pro",
        "hint": "Через OpenRouter. Ключ: openrouter.ai/keys",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1/",
        "auth": AUTH_BEARER,
        "model_hint": "claude-sonnet-4-20250514, claude-opus-4, claude-3-5-sonnet",
        "hint": "Claude API. Ключ: console.anthropic.com",
    },
    {
        "id": "github",
        "name": "GitHub Copilot",
        "base_url": "https://api.githubcopilot.com",
        "auth": AUTH_BEARER,
        "model_hint": "см. документацию GitHub Copilot",
        "hint": "API для расширений Copilot. Ключ (Bearer) от GitHub. Лимиты для сторонних агентов.",
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "base_url": "http://localhost:11434/v1",
        "auth": AUTH_NONE,
        "model_hint": "llama2, mistral, codellama",
        "hint": "Локально. Ключ не нужен (можно оставить пустым или ollama).",
    },
    {
        "id": "lmstudio",
        "name": "LM Studio",
        "base_url": "http://localhost:1234/v1",
        "auth": AUTH_NONE,
        "model_hint": "имя модели из LM Studio",
        "hint": "Локально, порт 1234. Ключ не нужен.",
    },
]


def get_preset_by_id(preset_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает пресет по id или None."""
    if not preset_id:
        return None
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None


def get_presets_for_combo() -> List[tuple]:
    """Список для комбобокса «Провайдер»: (отображаемое имя, id)."""
    return [(p["name"], p["id"]) for p in PRESETS]


def get_provider_combo_choices() -> List[str]:
    """Только имена провайдеров в порядке пресетов (для добавления «Вручную» в начале)."""
    return [p["name"] for p in PRESETS]


def apply_preset_to_slot(preset_id: str) -> Dict[str, Any]:
    """
    Возвращает словарь для подстановки в слот: name, base_url, api_key, model, auth.
    api_key не трогаем (оставляем пустым в пресете, пользователь введёт сам).
    """
    preset = get_preset_by_id(preset_id)
    if not preset:
        return {}
    return {
        "name": preset["name"],
        "base_url": preset["base_url"].strip(),
        "api_key": "",  # пользователь вводит сам
        "model": preset["model_hint"].split(",")[0].strip() if preset.get("model_hint") else "",
        "auth": preset["auth"],
    }


def auth_index_from_value(auth_value: str) -> int:
    """Индекс в AUTH_VALUES / API_AUTH_OPTIONS (0, 1, 2)."""
    try:
        return AUTH_VALUES.index(auth_value)
    except ValueError:
        return 0


def auth_value_from_index(index: int) -> str:
    """Значение авторизации по индексу комбобокса."""
    if 0 <= index < len(AUTH_VALUES):
        return AUTH_VALUES[index]
    return AUTH_BEARER
