# MedOmit — next milestone report (Steps 1–4 and 6)

**Date:** 2026-11-18. **Baseline:** branch `main`, HEAD `e90748b`, **281 tests passing**.
**Nothing was committed or pushed. No policy, evaluator rule, clinical rule or frozen result was
changed. No experiment was run.**

---

## 1. Completed work (verified this session)

| Check | Result |
|---|---|
| Branch / HEAD | `main` / `e90748b` |
| **Unpushed local commits** | **3**: `e90748b`, `15d7060`, `26431c6` — the public GitHub repository does **not** contain G0/G1 or the Phase 0 audit |
| Working tree | clean except untracked MedOmit specification documents |
| Test baseline | **281 passed**, before and after this session |
| Frozen human-validation v1 | **11 of 11 hashes `OK`**, files still read-only |
| G0 / G1 outputs | present and unmodified |
| Tasks 5 / 9 / 10 policies | unmodified (`git status` on `policies/` and `procsafe/` is empty) |

## 2. Verified findings (new evidence, reproducible)

**F1 — 42/107 and 53/107 are nested, and the stricter figure is defective.**
`U2 ⊂ U3`; `U2 \ U3 = 0`; `U3 \ U2 = 11`. All **11** differing episodes are **the same case**
(`task5_9#128`, patient `S3195056`) observed in 11 runs. In every one the agent issued a faithful
`code=MG&patient=…` query, received an **empty bundle**, and correctly did not order — which is exactly
what task 5 instructs. `RETRIEVE_REQUIRED` never fires on an empty result, so the 53/107 definition
labels that correct behaviour "ungrounded". **42/107 = 39.3% is the sound figure**; 53/107 is a
sensitivity check with a known defect, and its excess rests on one patient, not 11 independent
observations.

**F2 — 80/480 and 86/480 are both correct and nested.**
`80` = episodes the harness refused to grade (`agent invalid action`), identical to
`terminal_result is null`. `86` = episodes with no parsable terminal `FINISH`. `80 ⊂ 86`. The six extra
episodes are all **truncated `FINISH(` payloads** — the model ran out of output tokens, the harness
accepts a terminal action by prefix and grades it `FAIL`, our adapter requires a balanced closing
parenthesis and records `INVALID_ACTION`. Three of the four categories named in the brief (invalid
response, incomplete trajectory, no `FINISH`) coincide at 86 on this data. **The plan's 80/480 is
correct for its definition and needs no correction** — my earlier note that it was "slightly off" was
wrong, and this report supersedes it.

**F3 — The environment constrains C1 and the renal C2 more sharply than the plan assumes.**
`AllergyIntolerance` = **0** resources; `Condition` = 74,821 in ICD-10 **with no `clinicalStatus`**;
`CREAT` exists for **1 of 30** task-9 patients while `EGFR` exists for **29**.

**F4 — Tasks 4 and 7 are genuinely read-only and mostly free to add**, but two traps exist: the
deferral label would mislabel stale-evidence task-4 cases, and **19 of 30 task-4 reference answers are
`-1`**, which today's grounding check would report as ungrounded.

**F5 — Reproducibility is the weakest part of the pipeline.** No per-case seeds, no model digest, no
prompt version, no repeat id, no simulator snapshot and no policy hashes are recorded in any run
artefact; model/prompt/repeat exist only in directory names, which already caused one real analysis
bug.

## 3. Proposed changes (not implemented)

| Proposal | Document | Blocking approval |
|---|---|---|
| Keep **UPR** as the plan defines it; add **UGR** for the 39.3%; **UGR-strict** as sensitivity | `MEDOMIT_METRIC_RECONCILIATION.md` | D1 |
| Report `ungraded_rate` (80) and `incomplete_trace_rate` (86) separately with one explanatory sentence | same | — |
| `FINISH_TRUNCATED` as its own adapter status | same | — |
| C1 scoped to drug-versus-condition; allergy half declared not evaluable | `MEDOMIT_GUIDE_DECISIONS_RECOMMENDATION.md` | **D3, clinician** |
| Renal precondition expressed as eGFR, new policy version, never retro-applied | same | **D4, clinician** |
| C3 confirmation half dropped from v1 | same | D5 |
| `decision_grounding` as a separate dimension, not a stretched C2 | same | D11 |
| `conditional_action: false` for read-only task policies | `TASK4_TASK7_IMPLEMENTATION_PLAN.md` | task-scope approval |
| Two new v1 policies for tasks 4 and 7, plus 15 regression tests | same | task-scope approval |
| Run manifest, `episode_uid`, per-case seeds, resource side-log, output-isolation guard, scorer provenance | `MEDOMIT_REPRODUCIBILITY_AUDIT.md` | — |

