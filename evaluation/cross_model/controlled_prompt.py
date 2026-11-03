"""The controlled prompt used to compare Code Llama, ChatGPT and Claude.

Why this exists
---------------
The tutoring agent is Code Llama *plus* a state machine, output guards, a retry
loop and canned fallback questions. ChatGPT and Claude cannot be run behind that
scaffolding, so to compare the *models* every one of them (Code Llama included)
is given the same single, frozen system prompt instead. The prompt reuses the
project's own wording (``backend/agent/prompts.py``) so that it tests the same
pedagogy, and moves the stage selection / conclusion rules, which the agent
normally enforces in code, into the prompt.

What is frozen
--------------
* ``controlled_prompt.txt``                 - the template
* ``controlled_prompt_language_notes.json`` - the per-language note
* the message layout below (first user message = problem + code + student text;
  later user messages = the student's text only)
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PROMPT_VERSION = "controlled_prompt"
LANGUAGES = ("python", "javascript")
LANGUAGE_LABELS = {"python": "Python", "javascript": "JavaScript"}

_DIR = Path(__file__).resolve().parent
_TEMPLATE_FILE = _DIR / "controlled_prompt.txt"
_NOTES_FILE = _DIR / "controlled_prompt_language_notes.json"
_PLACEHOLDER = "{{LANGUAGE_NOTE}}"


def _normalise(text: str) -> str:
    """Line-ending-insensitive, so Windows (CRLF) and Linux (LF) hash identically."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read(path: Path) -> str:
    return _normalise(path.read_text(encoding="utf-8"))


def build_system_prompt(language: str) -> str:
    """The full system prompt for ``language``. Identical for every model."""
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {LANGUAGES}, got {language!r}")
    template = _read(_TEMPLATE_FILE)
    if _PLACEHOLDER not in template:
        raise RuntimeError(f"{_TEMPLATE_FILE.name} is missing {_PLACEHOLDER}")
    note = json.loads(_read(_NOTES_FILE)).get(language, "").strip()
    rendered = template.replace(_PLACEHOLDER, f"\n{note}\n" if note else "")
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


def prompt_sha256(language: str) -> str:
    return hashlib.sha256(build_system_prompt(language).encode("utf-8")).hexdigest()


def build_first_user_message(code: str, problem: str, student_message: str, language: str) -> str:
    """First student turn: same fields, same order as the agent's own prompt body."""
    problem_block = f"Problem statement:\n{problem}\n" if problem else "Problem statement: (not provided)\n"
    return (
        f"{problem_block}\n"
        f"Student code:\n```{language}\n{code}\n```\n\n"
        f"Student message:\n{student_message}"
    )


def build_messages(problem: dict, student_turns: list[str], tutor_replies: list[str]) -> list[dict]:
    """Chat history (no system message) for the next tutor reply.

    ``student_turns`` has one more item than ``tutor_replies``: the student has
    just spoken and the tutor must answer.
    """
    if len(student_turns) != len(tutor_replies) + 1:
        raise ValueError("student_turns must be exactly one longer than tutor_replies")
    messages = [{
        "role": "user",
        "content": build_first_user_message(
            problem["code"], problem["problem"], student_turns[0], problem["language"]
        ),
    }]
    for reply, student in zip(tutor_replies, student_turns[1:]):
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": student})
    return messages


def manual_first_message(problem: dict, student_message: str) -> str:
    """For pasting into a chat UI that has no system-prompt box: instructions, then turn 1."""
    return (
        "=== TUTOR INSTRUCTIONS (follow for the whole conversation) ===\n"
        f"{build_system_prompt(problem['language'])}\n"
        "=== END OF INSTRUCTIONS ===\n\n"
        + build_first_user_message(problem["code"], problem["problem"], student_message, problem["language"])
    )
