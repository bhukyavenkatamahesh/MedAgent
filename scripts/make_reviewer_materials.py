"""Build reviewer-facing (blinded) annotation materials. The source package is never modified.

Two subcommands:

    blind        anonymise the 30-episode sample: strip model and prompt names, the internal case
                 id and the harness run status; keep the task identity, the task text and the full
                 trajectory with every returned value, unit, timestamp and patient reference.
    calibration  render three separate calibration trajectories, in the same blinded format, from
                 the PROMPT-DEVELOPMENT cases, so they cannot overlap the 30-episode sample.

The original-to-anonymous mapping is written outside the reviewer-facing directory. Neither
subcommand reads the evaluator key, and neither writes any annotation.

    python scripts/make_reviewer_materials.py blind
    python scripts/make_reviewer_materials.py calibration --mab ../../MedAgentBench/MedAgentBench
"""
from __future__ import annotations

import argparse
import csv
import shutil
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("mas", ROOT / "scripts/make_annotation_sample.py")
mas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mas)          # reuse the raw-JSON observation parser

# Reviewer sheets carry the episode id, the task type and the reviewer's own judgements. No
# system, configuration or run identifier: those would let a reviewer group episodes by model or
# prompt. They live only in the hidden mapping, and are joined back after adjudication.
SHEET_COLUMNS = ["annotation_id", "task", "annotator_initials", "date",
                 "h_action_requirement", "h_required_tools", "h_medicationrequest_attempted",
                 "h_servicerequest_attempted", "h_missed_required_action", "h_unnecessary_action",
                 "h_premature_action", "h_unsafe_action", "h_appropriate_deferral",
                 "h_final_claims_grounded", "h_confidence", "h_rationale", "h_flag_for_clinician"]

PREAMBLE = """# {title}

Each episode below is a saved trajectory of a software agent working on one clinical benchmark task.
You see the task exactly as the agent saw it, every message the agent sent, and what the environment
returned. **Which system produced a trajectory is deliberately withheld**, and so is any way of
telling which episodes came from the same system, prompt or run. No result, score or automatic
label appears anywhere in this file.

Fill in your own judgements in your annotation sheet. Read `ACTION_ANNOTATION_GUIDE.md` first.

Returned-observation tables are parsed directly from the raw server JSON in the log.
`(no parsable body)` means the reply was an error or could not be read as JSON.
"""


def render(aid: str, task: dict, history: list[dict], task_type: str) -> list[str]:
    """One blinded episode block: task text plus the chronological trajectory.

    Nothing identifies which system, prompt configuration or run produced it, not even an
    anonymous id, so episodes cannot be grouped by their origin.
    """
    out = [f"## {aid}", "",
           f"- Task type: **{task_type}**",
           f"- Patient MRN in the task: `{task['eval_MRN']}`",
           "",
           "**Task instruction given to the agent**", "", "```", task["instruction"].strip(), "```", "",
           "**Task context given to the agent**", "", "```", task["context"].strip(), "```", "",
           "**Trajectory**", ""]
    turn = 0
    for h in history:
        if h["role"] == "agent":
            turn += 1
            out += [f"*Agent message {turn}*", "", "```", h["content"].strip()[:1200], "```", ""]
            continue
        body = h["content"]
        out += ["*Environment reply*", ""]
        if "response from the GET request" not in body:
            out += ["```", body.strip()[:400], "```", ""]
            continue
        obs = mas.observations(body)
        if obs is None:
            out += ["```", "(no parsable body) " + body.strip()[:200], "```", ""]
        elif not obs:
            out += ["Returned 0 resources (empty search result).", ""]
        else:
            out += ["| code | system | value | unit | effectiveDateTime | subject | id |",
                    "|---|---|---|---|---|---|---|"]
            for o in obs[:8]:
                out.append("| " + " | ".join(str(o.get(k, "-")) for k in
                           ("code", "code_system", "value", "unit", "effectiveDateTime",
                            "subject", "id")) + " |")
            out += ([f"...and {len(obs) - 8} more"] if len(obs) > 8 else []) + [""]
    return out + ["---", ""]


