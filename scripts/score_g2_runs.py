"""Score the G2 read-only null-agent trajectories with the real task-4 and task-7 policies.

Read-only with respect to the trajectories; writes only into --out.

    python scripts/score_g2_runs.py --runs runs/G2_null_agents \
        --tasks ../../MedAgentBench/MedAgentBench/data/medagentbench/test_data_v2.json \
        --out outputs/g2_real_policy
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procsafe.adapters.medagentbench import load_overall_terminal, load_runs
from procsafe.checker import SafetyChecker
from procsafe.metrics import aggregate
from procsafe.policy import Policy
from procsafe.report import write_outputs

POLICIES = {"task4": "policies/mab_task4_magnesium_query_v1.yaml",
            "task7": "policies/mab_task7_glucose_query_v1.yaml"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    report = {}
    for run in sorted(Path(a.runs).glob("null-ro-*")):
        gz = run / "runs.jsonl.gz"
        runs_file = Path(tempfile.mkdtemp()) / "runs.jsonl"
        runs_file.write_bytes(gzip.open(gz, "rb").read())
        terminal = load_overall_terminal(run / "overall.json")
        for task, path in POLICIES.items():
            policy = Policy.load(ROOT / path)
            eps = load_runs(str(runs_file), a.tasks, terminal, (task,), lenient=False)
            res = [SafetyChecker(policy).evaluate(e) for e in eps]
            out = Path(a.out) / f"{run.name}_{task}"
            write_outputs(res, aggregate(res), out)
            passes = [r for r in res if r.terminal_result == "PASS"]
            report[f"{run.name}/{task}"] = {
                "policy": policy.policy_id, "episodes": len(res),
                "official_pass": len(passes),
                "action_requirement_status": dict(Counter(r.action_requirement_status for r in res)),
                "decision_grounding": dict(Counter(r.decision_grounding for r in res)),
                "answer_grounding": dict(Counter(str(r.grounding_result) for r in res)),
                "process_result": dict(Counter(str(r.process_result) for r in res)),
                "appropriate_defer": sum(r.appropriate_defer for r in res),
                "missed_required_action": sum(r.missed_required_action for r in res),
                "unnecessary_action": sum(r.unnecessary_action for r in res),
                "constraint_applicability": dict(Counter(
                    json.dumps(r.constraint_applicability, sort_keys=True) for r in res)),
                "passes_verified_outcome": dict(Counter(str(r.verified_outcome) for r in passes)),
                "passes_claim_status": dict(Counter(d["status"] for r in passes
                                                    for d in r.claim_details)),
            }
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "g2_real_policy_summary.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
