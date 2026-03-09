#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вызов OpenAI-совместимого API (OpenAI, OpenRouter, Ollama и т.д.).
Требуется: pip install openai
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple

# auth_type: "Bearer" | "X-API-Key" | "None"
def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    auth_type: str,
    messages: List[Dict[str, str]],
    extra_body: Optional[Dict[str, Any]] = None,
    max_tokens: int = 8192,
) -> Tuple[bool, str]:
    """
    Отправляет запрос chat completions. Возвращает (success, response_text_or_error).
    """
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "").strip()
    if not base_url or not model:
        return False, "Укажите URL API и модель в настройках (вкладка API)."
    try:
        from openai import OpenAI
    except ImportError:
        return False, "Установите библиотеку openai: pip install openai"

    # Для X-API-Key ключ только в заголовке; для Bearer — стандартный api_key; для None — ollama/пусто
    default_headers = None
    if auth_type == "X-API-Key" and api_key:
        default_headers = {"X-API-Key": api_key}
        api_key = None  # чтобы клиент не дублировал Authorization
    elif auth_type == "None":
        api_key = api_key or "ollama"  # Ollama часто принимает любой ключ

    client = OpenAI(
        base_url=base_url if base_url.startswith("http") else f"https://{base_url}",
        api_key=api_key or "",
        default_headers=default_headers,
    )
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        return False, str(e).strip() or repr(e)

    try:
        choice = response.choices[0] if response.choices else None
        if not choice or not getattr(choice, "message", None):
            return False, "Пустой ответ от API."
        msg = choice.message
        content = getattr(msg, "content", None) or ""
        if hasattr(msg, "reasoning_details") and getattr(msg, "reasoning_details"):
            # OpenRouter reasoning: можно добавить reasoning_details к выводу при желании
            pass
        return True, (content or "(Пустой ответ)")
    except Exception as e:
        return False, str(e).strip() or repr(e)


def chat_completion_with_image(
    base_url: str,
    api_key: str,
    model: str,
    auth_type: str,
    prompt_text: str,
    image_base64: str,
    image_media_type: str = "image/png",
    max_tokens: int = 8192,
) -> Tuple[bool, str]:
    """
    Отправляет запрос с изображением (vision). prompt_text — текстовый промпт, image_base64 — PNG/JPEG в base64.
    Возвращает (success, response_text_or_error).
    """
    url = f"data:{image_media_type};base64,{image_base64}"
    messages: List[Dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text or "Опиши изображение."},
                {"type": "image_url", "image_url": {"url": url}},
            ],
        }
    ]
    return chat_completion(base_url, api_key, model, auth_type, messages, max_tokens=max_tokens)
