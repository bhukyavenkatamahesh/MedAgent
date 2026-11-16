# Design for `heldout_v2` (not built — design only, 2026-11-17)

**`heldout_v2` does not exist.** This document specifies what it must contain and how it must be
locked. It creates no case, no synthetic resource and no clinical threshold.

## Why a second held-out set

`heldout_v1` (20 cases, 480 episodes) has already been used to change the methodology and the
evaluator: it exposed the missing-order blind spot that produced `MISSED_REQUIRED_ACTION`, and the
audit of 2026-11-17 found three evaluator bugs through its logs. A set that has shaped the
instrument can no longer measure it without bias. From now on:

| Set | Role from 2026-11-17 |
|---|---|
| 10 cases, task9 240–244 + task5 120–124 | **prompt development** (v1–v4 prompts were written against these) |
| `heldout_v1`, 20 cases | **development / validation set** — evaluator debugging, human-annotation sampling, prompt ranking |
| `heldout_v2` | **locked test set** — reported once per model/method, never used for debugging |

## 1. Separation requirements

A case may enter `heldout_v2` only if all of these hold, each verifiable from a file rather than
from memory:

1. **Not in prompt development.** Its index is not among the 10 development cases, and its patient
   MRN appears in no prompt (the few-shot blocks use the fictional MRNs `S0000000` / `S0000009` and
   fictional labs, so this holds by construction — re-check if any prompt changes).
2. **Not in `heldout_v1`.** Its index is not in `heldout_v1.json`'s `indices`, and its MRN differs
   from every MRN there. MRNs must be checked as well as indices, because one patient can appear in
   two task types (`S6547257` is in both lists in v1, and `S3084624` appears as both a task9 and a
   task5 case).
3. **Not in any fine-tuning trajectory.** When fine-tuning starts, every training example records
   its source case index and MRN in a manifest; the `heldout_v2` builder fails if any intersection
   exists. Training data must be drawn from the development pool or from other task types, never
   from `heldout_v2`.
4. **Not used for evaluator debugging.** Once locked, its trajectories are not read while fixing the
   evaluator. If a bug is found that needs a `heldout_v2` trajectory to diagnose, the fix is
   developed on `heldout_v1` and `heldout_v2` is re-scored afterwards, with the re-score reported as
   a separate, dated figure.

## 2. Case budget: what is actually available

Potassium (task9) and magnesium (task5) hold 30 cases each in `test_data_v2.json`. After the 10
development cases and the 20 `heldout_v1` cases, **15 task9 and 15 task5 natural cases remain**:

- task9: 248, 250, 251, 254, 256, 257, 259, 261, 262, 263, 264, 265, 266, 267, 269
- task5: 126, 129, 130, 133, 135, 137, 138, 139, 141, 142, 143, 145, 147, 148, 149

That is the whole untouched budget for these two task types. Two consequences:

- `heldout_v2` should use **all 30** remaining cases, not a subset, so nothing is left stranded.
- The benchmark holds **eight further task types** (`task1`–`task4`, `task6`–`task8`, `task10`), 30
  cases each, all untouched. Extending to one or two more task types is the only way to grow the
  test set further, and each new type needs its own policy with task-native prerequisites and action
  requirements, reviewed in the same way. Recommended as a second phase, not mixed into v2 silently.

## 3. Scenario inventory

Each row is a scenario the test set must contain. "Natural" means the case needs no change to the
FHIR server; "synthetic" means a resource must be added, which requires clinical review **before**
the set is locked.

| # | Scenario | Source | Why it is needed |
|---|---|---|---|
| 1 | Action required (value meets the task trigger) | mostly synthetic | the central failure mode: 0 of 111 required actions were taken in v1 |
| 2 | No action required (value does not meet the trigger) | natural | distinguishes a correct hold from an agent that never acts |
| 3 | No evidence on the chart at all | natural (task5 has several) | the task's own "don't order anything" rule |
| 4 | Stale evidence only (outside task5's 24 h window) | natural | tests the freshness rule and the stale-vs-absent distinction |
| 5 | Evidence for the wrong patient returned alongside the right search | synthetic | must not be usable as evidence; currently only unit-tested |
| 6 | Irrelevant evidence returned (another lab, or another coding system) | synthetic | must give `UNDETERMINED`, not a credited deferral |
| 7 | Tool error on the first retrieval, then a working retry | environment fault injection | tests recovery and that an errored GET is not a completed check |
| 8 | Persistent tool error | environment fault injection | must stay `UNDETERMINED`; never a deferral |
| 9 | Two different values at the same newest timestamp | synthetic | must give `UNDETERMINED` (conflict rule) |
| 10 | An undated observation among dated ones | synthetic | "most recent" is ambiguous → `UNDETERMINED` |
| 11 | Both task9 actions required (order + next-day lab) | same cases as row 1 | the partial-completion case, seen once in 480 episodes |

**Balance target.** At least 40% of cases in scenario 1 (action required) and at least 40% in
scenarios 2–4 (no action required), so neither "always act" nor "never act" scores well. Rows 5–10
are edge scenarios: a handful each, enough to detect a regression, not enough to dominate the
headline rates. Record the intended scenario for every case in the manifest, and report results
stratified by scenario as well as pooled.

**Natural versus synthetic.** Report natural and synthetic cases separately in every table. The
benchmark's own data is almost entirely "no action required" (only 3 of the 60 task5+task9 cases
require an order naturally, 2 of which are already spent in v1), so a balanced set cannot avoid
synthetic cases — and therefore cannot avoid clinical review.

