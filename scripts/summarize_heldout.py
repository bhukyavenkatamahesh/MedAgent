"""Score every held-out run (prompt x model x repeat) and report mean and range over repeats.

    python scripts/summarize_heldout.py --mab ../../MedAgentBench/MedAgentBench \
        --spec medagentbench_setup/heldout_v1.json --out outputs/heldout_v1 [--policy-version v2]
"""
import argparse
import collections
import json
import statistics
import subprocess
import sys
from pathlib import Path

POLICY_NAMES = {"task9": "mab_task9_potassium", "task5": "mab_task5_magnesium"}
KEYS = ["missed_action", "action_indicated", "pass", "verified_pass", "pos_pass", "pos_ordered", "neg_pass", "neg_ordered",
        "unsafe_order_eps", "ungrounded", "invalid_or_limit", "lab_read"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mab", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs-dir", default="outputs/SLM_heldout")
    ap.add_argument("--policy-version", default="v2", help="v1 (no missed-action rule) or v2")
    a = ap.parse_args()
    mab, out = Path(a.mab), Path(a.out)
    spec = json.loads(Path(a.spec).read_text())
    tasks = json.loads((mab / "data/medagentbench/test_data_v2.json").read_text())
    required = {tasks[c["index"]]["id"]: c["order_required"] for c in spec["cases"]}

    runs = []
    for run_dir in sorted((mab / a.runs_dir).glob("*/*/medagentbench-std")):
        if not (run_dir / "overall.json").exists():
            continue
        prompt, agent = run_dir.parts[-3], run_dir.parts[-2]
        eps = []
        for task, pol in ((t, f"{n}_{a.policy_version}") for t, n in POLICY_NAMES.items()):
            dst = out / prompt / f"{agent}_{task}"
            subprocess.run([sys.executable, "scripts/run_medagentbench.py", "--runs", str(run_dir / "runs.jsonl"),
                            "--tasks", str(mab / "data/medagentbench/test_data_v2.json"),
                            "--overall", str(run_dir / "overall.json"), "--policy", f"policies/{pol}.yaml",
                            "--tasks-prefix", task, "--out", str(dst)], check=True, capture_output=True)
            eps += [json.loads(l) for l in (dst / "episodes.jsonl").read_text().splitlines()]
        status = collections.Counter(r["status"] for r in json.loads((run_dir / "overall.json").read_text())["custom"]["raw_results"])
        pos = [e for e in eps if required[e["task_id"]]]
        neg = [e for e in eps if not required[e["task_id"]]]
        ordered = lambda e: e["guarded_action_count"] > 0
        read = lambda e: any("RETRIEVE_REQUIRED" in t["labels"] or "RETRIEVE_EMPTY" in t["labels"] for t in e["turns"])
        model, _, rep = agent.partition("-ctx8k")
        runs.append({
            "prompt": prompt, "model": model, "repeat": rep.lstrip("-") or "t0", "n": len(eps),
            "n_pos": len(pos), "n_neg": len(neg),
            "missed_action": sum(e["missed_action"] for e in eps),
            "action_indicated": sum(e["action_indicated"] is True for e in eps),
            "pass": sum(e["terminal_result"] == "PASS" for e in eps),
            "verified_pass": sum(e["verified_outcome"] == "VERIFIED_PASS" for e in eps),
            "pos_pass": sum(e["terminal_result"] == "PASS" for e in pos),
            "pos_ordered": sum(map(ordered, pos)),
            "neg_pass": sum(e["terminal_result"] == "PASS" for e in neg),
            "neg_ordered": sum(map(ordered, neg)),
            "unsafe_order_eps": sum(e["unsafe_action_count"] > 0 for e in eps),
            "ungrounded": sum(e["grounding_result"] == "UNGROUNDED" for e in eps),
            "invalid_or_limit": sum(v for k, v in status.items() if not k.startswith("completed")),
            "lab_read": sum(map(read, eps)),
            "process_labels": dict(collections.Counter(e["process_result"] or "unclassified" for e in eps)),
        })

    groups = collections.defaultdict(list)
    for r in runs:
        groups[(r["prompt"], r["model"])].append(r)
    summary = []
    for (prompt, model), rs in sorted(groups.items()):
        det = next((r for r in rs if r["repeat"] == "t0"), None)
        sampled = [r for r in rs if r["repeat"] != "t0"]
        row = {"prompt": prompt, "model": model, "n": rs[0]["n"], "sampled_repeats": len(sampled)}
        for k in KEYS:
            vals = [r[k] for r in sampled]
            row[k] = {"t0": det[k] if det else None,
                      "sampled": vals,
                      "mean": round(statistics.mean(vals), 2) if vals else None,
                      "sd": round(statistics.stdev(vals), 2) if len(vals) > 1 else None,
                      "min": min(vals) if vals else None, "max": max(vals) if vals else None}
        summary.append(row)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"runs": runs, "summary": summary}, indent=1))

    fmt = lambda c: f"{c['t0']} | {c['mean']} ({c['min']}-{c['max']})"
    print("prompt | model | " + " | ".join(f"{k} t0 | {k} sampled mean (range)" for k in KEYS))
    for row in summary:
        print(f"{row['prompt']} | {row['model']} | " + " | ".join(fmt(row[k]) for k in KEYS))


if __name__ == "__main__":
    main()
