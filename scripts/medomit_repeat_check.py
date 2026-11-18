"""Compare two runs of the same experiment and state which tier of reproducibility holds.

Three tiers, kept strictly apart, because conflating them is how reproducibility gets overclaimed:

  COMPLETE REPRODUCIBILITY   byte-identical trajectories from an independent re-execution, with
                             every pinned input identical AND the claim shown to survive a change of
                             host or runtime build. Not demonstrable from two runs on one machine.
  APPROXIMATE REPRODUCIBILITY  re-execution on the SAME host, runtime build and simulator state
                             reproduces the trajectories (byte-identical or label-identical). This
                             is the strongest claim a single machine can support.
  AUDITABLE RE-SCORING       the stored trajectories can be re-scored to the same labels by the
                             same evaluator. It needs no model and no simulator, and it is what the
                             660-episode comparison established.

    python scripts/medomit_repeat_check.py --a runs/X --b runs/Y --out outputs/repeat_check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PINNED = [("model digest", ("model", "digest")), ("prompt sha256", ("prompt", "sha256")),
          ("grader sha256", ("grader", "sha256")), ("run_id", ("run_id",)),
          ("benchmark test data", ("benchmark", "test_data_sha256")),
          ("evaluator source", ("evaluator", "source_sha256")),
          ("simulator image", ("simulator", "image_digest"))]


def dig(body: dict, path: tuple):
    cur = body
    for key in path:
        cur = (cur or {}).get(key) if isinstance(cur, dict) else None
    return cur


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    ma = json.loads((Path(args.a) / "run_manifest.json").read_text())
    mb = json.loads((Path(args.b) / "run_manifest.json").read_text())

    pinned = {}
    for label, path in PINNED:
        va, vb = dig(ma, path), dig(mb, path)
        pinned[label] = {"a": va, "b": vb, "identical": va == vb}
    state = {"before_identical": (dig(ma, ("simulator", "state_before", "fingerprint"))
                                  == dig(mb, ("simulator", "state_before", "fingerprint"))),
             "a_mutated": dig(ma, ("simulator", "state_mutated_by_run")),
             "b_mutated": dig(mb, ("simulator", "state_mutated_by_run"))}
    host = {"identical": ma.get("host") == mb.get("host"),
             "runtime_version_identical": (dig(ma, ("model", "runtime_version"))
                                           == dig(mb, ("model", "runtime_version")))}

    ea = {e["case_index"]: e for e in ma.get("episodes", [])}
    eb = {e["case_index"]: e for e in mb.get("episodes", [])}
    shared = sorted(set(ea) & set(eb))
    episodes = []
    for k in shared:
        x, y = ea[k], eb[k]
        episodes.append({
            "case_index": k, "task_id": x.get("task_id"),
            "seed_identical": x.get("requested_seed") == y.get("requested_seed"),
            "raw_identical": x.get("raw_final_message") == y.get("raw_final_message"),
            "grade_identical": x.get("official_grade") == y.get("official_grade"),
            "completion_identical": x.get("completion_status") == y.get("completion_status")})

    all_pinned = all(v["identical"] for v in pinned.values())
    all_raw = bool(episodes) and all(e["raw_identical"] for e in episodes)
    all_labels = bool(episodes) and all(e["grade_identical"] and e["completion_identical"]
                                        for e in episodes)
    same_machine = host["identical"] and host["runtime_version_identical"]

    if all_pinned and all_raw and state["before_identical"] and same_machine:
        tier = "approximate_reproducibility"
        why = ("re-execution on the same host, runtime build and simulator state reproduced every "
               "trajectory byte-identically. This is NOT complete reproducibility: no change of "
               "host or runtime build has been tested, and the first generation after a model load "
               "is a different deterministic regime (see outputs/seed_check/).")
    elif all_pinned and all_labels:
        tier = "approximate_reproducibility_labels_only"
        why = "the labels and grades reproduced, but the trajectories were not byte-identical"
    elif not shared:
        tier = "not_comparable"
        why = "the two runs share no episodes"
    else:
        tier = "not_reproduced"
        why = "a pinned input or an episode outcome differed; see the per-item detail"

    result = {"a": args.a, "b": args.b, "episodes_compared": len(shared),
              "pinned_inputs": pinned, "simulator_state": state, "host": host,
              "episodes": episodes, "tier": tier, "reason": why,
              "complete_reproducibility": False,
              "complete_reproducibility_note": ("Requires an independent re-execution on different "
                                                "hardware or a different runtime build. Never "
                                                "claimed from runs on one machine."),
              "auditable_rescoring": ("established separately: 660 historical episodes re-scored "
                                      "with zero label changes (scripts/medomit_rescore_diff.py)")}
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("pinned_inputs", "episodes")}, indent=1))
    for label, v in pinned.items():
        print(f"  pinned {label:22} identical={v['identical']}")
    for e in episodes:
        print(f"  case {e['case_index']} seed={e['seed_identical']} raw={e['raw_identical']} "
              f"grade={e['grade_identical']}")
    if args.out:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        (out / "repeat_check.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
