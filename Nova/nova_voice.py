"""Voice input (SpeechRecognition + Whisper API) and output (ElevenLabs + pygame)."""

import io
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pygame
import requests
import speech_recognition as sr

import nova_config


def init_microphone() -> None:
    """Microphone is managed by SpeechRecognition/PyAudio."""
    print("[NOVA] Using SpeechRecognition built-in microphone handling.")


def _log_error(message: str) -> None:
    try:
        with open(config.ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} [VOICE] {message}\n")
    except OSError:
        pass


def listen() -> Optional[str]:
    """Listen via SpeechRecognition with automatic silence detection."""
    if config.OPENAI_API_KEY in ("", "your_key_here"):
        _log_error("OpenAI API key not configured")
        print("[NOVA] Error: OpenAI API key not configured")
        return ""

    recognizer = sr.Recognizer()

    try:
        with sr.Microphone() as source:
            print("[NOVA] Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print("[NOVA] Listening... speak now.")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)

        text = recognizer.recognize_openai(
            audio,
            api_key=config.OPENAI_API_KEY,
            model="whisper-1",
        )
        print(f"[NOVA] Heard: {text}")
        return text
    except sr.WaitTimeoutError:
        print("[NOVA] Listening timed out — no speech detected.")
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as exc:
        print(f"[NOVA] Error: {exc}")
        _log_error(f"Speech recognition failed: {exc}")
        return ""


def _ensure_pygame_mixer() -> None:
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)


def play_tone(frequency: float, duration: float = 0.25, volume: float = 0.3) -> None:
    """Play a simple tone for activation/deactivation feedback."""
    try:
        _ensure_pygame_mixer()
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave_data = volume * np.sin(2 * np.pi * frequency * t) * np.exp(-4 * t / duration)
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
