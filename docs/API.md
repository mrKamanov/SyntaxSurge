# Настройка API SyntaxSurge

SyntaxSurge поддерживает **OpenAI-совместимые** API. Настройка в главном окне: вкладка **API**.

---

## Провайдеры (пресеты)

| Провайдер | Описание |
|-----------|----------|
| **OpenRouter** | Много моделей (OpenAI, Gemini, Claude…). Ключ: openrouter.ai/keys |
| **OpenAI** | Официальный API. Ключ: platform.openai.com/api-keys |
| **Google Gemini** | Официальный API. Ключ: aistudio.google.com/apikey |
| **Anthropic (Claude)** | Claude API. Ключ: console.anthropic.com |
| **Ollama** | Локальные модели. Без ключа |
| **LM Studio** | Локальный сервер. Без ключа |
| **GitHub Copilot** | API для расширений Copilot |

---

## Типы авторизации

- **Authorization: Bearer** — стандартный заголовок `Authorization: Bearer <ключ>`
- **X-API-Key** — заголовок `X-API-Key: <ключ>`
- **Без ключа** — для Ollama, LM Studio и локальных серверов

---

## Поля настройки

- **URL API** — базовый URL (например, `https://api.openai.com/v1`)
- **Ключ** — API-ключ (для Bearer или X-API-Key)
- **Модель** — имя модели (например, `gpt-4o-mini`, `gemini-2.0-flash`)

---

## Слоты

Можно настроить несколько слотов (API 1, API 2, …) и переключаться между ними. Каждый слот хранит свой URL, ключ и модель.

---

## Примеры

### Ollama (локально)

- URL: `http://localhost:11434/v1`
- Ключ: пусто или любое значение
- Авторизация: Без ключа
- Модель: `llama3.2`, `codellama` и др.

### OpenRouter

- URL: `https://openrouter.ai/api/v1`
- Ключ: ваш ключ с openrouter.ai
- Авторизация: Bearer
- Модель: `openai/gpt-4o-mini`, `google/gemini-2.0-flash-exp` и др.

### OpenAI

- URL: `https://api.openai.com/v1`
- Ключ: ваш ключ с platform.openai.com
- Авторизация: Bearer
- Модель: `gpt-4o-mini`, `gpt-4o` и др.
