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



## Cross-model thesis evaluation (Code Llama vs ChatGPT/Claude web apps)

ChatGPT and Claude are not accessed through paid APIs. Run Code Llama's local conditions with:

```bash
python -m evaluation.cross_model.run_cross_model_eval run --language both --repeats 3 --run-id local-main
```

Export controlled-prompt worksheets for the web applications:

```bash
python -m evaluation.cross_model.run_cross_model_eval export-manual --condition chatgpt --language both --out manual_pack
python -m evaluation.cross_model.run_cross_model_eval export-manual --condition claude --language both --out manual_pack
```

Complete the worksheets by pasting the same instructions and scripted student turns into each web app and recording each reply. Then import and analyse them:

```bash
python -m evaluation.cross_model.run_cross_model_eval import-manual --condition chatgpt --dir manual_pack/chatgpt --model "ChatGPT web, MODEL, YYYY-MM-DD" --run-id chatgpt-web
python -m evaluation.cross_model.run_cross_model_eval import-manual --condition claude --dir manual_pack/claude --model "Claude web, MODEL, YYYY-MM-DD" --run-id claude-web
python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/chatgpt-web
python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/claude-web
```

See `evaluation/cross_model/README.md` for collection protocol and limitations. Web-app sampling and latency are not directly controllable/comparable with local model generation.
