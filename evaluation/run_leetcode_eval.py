"""Run the 10-problem LeetCode test set through the Socratic tutor.

Usage (from the project root, with Ollama running and `ollama pull codellama:7b`):

    python -m evaluation.run_leetcode_eval                 # all 10 problems, real Code Llama
    python -m evaluation.run_leetcode_eval --only 1,5,9    # a subset
    python -m evaluation.run_leetcode_eval --dry-run       # stub LLM: checks the plumbing only

A scripted student replies in a fixed order: diagnosis -> own fix -> validation
-> three reflection answers. The run stops when the tutor concludes.

Automatic columns are PROXIES computed by the same detectors the agent uses
(so they cannot catch what those detectors miss). The columns marked MANUAL are
left blank on purpose: judge them by reading transcripts.md.

Outputs (default results/leetcode_eval/): leetcode_results.csv, transcripts.md
"""

import argparse
import re
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agent import tutor_agent as ta  # noqa: E402
from backend.agent.conversation import get_conversation  # noqa: E402
from dataset.leetcode_eval import PROBLEMS  # noqa: E402

REPEAT_THRESHOLD = 0.65
POST_DIAGNOSIS_STAGES = {"propose", "test", "validate", "consolidate"}


def scripted_turns(problem: dict) -> list[tuple[str, str]]:
    turns = [
        ("diagnosis", problem["first_response"]),
        ("fix", problem["fix"]),
        ("validation", problem["validation"]),
    ]
    turns += [("reflection", text) for text in problem["reflections"]]
    return turns


# --------------------------------------------------------------------------- #
# Dry-run stub: exercises the pipeline without a model. NOT a result.
# --------------------------------------------------------------------------- #
_STUB_QUESTIONS = [
    "Which input would you run first to see the behaviour you described?",
    "What does the code produce for a small example, step by step?",
    "How could you test that idea on the example from the problem statement?",
    "Why does the earlier failing case now behave the way you expect?",
    "Which unusual input would you try next, and what should come back?",
    "Could anything that already worked be affected by that adjustment?",
    "What will you look for first when you meet a similar issue again?",
    "Where in the code does the observed value first diverge from the expected one?",
]


def install_stub_llm():
    state = {"role": "diagnosis", "calls": 0}

    def stub(prompt, temperature=None, json_mode=False):
        role = state["role"]
        if "private diagnostic component" in prompt.lower():
            flags = {
                "diagnosis": (True, False, False, False),
                "fix": (True, True, True, False),
                "validation": (True, True, True, True),
                "reflection": (True, True, True, True),
            }[role]
            keys = ("problem_identified", "solution_proposed", "solution_correct", "solution_validated")
            body = ", ".join(f'"{k}": {str(v).lower()}' for k, v in zip(keys, flags))
            return "{" + body + ', "student_evidence": "stub", "next_step": "diagnose"}'
        if "concluding a socratic" in prompt.lower():
            return "You found the cause, proposed a change yourself and checked it. Run it once more on an edge case."
        state["calls"] += 1
        return _STUB_QUESTIONS[state["calls"] % len(_STUB_QUESTIONS)]

    ta.ask_llm = stub
    return state


# --------------------------------------------------------------------------- #

def _fallback_texts() -> set[str]:
    texts = {t for group in ta._FALLBACK_QUESTIONS.values() for t in group}
    texts |= set(ta._CONSOLIDATION_FALLBACKS)
    texts.add(ta._fallback_conclusion())
    return texts


