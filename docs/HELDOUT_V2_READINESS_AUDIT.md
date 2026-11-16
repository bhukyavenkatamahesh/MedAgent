# `heldout_v2` readiness audit

**Status: AUDIT. `heldout_v2` does not exist and nothing was built by this document.** It checks the
existing design (`docs/HELDOUT_V2_DESIGN.md`) against the data and names what is still missing for a
defensible final test set.

All counts below were measured on 2026-11-17 from `data/medagentbench/test_data_v2.json` and the
local FHIR server (container `great_burnell`), with no model inference.

---

## 1. Findings that change the design

### 1.1 BLOCKER — the remaining natural pool contains **zero** order-required cases

The design assumed "mostly synthetic" positives. It is worse than that: **every** positive-action
case in `heldout_v2` must be synthetic.

| Task | Cases left | Latest values (reference time 2023-11-13T10:15Z) | Natural positives |
|---|---|---|---|
| task9 (K < 3.5 required) | 15 | 3.5, 3.6, 3.8, 3.8, 3.8, 3.9, 3.9, 3.9, 4.0, 4.1, 4.1, 4.3, 4.3, 4.5, 4.7 | **0** |
| task5 (Mg ≤ 1.9 within 24 h required) | 15 | 2.0, 2.0, 2.0, 2.0, 2.1, 2.1, 2.1, 2.2, and 7 with no result in window | **0** |

The benchmark's three natural order-required cases are all spent: one in the development set
(task9_3, K 3.1) and two in `heldout_v1` (task5_21 Mg 1.8, task5_25 Mg 1.9).

**Consequence:** clinical review of synthetic cases moves from "should do" to **hard prerequisite**.
Without it there is no positive-action half of the test set, and the headline finding (0 of 111
required actions taken) has nothing new to be measured against.

### 1.2 Patient-level separation is violated by 3 of the 30 pool cases

The design requires separation by MRN as well as by index. Measured:

| Pool case | MRN | Already used as |
|---|---|---|
| `task5_16` (index 135) | `S1023381` | `task9_2` — development set |
| `task5_19` (index 138) | `S3057899` | `task9_13` — `heldout_v1` |
| `task9_12` (index 251) | `S6541353` | `task5_2` — development set |

Also, one patient appears **twice inside the pool**: `S6537563` is both `task5_11` and `task9_17`.

**Usable pool: 30 → 27** after excluding cross-set collisions, **→ 26** if a patient may appear only
once inside the test set. Decision needed (audit item D3 below): strict patient-level separation
(26 cases) or index-level only (30, documented as patient-overlapping).

### 1.3 A 26–27 case test set is small for the planned matrix

With 5 repeats and ~27 cases an arm has ~135 episodes, but the *positive* half rests on ~13
synthetic cases. Any per-case claim will have wide intervals. Two ways out: accept it and report
per-case results with the spread, or extend to a third task type (eight task types, 30 cases each,
are untouched) at the cost of a new policy plus its own review.

## 2. Checks requested, and their verdicts

| Check | Verdict | Detail |
|---|---|---|
| **Sample independence** (no overlap with prompt development) | **PASS at index level** | The pool excludes all 10 development cases and all 20 `heldout_v1` cases by construction (`medagentbench_setup/heldout_v1.json`). Few-shot prompts use fictional MRNs (`S0000000`, `S0000009`), so no pool patient appears in a prompt |
| **Patient-level separation** | **FAIL** | 3 cross-set collisions and 1 within-pool duplicate (§1.2). Not currently enforced by any script |
| **Per-case random seeds** | **NOT IMPLEMENTED** | The seed is a static field in `configs/agents/api_agents.yaml` (`options.seed: 1|2|3`), sent unchanged on every request, so all cases in a run share it. `heldout_v1`'s runs show the effect: whole runs swung between 0 and 20 invalid replies. Needs a harness change: inject `seed = f(case_id, repeat)` per sample |
| **Frozen policy version** | **PARTIAL** | Policies are versioned and carry `review_status`, and v2 is the current pair. Nothing yet records a hash, and nothing refuses to run against a modified policy |
| **Frozen scorer version** | **MISSING** | No manifest, no commit pinning, no clean-worktree assertion. The working tree currently has uncommitted evaluator changes from the 2026-11-17 audit, which is exactly the state a lock must forbid |
| **Positive-action coverage** | **FAIL without synthetic cases** | 0 of 27 natural positives (§1.1) |
| **Negative-action coverage** | **PASS** | All 27 remaining cases are natural negatives: 15 "value not low", 7 "no result in the 24 h window", plus the rest |
| **Edge-scenario coverage** (wrong patient, irrelevant evidence, tool error, conflicting/undated observations) | **MISSING** | Designed in `HELDOUT_V2_DESIGN.md` §3 rows 5–10 but none exists. Rows 7–8 (tool errors) also need an environment fault-injection mechanism that has not been written |
| **Unnecessary-action coverage** | **MISSING, and not fixable by case selection alone** | Needs an agent that orders after reading a normal value; observed once in 480 episodes. See backlog E6 |

## 3. What is still missing, in build order

1. **Clinical review of synthetic positives** — now a prerequisite. A review sheet modelled on
   `medagentbench_setup/heldout_v1_clinical_review.md`, with candidate values per dose band, signed
   before anything is locked.
2. **A separation checker** that fails on index *or* MRN overlap with the development set,
   `heldout_v1`, and any fine-tuning manifest. Does not exist.
3. **Per-case seeding** in the MedAgentBench patch, plus the seed recorded per episode so a single
   episode can be replayed.
4. **A lock manifest and a runner that enforces it**: policy paths + hashes, procsafe commit with a
   clean-worktree assertion, MedAgentBench commit + patch hash, `refsol.py` hash, FHIR image digest,
   model digests, `num_ctx`, temperature, and the pre-registered analysis plan.
5. **Fault injection** for the tool-error scenarios, written and tested before the set is locked.
6. **A frozen evaluator version**: decide the backlog items (E1–E3 especially) *before* v2 runs, so
   v2 is scored once and never re-scored.
7. **A pre-registered analysis plan** inside the manifest: primary metric (the three-way action
   outcome), secondary metrics, stratifications, repeat count.

## 4. Decisions this audit needs from the supervisor

| # | Decision |
|---|---|
| D1 | Synthetic positives are now unavoidable. Approve the review route, and name the reviewer |
| D2 | Target size: 26–27 cases from the two existing task types, or extend to a third task type (new policy, new review) |
| D3 | Strict patient-level separation (26 cases) or index-level only (30, with the overlap documented) |
| D4 | Accept the per-case-seed harness change as a prerequisite, or run with run-level seeds and report the correlation as a limitation |
| D5 | Lock the evaluator before v2 at the current version, or first land guide v2 and backlog items E1–E3 |
| D6 | How many edge-scenario cases, and do the tool-error scenarios justify writing fault injection |
