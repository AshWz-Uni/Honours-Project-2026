# Cross-model evaluation: Code Llama agent, Code Llama (controlled prompt), ChatGPT, Claude

## 1. Data used

- `results/cross_model/local-main/transcripts.jsonl`: 60 conversations for `codellama_agent` (Code Llama 7B + tutoring agent).
- `results/cross_model/local-main/transcripts.jsonl`: 60 conversations for `codellama_prompt` (Code Llama 7B (controlled prompt)).
- `manual_pack/chatgpt`: 60 conversations loaded as `chatgpt` (ChatGPT (GPT-5.6 Luna)).
- `manual_pack/claude`: 60 conversations loaded as `claude` (Claude (Sonnet 5.5, medium)).
- Coverage check passed: 60 conversations for each of 4 models (10 problems x 2 languages x 3 repeats).

| model | conversations | tutor turns |
|---|---|---|
| Code Llama 7B + tutoring agent | 60 | 360 |
| Code Llama 7B (controlled prompt) | 60 | 360 |
| ChatGPT (GPT-5.6 Luna) | 60 | 360 |
| Claude (Sonnet 5.5, medium) | 60 | 360 |

All 60 conversations per model are used.

## 2. Headline measures (mean over all 60 conversations per model)

| measure | Code Llama 7B + tutoring agent | Code Llama 7B (controlled prompt) | ChatGPT (GPT-5.6 Luna) | Claude (Sonnet 5.5, medium) |
|---|---|---|---|---|
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | 1.00 | 0.66 | 0.89 | 0.89 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | 0.77 | 0.07 | 0.89 | 0.89 |
| Concluded exactly on turn 6 | 1.00 | 0.00 | 0.48 | 0.42 |
| Concluded before turn 6 | 0.00 | 0.08 | 0.37 | 0.42 |
| Never concluded (a question on turn 6 and no earlier conclusion) | 0.00 | 0.92 | 0.15 | 0.17 |
| Turns with 2+ questions (of 6) | 0.00 | 1.10 | 0.00 | 0.02 |
| Turns longer than 3 sentences (of 6) | 1.30 | 1.93 | 0.02 | 0.03 |
| Mean words per reply | 41.42 | 48.86 | 37.06 | 44.06 |
| Turns containing a code block (of 6) | 0.00 | 0.30 | 0.00 | 0.00 |
| Turns introducing new code (of 6) † | 0.00 | 0.02 | 0.08 | 0.07 |
| Turns flagged as leaking the solution (of 6) † | 0.00 | 0.58 | 0.00 | 0.02 |
| Turns with fix-giving phrases (of 6, loose heuristic) | 0.38 | 0.42 | 0.00 | 0.00 |
| Turns repeating an earlier question (of 6) | 0.07 | 1.87 | 0.00 | 0.00 |
| Turns showing Hint:/Question: labels (of 6) | 0.00 | 4.27 | 0.00 | 0.02 |
| JavaScript turns using Python terms (of 6) | 0.00 | 0.00 | 0.00 | 0.00 |
| Turns naming the model/vendor (of 6) | 0.00 | 0.00 | 0.00 | 0.00 |

† The agent filters its own replies with these two detectors, so its ~0 is by construction and is not evidence that it beats the other models; they are excluded from rule compliance and from the paired tests that involve the agent. The 'JavaScript turns using Python terms' row is averaged over the 30 JavaScript conversations of each model.

The Code Llama agent's replies include its canned fallback questions (about a quarter of its replies in the LeetCode run, see `results/analysis/codellama_leetcode/summary.md`). A well-formed agent conversation is partly produced by that scaffolding rather than by Code Llama alone.

## 3. Paired comparisons (item level)

**Primary: each Code Llama condition vs each web model**

