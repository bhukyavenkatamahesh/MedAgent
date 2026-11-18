"""MedOmit provenance CLI: build a run manifest, or the five-view output-status table.

Read-only with respect to every existing artefact: it writes only into --out, and refuses to write
into a non-empty directory unless --force is given. It records what it can verify and lists what it
cannot, with a reason. It never alters an official grade.

    # manifest for a historical run (fields that cannot be recovered are reported, not invented)
    python scripts/medomit_provenance.py manifest \
        --run runs/2026-11-16_slm-heldout_n20/fewshot4/qwen2.5-1.5b-ctx8k \
        --mab ../../MedAgentBench/MedAgentBench \
        --policy policies/mab_task9_potassium_v2.yaml --policy policies/mab_task5_magnesium_v2.yaml \
        --out outputs/medomit_provenance/<run_id>

    # five-view output status for the same run
    python scripts/medomit_provenance.py status --run <run dir> --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from procsafe.output_status import describe
from procsafe.provenance import (MANIFEST_VERSION, RunManifest, build_episode_uid, build_run_id,
                                 deterministic_case_order, ensure_fresh_output_dir, evaluator_version,
                                 file_sha256, host_fingerprint, policy_fingerprints,
                                 prompt_fingerprint, seed_record, simulator_fingerprint)

PROMPT_VERSION = {"fewshot2": "v2_clinical_sequence", "fewshot3": "v3_format_only",
                  "fewshot4": "v4_decision_step", "base": "base", "fewshot": "v1_narrated"}


def open_runs(run_dir: Path):
    """Yield the harness records from runs.jsonl or runs.jsonl.gz."""
    for name, opener in (("runs.jsonl", open), ("runs.jsonl.gz", lambda p: gzip.open(p, "rt"))):
        p = run_dir / "medagentbench" / name
        if not p.exists():
            p = run_dir / name
        if p.exists():
            with opener(p) as f:
                for line in f:
                    yield json.loads(line)
            return
    raise SystemExit(f"no runs.jsonl[.gz] under {run_dir}")


def harness_statuses(run_dir: Path) -> dict:
    for name in ("medagentbench/overall.json", "overall.json"):
        p = run_dir / name
        if p.exists():
            raw = json.loads(p.read_text())["custom"]["raw_results"]
            return {r["index"]: r["status"] for r in raw}
    return {}


def infer_run_identity(run_dir: Path) -> dict:
    """Model, prompt and repeat as encoded in the directory path.

    These are INFERRED from the path, which is how the historical runs recorded them. A future run
    should pass them explicitly instead; the manifest records which source was used.
    """
    agent = run_dir.name
    prompt_dir = run_dir.parent.name
    model, _, rep = agent.partition("-ctx8k")
    repeat_text = rep.lstrip("-") or "t0"
    m = re.search(r"s(\d+)$", repeat_text)
    return {"model_name": model or agent,
            "prompt_version": PROMPT_VERSION.get(prompt_dir, prompt_dir),
            "repeat_label": repeat_text,
            "repeat": int(m.group(1)) if m else 0,
            "source": "inferred from the run directory path"}


def final_agent_message(rec: dict) -> str:
    msgs = [h["content"] for h in rec["output"]["history"][1:] if h["role"] == "agent"]
    return msgs[-1].strip() if msgs else ""


def strict_parser_action(message: str) -> str:
    text = message.strip()
    if text.startswith("FINISH(") and text.endswith(")"):
        return "FINISH"
    for verb in ("GET", "POST"):
        if text.startswith(verb):
            return verb
    return "INVALID"


def cmd_manifest(a) -> int:
    run_dir, out = Path(a.run), ensure_fresh_output_dir(a.out, a.force)
    ident = infer_run_identity(run_dir) if not a.model else {
        "model_name": a.model, "prompt_version": a.prompt_version or "unspecified",
        "repeat_label": str(a.repeat), "repeat": a.repeat, "source": "passed on the command line"}
    records = list(open_runs(run_dir))
    statuses = harness_statuses(run_dir)
    tasks = {}
    if a.mab:
        data = Path(a.mab) / "data/medagentbench/test_data_v2.json"
        if data.is_file():
            tasks = {i: t for i, t in enumerate(json.loads(data.read_text()))}

    date = a.date or (records[0].get("time", {}).get("str", "")[:10] or "unknown").replace("/", "-")
    run_id = a.run_id or build_run_id(date, ident["model_name"], ident["prompt_version"], ident["repeat"])
    experiment_id = a.experiment_id or f"exp__{run_id}"

    indices = deterministic_case_order([r["index"] for r in records])
    episodes = []
    for idx in indices:
        rec = next(r for r in records if r["index"] == idx)
        task = tasks.get(idx, {})
        task_id = task.get("id", f"index{idx}")
        raw = final_agent_message(rec)
        st = describe(raw, statuses.get(idx), strict_parser_action(raw),
                      episode_uid=build_episode_uid(run_id, task_id, idx),
                      task_id=task_id, case_index=idx)
        episodes.append({
            "episode_uid": st.episode_uid, "task_id": task_id, "case_index": idx,
            "patient_id": task.get("eval_MRN"),
            "repeat": ident["repeat"], "repeat_label": ident["repeat_label"],
            "requested_seed": None,
            "started_at": rec.get("time", {}).get("str"),
            "harness_status": st.harness_status, "official_grade": st.official_grade,
            "graded": st.graded, "strict_parser_action": st.strict_parser_action,
            "completion_status": st.completion_status,
            "parser_and_harness_agree": st.parser_and_harness_agree,
            "turns": sum(1 for h in rec["output"]["history"][1:] if h["role"] == "agent"),
        })

    mab_root = Path(a.mab) if a.mab else None
    manifest = RunManifest(
        experiment_id=experiment_id, run_id=run_id, manifest_version=MANIFEST_VERSION,
        started_at=min((e["started_at"] for e in episodes if e["started_at"]), default=None),
        ended_at=max((e["started_at"] for e in episodes if e["started_at"]), default=None),
        model={"name": ident["model_name"], "digest": a.model_digest,
               "quantization": a.quantization, "runtime": a.runtime,
               "num_ctx": a.num_ctx, "temperature": a.temperature,
               "identity_source": ident["source"]},
        prompt=prompt_fingerprint(Path(a.prompt_file).read_text() if a.prompt_file else None,
                                  ident["prompt_version"]),
        seeds=seed_record(experiment_id, [e["task_id"] for e in episodes], ident["repeat"],
                          a.runtime or "unknown", honoured=None),
        repeat=ident["repeat"],
        cases={"count": len(indices), "indices": indices,
               "task_types": sorted({e["task_id"].split("_")[0] for e in episodes})},
        policies=policy_fingerprints(a.policy or []),
        evaluator=evaluator_version("."),
        grader={"path": str(mab_root / "src/server/tasks/medagentbench/refsol.py") if mab_root else None,
                "sha256": file_sha256(mab_root / "src/server/tasks/medagentbench/refsol.py") if mab_root else None},
        benchmark={**({"repo": str(mab_root)} if mab_root else {}),
                   "test_data_sha256": file_sha256(mab_root / "data/medagentbench/test_data_v2.json") if mab_root else None,
                   "patch_sha256": file_sha256("medagentbench_setup/medagentbench.patch")},
        simulator=simulator_fingerprint(a.fhir_container, a.case_table),
        host=host_fingerprint(),
        artifacts={"run_dir": str(run_dir), "manifest_dir": str(out),
                   "runs_jsonl_sha256": file_sha256(run_dir / "medagentbench/runs.jsonl.gz")
                                        or file_sha256(run_dir / "medagentbench/runs.jsonl"),
                   "overall_json_sha256": file_sha256(run_dir / "medagentbench/overall.json")},
        episodes=episodes,
    )
    unavailable = {}
    if not a.model_digest:
        unavailable["model.digest"] = ("not recorded by the runner; recoverable only while the same "
                                      "model is still installed in the local runtime")
    if not a.quantization:
        unavailable["model.quantization"] = "not recorded by the runner"
    if not a.prompt_file:
        unavailable["prompt.sha256"] = ("the prompt was selected by the FEWSHOT environment variable "
                                        "and its text was not stored with the run")
    if ident["source"].startswith("inferred"):
        unavailable["model/prompt/repeat identity"] = ("inferred from the directory path, not recorded "
                                                       "in any artefact")
    unavailable["seeds.actual"] = ("the runner used one static seed per run, not per case; the "
                                   "per-case seeds listed here are what a future run should request")
    if not manifest.simulator.get("image_digest"):
        unavailable["simulator.image_digest"] = "docker unavailable or container not present"
    manifest.unavailable = unavailable

    body = json.loads(manifest.to_json())
    body["manifest_sha256"] = manifest.self_hash()
    (out / "run_manifest.json").write_text(json.dumps(body, indent=1) + "\n")
    print(json.dumps({"run_id": run_id, "episodes": len(episodes),
                      "graded": sum(e["graded"] for e in episodes),
                      "completion_status": {k: sum(e["completion_status"] == k for e in episodes)
                                            for k in sorted({e["completion_status"] for e in episodes})},
                      "unavailable_fields": sorted(unavailable),
                      "manifest": str(out / "run_manifest.json")}, indent=1))
    return 0


def cmd_status(a) -> int:
    run_dir, out = Path(a.run), ensure_fresh_output_dir(a.out, a.force)
    statuses = harness_statuses(run_dir)
    tasks = {}
    if a.mab:
        data = Path(a.mab) / "data/medagentbench/test_data_v2.json"
        if data.is_file():
            tasks = {i: t for i, t in enumerate(json.loads(data.read_text()))}
    ident = infer_run_identity(run_dir)
    run_id = a.run_id or build_run_id(a.date or "unknown", ident["model_name"],
                                      ident["prompt_version"], ident["repeat"])
    rows = []
    for rec in open_runs(run_dir):
        idx = rec["index"]
        task_id = tasks.get(idx, {}).get("id", f"index{idx}")
        raw = final_agent_message(rec)
        st = describe(raw, statuses.get(idx), strict_parser_action(raw),
                      episode_uid=build_episode_uid(run_id, task_id, idx), task_id=task_id,
                      case_index=idx)
        d = st.as_dict()
        d["raw_final_message"] = d["raw_final_message"][:400]
        rows.append(d)
    rows.sort(key=lambda r: r["case_index"])
    with open(out / "output_status.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"run_dir": str(run_dir), "episodes": len(rows),
               "completion_status": {k: sum(r["completion_status"] == k for r in rows)
                                     for k in sorted({r["completion_status"] for r in rows})},
               "official_grade": {str(k): sum(r["official_grade"] == k for r in rows)
                                  for k in sorted({str(r["official_grade"]) for r in rows})},
               "parser_and_harness_disagree": sum(not r["parser_and_harness_agree"] for r in rows)}
    (out / "output_status_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("manifest", cmd_manifest), ("status", cmd_status)):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--mab")
        p.add_argument("--force", action="store_true")
        p.add_argument("--run-id")
        p.add_argument("--date")
        p.set_defaults(func=fn)
    m = sub.choices["manifest"]
    m.add_argument("--experiment-id")
    m.add_argument("--policy", action="append")
    m.add_argument("--model")
    m.add_argument("--model-digest")
    m.add_argument("--quantization")
    m.add_argument("--runtime", default="ollama")
    m.add_argument("--num-ctx", type=int)
    m.add_argument("--temperature", type=float)
    m.add_argument("--prompt-version")
    m.add_argument("--prompt-file")
    m.add_argument("--repeat", type=int, default=0)
    m.add_argument("--fhir-container")
    m.add_argument("--case-table")
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
