"""Run Code Llama locally and import ChatGPT/Claude web-app results under ONE controlled prompt.

See evaluation/cross_model/README.md for the experimental design. Quick reference
(run from the project root):

    # plumbing check, no model or API key needed (output is NOT a result)
    python -m evaluation.cross_model.run_cross_model_eval run --dry-run

    # run local Code Llama conditions only (needs Ollama running)
    python -m evaluation.cross_model.run_cross_model_eval run --repeats 3 --run-id main

    # resume an interrupted run (settings must match the original)
    python -m evaluation.cross_model.run_cross_model_eval run --repeats 3 --run-id main --resume

    # no API access? drive the ChatGPT / Claude web apps by hand instead
    python -m evaluation.cross_model.run_cross_model_eval export-manual --condition chatgpt
    python -m evaluation.cross_model.run_cross_model_eval import-manual --condition chatgpt \\
        --dir manual_pack/chatgpt --model "ChatGPT web, <model shown in UI>, <date>" --run-id manual

    # recompute metrics/summaries for an existing run
    python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/main

Automatic conditions (evaluation/cross_model/experiment_config.json):
    codellama_agent   existing tutoring agent, unchanged
    codellama_prompt  Code Llama with the controlled prompt only
ChatGPT and Claude are evaluated in their web applications using export-manual/import-manual.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

from backend.agent import tutor_agent as ta  # noqa: E402  (existing code, used unchanged)
from backend.agent.conversation import get_conversation  # noqa: E402
from dataset.leetcode_eval import get_problems  # noqa: E402
from evaluation.cross_model import controlled_prompt as cp  # noqa: E402
from evaluation.cross_model import metrics as mx  # noqa: E402
from evaluation.cross_model import providers  # noqa: E402
from evaluation.run_leetcode_eval import install_stub_llm, scripted_turns  # noqa: E402

CROSS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = CROSS_DIR / "experiment_config.json"
LLM_CONFIG = ROOT / "config" / "llm_config.json"
DEFAULT_OUT = ROOT / "results" / "cross_model"
EXPECTED_TURNS = 6  # diagnosis, fix, validation, 3 reflections (see run_leetcode_eval.scripted_turns)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def load_config(path: Path = DEFAULT_CONFIG) -> tuple[dict, dict]:
    """Return (sampling, conditions). Sampling is shared by every condition and
    inherits from config/llm_config.json so Code Llama's settings stay the single source of truth."""
    llm = json.loads(LLM_CONFIG.read_text(encoding="utf-8"))
    exp = json.loads(path.read_text(encoding="utf-8"))
    sampling = {
        "temperature": llm.get("temperature", 0.2),
        "max_tokens": llm.get("max_tokens", 300),
        "seed": llm.get("seed"),
    }
    sampling.update(exp.get("sampling_override") or {})

    conditions = {}
    for name, cfg in exp["conditions"].items():
        cfg = dict(cfg)
        if cfg.get("provider") == "ollama":
            cfg.setdefault("model", llm["model"])
            cfg.setdefault("base_url", llm["base_url"])
            cfg.setdefault("timeout", llm.get("timeout", 120))
        conditions[name] = cfg
    if "codellama_agent" in conditions:  # the agent reads config/llm_config.json itself
        conditions["codellama_agent"].setdefault("model", llm["model"])
    return sampling, conditions


def select_problems(language: str, only: set[int] | None) -> list[dict]:
    return [p for p in get_problems(language) if only is None or p["id"] in only]


