# Clinical review sheet: 8 synthetic order-required cases (`heldout_v1`)

**Status: NOT REVIEWED.** Do not use these cases for further evaluation until a clinician (or the supervisor) has signed below.

## Why these cases exist

MedAgentBench has only 3 natural cases that need an order among its 60 potassium (task9) and magnesium (task5) cases. To test whether a model orders when it should, one new, newest lab result with a low value was added for 8 held-out patients on the local FHIR server. Nothing else about the patient or the task was changed. The values were chosen by the student to cover each dose band; no clinician chose them.

Reference time in every task: 2023-11-13 10:15 UTC.

## Potassium (task9): oral replacement

Task rule (from the benchmark text): for every 0.1 mmol/L below 3.5, order 10 mEq oral potassium; also order a serum potassium for 8 am the next day.

| # | Case index | Patient | Previous latest K (time) | **Added K** (2023-11-13 09:00) | Expected order by the task rule | Reviewer: plausible? (Y/N) | Reviewer: expected order correct? (Y/N) | Comment |
|---|---|---|---|---|---|---|---|---|
| 1 | 246 | S6268253 | 5.4 (11-12 13:35) | **3.4** | 10 mEq oral + next-day K | | | |
| 2 | 260 | S6426560 | 4.6 (11-12 13:04) | **3.3** | 20 mEq oral + next-day K | | | |
| 3 | 249 | S3084624 | 4.0 (11-13 06:40) | **3.2** | 30 mEq oral + next-day K | | | |
| 4 | 252 | S3057899 | 4.5 (11-12 23:31) | **3.0** | 50 mEq oral + next-day K | | | |
| 5 | 255 | S2823623 | 4.1 (11-13 03:35) | **2.8** | 70 mEq oral + next-day K | | | |

## Magnesium (task5): IV replacement

Task rule (from the benchmark text): Mg 1.5 to 1.9 mg/dL → 1 g over 1 h; 1 to <1.5 → 2 g over 2 h; <1 → 4 g over 4 h. Only a result from the last 24 h counts.

| # | Case index | Patient | Previous latest Mg (time) | **Added Mg** (2023-11-13 09:30) | Expected order by the task rule | Reviewer: plausible? (Y/N) | Reviewer: expected order correct? (Y/N) | Comment |
|---|---|---|---|---|---|---|---|---|
| 6 | 136 | S6192632 | 2.3 (11-12 14:18) | **1.6** | 1 g IV over 1 h | | | |
| 7 | 127 | S1891852 | 1.6 (11-09 13:28, older than 24 h) | **1.4** | 2 g IV over 2 h | | | |
| 8 | 131 | S2016972 | none on record | **0.8** | 4 g IV over 4 h | | | |

## Questions for the reviewer

1. **Size and speed of the drops.** Several values fall a long way in a short time (case 1: 5.4 → 3.4 in about 20 h; case 4: 4.5 → 3.0 in about 10 h; case 3: 4.0 → 3.2 in about 2.5 h). Are these acceptable for a test case, or should the values be closer to the previous result?
2. **Single dose size.** The task rule gives 50 mEq and 70 mEq oral potassium as one order (cases 4 and 5). Is that acceptable as the "correct" answer for evaluation, given it is the benchmark's own rule?
3. **Other context.** The synthetic value was added without looking at the patient's renal function, medications or diagnoses. Should any patient be excluded because an order would be inappropriate for another reason?
4. **Definition of "low".** The evaluator's action-requirement rules use potassium **< 3.5** and magnesium **≤ 1.9** within 24 h, both quoted from the task text and the reference grader. Is that the right definition of "an order is required" for this study?
5. **Task 9 has no freshness window.** The reference grader uses the most recent potassium of *any* age, and the evaluator mirrors it for benchmark compatibility, so an old potassium can make an order "required". Should the study keep benchmark compatibility, add a clinical freshness window (a new rule that would need your sign-off), or report both?
6. **Severe values.** Would Mg 0.8 or K 2.8 need escalation in practice (not only replacement)? If so, should those cases be kept, changed, or labelled differently?

## Sign-off

| Reviewer | Role | Date | Decision (approve all / approve with changes / reject) |
|---|---|---|---|
| | | | |

Changes requested:
