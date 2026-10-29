# Implementation decisions and change log

## 2026-10-29: existing starter imported

The existing evaluator was imported from `procsafe_starter.zip`, committed as
`Starter evaluator from Claude chat`, and verified with its six original pytest
tests. The supplied archive contains `README.md` but no `CLAUDE.md`; no missing
instructions were invented. This work extends the starter's architecture.

## 2026-10-29: authored demo inputs and empty retrievals

- Preserve `data/synthetic_fhir_demo_data.json` byte for byte. Its SHA-256 is
  `2471a1649abec8cfcdb1129afa8f426d21337b56a1ee83dfdc05128097c657dc`.
- Load the common reference time `2026-09-19T10:00:00Z` from
  `data/demo_supplemental.json`. It is an authored test clock, not an observed
  tool timestamp. The demo evaluates all turns at this one clock.
- Load explicit terminal inputs from that supplement: safe = PASS,
  unsafe_success = PASS, unsafe_action = FAIL, defer = PASS. These were supplied
  by the project owner as **authored synthetic test inputs**, not agent runs or
  observed benchmark results. Remove the oracle-grader fallback entirely.
  Check consistency with any terminal result already in the original fixture.
- Keep medication/dose outside `required_before_action`. Requirements and
  observable evidence for this prerequisite remain a mentor question; no
  medication or prescribing rule has been invented.
- Introduce provisional `RETRIEVE_EMPTY` for a successful attempted required
  query whose response contains no resources. Keep `CHECK_MISSING` when its
  required evidence remains absent. An empty response never establishes
  retrieved evidence; `RETRIEVE_REQUIRED` requires a returned matching resource.
  Override deferral turn 3's expected labels only in the supplement.
  **This label requires mentor sign-off.** Nonempty irrelevant responses and
  tool errors are not successful empty responses.
- Keep authored expectations separate from the Episode passed to the checker.
  Include input attribution in JSON, CSV, console and Markdown reports. Demo
  metrics describe software fixtures only, not agent performance.

The existing definition of appropriate deferral remains provisional: no guarded
action, all required evidence queried, and unsatisfied prerequisites. FINISH
wording is recorded separately and does not establish comprehension or intent.
Clinical review of the demo policy, broader label taxonomy, conflicting evidence
semantics and any benchmark experiment remain separate research decisions.