## 4. Changes actually implemented this session

**One analysis script, no behaviour change:** `scripts/medomit_metric_reconciliation.py` (read-only;
writes only into its `--out` directory). Nothing else. No policy, evaluator, test, frozen output or
archived run was touched, and nothing was committed.

## 5. Decisions requiring supervisor approval

**D1** UPR definition · **D3** C1 scope · **D4** renal marker · **D5** C3 confirmation ·
**D11** decision grounding — each with the eight-part analysis and the exact question to ask in
`MEDOMIT_GUIDE_DECISIONS_RECOMMENDATION.md`. Plus the **task-scope expansion** to tasks 4 and 7.

Settleable immediately, without a clinician: D1, D5, D11, task scope.

## 6. Work blocked by clinical validation

| Blocked | Why |
|---|---|
| **C1** in any form | an ICD-10 → contraindicated-drug-class mapping is a clinical rule |
| **Renal C2** (the plan's flagship example) | both the marker (eGFR vs creatinine) and the threshold need review |
| **Plan E4**, the credibility gate | needs ≥ 1 qualified clinician, ~36 tasks, 100–150 turns, κ or ρ, and independent gold labels |
| `V_C1` column, plan E7 breakdown | depend on C1 |
| Any "clinically safe" wording | nothing in this project has been clinically reviewed |

Clinician recruitment is the longest-lead item and gates four deliverables. It should start in
parallel with engineering, not after it.

## 7. Next actions, in order

1. **Supervisor:** settle D1, D5, D11 and the task-scope expansion (no clinician needed).
2. **Supervisor:** start clinician recruitment for D3, D4 and E4.
3. **Engineering, unblocked now:** reproducibility group R1 + R2 + R5 + R7 (manifest, `episode_uid`,
   output guard, scorer provenance) — small, no scoring change.
4. **Then:** backlog E9 (sentinel grounding) — a prerequisite for task 4, where 19 of 30 answers are `-1`.
5. **Then:** `conditional_action`, the two read-only policies, the 15 regression tests, and a **G1
   null-agent dry run** over the 60 cases as a free negative control before any model runs.
6. **Then:** per-case seeds (R3) and the resource side-log (R4), before any sweep.
7. **Not yet:** the locked split, the model sweep, C1, the renal constraint, fine-tuning.

## 8. Plain-English summary for your supervisor

> We checked your plan's numbers against our saved data, episode by episode.
>
> Your "39%" is sound, and we can now say exactly what it means: of the 107 episodes the benchmark
> marked as passes, 42 were decided without the agent ever having usable evidence. A stricter way of
> counting gives 53, but we found that stricter count is wrong — all 11 extra episodes are the *same
> patient*, where the agent did the right thing: it searched for magnesium, found none in the last 24
> hours, and correctly ordered nothing. Counting that as a failure would punish correct behaviour, so
> we recommend keeping 42 as the headline and reporting 53 only as a cross-check.
>
> Your "80 of 480 invalid" is also correct. Our figure of 86 counts something slightly different —
> trajectories that never produced a readable final answer. The six-episode gap is explained: those
> agents started writing their answer and ran out of space mid-sentence, so the benchmark graded them
> while our tool refused to read them. Both numbers stay, each with its definition.
>
> Three things in the plan need your decision because the simulator cannot support them as written.
> There are **no allergy records at all** in the simulator, so C1 can only check drugs against recorded
> conditions. **Creatinine exists for only 1 of our 30 potassium patients** while eGFR exists for 29, so
> the kidney-function example has to use eGFR — and that is a clinical change needing a clinician, not a
> rename. And the simulator has **no way for a human to confirm an order**, so C3's confirmation half
> cannot be measured; we suggest listing it as future work.
>
> One more definition point: all three of your constraints describe an agent *doing* something, but our
> strongest result is about agents that correctly did *nothing* and still passed without looking. We
> suggest reporting that as its own "decision grounding" measure beside C1–C3, so your constraint
> definitions stay exactly as you wrote them.
>
> We can add the two query tasks (4 and 7, 60 more cases) with no new clinical rules, which would give
> your Table 7 its query-versus-action split for the first time. Two small fixes are needed first, both
> identified and specified.
>
> Nothing has been changed in the code or in any earlier result. We are waiting on five decisions, two
> of which need a clinician.
