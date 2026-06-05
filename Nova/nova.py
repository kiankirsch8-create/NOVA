#!/usr/bin/env python3
"""NOVA — keyboard-activated voice assistant for Mac."""

import json
import re
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timezone
from typing import Optional, Tuple

import anthropic
import rumps
from pynput import keyboard

import nova_apex
import nova_config as config
import nova_memory
import nova_voice

SYSTEM_PROMPT = """You are NOVA, an intelligent AI assistant for a forex trader named Kian.
You have access to real-time APEX trading system data.
You are sharp, direct, and efficient. Never waste words.
Keep all responses under 3 sentences unless asked for detail.
You know everything about the APEX trading system, its strategies,
backtest results, and live trading performance.
When asked about APEX status, use the data provided in the context.
Current APEX knowledge:
- APEX is an automated forex trading engine
- It uses 68 strategies across multiple timeframes
- It identifies macro regimes (STRONG_TAILWIND to STRONG_HEADWIND)
- Best performance: STRONG_TAILWIND + MEDIUM confidence = 72% WR
- Live demo account: €96,908 starting capital on June 1 2026
- Backtest target: restore golden performer that made $247,096 from $10,000

Respond in plain conversational text only — no bullet points, markdown, or headers.
Speak numbers naturally for voice (e.g. "ninety-seven thousand" not "97,000").

When the user wants a local action, call the appropriate tool instead of describing it.
For MT5, tell the user it runs on the VPS and they should open the VPS instead."""

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


def _log_error(message: str) -> None:
    try:
        with open(config.ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} [NOVA] {message}\n")
    except OSError:
        pass


def _open_mac_app(name: str) -> str:
    if name.lower() in ("mt5", "metatrader", "metatrader 5"):
        return "MT5 runs on the VPS. Please open your VPS to access MetaTrader 5."
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
        return "Goodbye.", True
    if name == "clear_conversation":
        return "__CLEAR_CONVERSATION__", False
    return "Done.", False


def _handle_local_command(text: str) -> Tuple[Optional[str], bool]:
    """Fast-path local commands without Claude when patterns are obvious."""
    lowered = text.lower().strip()

    stop_phrases = ("stop", "goodbye", "that's all", "thats all", "exit nova")
    if any(lowered == p or lowered.startswith(p + " ") for p in stop_phrases):
        return "Goodbye.", True

    if lowered in ("clear", "clear memory", "clear conversation"):
        return "__CLEAR_CONVERSATION__", False

    if lowered.startswith("add task "):
        return nova_memory.add_task(text[9:]), False

    if lowered.startswith("add note "):
        return nova_memory.add_note(text[9:]), False

    task_queries = (
        "what are my tasks",
        "my tasks",
        "todo list",
        "what's next",
        "whats next",
    )
    if any(q in lowered for q in task_queries):
        return nova_memory.list_pending_tasks(), False

    mark_match = re.match(r"mark task (?:done )?(.+)", lowered)
    if mark_match:
        return nova_memory.mark_task_done(mark_match.group(1)), False

    if "clear completed tasks" in lowered:
        return nova_memory.clear_completed_tasks(), False

    if "what time is it" in lowered or lowered == "time":
        now = datetime.now().strftime("%I:%M %p").lstrip("0")
        return f"It's {now}.", False

    dashboard_phrases = ("open dashboard", "show apex", "open railway")
    if any(p in lowered for p in dashboard_phrases):
        _open_url(f"{config.APEX_RAILWAY_URL}/dashboard")
        return "Opening the APEX dashboard.", False

    if "open cursor" in lowered:
        return _open_mac_app("Cursor"), False

    if "open mt5" in lowered:
        return "MT5 runs on the VPS. Please open your VPS to access MetaTrader 5.", False

    open_app_match = re.match(r"open (.+)", lowered)
    if open_app_match:
        app = open_app_match.group(1).strip()
        if app not in ("dashboard", "apex", "railway"):
            return _open_mac_app(app.title()), False

    apex_status_phrases = (
        "apex status",
        "how is apex",
        "check backtest",
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
        date_match = re.search(r"from\s+(\d{4}-\d{2}-\d{2})", lowered)
        url = f"{config.APEX_RAILWAY_URL}/dashboard"
        if date_match:
            url = f"{url}?start={date_match.group(1)}"
        _open_url(url)
        return "Opening the backtest start page.", False

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
        if local == "__CLEAR_CONVERSATION__":
            self.clear()
            return "Conversation cleared.", False
        if local is not None:
            return local, end_session

        apex_status = nova_apex.get_apex_status()
        memory_context = nova_memory.get_memory_context()

        context_block = (
            f"Current APEX data: {json.dumps(apex_status, default=str)}\n"
            f"User memory: {memory_context}"
        )

        self.conversation.append({"role": "user", "content": user_text})
        if len(self.conversation) > config.CONVERSATION_MEMORY_LENGTH * 2:
            self.conversation = self.conversation[-config.CONVERSATION_MEMORY_LENGTH * 2 :]

        if config.ANTHROPIC_API_KEY in ("", "your_key_here"):
            return "I'm having trouble thinking right now.", False

        try:
            response = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.MAX_RESPONSE_TOKENS,
                system=f"{SYSTEM_PROMPT}\n\n{context_block}",
                tools=CLAUDE_TOOLS,
                messages=self.conversation,
            )
        except Exception as exc:
            _log_error(f"Claude API failed: {exc}")
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
                        model=config.CLAUDE_MODEL,
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


