# Honours-Project-2026: Intelligent Conversational Tutoring Python Programming Agent

Aim: Assist students learning Python and Javascript coding through an intelligent conversational agent for programming projects.

## Prerequisites

- Python 3.11
- Node.js 18+
- [Ollama](https://ollama.ai) installed and running
- Code Llama model pulled: `ollama pull codellama`

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

## Tests

```bash
pip install -r requirements.txt
```

These check the agent's own logic (stage selection, guards, state). They say nothing about Code Llama's quality.

## Evaluation on the 10-problem LeetCode set

```bash
python -m evaluation.run_leetcode_eval                # needs Ollama + codellama:7b
python -m evaluation.run_leetcode_eval --only 1,5,9   # subset
python -m evaluation.run_leetcode_eval --dry-run      # stub LLM, plumbing check only
```

Writes `results/leetcode_eval/leetcode_results.csv` and `transcripts.md`. Columns prefixed
`auto_` are proxies from the agent's own detectors; columns prefixed `MANUAL_` are for you
to fill in after reading the transcripts. `config/llm_config.json` fixes a `seed` so runs are repeatable.

Set `TUTOR_DEBUG=1` to enable `GET /chat/{id}/state` (learning-state flags and messages).

## Tuning

In `backend/agent/tutor_agent.py`: `MIN_SOCRATIC_QUESTIONS` (default 5; the dialogue only
concludes once the fix is validated AND this many questions were asked; 0 = conclude at
validation) and `HARD_QUESTION_LIMIT` (default 15; safety valve).

