# Evaluator improvements suggested by human validation v1

**Status: BACKLOG. Nothing here is implemented.** No evaluator source file, policy file or published
figure is changed by this document. Each item records what the validation showed, what the change
would be, and what it would cost in re-scoring — because several of them change labels that are
already published.

Evidence: `outputs/human_validation_v1/FINAL_HUMAN_VALIDATION_REPORT.md`.

| ID | Item | Evidence | Re-scoring cost | Priority |
|---|---|---|---|---|
| **E8** | **A task-10 policy** (A1C: order when there is no result or the last one is older than a year) | E1: a blind agent passes **17 order-required task-10 cases** with no retrieval, and the checker cannot label any of them — no policy exists | None — new policy, no existing figure changes | **Highest.** It is the only task type with natural positive-action cases, and the only evidence-free passes the checker currently misses |
| **E1** | A label for "checked, no action needed, none taken" | 8 of 14 disagreements; `APPROPRIATE_DEFER` recall 0.20 | **High** — changes `process_result` and every `APPROPRIATE_DEFER` count published | Blocked on guide issue 1 |
| **E2** | Exclude resource ids, codes, MRNs and timestamps from grounding claims | 3 of 14 (`ANN-02`, `ANN-12`, `ANN-25`) | Medium — changes `grounding_result` and `verified_outcome` | High |
| **E3** | Require a stated number to be presented *as a value* before treating it as supported | 2 of 14 (`ANN-16`, `ANN-28`) | Medium — same fields as E2 | Medium |
| **E4** | Make the "no FINISH" precedence explicit in code and report it | 1 of 14 (`ANN-23`) | Low — affects a reporting convention, not a label | High (cheap) |
| **E5** | Carry turn-level labels into the annotation key | the first comparison run read 10.0% instead of 100.0% on premature/unsafe because `episode_id` identifies the *case*, not the run | None — tooling only | High (cheap) |
| **E6** | Give `UNNECESSARY_ACTION` a test set that actually contains the positive class | both sides found 0 in 30 episodes; κ undefined, F1 meaningless | None — case selection | High |
| **E7** | Record the unit alongside every claim comparison | unit mismatch is currently invisible in the grounding output | Low | Low |

## Detail

**E1 — "checked, nothing needed, nothing done."** Today this outcome splits across `SAFE_SUCCESS`
and `SAFE_FAILURE` depending only on the benchmark's terminal result, so the process dimension
cannot express "the agent made the right call". Options: a new episode label
(`VERIFIED_NO_ACTION`), or an additional boolean on `EpisodeResult`
(`required_evidence_checked_and_no_action`) that leaves `process_result` untouched. The boolean is
cheaper and does not invalidate any published count; the label is clearer in the thesis. **Decide
with guide issue 1, not separately.**

**E2 / E3 — grounding.** `claim_numbers()` already strips ISO datetimes, MRN-shaped tokens and
NDC/LOINC-shaped codes. It does not strip FHIR resource ids (bare integers like `330934`) because
they are indistinguishable from a value by shape alone. Two implementable signals: (a) a number that
equals the `id` of a resource returned in that episode is an identifier, not a claim; (b) a number
that appears in the response body but not as a `valueQuantity.value` is not a value claim. Both are
decidable from data the evaluator already has. E3 is the harder half: deciding when a number is
"presented as a value" needs either a syntactic rule (adjacent to a unit, or inside a
`FINISH([...])` list) or a decision to treat an un-unitted bare number as no claim.

**E4 — incomplete traces.** The checker already refuses to assert a missed action without a
`FINISH`. What is missing is that the *reports* do not say which episodes were excluded for that
reason, so a reader cannot tell a clean "no" from "not judgeable". Add `complete_trace` to the
report tables and to the metrics denominators' descriptions.

**E5 — key provenance.** The annotation key stores `episode_id`, which identifies the case; the same
case appears in all 24 runs of the held-out tree. Any future comparison must join on
`(prompt, agent, episode_id)`. Either store the run's identity in the key, or store the scored
episode's path. This caused a real analysis bug in v1 and will recur.

**E6 — untested detectors.** `UNNECESSARY_ACTION` had no positive instance in the 30-episode sample
(and only 1 in all 480 held-out episodes). Its 100% agreement is an artefact of an absent class. The
fix belongs in test-set design: `heldout_v2` must contain episodes where an order is placed after a
normal value is read. Note this cannot be forced by case selection alone — it depends on agent
behaviour — so it may need a seeded or scripted trajectory in the unit-test suite instead, and a
statement in the thesis that the detector is tested by construction rather than observation.

## Sequencing constraint

E1, E2 and E3 change labels that appear in published tables. The project's convention (set in the
2026-11-17 audit) is: originals stay as published, corrected figures are added as a new dated
section. If more than one of these lands, they should land **together**, once, before `heldout_v2`
is run, so that `heldout_v2` is scored by a single frozen evaluator version and never re-scored.
