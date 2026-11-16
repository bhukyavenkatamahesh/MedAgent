# Research plan: from human validation v1 to the final test-set result

**Written 2026-11-17. Nothing in this plan is implemented.** It is for supervisor review. The four
documents it refers to are proposals and audits, not changes:

| Document | What it is |
|---|---|
| `docs/ACTION_ANNOTATION_GUIDE_V2_PROPOSAL.md` | three guide fixes the v1 validation showed are needed |
| `docs/EVALUATOR_IMPROVEMENTS_BACKLOG.md` | seven evaluator items, with their re-scoring cost |
| `docs/HELDOUT_V2_READINESS_AUDIT.md` | what is missing before a defensible final test set |
| `docs/FINAL_EXPERIMENT_MATRIX_PROPOSAL.md` | the baseline / prompt-only / improved matrix |

## 1. Where the project stands

- The evaluator measures process safety on four dimensions and has survived an independent audit
  (three bugs found and fixed) and a two-reviewer human validation.
- **Human validation v1 (frozen):** reviewer-vs-reviewer 97.0% of 300 cells; evaluator-vs-adjudicated
  94.7% of 266 comparisons; 100% on the action-requirement label, both attempt fields, premature and
  unsafe actions; 96.7% missed action; 80.8% grounding; 73.3% deferral.
- **Headline research finding (development/validation, not test):** across 480 held-out episodes, 111
  were `REQUIRED` and **no completed trajectory ever attempted every demanded action** — 105 missed,
  6 unfinished. Prompting fixed format and retrieval, not the decision to act.
- `heldout_v1` is now the development/validation set. `heldout_v2`, the locked test set, does not exist.

## 2. The three things that block the final result

1. **No natural positive cases are left.** All 30 remaining potassium/magnesium cases are negatives
   (audit §1.1). Every order-required case in `heldout_v2` must be synthetic, so **clinical review is
   now a prerequisite, not a nicety**.
2. **The evaluator will change.** Guide v2 and backlog items E1–E3 alter what `APPROPRIATE_DEFER` and
   `grounding_result` mean. They must land *before* `heldout_v2` runs, so the test set is scored once.
3. **The harness cannot seed per case.** Run-level seeds made `heldout_v1`'s repeats swing between
   extremes; per-case intervals are impossible without the change.

## 3. Proposed sequence

| Phase | Work | Gate |
|---|---|---|
| **P0** (done) | v1 outputs frozen: manifest, hashes, read-only (`outputs/human_validation_v1/FROZEN_v1_MANIFEST.md`) | — |
| **P1** | Supervisor decisions below | your review |
| **P2** | Guide v2 + evaluator items E1–E5, landed together; full re-score of `heldout_v1` reported as a new dated section (originals untouched) | D5, D7 |
| **P3** | Partial re-validation of the three changed fields on fresh `heldout_v1` episodes | D7 |
| **P4** | `heldout_v2`: clinical review of synthetic positives, separation checker, per-case seeds, fault injection, lock manifest, pre-registered analysis plan | D1–D4, D6 |
| **P5** | Run arms A0 and A1 on `heldout_v2`; report | — |
| **P6** | Fine-tune; run A2, A3, R1; report once | D8, D9 |

P5 is the point after which the thesis has a defensible test-set result even if fine-tuning is
never finished. I would not reorder P4 and P5.

## 4. Decisions needing supervisor approval

| # | Decision | Why it cannot wait | My recommendation |
|---|---|---|---|
| **D1** | Who clinically reviews the synthetic order-required cases, and is review by a non-clinician supervisor acceptable if no clinician is available? | Blocks `heldout_v2` entirely: there are no natural positives left | Seek a clinician; if none, label the whole positive half "non-clinically-reviewed synthetic challenge cases" in every table and in the abstract |
| **D2** | `heldout_v2` scope: ~27 cases from the two existing task types, or add a third task type? | Changes the policy work and the review burden | Two task types only. A third needs a new policy and review, for little extra power |
| **D3** | Strict patient-level separation (26 cases) or index-level only (30, overlap documented)? | 3 pool cases reuse a dev/v1 patient; 1 patient appears twice inside the pool | Strict: 26 cases. Patient leakage is the harder criticism to answer |
| **D4** | Accept the per-case-seed harness change as a prerequisite? | Without it, no per-case variability estimate | Accept. It is a small change to the task worker |
| **D5** | Freeze the evaluator *now* at the current version, or first land guide v2 + E1–E3? | `heldout_v2` must be scored once, by one version | Land E1–E3 first, then freeze. Scoring the final set with a grounding check that cannot tell an id from a value is not defensible |
| **D6** | How many edge-scenario cases (wrong patient, irrelevant evidence, tool error, conflicting/undated), and is fault injection worth writing? | Decides whether code must be written before locking | Include rows 5, 6, 9, 10 as 1–2 cases each; **skip the tool-error rows** unless you want the fault-injection code |
| **D7** | Does guide v2 require a new human-validation round, and on which episodes? | v1 annotations cannot be re-mapped onto v2 fields | A targeted round on the three changed fields, on fresh `heldout_v1` episodes, reported as partial re-validation |
| **D8** | Is fine-tuning on synthetic positives acceptable, given the test positives are also synthetic? | Goes to the central validity threat | Yes, with different patients and different value bands between train and test, and the risk stated plainly |
| **D9** | Confirm the pre-registered decision rule: fine-tuning counts as an improvement only if the primary action metric improves **and** unsafe/ungrounded counts do not rise | Must be fixed before any result is seen | Confirm as written |

## 5. What I would not do

- Re-score or re-report the v1 validation numbers after the evaluator changes. They are frozen and
  cited as v1.
- Run any arm on `heldout_v2` before the lock manifest exists.
- Use `heldout_v1` for the final comparison, however tempting its 20 cases and existing baselines are.
- Describe any of this as clinical validation. No clinician has reviewed a policy, a threshold or a
  synthetic case to date.

## 6. Honest statement of the risk

If D1 cannot be resolved — no clinician, and a supervisor unwilling to sign off synthetic clinical
cases — then `heldout_v2` cannot contain positive-action cases, and the thesis's central claim stays
where it is today: a measured, reproducible **negative** result on a development/validation set,
with an evaluator validated against two independent human readers. That is a publishable result, but
it is not the result the project set out to produce, and the decision point is now rather than later.
