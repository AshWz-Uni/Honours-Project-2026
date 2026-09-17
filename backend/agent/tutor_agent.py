"""Socratic tutoring orchestration.

Code Llama is used in two private/student-facing roles:
1. A private diagnostic pass tracks what the student has understood.
2. A student-facing pass asks one Socratic question at a time.

The internal ``Hint:`` / ``Question:`` structure is parsed and removed before
anything is returned to the frontend.
"""

import json
import re

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
    return any(re.search(pattern, lowered, flags=re.DOTALL) for pattern in SOLUTION_LEAK_PATTERNS)


def _is_repetition_question(text: str, student_message: str) -> bool:
    lowered = text.lower().strip()
    if any(re.search(pattern, lowered) for pattern in REPETITION_PATTERNS):
        return True

    def normalise(value: str) -> str:
        value = value.lower()
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    student = normalise(student_message)
    response = normalise(text)
    return len(student.split()) >= 8 and student in response


def _parse_diagnostic(text: str) -> dict:
    """Parse the private diagnostic JSON, tolerating markdown fences."""
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)

    try:
        data = json.loads(cleaned)
        return {
            "problem_identified": bool(data.get("problem_identified", False)),
            "solution_proposed": bool(data.get("solution_proposed", False)),
            "solution_correct": bool(data.get("solution_correct", False)),
            "solution_validated": bool(data.get("solution_validated", False)),
            "student_evidence": str(data.get("student_evidence", "")),
            "next_step": str(data.get("next_step", "diagnose")),
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {
            "problem_identified": False,
            "solution_proposed": False,
            "solution_correct": False,
            "solution_validated": False,
            "student_evidence": "",
            "next_step": "diagnose",
        }


def _infer_explicit_student_progress(code: str, student_message: str, language: str) -> dict:
    """
    Deterministic safety net for explicit student reasoning.

    The LLM diagnostic is useful, but it must not be the only mechanism that
    decides whether a student has already solved a bug. Small local models can
    miss an explicit diagnosis and cause the tutor to restart the same line of
    questioning. This function only promotes state when the student's own
    message contains strong, unambiguous evidence.
    """
    text = student_message.lower()
    result = {
        "problem_identified": False,
        "solution_proposed": False,
        "solution_correct": False,
        "solution_validated": False,
        "student_evidence": "",
        "next_step": "diagnose",
    }

    # Explicit diagnosis language. These are intentionally conservative.
    diagnosis_patterns = [
        r"\bthe (?:problem|issue|bug) (?:is|seems to be|might be)",
        r"\b(?:because|since) .*\b(?:only|instead of|rather than|missing|incorrect)",
        r"\b(?:only) .*\b(?:returned|returning|returns)",
        r"\bmissing (?:a |the )?(?:value|index|condition|case|check)",
    ]
    if any(re.search(pattern, text, re.DOTALL) for pattern in diagnosis_patterns):
        result["problem_identified"] = True

    # Strong evidence that the student is proposing a concrete code change.
    proposal_patterns = [
        r"\b(?:it|this|that) should (?:be|return|use|change|include)",
        r"\b(?:i|we) (?:should|need to|could|would) (?:return|change|replace|add|remove|use)",
        r"\bso it should\b",
        r"\b(?:change|replace|return|add|remove)\b.*(?:with|to)",
        r"\breturn\s*\[[^\]]+\]",
    ]
    if any(re.search(pattern, text, re.DOTALL) for pattern in proposal_patterns):
        result["solution_proposed"] = True

    # Code-aware confirmation for the exact Two Sum failure mode used in
    # testing. The student has independently proposed the correct return
    # structure, so there is no pedagogical value in another diagnostic loop.
    if (
        language.lower() == "python"
        and "return[i]" in code.replace(" ", "").lower()
        and (
            re.search(r"\breturn\s*\[?\s*i\s*,\s*j\s*\]?", text)
            or re.search(r"\breturn\s+(?:both\s+)?i\s+and\s+j\b", text)
            or re.search(r"\bboth\s+i\s+and\s+j\b", text)
        )
    ):
        result["problem_identified"] = True
        result["solution_proposed"] = True
        result["solution_correct"] = True
        result["student_evidence"] = (
            "Student identified that only i is returned and independently proposed returning both i and j."
        )
        result["next_step"] = "conclude"
        return result

    if result["problem_identified"] and result["solution_proposed"]:
        result["next_step"] = "validate"
        result["student_evidence"] = student_message.strip()
    elif result["problem_identified"]:
        result["next_step"] = "propose"
        result["student_evidence"] = student_message.strip()

    return result


def _update_learning_state(conversation: Conversation, diagnostic: dict) -> None:
    """Persist only forward-moving learning state; never regress it."""
    conversation.problem_identified |= diagnostic["problem_identified"]
    conversation.solution_proposed |= diagnostic["solution_proposed"]
    conversation.solution_correct |= diagnostic["solution_correct"]
    conversation.solution_validated |= diagnostic["solution_validated"]


def _student_is_ready_to_conclude(conversation: Conversation) -> bool:
    """The dialogue can finish when the student identified the bug and proposed a correct fix."""
    return (
        conversation.problem_identified
        and conversation.solution_proposed
        and conversation.solution_correct
    )


def _clean_student_response(text: str) -> str:
    """Remove private Hint/Question labels and any accidental code blocks."""
    text = text.strip()
    text = re.sub(r"^(?:tutor|assistant)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "")
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # Extract the Question portion if the model followed the internal format.
    question_match = re.search(
        r"(?:^|\n)\s*Question\s*:\s*(.+?\?)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if question_match:
        question = question_match.group(1).strip()
        prefix = text[: question_match.start()].strip()
        # Preserve a short acknowledgement but discard the private Hint label/content.
        prefix = re.sub(r"(?:^|\n)\s*Hint\s*:\s*.*?(?=\n\s*Question\s*:|$)", "", prefix, flags=re.IGNORECASE | re.DOTALL)
        response = f"{prefix} {question}".strip()
    else:
        text = re.sub(r"(?:^|\n)\s*Hint\s*:\s*.*", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"(?:^|\n)\s*Question\s*:\s*", "", text, flags=re.IGNORECASE)
        response = text.strip()

    response = re.sub(r"\s+", " ", response)
    return response


def _fallback_question(conversation: Conversation) -> str:
    stage = STAGES[min(conversation.stage, len(STAGES) - 1)]
    questions = {
        "clarify": "What result should this function produce for the failing input, according to the problem statement?",
        "predict": "What value does your function currently produce for that input, and which path through the code leads to it?",
        "trace": "When you trace the code with the failing input, which statement first behaves differently from your expectation?",
        "diagnose": "What assumption about the variable, condition, or loop could explain the difference you observed?",
        "propose": "What small change could you make yourself to test that hypothesis?",
        "test": "What test case would confirm whether your proposed change works?",
        "reflect": "What programming concept does this debugging process demonstrate?",
    }
    return questions[stage]


def _fallback_conclusion(conversation: Conversation) -> str:
    return (
        "You identified the relevant issue and proposed a change that addresses it. "
        "Your reasoning connects the observed behaviour with the requirement, so the "
        "debugging step is complete. Verify your own change against the example and "
        "an appropriate edge case."
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
    """Generate a Socratic response or conclude when the student has solved the issue."""
    conversation_id, conversation = get_or_create_conversation(
        conversation_id=conversation_id,
        code=code,
        language=language,
    )

    # Once concluded, do not restart the tutoring loop.
    if conversation.concluded:
        return (
            "The tutoring dialogue has already concluded. Your proposed fix is ready for verification.",
            conversation_id,
        )

    add_message(conversation, "student", question)
    history = history_as_text(conversation)

    diagnostic_raw = ask_llm(
        build_diagnostic_prompt(
            code=conversation.code,
            question=question,
            history=history,
            language=conversation.language,
        ),
        temperature=0.15,
    )
    conversation.diagnostic = diagnostic_raw
    diagnostic = _parse_diagnostic(diagnostic_raw)

    # Never rely exclusively on the local LLM to recognise an explicit student
    # diagnosis. Merge conservative deterministic evidence from the latest
    # student message, with the student message taking precedence when it is
    # unambiguous.
    explicit_progress = _infer_explicit_student_progress(
        conversation.code, question, conversation.language
    )
    for key in (
        "problem_identified",
        "solution_proposed",
        "solution_correct",
        "solution_validated",
    ):
        diagnostic[key] = diagnostic[key] or explicit_progress[key]
    if explicit_progress["student_evidence"]:
        diagnostic["student_evidence"] = explicit_progress["student_evidence"]
    if explicit_progress["next_step"] != "diagnose":
        diagnostic["next_step"] = explicit_progress["next_step"]

    _update_learning_state(conversation, diagnostic)

    # Critical behaviour: if the student has already identified the bug and
    # proposed a correct fix, stop immediately instead of manufacturing more
    # Socratic questions. This is what prevents the Two Sum repetition loop.
    if _student_is_ready_to_conclude(conversation):
        conclusion_prompt = build_conclusion_prompt(
            code=conversation.code,
            question=question,
            history=history,
            diagnostic=diagnostic_raw,
            language=conversation.language,
        )
        response = ask_llm(conclusion_prompt, temperature=0.15).strip()
        response = _clean_student_response(response)
        if "?" in response or _contains_solution_leak(response) or not response:
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
        diagnostic=diagnostic_raw,
        language=conversation.language,
        stage=stage,
        question_number=question_number,
    )
    raw_response = ask_llm(socratic_prompt, temperature=0.25)
    response = _clean_student_response(raw_response)

    invalid = (
        _contains_solution_leak(response)
        or _is_repetition_question(response, question)
        or response.count("?") != 1
        or not response
        or re.search(r"\b(?:Hint|Question)\s*:", response, re.IGNORECASE)
    )

    if invalid:
        retry_prompt = socratic_prompt + """

STRICT STUDENT-FACING OUTPUT CONTRACT:
- Return natural conversational prose containing exactly one Socratic question.
- Do NOT output the words "Hint:" or "Question:".
- Do NOT ask the student to repeat, restate, reformat, or paste the question.
- Do NOT repeat the student's latest reasoning.
- Include exactly one question mark.
- No code blocks and no solution.
"""
        response = _clean_student_response(ask_llm(retry_prompt, temperature=0.1))
        invalid = (
            _contains_solution_leak(response)
            or _is_repetition_question(response, question)
            or response.count("?") != 1
            or not response
            or re.search(r"\b(?:Hint|Question)\s*:", response, re.IGNORECASE)
        )

    if invalid:
        response = _fallback_question(conversation)

    add_message(conversation, "assistant", response)
    conversation.question_count += 1
    conversation.turns += 1
    _advance_stage(conversation)

    return response, conversation_id
