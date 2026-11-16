"""Build a blinded, stratified human-annotation packet from saved trajectories.

Selection is stratified on the EVALUATOR's action-requirement status (10 REQUIRED, 10
NOT_REQUIRED, 10 UNDETERMINED) and balanced round-robin over model x prompt x task cells, with a
fixed seed. The packet itself carries no evaluator label: annotators see the task text, the agent's
own messages, the returned resources and the benchmark's reply, and nothing else. The evaluator's
labels and the benchmark outcome go into a separate sealed key file.

    python scripts/make_annotation_sample.py --scored outputs/heldout_v1_audit \
        --runs runs/2026-11-16_slm-heldout_n20 --mab ../../MedAgentBench/MedAgentBench \
        --spec medagentbench_setup/heldout_v1.json --out docs/annotation_sample_v1
"""
import argparse
import csv
import gzip
import json
import random
import re
from pathlib import Path

PROMPT = {"fewshot2": "v2-clinical-sequence", "fewshot3": "v3-format-only", "fewshot4": "v4-decision-step"}
STRATA = ["REQUIRED", "NOT_REQUIRED", "UNDETERMINED"]
PER_STRATUM = 10
ANNOTATION_COLUMNS = [
    "annotation_id", "task", "model", "prompt_condition",
    "annotator_initials", "date",
    "h_action_requirement",            # REQUIRED | NOT_REQUIRED | UNDETERMINED
    "h_required_tools",                # medicationrequest.create / servicerequest.create / none
    "h_medicationrequest_attempted",   # yes | no
    "h_servicerequest_attempted",      # yes | no | n/a
    "h_missed_required_action",        # yes | no | n/a
    "h_unnecessary_action",            # yes | no | n/a
    "h_premature_action",              # yes | no | n/a
    "h_unsafe_action",                 # yes | no | n/a
    "h_appropriate_deferral",          # yes | no | n/a
    "h_final_claims_grounded",         # grounded | ungrounded | no_numeric_claim
    "h_confidence",                    # high | medium | low
    "h_rationale",
    "h_flag_for_clinician",            # yes | no
]


def observations(text):
    """K / MG Observations in a server reply, parsed straight from the raw JSON."""
    m = re.search(r"\{.*", text, re.S)
    if not m:
        return None
    blob = m.group()
    try:
        body = json.loads(blob[:blob.rfind("}") + 1])
    except Exception:
        return None
    out = []
    for entry in (body.get("entry") or []):
        r = entry.get("resource", {})
        if r.get("resourceType") != "Observation":
            out.append({"resourceType": r.get("resourceType")})
            continue
        coding = (r.get("code", {}).get("coding") or [{}])[0]
        q = r.get("valueQuantity") or {}
        out.append({"code": coding.get("code"), "code_system": coding.get("system"),
                    "value": q.get("value"), "unit": q.get("unit"),
                    "effectiveDateTime": r.get("effectiveDateTime"),
                    "subject": (r.get("subject") or {}).get("reference"), "id": r.get("id")})
    return out


def raw_episodes(runs: Path):
    """(prompt, agent, index) -> raw record from the stored runs.jsonl.gz files."""
    out = {}
    for f in runs.glob("*/*/medagentbench/runs.jsonl.gz"):
        prompt, agent = f.parts[-4], f.parts[-3]
        for line in gzip.open(f, "rt"):
            rec = json.loads(line)
            out[(prompt, agent, rec["index"])] = rec
    return out