| measure | comparison | mean diff | better is | p | Holm p |
|---|---|---|---|---|---|
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | codellama_agent - chatgpt | +0.11 | higher | <0.001 | 0.009 |
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | codellama_agent - claude | +0.11 | higher | <0.001 | 0.007 |
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | codellama_prompt - chatgpt | -0.24 | higher | <0.001 | 0.018 |
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | codellama_prompt - claude | -0.24 | higher | <0.001 | 0.010 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | codellama_agent - chatgpt | -0.12 | higher | 0.004 | 0.138 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | codellama_agent - claude | -0.12 | higher | 0.001 | 0.055 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | codellama_prompt - chatgpt | -0.82 | higher | <0.001 | 0.005 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | codellama_prompt - claude | -0.82 | higher | <0.001 | 0.005 |
| Concluded exactly on turn 6 | codellama_agent - chatgpt | +0.52 | higher | <0.001 | 0.009 |
| Concluded exactly on turn 6 | codellama_agent - claude | +0.58 | higher | <0.001 | 0.007 |
| Concluded exactly on turn 6 | codellama_prompt - chatgpt | -0.48 | higher | <0.001 | 0.011 |
| Concluded exactly on turn 6 | codellama_prompt - claude | -0.42 | higher | <0.001 | 0.015 |
| Concluded before turn 6 | codellama_agent - chatgpt | -0.37 | lower | <0.001 | 0.020 |
| Concluded before turn 6 | codellama_agent - claude | -0.42 | lower | <0.001 | 0.015 |
| Concluded before turn 6 | codellama_prompt - chatgpt | -0.28 | lower | 0.008 | 0.288 |
| Concluded before turn 6 | codellama_prompt - claude | -0.33 | lower | 0.006 | 0.224 |
| Never concluded (a question on turn 6 and no earlier conclusion) | codellama_agent - chatgpt | -0.15 | lower | 0.011 | 0.388 |
| Never concluded (a question on turn 6 and no earlier conclusion) | codellama_agent - claude | -0.17 | lower | 0.007 | 0.240 |
| Never concluded (a question on turn 6 and no earlier conclusion) | codellama_prompt - chatgpt | +0.77 | lower | <0.001 | 0.009 |
| Never concluded (a question on turn 6 and no earlier conclusion) | codellama_prompt - claude | +0.75 | lower | <0.001 | 0.009 |
| Turns with 2+ questions (of 6) | codellama_agent - claude | -0.02 | lower | 0.317 | 1.000 |
| Turns with 2+ questions (of 6) | codellama_prompt - chatgpt | +1.10 | lower | 0.002 | 0.090 |
| Turns with 2+ questions (of 6) | codellama_prompt - claude | +1.08 | lower | 0.002 | 0.090 |
| Turns longer than 3 sentences (of 6) | codellama_agent - chatgpt | +1.28 | lower | <0.001 | 0.009 |
| Turns longer than 3 sentences (of 6) | codellama_agent - claude | +1.27 | lower | <0.001 | 0.008 |
| Turns longer than 3 sentences (of 6) | codellama_prompt - chatgpt | +1.92 | lower | 0.001 | 0.062 |
| Turns longer than 3 sentences (of 6) | codellama_prompt - claude | +1.90 | lower | 0.001 | 0.062 |
| Mean words per reply | codellama_agent - chatgpt | +4.37 | n/a | 0.030 | 0.941 |
| Mean words per reply | codellama_agent - claude | -2.63 | n/a | 0.202 | 1.000 |
| Mean words per reply | codellama_prompt - chatgpt | +11.80 | n/a | 0.105 | 1.000 |
| Mean words per reply | codellama_prompt - claude | +4.81 | n/a | 0.927 | 1.000 |
| Turns containing a code block (of 6) | codellama_prompt - chatgpt | +0.30 | lower | 0.068 | 1.000 |
| Turns containing a code block (of 6) | codellama_prompt - claude | +0.30 | lower | 0.068 | 1.000 |
| Turns introducing new code (of 6) † | codellama_prompt - chatgpt | -0.07 | lower | 0.194 | 1.000 |
| Turns introducing new code (of 6) † | codellama_prompt - claude | -0.05 | lower | 0.257 | 1.000 |
| Turns flagged as leaking the solution (of 6) † | codellama_prompt - chatgpt | +0.58 | lower | 0.011 | 0.388 |
| Turns flagged as leaking the solution (of 6) † | codellama_prompt - claude | +0.57 | lower | 0.012 | 0.388 |
| Turns with fix-giving phrases (of 6, loose heuristic) | codellama_agent - chatgpt | +0.38 | lower | 0.039 | 1.000 |
| Turns with fix-giving phrases (of 6, loose heuristic) | codellama_agent - claude | +0.38 | lower | 0.039 | 1.000 |
| Turns with fix-giving phrases (of 6, loose heuristic) | codellama_prompt - chatgpt | +0.42 | lower | 0.043 | 1.000 |
| Turns with fix-giving phrases (of 6, loose heuristic) | codellama_prompt - claude | +0.42 | lower | 0.043 | 1.000 |
| Turns repeating an earlier question (of 6) | codellama_agent - chatgpt | +0.07 | lower | 0.157 | 1.000 |
| Turns repeating an earlier question (of 6) | codellama_agent - claude | +0.07 | lower | 0.157 | 1.000 |
| Turns repeating an earlier question (of 6) | codellama_prompt - chatgpt | +1.87 | lower | <0.001 | 0.008 |
| Turns repeating an earlier question (of 6) | codellama_prompt - claude | +1.87 | lower | <0.001 | 0.008 |
| Turns showing Hint:/Question: labels (of 6) | codellama_agent - claude | -0.02 | lower | 0.317 | 1.000 |
| Turns showing Hint:/Question: labels (of 6) | codellama_prompt - chatgpt | +4.27 | lower | <0.001 | 0.011 |
| Turns showing Hint:/Question: labels (of 6) | codellama_prompt - claude | +4.25 | lower | <0.001 | 0.010 |

