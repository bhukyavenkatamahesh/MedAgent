# MedOmit — independent test split proposal (D3 revised)

Prepared 2026-11-18. **Proposal; nothing is locked by this document.**

D3 as revised: the 60 G2 cases have been inspected and must not be described as untouched held-out
data. They are **audited development / evaluator-validation** cases. This document reclassifies
every case accordingly and proposes what a defensible final test set can actually be.

## 1. The governing rule

> A test is not unseen because no language model has been evaluated on it. It is seen if **we**
> looked at it — read its reference answers, measured its distributions, or tuned a policy against it.

By that rule, tasks 4 and 7 became development data the moment the G2 audit computed their 60
reference answers. No amount of "no model has run on them" changes that.

## 2. Exposure register

| Tier | Task types | Cases | What was looked at | Usable as a final test set? |
|---|---|---|---|---|
| **T1 — Development (model-exposed)** | 5, 9 | 480 episodes over 20 cases × 24 runs | reference answers, per-episode labels, 42/107 analysis, two reviewer rounds | **No** |
| **T2 — Development (evaluator-exposed, G1)** | 5, 9, 10 | 90 | every reference answer recomputed; task-10 policy written *in response* to the result | **No** |
| **T3 — Development (evaluator-exposed, G2)** | 4, 7 | 60 | every reference answer recomputed; 19 sentinel cases identified; both policies written against the findings | **No** — this is the D3 reclassification |
| **T4 — Clinician annotation pool** | 5, 9 (v1); to be chosen for v2 | 30 annotated | trajectories read by two reviewers and adjudicated | Not a model test set; a *measurement of the evaluator* |
| **T5 — Never inspected** | 1, 2, 3, 6, 8 | 150 | nothing: no answer computed, no distribution measured, no policy written | **Yes, candidate** |

Everything in T1–T3 is development data. The thesis must say so.

## 3. Patient-disjointness is not achievable in MedAgentBench, and here is the arithmetic

Measured from `test_data_v2.json` on 2026-11-18:

- The whole benchmark contains **98 distinct patients** for 300 cases.
- Tasks 4, 5, 7, 9 and 10 together already touch **87 of those 98**.
- Patients shared between task types are the norm, not the exception: task4∩task10 = 10,
  task9∩task10 = 10, task5∩task7 = 10, task4∩task7 = 8, task4∩task9 = 8.
- Across the five never-inspected task types there are 79 patients, of which only **11 are disjoint
  from every exposed case**.

| Never-inspected type | Patients | Disjoint from all exposed |
|---|---|---|
| task1 (MRN lookup) | 28 | 5 |
| task2 (age) | 30 | 2 |
| task3 (record a BP) | 30 | 7 |
| task6 (average CBG over 24 h) | 30 | 3 |
| task8 (referral order) | 30 | 4 |
| **union** | **79** | **11** |

**A strictly patient-disjoint final test set would hold about 11 patients.** That is too small to
estimate anything with useful precision, so patient-disjointness cannot be the design. It must be
replaced by *case and task-type novelty plus patient-clustered uncertainty*, with the overlap
declared.

## 4. Proposal

### 4.1 Primary final test set — **task 6** (30 cases)

"What is the average CBG of the patient `<MRN>` over the last 24 hours?" Read-only
(`check_has_post`), glucose evidence, a 24-hour window, and an **aggregate** answer.

Why task 6:
- Never inspected: no reference answer computed, no distribution measured, no policy written.
- It reuses the evidence machinery tasks 4 and 7 exercise (code `GLU`, a 24-hour window), so it
  tests the built evaluator rather than requiring a new one.
- It is a genuinely harder grounding case, which is the point of a final test rather than a
  repetition.

One prerequisite, and it is a real evaluator gap: **the answer is a computed mean, not a retrieved
value**, so today's answer-grounding check — "does this number equal a value in the read set" — would
score every correct task-6 answer as `not_retrieved`. Task 6 therefore needs an aggregate-claim rule
(a stated number that equals a declared aggregate over the qualifying read set counts as supported)
before it can be used. That work must be specified, implemented and **frozen before any reference
answer for task 6 is computed**, or task 6 becomes development data exactly as tasks 4 and 7 did.

### 4.2 Secondary set — **task 2** (30 cases), optional

Patient age from the record. Read-only, trivially gradeable, and it tests decision grounding on a
`Patient` resource rather than an `Observation`. Cheap to add; adds breadth, not depth.

### 4.3 Explicitly excluded from the final set

- **Tasks 4, 5, 7, 9, 10** — development (T1–T3).
- **Tasks 3 and 8** — unconditional writes requiring no prior evidence, so decision grounding is
  `not_applicable` and they cannot test the central claim.
- **Task 1** — the patient identity is the *answer*, not an evidence input, so it tests a different
  question.

### 4.4 The locking procedure

Do these in order, and record each step in the run manifest:

1. Approve the split (this document) and the aggregate-claim rule for task 6.
2. Implement and freeze the evaluator, policies, grader hash and label schema. Record the evaluator
   source hash in the manifest.
3. **Only then** compute task-6 reference answers, and compute them *once*, as part of the scored
   run — never as a prior audit.
4. Lock the case list, per-case seeds, model digests and prompt text before any inference.
5. Report results with uncertainty clustered **by patient**, not by case, because patients recur.
6. Report natural and synthetic positives separately.

### 4.5 Limitations to state in the thesis, not bury

1. **Patient overlap is unavoidable**: task 6's 30 patients include 27 that appear in exposed cases.
   Inference must be patient-clustered and the overlap stated numerically.
2. **The simulator is one fixed snapshot.** Every "patient" is the same synthetic record across all
   task types, so task-type novelty is not population novelty.
3. **One task type is a narrow test.** 30 cases bound the precision of any single estimate; the
   finding that generalises is the *existence* result, not a rate.
4. **No external validity.** Nothing here speaks to a real EHR, a real clinician workflow, or a
   phone.
5. **The evaluator was built by the same person who runs it.** The clinician audit (plan E4) remains
   the gate, independent of this split.

## 5. What this changes about claims already made

Nothing in the measured results changes. What changes is their label: the 19/60 evidence-free passes
and the 89/90 G1 result are **development findings on inspected cases** — which is exactly what an
existence proof needs, and is not weakened by being development data. The final test set exists to
estimate *rates*, and no rate from T1–T3 may be presented as a held-out estimate.
