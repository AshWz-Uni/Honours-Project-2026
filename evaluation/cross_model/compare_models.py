"""Cross-model evaluation - Code Llama agent and Code Llama (controlled prompt) vs ChatGPT and Claude.

Run from the project root (no import-manual step needed; the ChatGPT / Claude worksheets in manual_pack/
are read directly by the same tolerant parser that `import-manual` uses)

Inputs
    results/cross_model/local-main/transcripts.jsonl   codellama_agent + codellama_prompt (30 per language each)
    manual_pack/chatgpt/*.md, manual_pack/claude/*.md   filled-in worksheets (3 runs x 20 problems each)

Outputs (default results/analysis/cross_model/)
    report.md, headline_by_condition.csv, pairwise_tests.csv, by_language.csv,
    conversation_metrics.csv, turn_metrics.csv, review_*.csv, fig0..fig5 *.png

Design decisions
    * Four conditions: Code Llama + tutoring agent, Code Llama (controlled prompt), ChatGPT (GPT-5.6 Luna),
      Claude (Sonnet 5.5, medium). The model names are written on every figure and in the report.
    * ALL 60 conversations per model are used (10 problems x 2 languages x 3 repeats = 360 tutor turns).
      Nothing is sampled. The script stops if any model has fewer than 60.

What is measured
    Automatic proxies for following the controlled prompt (one question per turn on turns 1-5, no question on
    turn 6, <= 3 sentences, no code, no Hint:/Question: labels, no repeated question). They do not measure
    whether the tutoring was *good*; that needs the blind manual rating (blind_rating.py).

    "rule compliance" uses only model-neutral checks. The two `agent_*` detectors (new code, solution leak) are
    the agent's own filters, so the agent scores ~0 on them by construction; they are reported with a dagger
    and are not used in rule compliance or in the paired tests that involve the agent.

Statistics: headline numbers are means over all 60 conversations. For the paired tests the 3 repeats of one
problem are averaged into one item (20 items per model), because repeats of the same problem are not
independent; all 60 conversations still feed those item means.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluation.cross_model import analysis_utils as au  # noqa: E402
from evaluation.cross_model import metrics as mx  # noqa: E402
from evaluation.cross_model import run_cross_model_eval as runner  # noqa: E402
from evaluation.cross_model import socratic_quality as sq  # noqa: E402

EXPECTED = mx.EXPECTED_CONCLUSION_TURN  # 6
CONDITIONS = list(au.ORDER)             # codellama_agent, codellama_prompt, chatgpt, claude
EXPECTED_PER_CONDITION = 60             # 10 problems x 2 languages x 3 repeats
CIRCULAR = {"agent_new_code_turns", "agent_solution_leak_turns"}   # agent filters its own replies with these
DAGGER = "\u2020"

PAIRS = [  # (a, b, family)
    ("codellama_agent", "chatgpt", "primary"), ("codellama_agent", "claude", "primary"),
    ("codellama_prompt", "chatgpt", "primary"), ("codellama_prompt", "claude", "primary"),
    ("codellama_agent", "codellama_prompt", "secondary"), ("chatgpt", "claude", "secondary"),
]

# (column, label, direction) direction: +1 higher is better, -1 lower is better, 0 descriptive
HEADLINE = [
    ("structure", "Right turn structure (exactly 1 question on turns 1-5, none on turn 6)", +1),
    ("rule_compliance", "Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats)", +1),
    ("on_time_conclusion", "Concluded exactly on turn 6", +1),
    ("premature_conclusion", "Concluded before turn 6", -1),
    ("never_concluded", "Never concluded (a question on turn 6 and no earlier conclusion)", -1),
    ("multi_question_turns", "Turns with 2+ questions (of 6)", -1),
    ("over_length_turns", "Turns longer than 3 sentences (of 6)", -1),
    ("mean_words_per_reply", "Mean words per reply", 0),
    ("has_code_block_turns", "Turns containing a code block (of 6)", -1),
    ("agent_new_code_turns", f"Turns introducing new code (of 6) {DAGGER}", -1),
    ("agent_solution_leak_turns", f"Turns flagged as leaking the solution (of 6) {DAGGER}", -1),
    ("possible_fix_giving_turns", "Turns with fix-giving phrases (of 6, loose heuristic)", -1),
    ("repeated_prior_question_turns", "Turns repeating an earlier question (of 6)", -1),
    ("label_leak_turns", "Turns showing Hint:/Question: labels (of 6)", -1),
    ("wrong_language_terms_turns", "JavaScript turns using Python terms (of 6)", -1),
    ("mentions_model_identity_turns", "Turns naming the model/vendor (of 6)", 0),
]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _short(c: str) -> str:
    return au.LABELS.get(c, c).replace("\n", " ")


def load_records(args) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    records: list[dict] = []

    local = Path(args.local_run) / "transcripts.jsonl"
    if local.exists():
        loaded = [r for r in runner.read_jsonl(local) if not r.get("error") and not r.get("dry_run")
                  and r["condition"] in CONDITIONS]
        # the local runner numbers repeats 0-2, the worksheets 1-3: put them on the same 1-3 scale
        if loaded and min(r["repeat"] for r in loaded) == 0:
            for r in loaded:
                r["repeat"] += 1
        records += loaded
        for cond in ("codellama_agent", "codellama_prompt"):
            n = sum(r["condition"] == cond for r in loaded)
            notes.append(f"`{_rel(local)}`: {n} conversations for `{cond}` ({au.MODEL_NAMES[cond]}).")
    else:
        notes.append(f"WARNING: no local run found at {_rel(local)}; the Code Llama conditions are missing.")

    labels = {"chatgpt": "ChatGPT web, GPT-5.6 Luna", "claude": "Claude web, Sonnet 5.5 (medium)"}
    labels.update(dict(m.split("=", 1) for m in (args.model or [])))
    for spec in args.manual:
        name, directory = spec.split("=", 1)
        if not Path(directory).exists():
            notes.append(f"WARNING: {_rel(directory)} not found; condition '{name}' skipped.")
            continue
        label = labels.get(name) or runner._default_model_label(name)
        recs, failures, audit = runner.load_manual_records(directory, name, label, f"manual-{name}",
                                                           keep_invalid=not args.drop_invalid)
        records += recs
        notes.append(f"`{_rel(directory)}`: {len(recs)} conversations loaded as `{name}` ({au.MODEL_NAMES.get(name, label)}).")
        for f in failures:
            notes.append(f"  EXCLUDED/UNPARSEABLE - {f}")
        for a_ in audit:
            notes.append(f"  {a_}")
    return records, notes


def check_complete(records: list[dict]) -> list[str]:
    """Stop unless every condition has exactly the 60 expected conversations."""
    keys: dict[str, set] = defaultdict(set)
    for r in records:
        keys[r["condition"]].add((r["language"], r["problem_id"], r["repeat"]))
    universe = set().union(*keys.values()) if keys else set()
    problems = []
    for cond in CONDITIONS:
        have = keys.get(cond, set())
        if len(have) != EXPECTED_PER_CONDITION:
            problems.append(f"{cond}: {len(have)} of {EXPECTED_PER_CONDITION} conversations; missing {sorted(universe - have)}")
    if problems:
        sys.exit("Not every model has all 60 conversations:\n  " + "\n  ".join(problems))
    return [f"Coverage check passed: {EXPECTED_PER_CONDITION} conversations for each of {len(CONDITIONS)} models "
            "(10 problems x 2 languages x 3 repeats). Nothing is sampled."]


# --------------------------------------------------------------------------- #
# Metrics (one definition per measure)
# --------------------------------------------------------------------------- #
def build_frames(records: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    turn_rows, conv_rows = [], []
    for rec in records:
        result = mx.conversation_metrics(rec)
        base = {"condition": rec["condition"], "language": rec["language"], "problem_id": rec["problem_id"],
                "problem_name": rec["problem_name"], "repeat": rec["repeat"]}
        for m, t in zip(result["per_turn"], rec["turns"]):
            text = t["tutor"]
            nq = m["n_question_marks"]
            structure_ok = (nq == 1) if m["turn"] < EXPECTED else (nq == 0)
            format_ok = not (m["over_length"] or m["has_code_block"] or m["label_leak"]
                             or m["repeated_prior_question"] or m["empty_reply"])
            turn_rows.append({**base, **m, "possible_fix_giving": int(au.tells_fix(text)),
                              "structure": int(structure_ok), "compliant": int(format_ok and structure_ok), "text": text})
        agg = result["aggregate"]
        conv_rows.append({**base, **agg,
                          "concluded_on_turn": agg["concluded_on_turn"] if agg["concluded_on_turn"] != "" else np.nan})
    turns = pd.DataFrame(turn_rows)
    conv = pd.DataFrame(conv_rows).rename(columns={"concluded_on_expected_turn": "on_time_conclusion"})

    key = ["condition", "language", "problem_id", "repeat"]
    g = turns.groupby(key)
    extra = pd.DataFrame({
        "structure": g["structure"].mean(),
        "rule_compliance": g["compliant"].mean(),
        "possible_fix_giving_turns": g["possible_fix_giving"].sum(),
    }).reset_index()
    conv = conv.merge(extra, on=key)
    conv.loc[conv["language"] != "javascript", "wrong_language_terms_turns"] = np.nan   # JS-only measure
    return conv, turns


def item_table(conv: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """One row per (condition, language, problem): mean over that problem's 3 repeats."""
    return conv.groupby(["condition", "language", "problem_id"])[metrics].mean().reset_index()