**Secondary: Code Llama agent vs Code Llama (controlled prompt), and ChatGPT vs Claude**

| measure | comparison | mean diff | better is | p | Holm p |
|---|---|---|---|---|---|
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | codellama_agent - codellama_prompt | +0.34 | higher | <0.001 | 0.005 |
| Right turn structure (exactly 1 question on turns 1-5, none on turn 6) | chatgpt - claude | -0.00 | higher | 0.803 | 1.000 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | codellama_agent - codellama_prompt | +0.70 | higher | <0.001 | 0.005 |
| Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats) | chatgpt - claude | +0.01 | higher | 0.897 | 1.000 |
| Concluded exactly on turn 6 | codellama_agent - codellama_prompt | +1.00 | higher | <0.001 | <0.001 |
| Concluded exactly on turn 6 | chatgpt - claude | +0.07 | higher | 0.449 | 1.000 |
| Concluded before turn 6 | codellama_agent - codellama_prompt | -0.08 | lower | 0.102 | 1.000 |
| Concluded before turn 6 | chatgpt - claude | -0.05 | lower | 0.582 | 1.000 |
| Never concluded (a question on turn 6 and no earlier conclusion) | codellama_agent - codellama_prompt | -0.92 | lower | <0.001 | 0.002 |
| Never concluded (a question on turn 6 and no earlier conclusion) | chatgpt - claude | -0.02 | lower | 0.705 | 1.000 |
| Turns with 2+ questions (of 6) | codellama_agent - codellama_prompt | -1.10 | lower | 0.002 | 0.090 |
| Turns with 2+ questions (of 6) | chatgpt - claude | -0.02 | lower | 0.317 | 1.000 |
| Turns longer than 3 sentences (of 6) | codellama_agent - codellama_prompt | -0.63 | lower | 0.264 | 1.000 |
| Turns longer than 3 sentences (of 6) | chatgpt - claude | -0.02 | lower | 0.317 | 1.000 |
| Mean words per reply | codellama_agent - codellama_prompt | -7.44 | n/a | 0.522 | 1.000 |
| Mean words per reply | chatgpt - claude | -7.00 | n/a | <0.001 | <0.001 |
| Turns containing a code block (of 6) | codellama_agent - codellama_prompt | -0.30 | lower | 0.068 | 1.000 |
| Turns introducing new code (of 6) † | chatgpt - claude | +0.02 | lower | 0.748 | 1.000 |
| Turns flagged as leaking the solution (of 6) † | chatgpt - claude | -0.02 | lower | 0.317 | 1.000 |
| Turns with fix-giving phrases (of 6, loose heuristic) | codellama_agent - codellama_prompt | -0.03 | lower | 0.932 | 1.000 |
| Turns repeating an earlier question (of 6) | codellama_agent - codellama_prompt | -1.80 | lower | <0.001 | 0.008 |
| Turns showing Hint:/Question: labels (of 6) | codellama_agent - codellama_prompt | -4.27 | lower | <0.001 | 0.011 |
| Turns showing Hint:/Question: labels (of 6) | chatgpt - claude | -0.02 | lower | 0.317 | 1.000 |

