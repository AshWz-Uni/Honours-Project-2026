# Honours-Project-2026: Intelligent Conversational Programming Tutor (Python & JavaScript)

## 1. Project Overview

This project develops an intelligent conversational programming tutor powered by Code Llama to assist students learning Python and JavaScript.

The agent uses a Socratic teaching approach, asking questions, encouraging students to explain their programming decisions, identifying potential issues, and guiding them towards improving their code without directly providing solutions.

The project evaluates the agent's functionality and tutoring effectiveness through programming problem testing, question quality assessment, and comparisons against other large language models.

## 2. Prerequisites

- Python 3.11
- Node.js 18+
- [Ollama](https://ollama.ai)
- Code Llama model

Download the model:

```bash
ollama pull codellama:7b
```

## 3. Installation and Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/AshWz-Uni/Honours-Project-2026
cd Honours-Project-2026
pip install -r requirements.txt
```

Start the backend:

```bash
uvicorn backend.main:app --reload --port 8000
```

In another terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Ensure Ollama is running:

```bash
ollama serve
```

Open the application at:

```text
http://localhost:5173
```

## 4. Supported Languages

The tutor supports Python and JavaScript, with automatic language detection available through the interface.

The `POST /chat` API accepts an optional `language` field (`python`, `javascript`, `js`, or `auto`). Language detection runs on each turn, allowing students to switch languages during conversations.

Language-specific prompts, code formatting, and solution-leak prevention are supported, while the underlying Socratic state machine and tutoring stages are shared.

## 5. Testing

Run the automated test suite:

```bash
python -m pytest
```

Tests cover stage selection, conversation state, solution-leak prevention, and language handling. They verify internal functionality rather than the quality of generated responses.

## 6. LeetCode Evaluation

The evaluation uses ten LeetCode problems implemented in both Python and JavaScript, with identical problem IDs, bugs, and scripted student responses.

Run the complete evaluation:

```bash
python -m evaluation.run_leetcode_eval
```

Additional options:

```bash
python -m evaluation.run_leetcode_eval --language javascript
python -m evaluation.run_leetcode_eval --only 1,5,9
python -m evaluation.run_leetcode_eval --dry-run
```

Results include individual language CSV files, conversation transcripts, and a combined CSV containing both languages.

Results are saved in:

```text
results/leetcode_eval/
```

Set `TUTOR_DEBUG=1` to enable the conversation-state endpoint:

```text
GET /chat/{id}/state
```

Tutoring behaviour can be adjusted in `backend/agent/tutor_agent.py` using `MIN_SOCRATIC_QUESTIONS` (default 5) and `HARD_QUESTION_LIMIT` (default 15).

## 7. Cross-Model Evaluation

The project compares four experimental conditions:

1. **Code Llama Agent:** Complete tutoring agent with its state machine and safeguards.
2. **Code Llama Controlled Prompt:** Code Llama using only the frozen controlled prompt.
3. **ChatGPT:** Manually collected responses from the ChatGPT web application.
4. **Claude:** Manually collected responses from the Claude web application.

ChatGPT and Claude are accessed through their web applications, due to limitations with paid API keys.

All conditions use the same ten programming problems, two languages, controlled prompts, and scripted student responses, with three repetitions per problem.

### 7.1 Code Llama Evaluation

Start Ollama and run:

```bash
python -m evaluation.cross_model.run_cross_model_eval run --language both --repeats 3 --run-id local-main
```

Use `--dry-run` for pipeline testing only. Dry-run results must not be included in the experiment.

### 7.2 ChatGPT and Claude Evaluation

Export separate worksheets for each model:

```bash
python -m evaluation.cross_model.run_cross_model_eval export-manual --condition chatgpt --language both --repeats 3 --out manual_pack

python -m evaluation.cross_model.run_cross_model_eval export-manual --condition claude --language both --repeats 3 --out manual_pack
```

Three separate Markdown worksheets (`_run1.md`, `_run2.md`, `_run3.md`) are generated for each problem.

For each worksheet:
1. Start a fresh conversation in the relevant web application.
2. Submit the tutor instructions and scripted student messages in order.
3. Record each model response in the corresponding worksheet.
4. Record the model version and collection date.

Import the completed worksheets:

```bash
python -m evaluation.cross_model.run_cross_model_eval import-manual --condition chatgpt --dir manual_pack/chatgpt --run-id chatgpt-web

python -m evaluation.cross_model.run_cross_model_eval import-manual --condition claude --dir manual_pack/claude --run-id claude-web
```

Analyse the results:

```bash
python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/chatgpt-web

python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/claude-web
```

## 8. Results Analysis
Run the Code Llama LeetCode analysis:

```bash
python -m evaluation.explore_codellama_leetcode
```

Compare the four experimental conditions:

```bash
python -m evaluation.cross_model.compare_models
```

The analysis includes a rule-based assessment of Socratic question quality using five criteria:

- Encourages reasoning.
- Relates to the student's code or input.
- Avoids leading questions or providing solutions.
- Focuses on one issue.
- Avoids repetition.

Questions receive a score from 0–5 and are categorised by cognitive type. Human blind ratings, implemented in `blind_rating.py`, provide additional evaluation of meaningful follow-up questions.

Outputs include CSV reports, question quality scores, question categories, and figures.

## 9. Evaluation Limitations

The experiment maintains consistent problems, prompts, and scripted student interactions across all conditions. However, ChatGPT and Claude web applications have potentially hidden instructions, changing model versions, and non-configurable sampling settings.

Additionally, manually collected web responses cannot be directly compared with local model generation times because manual collection includes human interaction.

These differences must be acknowledged when interpreting the results. Record model versions, collection dates, language, and any experimental deviations.

## 10. Evaluation Summary

The project uses five complementary evaluation approaches:

1. Automated testing of agent functionality.
2. LeetCode problem evaluation across Python and JavaScript.
3. Cross-model comparison against ChatGPT and Claude.
4. Rule-based assessment of Socratic question quality.
5. Blinded human evaluation of tutoring effectiveness.

Together, these methods assess the agent's technical functionality, conversational quality, and ability to encourage students to reason about their programming decisions.