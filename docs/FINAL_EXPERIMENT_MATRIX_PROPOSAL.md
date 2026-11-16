# Proposal: final experimental matrix

**Status: PROPOSAL. Nothing here is run.** It needs the `heldout_v2` prerequisites
(`docs/HELDOUT_V2_READINESS_AUDIT.md`) and supervisor sign-off first. Runtime estimates come from
measured `heldout_v1` runs (~4 min per 20-case run on this laptop).

## 1. What the matrix must separate

The project's result so far is that prompting changed *format and retrieval* but never produced a
single correct order (0 of 111 required actions on `heldout_v1`). The final experiment has to
distinguish four things that the development runs confounded:

1. the model's own ability (**baseline**, no few-shot help);
2. what a prompt adds (**prompt-only**);
3. what fine-tuning adds **on top of the same prompt** (so the gain is not just the prompt);
4. whether any gain survives on cases the prompts were never tuned on (`heldout_v2`).

## 2. Arms

| Arm | Model weights | Prompt | Purpose |
|---|---|---|---|
| **A0** | base | benchmark prompt, no examples | the honest floor; `heldout_v1` gave 0 valid actions here |
| **A1** | base | v4 decision-step (best prompt-only) | the prompt-only baseline to beat |
| **A2** | fine-tuned (LoRA) | benchmark prompt, no examples | does training replace the prompt? |
| **A3** | fine-tuned (LoRA) | v4 decision-step | the improved configuration; the headline comparison is **A3 vs A1** |
| **R1** | Qwen 2.5 7B, base | v4 decision-step | a size reference, run once, not fine-tuned |

A2 is the arm that makes the claim defensible: without it, an A3 gain cannot be attributed to
fine-tuning rather than to the prompt.

## 3. Models

Carried through from the pilots: **Llama 3.2 1B** and **Qwen 2.5 1.5B** (the two with complete
`heldout_v1` coverage). Gemma 3 1B and LFM2 1.2B were dropped after the first pilot (0/10 valid
actions) and should stay dropped unless breadth is specifically wanted. The 7B reference runs in
arm R1 only.

## 4. Conditions held fixed

- Parsing: **strict** is the reference condition; lenient reported as a secondary analysis only.
- Decoding: temperature 0 for one run per arm, plus **5 sampled repeats** at temperature 0.7 with
  **per-case seeds** (`seed = f(case_id, repeat)`), which requires the harness change in the audit.
- `num_ctx` 8192, `max_round` 8, as in `heldout_v1`.
- Scorer: a single frozen procsafe commit and frozen policy pair, recorded by hash in the run
  manifest. **No re-scoring after the fact.**

## 5. Size and runtime

| | Count |
|---|---|
| Cases per arm | 26–27 (pending decision D3) |
| Runs per model-arm | 1 (temp 0) + 5 (seeded) = 6 |
| Model-arms | 2 models x 4 arms = 8, plus R1 |
| Total runs | 8 x 6 + 1 = **49** |
| Episodes | ~49 x 27 ≈ **1,320** |
| Estimated runtime | ~6 min per run → **5–6 hours**, excluding fine-tuning |

## 6. Metrics, pre-registered

**Primary.** The three-way action outcome on order-required cases: *taken correctly* / *missed* /
*undecidable* (no usable evidence). The `heldout_v1` baseline to beat is 0 / 105 / 6 at episode level.

**Secondary, in this order.** Verified pass rate; benchmark pass rate; unsafe-order episodes;
unnecessary-action episodes; ungrounded answers; action-requirement status distribution (how often
the agent never obtained usable evidence); invalid-reply rate.

**Reporting rules.** Natural and synthetic cases reported separately; per-case medians with ranges
as well as pooled rates; every rate with its numerator, denominator and denominator description;
`UNDETERMINED` reported on its own and never folded into "no action needed".

**Decision rule, fixed in advance.** Fine-tuning is reported as an improvement only if A3 beats A1
on the primary metric **and** does not increase unsafe-order or ungrounded-answer counts. A gain in
benchmark pass rate alone is not an improvement — that is precisely the confusion this project
exists to expose.

## 7. Fine-tuning data, and the contamination risk

| Rule | Why |
|---|---|
| Training cases from the **development set and the other eight task types only** | never from `heldout_v2`, and not from `heldout_v1` either, which is the validation set |
| Every training example records its source case index and MRN in a manifest | the separation checker must be able to fail |
| Synthetic *values* may be used in training | unavoidable: there are no natural positives left anywhere |
| But training synthetic cases must be **distinct patients** from the `heldout_v2` synthetic cases | otherwise the model can memorise the patient, not the rule |

**Risk to state in the thesis:** both the training positives and the test positives are synthetic
and built by the same procedure, so a model could learn the *shape* of a synthetic case rather than
the clinical rule. Mitigations: different patients, different value bands between train and test, and
a sanity arm (A2) that shows whether behaviour transfers without the prompt.

## 8. Order of work

1. `heldout_v2` prerequisites (audit §3) — clinical review, separation checker, per-case seeds, lock manifest.
2. Freeze the evaluator (decide backlog E1–E3 first).
3. Run A0 and A1 on `heldout_v2`. Report. These are publishable without any fine-tuning.
4. Fine-tune, with the training manifest and separation check.
5. Run A2 and A3; run R1 once.
6. Score once, against the frozen manifest, and report with the pre-registered rules.

Steps 3 and 6 are the thesis's core results. If time runs out after step 3, the thesis still has a
defensible test-set result for the prompt-only configurations.
