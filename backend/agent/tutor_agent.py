"""Socratic tutoring orchestration.

Code Llama is used in two roles:
1. A private diagnostic pass records what the student has demonstrated.
2. A student-facing pass asks one Socratic question at a time.

The tutoring *stage* is derived from the learning state, not from a turn
counter, so the tutor never restarts diagnosis once the student has diagnosed
the bug:

    not identified   -> clarify / predict / trace / diagnose
    identified       -> propose   (acknowledge, then confirm or ask for a change)
    proposed, wrong  -> test      (student traces their own change)
    proposed, right  -> validate  (student tests it on a concrete input)
    validated        -> consolidate (why it works, edge cases, side effects)
                        ... then conclude once MIN_SOCRATIC_QUESTIONS is reached.

Reaching the question minimum never forces a conclusion: if the student has not
identified and validated a fix, questioning simply continues.

Every student-facing reply passes deterministic guards (solution leaks, new
code, repeated questions, re-asking a diagnosis, off-topic recursion, internal
Hint/Question markers) before it is returned.

Python and JavaScript are both supported. The language is chosen by the caller
or detected from the code (see ``backend.agent.language``); the state machine,
stages and guards are shared, and only the language-specific parts (prompt
note, code fence, new-code and recursion detection, extra leak patterns) differ.
"""

import json
import re

from backend.agent.conversation import (
    Conversation,
    add_message,
    get_or_create_conversation,
    history_as_text,
)
from backend.agent.language import (
    JAVASCRIPT,
    PYTHON,
    code_uses_recursion,
    normalise_language,
)
from backend.agent.prompts import (
    CONSOLIDATION_FOCI,
    build_conclusion_prompt,
    build_diagnostic_prompt,
    build_socratic_prompt,
)
from backend.services.llm_service import ask_llm


DIAGNOSIS_STAGES = ("clarify", "predict", "trace", "diagnose")
STAGES = DIAGNOSIS_STAGES + ("propose", "test", "validate", "consolidate", "conclude")

# The dialogue only concludes once the student has identified the bug, proposed a correct fix and validated it AND at least this many questions were asked.
# Set to 0 to conclude as soon as the fix is validated.
MIN_SOCRATIC_QUESTIONS = 5

# Safety valve against endless dialogues (e.g. a diagnostic model that never marks a correct fix as correct). Wraps up without claiming the fix is right.
HARD_QUESTION_LIMIT = 15

# --------------------------------------------------------------------------- #
# Output guards
# --------------------------------------------------------------------------- #

_EDIT_VERBS = (
    r"change|replace|remove|add|use|move|swap|store|return|append|reorder|update|"
    r"initiali[sz]e|extend|insert|rename|switch|wrap|call|set"
)

SOLUTION_LEAK_PATTERNS = [
    r"\bthe (?:answer|solution|fix) is\b",
    rf"\byou (?:should|need to|must|have to|ought to) (?:{_EDIT_VERBS})\b",
    r"\byou (?:might|could|may|can) (?:want to |also )?"
    r"(?:change|replace|remove|add|use|move|swap|store|return|append|reorder|update|"
    r"initiali[sz]e|extend|insert)\b",
    r"\b(?:try|consider) (?:using|adding|changing|replacing|removing|moving|swapping|"
    r"storing|returning|appending|reordering|updating|initiali[sz]ing|extending|"
    r"inserting|saving|switching)\b",
    r"\b(?:use|using) (?:a|an|the) (?:dictionary|dict|hash ?map|hash ?table|hash ?set|set|"
    r"stack|queue|deque|temporary variable|temp variable|second stack|two stacks|"
    r"extra variable|sentinel)\b",
    r"\bchange (?:line|the line)(?! by line)\b",
    r"\breplace .* with\b",
    r"\bhere(?:'s| is) (?:the )?(?:correct|fixed|corrected|updated) (?:code|solution|version)\b",
    r"\b(?:a|the) (?:fix|solution) (?:is|would be|could be) to\b",
    r"```python\s*[^`]+```",
    r"```(?:javascript|js|jsx|typescript|ts)\s*[^`]+```",
]

