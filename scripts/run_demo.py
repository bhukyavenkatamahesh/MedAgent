"""Run the checker on the 4 synthetic demo cases and print the audit tables.

    python scripts/run_demo.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procsafe.adapters.demo_json import load_demo
from procsafe.checker import SafetyChecker
from procsafe.metrics import aggregate
from procsafe.policy import Policy
from procsafe.report import episode_summary, episode_table, write_outputs

policy = Policy.load(ROOT / "policies/demo_renal_v0.yaml")
episodes, expected = load_demo(ROOT / "data/synthetic_fhir_demo_data.json", policy)
print("Synthetic software demo: terminal outcomes and reference time are AUTHORED_TEST_INPUT, not observed benchmark results.\n")
checker = SafetyChecker(policy)
results = [checker.evaluate(ep) for ep in episodes]

for r in results:
    print(episode_table(r))
    print(json.dumps(episode_summary(r), indent=2))
    ok = r.process_result == expected[r.episode_id]["episode"]
    print(f"expected episode label: {expected[r.episode_id]['episode']}  ->  {'MATCH' if ok else 'MISMATCH'}\n")

metrics = aggregate(results)
metrics["input_provenance"] = "AUTHORED_TEST_INPUT"
metrics["interpretation"] = "Software demo metrics from authored synthetic inputs; not observed agent performance."
print("## Metrics\n" + json.dumps(metrics, indent=2))
write_outputs(results, metrics, ROOT / "outputs/demo")
print(f"\nWrote outputs/demo/ (episodes.jsonl, turn_labels.csv, metrics.json, report.md)")
