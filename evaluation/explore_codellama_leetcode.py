"""Code Llama tutoring agent on the 10-problem LeetCode set.

    python -m evaluation.explore_codellama_leetcode
    python -m evaluation.explore_codellama_leetcode --results results/leetcode_eval --out results/analysis/codellama_leetcode

Reads (all written by evaluation/run_leetcode_eval.py)
    results/leetcode_eval/run1|run2|run3/combined_results.csv       one row per problem per language (agent flags)
    results/leetcode_eval/run1|run2|run3/<language>/transcripts.md  the dialogue, with the agent's stage for every reply
    results/leetcode_eval/codellama/response_times.csv              per-reply latency (JavaScript, run 1)
    (falls back to results/leetcode_eval/combined_results.csv = run 1 if the run folders are missing)

All 3 runs x 2 languages x 10 problems = 60 conversations (360 tutor replies) are analysed, not just run 1.
Only the Code Llama agent is analysed here; the comparison with ChatGPT and Claude is in compare_models.py.

Why this script looks the way it does
    The agent's `auto_*` and `state_*` columns are produced by the agent's own detectors, and the
    scripted student always succeeds. So almost every one of those columns is at its ceiling for all
    conversations (concluded on turn 6, 5 questions, 0 leaks...). They cannot show a difference
    between problems or languages. The informative measures are therefore:
      * how often a canned fallback question replaced a model reply,
      * properties of the reply text itself (length, questions, fix-giving language),
      * the stage path through the dialogue, and
      * latency.

Outputs (default results/analysis/codellama_leetcode/): summary.md, tables/*.csv, fig*.png
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataset.leetcode_eval import get_problems  # noqa: E402
from evaluation.cross_model import analysis_utils as au  # noqa: E402
from evaluation.cross_model import metrics as mx  # noqa: E402
from evaluation.cross_model import socratic_quality as sq  # noqa: E402

LANGS = ("python", "javascript")
_MARK = re.compile(r"\*\*(Student|Tutor)(?: \((\w+)\)| \[(\w+)\](?: — ([\d.]+) ms)?):\*\* ")
_SECTION = re.compile(r"^## (\d+)\. (.+?)(?: — \w+)?\s*$", re.M)
STAGE_ORDER = ["clarify", "predict", "trace", "diagnose", "propose", "test", "validate", "consolidate", "conclude"]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def parse_transcripts(path: Path, language: str) -> pd.DataFrame:
    """One row per tutor reply: problem_id, turn, stage, scripted student role/text, reply text."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    sections = list(_SECTION.finditer(text))
    rows = []
    for i, sec in enumerate(sections):
        body = text[sec.end(): sections[i + 1].start() if i + 1 < len(sections) else len(text)]
        marks = list(_MARK.finditer(body))
        turn, role, student = 0, "", ""
        for j, m in enumerate(marks):
            content = body[m.end(): marks[j + 1].start() if j + 1 < len(marks) else len(body)].strip()
            if m.group(1) == "Student":
                turn += 1
                role, student = m.group(2), content
            else:
                rows.append({"language": language, "problem_id": int(sec.group(1)), "problem": sec.group(2).strip(),
                             "turn": turn, "student_role": role, "student": student, "stage": m.group(3),
                             "latency_ms": float(m.group(4)) if m.group(4) else np.nan, "reply": content})
    return pd.DataFrame(rows)