def headline_table(conv: pd.DataFrame, conditions: list[str]) -> pd.DataFrame:
    rows = []
    for col, label, _ in HEADLINE:
        row = {"metric": col, "description": label}
        for c in conditions:
            vals = conv.loc[conv["condition"] == c, col].to_numpy(float)
            row[f"{c}_mean"] = float(np.nanmean(vals)) if len(vals) and not np.all(np.isnan(vals)) else np.nan
            row[f"{c}_n_conversations"] = int(np.sum(~np.isnan(vals)))
        rows.append(row)
    return pd.DataFrame(rows)


def pairwise_table(items: pd.DataFrame, conditions: list[str]) -> pd.DataFrame:
    rows = []
    for col, label, direction in HEADLINE:
        wide = items.pivot_table(index=["language", "problem_id"], columns="condition", values=col)
        for a, b, family in PAIRS:
            if a not in conditions or b not in conditions or a not in wide or b not in wide:
                continue
            if col in CIRCULAR and "codellama_agent" in (a, b):
                continue   # the agent filters its own replies with these detectors: a comparison would be meaningless
            res = au.paired_test(wide[a].to_numpy(), wide[b].to_numpy())
            rows.append({"metric": col, "description": label, "comparison": f"{a} - {b}", "family": family,
                         "better_is": {1: "higher", -1: "lower", 0: "n/a"}[direction], **res})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = au.holm(out["p_wilcoxon"].tolist())
    return out


