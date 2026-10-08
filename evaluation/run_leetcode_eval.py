"""Run the controlled LeetCode experiment across the project agent and comparison LLMs.

The experiment uses the same 10 Python and 10 JavaScript problems and the same
scripted student dialogue for every provider. For each tutor response it records
wall-clock response time with ``time.perf_counter()``. Results include both a
per-problem summary and a per-turn response log.

Providers:
    codellama   Local project agent (Ollama + Code Llama)
    chatgpt     OpenAI Responses API
    claude      Anthropic Messages API

Examples:
    python -m evaluation.run_leetcode_eval --provider codellama
    python -m evaluation.run_leetcode_eval --provider all
    python -m evaluation.run_leetcode_eval --provider all --language python
    python -m evaluation.run_leetcode_eval --provider all --only 1,5,9
    python -m evaluation.run_leetcode_eval --provider codellama --dry-run

External-provider credentials/models are supplied through environment variables.
See README.md for the exact variables. No API keys are stored in this project.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agent import tutor_agent as ta  # noqa: E402
from backend.agent.conversation import get_conversation  # noqa: E402
from backend.agent.language import SUPPORTED_LANGUAGES, detect_language  # noqa: E402
from backend.agent.prompts import SYSTEM_PROMPT, STAGE_GUIDANCE  # noqa: E402
from backend.services.llm_service import MODEL as CODELLAMA_MODEL  # noqa: E402
from dataset.leetcode_eval import get_problems  # noqa: E402
from evaluation.llm_providers import ProviderError, build_provider  # noqa: E402

REPEAT_THRESHOLD = 0.65
POST_DIAGNOSIS_STAGES = {"propose", "test", "validate", "consolidate"}
EXTERNAL_PROVIDERS = ("chatgpt", "claude")


def scripted_turns(problem: dict) -> list[tuple[str, str]]:
    turns = [
        ("diagnosis", problem["first_response"]),
        ("fix", problem["fix"]),
        ("validation", problem["validation"]),
    ]
    turns += [("reflection", text) for text in problem["reflections"]]
    return turns


def _stage_for_external_turn(role: str) -> str:
    # The scripted dialogue deliberately moves through these stages. The
    # comparison models receive the same stage instruction as the project
    # agent, but without the project's private diagnostic component.
    return {
        "diagnosis": "propose",
        "fix": "validate",
        "validation": "consolidate",
        "reflection": "consolidate",
    }[role]


def build_external_prompt(
    problem: dict,
    role: str,
    student_text: str,
    history: list[tuple[str, str, str]],
) -> str:
    stage = _stage_for_external_turn(role)
    guidance = STAGE_GUIDANCE[stage].format(
        focus="ask one deeper reflection question about the student's reasoning"
    )
    transcript = []
    for old_role, old_student, old_tutor in history:
        transcript.append(f"Student: {old_student}")
        transcript.append(f"Tutor: {old_tutor}")
    previous = "\n".join(transcript) if transcript else "(no previous turns)"

    return f"""
{SYSTEM_PROMPT}

CURRENT TUTORING STAGE: {stage}
STAGE GUIDANCE: {guidance}

Problem statement:
{problem["problem"]}

Student code:
```{problem["language"]}
{problem["code"]}
```

Conversation history:
{previous}

Latest student message:
{student_text}