Not tested because the two conditions were identical on every item: Turns with 2+ questions (of 6); Turns containing a code block (of 6); Turns with fix-giving phrases (of 6, loose heuristic); Turns repeating an earlier question (of 6); Turns showing Hint:/Question: labels (of 6); JavaScript turns using Python terms (of 6); Turns naming the model/vendor (of 6).

Mean diff is first condition minus second. Each of the 20 items (problem x language) is the mean of its 3 repeats, so all 60 conversations per model feed the test; Wilcoxon signed-rank on the 20 paired items; Holm correction over all tests in this table. With 20 items, small p-values are exploratory, and many measures are strongly correlated (they are not independent findings).

**Differences surviving Holm correction (auto-generated; check against the figures):**

- Right turn structure (exactly 1 question on turns 1-5, none on turn 6): Code Llama 7B + tutoring agent > ChatGPT (GPT-5.6 Luna) (diff 0.11, Holm p 0.009); favours Code Llama 7B + tutoring agent.
- Right turn structure (exactly 1 question on turns 1-5, none on turn 6): Code Llama 7B + tutoring agent > Claude (Sonnet 5.5, medium) (diff 0.11, Holm p 0.007); favours Code Llama 7B + tutoring agent.
- Right turn structure (exactly 1 question on turns 1-5, none on turn 6): ChatGPT (GPT-5.6 Luna) > Code Llama 7B (controlled prompt) (diff 0.24, Holm p 0.018); favours ChatGPT (GPT-5.6 Luna).
- Right turn structure (exactly 1 question on turns 1-5, none on turn 6): Claude (Sonnet 5.5, medium) > Code Llama 7B (controlled prompt) (diff 0.24, Holm p 0.010); favours Claude (Sonnet 5.5, medium).
- Right turn structure (exactly 1 question on turns 1-5, none on turn 6): Code Llama 7B + tutoring agent > Code Llama 7B (controlled prompt) (diff 0.34, Holm p 0.005); favours Code Llama 7B + tutoring agent.
- Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats): ChatGPT (GPT-5.6 Luna) > Code Llama 7B (controlled prompt) (diff 0.82, Holm p 0.005); favours ChatGPT (GPT-5.6 Luna).
- Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats): Claude (Sonnet 5.5, medium) > Code Llama 7B (controlled prompt) (diff 0.82, Holm p 0.005); favours Claude (Sonnet 5.5, medium).
- Structure AND every model-neutral format rule (<=3 sentences, no code/labels/repeats): Code Llama 7B + tutoring agent > Code Llama 7B (controlled prompt) (diff 0.70, Holm p 0.005); favours Code Llama 7B + tutoring agent.
- Concluded exactly on turn 6: Code Llama 7B + tutoring agent > ChatGPT (GPT-5.6 Luna) (diff 0.52, Holm p 0.009); favours Code Llama 7B + tutoring agent.
- Concluded exactly on turn 6: Code Llama 7B + tutoring agent > Claude (Sonnet 5.5, medium) (diff 0.58, Holm p 0.007); favours Code Llama 7B + tutoring agent.
- Concluded exactly on turn 6: ChatGPT (GPT-5.6 Luna) > Code Llama 7B (controlled prompt) (diff 0.48, Holm p 0.011); favours ChatGPT (GPT-5.6 Luna).
- Concluded exactly on turn 6: Claude (Sonnet 5.5, medium) > Code Llama 7B (controlled prompt) (diff 0.42, Holm p 0.015); favours Claude (Sonnet 5.5, medium).
- Concluded exactly on turn 6: Code Llama 7B + tutoring agent > Code Llama 7B (controlled prompt) (diff 1.00, Holm p <0.001); favours Code Llama 7B + tutoring agent.
- Concluded before turn 6: ChatGPT (GPT-5.6 Luna) > Code Llama 7B + tutoring agent (diff 0.37, Holm p 0.020); favours Code Llama 7B + tutoring agent.
- Concluded before turn 6: Claude (Sonnet 5.5, medium) > Code Llama 7B + tutoring agent (diff 0.42, Holm p 0.015); favours Code Llama 7B + tutoring agent.
- Never concluded (a question on turn 6 and no earlier conclusion): Code Llama 7B (controlled prompt) > ChatGPT (GPT-5.6 Luna) (diff 0.77, Holm p 0.009); favours ChatGPT (GPT-5.6 Luna).
- Never concluded (a question on turn 6 and no earlier conclusion): Code Llama 7B (controlled prompt) > Claude (Sonnet 5.5, medium) (diff 0.75, Holm p 0.009); favours Claude (Sonnet 5.5, medium).
- Never concluded (a question on turn 6 and no earlier conclusion): Code Llama 7B (controlled prompt) > Code Llama 7B + tutoring agent (diff 0.92, Holm p 0.002); favours Code Llama 7B + tutoring agent.
- Turns longer than 3 sentences (of 6): Code Llama 7B + tutoring agent > ChatGPT (GPT-5.6 Luna) (diff 1.28, Holm p 0.009); favours ChatGPT (GPT-5.6 Luna).
- Turns longer than 3 sentences (of 6): Code Llama 7B + tutoring agent > Claude (Sonnet 5.5, medium) (diff 1.27, Holm p 0.008); favours Claude (Sonnet 5.5, medium).
- Turns repeating an earlier question (of 6): Code Llama 7B (controlled prompt) > ChatGPT (GPT-5.6 Luna) (diff 1.87, Holm p 0.008); favours ChatGPT (GPT-5.6 Luna).
- Turns repeating an earlier question (of 6): Code Llama 7B (controlled prompt) > Claude (Sonnet 5.5, medium) (diff 1.87, Holm p 0.008); favours Claude (Sonnet 5.5, medium).
- Turns repeating an earlier question (of 6): Code Llama 7B (controlled prompt) > Code Llama 7B + tutoring agent (diff 1.80, Holm p 0.008); favours Code Llama 7B + tutoring agent.
- Turns showing Hint:/Question: labels (of 6): Code Llama 7B (controlled prompt) > ChatGPT (GPT-5.6 Luna) (diff 4.27, Holm p 0.011); favours ChatGPT (GPT-5.6 Luna).
- Turns showing Hint:/Question: labels (of 6): Code Llama 7B (controlled prompt) > Claude (Sonnet 5.5, medium) (diff 4.25, Holm p 0.010); favours Claude (Sonnet 5.5, medium).
- Turns showing Hint:/Question: labels (of 6): Code Llama 7B (controlled prompt) > Code Llama 7B + tutoring agent (diff 4.27, Holm p 0.011); favours Code Llama 7B + tutoring agent.

