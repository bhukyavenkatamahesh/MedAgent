# MedOmit Milestone 1 — Reproducibility Infrastructure

Date: 2026-11-18. Status: implemented, tested, **not committed**.
Scope: provenance and output accounting only. **No scoring path was changed.** No new clinical rule
was added. C1/C2/C3 definitions, UPR and UGR are untouched.

## 1. What the runner actually does (inspection result)

| Question | Finding |
|---|---|
| Where could a per-case seed be injected? | **Not in the agent.** `HTTPAgent.inference()` does `body = self.body.copy()` then `body.update(self._handle_history(history))`. The body is fixed for the whole run and the agent never receives the case. Per-case seeding must live in the MedAgentBench task worker or in a proxy between the harness and the model server. |
| What does `runs.jsonl` record? | `index`, `output{history,result,status}`, `time{timestamp,str}`, `info` (always `null`), `error`. No model digest, no seed, no prompt text, no resource measurement. |
| What does `overall.json` record? | `custom.{"success rate", raw_results}` plus a `validation` histogram. `raw_results[i].status` is the official per-case verdict. |
| How are runs kept apart? | By a hand-written `output:` field in the assignment YAML. Nothing prevents two runs writing to one directory. |
| Where do model / prompt / repeat live? | **Only in directory names** (`fewshot4/qwen2.5-1.5b-ctx8k-t07-s2`). They are not recorded inside any artefact. |

## 2. What was added

| File | Role |
|---|---|
| `procsafe/provenance.py` | Run identity, episode UIDs, per-case seed derivation, fingerprints (evaluator source, policies, grader, benchmark data, prompt, host, simulator), the versioned `RunManifest`, output-directory collision guard. |
| `procsafe/output_status.py` | The five separate views of an episode's output. Assigns no safety label and never alters a grade. |
| `scripts/medomit_provenance.py` | CLI: `manifest` and `status`. Works retrospectively over existing runs. |
| `tests/test_provenance.py` | 29 tests. |
| `tests/test_output_status.py` | 22 tests. |

Neither new module is imported by `checker.py`, `metrics.py`, `policy.py`, `evidence.py` or
`schema.py`; a test enforces that.

### Run manifest (`manifest_version: 1`)

`experiment_id`, `run_id`, `created_at/started_at/ended_at`, `model{name,digest,quantization,runtime,num_ctx,temperature,identity_source}`,
`prompt{version,sha256}`, `seeds`, `repeat`, `cases{count,indices,task_types}`, `policies[]` (path,
sha256, policy_id, version, status, review_status), `evaluator` (git commit, clean-worktree flag,
source sha256 over the scoring modules), `grader` (refsol path + sha256), `benchmark` (test-data and
patch sha256), `simulator` (container image digest, case-table hash), `host`, `artifacts` (run dir,
runs.jsonl sha256, overall.json sha256), `episodes[]`, `unavailable{field: reason}`, plus
`manifest_sha256` over everything else.

`run_id` = `<date>__<model>__<prompt-version>__r<repeat>`.
`episode_uid` = `<run_id>__<task_id>#<case_index>`. **`task_id` alone is not unique** — it recurs in
every run, which is the bug that once produced a 10.0% figure where 100.0% was correct. A test pins
this.

### Seeds — what is and is not claimed

`derive_seed = sha256("<experiment_id>:<case_id>:<repeat>")[:16] mod (2^31 − 1)`, so each case in each
repeat has a stable, independently recomputable seed.

The manifest records these as **requested** seeds and carries `seed_support ∈ {honoured, unverified,
not honoured}` with `deterministic: false` and an explicit caveat. **No determinism is claimed.** A
seed constrains sampling only; it does not pin the runtime build, the kernels, concurrency, or the
FHIR server's mutable state. For the historical runs the honest value is: one static seed per run,
none per case. Three tests assert that no code path can report `deterministic: true`.

## 3. Output handling for truncated `FINISH(` payloads

Five views are stored side by side and never collapsed:

1. `raw_final_message` — the model's bytes, verbatim.
2. `harness_status` — MedAgentBench's own interpretation.
3. `official_grade` — `completedCorrect → PASS`, `completedIncorrect → FAIL`, anything else `None`
   (`graded: false`). A verbatim map; nothing else can write this field.
4. `strict_parser_action` — what procsafe's strict adapter extracts.
5. `completion_status` — `FINISH_PARSED` / `FINISH_TRUNCATED` / `FINISH_MALFORMED` /
   `NO_TERMINAL_ACTION` / `NO_TURNS`, plus `parser_and_harness_agree`.

A truncated payload keeps its official grade in **both** directions: an official `FAIL` is never
promoted, and an official `PASS` is never demoted — the disagreement is flagged, not resolved. Two
tests enforce each direction, and one test asserts `describe()` emits no safety label at all.

## 4. Historical-data compatibility

All **55** run directories with an `overall.json` were processed retrospectively; **0 errors**.
Outputs: `outputs/medomit_provenance/sweep/historical_compatibility.csv` and
`truncated_finish_episodes.csv`.

| | All 55 runs | The 24 held-out runs |
|---|---|---|
| Episodes | 945 | **480** |
| Graded | 760 | 400 |
| Ungraded | 185 | **80** |
| Official PASS | 278 | **107** |
| `FINISH_PARSED` | 753 | 394 |
| `FINISH_TRUNCATED` | 10 | **6** |
| `FINISH_MALFORMED` | 2 | 2 |
| `NO_TERMINAL_ACTION` | 180 | 78 |

This independently reproduces every disputed figure: **80** is exactly the harness's ungraded count
(the plan's number, correct for its definition); **86** is 80 + the **6** truncated `FINISH(`
episodes that the strict parser rejects; **107** is the development PASS denominator. The 6 are
Llama 3.2 1B only — four task9 cases in `fewshot2/llama3.2-1b-ctx8k` and two task5 cases in the
`t07-s2` repeats.

### Recoverable vs unrecoverable, per historical run

Identical for all 55 runs:

| Field | Status |
|---|---|
| case indices, order, episode UIDs, turn counts, timestamps | **recoverable** |
| harness status, official grade, raw final message, completion status | **recoverable** |
| artefact hashes (runs.jsonl, overall.json), grader sha256, benchmark data sha256 | **recoverable** |
| evaluator git commit + source hash, policy hashes | **recoverable** (as of today, not as of the run) |
| model name, prompt version, repeat | **inferred from the directory path** — flagged `identity_source` |
| `model.digest`, `model.quantization` | **not recorded**; recoverable only while the same tag is still installed locally, and a tag is not a digest |
| `prompt.sha256` | **not recorded** — the prompt was chosen by the `FEWSHOT` env var and its text was not stored |
| per-case seeds | **never existed** |
| simulator image digest, server state at run time | **unrecoverable** |
| peak RSS, time to first token, tokens/sec | **never measured** |

Conclusion: the historical runs are fully re-scorable and fully auditable, but **not
re-executable**. They remain development evidence. Anything the thesis presents as final must come
from a run carried out under this manifest.

## 5. Protection of existing artefacts

The sweep wrote only into `outputs/medomit_provenance/`. `ensure_fresh_output_dir` refuses a
non-empty target unless `--force` is passed. `git status` confirms `procsafe/checker.py`,
`procsafe/metrics.py`, `policies/`, `runs/` and `outputs/human_validation_v1/` are unmodified; the
v1 freeze and the `runs/E0_grader_audit` + `runs/E1_null_agents` (G0/G1) trees are untouched.

## 6. Test results

```
.venv/bin/python -m pytest -q
332 passed, 0 failed    (281 before this milestone, +51 new)
```

Coverage of the validation list: stable UID construction (4 tests incl. the cross-run uniqueness
guard); different repeat IDs; different tasks and case indices; missing model metadata; missing seed
support (3 tests, incl. that `honoured` still does not imply determinism); truncated `FINISH`
(4 tests, both grade directions); normal `FINISH`; invalid responses (5 ungraded statuses);
official-grade vs parser separation; manifest integrity and hashing (4 tests); output-directory
collision prevention (4 tests); backward compatibility for tasks 5, 9 and 10 (the three v2 policies
still load with their action requirements); plus two tests that the provenance layer neither imports
into the scoring modules nor references any frozen path.

## 7. What is ready for the supervisor's model sweep (plan E1/E2)

Ready: a versioned manifest capturing model, prompt, policy, evaluator, grader, benchmark,
simulator and host fingerprints; stable cross-run episode identity; deterministic case ordering;
reproducible per-case seed derivation; output-collision prevention; honest five-view output
accounting; retrospective coverage of all 55 existing runs.

Still required before a *final* run, and not in this milestone:
1. **Per-case seed injection** in the task worker or a proxy, plus a measurement of whether the
   local runtime honours it (`seed_support` stays `unverified` until then).
2. **Model digest and quantization capture** at launch (`ollama show --json`), not the tag.
3. **Prompt text stored with the run**, so `prompt.sha256` is real.
4. **Resource side-log**: peak RSS, time to first token, tokens/sec, wall time per episode, tool-call
   validity — the deck's required on-device side-log, currently absent.
5. **Simulator snapshot**: image digest plus a hash of the FHIR state the run saw.