# --------------------------------------------------------------------------- #
# Quality of the Socratic questions (see socratic_quality.py for the criteria)
# --------------------------------------------------------------------------- #
def quality_frame(records: list[dict]) -> pd.DataFrame:
    """One row per tutor reply on turns 1-5 (the turns where a question is expected)."""
    rows = []
    for rec in records:
        scored = sq.score_conversation([t["tutor"] for t in rec["turns"]], [t["student"] for t in rec["turns"]],
                                       rec["code"], rec["language"])
        for s_ in scored:
            rows.append({"condition": rec["condition"], "language": rec["language"], "problem_id": rec["problem_id"],
                         "problem_name": rec["problem_name"], "repeat": rec["repeat"], **s_})
    q = pd.DataFrame(rows)
    for col in sq.CRITERIA + ["quality_score", "high_quality", "yes_no_start", "responsive_to_student", "canned"]:
        q[col] = q[col].astype(float)   # NaN on turns with no question
    return q


def quality_tables(q: pd.DataFrame, conditions: list[str]) -> dict[str, pd.DataFrame]:
    rows, types, by_turn = [], [], []
    for c in conditions:
        sub = q[q["condition"] == c]
        asked = sub[sub["has_question"] == 1]
        row = {"condition": c, "model": au.MODEL_NAMES[c], "question_turns_expected": len(sub),
               "turns_with_a_question": len(asked), "turns_without_a_question": len(sub) - len(asked),
               "mean_quality_score_0_to_5": asked["quality_score"].mean(),
               "high_quality_share_of_questions": asked["high_quality"].mean(),
               "high_quality_share_of_all_expected_turns": asked["high_quality"].sum() / len(sub)}
        for crit in sq.CRITERIA + ["responsive_to_student", "yes_no_start"]:
            row[crit] = asked[crit].mean()
        row["canned_fallback_share"] = asked["canned"].mean()
        rows.append(row)
        for t in sq.TYPES:
            types.append({"condition": c, "question_type": t, "share": (asked["question_type"] == t).mean(),
                          "count": int((asked["question_type"] == t).sum())})
        for t, g in asked.groupby("turn"):
            by_turn.append({"condition": c, "turn": int(t), "mean_quality_score": g["quality_score"].mean(),
                            "high_quality_share": g["high_quality"].mean(), "n": len(g)})
    out = {"by_condition": pd.DataFrame(rows), "types": pd.DataFrame(types), "by_turn": pd.DataFrame(by_turn)}
    ag = q[(q["condition"] == "codellama_agent") & (q["has_question"] == 1)]
    if len(ag):
        out["agent_split"] = pd.DataFrame([
            {"source": name, "questions": len(g), "mean_quality_score": g["quality_score"].mean(),
             "high_quality_share": g["high_quality"].mean(), "code_grounded": g["code_grounded"].mean()}
            for name, g in (("written by Code Llama", ag[ag["canned"] == 0]), ("canned fallback question", ag[ag["canned"] == 1]))
            if len(g)])
    return out


def quality_conversation_table(q: pd.DataFrame) -> pd.DataFrame:
    """One row per conversation: mean quality over its question turns, and how varied its question types were."""
    asked = q[q["has_question"] == 1]
    g = asked.groupby(["condition", "language", "problem_id", "repeat"])
    conv = pd.DataFrame({"mean_quality_score": g["quality_score"].mean(), "high_quality_share": g["high_quality"].mean(),
                         "type_variety": g["question_type"].apply(lambda s: s.nunique() / len(s))}).reset_index()
    return conv


def quality_tests(qconv: pd.DataFrame, conditions: list[str]) -> pd.DataFrame:
    items = qconv.groupby(["condition", "language", "problem_id"])[["mean_quality_score", "high_quality_share", "type_variety"]].mean().reset_index()
    labels = {"mean_quality_score": "Mean question quality score (0-5)", "high_quality_share": "Share of high-quality questions",
              "type_variety": "Variety of question types (distinct types / questions)"}
    rows = []
    for col, label in labels.items():
        wide = items.pivot_table(index=["language", "problem_id"], columns="condition", values=col)
        for a, b, family in PAIRS:
            if a in wide and b in wide:
                rows.append({"metric": col, "description": label, "comparison": f"{a} - {b}", "family": family,
                             **au.paired_test(wide[a].to_numpy(), wide[b].to_numpy())})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = au.holm(out["p_wilcoxon"].tolist())
    return out


