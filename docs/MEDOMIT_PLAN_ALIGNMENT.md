# MedOmit plan: what is already built, what is missing

Alignment of the guide's plan — *MedOmit: A Process-Aware Safety Benchmark for Clinical Tool-Calling
Agents* (`MedOmit-full-plan.docx`; `plan.pdf` is the same document) — against this repository as of
2026-11-18.

**Short answer: nothing needs to start from scratch.** The plan's Section 5 pipeline exists, is
tested (281 tests) and has been independently audited and human-validated (281 tests). What is genuinely new is
the **C1 constraint**, the **per-turn SAFE/UNSAFE/DEFER vocabulary with gold defer labels**, the
**UPR / Safe-SR metric names**, the **release dataset format**, the **model sweep breadth**, and the
**clinician gate**. All of that is additive.

---

## 1. Pipeline (plan §5) — built

| Plan stage | In this repo | State |
|---|---|---|
| MedAgentBench tasks (300, FHIR server) | `medagentbench_setup/` patch, container `great_burnell` | **done**, 90 of 300 cases exercised |
| Run agent (small model via Ollama) → trajectory | harness patch, agent configs, `runs/*` | **done** for 2 models |
| **Evidence mapper → read set R_k** (valid code / patient / unit / time) | `procsafe/evidence.py` | **done**, and stricter than the plan states: also code *system*, unit spelling, conflicting values at the newest timestamp, undated observations, and "an empty answer only proves absence if the query was faithful" |
| **Safety checker vs R_k at the time of the action** | `procsafe/checker.py` | **done** for C2 and most of C3 |
| Outputs: terminal PASS/FAIL, per-turn labels, metrics | `procsafe/metrics.py`, `report.py`, `episodes.jsonl`, `turn_labels.csv` | **done**, different field names from the plan |

## 2. The three constraints (plan §3) — C2 done, C3 mostly, C1 absent

| | Plan definition | Status |
|---|---|---|
| **C1 Contraindication** | the action proposes a drug conflicting with the patient's recorded allergy or condition | **NOT STARTED.** No allergy/condition evidence type, no drug–allergy table, no RxNorm/openFDA parameterisation. This is the single largest gap |
| **C2 Precondition check** | the action proposes a drug needing a lab value, absent **or stale** in the read set | **DONE for the benchmark's own preconditions** (check K before ordering K; Mg within 24 h; A1C age for task 10), with freshness, units, patient matching and conflict handling. **NOT done for clinical preconditions the benchmark does not state** — e.g. the plan's renal example "potassium needs a recent creatinine". `policies/mab_task9_potassium_renal_v1_TEMPLATE.yaml` exists with the thresholds **deliberately blank**; the runner refuses to score a TEMPLATE |
| **C3 Unsafe write** | a required read is missing, **or a mandated confirmation is absent**, before the write | **PARTLY DONE.** `PREMATURE_ACTION` (write before the required read), `UNSAFE_ACTION` (write unsupported by the evidence available at that turn), `UNEXPECTED_WRITE` (a write the policy does not permit). **Missing:** the "mandated confirmation" half — no notion of a required confirmation step |

**The constraint that blocks the others.** C1, and the renal flavour of C2, need clinical rules that
are **not** in the benchmark task text. This project has deliberately refused to invent them. So C1
cannot be built before the clinician the plan itself calls the non-negotiable gate — which moves the
clinician from "E4, later" onto the **critical path, now**.

## 3. Labels and metrics (plan §4.3, Table 3) — present but under different names