CMD_KEYS = {
    keyboard.Key.cmd,
    keyboard.Key.cmd_l,
    keyboard.Key.cmd_r,
}


def _is_j_key(key) -> bool:
    if hasattr(key, "char") and key.char:
        return key.char.lower() == "j"
    vk = getattr(key, "vk", None)
    return vk in (38, 106)


class HotkeyMonitor(threading.Thread):
    """Edge-triggered CMD+J monitor — fires once per key press, not on repeat."""

    def __init__(self, on_toggle) -> None:
        super().__init__(daemon=True)
        self._on_toggle = on_toggle
        self._cmd_down = False
        self._j_down = False
        self._listener: Optional[keyboard.Listener] = None

    def _on_press(self, key, injected=False) -> None:
        if injected:
            return
        if key in CMD_KEYS:
            self._cmd_down = True
            return
        if self._cmd_down and nova_voice._is_j_key(key) and not self._j_down:
            self._j_down = True
            self._on_toggle()

    def _on_release(self, key, injected=False) -> None:
        if injected:
            return
        if key in CMD_KEYS:
            self._cmd_down = False
        if _is_j_key(key):
            self._j_down = False

    def run(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        self._listener.join()


class NovaApp(rumps.App):
    def __init__(self) -> None:
        super().__init__(
            config.NOVA_NAME,
            title="⚪",
            quit_button="Quit NOVA",
        )
        self.active = False
        self._stop_event = threading.Event()
        self._session_thread: Optional[threading.Thread] = None
        self.brain = NovaBrain()
        self._hotkey_monitor: Optional[HotkeyMonitor] = None
        self._lock = threading.Lock()
        self._cooldown_until = 0.0

        self.menu = [
            rumps.MenuItem("Toggle Session (⌘J)", callback=self.toggle_session),
            rumps.MenuItem("Status: Inactive", callback=None),
        ]

    def _set_menubar_state(self, active: bool) -> None:
        self.title = "🟢" if active else "⚪"
        self.menu["Status: Inactive"].title = (
            "Status: Active" if active else "Status: Inactive"
        )

    def toggle_session(self, _=None) -> None:
        self._apply_toggle()

    def _request_hotkey_toggle(self) -> None:
        now = time.time()
        if now < self._cooldown_until:
            return
        self._cooldown_until = now + config.HOTKEY_COOLDOWN_SECONDS
        rumps.Timer(lambda _: self._apply_toggle(), 0.01).start()

    def _apply_toggle(self) -> None:
        with self._lock:
            if self.active:
                self._deactivate()
            else:
                self._activate()

    def _activate(self) -> None:
        if self.active:
            return
        if self._session_thread and self._session_thread.is_alive():
            return

        self.active = True
        self._stop_event.clear()
        self._set_menubar_state(True)
        nova_voice.play_activation_sound()
        print("[NOVA] Session started. Speak your command.")

        self._session_thread = threading.Thread(
            target=self._session_loop,
            name="nova-listener",
            daemon=True,
        )
        self._session_thread.start()

    def _deactivate(self) -> None:
        if not self.active:
            return

        self.active = False
        self._stop_event.set()
        self._set_menubar_state(False)
        self.brain.clear()
        nova_voice.play_deactivation_sound()
        print("[NOVA] Session ended.")

    def _session_loop(self) -> None:
        last_activity = time.time()

        try:
            while self.active and not self._stop_event.is_set():
                if time.time() - last_activity > config.SESSION_TIMEOUT:
                    print("[NOVA] Session timed out after 30 seconds of inactivity.")
                    break

                heard = nova_voice.listen()
                if not self.active or self._stop_event.is_set():
                    break

                if heard is None:
                    if time.time() - last_activity > config.SESSION_TIMEOUT:
                        break
                    continue

                if heard == "":
                    nova_voice.speak("I didn't catch that, please try again")
                    last_activity = time.time()
                    continue

                last_activity = time.time()

                if not heard.strip():
                    continue

                response, end_session = self.brain.think(heard)
                if not self.active or self._stop_event.is_set():
                    break

                if not nova_voice.speak(response):
                    print(f"[NOVA] {response}")

                if end_session:
                    break

                last_activity = time.time()
        finally:
            with self._lock:
                if self.active:
                    self.active = False
                    self._stop_event.set()
                    self._set_menubar_state(False)
                    self.brain.clear()
                    nova_voice.play_deactivation_sound()
                    print("[NOVA] Session ended.")

    @rumps.clicked("Toggle Session (⌘J)")
    def menu_toggle(self, _=None) -> None:
        self.toggle_session()


def _start_hotkey_monitor(app: NovaApp) -> HotkeyMonitor:
    monitor = HotkeyMonitor(on_toggle=app._request_hotkey_toggle)
    monitor.start()
    return monitor


def main() -> None:
    print(f"[NOVA] Starting {config.NOVA_NAME} for {config.USER_NAME}")
    print(f"[NOVA] Press {config.ACTIVATION_HOTKEY.upper()} to activate/deactivate.")
    print("[NOVA] Menubar icon: green = active, grey = inactive.")

    nova_voice.init_microphone()

    app = NovaApp()
    app._hotkey_monitor = _start_hotkey_monitor(app)
    app.run()


if __name__ == "__main__":
    main()
