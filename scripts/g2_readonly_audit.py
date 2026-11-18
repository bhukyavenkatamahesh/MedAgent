"""G2 — read-only task audit (MedAgentBench tasks 4 and 7). No model inference.

The read-only analogue of G0/G1. For each of the 60 cases it recomputes the reference answer
directly from the FHIR server, exactly as the reference grader does, and reports which scripted
null agent the grader would pass:

    N0   `FINISH([])` only                — no GET, no POST, answer []
    N2   one blind fixed answer, no GET   — task 4: `FINISH([-1])` (the task's own no-data sentinel)
                                            task 7: `FINISH([<a fixed plausible value>])`

Both graders accept only an exact match of `[value]`, or `[-1]` when no qualifying measurement
exists, and both fail the case outright if the trajectory contains any POST (refsol.py task4 L87,
task7 L192). So N2's pass count on task 4 is exactly the number of cases whose reference answer is
the sentinel — obtainable with zero retrieval.

This is kept separate from the G0/G1 results for tasks 5/9/10. It adds no policy and changes no
score.

    python scripts/g2_readonly_audit.py --mab ../../MedAgentBench/MedAgentBench \
        --out runs/G2_readonly_audit
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

REFERENCE_TIME = datetime.fromisoformat("2023-11-13T10:15:00+00:00")

# Re-implemented from the reference grader's own code with line numbers cited. refsol.py is
# redistributed by Stanford and is never copied into this repository.
RULES = {
    "task4": {"code": "MG", "window_hours": 24,
              "refsol_lines": "task4(): check_has_post -> False at L87; Observation?code=MG&_count=5000 "
                              "at L89; 'if effective_time >= (cutoff - timedelta(hours=24))' at L96; "
                              "ref_sol = [last_value if last_value is not None else -1] at L100; "
                              "exact list comparison at L104"},
    "task7": {"code": "GLU", "window_hours": None,
              "refsol_lines": "task7(): check_has_post -> False at L192; Observation?code=GLU&_count=5000 "
                              "at L194; newest of any age at L200; ref_sol = [last_value if last_value "
                              "is not None else -1] at L203; exact list comparison at L207"},
}
# N2's blind answer. Task 4 uses the sentinel the task text itself defines. Task 7 has no sentinel
# path that a blind agent could rely on, so it states one fixed value; the number is arbitrary by
# design and is NOT a clinical value.
BLIND_ANSWER = {"task4": [-1], "task7": [100]}


def fhir_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read().decode())


def reference_answer(base: str, mrn: str, code: str, window_hours) -> tuple[list, int, int]:
    """(ref_sol, observations seen, observations inside the window) — the grader's own computation."""
    bundle = fhir_get(base, f"Observation?patient={mrn}&code={code}&_count=5000&_format=json")
    entries = bundle.get("entry", [])
    cutoff = REFERENCE_TIME - timedelta(hours=window_hours) if window_hours else None
    last_meas, last_value, in_window = None, None, 0
    for e in entries:
        res = e["resource"]
        when = datetime.fromisoformat(res["effectiveDateTime"])
        value = res["valueQuantity"]["value"]
        if cutoff is not None and when < cutoff:
            continue
        in_window += 1
        if last_meas is None or when > last_meas:
            last_meas, last_value = when, value
    return [last_value if last_value is not None else -1], len(entries), in_window


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mab", required=True)
    ap.add_argument("--fhir", default="http://localhost:8080/fhir/")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tasks = json.loads((Path(a.mab) / "data/medagentbench/test_data_v2.json").read_text())
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, case in enumerate(tasks):
        prefix = case["id"].split("_")[0]
        if prefix not in RULES:
            continue
        rule = RULES[prefix]
        ref, seen, in_window = reference_answer(a.fhir, case["eval_MRN"], rule["code"],
                                                rule["window_hours"])
        rows.append({
            "case_index": index, "task_id": case["id"], "patient_id": case["eval_MRN"],
            "code": rule["code"], "window_hours": rule["window_hours"],
            "observations_for_patient": seen, "observations_in_window": in_window,
            "reference_answer": json.dumps(ref),
            "answer_is_sentinel": ref == [-1],
            "order_required": False,            # both tasks are read-only: any POST fails the case
            "n0_passes": ref == [],             # FINISH([]) can never match [value] or [-1]
            "n2_passes": ref == BLIND_ANSWER[prefix],
            "n2_answer": json.dumps(BLIND_ANSWER[prefix]),
            "refsol_lines": rule["refsol_lines"],
        })
    with open(out / "g2_case_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    summary = {"fhir_base": a.fhir, "generated": datetime.now().astimezone().isoformat(),
               "note": "Read-only tasks. No model inference. No policy applied. Separate from G0/G1.",
               "tasks": {}}
    for prefix in RULES:
        sub = [r for r in rows if r["task_id"].startswith(prefix + "_")]
        summary["tasks"][prefix] = {
            "cases": len(sub),
            "order_required": 0,
            "reference_answer_is_sentinel": sum(r["answer_is_sentinel"] for r in sub),
            "reference_answer_is_a_value": sum(not r["answer_is_sentinel"] for r in sub),
            "observations_total": sum(r["observations_for_patient"] for r in sub),
            "n0_predicted_passes": sum(r["n0_passes"] for r in sub),
            "n2_predicted_passes": sum(r["n2_passes"] for r in sub),
            "n2_blind_answer": json.dumps(BLIND_ANSWER[prefix]),
            "refsol_lines": RULES[prefix]["refsol_lines"],
        }
    (out / "g2_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary["tasks"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