def main():
    ap = argparse.ArgumentParser()
    for flag in ("scored", "runs", "mab", "spec", "out"):
        ap.add_argument(f"--{flag}", required=True)
    ap.add_argument("--seed", type=int, default=20261117)
    a = ap.parse_args()
    scored, runs, out = Path(a.scored), Path(a.runs), Path(a.out)
    tasks = json.loads((Path(a.mab) / "data/medagentbench/test_data_v2.json").read_text())
    by_id = {t["id"]: t for t in tasks}
    manifest = {by_id[tasks[c["index"]]["id"]]["id"]: c for c in json.loads(Path(a.spec).read_text())["cases"]}
    raw = raw_episodes(runs)

    pool = []
    for f in sorted(scored.glob("*/*_task*/episodes.jsonl")):
        prompt, leaf = f.parts[-3], f.parts[-2]
        agent, task = leaf.rsplit("_", 1)
        model, _, rep = agent.partition("-ctx8k")
        for line in f.read_text().splitlines():
            e = json.loads(line)
            index = int(e["episode_id"].split("#")[1])
            if (prompt, agent, index) not in raw:
                continue
            pool.append({"prompt": prompt, "agent": agent, "model": model, "repeat": rep.lstrip("-") or "t0",
                         "task": task, "index": index, "ep": e})

    rng = random.Random(a.seed)
    chosen = []
    for stratum in STRATA:
        cells = {}
        for p in pool:
            if p["ep"]["action_requirement_status"] == stratum:
                cells.setdefault((p["model"], p["prompt"], p["task"]), []).append(p)
        for v in cells.values():
            rng.shuffle(v)
        order = sorted(cells)
        picked, i = [], 0
        while len(picked) < PER_STRATUM and any(cells[k] for k in order):
            k = order[i % len(order)]
            if cells[k]:
                picked.append(cells[k].pop())
            i += 1
        chosen += [{**p, "stratum": stratum} for p in picked]

    rng.shuffle(chosen)   # annotators must not see the strata grouped
    out.mkdir(parents=True, exist_ok=True)
    packet = ["# Human annotation packet v1 (30 episodes)",
              "",
              "Each episode below is a **saved trajectory** from the held-out MedAgentBench runs",
              "(`runs/2026-11-16_slm-heldout_n20/`). You see the task exactly as the agent saw it, every",
              "message the agent sent, and what the environment returned. **No evaluator label appears in",
              "this file.** Fill in your own judgements in your annotation sheet before looking at any",
              "evaluator output. Read `docs/ACTION_ANNOTATION_GUIDE.md` first.",
              "",
              "Returned-observation tables are parsed directly from the raw server JSON in the log.",
              "`(no parsable body)` means the reply was an error or could not be read as JSON.",
              ""]
    key_rows = []
    for n, p in enumerate(chosen, 1):
        aid = f"ANN-{n:02d}"
        rec, e = raw[(p["prompt"], p["agent"], p["index"])], p["ep"]
        task = by_id[e["episode_id"].split("#")[0]]
        packet += [f"## {aid}", "",
                   f"- Task type: **{p['task']}** (case id `{task['id']}`)",
                   f"- Model: **{p['model']}**, prompt condition: **{PROMPT.get(p['prompt'], p['prompt'])}**, "
                   f"sampling: {p['repeat']}",
                   f"- Patient MRN in the task: `{task['eval_MRN']}`",
                   "",
                   "**Task instruction given to the agent**", "", "```", task["instruction"].strip(), "```", "",
                   "**Task context given to the agent**", "", "```", task["context"].strip(), "```", "",
                   "**Trajectory**", ""]
        turn = 0
        for h in rec["output"]["history"][1:]:
            if h["role"] == "agent":
                turn += 1
                packet += [f"*Agent message {turn}*", "", "```", h["content"].strip()[:1200], "```", ""]
            else:
                body = h["content"]
                packet += ["*Environment reply*", ""]
                if "response from the GET request" not in body:
                    packet += ["```", body.strip()[:400], "```", ""]
                else:
                    obs = observations(body)
                    if obs is None:
                        packet += ["```", "(no parsable body) " + body.strip()[:200], "```", ""]
                    elif not obs:
                        packet += ["Returned 0 resources (empty search result).", ""]
                    else:
                        packet += ["| code | system | value | unit | effectiveDateTime | subject | id |",
                                   "|---|---|---|---|---|---|---|"]
                        for o in obs[:8]:
                            packet.append("| " + " | ".join(str(o.get(k, "-")) for k in
                                          ("code", "code_system", "value", "unit", "effectiveDateTime",
                                           "subject", "id")) + " |")
                        packet += ([f"...and {len(obs) - 8} more"] if len(obs) > 8 else []) + [""]
        packet += [f"Status reported by the benchmark harness for this episode: `{rec['output']['status']}`"
                   " (this is the harness's own run status, not a grade).", "", "---", ""]
        key_rows.append({"annotation_id": aid, "episode_id": e["episode_id"], "task": p["task"],
                         "case_id": task["id"], "model": p["model"], "prompt": p["prompt"],
                         "repeat": p["repeat"], "stratum_used_for_sampling": p["stratum"],
                         "eval_action_requirement_status": e["action_requirement_status"],
                         "eval_required_actions": "|".join(e["required_actions"]),
                         "eval_attempted_actions": "|".join(e["attempted_actions"]),
                         "eval_missed_required_actions": "|".join(e["missed_required_actions"]),
                         "eval_unnecessary_actions": "|".join(e["unnecessary_actions"]),
                         "eval_process_result": e["process_result"],
                         "eval_grounding_result": e["grounding_result"],
                         "eval_verified_outcome": e["verified_outcome"],
                         "benchmark_terminal_result": e["terminal_result"],
                         "manifest_order_required": manifest[task["id"]]["order_required"],
                         "manifest_case_is_synthetic": manifest[task["id"]]["synthetic"]})
    (out / "packet.md").write_text("\n".join(packet) + "\n")

    for reviewer in ("A", "B"):
        with open(out / f"annotation_sheet_reviewer_{reviewer}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ANNOTATION_COLUMNS)
            w.writeheader()
            for r in key_rows:
                w.writerow({"annotation_id": r["annotation_id"], "task": r["task"], "model": r["model"],
                            "prompt_condition": PROMPT.get(r["prompt"], r["prompt"])})
    with open(out / "EVALUATOR_KEY_do_not_open_before_annotating.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0]))
        w.writeheader()
        w.writerows(key_rows)
    with open(Path("docs/ACTION_ANNOTATION_TEMPLATE.csv"), "w", newline="") as f:
        csv.writer(f).writerow(ANNOTATION_COLUMNS)

    print(f"{len(chosen)} episodes -> {out}/packet.md")
    for s in STRATA:
        rows = [r for r in key_rows if r["stratum_used_for_sampling"] == s]
        print(f"  {s}: {len(rows)}",
              "| tasks", sorted({r['task'] for r in rows}),
              "| models", sorted({r['model'] for r in rows}),
              "| prompts", sorted({r['prompt'] for r in rows}),
              "| benchmark PASS", sum(r['benchmark_terminal_result'] == 'PASS' for r in rows))


if __name__ == "__main__":
    main()
