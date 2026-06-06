#!/usr/bin/env python3
"""NOVA — voice command center for the APEX trading ecosystem."""

import json
import re
import subprocess
import threading
import webbrowser
from datetime import datetime, timezone
from typing import Optional, Tuple

import anthropic

import nova_apex
import nova_config as config
import nova_memory
import nova_voice

SYSTEM_PROMPT = """You are NOVA, the intelligent assistant for Kian's APEX trading ecosystem.
You are like Jarvis from Iron Man — sharp, direct, efficient, and genuinely
helpful. You know everything about APEX.

APEX is an autonomous forex trading engine that:
- Uses 68 strategies across multiple timeframes
- Identifies macro regimes (STRONG_TAILWIND produces 72% win rate)
- Made $247,096 from $10,000 in 2.3 years in backtesting
- Is currently live trading on a €96,908 demo account since June 1 2026
- Is running a v7.6 backtest currently showing 35% better than v7.5

Kian is 18 years old building a trading empire. His goal is to pass a
funded account challenge (€100k-200k) in 2026, compound profits quietly,
and build the full APEX ecosystem.

Rules for responses:
- Keep responses under 3 sentences for simple questions
- Speak numbers naturally: 'ninety-seven thousand' not '97,000'
- Be direct and confident, never vague
- When you have live APEX data in context, use it specifically
- Never say 'I don't have access to' — always try to help
- Address Kian by name occasionally

Respond in plain conversational text only — no bullet points, markdown, or headers."""

