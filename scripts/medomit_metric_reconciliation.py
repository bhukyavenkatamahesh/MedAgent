"""Episode-by-episode reconciliation of the MedOmit headline metrics. Read-only analysis.

Answers two questions with evidence from the saved trajectories and scored outputs:

  A. UPR: why 42/107 (ungrounded decision) and 53/107 (no successful required retrieval) differ, with
     a per-episode table for every disagreeing episode.
  B. Completeness: what 80/480 and 86/480 each count, whether they overlap, and which episodes sit in
     the difference.

It writes nothing outside --out and changes no result.

    python scripts/medomit_metric_reconciliation.py --scored outputs/heldout_v1_audit \
        --runs runs/2026-11-16_slm-heldout_n20 --out outputs/medomit_reconciliation
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import json
import re
from collections import Counter
from pathlib import Path

PROMPT = {"fewshot2": "v2-clinical-sequence", "fewshot3": "v3-format-only", "fewshot4": "v4-decision-step"}


def load_scored(scored: Path) -> list[dict]:
    out = []
    for f in sorted(scored.glob("*/*_task*/episodes.jsonl")):
        prompt, leaf = f.parts[-3], f.parts[-2]
        agent, task = leaf.rsplit("_", 1)
        model, _, rep = agent.partition("-ctx8k")
        for line in f.read_text().splitlines():
            e = json.loads(line)
            e["_prompt"], e["_model"], e["_repeat"], e["_task"] = prompt, model, rep.lstrip("-") or "t0", task
            e["_agent"] = agent
            out.append(e)
    return out


def load_raw(runs: Path) -> dict:
    """(prompt, agent, case_index) -> the agent's messages and the environment's replies."""
    raw = {}
    for f in runs.glob("*/*/medagentbench/runs.jsonl.gz"):
        prompt, agent = f.parts[-4], f.parts[-3]
        for line in gzip.open(f, "rt"):
            rec = json.loads(line)
            raw[(prompt, agent, rec["index"])] = rec
    return raw


def gets_and_replies(rec: dict) -> list[tuple[str, str]]:
    """(agent message, next environment reply) pairs, trimmed."""
    hist = rec["output"]["history"][1:]
    pairs = []
    for i, h in enumerate(hist):
        if h["role"] != "agent":
            continue
        reply = hist[i + 1]["content"] if i + 1 < len(hist) and hist[i + 1]["role"] == "user" else ""
        pairs.append((h["content"].strip(), reply.strip()))
    return pairs


def summarise_reply(reply: str) -> str:
    if not reply:
        return "(no reply: last turn)"
    if "Error in sending" in reply:
        return "ERROR: " + reply.split("Error in sending the GET request:")[-1].strip()[:90]
    if "response from the GET request" not in reply:
        return reply[:90]
    body = reply.split("response from the GET request:", 1)[1]
    m = re.search(r"\{.*", body, re.S)
    if not m:
        return "(unparsable body)"
    try:
        bundle = json.loads(m.group()[:m.group().rfind("}") + 1])
    except Exception:
        return "(unparsable body)"
    entries = bundle.get("entry") or []
    if not entries:
        return f"empty bundle (total={bundle.get('total')})"
    vals = []
    for e in entries[:4]:
        r = e.get("resource", {})
        code = (r.get("code", {}).get("coding") or [{}])[0].get("code")
        q = r.get("valueQuantity") or {}
        vals.append(f"{code}={q.get('value')}{q.get('unit','')}@{(r.get('effectiveDateTime') or '')[:16]}")
    return f"{len(entries)} resource(s): " + "; ".join(vals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    eps = load_scored(Path(a.scored))
    raw = load_raw(Path(a.runs))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---------- A. UPR definitions ----------
    def u2(e):   # decision ungrounded: no usable required evidence at the decision
        return e["action_requirement_status"] == "UNDETERMINED"

    def u3(e):   # no successful required retrieval anywhere in the episode
        return not any("RETRIEVE_REQUIRED" in t["labels"] for t in e["turns"])

    def u1(e):   # a constraint fired (today: a guarded write judged unsafe, or an unexpected write)
        return e["unsafe_action_count"] > 0 or e["unexpected_write_count"] > 0

    passes = [e for e in eps if e["terminal_result"] == "PASS"]
    rows = []
    for e in passes:
        if u2(e) == u3(e):
            continue
        idx = int(e["episode_id"].split("#")[1])
        rec = raw.get((e["_prompt"], e["_agent"], idx))
        pairs = gets_and_replies(rec) if rec else []
        retrieved_turns = [t["turn"] for t in e["turns"] if "RETRIEVE_REQUIRED" in t["labels"]]
        decision_turn = next((t["turn"] for t in e["turns"] if t["action_type"] == "FINISH"), None)
        audit = (e["action_audit"] or [{}])[0]
        rows.append({
            "episode_id": e["episode_id"], "task": e["_task"], "case_id": e["task_id"],
            "model": e["_model"], "prompt": PROMPT.get(e["_prompt"], e["_prompt"]), "repeat": e["_repeat"],
            "evidence_requested": " | ".join(m[:120] for m, _ in pairs if m.upper().startswith("GET")) or "(none)",
            "evidence_returned": " | ".join(summarise_reply(r) for m, r in pairs if m.upper().startswith("GET")) or "(none)",
            "required_evidence_retrieved_at_turns": ",".join(map(str, retrieved_turns)) or "never",
            "decision_turn": decision_turn,
            "evidence_usable_at_decision": "no" if u2(e) else "yes",
            "action_requirement_status": e["action_requirement_status"],
            "action_requirement_reason": audit.get("reason", ""),
            "process_result": e["process_result"], "grounding_result": e["grounding_result"],
            "counted_by_U2_ungrounded_decision": u2(e), "counted_by_U3_no_retrieval": u3(e),
            "why_they_differ": ("retrieved the required item, but it was not usable at the decision "
                                "(stale, wrong unit, conflicting, or retrieved after the decision)"
                                if u3(e) is False and u2(e) is True else
                                "no required retrieval succeeded, yet the requirement was decidable "
                                "(a faithful empty search settled it)"),
        })
    with open(out / "upr_disagreements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["episode_id"])
        w.writeheader()
        w.writerows(rows)

    summary = {
        "episodes": len(eps), "terminal_pass": len(passes),
        "U1_constraint_fired": sum(u1(e) for e in passes),
        "U2_ungrounded_decision": sum(u2(e) for e in passes),
        "U3_no_required_retrieval": sum(u3(e) for e in passes),
        "U2_and_U3": sum(u2(e) and u3(e) for e in passes),
        "U3_only": sum(u3(e) and not u2(e) for e in passes),
        "U2_only": sum(u2(e) and not u3(e) for e in passes),
        "disagreements": len(rows),
    }

    # ---------- B. completeness / invalid ----------
    harness = Counter()
    for f in sorted(glob.glob(f"{a.runs}/*/*/medagentbench/overall.json")):
        harness.update(r["status"] for r in json.load(open(f))["custom"]["raw_results"])
    incomplete = [e for e in eps if not e["complete_trace"]]
    ungraded = [e for e in eps if e["terminal_result"] is None]
    graded_but_incomplete = [e for e in incomplete if e["terminal_result"] is not None]
    rows_b = [{
        "episode_id": e["episode_id"], "task": e["_task"], "model": e["_model"],
        "prompt": PROMPT.get(e["_prompt"], e["_prompt"]), "repeat": e["_repeat"],
        "terminal_result": e["terminal_result"],
        "last_turn_action": e["turns"][-1]["action_type"] if e["turns"] else "(no turns)",
        "last_turn_labels": "|".join(e["turns"][-1]["labels"]) if e["turns"] else "",
        "turns": len(e["turns"]),
        "evaluation_notes": " | ".join(e["evaluation_notes"]),
    } for e in graded_but_incomplete]
    with open(out / "completeness_difference.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_b[0]) if rows_b else ["episode_id"])
        w.writeheader()
        w.writerows(rows_b)

    summary["completeness"] = {
        "harness_status_counts": dict(harness),
        "harness_agent_invalid_action": harness.get("agent invalid action", 0),
        "ungraded_terminal_result_null": len(ungraded),
        "incomplete_trace_no_FINISH": len(incomplete),
        "graded_but_incomplete": len(graded_but_incomplete),
        "ungraded_is_subset_of_incomplete": set(e["episode_id"] for e in ungraded) <= set(e["episode_id"] for e in incomplete),
    }
    (out / "reconciliation_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