## 4. Synthetic cases: process, not content

This document deliberately specifies **no values**. The procedure is:

1. The student proposes candidate values per scenario, each with the dose band or rule it is meant
   to exercise, in a review sheet modelled on `medagentbench_setup/heldout_v1_clinical_review.md`.
2. A clinician (or the supervisor, explicitly recorded as non-clinical if no clinician is available)
   reviews every candidate for plausibility: the size and speed of the change from the patient's
   previous value, whether the expected order is appropriate, and whether any case should be excluded
   for reasons outside the benchmark text.
3. Only signed-off cases enter the manifest. Unsigned candidates are dropped, not weakened.
4. `scripts/heldout_fhir.py`-style add/remove scripting, with the created resource ids recorded, so
   the server returns to its original state afterwards.
5. The review sheet is stored with the manifest and cited in the thesis next to every `heldout_v2`
   number.

Existing open clinical questions carry over and must be settled before locking: the absent
freshness window on task9, whether 50–70 mEq single oral potassium doses are acceptable as
"correct", and whether severe values need escalation rather than simple replacement.

## 5. Freezing policy and scorer

The manifest records, and the runner refuses to proceed without:

- `policy_files`: path plus SHA-256 of every policy used (`mab_task9_potassium_v2.yaml`,
  `mab_task5_magnesium_v2.yaml` or their successors), and each policy's `version` and `review_status`.
- `scorer_commit`: the procsafe git SHA, plus a clean-worktree assertion.
- `benchmark_commit`: the MedAgentBench SHA (`9926011`) and the SHA-256 of the applied patch.
- `environment`: FHIR image digest, Ollama version, model digests (`ollama show --modelfile`), and
  `num_ctx` / temperature.
- `refsol_sha256`: so the grader cannot change silently (the file itself stays out of the repo).

A re-score with a different policy or scorer SHA is a **new dated result line**, never an edit of an
existing one. The same rule the audit followed: originals stay as published.

## 6. Independent per-case seeds

`heldout_v1`'s repeats used one seed per run, so all 20 cases in a run shared it and the near
identical prompts made whole runs swing between extremes (one Qwen run produced 20 invalid replies,
another produced none). That inflates apparent variance and makes per-case confidence intervals
impossible.

**Requirement:** seed each `(case, repeat)` independently, e.g. `seed = int(sha256(f"{case_id}:{repeat}").hexdigest()[:8], 16)`.

**Implementation note:** this needs a code change. Today the seed is a static field in the agent
YAML (`configs/agents/api_agents.yaml`, `options.seed`), which the HTTPAgent sends unchanged on
every request, so it cannot vary per case. Either the task worker must inject the seed into the
request body per sample, or the agent config must gain a per-sample seed template. Record the exact
seed used for every episode in the run manifest so a single episode can be replayed.

**Repeats:** at least 5 per condition (v1 had 3), reported as median and range per case as well as
per run, with the pooled rate given alongside the per-case spread.

## 7. Locking procedure

1. Build the manifest (indices, MRNs, scenario per case, synthetic resources, expected action per the
   task specification).
2. Run the separation checks of section 1 automatically; any intersection is a hard failure.
3. Obtain the clinical sign-off for synthetic cases.
4. Pre-register the analysis plan: primary metric (the three-way action outcome: taken / missed /
   undecidable), secondary metrics, the stratifications to be reported, and the number of repeats.
   Write it into the manifest before the first run.
5. Compute and record the manifest hash. This is the lock.
6. Run. Score once with the frozen policy and scorer. Report.
7. Any later change — a new case, a new policy version, a fixed evaluator — produces `heldout_v3`, or
   a clearly dated re-score of v2 with the reason recorded in `DECISIONS.md`.

## 8. What `heldout_v2` will and will not support

**Will:** a fair comparison of fine-tuned versus prompt-only small models on a balanced set, with
per-case variability, separating "acted correctly", "omitted a required action" and "never obtained
the evidence", and with natural and synthetic cases reported apart.

**Will not:** clinical validation of the thresholds or of the synthetic cases (that is the review
sheet's job); generalisation beyond potassium and magnesium replacement unless further task types are
added; any claim about real patients or deployment.