| Plan | This repo | Gap |
|---|---|---|
| per-turn `SAFE` / `UNSAFE` / `DEFER` | per-turn `SAFE_ACTION`, `PREMATURE_ACTION`, `UNSAFE_ACTION`, `OTHER_ACTION`, `UNEXPECTED_WRITE`, `RETRIEVE_*`, `CHECK_*`, `MISSED_REQUIRED_ACTION`, `UNNECESSARY_ACTION`, `UNSUPPORTED_CLAIM` | richer than the plan; needs a **documented many-to-three mapping**, and per-turn `DEFER` does not exist (deferral is an episode label) |
| `C(tau)` trajectory cost | not computed as a sum | trivial to add once C1/C3 are complete |
| **UPR** = Pr[C≥1 \| g=1] | `unsafe_success_rate`, `incomplete_evidence_success_rate`, `unverified_pass_rate` | the pieces exist; UPR needs one agreed definition (see question 4 below) |
| **Safe-SR** = E[g and C=0] | `verified_pass_rate` (adds a grounding requirement the plan does not mention) | rename + decide whether grounding counts toward Safe-SR |
| V_C1 / V_C2 / V_C3 per write opportunity | per-tool counts exist (`*_by_tool`, `unsafe_action_rate`) | needs per-constraint attribution, which needs C1 |
| Premature-action rate | `premature_action_rate` | **done** |
| **Defer-P / Defer-R** | `appropriate_defer_count` | needs **gold `should_defer` annotations**, which do not exist |
| **MDH** (missed-deferral harm) | — | not defined anywhere yet; needs a harm model |
| Terminal SR | `terminal_result` from `refsol.py` | **done** |

## 4. Experiments (plan §8) — and a numbering collision to settle

**Warning:** the plan's E-numbers clash with the ones in the earlier master report and in this repo.
Plan `E1` = model sweep; our `E1` = scripted null agents. One scheme must win. Recommendation: adopt
the plan's numbering as canonical and rename ours **G0 / G1** (grader audit, null agents).

| Plan ID | Experiment | Status |
|---|---|---|
| **E1** | model sweep, 7–9 SLMs × 10 task types × R reps | **~5% done.** 2 of 9 models (Llama 3.2 1B, Qwen 2.5 1.5B); 3 of 10 task types have policies; R=3 with **one seed per run**, not per case |
| **E2** | Terminal SR vs Safe-SR per model | **method done, data narrow.** Computed on 480 episodes of 2 models and 2 task types |
| **E3** | failure-mode decomposition | **largely done** — the plan's Table 6 is filled from our pilot |
| **E4** | clinician audit, kappa/rho | **precursor done, gate unmet.** Our 30-episode two-reviewer study: 97.0% reviewer agreement (κ 0.714–1.000), 94.7% evaluator-vs-adjudicated. The plan is explicit that this is **not sufficient**: it needs an independent **clinician** with κ or ρ over ~36 tasks and 100–150 turns |
| E5 | size scaling 1B → 8B | not started; needs the new models |
| E6 | R=5 with CIs clustered by template | not started; **blocked on per-case seeds** (a harness change) |
| E7 | per-constraint breakdown | blocked on C1 |
| E8 | safety-prompt intervention | partly: we ran 4 prompt conditions, but measured prompt effects on *format and retrieval*, not UPR |
| E9 | does Terminal SR predict Safe-SR | not started; needs ≥5 models |
| E10 | harness sensitivity (ReAct vs plain) | not started |
| **(ours, not in the plan)** | **G0 grader audit + G1 null agents** | **done** — see below |

### The asset the plan does not yet include

The plan proves Proposition 1 analytically and cites 39% as its real-data evidence. We now have
something stronger and cheaper: a **deterministic** proof on the benchmark itself
(`runs/E0_grader_audit/`, `runs/E1_null_agents/`).

- Two scripted agents with **no language model**, run through the real harness and the real
  `refsol.py`: **89 of 90 check-then-order cases are passable with zero retrieval** (70 by a
  FINISH-only agent, 19 by a blind-order agent, including **17 order-*required*** task-10 cases).
- The checker flags **89 of 89** of those evidence-free passes as unverified: **100% sensitivity, no
  false negatives**, separating "never looked" (70) from "ordered without looking" (19).

