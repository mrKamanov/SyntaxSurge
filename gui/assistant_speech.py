# -*- coding: utf-8 -*-
"""
Распознавание речи для вкладки «Помощник».
Использует sherpa-onnx (encoder.chunk64.onnx, decoder.chunk64.onnx, joiner.chunk64.onnx)
и sounddevice для захвата с микрофона. Весь код распознавания вынесен сюда.
"""
from __future__ import annotations

import os
import queue
import threading
from typing import Callable, Optional

try:
    import sounddevice as sd
    _sd_available = True
except ImportError:
    _sd_available = False
    sd = None

try:
    import sherpa_onnx
    _sherpa_available = True
except ImportError:
    _sherpa_available = False
    sherpa_onnx = None


# Имена файлов модели (chunk 64)
ENCODER_FILENAME = "encoder.chunk64.onnx"
DECODER_FILENAME = "decoder.chunk64.onnx"
JOINER_FILENAME = "joiner.chunk64.onnx"
TOKENS_FILENAME = "tokens.txt"

# Параметры по умолчанию:
# - model_sample_rate: частота модели (обычно 16000)
# - input_sample_rate: частота захвата с микрофона (часто 48000; sherpa-onnx ресэмплит внутри accept_waveform)
DEFAULT_MODEL_SAMPLE_RATE = 16000
DEFAULT_INPUT_SAMPLE_RATE = 48000
DEFAULT_FEATURE_DIM = 80
SAMPLES_PER_READ_MS = 120  # 120 ms — меньше нагрузка при двух потоках (микрофон + собеседник)


def is_available() -> bool:
    """Проверка: установлены ли sounddevice и sherpa_onnx."""
    return _sd_available and _sherpa_available


def check_models(models_dir: str) -> tuple[bool, list[str]]:
    """
    Проверяет наличие всех файлов модели в каталоге.
    Возвращает (всё_найдено, список_недостающих_имён).
    """
    required = (ENCODER_FILENAME, DECODER_FILENAME, JOINER_FILENAME, TOKENS_FILENAME)
    missing = []
    for name in required:
        if not os.path.isfile(os.path.join(models_dir, name)):
            missing.append(name)
    return len(missing) == 0, missing


def create_recognizer(
    models_dir: str,
    model_sample_rate: int = DEFAULT_MODEL_SAMPLE_RATE,
    feature_dim: int = DEFAULT_FEATURE_DIM,
    num_threads: int = 1,
    provider: str = "cpu",
) -> "sherpa_onnx.OnlineRecognizer":
    """Создаёт потоковый распознаватель sherpa-onnx (transducer)."""
    if not _sherpa_available:
        raise RuntimeError("sherpa_onnx не установлен. Установите: pip install sherpa-onnx")
    ok, missing = check_models(models_dir)
    if not ok:
        raise FileNotFoundError(f"В {models_dir} не хватает файлов: {', '.join(missing)}")

    tokens = os.path.join(models_dir, TOKENS_FILENAME)
    encoder = os.path.join(models_dir, ENCODER_FILENAME)
    decoder = os.path.join(models_dir, DECODER_FILENAME)
    joiner = os.path.join(models_dir, JOINER_FILENAME)

    recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=tokens,
        encoder=encoder,
        decoder=decoder,
        joiner=joiner,
        num_threads=num_threads,
        sample_rate=model_sample_rate,
        feature_dim=feature_dim,
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=1.2,
        rule3_min_utterance_length=300,
        decoding_method="greedy_search",
        provider=provider,
    )
    return recognizer


def run_recognition_loop(
    models_dir: str,
    device_id: int,
    *,
    on_text: Callable[[str, bool, str], None],
    stop_event: threading.Event,
    role: str = "user",
    model_sample_rate: int = DEFAULT_MODEL_SAMPLE_RATE,
    input_sample_rate: int = DEFAULT_INPUT_SAMPLE_RATE,
    channels: int = 1,
    mute_event: Optional[threading.Event] = None,
) -> None:
    """
    Запускает цикл распознавания в текущем потоке (обычно worker thread).
    Читает аудио с устройства device_id (sounddevice), распознаёт и вызывает
    on_text(text, is_final, role) для каждой частичной и финальной фразы.
    Цикл завершается, когда stop_event установлен.

    role: "user" (микрофон) или "interlocutor" (захват с ПК, напр. Стерео микшер).
    channels: 1 — моно (микрофон), 2 — стерео с сведением в моно (Стерео микшер).
    mute_event: если задан и установлен (set), аудио не подаётся в распознаватель (только для role "user").
    """
    def _cb(t: str, f: bool):
        on_text(t, f, role)

    if not _sd_available or not _sherpa_available:
        _cb("Ошибка: установите sounddevice и sherpa-onnx.", True)
        return

    try:
        recognizer = create_recognizer(models_dir, model_sample_rate=model_sample_rate)
    except Exception as e:
        _cb(f"Ошибка загрузки модели: {e}", True)
        return

    stream = recognizer.create_stream()
    samples_per_read = int((SAMPLES_PER_READ_MS / 1000.0) * input_sample_rate)
    audio_queue = queue.Queue()

    def _input_callback(indata, frames, time_info, status):
        if status:
            # input_overflow при двух потоках — не фатально, не останавливаем распознавание
            if getattr(status, "input_overflow", False):
                return
            audio_queue.put(("status", status))
            return
        try:
            audio_queue.put(("data", indata.copy()))
        except Exception:
            pass

    try:
        # Режим callback + увеличенный буфер: Стерео микшер и два потока без overflow
        with sd.InputStream(
            device=device_id,
            channels=channels,
            dtype="float32",
            samplerate=input_sample_rate,
            blocksize=samples_per_read,
            callback=_input_callback,
            latency=0.25,
        ):
            while not stop_event.is_set():
                try:
                    msg = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if msg[0] == "status":
                    _cb(f"Ошибка устройства: {msg[1]}", True)
                    break
                data = msg[1]
                if data is None or data.size == 0:
                    continue
                if mute_event is not None and mute_event.is_set():
                    continue
                # Стерео (channels=2) → моно для модели
                if data.ndim >= 2 and data.shape[1] >= 2:
                    samples = data.mean(axis=1).astype(data.dtype)
                else:
                    samples = data.reshape(-1)
                stream.accept_waveform(input_sample_rate, samples)

                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

                result = recognizer.get_result(stream)
                if result and result.strip():
                    is_endpoint = recognizer.is_endpoint(stream)
                    _cb(result.strip(), is_endpoint)
                    if is_endpoint:
                        recognizer.reset(stream)
    except Exception as e:
        _cb(f"Ошибка распознавания: {e}", True)
    finally:
        pass


def get_sherpa_and_sounddevice_available() -> tuple[bool, bool]:
    """Возвращает (sherpa_onnx_доступен, sounddevice_доступен)."""
    return (_sherpa_available, _sd_available)