def quality_figures(out: Path, q: pd.DataFrame, qt: dict, conditions: list[str]) -> list[str]:
    plt = au.setup_matplotlib()
    made: list[str] = []
    colors = {c: au.PALETTE[c] for c in conditions}
    bc = qt["by_condition"].set_index("condition")

    def done(fig, name):
        au.save(fig, out / name, au.FOOTER_CROSS + "  |  question-quality scores are rule-based proxies")
        plt.close(fig)
        made.append(name)

    # fig6 - criteria pass rates (among turns that contain a question) + high-quality share
    cols = sq.CRITERIA + ["high_quality_share_of_questions"]
    labels = [sq.CRITERIA_LABELS[c] for c in sq.CRITERIA] + ["High quality\n(all 5 met)"]
    fig, ax = plt.subplots(figsize=(12.5, 5.6))
    x = np.arange(len(cols))
    w = 0.8 / len(conditions)
    for i, c in enumerate(conditions):
        vals = [bc.loc[c, k] for k in cols]
        bars = ax.bar(x + (i - (len(conditions) - 1) / 2) * w, vals, w, color=colors[c], label=au.MODEL_NAMES[c])
        au.annotate_bars(ax, bars, "pct", fontsize=7)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Share of tutor turns that contain a question (turns 1-5)")
    ax.set_title("Quality of the Socratic questions: share of questions meeting each criterion")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.17), fontsize=8)
    n_txt = "; ".join(f"{au.LABELS[c].split(chr(10))[0]} {int(bc.loc[c, 'turns_with_a_question'])}/{int(bc.loc[c, 'question_turns_expected'])}" for c in conditions)
    ax.text(0, -0.30, f"Turns containing a question (scored / expected): {n_txt}", transform=ax.transAxes, fontsize=7, color="#555555")
    done(fig, "fig6_question_quality_criteria.png")

    # fig7 - what kind of question is asked
    tp = qt["types"]
    fig, ax = plt.subplots(figsize=(10.5, 4.4))
    left = np.zeros(len(conditions))
    ypos = np.arange(len(conditions))[::-1]
    shades = plt.cm.viridis(np.linspace(0.1, 0.9, len(sq.TYPES)))
    for t, shade in zip(sq.TYPES, shades):
        share = np.array([tp[(tp["condition"] == c) & (tp["question_type"] == t)]["share"].iloc[0] for c in conditions])
        cnt = np.array([tp[(tp["condition"] == c) & (tp["question_type"] == t)]["count"].iloc[0] for c in conditions])
        bars = ax.barh(ypos, share, left=left, color=[shade], edgecolor="white", label=t)
        for bar, sh, k, l0 in zip(bars, share, cnt, left):
            if sh >= 0.05:
                ax.text(l0 + sh / 2, bar.get_y() + bar.get_height() / 2, f"{100 * sh:.0f}%\n({k})", ha="center", va="center",
                        fontsize=7, color="white" if t in ("recall", "propose", "predict") else "black")
            elif k:
                ax.text(l0 + sh / 2, bar.get_y() + bar.get_height() / 2, f"{k}", ha="center", va="center", fontsize=6)
        left += share
    ax.set_yticks(ypos, [au.LABELS[c] for c in conditions], fontsize=8)
    ax.set_xlim(0, 1)
    ax.grid(axis="y", visible=False)
    ax.set_title("What the questions ask the student to do (cognitive type)", fontsize=10)
    ax.set_xlabel("Share of questions (count in brackets)")
    ax.legend(ncol=6, bbox_to_anchor=(0, 1.1), loc="lower left", frameon=False, fontsize=8)
    done(fig, "fig7_question_types.png")

    # fig8 - quality by turn (mean 0-5 score), annotated heat map
    bt = qt["by_turn"]
    tt = list(range(1, EXPECTED))
    mat = np.array([[bt[(bt["condition"] == c) & (bt["turn"] == t)]["mean_quality_score"].mean() for t in tt] for c in conditions])
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    im = ax.imshow(mat, cmap="YlGn", vmin=0, vmax=5, aspect="auto")
    ax.set_xticks(range(len(tt)), [f"turn {t}" for t in tt])
    ax.set_yticks(range(len(conditions)), [au.LABELS[c] for c in conditions], fontsize=8)
    ax.grid(False)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, "" if np.isnan(mat[i, j]) else f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, label="Mean quality score (0-5)")
    ax.set_title("Question quality score by turn (questions only)", fontsize=10)
    done(fig, "fig8_question_quality_by_turn.png")
    return made