CLAUDE_TOOLS = [
    {
        "name": "add_task",
        "description": "Add a task to the user's todo list.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Task description"}},
            "required": ["text"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List all pending tasks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mark_task_done",
        "description": "Mark a task complete by number or description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Task id number or partial description",
                }
            },
            "required": ["identifier"],
        },
    },
    {
        "name": "clear_completed_tasks",
        "description": "Remove all completed tasks from the list.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_note",
        "description": "Save a note for later.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "open_dashboard",
        "description": "Open the APEX dashboard in the browser.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "open_backtest_start",
        "description": "Open the backtest start page in the browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Optional start date YYYY-MM-DD",
                }
            },
        },
    },
    {
        "name": "open_url",
        "description": "Open a URL in the default browser.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "open_app",
        "description": "Open a Mac application by name.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_time",
        "description": "Get the current local time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "end_session",
        "description": "End the NOVA voice session when user says stop, goodbye, etc.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_conversation",
        "description": "Clear in-session conversation memory.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

STOP_PHRASES = (
    "stop",
    "goodbye",
    "exit",
    "that is all",
    "that's all",
    "thats all",
    "exit nova",
)


def _log_error(message: str) -> None:
    try:
        with open(config.ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} [NOVA] {message}\n")
    except OSError:
        pass


def _strip_nova_prefix(text: str) -> str:
    return re.sub(r"^(?:hey\s+)?nova[,\s]+", "", text.strip(), flags=re.IGNORECASE)


def _is_stop_command(text: str) -> bool:
    lowered = _strip_nova_prefix(text).lower().strip()
    return any(phrase in lowered for phrase in STOP_PHRASES)


def handle_open_command(text: str) -> Optional[str]:
    """Open apps and URLs by voice command."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["dashboard", "railway"]):
        subprocess.Popen(["open", f"{config.APEX_RAILWAY_URL}/dashboard"])
        return "Opening the APEX dashboard."
    if "github" in text_lower:
        subprocess.Popen(["open", "https://github.com/kiankirsch8-create/APEX"])
        return "Opening GitHub."
    if "cursor" in text_lower:
        subprocess.Popen(["open", "-a", "Cursor"])
        return "Opening Cursor."
    if "terminal" in text_lower:
        subprocess.Popen(["open", "-a", "Terminal"])
        return "Opening Terminal."
    if "vps" in text_lower and "open" in text_lower:
        return (
            "The VPS is at 192.248.191.134. "
            "Use Remote Desktop or SSH to connect."
        )
    return None


def _open_mac_app(name: str) -> str:
    if name.lower() in ("mt5", "metatrader", "metatrader 5"):
        return "MT5 runs on the VPS at 192.248.191.134. Use Remote Desktop to connect."
    try:
        subprocess.run(["open", "-a", name], check=True)
        return f"Opening {name}."
    except subprocess.CalledProcessError as exc:
        _log_error(f"Failed to open app {name}: {exc}")
        return f"I couldn't open {name}."


def _open_url(url: str) -> str:
    try:
        webbrowser.open(url)
        return "Opening in your browser."
    except Exception as exc:
        _log_error(f"Failed to open URL {url}: {exc}")
        return "I couldn't open that URL."


def _extract_payload(text: str, markers: tuple[str, ...]) -> Optional[str]:
    lowered = text.lower()
    for marker in markers:
        if marker in lowered:
            idx = lowered.index(marker) + len(marker)
            payload = text[idx:].strip(" :,-")
            if payload:
                return payload
    return None


def _daily_briefing() -> str:
    status = nova_apex.get_apex_status()
    apex_line = nova_apex.format_status_for_speech(status)
    tasks = nova_memory.list_pending_tasks()
    return (
        f"Good morning Kian. {apex_line} "
        f"{tasks} "
        "All systems are being monitored."
    )


def _execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run a tool. Returns (result_message, should_end_session)."""
    if name == "add_task":
        return nova_memory.add_task(tool_input.get("text", "")), False
    if name == "list_tasks":
        return nova_memory.list_pending_tasks(), False
    if name == "mark_task_done":
        return nova_memory.mark_task_done(tool_input.get("identifier", "")), False
    if name == "clear_completed_tasks":
        return nova_memory.clear_completed_tasks(), False
    if name == "add_note":
        return nova_memory.add_note(tool_input.get("text", "")), False
    if name == "open_dashboard":
        _open_url(f"{config.APEX_RAILWAY_URL}/dashboard")
        return "Opening the APEX dashboard.", False
    if name == "open_backtest_start":
        date = tool_input.get("date")
        url = f"{config.APEX_RAILWAY_URL}/dashboard"
        if date:
            url = f"{config.APEX_RAILWAY_URL}/dashboard?start={date}"
        _open_url(url)
        return "Opening the backtest start page.", False
    if name == "open_url":
        return _open_url(tool_input.get("url", "")), False
    if name == "open_app":
        app_name = tool_input.get("name", "")
        if app_name.lower() == "railway":
            return _open_url(f"{config.APEX_RAILWAY_URL}/dashboard"), False
        if app_name.lower() == "cursor":
            return _open_mac_app("Cursor"), False
        return _open_mac_app(app_name), False
    if name == "get_time":
        now = datetime.now().strftime("%I:%M %p").lstrip("0")
        return f"It's {now}.", False
    if name == "end_session":
        return "Goodbye Kian.", True
    if name == "clear_conversation":
        return "__CLEAR_CONVERSATION__", False
    return "Done.", False


def _handle_local_command(text: str) -> Tuple[Optional[str], bool]:
    """Fast-path local commands without Claude when patterns are obvious."""
    cleaned = _strip_nova_prefix(text)
    lowered = cleaned.lower().strip()

    if _is_stop_command(cleaned):
        return "Goodbye Kian.", True

    if lowered in ("clear", "clear memory", "clear conversation"):
        return "__CLEAR_CONVERSATION__", False

    open_response = handle_open_command(cleaned)
    if open_response:
        return open_response, False

    if any(p in lowered for p in ("good morning", "brief me", "daily briefing")):
        return _daily_briefing(), False

    task_text = _extract_payload(cleaned, ("add task", "remember to", "don't forget", "dont forget"))
    if task_text:
        return nova_memory.add_task(task_text), False

    note_text = _extract_payload(cleaned, ("add note",))
    if note_text:
        return nova_memory.add_note(note_text), False

    task_queries = (
        "what are my tasks",
        "my tasks",
        "todo list",
        "what's next",
        "whats next",
    )
    if any(q in lowered for q in task_queries):
        return nova_memory.list_pending_tasks(), False

    if "read my notes" in lowered or "my notes" in lowered:
        return nova_memory.list_recent_notes(), False

    mark_match = re.search(r"mark task (?:done )?(.+)", lowered)
    if mark_match:
        return nova_memory.mark_task_done(mark_match.group(1)), False

    if "clear completed tasks" in lowered:
        return nova_memory.clear_completed_tasks(), False

    if "what time is it" in lowered or lowered == "time":
        now = datetime.now().strftime("%I:%M %p").lstrip("0")
        return f"It's {now}.", False

    if "open mt5" in lowered:
        return "MT5 runs on the VPS at 192.248.191.134. Use Remote Desktop to connect.", False

    if "vps logs" in lowered or "check the vps logs" in lowered or "check vps logs" in lowered:
        logs = nova_apex.get_live_logs_text()
        tail = logs.splitlines()[-5:]
        return "Recent VPS logs: " + ". ".join(tail) + ".", False

    apex_status_phrases = (
        "apex status",
        "how is apex",
        "how is apex doing",
        "check backtest",
        "what's the backtest",
        "whats the backtest",
        "how are the live trades",
        "how is live",
        "check live",
        "how much money",
        "what is the capital",
    )
    if any(p in lowered for p in apex_status_phrases):
        status = nova_apex.get_apex_status()
        if status.get("stale"):
            prefix = "APEX data is currently unavailable, using last known status. "
        else:
            prefix = ""
        return prefix + nova_apex.format_status_for_speech(status), False

    if lowered.startswith("start backtest") or lowered.startswith("run backtest"):
        date_match = re.search(r"from\s+(\w+\s+\d{4}|\d{4}-\d{2}-\d{2})", lowered)
        url = f"{config.APEX_RAILWAY_URL}/dashboard"
        if date_match:
            url = f"{url}?start={date_match.group(1)}"
        _open_url(url)
        spoken_date = date_match.group(1) if date_match else "the selected date"
        return f"Starting new backtest from {spoken_date}.", False

    return None, False


class NovaBrain:
    def __init__(self) -> None:
        self.conversation: list[dict] = []
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def clear(self) -> None:
        self.conversation.clear()

    def think(self, user_text: str) -> tuple[str, bool]:
        """
        Process user input through Claude with APEX context.
        Returns (spoken_response, should_end_session).
        """
        local, end_session = _handle_local_command(user_text)
        print("[DEBUG] local command checked")
        if local == "__CLEAR_CONVERSATION__":
            self.clear()
            return "Conversation cleared.", False
        if local is not None:
            return local, end_session

        apex_status = nova_apex.get_apex_status()
        print("[DEBUG] apex fetched")
        memory_context = nova_memory.get_memory_context()
        context_block = (
            f"Current APEX status: {json.dumps(apex_status, default=str)}\n"
            f"User memory: {memory_context}"
        )

        self.conversation.append({"role": "user", "content": user_text})
        print("[DEBUG] calling Claude...")
        if len(self.conversation) > config.CONVERSATION_MEMORY_LENGTH * 2:
            self.conversation = self.conversation[-config.CONVERSATION_MEMORY_LENGTH * 2 :]

        if config.ANTHROPIC_API_KEY in ("", "your_key_here"):
            return "I'm having trouble thinking right now.", False

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=config.MAX_RESPONSE_TOKENS,
                system=f"{SYSTEM_PROMPT}\n\n{context_block}",
                tools=CLAUDE_TOOLS,
                messages=self.conversation,
            )
            print("[DEBUG] Claude returned")
        except Exception as exc:
            _log_error(f"Claude API failed: {exc}")
            print(f"[NOVA] Claude error: {exc}")
            return "I'm having trouble thinking right now.", False

        tool_results = []
        spoken_parts: list[str] = []
        end_session = False
        clear_conversation = False

        for block in response.content:
            if block.type == "text" and block.text.strip():
                spoken_parts.append(block.text.strip())
            elif block.type == "tool_use":
                result, should_end = _execute_tool(block.name, block.input or {})
                if result == "__CLEAR_CONVERSATION__":
                    clear_conversation = True
                    result = "Conversation cleared."
                if should_end:
                    end_session = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
                if not spoken_parts:
                    spoken_parts.append(result)

        assistant_content = response.content
        self.conversation.append({"role": "assistant", "content": assistant_content})

        if tool_results:
            self.conversation.append({"role": "user", "content": tool_results})
            if not any(b.type == "text" and b.text.strip() for b in response.content):
                try:
                    followup = self._client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=config.MAX_RESPONSE_TOKENS,
                        system=f"{SYSTEM_PROMPT}\n\n{context_block}",
                        tools=CLAUDE_TOOLS,
                        messages=self.conversation,
                    )
                    for block in followup.content:
                        if block.type == "text" and block.text.strip():
                            spoken_parts.append(block.text.strip())
                    self.conversation.append(
                        {"role": "assistant", "content": followup.content}
                    )
                except Exception as exc:
                    _log_error(f"Claude follow-up failed: {exc}")

        if clear_conversation:
            self.clear()

        reply = " ".join(spoken_parts).strip()
        print(f"[DEBUG] reply ready: {reply[:50]}")
        if not reply:
            reply = "I'm not sure how to help with that."

        if apex_status.get("stale") and any(
            w in user_text.lower() for w in ("apex", "backtest", "live", "trading", "capital")
        ):
            if "unavailable" not in reply.lower():
                reply = (
                    "APEX data is currently unavailable, using last known status. " + reply
                )

        return reply, end_session


