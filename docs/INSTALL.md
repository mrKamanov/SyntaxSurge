# Установка SyntaxSurge

## Системные требования

- **ОС:** Windows 10/11
- **Python:** 3.8 или выше
- **Архитектура:** x64 (рекомендуется)

## Шаг 1: Клонирование и зависимости

```bash
git clone <url-репозитория> SyntaxSurge
cd SyntaxSurge
pip install -r requirements.txt
```

## Шаг 2: Проверка установки

```bash
python run_gui.py
```

Должно открыться главное окно приложения.

## Опциональные компоненты

### OCR (распознавание текста на скриншоте)

Уже включено в `requirements.txt`:
- `rapidocr` — движок распознавания
- `onnxruntime` — зависимость rapidocr

При первом использовании OCR, если модуль не найден, приложение покажет команду установки.

### Помощник (голосовой ввод)

Требуются:
- `sherpa-onnx` — распознавание речи
- `sounddevice` — захват с микрофона

Дополнительно нужны файлы модели (encoder, decoder, joiner, tokens) в папке `models/`. См. [документацию sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx).

### Глобальные горячие клавиши

Требуется `pynput`. При отсутствии горячие клавиши работают только внутри окна приложения.

### Скриншоты (pyautogui)

Опционально. При отсутствии функция скриншота отключается.

## Редакторы кода

### VS Code / Cursor

1. Откройте папку `vscode-extension/`
2. Выполните `npm install` и `npm run compile`
3. Запустите отладку (F5) или соберите `.vsix` и установите

### PyCharm

1. Соберите плагин из `pycharm-plugin/`
2. Установите через **Settings → Plugins → Install Plugin from Disk**

### HH.ru (браузер)

1. Установите **Tampermonkey** или **Violentmonkey**
2. Добавьте скрипт из `typer/editors/hh_ru/userscript_hh_ru.user.js`
3. Разрешите доступ к `127.0.0.1` при первом запросе

### Yandex.Code

1. Установите Tampermonkey
2. Добавьте скрипт из `typer/editors/yandex_code/userscript_yandex_code.user.js`
