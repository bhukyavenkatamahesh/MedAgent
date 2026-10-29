"""Run the checker on real MedAgentBench logs.

    python scripts/run_medagentbench.py \
        --runs   ../MedAgentBench/outputs/MedAgentBenchv1/gpt-4o-mini/medagentbench-std/runs.jsonl \
        --tasks  ../MedAgentBench/data/medagentbench/test_data_v2.json \
        --overall ../MedAgentBench/outputs/MedAgentBenchv1/gpt-4o-mini/medagentbench-std/overall.json \
        --policy policies/mab_task9_potassium_v0.yaml --tasks-prefix task9 \
        --out outputs/mab_gpt4omini_task9
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procsafe.adapters.medagentbench import load_overall_terminal, load_runs
from procsafe.checker import SafetyChecker
from procsafe.metrics import aggregate
from procsafe.policy import Policy
from procsafe.report import write_outputs

ap = argparse.ArgumentParser()
ap.add_argument("--runs", required=True)
ap.add_argument("--tasks", required=True)
ap.add_argument("--overall", help="overall.json with Correct/Incorrect status per index")
ap.add_argument("--policy", required=True)
ap.add_argument("--tasks-prefix", nargs="+", default=["task9"])
ap.add_argument("--out", required=True)
a = ap.parse_args()

policy = Policy.load(a.policy)
if policy.status.startswith("TEMPLATE"):
    sys.exit("Refusing to run a TEMPLATE policy: fill in and review the thresholds first.")
terminal = load_overall_terminal(a.overall) if a.overall else None
episodes = load_runs(a.runs, a.tasks, terminal, tuple(a.tasks_prefix))
results = [SafetyChecker(policy).evaluate(ep) for ep in episodes]
metrics = aggregate(results)
write_outputs(results, metrics, a.out)
print(json.dumps(metrics, indent=2))
missing = sum(ep.terminal_result is None for ep in episodes)
if missing:
    print(f"WARNING: {missing} episodes have no terminal PASS/FAIL (pass --overall).")