def ship_guide(out_dir: Path) -> None:
    """Copy the label definitions in beside the packet, so the folder is self-contained.

    The guide is reviewer-facing by design and must contain the label names; the blinding QA
    therefore skips it by filename when scanning for leaks.
    """
    shutil.copy(ROOT / "docs/ACTION_ANNOTATION_GUIDE.md", out_dir / "ACTION_ANNOTATION_GUIDE.md")


def write_sheets(out_dir: Path, rows: list[dict], prefix: str) -> None:
    for reviewer in ("A", "B"):
        with open(out_dir / f"{prefix}_reviewer_{reviewer}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({"annotation_id": r["annotation_id"], "task": r["task"]})


def write_map(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fields} for r in rows])


# ---------------------------------------------------------------- blind


def blind(a) -> None:
    src, out = Path(a.source), Path(a.out)
    packet = (src / "packet.md").read_text()
    blocks = re.findall(r"^## (ANN-\d+)\n(.*?)(?=^## ANN-|\Z)", packet, re.S | re.M)
    meta = []
    for aid, body in blocks:
        meta.append({"annotation_id": aid,
                     "task": re.search(r"Task type: \*\*(\w+)\*\*", body).group(1),
                     "case_id": re.search(r"case id `([^`]+)`", body).group(1),
                     "model": re.search(r"Model: \*\*([^*]+)\*\*", body).group(1),
                     "prompt_condition": re.search(r"prompt condition: \*\*([^*]+)\*\*", body).group(1),
                     "sampling": re.search(r"sampling: (\S+)", body).group(1),
                     "body": body})
    systems = {m: f"SYS-{i}" for i, m in enumerate(sorted({x["model"] for x in meta}), 1)}
    conds = {c: f"CND-{i}" for i, c in enumerate(sorted({x["prompt_condition"] for x in meta}), 1)}
    runs = {r: f"RUN-{i:02d}" for i, r in enumerate(
        sorted({(x["model"], x["prompt_condition"], x["sampling"]) for x in meta}), 1)}
    lines = [PREAMBLE.format(title=f"Annotation packet ({len(meta)} episodes)"), ""]
    for m in meta:
        m["sys_id"] = systems[m["model"]]
        m["cnd_id"] = conds[m["prompt_condition"]]
        m["run_id"] = runs[(m["model"], m["prompt_condition"], m["sampling"])]
        body = m["body"]
        instruction = re.search(r"\*\*Task instruction given to the agent\*\*\n\n```\n(.*?)\n```",
                                body, re.S).group(1)
        context = re.search(r"\*\*Task context given to the agent\*\*\n\n```\n(.*?)\n```",
                            body, re.S).group(1)
        traj = body.split("**Trajectory**", 1)[1]
        # drop the harness run status: it is experiment metadata, not part of the trajectory
        traj = re.sub(r"\nStatus reported by the benchmark harness.*?\n", "\n", traj, flags=re.S)
        traj = traj.rstrip().rstrip("-").rstrip()
        mrn = re.search(r"Patient MRN in the task: `(\S+)`", body).group(1)
        lines += [f"## {m['annotation_id']}", "",
                  f"- Task type: **{m['task']}**",
                  f"- Patient MRN in the task: `{mrn}`",
                  "", "**Task instruction given to the agent**", "", "```", instruction, "```", "",
                  "**Task context given to the agent**", "", "```", context, "```", "",
                  "**Trajectory**", traj, "", "---", ""]
    out.mkdir(parents=True, exist_ok=True)
    (out / "packet.md").write_text("\n".join(lines) + "\n")
    ship_guide(out)
    write_sheets(out, meta, "annotation_sheet")
    write_map(Path(a.map), meta, ["annotation_id", "task", "case_id", "model", "prompt_condition",
                                  "sampling", "sys_id", "cnd_id", "run_id"])
    print(f"blinded packet -> {out}/packet.md  ({len(meta)} episodes)")
    print(f"blinded sheets -> {out}/annotation_sheet_reviewer_[A|B].csv")
    print(f"mapping (NOT for reviewers) -> {a.map}")
    print("hidden mapping holds", len(systems), "systems,", len(conds), "configurations and",
          len(runs), "runs; none of these ids appears in the reviewer materials")


# ---------------------------------------------------------------- calibration


