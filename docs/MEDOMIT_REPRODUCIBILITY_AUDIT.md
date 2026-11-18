# MedOmit reproducibility audit

**Status: AUDIT. Nothing was changed and no experiment was run.** Inspected: the MedAgentBench harness
patch, the agent configs, `runs.jsonl` / `overall.json` records, `episodes.jsonl`, and the run
directories of the 24 held-out runs.

---

## 1. What the runner records today

| Requirement | Present? | Where it lives today |
|---|---|---|
| **Per-case seeds** | **No** | `options.seed` is a static field in `configs/agents/api_agents.yaml`, sent unchanged on every request. One seed per *run*, shared by all cases in it |
| **Model identifier** | Partly | the Ollama model *name* is in the agent config (`qwen2.5:1.5b-instruct`); it appears in no output artefact |
| **Model digest / quantization** | **No** | obtainable from `ollama show` / `/api/tags` but never captured. Ollama is not even running now, so the digests used in the 2026-11-16 runs are **unrecoverable** |
| **Prompt version** | **No** | selected by the `FEWSHOT` environment variable at worker start; recorded nowhere in the output |
| **Task identifier** | Yes | `index` in `runs.jsonl`; `task_id` and `episode_id` in `episodes.jsonl` |
| **Patient identifier** | Indirect | only via the task definition; not copied into any record |
| **Repeat ID** | **No** | encoded in the *directory name* (`…-t07-s1`), not in the data |
| **Simulator state / snapshot** | **No** | the FHIR container is mutated in place. The `heldout_v1` synthetic observations were added and later deleted, so the server state at run time cannot be reconstructed from any artefact |
| **Evaluator / policy hashes** | Partly | `episodes.jsonl` carries `policy_id` and `policy_version`; **no file hash, no scorer commit**. `input_provenance` exists but is `{}` for real runs |
| **Grader hash** | Only in G0 | `runs/E0_grader_audit/e0_summary.json` records `refsol.py` sha256. Normal runs do not |
| **Output directory isolation** | Manual | the assignment YAML's `output:` field; nothing prevents two runs writing to the same place |

### 1.1 The consequence already observed

Because `episode_id` identifies the **case** and not the run, the same id occurs in all 24 runs. That
caused a real analysis bug in the human-validation comparison: turn labels were unioned across runs
and two fields read 10.0% instead of 100.0% until the join was keyed on
`(prompt, agent, episode_id)`. This is not hypothetical — it is why `episode_uid` is mandatory in the
dataset schema.

### 1.2 What *is* reproducible today

- Raw trajectories: `runs/*/*/medagentbench/runs.jsonl[.gz]` with full message history.
- Terminal grades: `overall.json`, including the harness's own status histogram.
- Re-scoring: any saved run can be re-scored with any policy version, which is how the 2026-11-17
  audit and the task-10 re-score were done with no model inference.
- G0's 90-case table pins the server's answer per case at that time, which is the closest thing to a
  simulator snapshot that exists.

## 2. Minimal implementation plan (not implemented)

Ordered by value per unit of work. None of it requires a model run.

| # | Change | Where | Effort | Unblocks |
|---|---|---|---|---|
| **R1** | **Run manifest** written at the start of every run: timestamp, `run_id`, model name + digest + quantization, `num_ctx`, temperature, prompt version (`FEWSHOT`), parse mode, `CASE_INDICES`, policy files with sha256 and `review_status`, `refsol.py` sha256, procsafe commit + clean-worktree assertion, MedAgentBench commit + patch sha256, FHIR image digest, host hardware | new `scripts/write_run_manifest.py`, called by the driver | small | every freezing and provenance requirement |
| **R2** | **`episode_uid`** = `f"{run_id}__{task_id}#{index}"` emitted in `runs.jsonl` and `episodes.jsonl` | harness patch + `procsafe/report.py` | small | correct joins; prevents the §1.1 bug class |
| **R3** | **Per-case seed**: `seed = int(sha256(f"{run_id}:{case_id}:{repeat}").hexdigest()[:8], 16)`, injected per request and recorded per episode | task worker (the agent config cannot vary per sample) | medium | plan E6, any confidence interval |
| **R4** | **Resource side-log** per episode: peak RSS, time to first token, tokens/s, wall time, tool-call validity | driver wrapper around the agent call | medium | the on-device claim, scope discipline |
| **R5** | **Output isolation guard**: refuse to write into a non-empty run directory unless `--force` | driver | small | prevents silent overwrites |
| **R6** | **Simulator snapshot record**: store the per-case reference answer table (as G0 does) plus the FHIR image digest and any mutation script actually applied | extend `scripts/e0_grader_audit.py` output into the manifest | small | the dataset's claim that the environment is fixed |
| **R7** | **Scorer provenance in `episodes.jsonl`**: policy file hashes and the procsafe commit, replacing the empty `input_provenance` | `procsafe/report.py` | small | re-score auditability |

**Suggested grouping.** R1 + R2 + R5 + R7 are a single small change set with no behavioural effect on
scoring and would let every future run be frozen properly. R3 and R4 touch the run loop and should
land together, before any sweep. R6 is a by-product of R1.

## 3. What cannot be recovered retrospectively

Stated plainly so the thesis does not overclaim:

- the **model digests and quantization** of the 2026-11-16 runs;
- the **exact seed per case** for those runs (only the per-run seed is known, from the agent name);
- the **FHIR server state** at that time, beyond the per-case reference answers recorded by G0;
- any **resource measurement** (none was taken; only wall-clock run times are known).

These runs therefore remain **development/validation** evidence. They cannot be promoted to a
reproducible test result, which is an independent reason the locked split must be built and run under
R1–R5 rather than reusing existing logs.
