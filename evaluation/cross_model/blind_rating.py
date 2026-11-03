"""Blinded manual rating for the cross-model study.

Why blind: the rater knows the agent is "their" system and that GPT/Claude are
the strong baselines. Unblinded ratings would be biased. This tool strips every
condition/model label, shuffles all conversations from all runs together, and
keeps the mapping in a separate ``answer_key.csv`` that is opened only after
rating is finished.

    python -m evaluation.cross_model.blind_rating make \\
        --run-dir results/cross_model/main --run-dir results/cross_model/manual

    # ... rate rating_sheet.csv by reading rating_transcripts.md ...

    python -m evaluation.cross_model.blind_rating summarise \\
        --sheet results/cross_model/main/blind/rating_sheet.csv \\
        --key   results/cross_model/main/blind/answer_key.csv

For inter-rater agreement give a second person a copy of the BLANK
``rating_sheet.csv`` and pass it with ``--sheet2``. Blinding is imperfect: the
agent's replies stop at its conclusion and each vendor has a recognisable style.
Say so in the limitations section.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluation.cross_model.metrics import mentions_model_identity  # noqa: E402

# The first three keep the names of the existing MANUAL_ columns in run_leetcode_eval.py.
SCALE_COLUMNS = (
    "diagnosis_recognised",
    "meaningful_followups",
    "appropriate_conclusion",
    "code_grounded",
    "tone_concise",
)
BINARY_COLUMNS = ("solution_leak",)

RUBRIC = """# Rating guide (read before rating; keep open while rating)

You see only the problem, the student's code, the hidden ground-truth bug and a
fixed dialogue. The student's lines are scripted and identical for every tutor,
so do not penalise the tutor for how the student answers. Judge the tutor's
replies only. Rate each conversation as a whole. Do not try to guess which
system wrote it; if you think you can tell, note it in `notes` and carry on.

Scale columns are 1-5 (whole numbers). Leave nothing blank.

| column | 1 | 3 | 5 |
|---|---|---|---|
| diagnosis_recognised | ignores or contradicts the student's correct diagnosis, or keeps asking them to find the bug | acknowledges it but partly re-asks or restates it | briefly acknowledges it and moves straight on, never re-asks |
| meaningful_followups | generic, repetitive, or off the student's reasoning | relevant but some questions add little or overlap | every question moves the student's reasoning forward for that moment (confirm, test, edge case, side effects) |
| appropriate_conclusion | never concludes, or concludes long before the student has validated the fix | concludes at a sensible point but asks a question, adds new material, or is rambling | concludes after the student has validated the fix and been probed, with no question, no new solution, and a nudge to re-run their own change |
| code_grounded | talks about things not in the student's code (wrong language, invented variables, unrelated concepts such as recursion in iterative code) | mostly grounded with one slip | every reference matches the student's actual code and language |
| tone_concise | long, lecturing, or confusing for a student | acceptable | short, supportive, conversational, 1-3 sentences |

