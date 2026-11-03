"""Shared helpers for the exploration scripts (statistics, extra text proxies, plotting style, bar/line value labels).

Nothing here calls a model or changes any result file.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Consistent colours across every figure (colour-blind-safe Okabe-Ito palette).
PALETTE = {
    "codellama_agent": "#CC79A7",
    "codellama_prompt": "#0072B2",
    "chatgpt": "#009E73",
    "claude": "#D55E00",
}
# Model names
MODEL_NAMES = {
    "codellama_agent": "Code Llama 7B + tutoring agent",
    "codellama_prompt": "Code Llama 7B (controlled prompt)",
    "chatgpt": "ChatGPT (GPT-5.6 Luna)",
    "claude": "Claude (Sonnet 5.5, medium)",
}
LABELS = {
    "codellama_agent": "Code Llama 7B\n+ tutoring agent",
    "codellama_prompt": "Code Llama 7B\n(controlled prompt)",
    "chatgpt": "ChatGPT\n(GPT-5.6 Luna)",
    "claude": "Claude\n(Sonnet 5.5, medium)",
}
ORDER = ["codellama_agent", "codellama_prompt", "chatgpt", "claude"]
FOOTER_CROSS = ("Models: Code Llama = codellama:7b | ChatGPT = GPT-5.6 Luna (web) | Claude = Sonnet 5.5, medium (web)  |  "
                "60 conversations per model")
FOOTER_STEP1 = "Model: Code Llama 7B (codellama:7b) + tutoring agent  |  LeetCode set, 3 runs x 2 languages x 10 problems = 60 conversations"


# --------------------------------------------------------------------------- #
# Text proxy
# --------------------------------------------------------------------------- #
# Phrases where the tutor tells the student what to change (a possible breach of "never give the fix") that the agent's own leak detectors do not look for.
_TELLS_FIX = re.compile(
    r"\byou\s+(?:can|could|should|need\s+to|have\s+to|must|will\s+need\s+to)\s+"
    r"(?:modify|change|add|use|return|replace|update|swap|move|initiali[sz]e|set|store|keep|create|"
    r"define|declare|rewrite|remove|put|call|check\s+(?:if|whether)\s+\w+\s+(?:is|==))\b"
    r"|\b(?:the\s+(?:correct|right|fixed)\s+(?:solution|code|fix)|would\s+be\s+the\s+correct\s+solution)\b",
    re.I,
)
_FENCED = re.compile(r"```.*?```", re.S)


def _plain(text: str) -> str:
    return " ".join(_FENCED.sub(" ", text).split())


def tells_fix(text: str) -> bool:
    return bool(_TELLS_FIX.search(_plain(text)))


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def paired_test(a, b) -> dict:
    """Paired comparison of two equally long vectors (one entry per problem/language item).

    Returns the mean difference (a - b) and a Wilcoxon signed-rank p-value (NaN when every
    difference is exactly zero, where the test is undefined). No bootstrap / confidence
    intervals are computed anywhere in this project's analysis code.
    """
    from scipy import stats

    a, b = np.asarray(a, float), np.asarray(b, float)
    keep = ~(np.isnan(a) | np.isnan(b))
    a, b = a[keep], b[keep]
    d = a - b
    out = {"n_items": int(len(d)), "mean_diff": float(d.mean()) if len(d) else np.nan, "p_wilcoxon": np.nan}
    if len(d) == 0:
        return out
    if np.allclose(d, 0):
        out["p_wilcoxon"] = np.nan  # identical on every item: nothing to test (and kept out of Holm's family)
    else:
        try:
            out["p_wilcoxon"] = float(stats.wilcoxon(a, b, zero_method="wilcox").pvalue)
        except ValueError:
            out["p_wilcoxon"] = np.nan
    return out


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (NaN stays NaN)."""
    p = np.asarray(pvalues, float)
    adj = np.full_like(p, np.nan)
    idx = [i for i in np.argsort(p) if not np.isnan(p[i])]
    running, m = 0.0, len(idx)
    for rank, i in enumerate(idx):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj.tolist()


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
def md_table(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> str:
    """Tiny markdown table writer (avoids depending on `tabulate`)."""
    def cell(v):
        if isinstance(v, (bool, np.bool_)):
            return str(bool(v))
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        if isinstance(v, (float, np.floating)):
            return "" if np.isnan(v) else floatfmt.format(v)
        return str(v)

    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for i in range(len(df)):  # positional access keeps each column's dtype (iterrows would upcast ints to floats)
        lines.append("| " + " | ".join(cell(df.iat[i, j]) for j in range(len(cols))) + " |")
    return "\n".join(lines)


def p_fmt(p: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def fmt_value(v, kind: str = "auto") -> str:
    """Compact label for a plotted value: 0.87 -> '0.87', 0.87 as share -> '87%', 41.4 -> '41.4'."""
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return ""
    if kind == "pct":
        return f"{100 * v:.0f}%"
    if kind == "int":
        return f"{v:.0f}"
    if kind == "1dp":
        return f"{v:.1f}"
    if kind == "2dp":
        return f"{v:.2f}"
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"


def annotate_bars(ax, bars, kind: str = "auto", fontsize: int = 7, pad: float = 2, rotation: int = 0) -> None:
    """Write each bar's value just above it (vertical bars)."""
    for b in bars:
        h = b.get_height()
        if h is None or np.isnan(h):
            continue
        ax.annotate(fmt_value(h, kind), (b.get_x() + b.get_width() / 2, b.get_y() + h), xytext=(0, pad),
                    textcoords="offset points", ha="center", va="bottom", fontsize=fontsize, rotation=rotation)


def annotate_hbars(ax, bars, kind: str = "auto", fontsize: int = 7, pad: float = 3) -> None:
    """Write each bar's value just beyond its end (horizontal bars)."""
    for b in bars:
        w = b.get_width()
        if w is None or np.isnan(w):
            continue
        ax.annotate(fmt_value(w, kind), (b.get_x() + w, b.get_y() + b.get_height() / 2), xytext=(pad, 0),
                    textcoords="offset points", ha="left", va="center", fontsize=fontsize)


def annotate_line(ax, xs, ys, kind: str = "auto", fontsize: int = 7, color: str = "black", dy: float = 5, dx: float = 0) -> None:
    """Label every point of a line plot (white halo so labels stay legible over lines/gridlines)."""
    for x, y in zip(xs, ys):
        if y is None or (isinstance(y, (float, np.floating)) and np.isnan(y)):
            continue
        ax.annotate(fmt_value(y, kind), (x, y), xytext=(dx, dy), textcoords="offset points",
                    ha="center", va="bottom", fontsize=fontsize, color=color,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75))


def setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.dpi": 130, "savefig.dpi": 160, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True, "font.size": 10,
        "axes.titlesize": 11, "axes.titleweight": "bold",
    })
    return plt


def save(fig, path, footer: str | None = None) -> None:
    """Save a figure with a small footer naming the model(s) and the data size."""
    if footer:
        fig.tight_layout(rect=(0, 0.035, 1, 1))
        fig.text(0.995, 0.006, footer, ha="right", va="bottom", fontsize=6.5, color="#555555")
    fig.savefig(path)