# Extra leak phrasings for JavaScript (applied on top of the shared list).
JS_SOLUTION_LEAK_PATTERNS = [
    r"\b(?:use|using) (?:a|an|the) (?:map|hash ?map|new map|new set|second array|extra array|"
    r"temporary array|helper array|object as a)\b",
    r"\byou (?:should|need to|must|have to|ought to) (?:push|splice|slice|declare|assign|"
    r"destructure|spread|concat|swap|reverse|floor|parse)\b",
    r"\byou (?:might|could|may|can) (?:want to |also )?(?:push|splice|slice|declare|assign|"
    r"destructure|spread|concat|swap|reverse|floor)\b",
    r"\b(?:try|consider) (?:pushing|splicing|slicing|declaring|assigning|destructuring|spreading|"
    r"concatenating|swapping|reversing|flooring)\b",
    r"\b(?:use|using) (?:===|!==|strict equality|math\.(?:floor|max|min|trunc|round)|parseint|number\()",
]

# Stating the cause is only a leak while the student has not found it themselves.
NAMES_CAUSE_PATTERNS = [
    r"\bthe (?:bug|problem|issue|mistake|error) (?:is|lies|occurs)\b",
    r"\b(?:this|that|it) (?:happens|occurs|fails|is wrong|is incorrect) because\b",
]

REPETITION_PATTERNS = [
    r"\bcan you (?:please )?(?:repeat|restate|rephrase) (?:the )?(?:question|problem)\b",
    r"\b(?:please )?(?:repeat|restate|rephrase) (?:the )?(?:question|problem)\b",
    r"\bwhat (?:is|was) your question\b",
    r"\bcan you (?:tell|say) me (?:the )?question again\b",
    r"\bcan you (?:format|reformat) (?:the )?(?:question|problem)\b",
]

# Diagnosis-style questions. Forbidden once the student has diagnosed the bug.
REASK_DIAGNOSIS_PATTERNS = [
    r"\bwhat (?:do you think |might |could |would )?(?:is|are|be|'s|seems to be) "
    r"(?:causing|wrong|the (?:problem|issue|bug|cause|mistake))\b",
    r"\bwhy (?:are|do|does|is|might|would) (?:you|your|the|it|this)\b.{0,80}"
    r"\b(?:only|wrong|fail|fails|incorrect|not (?:work|working|match|return|returning))\b",
    r"\bcan you (?:identify|find|spot|explain why you)\b",
    r"\bwhich (?:line|statement|part) (?:is|might be|could be) (?:causing|wrong|responsible)\b",
    r"\bwhat (?:seems|appears) to be (?:wrong|the (?:problem|issue))\b",
]

_RECURSION_TERMS = re.compile(
    r"\brecurs\w*|\bcalls? itself\b|\bcall stack\b|\bstack overflow\b", re.IGNORECASE
)


def _contains_solution_leak(text: str, language: str | None = None) -> bool:
    lowered = text.lower()
    patterns = SOLUTION_LEAK_PATTERNS
    if normalise_language(language) == JAVASCRIPT:
        patterns = patterns + JS_SOLUTION_LEAK_PATTERNS
    return any(re.search(p, lowered, flags=re.DOTALL) for p in patterns)


def _names_the_cause(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered, flags=re.DOTALL) for p in NAMES_CAUSE_PATTERNS)


_NEW_CODE_KEYWORDS = {
    PYTHON: re.compile(
        r"\b(?:return|append|extend|while|elif|else|if|for|def|lambda|yield|raise|del)\b"
        r"|=>|\.\w+\("
    ),
    JAVASCRIPT: re.compile(
        r"\b(?:return|const|let|var|function|while|else|if|for|switch|case|throw|new|"
        r"await|async|yield|delete|typeof)\b"
        r"|=>|\.\w+\("
    ),
}
_ASSIGNMENT = re.compile(r"^[A-Za-z_$][\w$.\[\]]*\s*[-+*/%]?=(?!=)\s*(.+)$")


