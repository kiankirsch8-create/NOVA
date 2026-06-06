# NOVA — AI Voice Assistant

NOVA is a terminal voice assistant for Mac, connected to the APEX trading ecosystem. Press **ENTER** to start or stop a listening session. NOVA hears you via Google speech recognition (free), thinks with Claude, and responds with ElevenLabs voice.

## Requirements

- macOS
- Python 3.9+
- Microphone access
- Terminal access (runs from Terminal or iTerm)

## Installation

1. Install dependencies:

```bash
cd Nova
pip install -r requirements.txt
```

2. Create your config from the template and fill in API keys:

```bash
cp nova_config.example.py nova_config.py
```

   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`
   - `ELEVENLABS_API_KEY`

   `nova_config.py` is gitignored so keys are not committed.

3. Run NOVA:

```bash
python nova.py
```

Or double-click `start_nova.sh` (make it executable first: `chmod +x start_nova.sh`).

## Usage

1. Start NOVA — it runs in the terminal.
2. Press **ENTER** to start a session (pleasant chime plays).
3. Speak your command — recording stops automatically when you pause.
4. NOVA responds by voice and listens again for your next command.
5. Press **ENTER** again to stop, or say "stop" / "goodbye".
6. Press **ENTER** once more to start a new session.

## Mac Permissions

Grant these in **System Settings → Privacy & Security**:

| Permission      | Why                                      |
|-----------------|------------------------------------------|
| **Microphone**  | Voice input via Google speech recognition |
Restart NOVA after granting microphone permission.

## Voice Commands

NOVA understands natural language. Examples:

- **APEX:** "APEX status", "how is live trading", "what is the capital"
- **Tasks:** "Add task check APEX results", "what are my tasks", "mark task done 1"
- **Notes:** "Add note review strategy performance"
- **Mac:** "Open Cursor", "Open dashboard", "Open Safari"
- **General:** "What time is it", "stop", "goodbye"

Tasks and notes persist in `nova_memory.json` between sessions.

## APEX Integration

NOVA reads from the live APEX Railway APIs (read-only):

- Backtest status: `/api/chrono/active`
- Live trading: `/api/live/status`
- Dashboard summary: `/api/dashboard/summary`

If APIs are offline, NOVA uses the last cached data and tells you.

## Configuration

Edit `nova_config.py` to change:

- Voice (Rachel or Adam via `ELEVENLABS_VOICE_ID`)
- Recording duration
- Claude model and token limits

## Troubleshooting

- Errors are logged to `nova_errors.log`.
- If ElevenLabs fails, responses print to the terminal.
- If speech recognition fails, NOVA says "I didn't catch that, please try again".
- If Claude fails, NOVA says "I'm having trouble thinking right now".

## Files

| File              | Purpose                              |
|-------------------|--------------------------------------|
| `nova.py`         | Main application entry point         |
| `nova_config.py`  | API keys and settings                |
| `nova_apex.py`    | APEX data fetching                   |
| `nova_memory.py`  | Tasks and notes                      |
| `nova_voice.py`   | Speech input, ElevenLabs output      |
| `nova_memory.json`| Persistent task/note storage         |
