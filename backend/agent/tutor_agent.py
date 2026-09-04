"""Socratic tutoring orchestration.

The important design choice here is that Code Llama is used in two separate
roles:

1. A private diagnostic pass identifies what the student should reason about.
2. A student-facing Socratic pass converts that diagnosis into ONE question.

The diagnostic answer is never returned to the frontend.
"""

import re
from dataclasses import dataclass

from backend.agent.conversation import (
    Conversation,
    add_message,
    get_or_create_conversation,
    history_as_text,
)
from backend.agent.prompts import build_diagnostic_prompt, build_socratic_prompt
from backend.services.llm_service import ask_llm


STAGES = (
    "clarify",
    "predict",
    "trace",
    "diagnose",
    "propose",
    "test",
    "reflect",
)

# Phrases that are especially likely to indicate that the model leaked a fix.
# This is a safety net, not the primary tutoring mechanism.
SOLUTION_LEAK_PATTERNS = [
    r"\bthe (?:answer|solution) is\b",
    r"\byou (?:should|need to) (?:change|replace|remove|add|use)\b",
    r"\bchange (?:line|the line)\b",
    r"\breplace .* with\b",
    r"\bhere(?:'s| is) (?:the )?(?:correct|fixed) (?:code|solution)\b",
    r"```(?:python|javascript|js)?\s*[^`]+```",
]


def _contains_solution_leak(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.DOTALL) for pattern in SOLUTION_LEAK_PATTERNS)


def _clean_question(text: str) -> str:
    """Normalise the model output into a single student-facing question."""
    text = text.strip()
    text = re.sub(r"^(?:tutor|assistant)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "")

    # Remove transcript-like prefixes if the model ignored the instruction.
    text = re.sub(r"^(?:student|tutor)\s*:\s*", "", text, flags=re.IGNORECASE)

    # Keep the first complete question. This prevents the model from turning
    # one turn into a mini lesson with several questions/answers.
    matches = list(re.finditer(r"[^?]*\?", text, flags=re.DOTALL))
    if matches:
        return matches[0].group(0).strip()

    # Last-resort conversion. The backend never intentionally returns a
    # non-question because the UI is designed around Socratic turns.
    sentence = text.split("\n", 1)[0].strip()
    return sentence.rstrip(".") + "?"


def _fallback_question(conversation: Conversation) -> str:
    """Safe questions used when the model violates the output contract."""
    stage = STAGES[min(conversation.stage, len(STAGES) - 1)]
    if stage == "clarify":
        return "What should this part of your program do when it receives the input you are testing?"
    if stage == "predict":
        return "Before changing anything, what output or behaviour do you expect this code to produce, and why?"
    if stage == "trace":
        return "Which statement first produces a value that differs from your expectation, and what value does it produce?"
    if stage == "diagnose":
        return "What assumption about this variable, condition, or function could explain the behaviour you observed?"
    if stage == "propose":
        return "What change could you make yourself to test that hypothesis, and why do you expect it to affect the behaviour?"
    if stage == "test":
        return "After testing your proposed change, what changed in the program's behaviour and what does that tell you?"
    return "What did you learn from this debugging process that you could apply to a similar problem?"


def _advance_stage(conversation: Conversation, student_message: str) -> None:
    """Move through the tutoring scaffold without skipping to a solution."""
    # Early turns deliberately stay in the foundational stages. Later stages
    # require the student to contribute reasoning rather than merely asking a
    # new question.
    if conversation.turns == 0:
        conversation.stage = 0
        return

    if conversation.stage < len(STAGES) - 1:
        conversation.stage += 1


def generate_tutor_response(
    code: str,
    question: str,
    conversation_id: str | None = None,
    language: str = "python",
) -> tuple[str, str]:
    """Generate one Socratic tutor question and retain the tutoring state."""
    conversation_id, conversation = get_or_create_conversation(
        conversation_id=conversation_id,
        code=code,
        language=language,
    )

    add_message(conversation, "student", question)
    history = history_as_text(conversation)
    stage = STAGES[min(conversation.stage, len(STAGES) - 1)]

    # Pass 1: private reasoning. This can contain the likely answer because it
    # never leaves the backend. It gives the question generator a concrete
    # target instead of relying on a generic system prompt.
    diagnostic_prompt = build_diagnostic_prompt(
        code=conversation.code,
        question=question,
        history=history,
        language=conversation.language,
    )
    diagnostic = ask_llm(diagnostic_prompt, temperature=0.15)
    conversation.diagnostic = diagnostic

    # Pass 2: student-facing Socratic question.
    socratic_prompt = build_socratic_prompt(
        code=conversation.code,
        question=question,
        history=history,
        diagnostic=diagnostic,
        language=conversation.language,
        stage=stage,
    )
    response = _clean_question(ask_llm(socratic_prompt, temperature=0.25))

    # Never expose a response that appears to contain a solution. A fresh
    # constrained generation is attempted once, then a deterministic question
    # is returned if Code Llama still violates the contract.
    if _contains_solution_leak(response) or "?" not in response:
        retry_prompt = build_socratic_prompt(
            code=conversation.code,
            question=question,
            history=history,
            diagnostic=diagnostic,
            language=conversation.language,
            stage=stage,
        ) + "\n\nSTRICT OUTPUT CONTRACT: Return exactly one short question and nothing else."
        response = _clean_question(ask_llm(retry_prompt, temperature=0.1))

    if _contains_solution_leak(response) or "?" not in response:
        response = _fallback_question(conversation)

    add_message(conversation, "assistant", response)
    conversation.turns += 1
    _advance_stage(conversation, question)

    return response, conversation_id