def _introduces_new_code(text: str, code: str, language: str | None = None) -> bool:
    """True if the reply puts a new code statement in backticks.

    Quoting the student's own code or a test input (``n = 15``) is allowed.
    Inventing statements or assignments (``current = current.next``) is not.
    """
    lang = normalise_language(language) or PYTHON
    keywords = _NEW_CODE_KEYWORDS[lang]
    squashed_code = re.sub(r"\s+", "", code)
    for span in re.findall(r"`([^`\n]+)`", text):
        stripped = span.strip()
        if re.sub(r"\s+", "", stripped) in squashed_code:
            continue
        if keywords.search(stripped):
            return True
        assignment = _ASSIGNMENT.match(stripped)
        if assignment and re.search(r"[A-Za-z_$]", assignment.group(1)):
            return True
    return False


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


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _repeats_previous_tutor_question(text: str, conversation: Conversation) -> bool:
    """Near-duplicate of a question the tutor already asked (Jaccard >= 0.65)."""
    new = _tokens(text)
    if not new:
        return False
    for message in conversation.messages:
        if message.role != "assistant" or "?" not in message.content:
            continue
        old = _tokens(message.content)
        if old and len(new & old) / len(new | old) >= 0.65:
            return True
    return False


def _re_asks_diagnosis(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered, flags=re.DOTALL) for p in REASK_DIAGNOSIS_PATTERNS)


def _code_uses_recursion(code: str, language: str | None = None) -> bool:
    """Does any function in the student's code (Python or JavaScript) call itself?"""
    return code_uses_recursion(code, language)


def _off_topic_recursion(text: str, conversation: Conversation, student_message: str) -> bool:
    """Reply talks about recursion although the code is not recursive."""
    if not _RECURSION_TERMS.search(text):
        return False
    if _RECURSION_TERMS.search(student_message) or _RECURSION_TERMS.search(conversation.problem):
        return False
    return not _code_uses_recursion(conversation.code, conversation.language)


# --------------------------------------------------------------------------- #
# Learning-state inference
# --------------------------------------------------------------------------- #

def _empty_diagnostic() -> dict:
    return {
        "problem_identified": False,
        "solution_proposed": False,
        "solution_correct": False,
        "solution_validated": False,
        "student_evidence": "",
        "next_step": "diagnose",
    }


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _parse_diagnostic(text: str) -> dict:
    """Parse the private diagnostic JSON, tolerating fences and stray prose."""
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)

    data = None
    for candidate in (cleaned, (re.search(r"\{.*\}", cleaned, re.DOTALL) or [None])[0]):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            break
        except (json.JSONDecodeError, TypeError):
            continue

    if not isinstance(data, dict):
        return _empty_diagnostic()

    return {
        "problem_identified": _as_bool(data.get("problem_identified", False)),
        "solution_proposed": _as_bool(data.get("solution_proposed", False)),
        "solution_correct": _as_bool(data.get("solution_correct", False)),
        "solution_validated": _as_bool(data.get("solution_validated", False)),
        "student_evidence": str(data.get("student_evidence", "")),
        "next_step": str(data.get("next_step", "diagnose")),
    }


# Strong uncertainty suppresses the heuristics (a hedge like "not sure, but I think..." does not).
_UNCERTAIN = re.compile(
    r"\b(?:no idea|no clue|dunno|completely lost|totally lost|confused|"
    r"(?:don'?t|do not) (?:know|understand))\b"
)

_CAUSE_PATTERNS = [
    r"\b(?:the )?(?:problem|issue|bug|mistake|error)\s+(?:is|might be|may be|could be|seems to be|must be)\b",
    r"\bcould (?:it|that|this) be (?:because|that|since)\b",
    r"\b(?:i think|i believe|maybe|perhaps|probably)\b.*\b(?:because|since|when|never|missing|only|"
    r"instead of|rather than|before|after|shifted|off by)\b",
    r"\b(?:i|we)\s+(?:never|forgot to|fail to|didn'?t|did not|only)\b",
    r"\b(?:i am|i'm)\s+(?:losing|missing|skipping|overwriting|never|only|not (?:storing|saving|"
    r"adding|updating|checking|handling))\b",
    r"\bmissing (?:a |an |the )?\w+",
    r"\b(?:earlier|first|previous) (?:condition|branch|check|case)s? (?:catch|catches|handle|handles|match|matches)\b",
    r"\b(?:treats?|handles?) .{0,60}(?:the same|incorrectly|wrongly)\b",
    r"\b(?:stops?|exits?|ends?) (?:when|before|too early)\b",
    r"\boff[- ]by[- ]one\b|\bshifted\b",
    r"\b(?:doesn'?t|does not|don'?t|do not) match\b",
]

