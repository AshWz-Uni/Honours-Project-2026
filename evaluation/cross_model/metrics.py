"""Automatic metrics for the cross-model comparison.

Two families, deliberately kept apart:

``<name>``        Model-independent checks written for this study. They look only
                  at the text of the reply (question marks, fences, length, ...),
                  so they treat all conditions identically. These are the
                  primary automatic measures.

``agent_<name>``  The existing agent's own detectors from
                  ``backend/agent/tutor_agent.py`` (solution-leak regexes etc.).
                  CAUTION: the agent's replies are *filtered by these same
                  detectors* before they are shown, so ``codellama_agent`` will
                  score ~0 on them by construction. Report them as a
                  descriptive extra for the other conditions, never as evidence
                  that the agent beats another model.

Automatic metrics are proxies. The manual blind rating (``blind_rating.py``) is
the evidence for pedagogical quality; these only catch format and rule breaks.
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from backend.agent import tutor_agent as ta  # read-only use of the existing detectors

# The controlled prompt asks for 5 questions, then a conclusion on the 6th reply
# (6 scripted student turns). See "WHEN TO CONCLUDE" in controlled_prompt.txt.
EXPECTED_CONCLUSION_TURN = 6
MAX_SENTENCES = 3          # STYLE rule: "1-3 sentences"
REPEAT_THRESHOLD = 0.65    # same Jaccard threshold as the existing runner

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_FENCE = re.compile(r"```")
_FENCED_BLOCK = re.compile(r"```.*?```", re.S)
_INLINE = re.compile(r"`([^`\n]+)`")
_LABEL = re.compile(r"\b(?:Hint|Question)\s*:", re.I)
_PYTHON_TERMS = re.compile(r"\bNone\b|\belif\b|\blen\(|\bdictionary\b")
_WORD = re.compile(r"[A-Za-z0-9_]+")
_SELF_ID = re.compile(r"\b(?:ChatGPT|OpenAI|GPT-?\d\w*|Claude|Anthropic|Code ?Llama|Llama|Meta AI)\b", re.I)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) > 2}


def _sentences(text: str) -> list[str]:
    without_blocks = _FENCED_BLOCK.sub(" CODE. ", text)
    return [s for s in _SENTENCE_SPLIT.split(without_blocks.strip()) if s.strip()]


def mentions_model_identity(text: str) -> bool:
    """True if a reply names its own vendor/model (would break blind rating)."""
    return bool(_SELF_ID.search(text))


def turn_metrics(
    reply: str,
    turn: int,
    problem: dict,
    student_texts: list[str],
    earlier_tutor_replies: list[str],
    finish_reason: str = "",
) -> dict:
    """Metrics for one tutor reply. ``student_texts`` are all student messages up to this turn."""
    language = problem["language"]
    n_q = reply.count("?")
    known_text = _squash(" ".join([problem["code"], problem["problem"], *student_texts]))

    inline_spans = [_squash(s) for s in _INLINE.findall(_FENCED_BLOCK.sub("", reply))]
    new_spans = [s for s in inline_spans if s and s not in known_text]

    tokens = _tokens(reply)
    repeated = False
    if n_q:
        for earlier in earlier_tutor_replies:
            if "?" not in earlier:
                continue
            other = _tokens(earlier)
            if tokens and other and len(tokens & other) / len(tokens | other) >= REPEAT_THRESHOLD:
                repeated = True
                break

    return {
        "turn": turn,
        "empty_reply": int(not reply.strip()),
        "truncated": int(finish_reason in ("length", "max_tokens")),
        "n_question_marks": n_q,
        "has_question": int(n_q >= 1),
        "exactly_one_question": int(n_q == 1),
        "word_count": len(reply.split()),
        "sentence_count": len(_sentences(reply)),
        "over_length": int(len(_sentences(reply)) > MAX_SENTENCES),
        "has_code_block": int(bool(_FENCE.search(reply))),
        "inline_code_new_spans": len(new_spans),  # test inputs are allowed: needs a manual look
        "label_leak": int(bool(_LABEL.search(reply))),
        "wrong_language_terms": int(language == "javascript" and bool(_PYTHON_TERMS.search(_INLINE.sub("", reply)))),
        "repeated_prior_question": int(repeated),
        "mentions_model_identity": int(mentions_model_identity(reply)),
        # ---- agent-tuned detectors (see module docstring) ----
        "agent_solution_leak": int(ta._contains_solution_leak(reply, language)),
        "agent_new_code": int(ta._introduces_new_code(reply, problem["code"], language)),
        "agent_reasked_diagnosis": int(turn >= 2 and ta._re_asks_diagnosis(reply)),
    }


_SUM_COLUMNS = (
    "empty_reply", "truncated", "over_length", "has_code_block", "label_leak",
    "wrong_language_terms", "repeated_prior_question", "mentions_model_identity",
    "inline_code_new_spans", "agent_solution_leak", "agent_new_code", "agent_reasked_diagnosis",
)


def conversation_metrics(record: dict) -> dict:
    """Per-turn metrics for a whole transcript record, plus conversation-level aggregates."""
    problem = {
        "code": record["code"], "problem": record["problem_text"], "language": record["language"],
    }
    student_texts: list[str] = []
    tutor_replies: list[str] = []
    per_turn = []
    for t in record["turns"]:
        student_texts.append(t["student"])
        per_turn.append(turn_metrics(
            t["tutor"], t["turn"], problem, list(student_texts), list(tutor_replies), t.get("finish_reason", ""),
        ))
        tutor_replies.append(t["tutor"])

    first_no_q = next((m["turn"] for m in per_turn if not m["has_question"] and not m["empty_reply"]), None)
    question_turns = [m for m in per_turn if m["has_question"]]

    agg = {
        "n_turns": len(per_turn),
        "concluded_on_turn": first_no_q if first_no_q is not None else "",
        "premature_conclusion": int(first_no_q is not None and first_no_q < EXPECTED_CONCLUSION_TURN),
        "concluded_on_expected_turn": int(first_no_q == EXPECTED_CONCLUSION_TURN),
        "never_concluded": int(first_no_q is None),
        "multi_question_turns": sum(m["n_question_marks"] > 1 for m in per_turn),
        "exactly_one_question_rate": round(mean(m["exactly_one_question"] for m in question_turns), 3) if question_turns else "",
        "mean_words_per_reply": round(mean(m["word_count"] for m in per_turn), 1) if per_turn else "",
        "total_output_tokens": sum((t.get("output_tokens") or 0) for t in record["turns"]),
        "total_latency_s": round(sum((t.get("latency_s") or 0) for t in record["turns"]), 2),
    }
    for col in _SUM_COLUMNS:
        agg[col + "_turns" if not col.startswith("inline") else col] = sum(m[col] for m in per_turn)
    return {"per_turn": per_turn, "aggregate": agg}


def summarise(rows: list[dict], group_keys: tuple[str, ...] = ("condition",)) -> list[dict]:
    """Mean of every numeric column of ``rows`` per group, plus the group size."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in group_keys)].append(row)

    out = []
    for key, members in sorted(groups.items()):
        summary = dict(zip(group_keys, key))
        summary["n_conversations"] = len(members)
        for col in members[0]:
            if col in group_keys or col in ("run_id", "problem_id", "repeat", "problem_name", "language", "condition", "model"):
                continue
            values = [r[col] for r in members if isinstance(r.get(col), (int, float)) and not isinstance(r.get(col), bool)]
            if values:
                summary["mean_" + col] = round(mean(values), 3)
        out.append(summary)
    return out
