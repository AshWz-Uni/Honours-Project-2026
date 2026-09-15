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
from backend.agent.prompts import (
    build_conclusion_prompt,
    build_diagnostic_prompt,
    build_socratic_prompt,
)
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

MIN_SOCRATIC_QUESTIONS = 5

SOLUTION_LEAK_PATTERNS = [
    r"\bthe (?:answer|solution) is\b",
    r"\byou (?:should|need to) (?:change|replace|remove|add|use)\b",
    r"\bchange (?:line|the line)\b",
    r"\breplace .* with\b",
    r"\bhere(?:'s| is) (?:the )?(?:correct|fixed) (?:code|solution)\b",
    r"```(?:python|javascript|js)?\s*[^`]+```",
]

REPETITION_PATTERNS = [
    r"\bcan you (?:please )?(?:repeat|restate|rephrase) (?:the )?(?:question|problem)\b",
    r"\b(?:please )?(?:repeat|restate|rephrase) (?:the )?(?:question|problem)\b",
    r"\bwhat (?:is|was) your question\b",
    r"\bcan you (?:tell|say) me (?:the )?question again\b",
    r"\bcan you (?:format|reformat) (?:the )?(?:question|problem)\b",
]


def _contains_solution_leak(text: str) -> bool:
    lowered = text.lower()
    return any(
        re.search(pattern, lowered, flags=re.DOTALL)
        for pattern in SOLUTION_LEAK_PATTERNS
    )


def _is_repetition_question(text: str, student_message: str) -> bool:
    lowered = text.lower().strip()
    if any(re.search(pattern, lowered) for pattern in REPETITION_PATTERNS):
        return True

    # Catch a near-copy of the student's question. This avoids responses that
    # technically differ but merely reformat/repeat what the student asked.
    def normalise(value: str) -> str:
        value = value.lower()
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    student = normalise(student_message)
    response = normalise(text)
    if len(student.split()) >= 8 and student in response:
        return True
    return False


