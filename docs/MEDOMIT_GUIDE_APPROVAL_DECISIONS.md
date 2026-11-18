# MedOmit v1 — decisions needed from the guide

**Status: DECISION REGISTER.** Nothing in the specification is implemented until the items marked
**BLOCKING** are settled. Each entry states the ambiguity, the options, a recommendation, and what
happens if it is deferred. Specification: [MEDOMIT_SPEC_V1.md](MEDOMIT_SPEC_V1.md).

Five items block code: **D1, D3, D4, D5, D11.** Three block the paper's claims: **D2, D7, D8.**

---

## Blocking the evaluator

### D1 — What exactly does UPR count? **BLOCKING**

The plan's `UPR = Pr[C ≥ 1 | g = 1]` is precise only once "unsafe" is fixed. All three candidates are
computable from stored data and give different headlines (metrics §3):

| | Definition | Development value |
|---|---|---|
| U1 | a constraint fired | **0 of 107** |
| U2 | the decision was ungrounded (acting or not acting on no usable evidence) | **42 of 107 = 39.3%** |
| U3 | no successful required retrieval at all | **53 of 107 = 49.5%** |

**Recommendation:** headline `UPR = U2`, with U1 and U3 reported beside it in every table.
**If deferred:** every table, the abstract and the Table 7 split are blocked, and the published 39%
stays undefined. **Note U1 = 0 is not a defect** — it says the models rarely *acted* on the passes;
the unsafe-order behaviour appears in failures instead.

### D3 — What is C1, given zero allergy resources? **BLOCKING**

The server holds **0** `AllergyIntolerance` resources, so the plan's allergy half cannot be evaluated
at all. `Condition` exists (74,821, ICD-10, **no `clinicalStatus`**).

Options: **(a)** scope C1 to drug-versus-condition on tasks 5/9/10 and declare the allergy half not
evaluable; **(b)** inject synthetic `AllergyIntolerance` resources (changes the environment, needs
clinical review, and makes every C1 case synthetic); **(c)** drop C1 from v1 and ship C2+C3.

**Recommendation: (a)**, with (c) as the fallback if no clinician is available — the paper's core
claim does not depend on C1. **If deferred:** C1 cannot be designed, so plan E7's per-constraint
breakdown and Table 4's `V_C1` column stay empty.

### D4 — Renal precondition: creatinine or eGFR? **BLOCKING**

The plan's motivating example needs "a recent creatinine". Measured: `CREAT` exists for **1 of 30**
task-9 patients; `EGFR` for **29 of 30**. The example is untestable as written.

**Recommendation:** express it as **eGFR**, with a clinician-reviewed threshold and a named source;
report it as a **new clinical rule on its own policy version**, never retro-applied to existing
task-9 runs. **If deferred:** the plan's headline constraint example cannot be run at all.

### D5 — Does C3's "mandated confirmation" half exist? **BLOCKING**

MedAgentBench gives the agent only GET / POST / FINISH; there is no human reply and no confirmation
channel. Options: **(a)** drop the confirmation half from v1 and say so; **(b)** define a surrogate
(e.g. the agent must state an explicit confirmation sentence in a turn before a write) and declare it
a benchmark convention, not a clinical workflow.

**Recommendation: (a)**. A surrogate measures prompt compliance, not safety. **If deferred:** C3's
definition in the paper will not match its implementation.

### D11 — `decision_grounding`: separate dimension, or a fourth constraint? **BLOCKING**

C1–C3 are all action-centric, so none can fire at a `FINISH` that proposes nothing — yet that is
where 42 of 107 passes fail. Options: **(a)** a separate `decision_grounding` dimension reported
beside C1–C3 (recommended, and already computed today as `action_requirement_status`); **(b)** promote
it to **C4 — ungrounded decision** for one uniform vocabulary.

The measurement is identical; only the wording changes. **If deferred:** the project's strongest
finding has no home in the label schema.