solution_leak is 0 or 1: put 1 if at ANY turn the tutor supplied corrected code,
the replacement expression, the exact change to make, or the cause of the bug
before the student said it. Quoting the student's own code or suggesting a
test input to trace is NOT a leak.
"""


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# make
# --------------------------------------------------------------------------- #
def make(run_dirs: list[Path], out: Path, seed: int, allow_dry_run: bool) -> None:
    records = []
    for run_dir in run_dirs:
        for rec in _read_jsonl(run_dir / "transcripts.jsonl"):
            if rec.get("dry_run") and not allow_dry_run:
                sys.exit(f"{run_dir} is a dry run (mock models). Refusing to build a rating set from it; pass --allow-dry-run to override.")
            records.append(rec)
    if not records:
        sys.exit("No transcripts found.")

    random.Random(seed).shuffle(records)
    out.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(len(records))))

    sheet_rows, key_rows, md = [], [], ["# Transcripts for blind rating", "",
                                         "Rate each item in `rating_sheet.csv` using `RATING_GUIDE.md`.", ""]
    for n, rec in enumerate(records, start=1):
        item = f"R{n:0{width}d}"
        sheet_rows.append({"item_id": item, "language": rec["language"], "problem_id": rec["problem_id"],
                           "problem_name": rec["problem_name"], **{c: "" for c in (*SCALE_COLUMNS, *BINARY_COLUMNS)}, "notes": ""})
        key_rows.append({
            "item_id": item, "condition": rec["condition"], "model": ";".join(rec.get("model_returned") or []),
            "run_id": rec["run_id"], "repeat": rec["repeat"], "language": rec["language"], "problem_id": rec["problem_id"],
            "reply_mentions_model_identity": int(any(mentions_model_identity(t["tutor"]) for t in rec["turns"])),
        })
        md += [f"## {item} - {rec['problem_name']} ({rec['language']})", "",
               f"Hidden ground-truth bug: {rec['bug']}", "",
               f"Problem: {rec['problem_text']}", "",
               f"```{rec['language']}", rec["code"], "```", ""]
        for t in rec["turns"]:
            md += [f"**Student:** {t['student']}", "", f"**Tutor:** {t['tutor']}", ""]
        md += ["---", ""]

    def write_csv(name: str, rows: list[dict]) -> None:
        with (out / name).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv("rating_sheet.csv", sheet_rows)
    write_csv("answer_key.csv", key_rows)
    (out / "rating_transcripts.md").write_text("\n".join(md), encoding="utf-8")
    (out / "RATING_GUIDE.md").write_text(RUBRIC, encoding="utf-8")

    leaks = sum(r["reply_mentions_model_identity"] for r in key_rows)
    print(f"Wrote {len(records)} blinded items to {out}")
    print("Do NOT open answer_key.csv until all ratings are complete.")
    if leaks:
        print(f"NOTE: {leaks} conversation(s) have replies naming their own model/vendor; they are flagged in answer_key.csv "
              f"(reply_mentions_model_identity). Consider redacting those items or noting the blinding break.")


# --------------------------------------------------------------------------- #
# summarise
# --------------------------------------------------------------------------- #
def cohen_kappa(a: list[int], b: list[int], categories: list[int], quadratic: bool) -> float | None:
    """Cohen's kappa; quadratic-weighted if ``quadratic`` (use for ordinal 1-5 scales).
    Returns None when chance agreement leaves nothing to measure (e.g. both raters constant)."""
    k = len(categories)
    index = {c: i for i, c in enumerate(categories)}
    n = len(a)
    if n == 0 or n != len(b):
        return None
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[index[x]][index[y]] += 1
    row = [sum(observed[i]) for i in range(k)]
    col = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    def weight(i: int, j: int) -> float:
        if quadratic:
            return ((i - j) ** 2) / ((k - 1) ** 2) if k > 1 else 0.0
        return 0.0 if i == j else 1.0

    num = sum(weight(i, j) * observed[i][j] for i in range(k) for j in range(k))
    den = sum(weight(i, j) * row[i] * col[j] / n for i in range(k) for j in range(k))
    if den == 0:
        return None
    return 1 - num / den


def _load_ratings(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["item_id"]] = row
    return rows


def _validate(rows: dict[str, dict], label: str) -> dict[str, dict]:
    """Return only complete, in-range rows; report the rest."""
    good, bad = {}, []
    for item, row in rows.items():
        try:
            parsed = {c: int(row[c]) for c in (*SCALE_COLUMNS, *BINARY_COLUMNS)}
            if not all(1 <= parsed[c] <= 5 for c in SCALE_COLUMNS) or not all(parsed[c] in (0, 1) for c in BINARY_COLUMNS):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            bad.append(item)
            continue
        good[item] = parsed
    if bad:
        print(f"WARNING: {label}: {len(bad)} incomplete/invalid row(s) ignored (first few: {bad[:5]}).")
    return good


def summarise(sheet: Path, key: Path, sheet2: Path | None, out: Path | None) -> list[dict]:
    keys = {r["item_id"]: r for r in csv.DictReader(key.open(newline="", encoding="utf-8"))}
    r1 = _validate(_load_ratings(sheet), "rater 1")
    r2 = _validate(_load_ratings(sheet2), "rater 2") if sheet2 else {}

    if sheet2:
        shared = sorted(set(r1) & set(r2))
        print(f"\nInter-rater agreement on {len(shared)} items")
        for c in SCALE_COLUMNS:
            kappa = cohen_kappa([r1[i][c] for i in shared], [r2[i][c] for i in shared], [1, 2, 3, 4, 5], quadratic=True)
            exact = mean(r1[i][c] == r2[i][c] for i in shared) if shared else float("nan")
            print(f"  {c:<24} weighted kappa = {'n/a' if kappa is None else f'{kappa:.2f}'}   exact agreement = {exact:.0%}")
        for c in BINARY_COLUMNS:
            kappa = cohen_kappa([r1[i][c] for i in shared], [r2[i][c] for i in shared], [0, 1], quadratic=False)
            print(f"  {c:<24} kappa = {'n/a' if kappa is None else f'{kappa:.2f}'}")

    # Average the raters per item where both rated, otherwise use rater 1.
    combined = {}
    for item, ratings in r1.items():
        combined[item] = ({c: mean([ratings[c], r2[item][c]]) for c in ratings} if item in r2 else ratings)

    groups: dict[str, list[dict]] = defaultdict(list)
    for item, ratings in combined.items():
        groups[keys[item]["condition"]].append(ratings)

    rows = []
    for condition, members in sorted(groups.items()):
        row = {"condition": condition, "n_rated": len(members)}
        for c in SCALE_COLUMNS:
            values = [m[c] for m in members]
            row[f"{c}_mean"] = round(mean(values), 2)
            row[f"{c}_sd"] = round(stdev(values), 2) if len(values) > 1 else ""
        row["solution_leak_rate"] = round(mean(m["solution_leak"] for m in members), 3)
        rows.append(row)

    print("\nMean rating by condition (1-5; higher is better, except solution_leak_rate where lower is better)")
    for row in rows:
        scores = "  ".join(f"{c.split('_')[0][:5]}={row[f'{c}_mean']:.2f}" for c in SCALE_COLUMNS)
        print(f"  {row['condition']:<18} n={row['n_rated']:<3} {scores}  leak={row['solution_leak_rate']:.2f}")

    if out and rows:
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nWrote {out}")
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    m = sub.add_parser("make", help="build the blinded rating set")
    m.add_argument("--run-dir", action="append", required=True, type=Path, help="repeatable; all runs are shuffled together")
    m.add_argument("--out", type=Path, help="default: <first run-dir>/blind")
    m.add_argument("--seed", type=int, default=2026, help="shuffle seed (recorded nowhere else: keep it with your notes)")
    m.add_argument("--allow-dry-run", action="store_true")

    s = sub.add_parser("summarise", help="aggregate completed ratings by condition")
    s.add_argument("--sheet", required=True, type=Path)
    s.add_argument("--key", required=True, type=Path)
    s.add_argument("--sheet2", type=Path, help="second rater's completed copy of the same sheet")
    s.add_argument("--out", type=Path, help="write the summary CSV here")

    args = parser.parse_args(argv)
    if args.command == "make":
        make(args.run_dir, args.out or args.run_dir[0] / "blind", args.seed, args.allow_dry_run)
    else:
        summarise(args.sheet, args.key, args.sheet2, args.out)


if __name__ == "__main__":
    main()
