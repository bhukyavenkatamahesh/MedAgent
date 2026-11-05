# MedAgentBench local setup

Changes made to a clone of [stanfordmlgroup/MedAgentBench](https://github.com/stanfordmlgroup/MedAgentBench) at commit `9926011` for the procsafe runs.

| File | What it does |
|---|---|
| `medagentbench.patch` | Adds the `qwen2.5-local` agent, makes it the default assignment (concurrency 1), and limits `get_indices()` to the first 5 task9 cases |
| `ollama-chat.yaml` | HTTPAgent config for a local Ollama server (`http://localhost:11434/v1/chat/completions`). The `Bearer ollama` header is a placeholder; Ollama doesn't check it |

Apply:

```bash
git clone https://github.com/stanfordmlgroup/MedAgentBench && cd MedAgentBench
git checkout 9926011
git apply ../procsafe/medagentbench_setup/medagentbench.patch
cp ../procsafe/medagentbench_setup/ollama-chat.yaml configs/agents/
```

Not included: `src/server/tasks/medagentbench/refsol.py`, the benchmark's reference grader. Stanford distributes it separately (Box link in their README), so download it from there.

Note: the `get_indices()` change runs only 5 cases. Revert that line for full runs.