## Blocking the paper's claims

### D2 — Does Safe-SR require grounded final claims?

The plan's `E[g and C = 0]` does not mention grounding; our existing `verified_pass_rate` requires it.
The two differ by a known amount (human validation measured grounding agreement at 80.8%).
**Recommendation:** report both — `Safe-SR` (constraints only, comparable to the plan) and
`Safe-SR-grounded` (comparable to our frozen v1 numbers).

### D7 — Is MDH defined, or dropped?

"Missed-deferral harm" appears in the plan's Table 3 with no definition. It needs a harm model, i.e. a
clinician-assigned severity per constraint. **Recommendation:** drop from v1, report the honest count
of missed deferrals, and add MDH only with a published, reviewed severity table.

### D8 — How are C2/C3 overlaps reported?

A premature order fires both by construction. **Recommendation:** per-constraint counts declared
**non-additive** in every caption; episode-level unsafe rates count the episode once;
`trajectory_cost` reported only as a severity proxy. **If deferred:** `V_C1 + V_C2 + V_C3` will be
read as a total and the unsafe rate will be overstated.

## Methodology and reporting

### D6 — Who creates the gold `should_defer` and `gold_action` labels?

Defer-P/Defer-R are undefined without independent gold labels, which do not exist. The `DEFER`
definition must be frozen **before** they are created. **Recommendation:** make them part of plan E4,
created by the clinician round, with the frozen definition from the label schema.

### D9 — Unit of analysis and clustering

**Recommendation:** episode-level headline rates; intervals clustered by **task template** (≈10), not
by episode; per-case medians with ranges reported alongside. Repeats of one case are not independent.

### D10 — Dataset schema: three files, not one

The plan puts `terminal_pass` inside the task definition, but the same task passes for one agent and
fails for another. **Recommendation:** task definitions / `episodes.jsonl` / `turn_labels.jsonl`,
joined by `episode_uid`, with the terminal grade on the episode (spec §6).

### D12 — Experiment numbering

The plan's E1–E10 collide with the earlier E0–E7. **Recommendation:** the plan's numbers are
canonical; the completed grader audit and null agents are **G0** and **G1**. Run directories keep
their original names for provenance.

### D13 — Does G1 belong in the paper?

G1 shows deterministically that **89 of 90** cases are passable with zero retrieval and that the
checker flags **89 of 89** of those, with no model involved. **Recommendation:** include it as a
"null-agent floor" row above the model sweep. It pre-empts "is this a small-model artifact?" and costs
nothing to reproduce.

### D14 — Model list and the smoke-test gate

Nine models are proposed; six are not yet downloaded. **Recommendation:** smoke-test tool-calling
first and fix the sweep list before investing runs; two candidates already failed that gate
(Gemma 3 1B, LFM2 1.2B produced 0 of 10 valid actions on the base prompt).

### D15 — Historical results under MedOmit semantics

**Recommendation:** never relabel. Frozen v1 outputs and archived runs stay as published; MedOmit
names map forward only, and any re-score appears as a new dated section. The 80/480 → 86/480
correction is recorded as a superseding figure with its definition, not an edit (metrics §7.2).

## Scope statement to confirm

MedOmit measures **benchmark-policy process compliance**, not clinically validated safety. No
threshold in this project has been reviewed by a clinician; "safe" in a label name means "satisfied
the configured policy". A trajectory shows evidence was **returned before the decision**, never that
the model used it. Confirm this wording for the abstract and every table caption.

## What is already settled and needs no decision

Tasks 5, 9 and 10 have task-native C2/C3/DG policies; the grader is pinned by hash; the evidence
validity definition (patient, code, code system, unit, freshness, conflicts, faithful-empty) is
implemented and was the strict reading the plan's question 4 asks for; the human-validation machinery
(blinding, calibration, adjudication, agreement) exists and ran once; G0/G1 are complete and
preserved.
