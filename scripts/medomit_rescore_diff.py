"""Re-score saved trajectories with the current evaluator and diff against frozen scored outputs.

The regression guard for any change to the scoring path: it answers "which published label would
this change move?" with evidence instead of argument. Read-only — it writes nothing unless --out
is given, and it never touches the frozen inputs.

    python scripts/medomit_rescore_diff.py \
        --frozen outputs/heldout_v1_audit \
        --runs runs/2026-11-16_slm-heldout_n20 \
        --tasks ../../MedAgentBench/MedAgentBench/data/medagentbench/test_data_v2.json \
        --policy task5=policies/mab_task5_magnesium_v2.yaml \
        --policy task9=policies/mab_task9_potassium_v2.yaml
"""
from __future__ import annotations

import argparse
import csv
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
from procsafe.policy import Policy

FIELDS = ("terminal_result", "process_result", "grounding_result", "verified_outcome",
          "action_requirement_status")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", required=True, help="directory of frozen */*_task*/episodes.jsonl")
    ap.add_argument("--runs", required=True, help="matching runs/<experiment> tree")
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--policy", action="append", required=True, metavar="PREFIX=PATH")
    ap.add_argument("--lenient", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    pol = {}
    for spec in a.policy:
        prefix, _, path = spec.partition("=")
        pol[prefix] = Policy.load(path)

    diffs, compared, skipped = [], 0, []
    for frozen in sorted(Path(a.frozen).glob("*/*_task*/episodes.jsonl")):
        prompt, leaf = frozen.parts[-3], frozen.parts[-2]
        agent, task = leaf.rsplit("_", 1)
        if task not in pol:
            skipped.append(f"{prompt}/{leaf}: no policy for {task}")
            continue
        run = Path(a.runs) / prompt / agent / "medagentbench"
        runs_file, gz = run / "runs.jsonl", run / "runs.jsonl.gz"
        if gz.exists():
            runs_file = Path(tempfile.mkdtemp()) / "runs.jsonl"
            runs_file.write_bytes(gzip.open(gz, "rb").read())
        if not runs_file.exists():
            skipped.append(f"{prompt}/{leaf}: no runs.jsonl"); continue
        terminal = load_overall_terminal(run / "overall.json") if (run / "overall.json").exists() else None
        episodes = load_runs(str(runs_file), a.tasks, terminal, (task,), lenient=a.lenient)
        now = {e.episode_id: SafetyChecker(pol[task]).evaluate(e) for e in episodes}
        for line in frozen.read_text().splitlines():
            before = json.loads(line)
            after = now.get(before["episode_id"])
            if after is None:
                skipped.append(f"{prompt}/{leaf}: {before['episode_id']} not re-scored"); continue
            compared += 1
            for f in FIELDS:
                b, n = before.get(f), getattr(after, f, None)
                if b != n:
                    diffs.append({"prompt": prompt, "agent": agent, "task": task,
                                  "episode_id": before["episode_id"], "field": f,
                                  "before": b, "after": n})

    summary = {"episodes_compared": compared, "field_changes": len(diffs),
               "changes_by_transition": {f"{d['field']}: {d['before']} -> {d['after']}": c
                                         for d, c in _group(diffs)},
               "skipped": skipped}
    print(json.dumps(summary, indent=1))
    if a.out:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        (out / "rescore_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
        with open(out / "rescore_diffs.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["prompt", "agent", "task", "episode_id", "field",
                                              "before", "after"])
            w.writeheader(); w.writerows(diffs)
    return 1 if diffs else 0


def _group(diffs):
    counts = Counter((d["field"], str(d["before"]), str(d["after"])) for d in diffs)
    for (field, before, after), c in counts.items():
        yield {"field": field, "before": before, "after": after}, c


if __name__ == "__main__":
    sys.exit(main())
