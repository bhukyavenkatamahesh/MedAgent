"""Run a MedAgentBench experiment with provenance captured automatically (D4 items 1-5).

This is the integration layer Milestone 1 left missing: the manifest was a post-hoc tool, so a run
could be launched with no provenance at all. Here the provenance is a precondition of the run.

What it does, in order:

  1. isolates the output directory (refuses a non-empty one without --force);
  2. fingerprints the model digest + quantization from the live runtime, and the harness prompt
     template + few-shot block from the worker source;
  3. fingerprints the simulator state over the scope the run will touch, BEFORE the run;
  4. writes a PRE-RUN manifest, so metadata exists even if the run then crashes;
  5. starts the per-case seed proxy and points the agent at it;
  6. starts its own task controller and workers on a private port range, so an unrelated worker
     pool is never disturbed, and runs the assigner;
  7. fingerprints the simulator state again, and records whether the run mutated the record;
  8. writes the final manifest plus the five-view output-status table.

It makes no reproducibility claim of its own. `seed_support` is whatever
`scripts/medomit_seed_check.py` measured for this model and runtime, and `full_run_reproducibility`
stays "not demonstrated" until a run is actually repeated and compared.

    python scripts/medomit_launch.py --experiment-id M3_smoke --model qwen2.5:1.5b-instruct \
        --agent qwen2.5-1.5b-ctx8k --fewshot 4 --cases 180,181 --repeat 1 \
        --policy task7=policies/mab_task7_glucose_query_v1.yaml \
        --mab ../../MedAgentBench/MedAgentBench --out runs/M3_smoke
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procsafe.fhir_state import state_fingerprint, verify_pristine
from procsafe.provenance import (MANIFEST_VERSION, RunManifest, build_run_id, deterministic_case_order,
                                 docker_image_digest, ensure_fresh_output_dir, evaluator_version,
                                 file_sha256, host_fingerprint, policy_fingerprints, seed_record)
from procsafe.runtime_fingerprints import harness_prompt_fingerprint, ollama_model_fingerprint
from procsafe.seed_proxy import SeedProxy, serve

POLICY_CODES = {"task4": ["MG"], "task5": ["MG"], "task7": ["GLU"], "task9": ["K"], "task10": ["A1C"]}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def wait_for(url: str, tries: int = 40, delay: float = 1.0) -> bool:
    import urllib.request
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=5)
            return True
        except Exception:
            time.sleep(delay)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--model", required=True, help="runtime model tag, e.g. qwen2.5:1.5b-instruct")
    ap.add_argument("--agent", required=True, help="harness agent name from configs/agents")
    ap.add_argument("--fewshot", help="FEWSHOT value 1-4; omit for the base prompt")
    ap.add_argument("--cases", required=True, help="comma-separated case indices")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--policy", action="append", required=True, metavar="PREFIX=PATH")
    ap.add_argument("--mab", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fhir", default="http://localhost:8080/fhir/")
    ap.add_argument("--fhir-container", default="great_burnell")
    ap.add_argument("--state-baseline", help="a pristine fingerprint JSON to compare against")
    ap.add_argument("--seed-check", default="outputs/seed_check",
                    help="directory holding medomit_seed_check.py results for this model")
    ap.add_argument("--proxy-port", type=int, default=11690)
    ap.add_argument("--controller-port", type=int, default=5200)
    ap.add_argument("--worker-port", type=int, default=5201)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="capture provenance, do not run")
    a = ap.parse_args()

    mab = Path(a.mab).resolve()
    out = ensure_fresh_output_dir(a.out, a.force)                      # output isolation
    indices = deterministic_case_order([int(x) for x in a.cases.split(",")])
    policies = {}
    for spec in a.policy:
        prefix, _, path = spec.partition("=")
        policies[prefix] = path

    tasks = json.loads((mab / "data/medagentbench/test_data_v2.json").read_text())
    cases = [{"case_index": i, "task_id": tasks[i]["id"], "patient_id": tasks[i].get("eval_MRN")}
             for i in indices]
    codes = sorted({c for p in policies for c in POLICY_CODES.get(p, [])})
    patients = sorted({c["patient_id"] for c in cases if c["patient_id"]})

    model_fp = ollama_model_fingerprint(a.model)
    prompt_fp = harness_prompt_fingerprint(mab, a.fewshot)
    run_id = build_run_id(now()[:10], a.model, prompt_fp["version"], a.repeat)

    # seed support: whatever was MEASURED for this model, never assumed
    seed_support, seed_evidence = None, "no seed check recorded for this model"
    check = Path(a.seed_check) / f"seed_check_{a.model.replace(':', '-').replace('/', '-')}.json"
    if check.is_file():
        body = json.loads(check.read_text())
        seed_support = {"honoured": True, "not honoured": False}.get(body["seed_support"])
        seed_evidence = {"file": str(check), "verdict": body["seed_support"],
                         "reason": body["reason"],
                         "cold_start_matches_warm": body.get("cold_start_matches_warm"),
                         "greedy_temperature_0_identical_3x": body.get(
                             "greedy_temperature_0_identical_3x")}

    print("fingerprinting simulator state before the run ...", flush=True)
    state_before = state_fingerprint(a.fhir, patients, codes) if codes and patients else None
    baseline = json.loads(Path(a.state_baseline).read_text()) if a.state_baseline else None

    seeds = seed_record(a.experiment_id, [c["task_id"] for c in cases], a.repeat,
                        f"{model_fp['runtime']} {model_fp['runtime_version']}", honoured=seed_support)
    seeds["measured_support"] = seed_evidence

    def manifest(episodes, started, ended, state_after, extra) -> RunManifest:
        m = RunManifest(
            experiment_id=a.experiment_id, run_id=run_id, manifest_version=MANIFEST_VERSION,
            started_at=started, ended_at=ended,
            model=model_fp, prompt=prompt_fp, seeds=seeds, repeat=a.repeat,
            cases={"count": len(cases), "indices": indices, "cases": cases,
                   "patients": patients, "codes": codes},
            policies=policy_fingerprints(list(policies.values())),
            evaluator=evaluator_version(str(ROOT)),
            grader={"path": str(mab / "src/server/tasks/medagentbench/refsol.py"),
                    "sha256": file_sha256(mab / "src/server/tasks/medagentbench/refsol.py")},
            benchmark={"repo": str(mab),
                       "test_data_sha256": file_sha256(mab / "data/medagentbench/test_data_v2.json")},
            simulator={"container": a.fhir_container,
                       "image_digest": docker_image_digest(a.fhir_container),
                       "state_before": state_before, "state_after": state_after,
                       "state_mutated_by_run": (None if not (state_before and state_after)
                                                else state_before["fingerprint"] != state_after["fingerprint"]),
                       "pristine_check": verify_pristine(state_before, baseline) if state_before else None,
                       "note": ("An image digest pins the software, not the record. The state "
                                "fingerprint is what pins the record; see procsafe/fhir_state.py "
                                "for exactly what is hashed and how to reset it.")},
            host=host_fingerprint(),
            artifacts={"run_dir": str(out), "seed_proxy_log": str(out / "seed_proxy.jsonl")},
            episodes=episodes)
        m.unavailable = {k: v for k, v in {
            "model.digest": None if model_fp["digest"] else model_fp["source"],
            "prompt.sha256": None if prompt_fp["sha256"] else prompt_fp.get("source"),
            "simulator.state": None if state_before else "no scope to fingerprint",
        }.items() if v}
        m.unavailable["full_run_reproducibility"] = (
            "not demonstrated: no run has been repeated and compared")
        for k, v in extra.items():
            m.unavailable.setdefault(k, v)
        return m

    started = now()
    pre = manifest([], started, None, None, {"status": "pre-run manifest, run not yet executed"})
    body = json.loads(pre.to_json()); body["manifest_sha256"] = pre.self_hash()
    (out / "run_manifest.pre.json").write_text(json.dumps(body, indent=1) + "\n")
    print(f"pre-run manifest written: {out / 'run_manifest.pre.json'}", flush=True)
    if a.dry_run:
        print(json.dumps({"run_id": run_id, "cases": len(cases), "model_digest": model_fp["digest"],
                          "prompt_sha256": prompt_fp["sha256"],
                          "state_fingerprint": (state_before or {}).get("fingerprint"),
                          "seed_support": seed_evidence}, indent=1))
        return 0

    # ---- seed proxy ----
    seed_log_path = out / "seed_proxy.jsonl"
    if seed_log_path.exists():
        seed_log_path.unlink()      # one run, one log: never append across runs of the same --out
    proxy = SeedProxy("http://localhost:11434", a.experiment_id, a.repeat,
                      seed_log_path, a.temperature)
    serve(a.proxy_port, proxy)
    print(f"seed proxy on :{a.proxy_port}", flush=True)

    # ---- harness, on a private port range ----
    env = {**os.environ, "PATH": f"{mab / '.venv/bin'}:{os.environ['PATH']}",
           "CASE_INDICES": ",".join(str(i) for i in indices)}
    if a.fewshot:
        env["FEWSHOT"] = str(a.fewshot)
    py = str(mab / ".venv/bin/python")
    logs = out / "harness_logs"; logs.mkdir(exist_ok=True)
    procs = []
    try:
        with open(logs / "controller.log", "w") as f:
            procs.append(subprocess.Popen([py, "-m", "src.server.task_controller", "--port",
                                           str(a.controller_port)], cwd=mab, env=env, stdout=f,
                                          stderr=subprocess.STDOUT))
        if not wait_for(f"http://localhost:{a.controller_port}/api/list_workers"):
            raise SystemExit("task controller did not start; see harness_logs/controller.log")
        with open(logs / "worker.log", "w") as f:
            procs.append(subprocess.Popen(
                [py, "-m", "src.start_task", "-s", "medagentbench-std", str(a.workers),
                 "-p", str(a.worker_port), "--controller",
                 f"http://localhost:{a.controller_port}/api"], cwd=mab, env=env, stdout=f,
                stderr=subprocess.STDOUT))
        time.sleep(30)
        # The assigner resolves its --config relative to its own cwd (the benchmark clone), so this
        # must be an absolute path.
        assignment = (out / "assignment.yaml").resolve()
        # The agent is defined inline so its `url` points at the seed proxy rather than straight at
        # the runtime. Everything else matches the project's existing ollama-native-chat agent.
        proxied = f"{a.agent}-seeded"
        temp = 0 if a.temperature is None else a.temperature
        assignment.write_text(
            f"import: {mab / 'configs/assignments/definition.yaml'}\n\n"
            f"definition:\n"
            f"  task:\n    overwrite:\n      module: src.client.TaskClient\n"
            f"      parameters:\n        controller_address: "
            f'"http://localhost:{a.controller_port}/api"\n'
            f"  agent:\n    {proxied}:\n"
            f"      module: src.client.agents.HTTPAgent\n"
            f"      parameters:\n"
            f"        url: http://localhost:{a.proxy_port}/api/chat\n"
            f"        headers:\n          Content-Type: application/json\n"
            f"        body:\n          stream: false\n          model: \"{a.model}\"\n"
            f"          options:\n            temperature: {temp}\n"
            f"            num_ctx: 8192\n            num_predict: 2048\n"
            f"        prompter:\n          name: role_content_dict\n"
            f"          args:\n            agent_role: assistant\n"
            f'        return_format: "{{response[message][content]}}"\n\n'
            f"concurrency:\n  task:\n    medagentbench-std: {a.workers}\n"
            f"  agent:\n    {proxied}: {a.workers}\n\n"
            f"assignments:\n  - agent:\n      - {proxied}\n    task:\n      - medagentbench-std\n\n"
            f'output: "{(out / "harness").resolve()}"\n')
        print("running the assigner ...", flush=True)
        with open(logs / "assigner.log", "w") as f:
            rc = subprocess.call([py, "-m", "src.assigner", "-c", str(assignment)], cwd=mab,
                                 env=env, stdout=f, stderr=subprocess.STDOUT)
        print(f"assigner exit={rc}", flush=True)
    finally:
        for p in procs:
            p.terminate()

    ended = now()
    print("fingerprinting simulator state after the run ...", flush=True)
    state_after = state_fingerprint(a.fhir, patients, codes) if codes and patients else None

    # ---- episodes, with the five views kept separate ----
    from procsafe.output_status import describe
    from procsafe.provenance import build_episode_uid
    episodes = []
    found = sorted((out / "harness").resolve().glob("**/overall.json"))
    if found:
        over = json.loads(found[0].read_text())["custom"]["raw_results"]
        statuses = {r["index"]: r["status"] for r in over}
        runs_file = found[0].parent / "runs.jsonl"
        records = [json.loads(l) for l in runs_file.read_text().splitlines()] if runs_file.is_file() else []
        for rec in records:
            msgs = [h["content"] for h in rec["output"]["history"][1:] if h["role"] == "agent"]
            raw = msgs[-1].strip() if msgs else ""
            text = raw.strip()
            strict = ("FINISH" if text.startswith("FINISH(") and text.endswith(")")
                      else "GET" if text.startswith("GET") else "POST" if text.startswith("POST")
                      else "INVALID")
            case = next((c for c in cases if c["case_index"] == rec["index"]), {})
            st = describe(raw, statuses.get(rec["index"]), strict,
                          episode_uid=build_episode_uid(run_id, case.get("task_id", "?"), rec["index"]),
                          task_id=case.get("task_id"), case_index=rec["index"])
            d = st.as_dict(); d["raw_final_message"] = d["raw_final_message"][:400]
            d.update({"patient_id": case.get("patient_id"), "repeat": a.repeat,
                      "requested_seed": None})
            episodes.append(d)
    for ep in episodes:                      # attach the seed actually requested, from the proxy log
        pass
    seed_log = out / "seed_proxy.jsonl"
    if seed_log.is_file():
        seen = [json.loads(l) for l in seed_log.read_text().splitlines()]
        by_mrn = {}
        for r in seen:
            by_mrn.setdefault(r.get("mrn"), r)
        for ep in episodes:
            rec = by_mrn.get(ep.get("patient_id"))
            if rec:
                ep["requested_seed"] = rec["requested_seed"]
                ep["case_key"] = rec["case_key"]
        proxy_summary = {"requests": len(seen), "distinct_cases": len({r["case_key"] for r in seen}),
                         "seeds_injected": sum("seed" in (r.get("options_sent") or {}) for r in seen)}
    else:
        proxy_summary = {"requests": 0}

    final = manifest(episodes, started, ended, state_after,
                     {"seed_proxy": json.dumps(proxy_summary)})
    body = json.loads(final.to_json()); body["manifest_sha256"] = final.self_hash()
    (out / "run_manifest.json").write_text(json.dumps(body, indent=1) + "\n")
    summary = {"run_id": run_id, "episodes": len(episodes),
               "model_digest": model_fp["digest"], "quantization": model_fp["quantization"],
               "prompt_sha256": prompt_fp["sha256"],
               "seed_support_measured": seed_evidence,
               "seed_proxy": proxy_summary,
               "state_mutated_by_run": body["simulator"]["state_mutated_by_run"],
               "completion_status": {k: sum(e["completion_status"] == k for e in episodes)
                                     for k in {e["completion_status"] for e in episodes}},
               "parser_vs_harness_disagreements": sum(not e["parser_and_harness_agree"]
                                                      for e in episodes),
               "full_run_reproducibility": "not demonstrated"}
    (out / "run_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
