"""Conversation state for the tutoring agent.

The tutor is deliberately stateful: Socratic tutoring works best when the next
question depends on what the student said previously and on the current stage
of the reasoning process.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Conversation:
    code: str = ""
    language: str = "python"
    messages: List[Message] = field(default_factory=list)
    stage: int = 0
    turns: int = 0
    diagnostic: str = ""
    # Number of student-facing Socratic questions already produced.
    question_count: int = 0
    # Internal learning-state flags. These are never exposed to the frontend.
    problem_identified: bool = False
    solution_proposed: bool = False
    solution_correct: bool = False
    solution_validated: bool = False
    # True once the student's reasoning is sufficient to finish the dialogue.
    concluded: bool = False


_conversations: Dict[str, Conversation] = {}


def create_conversation(code: str = "", language: str = "python") -> str:
    conversation_id = str(uuid4())
    _conversations[conversation_id] = Conversation(code=code, language=language)
    return conversation_id


def get_conversation(conversation_id: str) -> Optional[Conversation]:
    return _conversations.get(conversation_id)


def get_or_create_conversation(
    conversation_id: Optional[str],
    code: str,
    language: str,
) -> tuple[str, Conversation]:
    if conversation_id and conversation_id in _conversations:
        conversation = _conversations[conversation_id]
        conversation.code = code or conversation.code
        conversation.language = language or conversation.language
        return conversation_id, conversation

    new_id = create_conversation(code=code, language=language)
    return new_id, _conversations[new_id]


def add_message(conversation: Conversation, role: str, content: str) -> None:
    conversation.messages.append(Message(role, content))


def history_as_text(conversation: Conversation, limit: int = 12) -> str:
    recent = conversation.messages[-limit:]
    if not recent:
        return "No previous conversation."

    return "\n\n".join(
        f"{message.role.title()}: {message.content}" for message in recent
    )


def clear_conversation(conversation_id: str) -> bool:
    return _conversations.pop(conversation_id, None) is not None