# --------------------------------------------------------------------------- #
# Figures (model names in every legend/axis and in a footer; every value is written on the chart)
# --------------------------------------------------------------------------- #
def make_figures(out: Path, conv, turns, items, headline, conditions) -> list[str]:
    plt = au.setup_matplotlib()
    made: list[str] = []
    colors = {c: au.PALETTE[c] for c in conditions}
    n_conv = conv.groupby("condition").size().reindex(conditions)
    foot = au.FOOTER_CROSS
    h = headline.set_index("metric")

    def done(fig, name):
        au.save(fig, out / name, foot)
        plt.close(fig)
        made.append(name)

    # fig0 - coverage: all 60 conversations per model
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = np.arange(len(conditions))
    bottoms = np.zeros(len(conditions))
    for lang, shade in (("python", "#4C78A8"), ("javascript", "#F2B134")):
        vals = np.array([((conv["condition"] == c) & (conv["language"] == lang)).sum() for c in conditions], float)
        bars = ax.bar(x, vals, bottom=bottoms, color=shade, edgecolor="white", label=lang, width=0.55)
        for bar, v, b0 in zip(bars, vals, bottoms):
            ax.text(bar.get_x() + bar.get_width() / 2, b0 + v / 2, f"{v:.0f}", ha="center", va="center", fontsize=9)
        bottoms += vals
    for xi, tot in zip(x, bottoms):
        ax.text(xi, tot + 1, f"{tot:.0f} conversations", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_xticks(x, [au.LABELS[c] for c in conditions], fontsize=8)
    ax.set_ylim(0, EXPECTED_PER_CONDITION * 1.15)
    ax.set_ylabel("Conversations analysed")
    ax.set_title("Coverage: all 60 conversations per model (10 problems x 3 repeats x 2 languages)", fontsize=9.5)
    ax.legend(frameon=False, loc="lower right")
    done(fig, "fig0_coverage.png")

    # fig1 - compliance (three measures), grouped horizontal bars
    measures = [("structure", "Right turn structure\n(1 question on turns 1-5,\nnone on turn 6)"),
                ("rule_compliance", "Structure + all model-neutral\nformat rules"),
                ("on_time_conclusion", "Concluded exactly\non turn 6")]
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    bh = 0.8 / len(conditions)
    ypos = np.arange(len(measures))[::-1]
    for i, c in enumerate(conditions):
        vals = [h.loc[m, f"{c}_mean"] for m, _ in measures]
        bars = ax.barh(ypos - (i - (len(conditions) - 1) / 2) * bh, vals, bh, color=colors[c], label=au.MODEL_NAMES[c])
        au.annotate_hbars(ax, bars, "pct", fontsize=8)
    ax.set_yticks(ypos, [m[1] for m in measures])
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("Share (turns for the first two measures, conversations for the third; all 60 conversations per model)")
    ax.set_title("Following the controlled prompt")
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.45, -0.16), fontsize=8)
    ax.grid(axis="y", visible=False)
    done(fig, "fig1_rule_compliance.png")

    # fig2 - which turn was the first reply without a question? (100% stacked, "pct (count)")
    cats = [1, 2, 3, 4, 5, 6, "never"]
    shades = plt.cm.Blues(np.linspace(0.25, 0.9, 6)).tolist() + [[0.85, 0.85, 0.85, 1]]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    left = np.zeros(len(conditions))
    ypos = np.arange(len(conditions))[::-1]
    for cat, shade in zip(cats, shades):
        counts = []
        for c in conditions:
            s_ = conv.loc[conv["condition"] == c, "concluded_on_turn"]
            counts.append(int(s_.isna().sum()) if cat == "never" else int((s_ == cat).sum()))
        counts = np.array(counts, float)
        share = counts / n_conv.to_numpy()
        bars = ax.barh(ypos, share, left=left, color=[shade], edgecolor="white", label=f"turn {cat}" if cat != "never" else "never")
        for bar, sh, k, l0 in zip(bars, share, counts, left):
            if k == 0:
                continue
            col = "white" if cat not in ("never", 1, 2) else "black"
            txt = f"{100 * sh:.0f}%\n({k:.0f})" if sh >= 0.045 else f"{k:.0f}"
            ax.text(l0 + sh / 2, bar.get_y() + bar.get_height() / 2, txt, ha="center", va="center",
                    fontsize=7 if sh >= 0.045 else 6.5, color=col)
        left += share
    ax.set_yticks(ypos, [au.LABELS[c] for c in conditions], fontsize=8)
    ax.set_xlim(0, 1)
    ax.grid(axis="y", visible=False)
    ax.set_title("Turn of the first reply with no question (target = turn 6)", fontsize=10)
    ax.set_xlabel("Share of the 60 conversations per model (count in brackets; narrow segments show the count only)")
    ax.legend(ncol=7, bbox_to_anchor=(0, 1.1), loc="lower left", frameon=False, fontsize=8)
    done(fig, "fig2_conclusion_turn.png")

    # fig3 - turn by turn, as two annotated heat maps (models x turns): no overlapping labels
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    tt = list(range(1, EXPECTED + 1))
    panels = [("structure", "Share of conversations whose reply has the right structure", "Greens", 0, 1, "pct"),
              ("word_count", "Mean words per reply", "Purples", 0, None, "1dp")]
    for ax, (col, title, cmap, vmin, vmax, kind) in zip(axes, panels):
        mat = np.array([[turns[(turns["condition"] == c) & (turns["turn"] == t)][col].mean() for t in tt] for c in conditions])
        im = ax.imshow(mat, cmap=cmap, vmin=vmin, vmax=vmax if vmax is not None else float(mat.max()), aspect="auto")
        ax.set_xticks(range(len(tt)), [f"turn {t}" + ("\n(conclude)" if t == EXPECTED else "") for t in tt], fontsize=8)
        ax.set_yticks(range(len(conditions)), [au.LABELS[c] for c in conditions], fontsize=8)
        ax.grid(False)
        ax.set_title(title, fontsize=10)
        top = im.norm.vmax
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat[i, j]
                ax.text(j, i, au.fmt_value(v, kind), ha="center", va="center", fontsize=9,
                        color="white" if v > 0.6 * top else "black")
        fig.colorbar(im, ax=ax, shrink=0.85)
    done(fig, "fig3_turn_by_turn.png")

    # fig4 - rule-break heat map
    brk = [("over_length", "> 3 sentences"), ("has_code_block", "code block"),
           ("agent_new_code", f"new code {DAGGER}"), ("agent_solution_leak", f"solution leak {DAGGER}"),
           ("possible_fix_giving", "fix-giving phrase (heuristic)"), ("repeated_prior_question", "repeated question"),
           ("label_leak", "Hint:/Question: label"), ("n_multi", "2+ questions in one reply")]
    turns = turns.assign(n_multi=(turns["n_question_marks"] > 1).astype(int))
    mat = np.array([[turns.loc[turns["condition"] == c, col].mean() for c in conditions] for col, _ in brk])
    cnt = np.array([[int(turns.loc[turns["condition"] == c, col].sum()) for c in conditions] for col, _ in brk])
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    im = ax.imshow(mat, cmap="Reds", vmin=0, vmax=max(0.5, float(mat.max())), aspect="auto")
    ax.set_xticks(range(len(conditions)), [au.LABELS[c] for c in conditions], fontsize=7.5)
    ax.set_yticks(range(len(brk)), [b[1] for b in brk], fontsize=8)
    ax.grid(False)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{100 * mat[i, j]:.1f}%\n({cnt[i, j]})", ha="center", va="center", fontsize=8,
                    color="white" if mat[i, j] > 0.6 * im.norm.vmax else "black")
    n_turns = int(turns.groupby("condition").size().min())
    fig.colorbar(im, ax=ax, label="Share of tutor turns")
    ax.set_title(f"Rule breaks: % of {n_turns} tutor turns per model (count in brackets)")
    ax.text(0, -0.17, f"{DAGGER} the agent filters its own replies with these detectors, so its ~0 is by construction",
            transform=ax.transAxes, fontsize=7, color="#555555")
    done(fig, "fig4_rule_breaks.png")

    # fig5 - per-problem rule compliance, one panel per language
    wide = items.pivot_table(index=["language", "problem_id"], columns="condition", values="rule_compliance")[conditions]
    names = conv.drop_duplicates(["language", "problem_id"]).set_index(["language", "problem_id"])["problem_name"]
    langs = [lg for lg in ("python", "javascript") if lg in set(wide.index.get_level_values(0))]
    fig, axes = plt.subplots(1, len(langs), figsize=(5.2 * len(langs) + 3, 6), sharey=True)
    axes = np.atleast_1d(axes)
    im = None
    for ax, lang in zip(axes, langs):
        sub = wide.loc[lang]
        im = ax.imshow(sub.to_numpy(), vmin=0, vmax=1, cmap="viridis", aspect="auto")
        ax.set_xticks(range(len(conditions)), [au.LABELS[c].replace("\n", "\n") for c in conditions], fontsize=6.5)
        ax.set_yticks(range(len(sub)), [f"{pid:02d} {names.get((lang, pid), '')}" for pid in sub.index], fontsize=8)
        ax.grid(False)
        ax.set_title({"python": "Python", "javascript": "JavaScript"}.get(lang, lang))
        for i in range(sub.shape[0]):
            for j in range(sub.shape[1]):
                v = sub.iat[i, j]
                ax.text(j, i, "" if np.isnan(v) else f"{v:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if v < 0.6 else "black")
    for ax in axes[1:]:
        ax.tick_params(labelleft=False)
    fig.colorbar(im, ax=list(axes), label="Rule compliance, mean of 3 repeats", shrink=0.8)
    fig.suptitle("Per-problem rule compliance", fontweight="bold")
    fig.text(0.995, 0.006, foot, ha="right", va="bottom", fontsize=6.5, color="#555555")
    fig.savefig(out / "fig5_item_heatmap.png", bbox_inches="tight")
    plt.close(fig)
    made.append("fig5_item_heatmap.png")
    return made


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def fmt_mean(row, c):
    m = row[f"{c}_mean"]
    return "" if np.isnan(m) else f"{m:.2f}"


def write_report(out, notes, conv, turns, headline, tests, bylang, conditions, figs, qt, qtests) -> None:
    counts = conv.groupby("condition").size().reindex(conditions)
    n_turns = turns.groupby("condition").size().reindex(conditions)
    lines = ["# Cross-model evaluation: Code Llama agent, Code Llama (controlled prompt), ChatGPT, Claude", ""]
    lines += ["## 1. Data used", ""]
    lines += [f"- {n}" if not n.startswith("  ") else f"  - {n.strip()}" for n in notes]
    cov = pd.DataFrame({"model": [au.MODEL_NAMES[c] for c in conditions], "conversations": counts.values.astype(int),
                        "tutor turns": n_turns.values.astype(int)})
    lines += ["", au.md_table(cov, "{:.0f}"), ""]
    lines += ["All 60 conversations per model are used; nothing is sampled. No bootstrap or confidence intervals are used. "
              "Every measure has a single definition (no strict/lenient variants): a reply asks a question if and only if it "
              "contains a `?`.", ""]

    lines += ["## 2. Headline measures (mean over all 60 conversations per model)", ""]
    show = pd.DataFrame({"measure": headline["description"],
                         **{au.MODEL_NAMES[c]: headline.apply(lambda r, c=c: fmt_mean(r, c), axis=1) for c in conditions}})
    lines += [au.md_table(show), ""]
    lines += [f"{DAGGER} The agent filters its own replies with these two detectors, so its ~0 is by construction and is not evidence "
              "that it beats the other models; they are excluded from rule compliance and from the paired tests that involve the agent. "
              "The 'JavaScript turns using Python terms' row is averaged over the 30 JavaScript conversations of each model.", "",
              "The Code Llama agent's replies include its canned fallback questions (about a quarter of its replies in the "
              "LeetCode run, see `results/analysis/codellama_leetcode/summary.md`). A well-formed agent conversation is partly "
              "produced by that scaffolding rather than by Code Llama alone.", ""]

    if not tests.empty:
        lines += ["## 3. Paired comparisons (item level)", ""]
        shown = tests[tests["p_wilcoxon"].notna()]
        hidden = tests[tests["p_wilcoxon"].isna()]["description"].unique()
        for title, fam in (("Primary: each Code Llama condition vs each web model", "primary"),
                           ("Secondary: Code Llama agent vs Code Llama (controlled prompt), and ChatGPT vs Claude", "secondary")):
            df = shown[shown["family"] == fam]
            if df.empty:
                continue
            t = pd.DataFrame({"measure": df["description"], "comparison": df["comparison"],
                              "mean diff": df["mean_diff"].map(lambda v: f"{v:+.2f}"), "better is": df["better_is"],
                              "p": df["p_wilcoxon"].map(au.p_fmt), "Holm p": df["p_holm"].map(au.p_fmt)})
            lines += [f"**{title}**", "", au.md_table(t), ""]
        if len(hidden):
            lines += ["Not tested because the two conditions were identical on every item: " + "; ".join(hidden) + ".", ""]
        lines += ["Mean diff is first condition minus second. Each of the 20 items (problem x language) is the mean of its 3 repeats, "
                  "so all 60 conversations per model feed the test; Wilcoxon signed-rank on the 20 paired items; Holm correction "
                  "over all tests in this table. With 20 items, small p-values are exploratory, and many measures are strongly "
                  "correlated (they are not independent findings).", ""]
        sig = tests[(tests["p_holm"] < 0.05) & (tests["better_is"] != "n/a")]
        if not sig.empty:
            lines += ["**Differences surviving Holm correction (auto-generated; check against the figures):**", ""]
            for _, r in sig.iterrows():
                a, b = r["comparison"].split(" - ")
                hi, lo = (a, b) if r["mean_diff"] > 0 else (b, a)
                favours = hi if r["better_is"] == "higher" else lo
                lines.append(f"- {r['description']}: {au.MODEL_NAMES[hi]} > {au.MODEL_NAMES[lo]} "
                             f"(diff {abs(r['mean_diff']):.2f}, Holm p {au.p_fmt(r['p_holm'])}); favours {au.MODEL_NAMES[favours]}.")
            lines.append("")

    lines += ["## 4. Quality of the Socratic questions", ""]
    lines += ["Rule-based proxy (see `evaluation/cross_model/socratic_quality.py`), applied identically to every model. Each question on "
              "turns 1-5 is scored on five criteria (asks for reasoning, grounded in the student's code, does not lead or give the fix, "
              "single focus, not a repeat). Quality score = criteria met (0-5); high quality = all five. Equal weights are a "
              "transparency choice, not a claim that the criteria matter equally. Replies with no `?` have no question to score "
              "and are counted separately.", ""]
    bc = qt["by_condition"]
    qshow = pd.DataFrame({"model": bc["model"], "questions scored": bc["turns_with_a_question"].astype(int),
                          "turns with no question": bc["turns_without_a_question"].astype(int),
                          "mean score (0-5)": bc["mean_quality_score_0_to_5"], "high quality": bc["high_quality_share_of_questions"],
                          "reasoning": bc["reasoning_prompt"], "code-grounded": bc["code_grounded"], "non-leading": bc["non_leading"],
                          "single focus": bc["single_focus"], "not repeated": bc["not_repeated"],
                          "high quality, % of all 300 expected": bc["high_quality_share_of_all_expected_turns"]})
    lines += [au.md_table(qshow), ""]
    tp = qt["types"].pivot(index="condition", columns="question_type", values="share").reindex(conditions)[sq.TYPES]
    tp.insert(0, "model", [au.MODEL_NAMES[c] for c in tp.index])
    lines += ["Share of questions by cognitive type:", "", au.md_table(tp.reset_index(drop=True)), ""]
    if "agent_split" in qt:
        lines += ["Code Llama agent: replies written by the model versus its fixed fallback questions:", "",
                  au.md_table(qt["agent_split"]), ""]
    if not qtests.empty:
        shown = qtests[qtests["p_wilcoxon"].notna()]
        t = pd.DataFrame({"measure": shown["description"], "comparison": shown["comparison"],
                          "mean diff": shown["mean_diff"].map(lambda v: f"{v:+.2f}"), "p": shown["p_wilcoxon"].map(au.p_fmt),
                          "Holm p": shown["p_holm"].map(au.p_fmt)})
        lines += ["Paired comparisons (20 items per model, 3 repeats averaged; Wilcoxon, Holm over this table):", "", au.md_table(t), ""]
    lines += ["Limits: the score checks form, not pedagogical wisdom. A question can pass all five criteria and still be asked at the wrong "
              "moment, and a good question can fail one (for example a conceptual question with no code reference). Validate it with the "
              "blinded manual rating (`blind_rating.py`, column `meaningful_followups`).", ""]
    lines += ["## 5. By language (30 conversations per model per language)", "", au.md_table(bylang), ""]
    lines += ["## 6. Figures (model names and values are written on every chart)", ""] + [f"- `{f}`" for f in figs] + [""]
    lines += ["## 7. What to check by hand before citing any of this", "",
              "1. `review_no_question_replies.csv` - replies on turns 1-5 with no `?` and replies on turn 6 that do contain one. "
              "Some of these are Socratic prompts phrased as instructions (e.g. \"Now pick an edge case and predict ...\"), which this "
              "single `?`-based rule counts as not asking a question. Read them before drawing conclusions about premature conclusions.",
              "2. `review_possible_fix_giving.csv` - a loose regex; expect false positives.",
              "3. Record the collection date for ChatGPT and Claude (not stored in the worksheets); pass it with `--model chatgpt=... --model claude=...`.",
              "4. These measures check rule-following, not teaching quality: use the blind manual rating for the latter.",
              "5. Web apps may add hidden instructions, use different sampling and change model versions, so latency and tokens are not "
              "compared. Code Llama ran with temperature 0.2 and `max_tokens` 300, which can truncate replies (see `truncated_turns` in "
              "`conversation_metrics.csv`).", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local-run", default=str(ROOT / "results" / "cross_model" / "local-main"))
    ap.add_argument("--manual", action="append", metavar="NAME=DIR",
                    help="worksheet folder per web model (default: chatgpt=manual_pack/chatgpt claude=manual_pack/claude)")
    ap.add_argument("--model", action="append", metavar="NAME=LABEL", help="model/version/date label for a --manual condition")
    ap.add_argument("--drop-invalid", action="store_true",
                    help="exclude worksheets with recording ERRORs (the run then stops unless every model still has 60)")
    ap.add_argument("--out", default=str(ROOT / "results" / "analysis" / "cross_model"))
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)
    if not args.manual:
        args.manual = [f"chatgpt={ROOT / 'manual_pack' / 'chatgpt'}", f"claude={ROOT / 'manual_pack' / 'claude'}"]

    records, notes = load_records(args)
    if not records:
        sys.exit("No conversations found.\n" + "\n".join(notes))
    notes += check_complete(records)
    conv, turns = build_frames(records)
    conditions = [c for c in CONDITIONS if c in set(conv["condition"])]
    items = item_table(conv, [h[0] for h in HEADLINE])
    headline = headline_table(conv, conditions)
    tests = pairwise_table(items, conditions)

    by_lang_rows = []
    for lang in sorted(conv["language"].unique()):
        sub = conv[conv["language"] == lang]
        for col, label in (("structure", "right turn structure"), ("rule_compliance", "rule compliance"),
                           ("premature_conclusion", "premature conclusion"), ("mean_words_per_reply", "words per reply")):
            row = {"language": lang, "measure": label}
            for c in conditions:
                row[au.MODEL_NAMES[c]] = sub.loc[sub["condition"] == c, col].mean()
            by_lang_rows.append(row)
    bylang = pd.DataFrame(by_lang_rows)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in list(out.glob("fig*.png")) + list(out.glob("*.csv")):
        stale.unlink()
    conv.to_csv(out / "conversation_metrics.csv", index=False)
    turns.drop(columns=["text"]).to_csv(out / "turn_metrics.csv", index=False)
    headline.to_csv(out / "headline_by_condition.csv", index=False)
    tests.to_csv(out / "pairwise_tests.csv", index=False)
    bylang.to_csv(out / "by_language.csv", index=False)

    review = turns[((turns["turn"] < EXPECTED) & (turns["n_question_marks"] == 0))
                   | ((turns["turn"] == EXPECTED) & (turns["n_question_marks"] > 0))].copy()
    review["what_happened"] = np.where(review["turn"] == EXPECTED, "question on the concluding turn", "no question before turn 6")
    review["YOUR_LABEL"] = ""
    review[["condition", "language", "problem_id", "repeat", "turn", "what_happened", "YOUR_LABEL", "text"]] \
        .to_csv(out / "review_no_question_replies.csv", index=False)
    turns.loc[turns["possible_fix_giving"] == 1, ["condition", "language", "problem_id", "repeat", "turn", "text"]] \
        .to_csv(out / "review_possible_fix_giving.csv", index=False)

    q = quality_frame(records)
    qt = quality_tables(q, conditions)
    qconv = quality_conversation_table(q)
    qtests = quality_tests(qconv, conditions)
    q.drop(columns=["question"]).to_csv(out / "question_quality_per_turn.csv", index=False)
    q[q["has_question"] == 1][["condition", "language", "problem_id", "repeat", "turn", "quality_score", "question_type", "question"]] \
        .to_csv(out / "question_quality_review.csv", index=False)
    qconv.to_csv(out / "question_quality_per_conversation.csv", index=False)
    qt["by_condition"].to_csv(out / "question_quality_by_condition.csv", index=False)
    qt["types"].to_csv(out / "question_types.csv", index=False)
    qt["by_turn"].to_csv(out / "question_quality_by_turn.csv", index=False)
    qtests.to_csv(out / "question_quality_tests.csv", index=False)

    figs = [] if args.no_figures else make_figures(out, conv, turns, items, headline, conditions)
    if not args.no_figures:
        figs += quality_figures(out, q, qt, conditions)
    write_report(out, notes, conv, turns, headline, tests, bylang, conditions, figs, qt, qtests)

    print(f"Wrote analysis to {out}\n")
    for n in notes:
        print(n)
    keys = ["structure", "rule_compliance", "on_time_conclusion", "premature_conclusion", "over_length_turns"]
    show = headline[headline["metric"].isin(keys)]
    print("\nQuestion quality:\n" + au.md_table(qt["by_condition"][["model", "turns_with_a_question", "mean_quality_score_0_to_5",
                                                              "high_quality_share_of_questions"]]))
    print("\n" + au.md_table(pd.DataFrame({"measure": show["description"].str.slice(0, 60),
                                           **{c: show[f"{c}_mean"] for c in conditions}})))


if __name__ == "__main__":
    main()
