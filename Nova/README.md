# NOVA — AI Voice Assistant

NOVA is a keyboard-activated voice assistant for Mac, connected to the APEX trading ecosystem. Press **CMD+J** to start or stop a listening session. NOVA hears you via Whisper, thinks with Claude, and responds with ElevenLabs voice.

## Requirements

- macOS
- Python 3.10+
- Microphone access
- Accessibility access (for global hotkey)

## Installation

1. Install dependencies:

```bash
cd Nova
pip install -r requirements.txt
```

2. Fill in API keys in `nova_config.py`:

   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`
   - `ELEVENLABS_API_KEY`

3. Run NOVA:

```bash
python nova.py
```

Or double-click `start_nova.sh` (make it executable first: `chmod +x start_nova.sh`).

## Usage

1. Start NOVA — it runs in the background with a menubar icon.
2. Press **CMD+J** to activate (pleasant chime plays).
3. Speak your command when you see `listening...` in the terminal.
4. NOVA responds by voice and immediately listens for the next command.
5. Press **CMD+J** again to stop, or say "stop" / "goodbye".
6. Sessions auto-end after 30 seconds of no voice input.

**Menubar indicator:** green circle = active session, grey circle = inactive.

## Mac Permissions

Grant these in **System Settings → Privacy & Security**:

| Permission      | Why                                      |
|-----------------|------------------------------------------|
| **Microphone**  | Voice input via Whisper                  |
| **Accessibility** | Global CMD+J hotkey via pynput       |

Restart NOVA after granting permissions.

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
- Hotkey, silence detection, session timeout
- Claude model and token limits

## Troubleshooting

- Errors are logged to `nova_errors.log`.
- If ElevenLabs fails, responses print to the terminal.
- If Whisper fails, NOVA says "I didn't catch that, please try again".
- If Claude fails, NOVA says "I'm having trouble thinking right now".

## Files

| File              | Purpose                              |
|-------------------|--------------------------------------|
| `nova.py`         | Main application entry point         |
| `nova_config.py`  | API keys and settings                |
| `nova_apex.py`    | APEX data fetching                   |
| `nova_memory.py`  | Tasks and notes                      |
| `nova_voice.py`   | Whisper input, ElevenLabs output     |
| `nova_memory.json`| Persistent task/note storage         |