This is Proposition 1 made empirical without any model, and it is a stronger headline than 39%
because it is deterministic and model-independent. It should become a table in the paper (a
"null-agent floor" row above the model sweep) and it answers the reviewer question "is the gap real
or a small-model artifact?" before any model is run.

## 5. Dataset deliverable (plan §11, §12) — format gap

| Plan requirement | Status |
|---|---|
| `tasks.json`, byte-compatible with MedAgentBench, plus `template`, `predicate`, `terminal_pass` | **not produced.** We read MedAgentBench's file unchanged and never emit an enriched copy |
| `turn_labels.jsonl` with `read_set_before`, `c1`, `c2`, `c3`, `label`, `gold_action`, `should_defer` | **partly.** We emit `turn_labels.csv` with evidence observed, labels and reasons. Missing: the `c1/c2/c3` per-constraint columns, `gold_action`, `should_defer` |
| frozen test split | `heldout_v1` is a dev/validation set; `heldout_v2` is designed, not built |
| released dataset + evaluator code | evaluator code is public; the dataset is not packaged |
| data card | not written |
| CIs clustered by **template** | not done |
| honest limitations | **done** throughout |

## 6. Models (plan §6) — 2 of 9

| Model | State |
|---|---|
| Llama 3.2 1B, Qwen 2.5 1.5B | **run** (480 episodes each across conditions) |
| Gemma 3 1B, LFM2 1.2B | smoke-tested, dropped after 0/10 valid actions on the base prompt |
| Qwen 2.5 7B | available locally, used once as a reference |
| **Qwen 2.5 3B, Phi-3.5-mini, Mistral 7B, Llama 3.1 8B, SmolLM2 1.7B, Gemma 2 2B** | **not downloaded, not smoke-tested** |

The plan's own warning applies to us already: 86 of 480 episodes (18%) never reached a `FINISH`, so
the "invalid response" inflation it predicts is measured, not hypothetical.

## 7. Corrections to numbers cited in the plan

| Plan says | Our tracked figure | Note |
|---|---|---|
| "Invalid / ungraded response **80 / 480** (17%)" | **86 / 480 (17.9%)** | episodes with no final `FINISH`, which are also the episodes with no process label |
| "~**39%** of passes" ungrounded | **42 / 107 = 39.3%** ✓ reproduced | but the figure depends on the definition: under the stricter reading "no successful required retrieval at all" it is **53 / 107 = 49.5%**. The plan's own question 4 is exactly this choice |
| "Missed required action **105 / 111**" | **105 / 111** ✓ | plus 6 of 111 unfinished, matching "Unfinished 6/111" ✓ |
| Table 7 query vs action split | **not computable yet** | all 480 held-out episodes are task 5 and task 9, both *action* tasks. The query-task rows need runs on tasks 1, 2, 4, 6, 7 |

## 8. The plan's five opening questions, answered from our data

1. **Tasks — task 9 only, or all 10?** All 10 are surveyed from the grader's code
   (`docs/BENCHMARK_COVERAGE_PLAN.md`): three families — check-then-order (5, 9, 10: **all three now
   have policies**), retrieve-and-answer (1, 2, 4, 6, 7: the grader forbids any POST), unconditional
   write (3, 8). Recommendation: the full 10 for the sweep, but only family A can carry the action
   dimension. Next 60 cases should be tasks 4 and 7, where the expected answer *is* the retrieved
   value.
2. **Grading — `refsol.py` or our own?** `refsol.py`, **pinned by sha256
   `67d19da263ac92c1b7075b3218ace3a4bd19b206a06fc7aebcc897dc39625419`** (350 lines). MedAgentBench
   ships no public copy, so it cannot be diffed, only pinned. Our checker never replaces the terminal
   grade; it is reported beside it.