def problem_set_sha256(problems: list[dict]) -> str:
    keep = ("id", "language", "code", "problem", "first_response", "fix", "validation", "reflections")
    blob = json.dumps([{k: p[k] for k in keep} for p in problems], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# Running one conversation
# --------------------------------------------------------------------------- #
def _base_record(run_id: str, condition: str, cfg: dict, problem: dict, repeat: int, dry_run: bool) -> dict:
    return {
        "run_id": run_id,
        "condition": condition,
        "kind": "agent" if cfg.get("kind") == "agent" else "prompt",
        "provider": cfg.get("provider", "agent"),
        "model_requested": cfg.get("model", ""),
        "language": problem["language"],
        "problem_id": problem["id"],
        "problem_name": problem["name"],
        "problem_text": problem["problem"],
        "code": problem["code"],
        "bug": problem["bug"],
        "repeat": repeat,
        "prompt_version": cp.PROMPT_VERSION if cfg.get("kind") != "agent" else "agent-pipeline",
        "prompt_sha256": cp.prompt_sha256(problem["language"]) if cfg.get("kind") != "agent" else "",
        "prompt_delivery": "n/a" if cfg.get("kind") == "agent" else "system_role",
        "dry_run": dry_run,
        "error": None,
    }


def run_agent_conversation(run_id, condition, cfg, problem, repeat, dry_run, stub_state) -> dict:
    """The existing agent, called exactly as run_leetcode_eval does. Stops when the agent concludes."""
    record = _base_record(run_id, condition, cfg, problem, repeat, dry_run)
    record["turns"] = []
    conversation_id = None
    for turn, (role, student_text) in enumerate(scripted_turns(problem), start=1):
        if stub_state is not None:
            stub_state["role"] = role
        reply, conversation_id = ta.generate_tutor_response(
            code=problem["code"], question=student_text, conversation_id=conversation_id,
            problem=problem["problem"], language=problem["language"],
        )
        conv = get_conversation(conversation_id)
        record["turns"].append({
            "turn": turn, "scripted_role": role, "student": student_text, "tutor": reply,
            "stage": conv.stage_name, "finish_reason": "", "input_tokens": None,
            "output_tokens": None, "latency_s": None,
        })
        if conv.concluded:
            break
    record["model_returned"] = [cfg.get("model", "")]
    record["sampling"] = {"note": "agent uses its own per-call temperatures; see backend/agent/tutor_agent.py"}
    return record


def run_prompt_conversation(run_id, condition, cfg, problem, repeat, sampling, dry_run) -> dict:
    """Controlled-prompt conversation: always runs all scripted turns for equal exposure."""
    record = _base_record(run_id, condition, cfg, problem, repeat, dry_run)
    effective = {**cfg, "provider": "mock"} if dry_run else cfg
    seed = None if sampling.get("seed") is None else sampling["seed"] + repeat
    system = cp.build_system_prompt(problem["language"])

    student_turns: list[str] = []
    tutor_replies: list[str] = []
    record["turns"] = []
    returned: set[str] = set()
    params_sent: dict = {}
    for turn, (role, student_text) in enumerate(scripted_turns(problem), start=1):
        student_turns.append(student_text)
        messages = cp.build_messages(problem, student_turns, tutor_replies)
        result = providers.chat(effective, system, messages, sampling, seed)
        tutor_replies.append(result.text)
        returned.add(result.model_returned)
        params_sent = result.params_sent or params_sent
        record["turns"].append({
            "turn": turn, "scripted_role": role, "student": student_text, "tutor": result.text,
            "stage": "", "finish_reason": result.finish_reason, "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens, "latency_s": result.latency_s,
        })
    record["model_returned"] = sorted(returned)
    record["sampling"] = {"requested": {**sampling, "seed": seed}, "params_sent": params_sent}
    return record


# --------------------------------------------------------------------------- #
# Run bookkeeping
# --------------------------------------------------------------------------- #
def _key(rec: dict) -> tuple:
    return (rec["condition"], rec["language"], rec["problem_id"], rec["repeat"])


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_metadata(args, sampling, conditions, problems_by_lang, run_id, dry_run) -> dict:
    return {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "prompt_version": cp.PROMPT_VERSION,
        "prompt_sha256": {lang: cp.prompt_sha256(lang) for lang in cp.LANGUAGES},
        "prompt_delivery": "system_role",
        "sampling": sampling,
        "repeats": args.repeats,
        "languages": sorted(problems_by_lang),
        "problem_ids": {lang: [p["id"] for p in ps] for lang, ps in problems_by_lang.items()},
        "problem_set_sha256": {lang: problem_set_sha256(ps) for lang, ps in problems_by_lang.items()},
        "conditions": conditions,
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "argv": sys.argv[1:],
    }


def check_resume_compatible(existing: dict, new: dict) -> None:
    """Refuse to mix results produced under different controls."""
    for field in ("prompt_sha256", "sampling", "problem_set_sha256", "conditions", "repeats"):
        if existing.get(field) != new.get(field):
            sys.exit(
                f"Cannot --resume: '{field}' differs from the original run, which would silently "
                f"break the controlled comparison.\n  original: {existing.get(field)}\n  now:      {new.get(field)}"
            )


def preflight(conditions: dict, selected: list[str]) -> None:
    """Fail fast if Ollama is unreachable or the required local model is missing."""
    for name in selected:
        cfg = conditions[name]
        provider = cfg.get("provider")
        if provider == "ollama" or cfg.get("kind") == "agent":
            base = cfg.get("base_url") or json.loads(LLM_CONFIG.read_text(encoding="utf-8"))["base_url"]
            model = cfg["model"]
            try:
                tags = requests.get(f"{base.rstrip('/')}/api/tags", timeout=10).json()
            except Exception as exc:  # noqa: BLE001
                sys.exit(f"[{name}] Cannot reach Ollama at {base}: {exc}\nStart it with `ollama serve`.")
            names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
            if model not in names:
                sys.exit(f"[{name}] Ollama has no model '{model}'. Run: ollama pull {model}")


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def write_analysis(run_dir: Path) -> None:
    records = read_jsonl(run_dir / "transcripts.jsonl")
    if not records:
        sys.exit(f"No transcripts found in {run_dir}")

    conv_rows, turn_rows = [], []
    for rec in records:
        result = mx.conversation_metrics(rec)
        base = {
            "run_id": rec["run_id"], "condition": rec["condition"], "model": ";".join(rec.get("model_returned") or []),
            "language": rec["language"], "problem_id": rec["problem_id"], "problem_name": rec["problem_name"],
            "repeat": rec["repeat"],
        }
        conv_rows.append({**base, **result["aggregate"]})
        turn_rows += [{**base, **m} for m in result["per_turn"]]

    def write_csv(name: str, rows: list[dict]) -> None:
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with (run_dir / name).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write_csv("metrics_per_conversation.csv", conv_rows)
    write_csv("metrics_per_turn.csv", turn_rows)
    write_csv("summary_by_condition.csv", mx.summarise(conv_rows, ("condition",)))
    write_csv("summary_by_condition_language.csv", mx.summarise(conv_rows, ("condition", "language")))

    empties = sum(r["empty_reply_turns"] for r in conv_rows)
    truncated = sum(r["truncated_turns"] for r in conv_rows)
    print(f"\nAnalysis written to {run_dir}  ({len(conv_rows)} conversations)")
    if empties:
        print(f"WARNING: {empties} empty replies. For reasoning models this usually means max_tokens was used up "
              f"on hidden reasoning; raise sampling_override.max_tokens for ALL conditions or lower the reasoning effort.")
    if truncated:
        print(f"WARNING: {truncated} replies were cut off by the token limit (finish_reason=length/max_tokens).")
    if any(r.get("dry_run") for r in records):
        print("NOTE: this run used stub/mock models (--dry-run). It checks plumbing only; it is NOT a result.")


# --------------------------------------------------------------------------- #
# Subcommand: run
# --------------------------------------------------------------------------- #
def cmd_run(args) -> None:
    sampling, conditions = load_config(Path(args.config))
    selected = [c.strip() for c in args.conditions.split(",")] if args.conditions else list(conditions)
    unknown = [c for c in selected if c not in conditions]
    if unknown:
        sys.exit(f"Unknown condition(s) {unknown}. Defined in config: {list(conditions)}")

    languages = cp.LANGUAGES if args.language == "both" else (args.language,)
    only = {int(x) for x in args.only.split(",")} if args.only else None
    problems_by_lang = {lang: select_problems(lang, only) for lang in languages}

    dry_run = args.dry_run
    run_id = args.run_id or (("dryrun-" if dry_run else "run-") + datetime.now().strftime("%Y%m%d-%H%M%S"))
    run_dir = Path(args.out) / run_id
    meta = build_metadata(args, sampling, {c: conditions[c] for c in selected}, problems_by_lang, run_id, dry_run)

    if not dry_run:
        try:
            preflight(conditions, selected)
        except providers.ProviderError as exc:
            sys.exit(str(exc))

    transcripts = run_dir / "transcripts.jsonl"
    meta_path = run_dir / "run_metadata.json"
    if run_dir.exists() and transcripts.exists():
        if not args.resume:
            sys.exit(f"{run_dir} already has results. Use --resume to continue it, or choose a new --run-id.")
        if meta_path.exists():
            check_resume_compatible(json.loads(meta_path.read_text(encoding="utf-8")), json.loads(json.dumps(meta)))
    run_dir.mkdir(parents=True, exist_ok=True)
    if not meta_path.exists():
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    done = {_key(r) for r in read_jsonl(transcripts) if not r.get("error")}
    stub_state = install_stub_llm() if dry_run else None

    total = sum(len(ps) for ps in problems_by_lang.values()) * len(selected) * args.repeats
    count = 0
    for condition in selected:
        cfg = conditions[condition]
        for language, problems in problems_by_lang.items():
            for problem in problems:
                for repeat in range(args.repeats):
                    count += 1
                    label = f"[{count}/{total}] {condition} {language} #{problem['id']} {problem['name']} r{repeat}"
                    if (condition, language, problem["id"], repeat) in done:
                        print(f"{label}  (skipped: already done)")
                        continue
                    print(label, flush=True)
                    try:
                        if cfg.get("kind") == "agent":
                            rec = run_agent_conversation(run_id, condition, cfg, problem, repeat, dry_run, stub_state)
                        else:
                            rec = run_prompt_conversation(run_id, condition, cfg, problem, repeat, sampling, dry_run)
                    except Exception as exc:  # noqa: BLE001
                        sys.exit(f"\nStopped at: {label}\n  {type(exc).__name__}: {exc}\n"
                                 f"Completed conversations are saved. Re-run the same command with --resume to continue.")
                    append_jsonl(transcripts, rec)

    write_analysis(run_dir)


# --------------------------------------------------------------------------- #
# Subcommands: export-manual / import-manual (web-app route)
# --------------------------------------------------------------------------- #
_REPLY_HEADING = re.compile(r"^### TURN (\d+) REPLY[ \t]*$", re.M)
_HEADER = re.compile(r"<!-- cross_model: version=(\S+) language=(\S+) id=(\d+) condition=(\S+)(?: repeat=(\d+))? -->")

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def render_manual_sheet(problem: dict, condition: str, repeat: int = 1) -> str:
    """Render one independent run in one file, preserving the single-run sheet structure."""
    turns = scripted_turns(problem)
    lines = [
        f"<!-- cross_model: version={cp.PROMPT_VERSION} language={problem['language']} id={problem['id']} condition={condition} repeat={repeat} -->",
        f"# Manual run sheet: {problem['language']} #{problem['id']} {problem['name']}  (condition: {condition}, repeat: {repeat})",
        "",
        "Start a brand-new chat for this run. Paste each turn exactly as written.",
        "Keep model/version, settings, and scripted text consistent across runs. Do not regenerate replies.",
        "Record the exact model name/version and collection date for `import-manual --model`.",
        "",
    ]
    for i, (role, student_text) in enumerate(turns, start=1):
        shown = cp.manual_first_message(problem, student_text) if i == 1 else student_text
        lines += [f"## TURN {i} - paste this" + (" (instructions + problem + code + student message)" if i == 1 else ""),
                  "````text", shown, "````", ""]
    lines += ["## RECORD REPLIES", ""]
    for i in range(1, len(turns) + 1):
        lines += [f"### TURN {i} REPLY", "<!-- paste the model's reply here -->", ""]
    return "\n".join(lines)


def cmd_export_manual(args) -> None:
    languages = cp.LANGUAGES if args.language == "both" else (args.language,)
    only = {int(x) for x in args.only.split(",")} if args.only else None
    out = Path(args.out) / args.condition
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for language in languages:
        for problem in select_problems(language, only):
            stem = f"{language}_{problem['id']:02d}_{_slug(problem['name'])}"
            for repeat in range(1, args.repeats + 1):
                path = out / f"{stem}_run{repeat}.md"
                path.write_text(render_manual_sheet(problem, args.condition, repeat), encoding="utf-8", newline="\n")
                count += 1
    print(f"Wrote {count} independent run sheets to {out}")


def parse_manual_sheet(text: str) -> tuple[dict, list[list[str]]]:
    header = _HEADER.search(text)
    if not header:
        raise ValueError("missing the '<!-- cross_model: ... -->' header line")
    version, language, pid, condition, repeat = header.groups()
    replies = {}
    headings = list(re.finditer(r"^### TURN (\d+) REPLY\s*$", text, re.M))
    for idx, heading in enumerate(headings):
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
        body = re.sub(r"<!--.*?-->", "", text[heading.end():end], flags=re.S).strip()
        if body:
            replies[int(heading.group(1))] = body
    ordered = [replies.get(i, "") for i in range(1, EXPECTED_TURNS + 1)]
    missing = [i for i, reply in enumerate(ordered, 1) if not reply]
    if missing:
        raise ValueError(f"no reply recorded for turn(s) {missing}")
    return {"version": version, "language": language, "id": int(pid), "condition": condition,
            "repeat": int(repeat) if repeat else 1}, [ordered]


def cmd_import_manual(args) -> None:
    run_dir = Path(args.out) / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    transcripts = run_dir / "transcripts.jsonl"
    done = {_key(r) for r in read_jsonl(transcripts)}
    problems = {(p["language"], p["id"]): p for lang in cp.LANGUAGES for p in get_problems(lang)}

    imported, failures = 0, []
    for path in sorted(Path(args.dir).glob("*.md")):
        try:
            info, repeat_replies = parse_manual_sheet(path.read_text(encoding="utf-8"))
            if info["version"] != cp.PROMPT_VERSION:
                raise ValueError(f"sheet is for prompt {info['version']}, current is {cp.PROMPT_VERSION}")
            if info["condition"] != args.condition:
                raise ValueError(f"sheet condition is '{info['condition']}', not '{args.condition}'")
            problem = problems[(info["language"], info["id"])]
        except (ValueError, KeyError) as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        for replies in repeat_replies:
            repeat = info["repeat"]
            rec = _base_record(args.run_id, args.condition, {"provider": "manual", "model": args.model}, problem, repeat, False)
            rec["prompt_delivery"] = "inline_first_message"
            rec["kind"] = "prompt"
            rec["prompt_version"] = cp.PROMPT_VERSION
            rec["prompt_sha256"] = cp.prompt_sha256(problem["language"])
            rec["manual"] = True
            rec["turns"] = [
                {"turn": i, "scripted_role": role, "student": text, "tutor": replies[i - 1], "stage": "",
                 "finish_reason": "", "input_tokens": None, "output_tokens": None, "latency_s": None}
                for i, (role, text) in enumerate(scripted_turns(problem), start=1)
            ]
            rec["model_returned"] = [args.model]
            rec["sampling"] = {"note": "set by the web app; not controllable"}
            if _key(rec) in done:
                failures.append(f"{path.name} run {repeat}: already imported into {run_dir.name}")
                continue
            append_jsonl(transcripts, rec)
            done.add(_key(rec))
            imported += 1

    meta_path = run_dir / "run_metadata.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "run_id": args.run_id, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dry_run": False, "manual": True, "prompt_version": cp.PROMPT_VERSION,
            "prompt_sha256": {lang: cp.prompt_sha256(lang) for lang in cp.LANGUAGES},
            "prompt_delivery": "inline_first_message", "git_commit": git_commit(),
        }, indent=2), encoding="utf-8")
    print(f"Imported {imported} conversation(s) into {run_dir}")
    for failure in failures:
        print(f"  SKIPPED {failure}")
    if imported:
        write_analysis(run_dir)


