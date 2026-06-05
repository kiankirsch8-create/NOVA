"""NOVA configuration template — copy to nova_config.py and fill in API keys."""

# API Keys (fill in before running)
ANTHROPIC_API_KEY = "your_key_here"
OPENAI_API_KEY = "your_key_here"
ELEVENLABS_API_KEY = "your_key_here"
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel; use pNInz6obpgDQGcFmaJgB for Adam

# APEX
APEX_RAILWAY_URL = "https://apex-production-b5bc.up.railway.app"
APEX_LIVE_START_CAPITAL = 96908.79
APEX_LIVE_START_DATE = "2026-06-01"

# Hotkey and audio
ACTIVATION_HOTKEY = "cmd+j"
HOTKEY_COOLDOWN_SECONDS = 3
SESSION_TIMEOUT = 30
MAX_RESPONSE_TOKENS = 300
CONVERSATION_MEMORY_LENGTH = 5

# Identity
NOVA_NAME = "NOVA"
USER_NAME = "Kian"

# Audio recording (16000 Hz mono — required by Google Speech Recognition)
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.008
SILENCE_DURATION = 1.5
MIN_RECORDING_SECONDS = 1.0
MAX_RECORDING_SECONDS = 30.0
CHUNK_DURATION = 0.1
MIN_WAV_BYTES = 1000

# API caching (seconds)
BACKTEST_CACHE_SECONDS = 60
LIVE_CACHE_SECONDS = 30

# Claude
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ElevenLabs
ELEVENLABS_MODEL = "eleven_monolingual_v1"
ELEVENLABS_STABILITY = 0.75
ELEVENLABS_SIMILARITY_BOOST = 0.75

# Paths
MEMORY_FILE = "nova_memory.json"
ERROR_LOG_FILE = "nova_errors.log"