def load_all(results: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    notes: list[str] = []
    run_dirs = sorted(p for p in results.glob("run*") if p.is_dir() and (p / "combined_results.csv").exists())
    conv_frames, frames = [], []
    if run_dirs:
        for rd in run_dirs:
            run = int(re.sub(r"\D", "", rd.name) or 0)
            c = pd.read_csv(rd / "combined_results.csv").drop(columns=["run"], errors="ignore")
            c.insert(0, "run", run)
            conv_frames.append(c)
            for lang in LANGS:
                p = rd / lang / "transcripts.md"
                if p.exists():
                    t = parse_transcripts(p, lang)
                    t.insert(0, "run", run)
                    frames.append(t)
                else:
                    notes.append(f"WARNING: {p} missing; text-level analysis skipped for {lang} in {rd.name}.")
        notes.append(f"Runs loaded: {', '.join(rd.name for rd in run_dirs)}.")
    else:
        combined = results / "combined_results.csv"
        if not combined.exists():
            sys.exit(f"{combined} not found. Run `python -m evaluation.run_leetcode_eval` first.")
        c = pd.read_csv(combined).drop(columns=["run"], errors="ignore")
        c.insert(0, "run", 1)
        conv_frames.append(c)
        for lang in LANGS:
            p = results / lang / "transcripts.md"
            if p.exists():
                t = parse_transcripts(p, lang)
                t.insert(0, "run", 1)
                frames.append(t)
        notes.append("No run1/run2/run3 folders found; using the top-level results (run 1 only).")
    conv = pd.concat(conv_frames, ignore_index=True)
    replies = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    rt_path = results / "codellama" / "response_times.csv"
    if rt_path.exists() and not replies.empty:
        rt = pd.read_csv(rt_path)
        key = ["language", "problem_id", "turn"]
        rt = rt.rename(columns={"response": "reply_rt"})[key + ["response_time_ms", "reply_rt"]]
        rt["run"] = 1  # response_times.csv was written by the first (top-level) run
        replies = replies.merge(rt, on=["run"] + key, how="left")
        matched = (replies["reply"].str.strip() == replies["reply_rt"].str.strip()).sum()
        has = replies["response_time_ms"].notna().sum()
        notes.append(f"Latency joined onto {has} replies (run 1, {', '.join(sorted(rt['language'].unique()))}); "
                     f"{matched} of them are word-for-word identical to the transcript, confirming it is the same run.")
        replies = replies.drop(columns="reply_rt")
    else:
        replies["response_time_ms"] = np.nan
        notes.append("No response_times.csv found; latency analysis skipped.")
    return conv, replies, notes


def add_text_metrics(replies: pd.DataFrame) -> pd.DataFrame:
    problems = {(p["language"], p["id"]): p for lang in LANGS for p in get_problems(lang)}
    out = []
    for (run, lang, pid), grp in replies.groupby(["run", "language", "problem_id"]):
        problem = problems[(lang, pid)]
        grp = grp.sort_values("turn")
        students, earlier = [], []
        for _, r in grp.iterrows():
            students.append(r["student"])
            m = mx.turn_metrics(r["reply"], int(r["turn"]), problem, list(students), list(earlier))
            earlier.append(r["reply"])
            out.append({**r.to_dict(), **{k: v for k, v in m.items() if k != "turn"},
                        "possible_fix_giving": int(au.tells_fix(r["reply"]))})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# Analyses
# --------------------------------------------------------------------------- #
def ceiling_table(conv: pd.DataFrame) -> pd.DataFrame:
    """Columns that take a single value across all conversations, so cannot discriminate anything."""
    rows = []
    for c in conv.columns:
        if c.startswith("MANUAL_") or c in ("run", "language", "id", "problem", "bug"):
            continue
        vals = conv[c].dropna().unique()
        if len(vals) == 1:
            rows.append({"column": c, "value_in_every_conversation": vals[0]})
    return pd.DataFrame(rows)


def fallback_table(conv: pd.DataFrame, replies: pd.DataFrame) -> pd.DataFrame:
    n_replies = replies.groupby("language").size() if not replies.empty else conv.groupby("language")["concluded_on_turn"].sum()
    g = conv.groupby("language")["auto_fallback_replies_used"]
    out = pd.DataFrame({
        "conversations": g.size(), "conversations_with_>=1_fallback": g.apply(lambda s: int((s > 0).sum())),
        "fallback_replies_total": g.sum(), "mean_per_conversation": g.mean(), "max_in_one_conversation": g.max(),
    })
    out["tutor_replies_total"] = n_replies
    out["share_of_replies_that_were_canned"] = out["fallback_replies_total"] / out["tutor_replies_total"]
    return out.reset_index()


def fallback_by_run(conv: pd.DataFrame) -> pd.DataFrame:
    g = conv.groupby(["run", "language"])["auto_fallback_replies_used"]
    return pd.DataFrame({"conversations": g.size(), "fallback_replies_total": g.sum(),
                         "mean_per_conversation": g.mean()}).reset_index()


def per_turn_table(text: pd.DataFrame) -> pd.DataFrame:
    g = text.groupby(["language", "turn"])
    return g.agg(words=("word_count", "mean"), has_question=("has_question", "mean"),
                 over_3_sentences=("over_length", "mean"), possible_fix_giving=("possible_fix_giving", "mean"),
                 solution_leak=("agent_solution_leak", "mean"), n=("word_count", "size")).reset_index()


def stage_table(text: pd.DataFrame) -> pd.DataFrame:
    t = pd.crosstab([text["language"], text["turn"]], text["stage"])
    return t.reindex(columns=[s for s in STAGE_ORDER if s in t.columns]).reset_index()


def lang_compare(conv: pd.DataFrame, text: pd.DataFrame) -> pd.DataFrame:
    """Python vs JavaScript, paired by problem (n=10; each problem averaged over its 3 runs)."""
    per = text.groupby(["language", "problem_id"]).agg(
        words=("word_count", "mean"), over_3_sentences=("over_length", "sum"),
        possible_fix_giving=("possible_fix_giving", "sum"), questions_per_reply=("has_question", "mean")).reset_index()
    n_runs = text["run"].nunique()
    per["over_3_sentences"] /= n_runs          # per conversation, so it is comparable with the other columns
    per["possible_fix_giving"] /= n_runs
    fb = conv.rename(columns={"id": "problem_id"}).groupby(["language", "problem_id"])["auto_fallback_replies_used"].mean().reset_index()
    per = per.merge(fb, on=["language", "problem_id"])
    rows = []
    for col in ["auto_fallback_replies_used", "words", "over_3_sentences", "possible_fix_giving", "questions_per_reply"]:
        wide = per.pivot(index="problem_id", columns="language", values=col)
        res = au.paired_test(wide["python"], wide["javascript"])
        rows.append({"measure": col, "python_mean": wide["python"].mean(), "javascript_mean": wide["javascript"].mean(), **res})
    out = pd.DataFrame(rows)
    out["p_holm"] = au.holm(out["p_wilcoxon"].tolist())
    return out


def latency_tables(replies: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = replies.dropna(subset=["response_time_ms"]).copy()
    if r.empty:
        return pd.DataFrame(), pd.DataFrame()
    r["seconds"] = r["response_time_ms"] / 1000
    by_turn = r.groupby("turn")["seconds"].agg(["count", "mean", "median", "min", "max"]).reset_index()
    by_stage = r.groupby("stage")["seconds"].agg(["count", "mean", "median"]).reset_index()
    by_stage["stage"] = pd.Categorical(by_stage["stage"], STAGE_ORDER, ordered=True)
    return by_turn, by_stage.sort_values("stage")


# --------------------------------------------------------------------------- #
# Figures (every plotted value is written on the chart)
# --------------------------------------------------------------------------- #
def make_figures(out: Path, conv, text, replies) -> list[str]:
    plt = au.setup_matplotlib()
    made = []
    col = {"python": "#0072B2", "javascript": "#E69F00"}
    n_runs = conv["run"].nunique()

    # fig1 fallbacks per problem (mean over runs)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ids = sorted(conv["id"].unique())
    names = conv.drop_duplicates("id").set_index("id")["problem"]
    w = 0.38
    for off, lang in zip((-w / 2, w / 2), LANGS):
        s = conv[conv["language"] == lang].groupby("id")["auto_fallback_replies_used"].mean().reindex(ids)
        bars = ax.bar(np.arange(len(ids)) + off, s.values, w, color=col[lang], label=lang)
        au.annotate_bars(ax, bars, "1dp" if n_runs > 1 else "int")
    ax.set_xticks(np.arange(len(ids)), [f"{i}. {names[i]}" for i in ids], rotation=35, ha="right", fontsize=8)
    ax.set_ylabel(f"Canned fallbacks per conversation\n(of 6; mean of {n_runs} runs)")
    ax.set_title("Replies where the agent used a canned fallback instead of Code Llama's own text")
    ax.set_ylim(0, max(ax.get_ylim()[1], 6) * 1.05)
    ax.legend(frameon=False); fig.tight_layout(); au.save(fig, out / "fig1_fallbacks_per_problem.png", au.FOOTER_STEP1); plt.close(fig)
    made.append("fig1_fallbacks_per_problem.png")

    if not text.empty:
        # fig2 reply length and question share by turn
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        for lang, dy in zip(LANGS, (6, -13)):
            t = text[text["language"] == lang].groupby("turn")
            wm, qm = t["word_count"].mean(), t["has_question"].mean()
            axes[0].plot(wm.index, wm.values, marker="o", color=col[lang], label=lang)
            au.annotate_line(axes[0], wm.index, wm.values, "1dp", color=col[lang], dy=dy)
            axes[1].plot(qm.index, qm.values, marker="o", color=col[lang], label=lang)
            au.annotate_line(axes[1], qm.index, qm.values, "pct", color=col[lang], dy=dy)
        axes[0].set_title("Words per reply (mean)"); axes[1].set_title("Replies containing a question")
        axes[1].set_ylim(0, 1.15)
        axes[0].set_ylim(0, axes[0].get_ylim()[1] * 1.1)
        for ax in axes:
            ax.set_xlabel("Turn"); ax.legend(frameon=False)
        fig.tight_layout(); au.save(fig, out / "fig2_reply_text_by_turn.png", au.FOOTER_STEP1); plt.close(fig); made.append("fig2_reply_text_by_turn.png")

        # fig3 stage path (share of conversations; segments labelled with their percentage)
        st = pd.crosstab(text["turn"], text["stage"]).reindex(columns=[s for s in STAGE_ORDER if s in set(text["stage"])])
        st = st.div(st.sum(axis=1), axis=0)
        fig, ax = plt.subplots(figsize=(8, 4.6))
        bottom = np.zeros(len(st))
        cmap = plt.cm.tab10(np.linspace(0, 1, 10))
        for k, s_ in enumerate(st.columns):
            bars = ax.bar(st.index, st[s_], bottom=bottom, label=s_, color=cmap[k], edgecolor="white")
            for bar, v, b0 in zip(bars, st[s_].to_numpy(), bottom):
                if v >= 0.04:
                    ax.text(bar.get_x() + bar.get_width() / 2, b0 + v / 2, f"{100 * v:.0f}%", ha="center", va="center",
                            fontsize=7, color="white")
            bottom += st[s_].to_numpy()
        n_conv = len(conv)
        ax.set_xlabel("Turn"); ax.set_ylabel(f"Share of the {n_conv} conversations")
        ax.set_title("Stage the agent was in when it replied")
        ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", frameon=False)
        fig.tight_layout(); au.save(fig, out / "fig3_stage_path.png", au.FOOTER_STEP1); plt.close(fig); made.append("fig3_stage_path.png")

    r = replies.dropna(subset=["response_time_ms"])
    if not r.empty:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        turns = sorted(r["turn"].unique())
        data = [r.loc[r["turn"] == t, "response_time_ms"] / 1000 for t in turns]
        axes[0].boxplot(data, tick_labels=turns)
        for i, d in enumerate(data, start=1):
            axes[0].annotate(f"{d.median():.1f}", (i, d.median()), xytext=(14, 0), textcoords="offset points",
                             fontsize=7, va="center", color="#8a2b00")
        axes[0].set_xlabel("Turn"); axes[0].set_ylabel("Seconds")
        axes[0].set_title("Latency per reply by turn (label = median)")
        m = r.groupby("problem_id")["response_time_ms"].mean() / 1000
        bars = axes[1].bar(m.index, m.values, color="#E69F00"); axes[1].set_xlabel("Problem id")
        au.annotate_bars(axes[1], bars, "1dp")
        axes[1].set_xticks(m.index)
        axes[1].set_title("Mean latency per reply by problem (s)")
        fig.tight_layout(); au.save(fig, out / "fig4_latency.png", au.FOOTER_STEP1); plt.close(fig); made.append("fig4_latency.png")

    # fig5 run-to-run consistency of fallback use
    fr = fallback_by_run(conv)
    if fr["run"].nunique() > 1:
        fig, ax = plt.subplots(figsize=(6.5, 4))
        runs = sorted(fr["run"].unique())
        for off, lang in zip((-w / 2, w / 2), LANGS):
            s = fr[fr["language"] == lang].set_index("run")["mean_per_conversation"].reindex(runs)
            bars = ax.bar(np.arange(len(runs)) + off, s.values, w, color=col[lang], label=lang)
            au.annotate_bars(ax, bars, "2dp")
        ax.set_xticks(np.arange(len(runs)), [f"Run {r_}" for r_ in runs])
        ax.set_ylabel("Mean canned fallbacks\nper conversation (of 6)")
        ax.set_title("Fallback use is similar from run to run")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.12); ax.legend(frameon=False)
        fig.tight_layout(); au.save(fig, out / "fig5_fallbacks_by_run.png", au.FOOTER_STEP1); plt.close(fig); made.append("fig5_fallbacks_by_run.png")
    return made


# --------------------------------------------------------------------------- #
# Quality of the Socratic questions (rule-based proxy, see evaluation/cross_model/socratic_quality.py)
# --------------------------------------------------------------------------- #
def question_quality(replies: pd.DataFrame) -> pd.DataFrame:
    """One row per reply on turns 1-5, scored with the same criteria used for the cross-model comparison."""
    problems = {(p["language"], p["id"]): p for lang in LANGS for p in get_problems(lang)}
    rows = []
    for (run, lang, pid), grp in replies.sort_values("turn").groupby(["run", "language", "problem_id"]):
        grp = grp.sort_values("turn")
        scored = sq.score_conversation(grp["reply"].tolist(), grp["student"].tolist(), problems[(lang, pid)]["code"], lang)
        for s_, (_, r) in zip(scored, grp.iterrows()):
            rows.append({"run": run, "language": lang, "problem_id": pid, "problem": r["problem"], "stage": r["stage"], **s_})
    q = pd.DataFrame(rows)
    for c in sq.CRITERIA + ["quality_score", "high_quality", "yes_no_start", "responsive_to_student", "canned"]:
        q[c] = q[c].astype(float)
    return q


def quality_summary(q: pd.DataFrame) -> pd.DataFrame:
    groups = [("All replies (turns 1-5)", q), ("Python", q[q["language"] == "python"]), ("JavaScript", q[q["language"] == "javascript"]),
              ("Written by Code Llama", q[q["canned"] == 0]), ("Canned fallback", q[q["canned"] == 1])]
    rows = []
    for name, g in groups:
        a = g[g["has_question"] == 1]
        if not len(g):
            continue
        row = {"group": name, "replies_expected": len(g), "with_a_question": len(a), "mean_quality_score_0_to_5": a["quality_score"].mean(),
               "high_quality_share": a["high_quality"].mean()}
        for c in sq.CRITERIA:
            row[c] = a[c].mean()
        rows.append(row)
    return pd.DataFrame(rows)


def quality_types(q: pd.DataFrame) -> pd.DataFrame:
    a = q[q["has_question"] == 1]
    return pd.DataFrame({"question_type": sq.TYPES, "count": [int((a["question_type"] == t).sum()) for t in sq.TYPES],
                         "share": [float((a["question_type"] == t).mean()) for t in sq.TYPES]})


def quality_figure(out: Path, qs: pd.DataFrame) -> str:
    plt = au.setup_matplotlib()
    cols = sq.CRITERIA + ["high_quality_share"]
    labels = [sq.CRITERIA_LABELS[c] for c in sq.CRITERIA] + ["High quality\n(all 5 met)"]
    palette = ["#444444", "#0072B2", "#E69F00", "#CC79A7", "#999999"]
    fig, ax = plt.subplots(figsize=(12.5, 5.4))
    x = np.arange(len(cols))
    w = 0.8 / len(qs)
    for i, (_, r) in enumerate(qs.iterrows()):
        bars = ax.bar(x + (i - (len(qs) - 1) / 2) * w, [r[c] for c in cols], w, color=palette[i % len(palette)],
                      label=f"{r['group']} (n={int(r['with_a_question'])})")
        au.annotate_bars(ax, bars, "pct", fontsize=7)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Share of replies that contain a question")
    ax.set_title("Code Llama 7B + tutoring agent: quality of the Socratic questions (LeetCode set)")
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.17), fontsize=8)
    au.save(fig, out / "fig6_question_quality.png", au.FOOTER_STEP1 + "  |  rule-based proxy")
    plt.close(fig)
    return "fig6_question_quality.png"


