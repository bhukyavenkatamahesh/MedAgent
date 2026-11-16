# Annotation package QA (docs/annotation_sample_v1, 2026-11-17)

Pre-flight audit of the blinded human-annotation package, **before** any annotation is done.
Reproduce with:

```bash
python scripts/analyze_human_annotations.py --qa-only --packet docs/annotation_sample_v1
```

Machine-readable result: `outputs/human_validation_v1/package_qa.json`.
**No human annotation exists yet, and none was invented.** The 30-case sample was not modified.

## Result: 15 of 15 checks pass

> The 15 package checks below concern the **original** (un-blinded) package, which reviewers never
> receive. The 17 checks on the reviewer-facing material are in *Blinded reviewer materials* at the
> end of this document.

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Packet holds exactly 30 episodes | PASS | 30 `## ANN-nn` blocks |
| 2 | Episode ids unique | PASS | 0 duplicates, `ANN-01`…`ANN-30` |
| 3 | Both reviewer sheets carry the same ids as the packet | PASS | A=30, B=30, packet=30 |
| 4 | Every sheet field is known to the guide, template and script | PASS | 19 columns, all recognised |
| 5 | Blank template header matches the reviewer sheets | PASS | identical column list |
| 6 | Guide defines every label the sheet asks for | PASS | all 9 label terms present |
| 7 | Every episode carries the task instruction, the task context and a chronological trajectory | PASS | all 30 complete (instruction, context, `Trajectory`, ≥1 agent message) |
| 8 | Returned observations show value, unit, timestamp and patient reference | PASS | 20/30 episodes return observations; 60 K/MG rows, every one with value + unit + `effectiveDateTime` + `Patient/...` |
| 9 | Packet contains no evaluator label or status name | PASS | none of 24 searched terms occurs |
| 10 | No judgement is pre-filled in either sheet (nothing fabricated) | PASS | every `h_*` cell empty in both sheets |
| 11 | Sheets pre-fill only id/task/model/prompt context | PASS | context present on all 60 rows |
| 12 | Reviewer A sheet loads cleanly | PASS | comment row skipped, no duplicate ids |
| 13 | Reviewer B sheet loads cleanly | PASS | as above |
| 14 | Evaluator key present and left sealed | PASS | 31 lines (header + 30), SHA-256 `f4ddc77ab14381e7…` |
| 15 | Both tasks, both models and all three prompt conditions appear | PASS | see coverage below |

The leaked-label search (check 9) covers `MISSED_REQUIRED_ACTION`, `UNNECESSARY_ACTION`,
`PREMATURE_ACTION`, `UNSAFE_ACTION`, `SAFE_ACTION`, `SAFE_SUCCESS`, `SAFE_FAILURE`,
`APPROPRIATE_DEFER`, `VERIFIED_PASS`, `UNVERIFIED_PASS`, `INCOMPLETE_EVIDENCE`,
`UNEXPECTED_WRITE`, `UNSUPPORTED_CLAIM`, `RETRIEVE_REQUIRED`, `RETRIEVE_EMPTY`,
`CHECK_SATISFIED`, `CHECK_MISSING`, `NOT_REQUIRED`, `UNDETERMINED`, `process_result`,
`verified_outcome`, `action_requirement_status`, `terminal_result` and `order_required`.

## Coverage of the 30 episodes

| Split | Counts |
|---|---|
| Task | task9 17, task5 13 |
| Model | llama3.2-1b 16, qwen2.5-1.5b 14 |
| Prompt | v2-clinical-sequence 11, v3-format-only 10, v4-decision-step 9 |

All 12 model x prompt x task cells are represented (1–5 episodes each). The sampling strata
(10 `REQUIRED`, 10 `NOT_REQUIRED`, 10 `UNDETERMINED`) were enforced by
`scripts/make_annotation_sample.py` at generation time and are recorded **only** in the sealed key,
so this QA pass cannot and does not re-verify them from the key.

## How the key was treated

`EVALUATOR_KEY_do_not_open_before_annotating.csv` was checked by **byte count, line count and
SHA-256 only**; no field value was parsed. Its line count (31) is consistent with a header plus 30
rows.

Two disclosures, for honesty about blinding:

1. The key was *written* by `scripts/make_annotation_sample.py`, and during development of that
   script its header plus the first data row (`ANN-01`) were printed to a terminal. That exposure is
   on the implementation side only. It does not affect reviewers A and B, who never see the file, and
   neither reviewer is the implementer of the sampling script.
2. The key sits in the same directory as the packet. Anyone can open it. **Before handing the
   package to reviewers, move it out of the shared folder** (or rename/encrypt it) so that neither
   reviewer can open it by accident. The analysis script enforces the order of work in code — stage 2
   never reads the key, and stage 3 refuses to run without a filled adjudication file — and a
   regression test asserts that stage 2 completes even when `--key` points at a non-existent file.

## Minor observations (no change made)