# "<path to the run condition/agent directory>:<case index>". All three come from the
# PROMPT-DEVELOPMENT cases (task9 240-244, task5 120-124), which appear nowhere in the
# 30-episode sample, and they exercise the three action-requirement distinctions plus a
# premature order. No label is shown to reviewers.
DEFAULT_CALIBRATION = [
    "runs/2026-11-16_slm-ablation_n10/fewshot4_strict/qwen2.5-1.5b-ctx8k:242",
    "runs/2026-11-16_slm-fewshot_n10/fewshot2_strict/qwen2.5-1.5b-ctx8k:244",
    "runs/2026-11-16_slm-fewshot_n10/fewshot2_strict/llama3.2-1b-ctx8k:124",
]


def calibration(a) -> None:
    out = Path(a.out)
    tasks = json.loads((Path(a.mab) / "data/medagentbench/test_data_v2.json").read_text())
    sample_packet = (Path(a.sample) / "packet.md").read_text()
    sample_cases = set(re.findall(r"case id `([^`]+)`", sample_packet))
    sample_mrns = set(re.findall(r"Patient MRN in the task: `(\S+)`", sample_packet))
    rows, lines = [], [PREAMBLE.format(title="Calibration packet (3 episodes)"), "",
                       "These three episodes are **calibration material**. They come from different",
                       "patients and different benchmark cases than the main packet, and their",
                       "annotations are discarded after the calibration discussion.", ""]
    for n, spec in enumerate(a.episodes or DEFAULT_CALIBRATION, 1):
        run_path, _, index = spec.rpartition(":")
        index = int(index)
        cond, agent = Path(run_path).parts[-2], Path(run_path).name
        task = tasks[index]
        if task["id"] in sample_cases or task["eval_MRN"] in sample_mrns:
            raise SystemExit(f"REFUSING: {spec} ({task['id']}, {task['eval_MRN']}) overlaps the "
                             "30-episode sample")
        path = Path(run_path) / "medagentbench/runs.jsonl"
        rec = next(json.loads(l) for l in path.read_text().splitlines()
                   if json.loads(l)["index"] == index)
        aid = f"CAL-{n}"
        model, _, rep = agent.partition("-ctx8k")
        rows.append({"annotation_id": aid, "task": task["id"].split("_")[0], "case_id": task["id"],
                     "model": model, "prompt_condition": cond, "sampling": rep.lstrip("-") or "t0",
                     "sys_id": f"SYS-C{n}", "cnd_id": f"CND-C{n}", "run_id": f"RUN-C{n}",
                     "source": spec, "mrn": task["eval_MRN"]})
        lines += render(aid, task, rec["output"]["history"][1:], task["id"].split("_")[0])
    out.mkdir(parents=True, exist_ok=True)
    (out / "packet.md").write_text("\n".join(lines) + "\n")
    ship_guide(out)
    write_sheets(out, rows, "calibration_sheet")
    write_map(Path(a.map), rows, ["annotation_id", "task", "case_id", "mrn", "model",
                                  "prompt_condition", "sampling", "sys_id", "cnd_id", "run_id",
                                  "source"])
    print(f"calibration packet -> {out}/packet.md  ({len(rows)} episodes)")
    print(f"calibration sheets -> {out}/calibration_sheet_reviewer_[A|B].csv")
    print(f"mapping (NOT for reviewers) -> {a.map}")
    for r in rows:
        print(f"  {r['annotation_id']}: case {r['case_id']} (MRN {r['mrn']}) from {r['source']}"
              " - not in the 30-episode sample")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("blind", help="anonymise the 30-episode sample")
    b.add_argument("--source", default="docs/annotation_sample_v1")
    b.add_argument("--out", default="docs/annotation_sample_v1_blinded")
    b.add_argument("--map", default="docs/annotation_sample_v1/blinding_map_do_not_share.csv")
    b.set_defaults(func=blind)
    c = sub.add_parser("calibration", help="render separate calibration trajectories")
    c.add_argument("--mab", default="/Users/venkatamahesh/Desktop/MedAgentBench/MedAgentBench")
    c.add_argument("--sample", default="docs/annotation_sample_v1")
    c.add_argument("--out", default="docs/annotation_calibration_v1_blinded")
    c.add_argument("--map", default="docs/annotation_calibration_v1_map_do_not_share.csv")
    c.add_argument("--episodes", nargs="*",
                   help="'<run condition/agent dir>:<case index>' specs")
    c.set_defaults(func=calibration)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
