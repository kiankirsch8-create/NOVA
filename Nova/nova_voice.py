"""Voice input (OpenAI Whisper) and output (ElevenLabs + pygame)."""

import io
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pygame
import requests
import scipy.io.wavfile as wavfile
import sounddevice as sd
from openai import OpenAI

import nova_config as config

_input_device: Optional[int] = None
_input_device_name: Optional[str] = None


def init_microphone() -> None:
    """List input devices and select the system default microphone."""
    global _input_device, _input_device_name

    devices = sd.query_devices()
    default_pair = sd.default.device
    default_input = default_pair[0] if isinstance(default_pair, (list, tuple)) else default_pair

    print("[NOVA] Available input devices:")
    input_devices = []
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) > 0:
            input_devices.append((index, device))
            is_default = index == default_input
            marker = " (system default)" if is_default else ""
            print(
                f"  [{index}] {device['name']} "
                f"({device['max_input_channels']} ch, {device['default_samplerate']} Hz){marker}"
            )

    selected_index = None
    selected_name = None

    # Prefer built-in MacBook mic over Continuity Camera / iPhone devices.
    for index, device in input_devices:
        name = device["name"]
        name_lower = name.lower()
        if "macbook" in name_lower or "built-in" in name_lower:
            selected_index = index
            selected_name = name
            break

    if selected_index is None and isinstance(default_input, int) and default_input >= 0:
        selected_index = default_input
        selected_name = devices[default_input]["name"]

    if selected_index is None and input_devices:
        selected_index, device = input_devices[0]
        selected_name = device["name"]

    if selected_index is None:
        raise RuntimeError("No microphone input devices found.")

    _input_device = selected_index
    _input_device_name = selected_name

    # Force sounddevice to use the chosen input for all recordings.
    sd.default.device = (selected_index, sd.default.device[1])
    sd.check_input_settings(
        device=selected_index,
        channels=1,
        samplerate=config.SAMPLE_RATE,
    )

    print(
        f"[NOVA] Selected microphone: [{selected_index}] {selected_name} "
        f"at {config.SAMPLE_RATE} Hz"
    )


def _log_error(message: str) -> None:
    try:
        with open(config.ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} [VOICE] {message}\n")
    except OSError:
        pass


def _rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))


def record_audio() -> Optional[np.ndarray]:
    """
    Record continuously until the speaker stops talking.
    Stops after SILENCE_DURATION seconds below SILENCE_THRESHOLD.
    """
    sample_rate = config.SAMPLE_RATE
    chunk_samples = int(sample_rate * config.CHUNK_DURATION)
    silence_chunks_needed = int(config.SILENCE_DURATION / config.CHUNK_DURATION)
    min_chunks = max(1, int(config.MIN_RECORDING_SECONDS / config.CHUNK_DURATION))
    max_chunks = int(config.MAX_RECORDING_SECONDS / config.CHUNK_DURATION)

    device = _input_device
    if device is None:
        init_microphone()
        device = _input_device

    recorded: list[np.ndarray] = []
    silence_chunks = 0
    speech_started = False

    print("[NOVA] Listening... speak now.")

    for _ in range(max_chunks):
        chunk = sd.rec(
            chunk_samples,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device,
            blocking=True,
        )
        chunk = chunk.flatten()
        level = _rms(chunk)
        print(
            f"[NOVA] Audio level: {level:.4f} "
            f"(threshold: {config.SILENCE_THRESHOLD})"
        )

        if level >= config.SILENCE_THRESHOLD:
            speech_started = True
            silence_chunks = 0
            recorded.append(chunk)
            continue

        if not speech_started:
            continue

        recorded.append(chunk)
        silence_chunks += 1

        if len(recorded) >= min_chunks and silence_chunks >= silence_chunks_needed:
            print("[NOVA] Silence detected — stopping recording.")
            break

    if not speech_started or len(recorded) < min_chunks:
        print("[NOVA] No speech detected.")
        return None

    duration = len(recorded) * config.CHUNK_DURATION
    print(f"[NOVA] Recorded {duration:.1f} seconds of audio.")
    return np.concatenate(recorded)


def _save_wav(audio: np.ndarray, path: str, sample_rate: int) -> None:
    """Save mono 16-bit PCM WAV at the given sample rate."""
    mono = audio.flatten()
    clipped = np.clip(mono, -1.0, 1.0)
    int_audio = (clipped * 32767).astype(np.int16)
    wavfile.write(path, sample_rate, int_audio)


def transcribe(audio: np.ndarray) -> Optional[str]:
    """Save audio as WAV and transcribe with OpenAI Whisper."""
    if config.OPENAI_API_KEY in ("", "your_key_here"):
        _log_error("OpenAI API key not configured")
        return None

    sample_rate = config.SAMPLE_RATE
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        _save_wav(audio, wav_path, sample_rate)
        file_size = os.path.getsize(wav_path)
        print(f"[NOVA] WAV file size: {file_size} bytes (rate: {sample_rate} Hz)")

        if file_size < config.MIN_WAV_BYTES:
            print("[NOVA] Recording failed — audio file too small for Whisper.")
            return None

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        with open(wav_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
            )
        text = transcript.text

        print(f"[NOVA] Whisper returned: {text!r}")

        text = (text or "").strip()
        if text:
            print(f"[NOVA] Heard: {text}")
        return text or None
    except Exception as exc:
        _log_error(f"Whisper transcription failed: {exc}")
        print(f"[NOVA] Whisper error: {exc}")
        return None
    finally:
        if wav_path and os.path.exists(wav_path):
            os.unlink(wav_path)


def listen() -> Optional[str]:
    """Record until silence, transcribe with Whisper, and return text."""
    audio = record_audio()
    if audio is None:
        return ""
    text = transcribe(audio)
    if text is None or not text.strip():
        return ""
    return text


def _ensure_pygame_mixer() -> None:
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)


def play_tone(frequency: float, duration: float = 0.25, volume: float = 0.3) -> None:
    """Play a simple tone for activation/deactivation feedback."""
    try:
        _ensure_pygame_mixer()
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave_data = (volume * np.sin(2 * np.pi * frequency * t) * np.exp(-4 * t / duration))
        audio = (wave_data * 32767).astype(np.int16)
        sound = pygame.sndarray.make_sound(audio)
        sound.play()
        while pygame.mixer.get_busy():
            pygame.time.wait(10)
    except Exception as exc:
        _log_error(f"Tone playback failed: {exc}")


def play_activation_sound() -> None:
    play_tone(880, duration=0.2, volume=0.25)
    play_tone(1174, duration=0.25, volume=0.2)


def play_deactivation_sound() -> None:
    play_tone(440, duration=0.35, volume=0.25)


def speak(text: str) -> bool:
    """
    Convert text to speech via ElevenLabs and play with pygame.
    Returns True if audio played, False if fallback to terminal only.
    """
    if not text.strip():
        return False

    if config.ELEVENLABS_API_KEY in ("", "your_key_here"):
        print(f"[NOVA] {text}")
        return False

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": config.ELEVENLABS_STABILITY,
            "similarity_boost": config.ELEVENLABS_SIMILARITY_BOOST,
        },
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()

        _ensure_pygame_mixer()
        audio_data = io.BytesIO(response.content)
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
        return True
    except Exception as exc:
        _log_error(f"ElevenLabs playback failed: {exc}")
        print(f"[NOVA] {text}")
        return False