def _clean_question(text: str) -> str:
    """Normalise output while preserving a Hint + one Question contract."""
    text = text.strip()
    text = re.sub(r"^(?:tutor|assistant)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "")
    text = re.sub(r"^(?:student|tutor)\s*:\s*", "", text, flags=re.IGNORECASE)

    # Remove markdown code blocks if the model ignored the contract.
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    hint_match = re.search(r"(?:^|\n)\s*Hint\s*:\s*(.+?)(?=\n\s*(?:Question\s*:\s*)|$)", text, flags=re.IGNORECASE | re.DOTALL)
    question_match = re.search(r"(?:^|\n)\s*Question\s*:\s*(.+?\?)", text, flags=re.IGNORECASE | re.DOTALL)

    if question_match:
        question = question_match.group(1).strip()
    else:
        matches = list(re.finditer(r"[^?]*\?", text, flags=re.DOTALL))
        question = matches[0].group(0).strip() if matches else text.split("\n", 1)[0].strip().rstrip(".") + "?"

    hint = hint_match.group(1).strip() if hint_match else "Trace the relevant code path with the failing input before changing anything."
    hint = re.sub(r"\s+", " ", hint)
    question = re.sub(r"\s+", " ", question)

    return f"Hint: {hint}\nQuestion: {question}"


def _fallback_question(conversation: Conversation) -> str:
    """Safe questions used when the model violates the output contract."""
    stage = STAGES[min(conversation.stage, len(STAGES) - 1)]
    hints = {
        "clarify": "Focus on the expected result for the specific input that fails.",
        "predict": "Trace the first few statements using the failing input and note the values they create.",
        "trace": "Follow the relevant loop, condition, or function call one step at a time.",
        "diagnose": "Compare the value or behaviour you observed with what the problem requires.",
        "propose": "Think of a small change you could test without rewriting the whole solution.",
        "test": "Use the failing edge case and at least one nearby case to check your hypothesis.",
        "reflect": "Consider which programming concept caused the mismatch and how you would spot it next time.",
    }
    questions = {
        "clarify": "What result should this function produce for the failing input, according to the problem statement?",
        "predict": "What value does your function currently produce for that input, and which path through the code leads to it?",
        "trace": "When you trace the code with the failing input, which statement or iteration first behaves differently from your expectation?",
        "diagnose": "What assumption about the variable, condition, or loop could explain the difference you observed?",
        "propose": "What small change could you make yourself to test that hypothesis, and why should that test distinguish the two behaviours?",
        "test": "After applying your proposed change, which edge case would you test first and what result would confirm your reasoning?",
        "reflect": "What programming concept does this debugging process demonstrate, and how could you use it on a similar problem?",
    }
    return f"Hint: {hints[stage]}\nQuestion: {questions[stage]}"


def _fallback_conclusion(conversation: Conversation) -> str:
    return (
        "You have now worked through the required Socratic debugging steps. "
        "Your reasoning identified the relevant behaviour and gave you a basis "
        "for checking the implementation against the failing edge case. "
        "Before considering the problem complete, verify your own change against "
        "the edge cases from the problem statement."
    )


def _advance_stage(conversation: Conversation) -> None:
    if conversation.stage < len(STAGES) - 1:
        conversation.stage += 1


def generate_tutor_response(
    code: str,
    question: str,
    conversation_id: str | None = None,
    language: str = "python",
) -> tuple[str, str]:
    """Generate a Socratic question, then conclude after the minimum is met."""
    conversation_id, conversation = get_or_create_conversation(
        conversation_id=conversation_id,
        code=code,
        language=language,
    )

    add_message(conversation, "student", question)
    history = history_as_text(conversation)

    diagnostic_prompt = build_diagnostic_prompt(
        code=conversation.code,
        question=question,
        history=history,
        language=conversation.language,
    )
    diagnostic = ask_llm(diagnostic_prompt, temperature=0.15)
    conversation.diagnostic = diagnostic

    # Once five tutor questions have already been delivered, this turn is the
    # conclusion. It deliberately bypasses the question-generation pipeline.
    if conversation.question_count >= MIN_SOCRATIC_QUESTIONS:
        conclusion_prompt = build_conclusion_prompt(
            code=conversation.code,
            question=question,
            history=history,
            diagnostic=diagnostic,
            language=conversation.language,
        )
        response = ask_llm(conclusion_prompt, temperature=0.15).strip()
        if "?" in response or _contains_solution_leak(response):
            response = _fallback_conclusion(conversation)
        conversation.concluded = True
        add_message(conversation, "assistant", response)
        conversation.turns += 1
        return response, conversation_id

    question_number = conversation.question_count + 1
    stage = STAGES[min(conversation.stage, len(STAGES) - 1)]
    socratic_prompt = build_socratic_prompt(
        code=conversation.code,
        question=question,
        history=history,
        diagnostic=diagnostic,
        language=conversation.language,
        stage=stage,
        question_number=question_number,
    )
    response = _clean_question(ask_llm(socratic_prompt, temperature=0.25))

    invalid = (
        _contains_solution_leak(response)
        or _is_repetition_question(response, question)
        or response.count("?") != 1
        or "Hint:" not in response
        or "Question:" not in response
    )

    if invalid:
        retry_prompt = socratic_prompt + """

STRICT OUTPUT CONTRACT:
- Return exactly two lines/parts: one Hint and one Question.
- The Hint must guide the student without giving the fix.
- The Question must be new and specific to the student's code.
- Do NOT ask the student to repeat, restate, reformat, or paste the question.
- Do NOT repeat the student's question.
- Include exactly one question mark.
- No code blocks and no solution.
"""
        response = _clean_question(ask_llm(retry_prompt, temperature=0.1))
        invalid = (
            _contains_solution_leak(response)
            or _is_repetition_question(response, question)
            or response.count("?") != 1
            or "Hint:" not in response
        )

    if invalid:
        response = _fallback_question(conversation)

    add_message(conversation, "assistant", response)
    conversation.question_count += 1
    conversation.turns += 1
    _advance_stage(conversation)

    return response, conversation_id