Reply directly to the student. Return natural conversational prose only:
one short acknowledgement at most, followed by exactly one Socratic question.
Do not provide corrected code, reveal the answer, or describe your reasoning.
""".strip()


# --------------------------------------------------------------------------- #
# Dry-run stub: exercises the pipeline without a model.
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


def _fallback_texts() -> set[str]:
    texts = {t for group in ta._FALLBACK_QUESTIONS.values() for t in group}
    texts |= set(ta._CONSOLIDATION_FALLBACKS)
    texts.add(ta._fallback_conclusion())
    return texts


def _quality_fields(tutor_msgs: list[str], conv, problem: dict, stage_after_first: str) -> dict:
    fallbacks = _fallback_texts()
    questions = [m for m in tutor_msgs if "?" in m]
    repeated = any(
        len(ta._tokens(a) & ta._tokens(b))
        / max(1, len(ta._tokens(a) | ta._tokens(b))) >= REPEAT_THRESHOLD
        for i, a in enumerate(questions)
        for b in questions[i + 1 :]
    )
    detected = detect_language(problem["code"])
    return {
        "tutor_questions": conv.question_count,
        "auto_repeated_question": repeated,
        "auto_detected_language": detected or "",
        "auto_language_detected_correctly": detected == problem["language"],
        "auto_solution_leak_flags": sum(
            ta._contains_solution_leak(m, problem["language"])
            or ta._introduces_new_code(m, problem["code"], problem["language"])
            for m in tutor_msgs
        ),
        "auto_reasked_diagnosis": sum(
            ta._re_asks_diagnosis(m) for m in tutor_msgs[1:]
        ),
        "auto_stage_after_first_reply": stage_after_first,
        "auto_left_diagnosis_after_first_reply": stage_after_first in POST_DIAGNOSIS_STAGES,
        "auto_markers_visible": any(
            re.search(r"\b(?:Hint|Question)\s*:", m, re.I) for m in tutor_msgs
        ),
        "auto_off_topic_recursion": any(
            ta._off_topic_recursion(m, conv, "") for m in tutor_msgs
        ),
        "auto_fallback_replies_used": sum(m in fallbacks for m in tutor_msgs),
    }


def run_codellama(problem: dict, stub_state=None) -> tuple[dict, list[dict]]:
    conversation_id = None
    transcript = []
    response_rows = []
    stage_after_first = ""
    concluded_turn = None

    for turn, (role, student_text) in enumerate(scripted_turns(problem), start=1):
        if stub_state is not None:
            stub_state["role"] = role

        started = time.perf_counter()
        reply, conversation_id = ta.generate_tutor_response(
            code=problem["code"],
            question=student_text,
            conversation_id=conversation_id,
            problem=problem["problem"],
            language=problem["language"],
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        conv = get_conversation(conversation_id)
        transcript.append((role, student_text, reply, conv.stage_name))
        response_rows.append(
            {
                "provider": "codellama",
                "model": CODELLAMA_MODEL,
                "language": problem["language"],
                "problem_id": problem["id"],
                "problem": problem["name"],
                "turn": turn,
                "student_role": role,
                "response_time_ms": round(elapsed_ms, 3),
                "response": reply,
                "stage": conv.stage_name,
            }
        )
        if turn == 1:
            stage_after_first = conv.stage_name
        if conv.concluded:
            concluded_turn = turn
            break

    conv = get_conversation(conversation_id)
    tutor_msgs = [m.content for m in conv.messages if m.role == "assistant"]
    row = {
        "provider": "codellama",
        "model": CODELLAMA_MODEL,
        "language": problem["language"],
        "id": problem["id"],
        "problem": problem["name"],
        "bug": problem["bug"],
        **_quality_fields(tutor_msgs, conv, problem, stage_after_first),
        "response_time_total_ms": round(sum(r["response_time_ms"] for r in response_rows), 3),
        "response_time_avg_ms": round(
            sum(r["response_time_ms"] for r in response_rows) / max(1, len(response_rows)), 3
        ),
        "response_time_min_ms": round(min(r["response_time_ms"] for r in response_rows), 3),
        "response_time_max_ms": round(max(r["response_time_ms"] for r in response_rows), 3),
        "response_count": len(response_rows),
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
        "_language": problem["language"],
    }
    return row, response_rows


def run_external(problem: dict, provider, provider_name: str) -> tuple[dict, list[dict]]:
    history: list[tuple[str, str, str]] = []
    transcript = []
    response_rows = []

    for turn, (role, student_text) in enumerate(scripted_turns(problem), start=1):
        prompt = build_external_prompt(problem, role, student_text, history)
        started = time.perf_counter()
        reply_obj = provider.reply(
            prompt,
            [{"role": "user", "content": student_text}],
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        reply = reply_obj.text

        stage = _stage_for_external_turn(role)
        transcript.append((role, student_text, reply, stage))
        history.append((role, student_text, reply))
        response_rows.append(
            {
                "provider": provider_name,
                "model": reply_obj.model,
                "language": problem["language"],
                "problem_id": problem["id"],
                "problem": problem["name"],
                "turn": turn,
                "student_role": role,
                "response_time_ms": round(elapsed_ms, 3),
                "response": reply,
                "stage": stage,
            }
        )

    times = [r["response_time_ms"] for r in response_rows]
    tutor_msgs = [r["response"] for r in response_rows]
    # External models do not expose the project's internal learning-state flags,
    # so quality checks are deliberately limited to observable response text.
    row = {
        "provider": provider_name,
        "model": response_rows[0]["model"] if response_rows else "",
        "language": problem["language"],
        "id": problem["id"],
        "problem": problem["name"],
        "bug": problem["bug"],
        "tutor_questions": sum("?" in m for m in tutor_msgs),
        "auto_repeated_question": any(
            len(ta._tokens(a) & ta._tokens(b))
            / max(1, len(ta._tokens(a) | ta._tokens(b))) >= REPEAT_THRESHOLD
            for i, a in enumerate(tutor_msgs)
            for b in tutor_msgs[i + 1 :]
        ),
        "auto_detected_language": detect_language(problem["code"]) or "",
        "auto_language_detected_correctly": detect_language(problem["code"]) == problem["language"],
        "auto_solution_leak_flags": sum(
            ta._contains_solution_leak(m, problem["language"])
            or ta._introduces_new_code(m, problem["code"], problem["language"])
            for m in tutor_msgs
        ),
        "auto_reasked_diagnosis": sum(
            ta._re_asks_diagnosis(m) for m in tutor_msgs[1:]
        ),
        "auto_stage_after_first_reply": "propose",
        "auto_left_diagnosis_after_first_reply": False,
        "auto_markers_visible": any(
            re.search(r"\b(?:Hint|Question)\s*:", m, re.I) for m in tutor_msgs
        ),
        "auto_off_topic_recursion": any(
            re.search(r"\brecurs\w*|\bcalls? itself\b|\bcall stack\b", m, re.I)
            and not re.search(r"\brecurs\w*|\bcalls? itself\b|\bcall stack\b", problem["code"], re.I)
            for m in tutor_msgs
        ),
        "auto_fallback_replies_used": 0,
        "response_time_total_ms": round(sum(times), 3),
        "response_time_avg_ms": round(sum(times) / max(1, len(times)), 3),
        "response_time_min_ms": round(min(times), 3),
        "response_time_max_ms": round(max(times), 3),
        "response_count": len(times),
        "concluded": "",
        "concluded_on_turn": "",
        "state_problem_identified": "",
        "state_solution_proposed": "",
        "state_solution_correct": "",
        "state_solution_validated": "",
        "MANUAL_diagnosis_recognised": "",
        "MANUAL_meaningful_followups": "",
        "MANUAL_appropriate_conclusion": "",
        "MANUAL_notes": "",
        "_transcript": transcript,
        "_code": problem["code"],
        "_language": problem["language"],
    }
    return row, response_rows


def write_outputs(rows: list[dict], response_rows: list[dict], out_dir: Path, dry_run: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = [k for k in rows[0] if not k.startswith("_")]
    with (out_dir / "leetcode_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    response_fields = [
        "provider", "model", "language", "problem_id", "problem", "turn",
        "student_role", "stage", "response_time_ms", "response",
    ]
    with (out_dir / "response_times.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=response_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(response_rows)

    lines = [
        "# Transcripts"
        + ("  (DRY RUN — stub LLM, not real results)" if dry_run else ""),
        "",
    ]
    for row in rows:
        lines += [
            f"## {row['id']}. {row['problem']} — {row['provider']}",
            "",
            f"Model: {row['model']}",
            f"Ground-truth bug: {row['bug']}",
            f"Total response time: {row['response_time_total_ms']} ms",
            f"Average response time: {row['response_time_avg_ms']} ms",
            "",
            f"```{row['_language']}",
            row["_code"],
            "```",
            "",
        ]
        for turn_index, (role, student, tutor, stage) in enumerate(row["_transcript"], start=1):
            turn_time = next(
                (
                    x["response_time_ms"]
                    for x in response_rows
                    if x["provider"] == row["provider"]
                    and x["problem_id"] == row["id"]
                    and x["turn"] == turn_index
                ),
                "",
            )
            lines += [
                f"**Student ({role}):** {student}",
                "",
                f"**Tutor [{stage}] — {turn_time} ms:** {tutor}",
                "",
            ]
    (out_dir / "transcripts.md").write_text("\n".join(lines), encoding="utf-8")


def write_combined_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [k for k in rows[0] if not k.startswith("_")]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_provider(provider_name: str, problems: list[dict], out_root: Path, dry_run: bool) -> list[dict]:
    rows = []
    response_rows = []

    if provider_name == "codellama":
        stub_state = install_stub_llm() if dry_run else None
        for problem in problems:
            print(f"Running {problem['id']:>2}. {problem['name']} ...", flush=True)
            row, turns = run_codellama(problem, stub_state)
            rows.append(row)
            response_rows.extend(turns)
        write_outputs(rows, response_rows, out_root / provider_name, dry_run)
        return rows

    if dry_run:
        # The stub is only for the project agent; external API calls must not be
        # represented as real LLM results.
        raise SystemExit("--dry-run is supported only with --provider codellama")

    provider = build_provider(provider_name)
    try:
        for problem in problems:
            provider.reset()
            print(f"Running {problem['id']:>2}. {problem['name']} ...", flush=True)
            row, turns = run_external(problem, provider, provider_name)
            rows.append(row)
            response_rows.extend(turns)
    finally:
        provider.close()

    write_outputs(rows, response_rows, out_root / provider_name, False)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--provider",
        choices=("codellama", "chatgpt", "claude", "all"),
        default="codellama",
        help="LLM to evaluate (default: codellama)",
    )
    parser.add_argument(
        "--language",
        choices=(*SUPPORTED_LANGUAGES, "both"),
        default="both",
        help="problem language set (default: both)",
    )
    parser.add_argument("--only", help="comma-separated problem ids, e.g. 1,5,9")
    parser.add_argument("--out", default=str(ROOT / "results" / "leetcode_eval"))
    parser.add_argument("--dry-run", action="store_true", help="use the local stub; plumbing check only")
    args = parser.parse_args()

    selected = {int(x) for x in args.only.split(",")} if args.only else None
    languages = SUPPORTED_LANGUAGES if args.language == "both" else (args.language,)
    providers = ("codellama",) + EXTERNAL_PROVIDERS if args.provider == "all" else (args.provider,)

    out_root = Path(args.out)
    all_rows: list[dict] = []

    for provider_name in providers:
        print(f"\n=== {provider_name} ===", flush=True)
        for language in languages:
            problems = [
                p for p in get_problems(language)
                if selected is None or p["id"] in selected
            ]
            print(f"=== {language} ({len(problems)} problems) ===", flush=True)
            try:
                rows = run_provider(provider_name, problems, out_root, args.dry_run)
            except ProviderError as exc:
                sys.exit(f"\n{provider_name} setup failed: {exc}")
            except Exception as exc:
                sys.exit(
                    f"\nFailed on {provider_name}/{language}: {exc}\n"
                    "Check the provider credentials, model name and network/API access."
                )
            all_rows.extend(rows)

    if all_rows:
        combined_name = "all_providers_results.csv" if len(providers) > 1 else "combined_results.csv"
        write_combined_csv(all_rows, out_root / combined_name)
        print(f"\nWrote combined results to {out_root / combined_name}")


if __name__ == "__main__":
    main()
