# Cross-model evaluation: Code Llama, ChatGPT web, and Claude web

This evaluation compares the project's conversational programming tutor with a controlled-prompt baseline and with ChatGPT/Claude through their **web applications**. No OpenAI or Anthropic API calls or API keys are used.

## Conditions

- `codellama_agent`: existing Code Llama tutoring agent, including its state machine, guards and fallback behaviour.
- `codellama_prompt`: Code Llama using the frozen controlled prompt only.
- `chatgpt` and `claude`: responses manually collected from the respective web applications using the same controlled prompt and scripted student turns.

Do not edit `controlled_prompt.txt` or its language notes after collecting data; create a new version if the experiment design changes.

## 1. Run the local Code Llama conditions

Install the project requirements, start Ollama, and ensure the model is available:

```bash
ollama serve
ollama pull codellama:7b
python -m evaluation.cross_model.run_cross_model_eval run --language both --repeats 3 --run-id local-main
```

For a quick plumbing check (not real evaluation data):

```bash
python -m evaluation.cross_model.run_cross_model_eval run --dry-run --only 1 --language python --run-id dry-check
```

## 2. Export the ChatGPT and Claude web-app worksheets

Run from the project root:

```bash
python -m evaluation.cross_model.run_cross_model_eval export-manual --condition chatgpt --language both --repeats 3 --out manual_pack
python -m evaluation.cross_model.run_cross_model_eval export-manual --condition claude --language both --repeats 3 --out manual_pack
```

This creates three separate Markdown files per problem under `manual_pack/chatgpt/` and `manual_pack/claude/`, suffixed `_run1.md`, `_run2.md`, and `_run3.md`. Each file contains the same single-run structure as the Code Llama evaluation sheet; do not combine three runs into one file. Open each file in a fresh model conversation and record replies in that file:

1. Open ChatGPT or Claude in a browser and start a fresh conversation for each worksheet.
2. Paste the complete tutor instructions and first student message from the worksheet.
3. Submit the remaining scripted student turns in order, copying each model reply into the matching `Tutor reply` section.
4. Keep the same model/version where possible and record the model shown in the web app and the collection date. Do not add extra instructions or regenerate a reply unless you document the deviation.
5. Save the completed worksheet without changing its header or turn headings.

The web applications do not expose identical sampling controls to the local model. Record this as a methodological limitation. Manual collection latency is not directly comparable to API/model generation latency; do not treat it as equivalent.

## 3. Import the completed worksheets

Use a distinct run ID for each web-app condition:

```bash
python -m evaluation.cross_model.run_cross_model_eval import-manual --condition chatgpt --dir manual_pack/chatgpt --model "ChatGPT web, MODEL NAME, YYYY-MM-DD" --run-id chatgpt-web
python -m evaluation.cross_model.run_cross_model_eval import-manual --condition claude --dir manual_pack/claude --model "Claude web, MODEL NAME, YYYY-MM-DD" --run-id claude-web
```

Replace the model names and dates with what you actually observe in the UI. The results are written under `results/cross_model/<run-id>/`. The importer checks the prompt version, worksheet condition and required replies, then generates analysis files.

## 4. Analyse results

```bash
python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/chatgpt-web
python -m evaluation.cross_model.run_cross_model_eval analyse --run-dir results/cross_model/claude-web
```

Use the same rubric and blind-rating procedure for every condition. Keep the local and manual run folders separate; if combining results, document that web-app model versions and sampling settings may be less controllable.

## Fairness and limitations

The same problem/code, prompt wording, and scripted student turns are used across conditions. The first worksheet message contains the instructions and the problem; subsequent messages are the scripted student turns. Web-app models may have hidden system instructions, changing model versions, safety behaviour, and non-configurable sampling. This is therefore a controlled *task and prompt* comparison, not a fully controlled API-level experiment. Record model/version, date, language, any UI settings, and any deviations.

Do not use dry-run records as evaluation results.
