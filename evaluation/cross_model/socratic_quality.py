"""Rule-based assessment of the quality of the Socratic QUESTIONS a tutor asks.

This is an automatic proxy built from the project's own rubric (`blind_rating.py`: "meaningful_followups",
"code_grounded", "solution_leak") and from common Socratic-tutoring criteria. It reads the text of each reply
and does not call any model, so every condition (and every step of the study) is scored identically.
It cannot judge whether a question was pedagogically *wise* at that moment..

Scope: tutor replies on turns 1-5 that contain a "?" (the turns where a question is expected). Replies with
no "?" have no question to assess; they are counted and reported, not scored.

Five criteria per question (each 0/1; equal weights, chosen for transparency, not because they are equally important):
    reasoning_prompt  asks the student to reason (why / how / predict / trace / explain / which ...), not a bare yes-no
    code_grounded     refers to the student's code or a concrete input (backticked code, an identifier of the student's
                      code, or a literal such as 15 or [3, 3])
    non_leading       does not tell the student what to change and does not give the answer away (fix-giving phrases,
                      the agent's solution-leak detector, "have you considered using ...", "why not just ...")
    single_focus      exactly one question mark
    not_repeated      not a near-repeat of an earlier question in the same conversation (Jaccard >= 0.65)
    quality_score     number of criteria met (0-5)           high_quality = all five met

Also recorded: the cognitive type of the question (recall, predict, trace/test, explain, extend/reflect, propose) and
whether it responds to the student's latest message (>= 2 shared content words; descriptive only, not in the score).
"""

from __future__ import annotations

import re

from backend.agent import tutor_agent as ta
from evaluation.cross_model import analysis_utils as au
from evaluation.cross_model import metrics as mx

CRITERIA = ["reasoning_prompt", "code_grounded", "non_leading", "single_focus", "not_repeated"]
CRITERIA_LABELS = {
    "reasoning_prompt": "Asks for reasoning\n(not a yes/no)",
    "code_grounded": "Grounded in the\nstudent's code/input",
    "non_leading": "Does not lead or\ngive the fix",
    "single_focus": "Single focus\n(one '?')",
    "not_repeated": "Not a repeat of an\nearlier question",
}
TYPES = ["recall", "predict", "trace/test", "explain", "extend/reflect", "propose"]

_SENT = re.compile(r"(?<=[.!?])\s+")
_LABEL_LINE = re.compile(r"^\s*(?:Acknowledg\w+|Socratic question|Question|Hint)\s*:\s*", re.I | re.M)
_FENCED = re.compile(r"```.*?```", re.S)
_BACKTICK = re.compile(r"`[^`\n]+`")
_NUMBER = re.compile(r"(?<![A-Za-z_])\d+(?![A-Za-z_])|\[[^\]]*\]")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_WORD = re.compile(r"[a-z]{4,}")

_COMMON = {  # words that are identifiers in code but also everyday English / language keywords: not evidence of grounding
    "result", "return", "returns", "value", "values", "input", "output", "function", "code", "list", "array", "number", "numbers",
    "index", "item", "items", "element", "elements", "count", "true", "false", "none", "null", "else", "elif", "for", "while",
    "def", "class", "self", "let", "const", "var", "the", "and", "not", "len", "range", "print", "new", "this", "length", "next",
    "stack", "queue", "left", "right", "mid", "node", "root", "head", "current", "prev", "target", "sum", "max", "min", "test",
}
_STOP = {"that", "this", "with", "your", "what", "when", "which", "would", "could", "should", "have", "about", "there", "their",
         "then", "than", "them", "they", "will", "from", "into", "just", "also", "does", "make", "need", "think", "like", "only",
         "more", "some", "such", "been", "were", "where", "while", "because", "after", "before", "first", "again", "still", "here"}

_REASON = re.compile(
    r"\b(why|how|which|explain|predict|expect|trace|walk\s+(?:me\s+)?through|in\s+your\s+own\s+words|describe|"
    r"what\s+(?:would|will|do\s+you|does|did|should|happens?|value|result|general|small|lesson|input|change|part|makes?)|"
    r"what\s+(?:is|are)\s+(?:the|your)|where\s+(?:does|do|would)|when\s+(?:does|do|would))\b", re.I)
_YESNO_START = re.compile(r"^(?:is|are|do|does|did|will|would|can|could|should|have|has|was|were|shall)\b", re.I)
_LEADING = re.compile(
    r"\b(?:don'?t\s+you\s+think|wouldn'?t\s+it\s+be\s+better|shouldn'?t\s+you|why\s+not\s+(?:just\s+)?(?:use|add|change|try|return|set)|"
    r"have\s+you\s+considered\s+(?:using|adding|changing|returning)|what\s+if\s+you\s+(?:used|added|changed|returned|set)|"
    r"you\s+(?:might|could|should)\s+(?:want\s+to\s+)?(?:use|add|change|return|replace|try))\b", re.I)

