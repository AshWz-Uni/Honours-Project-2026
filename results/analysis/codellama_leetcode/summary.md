# Code Llama tutoring agent on the LeetCode set

## 1. Data

- Runs loaded: run1, run2, run3.
- Latency joined onto 60 replies (run 1, javascript); 60 of them are word-for-word identical to the transcript, confirming it is the same run.
- 60 conversations (python: 30, javascript: 30) over 3 run(s); 360 tutor replies analysed.

## 2. Outcome flags are at ceiling (they cannot discriminate)

These columns have the same value in every one of the conversations. They come from the agent's own detectors and state machine, and the scripted student always reaches the right fix, so this is expected by design. Do not present them as evidence of quality.

| column | value_in_every_conversation |
|---|---|
| tutor_questions | 5 |
| auto_repeated_question | False |
| auto_language_detected_correctly | True |
| auto_solution_leak_flags | 0 |
| auto_reasked_diagnosis | 0 |
| auto_left_diagnosis_after_first_reply | True |
| auto_markers_visible | False |
| auto_off_topic_recursion | False |
| concluded | True |
| concluded_on_turn | 6 |
| state_problem_identified | True |
| state_solution_proposed | True |
| state_solution_correct | True |
| state_solution_validated | True |

## 3. How much of the dialogue was Code Llama, and how much was a canned fallback?

| language | conversations | conversations_with_>=1_fallback | fallback_replies_total | mean_per_conversation | max_in_one_conversation | tutor_replies_total | share_of_replies_that_were_canned |
|---|---|---|---|---|---|---|---|
| javascript | 30 | 27 | 45 | 1.50 | 3 | 180 | 0.25 |
| python | 30 | 26 | 44 | 1.47 | 3 | 180 | 0.24 |

By run:

| run | language | conversations | fallback_replies_total | mean_per_conversation |
|---|---|---|---|---|
| 1 | javascript | 10 | 15 | 1.50 |
| 1 | python | 10 | 12 | 1.20 |
| 2 | javascript | 10 | 15 | 1.50 |
| 2 | python | 10 | 16 | 1.60 |
| 3 | javascript | 10 | 15 | 1.50 |
| 3 | python | 10 | 16 | 1.60 |

Fallback replies are fixed strings in `tutor_agent.py` that replace a model reply the guards rejected. A conversation can look well-formed because of them, so report this share next to every pass/conclusion figure.

## 4. What the reply text looks like, by turn

| language | turn | words | has_question | over_3_sentences | possible_fix_giving | solution_leak | n |
|---|---|---|---|---|---|---|---|
| javascript | 1 | 34.30 | 1.00 | 0.10 | 0.10 | 0.00 | 30 |
| javascript | 2 | 27.60 | 1.00 | 0.00 | 0.00 | 0.00 | 30 |
| javascript | 3 | 34.60 | 1.00 | 0.10 | 0.00 | 0.00 | 30 |
| javascript | 4 | 34.10 | 1.00 | 0.00 | 0.00 | 0.00 | 30 |
| javascript | 5 | 25.00 | 1.00 | 0.20 | 0.00 | 0.00 | 30 |
| javascript | 6 | 90.50 | 0.00 | 0.80 | 0.00 | 0.00 | 30 |
| python | 1 | 29.77 | 1.00 | 0.00 | 0.00 | 0.00 | 30 |
| python | 2 | 29.77 | 1.00 | 0.00 | 0.17 | 0.00 | 30 |
| python | 3 | 47.13 | 1.00 | 0.33 | 0.10 | 0.00 | 30 |
| python | 4 | 28.30 | 1.00 | 0.10 | 0.17 | 0.00 | 30 |
| python | 5 | 27.87 | 1.00 | 0.07 | 0.13 | 0.00 | 30 |
| python | 6 | 89.63 | 0.00 | 0.77 | 0.03 | 0.00 | 30 |

`possible_fix_giving` is a loose regex for phrases such as "you can modify the code to...". It exists because the agent's own leak detectors do not look for these.

## 5. Stage path (replies per stage, by turn)