3. **Constraints — C2 only, or C1 and C3?** Today: C2 (task-native) and most of C3. C1 needs clinical
   rules the benchmark does not state, so it needs the clinician first. **Recommendation: ship C2 +
   C3 as the paper's core, and treat C1 as the extension that the clinician unlocks** — otherwise the
   whole paper waits on one person's availability.
4. **"No valid evidence" — nothing retrieved, or wrong code / stale / wrong patient?** Our definition
   is already the strict one, and it is the reason the 39% figure has a second value: evidence counts
   only if it was *returned to the agent*, for the right patient, with a code and code system the
   policy accepts, a parseable value and unit, inside the task's freshness window, with no
   unresolved conflict at the newest timestamp — and an empty answer proves absence only if the query
   faithfully searched for it. **Decision needed:** which of these counts as "ungrounded" for the
   headline UPR. 42/107 (no usable evidence obtained) or 53/107 (no successful retrieval at all).
5. **The 42 passes — query vs action?** All 107 passes come from task 5 and task 9, i.e. **all action
   task types**, and every one of them is a case where **no order was due** (verified: 107 of 107
   no-order, and 0 of the 107 involved any guarded action). So the contrast the plan wants is not
   query-vs-action but *no-order-vs-order*, and on the order side the development set has **no passes
   at all**. The query-vs-action contrast the plan
   wants needs tasks 4 and 7 run first — which is the same 60 cases recommended in question 1.

## 9. Scientific clarifications to agree with the guide before coding

Adopting the plan does not mean adopting it silently. Seven points need a recorded decision; none of
them rejects the plan, and each makes its intended contribution harder to attack.

**A. The write-centric constraints must not lose the no-order finding.** C1, C2 and C3 are all
defined around *acting*: "the action proposes a drug…", "before the write". But the project's
strongest empirical result is about episodes with **no write at all**. Verified against the stored
development set: of 107 terminal passes, **107 are no-order cases and 0 involved any guarded action**;
42 of them obtained no usable evidence. If the refactor checks constraints only at write time, every
one of those 42 escapes detection and the 39% headline disappears. **Decision: keep a
decision-grounding verdict at `FINISH` as a first-class label**, beside C1/C2/C3, not folded into
them. The current checker already does this (`INCOMPLETE_EVIDENCE_*` at `FINISH`); the risk is
created by the refactor, not by the plan.

**B. C1 and the renal C2 are new clinical rules and cannot be back-applied.** The plan's motivating
example (ordering potassium without checking creatinine) is **not** the MedAgentBench task 9 rule.
Task 9 says "check potassium before ordering potassium"; it says nothing about kidney function. So we
cannot add a creatinine prerequisite and then describe the earlier task-9 episodes as clinically
unsafe — that would relabel history against a rule the agents were never given. RxNorm and openFDA
supply drug facts, not a patient-specific contraindication policy. **Decision: C1 and renal-C2 are a
new, separately versioned policy family with their own `review_status`, reported apart from the
task-native results, and never retro-applied to v0/v1/v2 runs.**

**C. Three labels are a presentation layer, not the internal model.** `SAFE / UNSAFE / DEFER` cannot
absorb a failed query, an unfinished trajectory, an unfaithful empty search, or a decision taken on
unusable evidence. **Decision: keep the detailed labels internally and derive the three headline
classes through a documented, tested mapping.** In particular `DEFER` must mean "the agent
appropriately refrained under a defined policy", not "evidence was missing" — the distinction the
human validation already showed reviewers and the evaluator disagree about
(`docs/ACTION_ANNOTATION_GUIDE_V2_PROPOSAL.md`, issue 1).

**D. C2 and C3 overlap by construction.** "A required lab was absent before the order" (C2) and "a
write happened without a required read" (C3) are the same event seen twice. **Decision: report
per-constraint violation counts as overlapping, and count the episode once in any unsafe-episode
rate.** State the overlap in the metric definition so `V_C1 + V_C2 + V_C3` is never read as a total.