_TYPE_RULES = [  # first match wins
    ("extend/reflect", re.compile(r"\b(edge\s+case|other\s+part|already\s+worked|affect|next\s+time|lesson|general|every\s+input|"
                                  r"any\s+other|side\s+effect|still\s+(?:work|hold)|break\s+(?:any|other))\b", re.I)),
    ("explain", re.compile(r"\b(why|explain|in\s+your\s+own\s+words|how\s+does|how\s+do\s+you\s+know|reason)\b", re.I)),
    ("predict", re.compile(r"\b(predict|expect|what\s+(?:would|should)\s+happen|how\s+would\s+(?:your|the)\s+\w+(?:\s+\w+)?\s+behave|what\s+do\s+you\s+think\s+(?:your\s+code\s+|the\s+code\s+|it\s+)?(?:actually\s+)?(?:returns?|outputs?|produces?|happens?)|"
                           r"what\s+(?:would|will|should|does)\s+(?:the\s+|your\s+)?(?:code|function|it|your\s+code|your\s+function)?\s*(?:actually\s+)?(?:return|produce|output|print|give))\b", re.I)),
    ("trace/test", re.compile(r"\b(trac(?:e|ing|ed)|walk\s+(?:me\s+)?through|step\s+by\s+step|line\s+by\s+line|test|run|apply|each\s+iteration|"
                              r"what\s+(?:values?|happens)|what\s+is\s+the\s+value|after\s+(?:the\s+)?(?:first|each|every)|what\s+do\s+[`\w, ]+\s+(?:hold|point\s+to)|which\s+(?:branch|line|statement))\b", re.I)),
    ("propose", re.compile(r"\b(change|modify|fix|update|adjust|way\s+to|how\s+(?:would|could|might)\s+you)\b", re.I)),
]


def _canned_set() -> set[str]:
    out = {s for opts in ta._FALLBACK_QUESTIONS.values() for s in opts}
    return out | set(ta._CONSOLIDATION_FALLBACKS)


_CANNED = None


def is_canned(reply: str) -> bool:
    """True if the reply is one of the agent's fixed fallback strings (not generated by the model)."""
    global _CANNED
    if _CANNED is None:
        _CANNED = _canned_set()
    return reply.strip() in _CANNED


def question_text(reply: str) -> str:
    """The question the tutor actually asks: the last sentence containing '?' (labels and code fences removed)."""
    body = _LABEL_LINE.sub("", _FENCED.sub(" ", reply))
    sents = [s.strip() for s in _SENT.split(" ".join(body.split())) if "?" in s]
    return sents[-1] if sents else ""


def _code_idents(code: str) -> set[str]:
    return {w.lower() for w in _IDENT.findall(code) if w.lower() not in _COMMON}


def _content(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def question_type(q: str) -> str:
    for name, rx in _TYPE_RULES:
        if rx.search(q):
            return name
    return "recall"


def score_question(reply: str, turn: int, code: str, language: str, student_latest: str, earlier_questions: list[str]) -> dict:
    """Score one reply. ``earlier_questions`` are the question texts of earlier replies in the same conversation."""
    q = question_text(reply)
    n_q = reply.count("?")
    if not q:
        return {"has_question": 0}
    plain = " ".join(_FENCED.sub(" ", reply).split())

    cue = bool(_REASON.search(q))
    reasoning = cue
    grounded = bool(_BACKTICK.search(q) or _NUMBER.search(q) or (_code_idents(code) & {w.lower() for w in _IDENT.findall(q)}))
    leading = bool(_LEADING.search(q) or au.tells_fix(plain) or ta._contains_solution_leak(reply, language))
    single = n_q == 1
    qt = mx._tokens(q)
    repeated = any(qt and (e := mx._tokens(x)) and len(qt & e) / len(qt | e) >= mx.REPEAT_THRESHOLD for x in earlier_questions)
    responsive = len(_content(student_latest) & _content(reply)) >= 2

    row = {"has_question": 1, "question": q, "question_type": question_type(q), "yes_no_start": int(bool(_YESNO_START.match(q)) and not cue),
           "reasoning_prompt": int(reasoning), "code_grounded": int(grounded), "non_leading": int(not leading),
           "single_focus": int(single), "not_repeated": int(not repeated), "responsive_to_student": int(responsive),
           "canned": int(is_canned(reply)), "turn": turn}
    row["quality_score"] = sum(row[c] for c in CRITERIA)
    row["high_quality"] = int(row["quality_score"] == len(CRITERIA))
    return row


def score_conversation(replies: list[str], students: list[str], code: str, language: str, first_turn: int = 1) -> list[dict]:
    """Score turns 1-5 of one conversation (turn 6 is the conclusion and is not a question turn)."""
    out, earlier = [], []
    for i, (reply, student) in enumerate(zip(replies, students)):
        turn = first_turn + i
        if turn >= mx.EXPECTED_CONCLUSION_TURN:
            break
        r = score_question(reply, turn, code, language, student, earlier)
        out.append({"turn": turn, **r} if "turn" not in r else r)
        if r.get("has_question"):
            earlier.append(r["question"])
    return out
