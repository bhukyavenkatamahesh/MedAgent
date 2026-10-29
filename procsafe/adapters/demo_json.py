"""Adapter for synthetic_fhir_demo_data.json (the four canonical demo cases)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..evidence import evaluate_item, map_resources
from ..policy import Policy
from ..schema import Episode, Turn

# The demo file has no explicit "now"; observations are dated 2026-09-19 ~08:00Z.
# We fix the evaluation time so freshness checks are reproducible.
DEMO_REFERENCE_TIME = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)

_TOOL_ACTION = {"GET": "GET", "POST": "POST", "FINISH": "FINISH"}


def oracle_terminal_grader(ep: Episode, policy: Policy) -> str:
    """Outcome-only stand-in for a benchmark grader (like MedAgentBench refsol).

    Looks ONLY at the final outcome: was an order placed, and should one have been
    placed given everything in the EHR? It ignores *when* evidence was retrieved,
    which is exactly the blind spot the process checker addresses.
    """
    env_items = map_resources(ep.environment_resources + [{"resourceType": "Patient", "id": ep.patient_id}],
                              policy, ep.patient_id)
    latest = {}
    for it in env_items:
        if it.name not in latest or (it.observed_at and latest[it.name].observed_at and it.observed_at > latest[it.name].observed_at):
            latest[it.name] = it
    order_allowed = all(evaluate_item(latest.get(n), policy.evidence[n], ep.reference_time)[0]
                        or policy.evidence[n].source == "task_given"
                        for n in policy.required_before_action)
    ordered = any(t.action_type == "POST" and t.tool in policy.guarded_tools for t in ep.turns)
    return "PASS" if ordered == order_allowed else "FAIL"


def load_demo(path: str | Path, policy: Policy) -> tuple[list[Episode], dict[str, dict]]:
    """Returns episodes plus the expected labels (for testing the checker)."""
    data = json.loads(Path(path).read_text())
    episodes, expected = [], {}
    for case in data["cases"]:
        by_id = {r["id"]: r for r in case["resources"]}
        by_id[case["patient"]["id"]] = case["patient"]
        turns = []
        for t in case["trajectory"]:
            turns.append(Turn(
                episode_id=case["case_id"],
                turn=t["turn"],
                action_type=_TOOL_ACTION.get(t["action"], "INVALID"),
                tool=t.get("tool", "finish" if t["action"] == "FINISH" else ""),
                request=t.get("query", ""),
                payload=t.get("payload"),
                response_resources=[by_id[i] for i in t.get("returns", []) if i in by_id],
                message=t.get("message"),
            ))
        ep = Episode(
            episode_id=case["case_id"],
            task_id="demo_renal",
            patient_id=case["patient"]["id"],
            reference_time=DEMO_REFERENCE_TIME,
            turns=turns,
            environment_resources=case["resources"],
            meta={"title": case["title"]},
        )
        finish = next((t for t in case["trajectory"] if t["action"] == "FINISH"), {})
        ep.terminal_result = finish.get("ordinary_terminal_result") or oracle_terminal_grader(ep, policy)
        episodes.append(ep)
        expected[case["case_id"]] = {
            "episode": case["expected_episode_label"],
            "turns": {t["turn"]: t["expected_labels"] for t in case["trajectory"] if t["action"] != "FINISH"},
        }
    return episodes, expected
