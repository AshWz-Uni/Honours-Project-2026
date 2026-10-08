# Honours-Project-2026: Intelligent Conversational Tutoring Programming Agent (Python & JavaScript)

Aim: Assist students learning Python and Javascript coding through an intelligent conversational agent for programming projects.

## Prerequisites

- Python 3.11
- Node.js 18+
- [Ollama](https://ollama.ai) installed and running
- Code Llama model pulled: `ollama pull codellama`
- *(Optional)* Node.js 18+ on the PATH: only needed for the tests that execute the JavaScript
  problems to prove each intentional bug is real (they are skipped if `node` is missing)

---

## Quick Start

### 1. Clone and set up the backend

```bash
git clone https://github.com/AshWz-Uni/Honours-Project-2026
cd Honours-Project-2026

# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
cd ..
uvicorn backend.main:app --reload --port 8000
```

### 2. Set up the frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Ensure Ollama is running with Code Llama

```bash
ollama serve
ollama pull codellama
```

### 4. Open your browser

Navigate to `http://localhost:5173`

---

## Languages

The tutor supports **Python** and **JavaScript**. Pick a language in the UI, or leave it on
*Auto-detect*. Over the API, `POST /chat` takes an optional `language` field
(`"python"`, `"javascript"`, aliases such as `"js"`, or `"auto"`/omitted). The response echoes the
`language` the tutor used. Detection is re-run every turn from the current code, so pasting a
different language mid-conversation switches the tutor with it; if the code is ambiguous
(e.g. a bare `x = 1`) the conversation keeps its previous language.

What is language-specific: the code fence and a short language note in the prompts (JavaScript
terms, common JavaScript pitfalls the tutor may steer toward with a question, never the fix), the
new-code and solution-leak guards, and recursion detection. The Socratic state machine, stages and
everything else are shared. Python prompts are unchanged from the Python-only version.

## Tests

```bash
pip install -r requirements.txt
```

```bash
python -m pytest
```

These check the agent's own logic (stage selection, guards, state, language handling). They say nothing about Code Llama's quality.

## Evaluation on the 10-problem LeetCode set (Python and JavaScript)

The same 10 problems exist in both languages (same ids, same single bug, same scripted student):
`dataset/leetcode_eval.py` (Python) and `dataset/leetcode_eval_js.py` (JavaScript, in LeetCode's JS
style). With Node installed, the tests execute every JavaScript problem to confirm the buggy
version fails and the reference fix in `dataset/leetcode_eval_js_checks.py` passes.

```bash
python -m evaluation.run_leetcode_eval                        # both languages; needs Ollama + codellama:7b
python -m evaluation.run_leetcode_eval --language javascript  # one language
python -m evaluation.run_leetcode_eval --only 1,5,9           # subset
python -m evaluation.run_leetcode_eval --dry-run              # stub LLM, plumbing check only
```

Writes `results/leetcode_eval/<language>/leetcode_results.csv` and `transcripts.md`, plus
`results/leetcode_eval/combined_results.csv` (both languages stacked, with a `language` column) when
both are run. The runner passes each problem's language explicitly and separately records whether
auto-detection would have found it (`auto_language_detected_correctly`). Columns prefixed
`auto_` are proxies from the agent's own detectors; columns prefixed `MANUAL_` are for you
to fill in after reading the transcripts. `config/llm_config.json` fixes a `seed` so runs are repeatable.

Set `TUTOR_DEBUG=1` to enable `GET /chat/{id}/state` (learning-state flags and messages).

## Tuning

In `backend/agent/tutor_agent.py`: `MIN_SOCRATIC_QUESTIONS` (default 5; the dialogue only
concludes once the fix is validated AND this many questions were asked; 0 = conclude at
validation) and `HARD_QUESTION_LIMIT` (default 15; safety valve).



## Controlled LLM comparison experiment

The evaluation runner now supports the project's **Code Llama agent** plus
**ChatGPT (OpenAI API), Claude (Anthropic API), and Microsoft 365 Copilot Chat
API**. Every provider receives the same problem, code, student dialogue and
Socratic tutoring instructions. The runner records wall-clock time for every
completed tutor response.

```bash
# Code Llama only
python -m evaluation.run_leetcode_eval --provider codellama

# One external provider
python -m evaluation.run_leetcode_eval --provider chatgpt
python -m evaluation.run_leetcode_eval --provider claude
python -m evaluation.run_leetcode_eval --provider copilot

# Run all four providers
python -m evaluation.run_leetcode_eval --provider all

# Useful during development
python -m evaluation.run_leetcode_eval --provider codellama --language python --only 1,2 --dry-run
```

Results are written under `results/leetcode_eval/`:

- `<provider>/leetcode_results.csv` — one summary row per problem.
- `<provider>/response_times.csv` — one row per tutor response, including
  `response_time_ms` and the generated response.
- `<provider>/transcripts.md` — the complete benchmark transcript with the
  measured response time shown beside each tutor response.
- `all_providers_results.csv` — all provider/problem summary rows together when multiple providers are run. A single-provider run uses `combined_results.csv`.

The summary contains `response_time_total_ms`, `response_time_avg_ms`,
`response_time_min_ms`, and `response_time_max_ms`. The timing starts immediately
before the provider/agent response is requested and stops when the complete
response is available. For Code Llama this measures the **whole project-agent
turn**, including its private diagnostic pass and response-generation pass.

### Provider configuration

The external providers use environment variables so credentials are not committed
to the repository.

**ChatGPT / OpenAI API**

```text
OPENAI_API_KEY=...
CHATGPT_MODEL=<model available to your API account>
```

Optional: `OPENAI_BASE_URL`, `OPENAI_TIMEOUT`.

**Claude / Anthropic API**

```text
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=<model available to your Anthropic account>
```

Optional: `ANTHROPIC_BASE_URL`, `ANTHROPIC_TIMEOUT`, `CLAUDE_MAX_TOKENS`.

**Microsoft 365 Copilot Chat API**

```text
COPILOT_ACCESS_TOKEN=...
COPILOT_TIME_ZONE=Australia/Sydney
```

Optional: `COPILOT_BASE_URL`, `COPILOT_TIMEOUT`.

Important: the ordinary consumer **Microsoft Copilot Chat** website does not
provide a general public API. The `copilot` adapter therefore uses Microsoft's
Microsoft 365 Copilot Chat API, which is currently a preview API and requires a
Microsoft 365 Copilot add-on licence plus delegated Microsoft Graph
authentication. If you are using the normal consumer Copilot website, record
those responses manually rather than treating an unofficial browser automation
method as an API benchmark.

### Evaluation methodology

For a defensible thesis comparison, keep these conditions fixed:

1. Use the same 10 Python and 10 JavaScript problems for every provider.
2. Use the same code, problem statement and scripted student messages.
3. Use the same Socratic tutoring instructions: one question per turn and no
   direct solution.
4. Run each provider in a fresh conversation for every problem.
5. Record latency for every response, rather than only the total experiment time.
6. Keep model names, model versions, temperatures/settings and run dates in the
   results so the experiment can be reproduced.
7. Treat response time and automated rule checks as quantitative measures, while
   the existing `MANUAL_` columns are completed after reviewing the transcripts
   for educational quality.
8. Do not compare only average latency: report median and spread as well when
   analysing results, because network/API variability can produce outliers.

The comparison is between the **implemented tutoring agent** and the selected
external LLM configurations. It should therefore be reported as an evaluation
of the configured systems, not as a claim that one company's underlying model
is universally better than another.