_PROPOSAL_PATTERNS = [
    r"\bi (?:think |believe )?(?:need|have|ought|must|should)(?: to)? "
    r"(?:return|change|replace|add|remove|use|store|move|swap|check|update|save|handle|reorder|"
    r"initiali[sz]e|keep|extend|append|preserve|reverse|push|splice|concat|declare|assign)\b",
    r"\b(?:i|we)(?:'d| would| could| will)\s+(?:return|change|replace|add|remove|use|store|move|swap|"
    r"check|update|save|handle|reorder|initiali[sz]e|extend|append|keep|preserve|push|splice|concat|"
    r"declare|assign)\b",
    r"\b(?:it|this|that) should (?:be|return|use|check|store|include|handle)\b",
]

_TEST_VERBS = re.compile(r"\b(?:traced|tested|tried|ran|when i (?:trace|test|try|run)|if i (?:trace|test|try|run))\b")
_RESULT_VERBS = re.compile(r"\b(?:returns?|gives?|outputs?|produces?|prints?|logs?|gets?|now works?|matches?)\b")
_DEBUG_ONLY = re.compile(r"\b(?:print|log|debug|breakpoint)\b")
_QUESTION_START = re.compile(
    r"^(?:do|does|did|should|shall|can|could|would|is|are|am|what|why|how|which|where|when)\b"
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _infer_explicit_student_progress(code: str, student_message: str) -> dict:
    """Conservative, problem-agnostic safety net for explicit student reasoning.

    A small local model can miss a clear diagnosis. This only *promotes*
    problem_identified / solution_proposed / solution_validated on strong
    wording in the student's own message. It never decides that a fix is
    *correct* (that needs the problem context, so it stays with the model) and
    it contains no problem-specific logic.
    """
    text = " ".join(student_message.lower().split())
    result = _empty_diagnostic()

    if len(text.split()) < 6 or _UNCERTAIN.search(text):
        return result

    if any(re.search(p, text, re.DOTALL) for p in _CAUSE_PATTERNS):
        result["problem_identified"] = True

    for sentence in _sentences(text):
        if _QUESTION_START.match(sentence) or _DEBUG_ONLY.search(sentence):
            continue
        if any(re.search(p, sentence) for p in _PROPOSAL_PATTERNS):
            result["solution_proposed"] = True
            break

    if _TEST_VERBS.search(text) and _RESULT_VERBS.search(text) and re.search(r"[\d\[\]]", text):
        result["solution_validated"] = True

    if result["solution_validated"]:
        result["next_step"] = "validate"
    elif result["solution_proposed"]:
        result["next_step"] = "validate"
    elif result["problem_identified"]:
        result["next_step"] = "propose"
    if result["problem_identified"] or result["solution_proposed"]:
        result["student_evidence"] = student_message.strip()

    return result


def _merge_diagnostics(llm: dict, heuristic: dict) -> dict:
    merged = dict(llm)
    for key in ("problem_identified", "solution_proposed", "solution_validated"):
        merged[key] = llm[key] or heuristic[key]
    # Correctness needs the problem context: only the model may assert it, and only alongside an actual proposal.
    merged["solution_correct"] = llm["solution_correct"] and merged["solution_proposed"]
    if heuristic["student_evidence"] and not llm["student_evidence"]:
        merged["student_evidence"] = heuristic["student_evidence"]
    return merged


def _update_learning_state(conversation: Conversation, diagnostic: dict) -> None:
    """Update learning state. Diagnosis is sticky; a new proposal supersedes the old one."""
    conversation.problem_identified |= diagnostic["problem_identified"]

    if diagnostic["solution_proposed"]:
        conversation.solution_proposed = True
        conversation.solution_correct = diagnostic["solution_correct"]
        if diagnostic["solution_correct"]:
            conversation.problem_identified = True  # a correct fix implies understanding
        else:
            conversation.solution_validated = False  # earlier validation no longer applies
    elif diagnostic["solution_correct"] and conversation.solution_proposed:
        conversation.solution_correct = True

    # A validation only counts once there is a proposal to validate.
    if diagnostic["solution_validated"] and conversation.solution_proposed:
        conversation.solution_validated = True


def learning_state(conversation: Conversation) -> dict:
    return {
        "stage": conversation.stage_name,
        "language": conversation.language,
        "question_count": conversation.question_count,
        "problem_identified": conversation.problem_identified,
        "solution_proposed": conversation.solution_proposed,
        "solution_correct": conversation.solution_correct,
        "solution_validated": conversation.solution_validated,
        "concluded": conversation.concluded,
    }


def _select_stage(conversation: Conversation) -> str:
    if not conversation.problem_identified:
        index = min(conversation.diagnosis_turns, len(DIAGNOSIS_STAGES) - 1)
        return DIAGNOSIS_STAGES[index]
    if not conversation.solution_proposed:
        return "propose"
    if not conversation.solution_correct:
        return "test"
    if not conversation.solution_validated:
        return "validate"
    return "consolidate"


def _ready_to_conclude(conversation: Conversation) -> bool:
    return (
        conversation.problem_identified
        and conversation.solution_proposed
        and conversation.solution_correct
        and conversation.solution_validated
        and conversation.question_count >= MIN_SOCRATIC_QUESTIONS
    )


# --------------------------------------------------------------------------- #
# Response construction
# --------------------------------------------------------------------------- #

_META_NARRATION_PATTERNS = (
    r"\bAcknowledging (?:the )?(?:student(?:'s)?|user(?:'s)?)[^:]*:\s*",
    r"\bAcknowledgement\s*:\s*",
    r"\bAcknowledgment\s*:\s*",
    r"\bSocratic\s*:?\s*",
    r"\b(?:I|we) (?:would )?(?:reply|respond)\s*:?\s*",
    r"\b(?:This|That) question (?:is|was) (?:asking|designed|intended)[^.?!]*[.?!]\s*",
    r"\b(?:This|That) (?:response|reply) (?:is|was) [^.?!]*[.?!]\s*",
    r"\bThe purpose of (?:this|the) question[^.?!]*[.?!]\s*",
    r"\bBy asking this question[^.?!]*[.?!]\s*",
    r"\b(?:This|That) (?:helps|will help|is meant) to[^.?!]*[.?!]\s*",
)


def _clean_student_response(text: str) -> str:
    """Return only student-facing prose; strip model narration and private labels."""
    text = text.strip()
    text = re.sub(r"^(?:tutor|assistant)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "")
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # Remove private scaffolding and model-generated narration. Repeat because narration can occur both before and after the actual question.
    for _ in range(3):
        for pattern in _META_NARRATION_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

    question_match = re.search(
        r"(?:^|\n)\s*Question\s*:\s*(.+?\?)", text, flags=re.IGNORECASE | re.DOTALL
    )
    if question_match:
        question = question_match.group(1).strip()
        prefix = text[: question_match.start()]
        prefix = re.sub(r"\bHint\s*:.*", "", prefix, flags=re.IGNORECASE | re.DOTALL)
        response = f"{prefix.strip()} {question}".strip()
    else:
        text = re.sub(r"\bHint\s*:.*?(?=\n\s*\n|$)", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\bQuestion\s*:\s*", "", text, flags=re.IGNORECASE)
        response = text.strip()

    # If the model wrapped the actual question in quotation marks and then explained it, keep the student-facing acknowledgement and question only.
    if response.count("?") == 1:
        qpos = response.find("?")
        trailing = response[qpos + 1:].strip()
        if trailing and re.search(
            r"\b(?:this|that) (?:question|response|reply)|\bthe purpose of|\bby asking",
            trailing,
            re.IGNORECASE,
        ):
            response = response[: qpos + 1]

    # Remove leading/trailing quote characters left by model narration.
    response = response.strip().strip('\"“”')
    return re.sub(r"\s+", " ", response).strip()


_FALLBACK_QUESTIONS = {
    "clarify": [
        "What result should this function produce for the failing input, according to the problem statement?",
        "Which input are you running when you notice the wrong behaviour, and what did you expect to see?",
    ],
    "predict": [
        "What value does your function currently produce for that input, and which path through the code leads to it?",
        "Before running it, what do you predict the function returns for a small input like the one that fails?",
    ],
    "trace": [
        "When you trace the code with the failing input, which statement first behaves differently from your expectation?",
        "If you write down the variables after each loop iteration or call for that input, where do they first differ from what you expected?",
    ],
    "diagnose": [
        "What assumption about a variable, condition, or loop bound could explain the difference you observed?",
        "Which single line in your code would you look at first to explain that difference, and why?",
        "If that line behaved exactly as you intended, what would the output be, and why does it differ from what you see?",
    ],
    "propose": [
        "That is a useful observation. Which concrete input could you trace to confirm it, and what would you change if the trace agrees?",
        "Good diagnosis. What small change would you make yourself to address it?",
    ],
    "test": [
        "Apply your proposed change to one concrete input. What does the code produce, and does it match what the problem requires?",
        "Trace your proposed change on a small example line by line. Where, if anywhere, does it still differ from the expected result?",
    ],
    "validate": [
        "That sounds like a promising fix. Pick one small input and trace it through your change. What result do you get, and does it match the requirement?",
        "How could you test your change on an example from the problem statement to check it behaves as required?",
    ],
}

_CONSOLIDATION_FALLBACKS = (
    "In your own words, why does your change make the earlier failing case behave correctly?",
    "Which edge case (empty input, a single element, or an extreme value) would you test next, and what should your code return for it?",
    "Could your change affect any other part of the algorithm or any input that already worked?",
    "What will you check first the next time you see this kind of bug?",
)


def _fallback_question(conversation: Conversation, stage: str) -> str:
    if stage == "consolidate":
        return _CONSOLIDATION_FALLBACKS[conversation.consolidation_turns % len(_CONSOLIDATION_FALLBACKS)]

    asked = {m.content for m in conversation.messages if m.role == "assistant"}
    options = _FALLBACK_QUESTIONS[stage]
    for option in options:
        if option not in asked:
            return option
    return options[-1]


def _fallback_conclusion() -> str:
    return (
        "You identified the cause, proposed a change of your own, and checked it against a "
        "concrete case, so your reasoning holds together. Before you submit, run your change "
        "on the original failing example and one edge case to confirm it."
    )


def _wrap_up_message() -> str:
    return (
        "We have spent a lot of turns on this, so let's pause here. Keep your traces and the "
        "observations you have made so far, and bring them to your instructor or a tutor "
        "session so you can continue from where you got to."
    )


_REJECTION_NOTES = {
    "empty": "The reply was empty.",
    "markers": 'Do NOT output the words "Hint:" or "Question:".',
    "meta_narration": "Do NOT describe your reasoning, response-generation process, or why the question is useful. Speak directly to the student.",
    "question_count": "Include exactly one question mark and one question.",
    "leak": "Do NOT tell the student what to change, what to use, or how to fix it.",
    "names_cause": "Do NOT state the cause of the bug; let the student find it.",
    "new_code": "Do NOT write new code. Only quote code already in the student's program or a test input.",
    "echo": "Do NOT repeat the student's own message back or ask them to restate anything.",
    "repeat": "You already asked something very similar. Ask a different, more specific question.",
    "reask_diagnosis": "The student has ALREADY identified the problem. Do NOT ask them to find or explain it again; follow the stage guidance.",
    "off_topic": "Do NOT mention recursion: the student's code is not recursive.",
}


def _contains_meta_narration(text: str) -> bool:
    """Detect model narration that should never reach the student."""
    patterns = (
        r"\bAcknowledging (?:the )?(?:student|user)",
        r"\bAcknowledg(?:e|ing|ement|ment|ed)",
        r"\bI (?:would )?(?:reply|respond)",
        r"\b(?:this|that) question (?:is|was) (?:asking|designed|intended)",
        r"\b(?:this|that) (?:response|reply) (?:is|was)",
        r"\bthe purpose of (?:this|the) question",
        r"\bby asking this question",
        r"\b(?:this|that) (?:helps|will help|is meant to)",
        r"\b(?:analysis|reasoning)\s*:",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _response_problem(response: str, conversation: Conversation, student_message: str) -> str | None:
    """Return the reason a student-facing reply is unacceptable, or None."""
    if not response:
        return "empty"
    if re.search(r"\b(?:Hint|Question)\s*:", response, re.IGNORECASE):
        return "markers"
    if _contains_meta_narration(response):
        return "meta_narration"
    if response.count("?") != 1:
        return "question_count"
    if _contains_solution_leak(response, conversation.language):
        return "leak"
    if not conversation.problem_identified and _names_the_cause(response):
        return "names_cause"
    if _introduces_new_code(response, conversation.code, conversation.language):
        return "new_code"
    if _is_repetition_question(response, student_message):
        return "echo"
    if _repeats_previous_tutor_question(response, conversation):
        return "repeat"
    if conversation.problem_identified and _re_asks_diagnosis(response):
        return "reask_diagnosis"
    if _off_topic_recursion(response, conversation, student_message):
        return "off_topic"
    return None


def _conclusion_is_acceptable(response: str, conversation: Conversation, student_message: str) -> bool:
    return bool(
        response
        and "?" not in response
        and not _contains_solution_leak(response, conversation.language)
        and not _introduces_new_code(response, conversation.code, conversation.language)
        and not _off_topic_recursion(response, conversation, student_message)
        and not re.search(r"\b(?:Hint|Question)\s*:", response, re.IGNORECASE)
    )


def generate_tutor_response(
    code: str,
    question: str,
    conversation_id: str | None = None,
    problem: str | None = None,
    language: str | None = None,
) -> tuple[str, str]:
    """Generate the next Socratic reply, or conclude when the student has earned it.

    ``language`` is ``"python"``, ``"javascript"`` or ``None`` to auto-detect from the code.
    """
    conversation_id, conversation = get_or_create_conversation(
        conversation_id=conversation_id, code=code, problem=problem, language=language
    )

    if conversation.concluded:
        return (
            "The tutoring dialogue has already concluded. Start a new conversation to work on another problem.",
            conversation_id,
        )

    history = history_as_text(conversation)  # everything before this student message
    add_message(conversation, "student", question)

    if conversation.question_count >= HARD_QUESTION_LIMIT:
        response = _wrap_up_message()
        conversation.concluded = True
        conversation.stage_name = "conclude"
        add_message(conversation, "assistant", response)
        conversation.turns += 1
        return response, conversation_id

    # Private diagnostic pass (JSON-constrained), merged with conservative deterministic evidence from the student's own words.
    diagnostic_raw = ask_llm(
        build_diagnostic_prompt(
            code=conversation.code,
            question=question,
            history=history,
            problem=conversation.problem,
            language=conversation.language,
        ),
        temperature=0.15,
        json_mode=True,
    )
    conversation.diagnostic = diagnostic_raw
    diagnostic = _merge_diagnostics(
        _parse_diagnostic(diagnostic_raw),
        _infer_explicit_student_progress(conversation.code, question),
    )
    _update_learning_state(conversation, diagnostic)

    if _ready_to_conclude(conversation):
        response = _clean_student_response(
            ask_llm(
                build_conclusion_prompt(
                    code=conversation.code,
                    question=question,
                    history=history,
                    diagnostic=diagnostic_raw,
                    problem=conversation.problem,
                    language=conversation.language,
                ),
                temperature=0.15,
            )
        )
        if not _conclusion_is_acceptable(response, conversation, question):
            response = _fallback_conclusion()
        conversation.concluded = True
        conversation.stage_name = "conclude"
        add_message(conversation, "assistant", response)
        conversation.turns += 1
        return response, conversation_id

    stage = _select_stage(conversation)
    conversation.stage_name = stage
    focus = (
        CONSOLIDATION_FOCI[conversation.consolidation_turns % len(CONSOLIDATION_FOCI)]
        if stage == "consolidate"
        else ""
    )

    socratic_prompt = build_socratic_prompt(
        code=conversation.code,
        question=question,
        history=history,
        diagnostic=diagnostic_raw,
        stage=stage,
        question_number=conversation.question_count + 1,
        problem=conversation.problem,
        focus=focus,
        language=conversation.language,
    )
    response = _clean_student_response(ask_llm(socratic_prompt, temperature=0.25))
    reason = _response_problem(response, conversation, question)

    if reason:
        retry_prompt = (
            socratic_prompt
            + "\n\nYour previous reply was rejected. "
            + _REJECTION_NOTES[reason]
            + "\nReturn natural conversational prose with exactly one Socratic question "
            "(one question mark), no Hint:/Question: labels, no code blocks, no solution."
        )
        response = _clean_student_response(ask_llm(retry_prompt, temperature=0.1))
        reason = _response_problem(response, conversation, question)

    if reason:
        response = _fallback_question(conversation, stage)

    add_message(conversation, "assistant", response)
    conversation.question_count += 1
    conversation.turns += 1
    if stage in DIAGNOSIS_STAGES:
        conversation.diagnosis_turns += 1
    elif stage == "consolidate":
        conversation.consolidation_turns += 1

    return response, conversation_id
