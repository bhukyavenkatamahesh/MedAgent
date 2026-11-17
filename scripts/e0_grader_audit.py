"""E0 — grader audit. Pins the reference grader by hash and classifies all 90 check-then-order
cases as order-needed or not, directly from the FHIR server, with no model inference.

For each case it also predicts which scripted null agent the *reference grader* would pass:

    N0  "FINISH([]) only"          — no GET, no POST, final answer []
    N1  "one blind fixed order"    — the task's expected POST(s) with no GET, then FINISH([])

The order rules are re-implemented here from the reference grader's own code, with line numbers
cited, because `refsol.py` is redistributed by Stanford and is never copied into this repository.
E1 then checks these predictions empirically by running the scripts through the real grader.

    python scripts/e0_grader_audit.py --mab ../../MedAgentBench/MedAgentBench \
        --out runs/E0_grader_audit
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

REFERENCE_TIME = datetime.fromisoformat("2023-11-13T10:15:00+00:00")

# Rules as implemented by the reference grader (refsol.py, 350 lines, sha256 67d19da2…).
RULES = {
    "task5": {"code": "MG", "window_hours": 24, "trigger": "value <= 1.9",
              "posts_required": 1, "payload_depends_on_value": True,
              "refsol_lines": "task5(): window cutoff-24h at L118; 'elif (last_value>1.9)' no-order at L126; "
                              "dose bands 4/2/1 g from last_value at L142-147"},
    "task9": {"code": "K", "window_hours": None, "trigger": "value < 3.5",
              "posts_required": 2, "payload_depends_on_value": True,
              "refsol_lines": "task9(): 'if (last_value is None) or (last_value>=3.5)' no-order at L250; "
                              "two POSTs required at L255; dose (3.5-last_value)/0.1*10 at L266"},
    "task10": {"code": "A1C", "window_hours": None, "trigger": "no result, or last result older than 1 year",
               "posts_required": 1, "payload_depends_on_value": False,
               "refsol_lines": "task10(): 'if (last_value is None) or (last_meas < 2022-11-13T10:15)' order "
                               "needed at L320; one ServiceRequest POST at L322; payload fields are all "
                               "constants plus the MRN (L328-335), none derived from the observed value"},
}


def latest(fhir: str, mrn: str, code: str, window_hours: float | None):
    url = f"{fhir}/Observation?patient={mrn}&code={code}&_count=5000&_format=json"
    with urllib.request.urlopen(url, timeout=30) as r:
        bundle = json.load(r)
    best = None
    for entry in bundle.get("entry", []):
        res = entry["resource"]
        when = datetime.fromisoformat(res["effectiveDateTime"])
        if window_hours is not None and when < REFERENCE_TIME - timedelta(hours=window_hours):
            continue
        value = res["valueQuantity"]["value"]
        if best is None or when > best[0]:
            best = (when, value)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mab", required=True)
    ap.add_argument("--fhir", default="http://localhost:8080/fhir")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    mab, out = Path(a.mab), Path(a.out)
    tasks = json.loads((mab / "data/medagentbench/test_data_v2.json").read_text())
    refsol = mab / "src/server/tasks/medagentbench/refsol.py"
    provenance = {
        "refsol_path": str(refsol),
        "refsol_sha256": hashlib.sha256(refsol.read_bytes()).hexdigest() if refsol.exists() else None,
        "refsol_lines": sum(1 for _ in refsol.open()) if refsol.exists() else None,
        "refsol_in_public_git": False,   # verified: git ls-files reports it untracked in the clone
        "refsol_note": ("MedAgentBench does not ship refsol.py in its GitHub repository (verified with "
                        "`git ls-files --error-unmatch`), so there is no public copy to diff against. "
                        "The grader is therefore pinned by hash and audited by reading its logic."),
        "test_data_sha256": hashlib.sha256((mab / "data/medagentbench/test_data_v2.json").read_bytes()).hexdigest(),
        "reference_time": REFERENCE_TIME.isoformat(),
        "fhir": a.fhir,
    }

    rows = []
    for index, task in enumerate(tasks):
        kind = task["id"].split("_")[0]
        rule = RULES.get(kind)
        if rule is None:
            continue
        best = latest(a.fhir, task["eval_MRN"], rule["code"], rule["window_hours"])
        when, value = (None, None) if best is None else (best[0], best[1])
        if kind == "task5":
            order_needed = value is not None and value <= 1.9
        elif kind == "task9":
            order_needed = value is not None and value < 3.5
        else:
            order_needed = value is None or when < REFERENCE_TIME - timedelta(days=365)
        # The grader accepts [] as the final answer for all three tasks ("We only ask the model to
        # check"), so a null agent's answer never costs it the case; only the POSTs matter.
        n0_passes = not order_needed
        n1_passes = order_needed and not rule["payload_depends_on_value"]
        rows.append({"index": index, "case_id": task["id"], "task": kind, "mrn": task["eval_MRN"],
                     "lab": rule["code"],
                     "window": "24h" if rule["window_hours"] else "any age",
                     "latest_value": "" if value is None else value,
                     "latest_time": "" if when is None else when.isoformat(),
                     "order_needed": order_needed,
                     "posts_required_if_order": rule["posts_required"],
                     "payload_depends_on_value": rule["payload_depends_on_value"],
                     "N0_finish_only_passes": n0_passes,
                     "N1_blind_order_passes": n1_passes})

    out.mkdir(parents=True, exist_ok=True)
    with open(out / "e0_case_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"provenance": provenance, "rules": RULES, "cases": len(rows), "by_task": {}}
    for kind in ("task5", "task9", "task10"):
        sub = [r for r in rows if r["task"] == kind]
        summary["by_task"][kind] = {
            "cases": len(sub),
            "order_needed": sum(r["order_needed"] for r in sub),
            "no_order": sum(not r["order_needed"] for r in sub),
            "N0_would_pass": sum(r["N0_finish_only_passes"] for r in sub),
            "N1_would_pass": sum(r["N1_blind_order_passes"] for r in sub),
        }
    summary["totals"] = {k: sum(v[k] for v in summary["by_task"].values())
                         for k in ("cases", "order_needed", "no_order", "N0_would_pass", "N1_would_pass")}
    (out / "e0_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({"provenance": {k: provenance[k] for k in ("refsol_sha256", "refsol_in_public_git")},
                      "by_task": summary["by_task"], "totals": summary["totals"]}, indent=1))


if __name__ == "__main__":
    main()
