# MedOmit — progress analysis against the guide's plan

Date: 2026-11-18. Covers everything built up to and including Milestone 3.
Tests: **465 passing, 0 failing.** Benchmark coverage: **150 of 300 cases**, 5 of 10 task types.

This is an honest audit, not a status boast. Where something is only partly done it says so, and
where a number is a development figure rather than a test-set figure it says that too.

---

## 1. The one-paragraph summary

The **evaluator is built, tested and backward-compatible**, and it now runs inside a reproducibility
harness that captures its own provenance. We have shown, three independent ways, that a benchmark
PASS does not prove the agent received the evidence the task required. What we have **not** done is
the part that makes those findings publishable as *rates*: no clinician has validated the labels, no
locked test set exists, and the model sweep has not been run. Every headline number so far is a
**development** number on cases we have inspected.

---

## 2. The plan's experiments, E1–E10

| Plan item | What it asks for | Status | Evidence / what is missing |
|---|---|---|---|
| **E1** | model sweep, 7–9 SLMs × 10 task types × R reps | **~8% done** | 2 of 9 models; **5 of 10 task types** have policies (was 3); R=3 but with one seed per run. Per-case seeds now exist, so the blocker is removed |
| **E2** | Terminal SR vs Safe-SR per model | **method done, data narrow** | computed on 480 episodes, 2 models, 2 task types. Needs the sweep |
| **E3** | failure-mode decomposition | **largely done** | the plan's Table 6 is filled from our pilot |
| **E4** | clinician audit, κ/ρ, ~36 tasks, 100–150 turns | **protocol drafted, gate UNMET** | `MEDOMIT_E4_CLINICIAN_PROTOCOL.md` v0.1. Our 30-episode two-reviewer study (97.0% reviewer agreement, κ 0.714–1.000; 94.7% evaluator-vs-adjudicated) is explicitly **not sufficient** — neither reviewer was a clinician. **No clinician is appointed** |
| **E5** | size scaling 1B → 8B | **not started** | needs more models; 6 are installed locally |
| **E6** | R=5 with CIs clustered by template | **unblocked, not started** | was blocked on per-case seeds, which now exist and are measured |
| **E7** | per-constraint breakdown | **blocked on C1** | and C1 is blocked by absent data, not by effort |
| **E8** | safety-prompt intervention | **partly** | 4 prompt conditions run, but measured on format and retrieval, not UPR |
| **E9** | does Terminal SR predict Safe-SR | **not started** | needs ≥5 models. (Distinct from our local backlog item, renamed **L1**, which is done) |
| **E10** | harness sensitivity (ReAct vs plain) | **not started** | — |

**Reading:** the plan's *method* work is largely done; the plan's *measurement* work has barely
started, and it is gated by E4 and the lock, in that order.

---

## 3. The three constraint templates

| | What it is | Status |
|---|---|---|
| **C1** contraindication | drug vs recorded allergy/condition | **UNIMPLEMENTABLE in this environment.** The simulator holds **0** `AllergyIntolerance` resources and 74,821 `Condition` rows with **no** `clinicalStatus`, so "active condition" cannot be established. No approval fixes this; it needs different data or a different environment |
| **C2** precondition check | lab absent or stale before an action | **BUILT** for benchmark-native preconditions (tasks 5, 9, 10). The renal variant is a new clinical rule and stays inert |
| **C3** unsafe write | a guarded write lacking its read, or an absent mandated confirmation | **BUILT** except the "mandated confirmation" half, which the benchmark never asks for |
| **decision grounding** | *our addition* — committing to act **or not to act** without usable evidence | **BUILT**, and now a first-class field. This is what carries the headline finding, because none of C1–C3 can fire at a FINISH that proposes nothing |

---

## 4. What is actually finished

### 4.1 The evaluator

Adapter → schema → evidence mapper → per-turn safety checker → metrics → report. Five scoring
dimensions reported separately and never merged: `terminal_result`, `process_result`,
`grounding_result` (answer grounding), `decision_grounding`, `action_requirement_status`, combined
into `verified_outcome`.

Five task types with policies, every rule quoted from the task text or the reference grader:

| Task | Type | Policy |
|---|---|---|
| 5 magnesium | check-then-order | `mab_task5_magnesium_v2` |
| 9 potassium | check-then-order, two required actions | `mab_task9_potassium_v2` |
| 10 HbA1C | check-then-order, age trigger, absence is the trigger | `mab_task10_hba1c_v2` |
| 4 magnesium query | read-only, 24 h window, task-defined `-1` sentinel | `mab_task4_magnesium_query_v1` |
| 7 CBG query | read-only, no window, **no sentinel** (the task defines none) | `mab_task7_glucose_query_v1` |

### 4.2 The three existence results

| Experiment | Finding |
|---|---|
| **G0/G1** (tasks 5/9/10, scripted agents, no model) | **89 of 90** cases pass with zero retrieval. Only `task9_3` resists, because its dose is a continuous function of the value |
| **G2** (tasks 4/7, scripted agents, no model) | **19 of 60** read-only cases pass with zero retrieval, by stating the task's own `-1` sentinel. Task 7 resists completely: its answer is always a measured value |
| **Development runs** (2 models, 480 episodes) | **42 of 107** passing episodes had no valid preceding evidence (39.3%) |

All three are **existence proofs on inspected cases**, which is exactly what an existence proof
needs — and none of them is a held-out rate.