def run_problem(problem: dict, stub_state=None) -> dict:
    conversation_id = None
    transcript = []
    stage_after_first = ""
    concluded_turn = None

    for turn, (role, student_text) in enumerate(scripted_turns(problem), start=1):
        if stub_state is not None:
            stub_state["role"] = role
        reply, conversation_id = ta.generate_tutor_response(
            code=problem["code"],
            question=student_text,
            conversation_id=conversation_id,
            problem=problem["problem"],
        )
        conv = get_conversation(conversation_id)
        transcript.append((role, student_text, reply, conv.stage_name))
        if turn == 1:
            stage_after_first = conv.stage_name
        if conv.concluded:
            concluded_turn = turn
            break

    conv = get_conversation(conversation_id)
    tutor_msgs = [m.content for m in conv.messages if m.role == "assistant"]
    questions = [m for m in tutor_msgs if "?" in m]
    fallbacks = _fallback_texts()

    repeated = any(
        len(ta._tokens(a) & ta._tokens(b)) / max(1, len(ta._tokens(a) | ta._tokens(b))) >= REPEAT_THRESHOLD
        for i, a in enumerate(questions)
        for b in questions[i + 1 :]
    )

    return {
        "id": problem["id"],
        "problem": problem["name"],
        "bug": problem["bug"],
        "tutor_questions": conv.question_count,
        "auto_repeated_question": repeated,
        "auto_solution_leak_flags": sum(
            ta._contains_solution_leak(m) or ta._introduces_new_code(m, problem["code"]) for m in tutor_msgs
        ),
        "auto_reasked_diagnosis": sum(ta._re_asks_diagnosis(m) for m in tutor_msgs[1:]),
        "auto_stage_after_first_reply": stage_after_first,
        "auto_left_diagnosis_after_first_reply": stage_after_first in POST_DIAGNOSIS_STAGES,
        "auto_markers_visible": any(
            re.search(r"\b(?:Hint|Question)\s*:", m, re.I) for m in tutor_msgs
        ),
        "auto_off_topic_recursion": any(ta._off_topic_recursion(m, conv, "") for m in tutor_msgs),
        "auto_fallback_replies_used": sum(m in fallbacks for m in tutor_msgs),
        "concluded": conv.concluded,
        "concluded_on_turn": concluded_turn or "",
        "state_problem_identified": conv.problem_identified,
        "state_solution_proposed": conv.solution_proposed,
        "state_solution_correct": conv.solution_correct,
        "state_solution_validated": conv.solution_validated,
        "MANUAL_diagnosis_recognised": "",
        "MANUAL_meaningful_followups": "",
        "MANUAL_appropriate_conclusion": "",
        "MANUAL_notes": "",
        "_transcript": transcript,
        "_code": problem["code"],
    }


def write_outputs(rows: list[dict], out_dir: Path, dry_run: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = [k for k in rows[0] if not k.startswith("_")]

    with (out_dir / "leetcode_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# Transcripts" + ("  (DRY RUN — stub LLM, not real results)" if dry_run else ""), ""]
    for row in rows:
        lines += [f"## {row['id']}. {row['problem']}", "", f"Ground-truth bug: {row['bug']}", "", "```python", row["_code"], "```", ""]
        for role, student, tutor, stage in row["_transcript"]:
            lines += [f"**Student ({role}):** {student}", "", f"**Tutor [{stage}]:** {tutor}", ""]
    (out_dir / "transcripts.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated problem ids, e.g. 1,5,9")
    parser.add_argument("--out", default=str(ROOT / "results" / "leetcode_eval"))
    parser.add_argument("--dry-run", action="store_true", help="use a stub LLM (plumbing check only)")
    args = parser.parse_args()

    selected = {int(x) for x in args.only.split(",")} if args.only else None
    problems = [p for p in PROBLEMS if selected is None or p["id"] in selected]

    stub_state = install_stub_llm() if args.dry_run else None
    rows = []
    for problem in problems:
        print(f"Running {problem['id']:>2}. {problem['name']} ...", flush=True)
        try:
            rows.append(run_problem(problem, stub_state))
        except Exception as exc:  # e.g. Ollama not running
            sys.exit(f"\nFailed on problem {problem['id']}: {exc}\nIs Ollama running with the model in config/llm_config.json?")

    write_outputs(rows, Path(args.out), args.dry_run)
    print(f"\nWrote {len(rows)} rows to {args.out}")
    for r in rows:
        print(f"  {r['id']:>2} {r['problem']:<30} Qs={r['tutor_questions']} concluded={r['concluded']} "
              f"leak_flags={r['auto_solution_leak_flags']} fallbacks={r['auto_fallback_replies_used']}")


if __name__ == "__main__":
    main()