1. **Harness status line.** Each episode ends with the benchmark harness's own run status
   (`completed`, `agent invalid action`, `task limit reached`), explicitly labelled in the packet as
   "the harness's own run status, not a grade". It is raw run metadata rather than an evaluator
   label, but it is a weak cue: `agent invalid action` hints that the trajectory was malformed. Kept,
   because removing it would hide a real property of the run. If a reviewer finds it distracting,
   regenerate the packet with that line suppressed; the sample ids and ordering are seed-stable.
2. **Observation tables are truncated at 8 rows** per reply ("…and N more"). No K/MG reply in the
   sample exceeds 8 observations, so nothing relevant is hidden in this sample.
3. **`h_required_tools` allows `both`**, while the evaluator records a list of tools. The comparison
   stage therefore compares the per-tool *attempt* columns rather than `h_required_tools`, which is
   used for reviewer-vs-reviewer agreement only. Documented in the workflow.
4. **Strata are evaluator-derived**, so the sample tests agreement within each evaluator label and
   not the evaluator's accuracy on a random draw. Already stated in
   `docs/HUMAN_VALIDATION_PROTOCOL.md`; a random-sample round is recommended for v2.
5. **Resolved on 2026-11-17:** the sheets used to carry `model` and `prompt_condition`, which could
   bias a reviewer who had read the earlier results ("Llama orders blindly") and would let either
   reviewer group episodes. Both columns, and the packet's system/configuration/run line, are gone
   from the reviewer-facing material; the information survives only in the hidden mapping.

## Blinded reviewer materials (added 2026-11-17)

Reviewers do **not** receive `docs/annotation_sample_v1/`. They receive blinded copies, built from
the untouched original by `scripts/make_reviewer_materials.py`:

| Folder | Contents |
|---|---|
| `docs/annotation_sample_v1_blinded/` | 30-episode `packet.md`, the guide, both reviewer sheets |
| `docs/annotation_calibration_v1_blinded/` | 3-episode calibration `packet.md`, the guide, both sheets |

Blinding removes the model name, the prompt configuration name, the internal case id and the harness
run status **entirely**. Earlier drafts replaced the first two with anonymous `SYS-n` / `CND-n` /
`RUN-nn` identifiers; those were dropped on 2026-11-17 because they would still let a reviewer group
episodes by system, prompt or run. Reviewer sheets now hold the episode id, the task type and the
judgement columns only. Which model, prompt and run produced each episode lives solely in the hidden
mapping beside the key, and is joined after adjudication. Task identity, task instruction, clinical
context, the chronological agent messages and every returned value, unit, timestamp and patient
reference are kept unchanged.

A second QA pass checks the reviewer-facing material:

```bash
python scripts/analyze_human_annotations.py --qa-blinded
```

**Result: 15 of 15 blinding checks pass** (`outputs/human_validation_v1/blinding_qa.json`). Per
folder: no forbidden identifier (`llama`, `qwen`, `gemma`, `lfm2`, `ollama`, `ctx8k`, `fewshot`,
`format-only`, `decision-step`, `clinical-sequence`, `t07-s`, `num_ctx`, `temperature`, `heldout`,
`procsafe`, `runs/2026`, `slm-`); no evaluator status token (30 uppercase names, including
`REQUIRED`, `NOT_REQUIRED`, `UNDETERMINED`, `MISSED_REQUIRED_ACTION`, `UNNECESSARY_ACTION`,
`VERIFIED_PASS`); **no grouping identifier matching `SYS-n` / `CND-n` / `RUN-nn` anywhere**; no
evaluator metadata key; no key or mapping file present; unique packet ids matching the sheets; **no
system, configuration, run or sampling column in the sheets**; no pre-filled judgement.
Across folders: the two packets share no episode id, no case and no patient, and the calibration
trajectories come from the prompt-development cases.

Three deliberate exclusions, so the check flags evaluator metadata and not ordinary language:

- **Status names are matched case-sensitively, as whole words.** Clinical text in a task instruction
  ("If low, then order replacement…", "don't order anything", a lowercase "required" or "not
  required") can never trigger them; a regression test asserts this on the real task text.
- **The guide and the blank template are not scanned.** They must contain the label names — they are
  the definitions reviewers have to read. Only episode packets and reviewer sheets are scanned.
- The reviewer's own `h_missed_required_action` and `h_unnecessary_action` columns are exempt from
  the metadata-key check (a lookbehind on `h_`), because they are the questions being asked.

## Hashes

`docs/annotation_sample_v1/SHA256SUMS_original_package.txt` records the four original files and
`..._reviewer_materials.txt` the eight reviewer-facing files. `shasum -a 256 -c` confirms the
originals were not modified by the blinding step, which only added the mapping file to that
directory.

## Conclusion

The materials are fit to send out, as the **blinded** folders. One action is required first: **move
the evaluator key and both blinding maps out of the shared tree** (step 0 of
`docs/HUMAN_VALIDATION_WORKFLOW.md`).