### 4.3 Reproducibility (D4: 4 of 5 complete)

Per-case seed injection via a proxy (the agent cannot carry it: the harness copies a static body and
never sees the case); model digest + quantization; prompt template and few-shot block hashes;
simulator **state** fingerprint (not just the image digest) computed before and after every run with
a mutation flag; experiment/episode IDs; output-directory isolation; and the five separate views of
every output. A launcher captures all of it automatically, writing a pre-run manifest so metadata
survives a crash.

**Measured, not assumed:** the seed **is** honoured by Ollama 0.40.16 for both 1B-class models — but
the **first generation after a model load is a different deterministic regime** from the warm one at
the identical seed, reproducibly so. A final run must warm the model and record cold/warm per
episode.

**Three tiers, kept apart:** auditable re-scoring **established** (660 episodes, 0 label changes);
approximate reproducibility **demonstrated** (two executions of a 2-case run, byte-identical, every
fingerprint matching); complete reproducibility **not demonstrated** and not claimed.

### 4.4 Human validation v1 (frozen)

30 episodes, two independent reviewers, blinded, adjudicated: 97.0% of 300 cells agreed
(κ 0.714–1.000, one undefined), evaluator-vs-adjudicated **94.7%** of 266 comparisons. Frozen with
checksums. **This is a precursor, not E4.**

---

## 5. What remains, in dependency order

| # | Work | Blocked by | Who |
|---|---|---|---|
| 1 | **Resource side-log** — peak RSS, time to first token, tokens/sec, wall time, tool-call validity | nothing | us |
| 2 | **Pristine simulator baseline** after a container recreate | nothing | us |
| 3 | **Model warm-up** in the launcher + cold/warm recorded per episode | nothing | us |
| 4 | **Wire the computed-answer (aggregate) rule** | **your approval** | you → us |
| 5 | **Approve the independent-test split** | **your approval** | you |
| 6 | **Freeze and hash the evaluator**, lock policies, grader, test set, seeds | 1–5 | us |
| 7 | **E4 clinician audit** | **a named clinician** | you → us |
| 8 | **Model sweep** (E1/E2), then E3, E5, E6, E9 | 6 and 7 | us |
| 9 | **C1 / renal rules** | clinical review **and** absent data | you + a different environment |
| 10 | Fine-tuning, if its six gates are met | 7 and 8 | optional |

### The four things only you can unblock

1. **A named clinician**, with availability for ~36 episodes / ~120 turns. This gates E4, which gates
   every rate in the thesis. It is the single longest-lead item and has been open the longest.
2. **Approval of the aggregate rule** (`MEDOMIT_TASK6_COMPUTED_ANSWER_SPEC.md` v1.0) so task 6 can be
   scored at all.
3. **Approval of the test split**, accepting that task 6's positive/negative balance stays unknown
   until the scored run.
4. **A decision on C1 and the renal rule** — including the possibility that C1 is simply out of
   scope for this environment, which the data suggest it is.

---

## 6. Honest limitations, stated once and plainly

1. **No clinician has reviewed anything.** Every threshold is a *benchmark-policy* value quoted from
   a task instruction or the grader. The word "safe" must keep the qualifier *process compliance
   with a benchmark policy* until E4 is done.
2. **No locked test set exists.** Tasks 4, 5, 7, 9 and 10 are all development data: we have read
   their reference answers. Task 6 is the only credible candidate and is not yet approved.
3. **A patient-disjoint final test set is impossible here.** 98 distinct patients for 300 cases;
   tasks 4/5/7/9/10 already touch 87. Only 11 patients across never-inspected task types are
   disjoint. Inference must be patient-clustered with the overlap stated numerically.
4. **The simulator is not pristine.** A two-patient scope already shows 128 `MedicationRequest`
   resources written by earlier experiments, so historical runs did not all see the same record.
5. **No model has run on tasks 4 or 7.** Their policies are verified against a constructed positive
   control with **zero false-positive exposure** — no agent in that sample ever retrieved anything,
   so specificity is untested.
6. **19/19 and 89/90 are controls, not sensitivity estimates.**
7. **No on-device evidence.** No RAM, latency, energy or battery measurement exists. "Locally
   executed 1–2B models" is defensible; "runs on phones" is not.
8. **Complete reproducibility is not demonstrated** — only approximate, on one machine.
9. **C1 is unimplementable** in this environment, so the plan's E7 cannot be completed as written.

---

## 7. What is genuinely novel, stated conservatively

Not "we evaluate agent steps first" — process-aware scoring exists (MedCTA, PAE, CliniCARE-Bench,
Hong, Cedar). The specific, testable combination is:

1. evidence validated for **patient, code, system, unit and time window**, not merely retrieved;
2. evidence availability checked **before the decisive step**, including the decision **not** to act;
3. **order-required versus no-order obligations** as a separate dimension, so a benchmark pass
   obtained by doing nothing is visible;
4. a **task-defined sentinel** treated as grounded only on an established absence — which keeps a
   correct "no data" answer from being scored as a failure, and keeps a guessed one from passing;
5. all of it demonstrated on **locally executed device-class models**, with scripted null agents
   proving the gap deterministically, with no model inference at all.

Claim wording stays: a trajectory shows valid evidence was **returned before the decisive step**,
never that the model *used* or *reasoned from* it.
