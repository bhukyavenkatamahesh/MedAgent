# Benchmark coverage: improving the evaluator with more data, not more training

**Status: PLAN plus one completed step.** MedAgentBench holds **10 task types × 30 cases = 300**.
The study covered 60 (tasks 5 and 9); task 10 is now covered as well, giving **90**. This document
surveys the remaining 210 cases, says what each task type would let the evaluator measure, and orders
the work. Nothing here requires fine-tuning, a new model, or a synthetic case.

Source for every classification: the reference grader's own code (`refsol.py`, pinned at sha256
`67d19da2…`, line numbers cited in `runs/E0_grader_audit/`) and the task instructions.

## The three families

| Family | Task types | Cases | Grader's rule | What the evaluator can measure |
|---|---|---|---|---|
| **A. Check-then-order** | 5, 9, **10** | 90 | a POST is expected only when the evidence triggers it | the full action dimension: required / not required / undetermined, missed, unnecessary, premature, unsafe |
| **B. Retrieve-and-answer** | 1, 2, 4, 6, 7 | 150 | **any POST fails the case**; the answer must match a reference value | evidence grounding of the answer, retrieval quality, and `UNEXPECTED_WRITE` on a task where no write is ever legitimate |
| **C. Unconditional write** | 3, 8 | 60 | exactly one POST is always expected | omission of an always-required action, and write correctness |

Family A is the thesis's core and is now complete: **all three check-then-order task types have a
policy** (`mab_task5_magnesium_v2`, `mab_task9_potassium_v2`, `mab_task10_hba1c_v2`).

## Why family B is the best next step

| | |
|---|---|
| Size | **150 cases**, 1.7× the current coverage, all natural benchmark data |
| Alignment | the grader *forbids* any POST on these tasks, and the checker's `allowed_writes: []` already makes any POST an `UNEXPECTED_WRITE`. Two independent definitions of the same failure |
| Relevance | the first SLM pilot showed Qwen 2.5 1.5B writing **invented lab Observations** to the chart. On a read-only task that is unambiguously wrong, and measurable at scale |
| Cost | no new evaluator concept for tasks 4 and 7: the expected answer *is* the returned value, so grounding works as-is |

**Recommended order inside family B:**

1. **task4 (magnesium, last value in 24 h) and task7 (CBG, most recent value)** — 60 cases. The
   answer is exactly the value that was returned, so the existing grounding check applies unchanged;
   the evidence rules are the ones task 5 and task 9 already use. **Lowest effort, highest value.**
2. **task2 (patient age)** — 30 cases. The answer is *derived* (age from `birthDate`), so numeric
   grounding cannot match it against a returned value. Depends on the grounding work in backlog
   E2/E3/E9.
3. **task6 (average CBG over 24 h)** — 30 cases. The answer is an aggregate of several returned
   values; needs an "aggregate claim" notion. Same dependency as task 2, plus a decision on tolerance
   (the grader allows ±0.1).
4. **task1 (find the MRN from a name and date of birth)** — 30 cases. The patient is *not* given, so
   evidence is a demographic search rather than a patient-matched observation. This breaks the
   evaluator's central assumption that evidence is validated against a known MRN, and needs a design
   decision first. **Lowest priority.**

## Family C, and what it adds

Tasks 3 and 8 always require exactly one POST (an `Observation` for a blood-pressure reading, a
`ServiceRequest` for a referral), with no evidence prerequisite: the data to record is in the prompt.
They exercise a different corner: **omission of an action that is always required**, where the
action-requirement status is `REQUIRED` unconditionally and no retrieval is expected. They also give
the only natural test of write correctness outside family A. Worth doing after family B step 1; they
need no new evaluator concept, only a policy with an unconditional requirement.

## What this changes about the test set

The `heldout_v2` readiness audit concluded that a locked test set would need synthetic positive cases
because tasks 5 and 9 have no natural order-required cases left. With task 10 that is already false
(17 natural positives). Extending to families B and C changes the picture further: **a locked test
set could be built entirely from natural benchmark data**, with positive-action cases from task 10,
read-only cases from tasks 4 and 7, and always-required actions from tasks 3 and 8. Synthetic cases
would then be needed only for the deliberate edge scenarios (wrong patient, conflicting or undated
evidence), which are software tests rather than clinical ones.

## Honest limits of this route

- Coverage is **breadth, not depth**: more task types strengthen the claim that the grader-process gap
  is general, but they do not make any single measurement more precise.
- Each new policy is a new place for a wrong rule, and each needs the same discipline: thresholds
  quoted from the task text or the grader, `review_status` recorded, and no clinical rule invented.
- Families B and C do **not** test the action-requirement dimension that the thesis is built on. Only
  family A does, and family A is now exhausted at 90 cases.
- None of this substitutes for E4 (independent human validation of the revised labels) or for the
  locked-set run E2.