## 4. Quality of the Socratic questions

Rule-based proxy (see `evaluation/cross_model/socratic_quality.py`), applied identically to every model. Each question on turns 1-5 is scored on five criteria (asks for reasoning, grounded in the student's code, does not lead or give the fix, single focus, not a repeat). Quality score = criteria met (0-5); high quality = all five. Equal weights are a transparency choice, not a claim that the criteria matter equally. Replies with no `?` have no question to score and are counted separately.

| model | questions scored | turns with no question | mean score (0-5) | high quality | reasoning | code-grounded | non-leading | single focus | not repeated | high quality, % of all 300 expected |
|---|---|---|---|---|---|---|---|---|---|---|
| Code Llama 7B + tutoring agent | 300 | 0 | 3.71 | 0.12 | 0.69 | 0.27 | 0.93 | 1.00 | 0.81 | 0.12 |
| Code Llama 7B (controlled prompt) | 289 | 11 | 3.34 | 0.11 | 0.65 | 0.36 | 0.91 | 0.81 | 0.61 | 0.10 |
| ChatGPT (GPT-5.6 Luna) | 276 | 24 | 4.83 | 0.84 | 0.95 | 0.89 | 1.00 | 1.00 | 1.00 | 0.77 |
| Claude (Sonnet 5.5, medium) | 273 | 27 | 4.65 | 0.71 | 0.84 | 0.82 | 1.00 | 1.00 | 1.00 | 0.65 |

Share of questions by cognitive type:

| model | recall | predict | trace/test | explain | extend/reflect | propose |
|---|---|---|---|---|---|---|
| Code Llama 7B + tutoring agent | 0.20 | 0.02 | 0.05 | 0.40 | 0.23 | 0.11 |
| Code Llama 7B (controlled prompt) | 0.26 | 0.02 | 0.14 | 0.36 | 0.04 | 0.18 |
| ChatGPT (GPT-5.6 Luna) | 0.09 | 0.15 | 0.28 | 0.17 | 0.15 | 0.16 |
| Claude (Sonnet 5.5, medium) | 0.06 | 0.12 | 0.19 | 0.22 | 0.23 | 0.17 |

Code Llama agent: replies written by the model versus its fixed fallback questions:

| source | questions | mean_quality_score | high_quality_share | code_grounded |
|---|---|---|---|---|
| written by Code Llama | 220 | 3.71 | 0.15 | 0.36 |
| canned fallback question | 80 | 3.70 | 0.04 | 0.04 |

Paired comparisons (20 items per model, 3 repeats averaged; Wilcoxon, Holm over this table):

| measure | comparison | mean diff | p | Holm p |
|---|---|---|---|---|
| Mean question quality score (0-5) | codellama_agent - chatgpt | -1.12 | <0.001 | 0.001 |
| Mean question quality score (0-5) | codellama_agent - claude | -0.93 | <0.001 | <0.001 |
| Mean question quality score (0-5) | codellama_prompt - chatgpt | -1.50 | <0.001 | 0.001 |
| Mean question quality score (0-5) | codellama_prompt - claude | -1.31 | <0.001 | <0.001 |
| Mean question quality score (0-5) | codellama_agent - codellama_prompt | +0.38 | 0.008 | 0.033 |
| Mean question quality score (0-5) | chatgpt - claude | +0.19 | 0.005 | 0.024 |
| Share of high-quality questions | codellama_agent - chatgpt | -0.71 | <0.001 | 0.001 |
| Share of high-quality questions | codellama_agent - claude | -0.58 | <0.001 | 0.001 |
| Share of high-quality questions | codellama_prompt - chatgpt | -0.73 | <0.001 | 0.001 |
| Share of high-quality questions | codellama_prompt - claude | -0.60 | <0.001 | 0.001 |
| Share of high-quality questions | codellama_agent - codellama_prompt | +0.02 | 0.569 | 0.569 |
| Share of high-quality questions | chatgpt - claude | +0.13 | 0.009 | 0.033 |
| Variety of question types (distinct types / questions) | codellama_agent - chatgpt | -0.13 | <0.001 | 0.002 |
| Variety of question types (distinct types / questions) | codellama_agent - claude | -0.21 | <0.001 | 0.001 |
| Variety of question types (distinct types / questions) | codellama_prompt - chatgpt | -0.33 | <0.001 | 0.001 |
| Variety of question types (distinct types / questions) | codellama_prompt - claude | -0.42 | <0.001 | 0.001 |
| Variety of question types (distinct types / questions) | codellama_agent - codellama_prompt | +0.20 | <0.001 | 0.003 |
| Variety of question types (distinct types / questions) | chatgpt - claude | -0.09 | 0.011 | 0.033 |

Limits: the score checks form, not pedagogical wisdom. A question can pass all five criteria and still be asked at the wrong moment, and a good question can fail one (for example a conceptual question with no code reference). 

## 5. By language (30 conversations per model per language)

| language | measure | Code Llama 7B + tutoring agent | Code Llama 7B (controlled prompt) | ChatGPT (GPT-5.6 Luna) | Claude (Sonnet 5.5, medium) |
|---|---|---|---|---|---|
| javascript | right turn structure | 1.00 | 0.67 | 0.87 | 0.88 |
| javascript | rule compliance | 0.79 | 0.07 | 0.87 | 0.87 |
| javascript | premature conclusion | 0.00 | 0.17 | 0.37 | 0.47 |
| javascript | words per reply | 39.05 | 56.33 | 37.74 | 44.50 |
| python | right turn structure | 1.00 | 0.64 | 0.92 | 0.91 |
| python | rule compliance | 0.76 | 0.07 | 0.92 | 0.91 |
| python | premature conclusion | 0.00 | 0.00 | 0.37 | 0.37 |
| python | words per reply | 43.80 | 41.40 | 36.37 | 43.61 |

## 6. Figures (model names and values are written on every chart)

- `fig0_coverage.png`
- `fig1_rule_compliance.png`
- `fig2_conclusion_turn.png`
- `fig3_turn_by_turn.png`
- `fig4_rule_breaks.png`
- `fig5_item_heatmap.png`
- `fig6_question_quality_criteria.png`
- `fig7_question_types.png`
- `fig8_question_quality_by_turn.png`

