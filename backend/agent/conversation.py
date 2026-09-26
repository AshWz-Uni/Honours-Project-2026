"""Conversation state for the tutoring agent.

The tutor is deliberately stateful: Socratic tutoring works best when the next
question depends on what the student has already said and on what they have
already worked out. Progress is therefore stored as learning-state flags, and
the tutoring stage is *derived* from those flags (see ``tutor_agent``), not
advanced blindly by a turn counter.
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
    # Optional plain-English problem statement (e.g. the LeetCode task). Gives the tutor the requirement it needs to judge a proposed fix.
    problem: str = ""
    messages: List[Message] = field(default_factory=list)
    # Name of the stage used for the most recent tutor turn.
    stage_name: str = "clarify"
    # Tutor turns spent in the diagnosis phase / consolidation phase.
    diagnosis_turns: int = 0
    consolidation_turns: int = 0
    turns: int = 0
    diagnostic: str = ""
    # Number of student-facing Socratic questions already produced.
    question_count: int = 0
    # Internal learning-state flags. These are never sent to the chat UI.
    problem_identified: bool = False
    solution_proposed: bool = False
    solution_correct: bool = False
    solution_validated: bool = False
    # True once the dialogue has finished.
    concluded: bool = False


_conversations: Dict[str, Conversation] = {}


def create_conversation(code: str = "", problem: str = "") -> str:
    conversation_id = str(uuid4())
    _conversations[conversation_id] = Conversation(
        code=code, problem=problem or ""
    )
    return conversation_id


def get_conversation(conversation_id: str) -> Optional[Conversation]:
    return _conversations.get(conversation_id)


def get_or_create_conversation(
    conversation_id: Optional[str],
    code: str,
    problem: Optional[str] = None,
) -> tuple[str, Conversation]:
    if conversation_id and conversation_id in _conversations:
        conversation = _conversations[conversation_id]
        conversation.code = code or conversation.code
        conversation.problem = problem or conversation.problem
        return conversation_id, conversation

    new_id = create_conversation(code=code, problem=problem or "")
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
