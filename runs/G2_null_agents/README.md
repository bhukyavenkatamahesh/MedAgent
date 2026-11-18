# G2 — scripted null agents on the READ-ONLY tasks (4 and 7), 60 cases, no model inference

The read-only counterpart of G0/G1. **Kept separate from `runs/E0_grader_audit/` and
`runs/E1_null_agents/`, which are frozen and untouched.** No language model, no policy change, and
no SLM sweep: two scripted HTTP agents run through the unmodified MedAgentBench harness and the real
reference grader.

| Agent | Behaviour | Retrieval |
|---|---|---|
| **N0** | replies `FINISH([])` and nothing else | **no GET, no POST** |
| **N2** | one blind answer, chosen from the prompt text alone — task 4 `FINISH([-1])`, task 7 `FINISH([100])` | **no GET, no POST** |

Both read-only graders accept only an exact match of `[value]`, or `[-1]` when no qualifying
measurement exists, and fail the case outright on any POST (`refsol.py` task4 L87/L100/L104,
task7 L192/L203/L207).

Reproduce:

```bash
python scripts/g2_readonly_audit.py --mab ../../MedAgentBench/MedAgentBench --out runs/G2_readonly_audit
python scripts/g2_null_agent_server.py --log runs/G2_null_agents/agent_log.jsonl
```

Then, in the MedAgentBench clone (its own controller on port 5100, so an existing worker pool on
5000 is left alone):

```bash
python -m src.server.task_controller --port 5100
CASE_INDICES=90..119,180..209 python -m src.start_task -s medagentbench-std 4 -p 5101 --controller http://localhost:5100/api
python -m src.assigner -c configs/assignments/g2_null-ro-n0.yaml
python -m src.assigner -c configs/assignments/g2_null-ro-n2.yaml
```

## Result 1 — prediction and measurement agree exactly

| | task4 | task7 | total |
|---|---|---|---|
| Cases | 30 | 30 | 60 |
| Reference answer is the `-1` sentinel | **19** | 0 | 19 |
| Reference answer is a measured value | 11 | 30 | 41 |
| Order required (any POST fails the case) | 0 | 0 | **0** |
| **N0 PASS** | 0 | 0 | **0 / 60** |
| **N2 PASS** (blind answer, no GET) | **19** | 0 | **19 / 60** |

Per-case agreement with the G2 audit's prediction: **N0 60/60, N2 60/60.**

**19 of the 60 read-only cases are passable with zero evidence retrieval**, by stating the sentinel
the task text itself defines. Task 7 resists completely: its answer is always a measured value, so
no blind number can match. The contrast is the point — a task is retrieval-proof only when its
expected answer is a continuous function of the record, exactly as G1 found for task 9's dose.

## Audit of the zero-retrieval claim

`agent_log.jsonl` records every reply the scripts sent, and the saved trajectories were re-read
independently: **120 agent turns across the two runs, 0 GETs, 0 POSTs.** The log holds one extra
reply (121) from a single smoke test of the server before the runs started.

## Result 2 — the L1 sentinel rule detects all 19 (demonstration, not a thesis result)

The checker has **no task-4 or task-7 policy**: those await the supervisor's decision 2. To show the
L1 mechanism works on real trajectories, the 30 task-4 episodes were scored with
`tests/fixtures/sentinel_probe_v0.yaml` — an **authored software test fixture**, not a benchmark
policy, deliberately kept out of `policies/`.

| | N0 | N2 |
|---|---|---|
| task-4 episodes scored | 30 | 30 |
| Official PASS | 0 | 19 |
| …labelled `UNGROUNDED` | – | **19 / 19** |
| …`verified_outcome` | – | `UNVERIFIED_PASS` 19 |
| claim status | – | `sentinel_absence_not_established` 19 |
| reason given | – | "never retrieved, so absence was not established" |

So on this controlled sample every evidence-free pass is identified. **This is a constructed
positive control on 19 episodes with one failure mode; it is not an estimate of the evaluator's
sensitivity in general**, and it says nothing about false positives on agents that do retrieve.

## Provenance

Both runs carry a Milestone 1 manifest (`outputs/medomit_provenance/G2_null_ro_n{0,2}/`) recording
the grader hash, benchmark data hash, evaluator commit and source hash, simulator image digest and
host. The agents are scripted and deterministic, so no model seed applies; `seeds.deterministic`
is nonetheless reported as `false`, because the FHIR server's state is not pinned by a manifest.
