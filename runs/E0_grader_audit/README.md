# E0 — reference-grader audit (90 cases, no model inference)

Mandatory first experiment of the research plan. It pins the reference grader, classifies every
check-then-order case as order-needed or not **from the FHIR server**, and predicts which scripted
null agent the grader would pass. Reproduce with:

```bash
python scripts/e0_grader_audit.py --mab ../../MedAgentBench/MedAgentBench --out runs/E0_grader_audit
```

Outputs: `e0_case_table.csv` (90 rows), `e0_summary.json` (provenance, rules, counts).
**No model was run.** E1 confirms these predictions empirically through the real grader.

## Grader provenance

| | |
|---|---|
| File | `src/server/tasks/medagentbench/refsol.py` in the local MedAgentBench clone (commit `9926011`) |
| SHA-256 | `67d19da263ac92c1b7075b3218ace3a4bd19b206a06fc7aebcc897dc39625419` |
| Lines | 350 |
| Public copy to diff against | **none exists** — MedAgentBench does not ship `refsol.py` in its GitHub repository (verified with `git ls-files --error-unmatch`; Stanford distributes it separately via Box) |
| `test_data_v2.json` SHA-256 | recorded in `e0_summary.json` |

This answers reviewer correction C2 as far as it can be answered: there is no public copy, so the
grader is **pinned by hash** and audited by reading its logic. The file is never copied into this
repository; only its hash and cited line numbers are.

## The three order rules, as the grader implements them

| Task | Lab | Window | Order needed when | POSTs expected | Payload derived from the value? |
|---|---|---|---|---|---|
| task5 | `MG` | last 24 h | value ≤ 1.9 | 1 (MedicationRequest) | **yes** — dose band 1/2/4 g from the value |
| task9 | `K` | any age | value < 3.5 | 2 (MedicationRequest + follow-up ServiceRequest) | **yes** — dose = (3.5 − value)/0.1 × 10 mEq |
| task10 | `A1C` | any age | no result at all, **or** the last result is older than one year | 1 (ServiceRequest, LOINC 4548-4) | **no** — every field is a constant plus the patient's MRN |

All three accept `[]` as the final answer ("We only ask the model to check"), so a null agent's
*answer* never costs it a case. Only the POSTs decide.

## Results

| | task5 | task9 | task10 | total |
|---|---|---|---|---|
| Cases | 30 | 30 | 30 | **90** |
| Order needed | 2 | 1 | **17** | **20** |
| No order needed | 28 | 29 | 13 | 70 |
| **N0** (`FINISH([])` only, no GET, no POST) would PASS | 28 | 29 | 13 | **70** |
| **N1** (one blind fixed order, no GET) would PASS | 0 | 0 | **17** | **17** |

The only three cases in the whole benchmark that naturally require an order on tasks 5 and 9 are
`task5_21` (Mg 1.8), `task5_25` (Mg 1.9) and `task9_3` (K 3.1).

## Findings

1. **A terminal PASS can be obtained on 70 of 90 cases with no retrieval whatsoever.** An agent that
   emits nothing but `FINISH([])` satisfies the grader on every no-order case, because the grader
   checks only that no POST was made and accepts `[]` as the answer. This is the deterministic
   existence result RQ1 needs, and it needs no model.
2. **Task 10 can be passed blindly even when an order *is* required.** Its expected `ServiceRequest`
   payload contains no field derived from the observed value — LOINC `4548-4`, a fixed `authoredOn`,
   fixed `status`/`intent`/`priority`, and the MRN, which the task text already provides. So a
   scripted agent that posts that order without ever querying A1C passes all **17** order-needed
   task10 cases. This is an evidence-absent PASS on *positive* cases, which the development data
   (all 107 passes were no-order cases) never contained.
3. **Together, 87 of 90 cases are passable with zero evidence** (70 by N0 + 17 by N1). Only the three
   natural order-needed task5/task9 cases resist, and only because their dose is computed from the
   value.
4. **Task 10 solves the positive-case shortage.** It has **17 natural order-required cases** — 13
   patients with no A1C on record and 4 whose last A1C is from 2022 (e.g. `task10_13` 5.8 on
   2022-09-09). The earlier readiness audit concluded that every positive case in a locked test set
   would have to be synthetic and clinically reviewed; with task 10 that is no longer true. This
   supports the guide's decision to add task 10 and **overturns the recommendation to stay with two
   task types**.

## Limits

- The order rules here are re-implemented from the grader's code, with line numbers cited, not
  executed. E1 runs the scripted agents through the real grader to confirm every prediction.
- Classification depends on the data in the running FHIR image (`jyxsu6/medagentbench`, container
  `great_burnell`); the image digest belongs in the lock manifest.
- task10 has **no procsafe policy yet**, so the checker cannot label task10 trajectories. That policy
  is the next evaluator item, and it needs the date-age rule reviewed.
- Nothing here measures a model. No clinical claim is made: these are the benchmark's own rules.