def cmd_analyse(args) -> None:
    write_analysis(Path(args.run_dir))


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run conditions through the problem set")
    run.add_argument("--conditions", help="comma-separated subset of conditions (default: all in the config)")
    run.add_argument("--language", choices=(*cp.LANGUAGES, "both"), default="both")
    run.add_argument("--only", help="comma-separated problem ids, e.g. 1,5,9")
    run.add_argument("--repeats", type=int, default=1, help="independent repeats per problem")
    run.add_argument("--run-id", help="name of the output folder (default: timestamp)")
    run.add_argument("--resume", action="store_true", help="continue an interrupted run with identical settings")
    run.add_argument("--out", default=str(DEFAULT_OUT))
    run.add_argument("--config", default=str(DEFAULT_CONFIG))
    run.add_argument("--dry-run", action="store_true", help="stub/mock models: plumbing check only, not a result")
    run.set_defaults(func=cmd_run)

    export = sub.add_parser("export-manual", help="write copy-paste run sheets for a chat web app")
    export.add_argument("--condition", required=True, help="label for the model, e.g. chatgpt or claude")
    export.add_argument("--language", choices=(*cp.LANGUAGES, "both"), default="both")
    export.add_argument("--only")
    export.add_argument("--repeats", type=int, default=3, help="independent manual runs per problem (default: 3)")
    export.add_argument("--out", default=str(ROOT / "manual_pack"))
    export.set_defaults(func=cmd_export_manual)

    imp = sub.add_parser("import-manual", help="read filled-in run sheets back into a results folder")
    imp.add_argument("--condition", required=True)
    imp.add_argument("--dir", required=True, help="folder of filled-in sheets")
    imp.add_argument("--model", required=True, help="exact model name/version shown in the app, plus date")
    imp.add_argument("--run-id", required=True)
    imp.add_argument("--out", default=str(DEFAULT_OUT))
    imp.set_defaults(func=cmd_import_manual)

    analyse = sub.add_parser("analyse", help="recompute metrics and summaries for a run folder")
    analyse.add_argument("--run-dir", required=True)
    analyse.set_defaults(func=cmd_analyse)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