| language | turn | propose | test | consolidate | conclude |
|---|---|---|---|---|---|
| javascript | 1 | 27 | 3 | 0 | 0 |
| javascript | 2 | 3 | 18 | 9 | 0 |
| javascript | 3 | 3 | 0 | 27 | 0 |
| javascript | 4 | 3 | 0 | 27 | 0 |
| javascript | 5 | 3 | 0 | 27 | 0 |
| javascript | 6 | 0 | 0 | 0 | 30 |
| python | 1 | 27 | 3 | 0 | 0 |
| python | 2 | 3 | 9 | 18 | 0 |
| python | 3 | 0 | 0 | 30 | 0 |
| python | 4 | 0 | 0 | 30 | 0 |
| python | 5 | 0 | 0 | 30 | 0 |
| python | 6 | 0 | 0 | 0 | 30 |

## 6. Python vs JavaScript (paired by problem, n = 10; each problem averaged over its runs)

| measure | python_mean | javascript_mean | n_items | mean_diff | p_wilcoxon | p_holm |
|---|---|---|---|---|---|---|
| auto_fallback_replies_used | 1.467 | 1.500 | 10 | -0.033 | 0.875 | 1.000 |
| words | 42.078 | 41.017 | 10 | 1.061 | 0.846 | 1.000 |
| over_3_sentences | 1.267 | 1.200 | 10 | 0.067 | 0.719 | 1.000 |
| possible_fix_giving | 0.600 | 0.100 | 10 | 0.500 | 0.125 | 0.500 |
| questions_per_reply | 0.833 | 0.833 | 10 | 0.000 |  |  |

With 10 pairs and many tied values these tests have very little power; read the means, not the p-values.

## 7. Latency (JavaScript, run 1, local Code Llama)

| turn | count | mean | median | min | max |
|---|---|---|---|---|---|
| 1 | 10 | 37.52 | 35.71 | 33.91 | 45.69 |
| 2 | 10 | 39.81 | 40.40 | 30.85 | 51.59 |
| 3 | 10 | 45.31 | 47.27 | 33.74 | 58.16 |
| 4 | 10 | 47.97 | 46.97 | 37.20 | 59.42 |
| 5 | 10 | 60.96 | 54.60 | 33.29 | 114.72 |
| 6 | 10 | 56.73 | 54.32 | 48.99 | 69.11 |

| stage | count | mean | median |
|---|---|---|---|
| propose | 13 | 45.24 | 36.29 |
| test | 7 | 37.01 | 35.86 |
| consolidate | 30 | 48.95 | 46.97 |
| conclude | 10 | 56.73 | 54.32 |

These times are not comparable with web-app latency.

## 8. Quality of the Socratic questions

Rule-based proxy (`evaluation/cross_model/socratic_quality.py`), identical to the one used in the cross-model comparison: each question on turns 1-5 is scored on five criteria (asks for reasoning, grounded in the student's code, does not lead or give the fix, single focus, not a repeat). Score = criteria met (0-5); high quality = all five. It checks form, not whether the question was wise at that moment; validate it with the blinded manual rating.

| group | replies_expected | with_a_question | mean_quality_score_0_to_5 | high_quality_share | reasoning_prompt | code_grounded | non_leading | single_focus | not_repeated |
|---|---|---|---|---|---|---|---|---|---|
| All replies (turns 1-5) | 300 | 300 | 3.69 | 0.09 | 0.71 | 0.26 | 0.93 | 1.00 | 0.79 |
| Python | 150 | 150 | 3.77 | 0.12 | 0.74 | 0.34 | 0.89 | 1.00 | 0.80 |
| JavaScript | 150 | 150 | 3.62 | 0.06 | 0.68 | 0.18 | 0.98 | 1.00 | 0.78 |
| Written by Code Llama | 224 | 224 | 3.68 | 0.11 | 0.71 | 0.33 | 0.91 | 1.00 | 0.72 |
| Canned fallback | 76 | 76 | 3.74 | 0.04 | 0.70 | 0.04 | 1.00 | 1.00 | 1.00 |

Question types (share of all questions):

| question_type | count | share |
|---|---|---|
| recall | 52 | 0.17 |
| predict | 6 | 0.02 |
| trace/test | 15 | 0.05 |
| explain | 127 | 0.42 |
| extend/reflect | 62 | 0.21 |
| propose | 38 | 0.13 |

The canned fallback questions are fixed strings from `tutor_agent.py`, so they show how much of the agent's question quality comes from that scaffolding rather than from Code Llama.

## 9. Figures (all values are annotated on the charts)

- `fig1_fallbacks_per_problem.png`
- `fig2_reply_text_by_turn.png`
- `fig3_stage_path.png`
- `fig4_latency.png`
- `fig5_fallbacks_by_run.png`
- `fig6_question_quality.png`