session_active = False
brain = NovaBrain()


def _wait_for_stop() -> None:
    """Background thread: second Enter press stops the active session."""
    global session_active
    input()
    session_active = False
    print("[NOVA] Stop requested.")


def run_session() -> None:
    """Record, transcribe, think, and speak until session_active becomes False."""
    global session_active

    try:
        nova_voice.play_activation_sound()
        print("[NOVA] Session started. Speak your command.")

        while session_active:
            heard = nova_voice.listen()
            if not session_active:
                break

            if not heard or not heard.strip():
                nova_voice.speak("I didn't catch that, please try again")
                continue

            print(f"[NOVA] Processing: {heard}")

            if _is_stop_command(heard):
                nova_voice.speak("Goodbye Kian.")
                session_active = False
                break

            open_response = handle_open_command(heard)
            if open_response:
                print(f"[NOVA] Response: {open_response}")
                if not nova_voice.speak(open_response):
                    print(f"[NOVA] {open_response}")
                continue

            response, end_session = brain.think(heard)
            if not session_active:
                break

            print(f"[NOVA] Response: {response}")
            if not nova_voice.speak(response):
                print(f"[NOVA] {response}")

            if end_session:
                session_active = False
                break
    finally:
        brain.clear()
        session_active = False
        nova_voice.play_deactivation_sound()
        print("[NOVA] Session ended.")


def main() -> None:
    global session_active

    print(f"[NOVA] Starting {config.NOVA_NAME} for {config.USER_NAME}")
    print("Press ENTER to start speaking, press ENTER again to stop")

    nova_voice.init_microphone()

    while True:
        input()
        session_active = True
        threading.Thread(target=_wait_for_stop, daemon=True).start()
        run_session()


if __name__ == "__main__":
    main()
