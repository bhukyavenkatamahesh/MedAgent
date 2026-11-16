# Human validation protocol for the procsafe action and process labels (v1)

## Purpose

Establish how far the evaluator's automatic labels agree with careful human reading of the same
trajectories. The evaluator is deterministic policy code; this exercise tests whether its labels
mean what the thesis claims they mean. It is **research-team annotation of benchmark compliance,
not clinical validation**; see "Scope" below.

## Material

| Item | Path | Reviewer-facing |
|---|---|---|
| Blinded episode packet (30 episodes) + guide + sheets | `docs/annotation_sample_v1_blinded/` | **yes** |
| Blinded calibration packet (3 separate episodes) + guide + sheets | `docs/annotation_calibration_v1_blinded/` | **yes** |
| Annotation guide | `docs/ACTION_ANNOTATION_GUIDE.md` (copied into both folders) | yes |
| Blank column template | `docs/ACTION_ANNOTATION_TEMPLATE.csv` | yes |
| Original un-blinded package | `docs/annotation_sample_v1/` | no |
| Hidden mapping (episode id -> model, prompt, run, case) | `docs/annotation_sample_v1/blinding_map_do_not_share.csv`, `docs/annotation_calibration_v1_map_do_not_share.csv` | no |
| Sealed evaluator key | `docs/annotation_sample_v1/EVALUATOR_KEY_do_not_open_before_annotating.csv` | no |
| Hashes of originals and reviewer materials | `docs/annotation_sample_v1/SHA256SUMS_original_package.txt`, `..._reviewer_materials.txt` | no |
| Regeneration scripts (seeded, reproducible) | `scripts/make_annotation_sample.py`, `scripts/make_reviewer_materials.py` | n/a |

Reviewers receive the blinded folders only. The packets and sheets name **no system, prompt
configuration or run**, not even an anonymous identifier, so episodes cannot be grouped by their
origin; the internal case id and the harness status line are removed too. The episode trajectories
themselves are untouched. Which model, prompt and run produced each episode lives only in the hidden
mapping, which is joined after adjudication (stage 3 of the analysis script, `--mapping`).
Operational steps: `docs/HUMAN_VALIDATION_WORKFLOW.md`.

## Sample

30 episodes drawn from the 480 saved held-out episodes, stratified on the evaluator's
action-requirement status (10 `REQUIRED`, 10 `NOT_REQUIRED`, 10 `UNDETERMINED`) and balanced
round-robin over model x prompt x task cells with a fixed seed (20261117). Both tasks, both models
and all three prompt conditions appear in every stratum. The packet is shuffled, so the strata are
not visible, and the set is deliberately not limited to successful episodes: the `REQUIRED` stratum
contains no benchmark pass at all, and 22 of the 30 episodes are benchmark failures.

**Known limitation of the design:** the strata come from the evaluator being tested, so the sample
is not an unbiased draw from the population of episodes. It tests agreement *within* each label
rather than the evaluator's overall accuracy on a random sample. A second round should add a random
sample for that purpose.

## Reviewers

Two independent reviewers, A and B:

- **Reviewer A:** the student (MedAgent author).
- **Reviewer B:** a second person who has **not** written the evaluator — the supervisor, a labmate,
  or another MTP student. Reviewer B must be able to read FHIR JSON but needs no familiarity with
  this codebase. Reviewer B works only from the guide and the packet.

Both reviewers annotate all 30 episodes independently, in one sitting per stratum-free pass, and
neither sees the other's sheet or the evaluator key until both sheets are handed in.

## Procedure

1. Both reviewers read `ACTION_ANNOTATION_GUIDE.md`.
2. Calibration on **separate material**: both reviewers annotate the 3 episodes of
   `docs/annotation_calibration_v1_blinded/`, which come from the prompt-development cases and
   overlap the 30-episode sample in neither episode, case nor patient. They compare, and resolve
   wording problems in the *guide* only. The calibration annotations are discarded and the guide is
   then frozen, with its hash recorded, before the 30-episode packet is distributed.
   **Completed 2026-11-17** (reviewers `BV` and `VM`): 35 of 36 judgement cells agreed; the one
   disagreement was traced to an ambiguity in the missed-action definition, which was rewritten.
   Findings: `docs/CALIBRATION_FINDINGS.md`. Guide frozen at SHA-256 `c998505c8d4abdf36bb791371f8c467304a32e04a36256620bfd99e5a9be32a9`. No agreement
   statistic was computed from three cases, and the calibration annotations are not research data.
3. Independent annotation of all 30 episodes.
4. Sheets are handed in (committed or sent) **before** anyone opens the evaluator key.
5. Agreement is computed between A and B: raw agreement and Cohen's kappa per field
   (`h_action_requirement`, `h_missed_required_action`, `h_unnecessary_action`,
   `h_premature_action`, `h_unsafe_action`, `h_appropriate_deferral`, `h_final_claims_grounded`).
6. **Adjudication:** every A-vs-B disagreement goes to a third person (the supervisor if they are not
   already reviewer B) who sees both rationales but not the evaluator label, and records the
   adjudicated value plus a one-line reason. The adjudicated set is the human reference standard.
7. Only then is the evaluator key opened, and evaluator-vs-human agreement is computed against the
   adjudicated standard, per label.
8. Every evaluator-vs-human disagreement is written up individually with a verdict: evaluator bug,
   policy-configuration gap, guide ambiguity, or human error. Bugs become regression tests in
   `tests/test_v2_action_requirements.py`.

## Reporting

Report, per label: human A-vs-B kappa, evaluator-vs-adjudicated agreement, and the full list of
disagreements with their verdicts. Report the stratified design and its limitation above. Do not
report a single headline "evaluator accuracy" number without the sampling caveat.

## Scope: what this does and does not establish

**Does:** whether the evaluator's labels can be reproduced by careful human reading of the same
trajectory against the benchmark task text; where its definitions are ambiguous.

**Does not:** whether the benchmark's own thresholds (potassium < 3.5, magnesium ≤ 1.9 within 24 h),
its dose rules, or the 8 synthetic held-out cases are clinically sound. Those need a clinician and
are tracked separately in `medagentbench_setup/heldout_v1_clinical_review.md`. If no clinician is
available, the thesis must say "research-team annotation of benchmark compliance" and must not
claim clinical validation. `h_flag_for_clinician` collects the episodes worth a clinician's time.