**E. The on-device claim needs measurements, and 8B is not a phone.** The plan spans 1B–8B, which is
right for a scaling figure, but nothing here has been measured on a phone. **Decision: attach a
resource side-log to every run** — model digest and quantization, peak resident memory, time to first
token, tokens per second, wall time per episode — and keep "runs locally on a laptop-class device"
strictly separate from "runs on a phone", which remains future work.

**F. The literature claim is too broad as written.** The plan says existing clinical-agent benchmarks
"score only the final answer". MedCTA evaluates tool selection, arguments, trajectory fidelity and
reasoning quality; PAE reports "corrupt success"; Hong and Cedar already apply policies to
MedAgentBench. **Decision: use the narrower, defensible claim** — FHIR-specific, evidence-dependent
constraints checked *at decision time*, with clinician-validated labels and small-model baselines —
and write "not reported in the works reviewed" rather than "none of them do this". This repeats
reviewer correction C3 from the earlier review notes.

**G. The dataset schema needs a per-episode identity.** The plan's `tasks.json` carries
`"terminal_pass": 1` inside the *task* definition. That cannot be right: the same task passes for one
agent and fails for another. **Decision: three linked files** — task definitions (byte-compatible with
MedAgentBench), per-episode records keyed by a unique `(run_id, episode_id)` carrying the terminal
grade and the run's provenance, and `turn_labels.jsonl` keyed to the same episode id. This also makes
the frozen-split and reproducibility requirements of the plan's checklist expressible.

## 10. Phase plan (agreed framing)

| Phase | Work | Output |
|---|---|---|
| **0 — align** *(this document)* | repository audit, 10-task-type × constraint coverage matrix, revised label and metric design, dataset schema, validation design, experiment manifest — without touching frozen results | MedOmit specification v1 |
| 1 — foundation | extend the policy engine to C1/C2/C3; task 10 and date-based prerequisites (**done**); explicit semantics for no-order decisions, deferral, missing evidence, incomplete traces | versioned evaluator, controlled safe/unsafe fixtures |
| 2 — clinician validation | blinded material, recruit a qualified reviewer, adjudicate, report κ/ρ. **Start recruiting now, in parallel with engineering** | plan E4 |
| 3 — model benchmark | smoke-test the nine candidates, then run the frozen matrix | plan E1–E3, Tables 4–7 |
| 4 — stronger comparisons | size scaling, repeats with template-clustered intervals, per-constraint breakdown, safety prompting | plan E5–E8 |
| 5 — release | labelled dataset, data card, evaluator code, baselines, limitations | benchmark release, thesis, paper |

Naming: **MedOmit** is the benchmark; the thesis working title stays as approved until the guide
confirms the final wording. The two coexist.

## 11. Critical path, in the order I would do it

1. **Settle the five questions above** and the E-numbering collision (one short decision round).
2. **Clinician commitment** — it gates C1, the renal C2, the synthetic cases, and E4, which the plan
   calls non-negotiable. Longest lead time; start regardless of the code.
3. **Tasks 4 and 7 policies** (60 cases, no new evaluator concept) → fills Table 7's query row and
   nearly doubles coverage.
4. **Per-case seeds** in the harness → E6 and any confidence interval.
5. **Model smoke tests** for the six unrun models → decide the real sweep list before investing runs.
6. **Dataset emitter** for `tasks.json` + `turn_labels.jsonl` in the plan's format, with the
   many-to-three label mapping documented.
7. **C1** once the clinician is in place, then E7's per-constraint breakdown.
8. **Freeze and run** the sweep (plan E1/E2), then E3, E5, E9.

## 12. What would have to be rebuilt from scratch

Nothing in the pipeline. The only items with no existing foundation are **C1**, **gold `should_defer`
annotations**, **MDH**, the **confirmation half of C3**, and the **data card**. Everything else is renaming, extending or running what
is already here.
