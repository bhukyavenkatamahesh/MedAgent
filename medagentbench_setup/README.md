# MedAgentBench local setup

Changes made to a clone of [stanfordmlgroup/MedAgentBench](https://github.com/stanfordmlgroup/MedAgentBench) at commit `9926011` for the procsafe runs.

| File | What it does |
|---|---|
| `medagentbench.patch` | Adds the local Ollama agents (`qwen2.5-local` 7B, plus the ~1B on-device SLMs `llama3.2-1b-local`, `gemma3-1b-local`, `qwen2.5-1.5b-local`, `lfm2-1.2b-local`), one assignment file per SLM (`configs/assignments/slm_<agent>[_lenient].yaml`), sample case selection, and the opt-in lenient parser |
| `ollama-chat.yaml` | HTTPAgent config for a local Ollama server (`http://localhost:11434/v1/chat/completions`). The `Bearer ollama` header is a placeholder; Ollama doesn't check it |

Apply:

```bash
git clone https://github.com/stanfordmlgroup/MedAgentBench && cd MedAgentBench
git checkout 9926011
git apply ../procsafe/medagentbench_setup/medagentbench.patch
cp ../procsafe/medagentbench_setup/ollama-chat.yaml configs/agents/
```

Not included: `src/server/tasks/medagentbench/refsol.py`, the benchmark's reference grader. Stanford distributes it separately (Box link in their README), so download it from there.

## Running the 1B sample

```bash
ollama pull llama3.2:1b && ollama pull gemma3:1b && ollama pull qwen2.5:1.5b-instruct && ollama pull hf.co/LiquidAI/LFM2-1.2B-GGUF
docker start <fhir-container>            # jyxsu6/medagentbench, port 8080
SAMPLE_N=5 python -m src.start_task -a   # add LENIENT_PARSE=1 for lenient mode
python -m src.assigner -c configs/assignments/slm_llama3.2-1b-local.yaml
```

Environment variables read by the task worker (set them when starting `src.start_task`):
- `SAMPLE_N` (default 5): runs the first N task9 + first N task5 cases. To run everything, revert `get_indices()` to `list(range(len(self.data)))`.
- `LENIENT_PARSE=1`: takes the first `GET` / `POST` / `FINISH(` line out of a reply that wraps it in prose. It's off by default (strict = original benchmark). Score lenient runs with `scripts/run_medagentbench.py --lenient`, which uses an identical copy of the extraction function.

Results of the first SLM run: `runs/2026-11-16_slm-1b_sample_n10/`.
