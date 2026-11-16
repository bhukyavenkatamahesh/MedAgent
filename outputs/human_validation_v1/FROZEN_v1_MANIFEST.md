# Human validation v1 — FROZEN 2026-11-17

These outputs are the record of human validation v1 and are **closed**. Nothing in this directory
may be edited, re-scored in place or overwritten. Any later analysis writes to a new directory.

- Contents and hashes: `SHA256SUMS_v1_frozen.txt` (verify with
  `shasum -a 256 -c outputs/human_validation_v1/SHA256SUMS_v1_frozen.txt` from the repository root).
- The files were also made read-only (`chmod a-w`). To work with a copy, copy it out; to deliberately
  unfreeze, `chmod u+w` and record why in `DECISIONS.md`.

| File | What it is |
|---|---|
| `FINAL_HUMAN_VALIDATION_REPORT.md` | the v1 report: reviewer agreement, evaluator-vs-human agreement, limitations |
| `final_comparison_2026-11-17/reviewer_agreement.json` | per-field raw agreement, Cohen's kappa, confusion matrices, prevalence |
| `final_comparison_2026-11-17/disagreements.csv` | the 9 reviewer-vs-reviewer disagreements sent to adjudication |
| `final_comparison_2026-11-17/adjudication_template.csv` | the blank template generated for the adjudicator |
| `final_comparison_2026-11-17/evaluator_vs_human.json` | the final evaluator-vs-human comparison |
| `final_comparison_2026-11-17/evaluator_vs_human_BEFORE_mapping_fix.json` | the first run, kept to document the three comparison-layer bugs |
| `final_comparison_2026-11-17/evaluator_vs_human_disagreements.csv` | the 14 disagreements, per episode |
| `final_comparison_2026-11-17/evaluator_vs_human_not_comparable.csv` | the 4 episode-fields with no evaluator label |
| `final_comparison_2026-11-17/inputs/adjudication_normalized.csv` | column-renamed copy of the adjudication sheet (values identical) |
| `package_qa.json`, `blinding_qa.json` | the package and blinding QA records |

**Not stored here, by design:** the completed reviewer sheets and the original adjudication sheet
(the reviewers' own files, outside the repository), and the evaluator key and blinding maps
(`~/medagent_sealed/`). Their locations and hashes are in the report's Appendix B and in
`docs/annotation_sample_v1/SHA256SUMS_sealed_material.txt`.

**Status of the v1 figures:** development/validation results on `heldout_v1`, measuring
benchmark-compliance annotation. **Not clinical validation.** If the evaluator or the annotation
guide changes (see `docs/EVALUATOR_IMPROVEMENTS_BACKLOG.md` and
`docs/ACTION_ANNOTATION_GUIDE_V2_PROPOSAL.md`), these numbers are **not** updated: a new validation
round gets its own directory and its own dated entry.
