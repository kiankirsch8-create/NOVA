"""Task list and context storage — persists to nova_memory.json."""

import json
import os
from datetime import date

import nova_config as config

DEFAULT_MEMORY = {"tasks": [], "notes": [], "context": {}}


def _memory_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, config.MEMORY_FILE)


def load_memory() -> dict:
    path = _memory_path()
    if not os.path.exists(path):
        save_memory(DEFAULT_MEMORY)
        return dict(DEFAULT_MEMORY)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in DEFAULT_MEMORY:
            data.setdefault(key, DEFAULT_MEMORY[key])
        return data
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_MEMORY)


def save_memory(data: dict) -> None:
    path = _memory_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _next_task_id(tasks: list) -> int:
    if not tasks:
        return 1
    return max(t.get("id", 0) for t in tasks) + 1


def add_task(text: str) -> str:
    data = load_memory()
    task = {
        "id": _next_task_id(data["tasks"]),
        "text": text.strip(),
        "created": date.today().isoformat(),
        "done": False,
    }
    data["tasks"].append(task)
    save_memory(data)
    return f"Added task: {task['text']}"


def list_pending_tasks() -> str:
    data = load_memory()
    pending = [t for t in data["tasks"] if not t.get("done")]
    if not pending:
        return "You have no pending tasks."
    lines = [f"Task {t['id']}: {t['text']}" for t in pending]
    return "Your pending tasks are: " + ". ".join(lines) + "."


def mark_task_done(identifier: str) -> str:
    data = load_memory()
    identifier = identifier.strip()
    matched = None

    if identifier.isdigit():
        task_id = int(identifier)
        for task in data["tasks"]:
            if task["id"] == task_id and not task.get("done"):
                matched = task
                break
    else:
        needle = identifier.lower()
        for task in data["tasks"]:
            if not task.get("done") and needle in task["text"].lower():
                matched = task
                break

    if not matched:
        return f"I couldn't find a pending task matching {identifier}."

    matched["done"] = True
    save_memory(data)
    return f"Marked task {matched['id']} as done: {matched['text']}."


def clear_completed_tasks() -> str:
    data = load_memory()
    before = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if not t.get("done")]
    removed = before - len(data["tasks"])
    save_memory(data)
    if removed == 0:
        return "No completed tasks to clear."
    return f"Cleared {removed} completed task{'s' if removed != 1 else ''}."


def add_note(text: str) -> str:
    data = load_memory()
    note = {"text": text.strip(), "created": date.today().isoformat()}
    data["notes"].append(note)
    save_memory(data)
    return "Note saved."


def get_memory_context() -> str:
    """Summary of tasks and notes for Claude context."""
    data = load_memory()
    pending = [t for t in data["tasks"] if not t.get("done")]
    parts = []
    if pending:
        task_str = "; ".join(f"{t['id']}. {t['text']}" for t in pending)
        parts.append(f"Pending tasks: {task_str}")
    if data["notes"]:
        recent = data["notes"][-5:]
        note_str = "; ".join(n["text"] for n in recent)
        parts.append(f"Recent notes: {note_str}")
    return "\n".join(parts) if parts else "No pending tasks or notes."