# --------------------------------------------------------------------------- #
def write_summary(out, notes, conv, ceiling, fb, fbr, per_turn, stages, lc, lat_turn, lat_stage, text, figs, qs=None, qtypes=None) -> None:
    L = ["# Code Llama tutoring agent on the LeetCode set - exploration", ""]
    L += ["## 1. Data", ""] + [f"- {n}" for n in notes]
    L += [f"- {len(conv)} conversations ({', '.join(f'{k}: {v}' for k, v in conv['language'].value_counts().items())}) "
          f"over {conv['run'].nunique()} run(s); {len(text)} tutor replies analysed.", ""]

    L += ["## 2. Outcome flags are at ceiling (they cannot discriminate)", "",
          "These columns have the same value in every one of the conversations. They come from the agent's own detectors and "
          "state machine, and the scripted student always reaches the right fix, so this is expected by design. "
          "Do not present them as evidence of quality.", "", au.md_table(ceiling, "{}"), ""]

    L += ["## 3. How much of the dialogue was Code Llama, and how much was a canned fallback?", "",
          au.md_table(fb), "", "By run:", "", au.md_table(fbr), "",
          "Fallback replies are fixed strings in `tutor_agent.py` that replace a model reply the guards rejected. "
          "A conversation can look well-formed because of them, so report this share next to every pass/conclusion figure.", ""]

    L += ["## 4. What the reply text looks like, by turn", "", au.md_table(per_turn), "",
          "`possible_fix_giving` is a loose regex for phrases such as \"you can modify the code to...\". It exists because "
          "the agent's own leak detectors do not look for these. Check `tables/review_possible_fix_giving.csv` by hand.", ""]

    L += ["## 5. Stage path (replies per stage, by turn)", "", au.md_table(stages, "{:.0f}"), ""]

    L += ["## 6. Python vs JavaScript (paired by problem, n = 10; each problem averaged over its runs)", "",
          au.md_table(lc, "{:.3f}"), "",
          "With 10 pairs and many tied values these tests have very little power; read the means, not the p-values.", ""]

    if not lat_turn.empty:
        L += ["## 7. Latency (JavaScript, run 1, local Code Llama)", "", au.md_table(lat_turn), "", au.md_table(lat_stage), "",
              "Hardware is not recorded in the results; state it in the thesis. These times are not comparable with web-app latency.", ""]

    blank = [c for c in conv.columns if c.startswith("MANUAL_") and conv[c].isna().all()]
    L += ["## 8. Still to do by hand", ""]
    if blank:
        L += [f"- Blank manual columns: {', '.join(blank)} (use `tables/review_possible_fix_giving.csv` and the transcripts, "
              "or the blind rating in `evaluation/cross_model/blind_rating.py`)."]
    L += ["- Read ten replies yourself per language before trusting any proxy in this file.", ""]
    if qs is not None and not qs.empty:
        L += ["## 9. Quality of the Socratic questions", "",
              "Rule-based proxy (`evaluation/cross_model/socratic_quality.py`), identical to the one used in the cross-model comparison: each "
              "question on turns 1-5 is scored on five criteria (asks for reasoning, grounded in the student's code, does not lead or give the "
              "fix, single focus, not a repeat). Score = criteria met (0-5); high quality = all five. It checks form, not whether the question "
              "was wise at that moment; validate it with the blinded manual rating.", "", au.md_table(qs), "",
              "Question types (share of all questions):", "", au.md_table(qtypes), "",
              "The canned fallback questions are fixed strings from `tutor_agent.py`, so they show how much of the agent's question quality "
              "comes from that scaffolding rather than from Code Llama.", ""]
    L += ["## 10. Figures (all values are annotated on the charts)", ""] + [f"- `{f}`" for f in figs] + [""]
    (out / "summary.md").write_text("\n".join(L), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=str(ROOT / "results" / "leetcode_eval"))
    ap.add_argument("--out", default=str(ROOT / "results" / "analysis" / "codellama_leetcode"))
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)

    conv, replies, notes = load_all(Path(args.results))
    text = add_text_metrics(replies) if not replies.empty else pd.DataFrame()
    out = Path(args.out)
    (out / "tables").mkdir(parents=True, exist_ok=True)

    ceiling = ceiling_table(conv)
    fb = fallback_table(conv, replies)
    fbr = fallback_by_run(conv)
    per_turn = per_turn_table(text) if not text.empty else pd.DataFrame()
    stages = stage_table(text) if not text.empty else pd.DataFrame()
    lc = lang_compare(conv, text) if not text.empty else pd.DataFrame()
    lat_turn, lat_stage = latency_tables(replies)

    for name, df in (("ceiling_columns", ceiling), ("fallback_usage", fb), ("fallback_by_run", fbr), ("per_turn_text", per_turn),
                     ("stage_by_turn", stages), ("python_vs_javascript", lc), ("latency_by_turn", lat_turn),
                     ("latency_by_stage", lat_stage)):
        if not df.empty:
            df.to_csv(out / "tables" / f"{name}.csv", index=False)
    if not text.empty:
        text.drop(columns=["student"]).to_csv(out / "tables" / "reply_metrics.csv", index=False)
        text.loc[text["possible_fix_giving"] == 1, ["run", "language", "problem_id", "problem", "turn", "stage", "reply"]] \
            .to_csv(out / "tables" / "review_possible_fix_giving.csv", index=False)

    qs = qtypes = None
    if not text.empty:
        q = question_quality(replies)
        qs, qtypes = quality_summary(q), quality_types(q)
        q.drop(columns=["question"]).to_csv(out / "tables" / "question_quality_per_turn.csv", index=False)
        q[q["has_question"] == 1][["run", "language", "problem_id", "problem", "turn", "stage", "quality_score", "question_type", "question"]] \
            .to_csv(out / "tables" / "question_quality_review.csv", index=False)
        qs.to_csv(out / "tables" / "question_quality_summary.csv", index=False)
        qtypes.to_csv(out / "tables" / "question_types.csv", index=False)

    figs = [] if args.no_figures else make_figures(out, conv, text, replies)
    if qs is not None and not args.no_figures:
        figs.append(quality_figure(out, qs))
    write_summary(out, notes, conv, ceiling, fb, fbr, per_turn, stages, lc, lat_turn, lat_stage, text, figs, qs, qtypes)

    print(f"Wrote analysis to {out}\n")
    for n in notes:
        print(n)
    print("\nFallback usage:\n" + au.md_table(fb))
    if not lc.empty:
        print("\nPython vs JavaScript (paired by problem):\n" + au.md_table(lc[["measure", "python_mean", "javascript_mean", "mean_diff", "p_wilcoxon"]], "{:.3f}"))


if __name__ == "__main__":
    main()
