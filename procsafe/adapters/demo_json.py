"""Load synthetic cases and explicit authored inputs without grading outcomes.

The catalogue only resolves resource IDs recorded in GET responses. Expected
labels are returned separately for tests and never passed to the checker.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..evidence import parse_time
from ..policy import Policy
from ..schema import Episode, Turn

_TOOL_ACTION = {"GET": "GET", "POST": "POST", "FINISH": "FINISH"}


def load_demo(path: str | Path, policy: Policy,
              supplemental_path: str | Path | None = None) -> tuple[list[Episode], dict[str, dict]]:
    """Return normalized episodes and independent test expectations.

    ``policy`` is retained for compatibility with starter callers; the adapter
    does not use safety predicates to manufacture terminal results. Missing or
    conflicting metadata raises an error instead of using a simulated grader.
    """
    path = Path(path)
    supplement_path = Path(supplemental_path) if supplemental_path else path.with_name("demo_supplemental.json")
    data = json.loads(path.read_text())
    supplement = json.loads(supplement_path.read_text())
    if supplement.get("schema_version") != "1.0" or supplement.get("provenance") != "AUTHORED_TEST_INPUT":
        raise ValueError("Supplement must declare schema_version 1.0 and AUTHORED_TEST_INPUT provenance")
    reference_time = parse_time(supplement.get("reference_time"))
    if reference_time is None or reference_time.utcoffset() is None:
        raise ValueError("Supplement reference_time must be an explicit timezone-aware timestamp")
    case_inputs = supplement.get("cases", {})
    if not isinstance(case_inputs, dict):
        raise ValueError("Supplement cases must be an object keyed by case ID")
    case_ids = [case["case_id"] for case in data["cases"]]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Duplicate case_id in demo input")
    if set(case_inputs) != set(case_ids):
        raise ValueError("Supplement must contain exactly the original demo case IDs")
    episodes, expected = [], {}
    for case in data["cases"]:
        case_id = case["case_id"]
        authored = case_inputs[case_id]
        if not isinstance(authored, dict):
            raise ValueError(f"{case_id}: authored case metadata must be an object")
        terminal = authored.get("terminal_result")
        if terminal not in ("PASS", "FAIL"):
            raise ValueError(f"{case_id}: explicit authored terminal_result PASS/FAIL is required")
        recorded = [t["ordinary_terminal_result"] for t in case["trajectory"] if "ordinary_terminal_result" in t]
        if any(result != terminal for result in recorded):
            raise ValueError(f"{case_id}: authored terminal_result conflicts with original fixture")
        by_id = {}
        for resource in [case["patient"], *case["resources"]]:
            rid = resource["id"]
            if rid in by_id:
                raise ValueError(f"{case_id}: duplicate resource ID {rid}")
            by_id[rid] = resource
        turns = []
        for t in case["trajectory"]:
            returned = t.get("returns", [])
            if not isinstance(returned, list) or any(not isinstance(rid, str) for rid in returned):
                raise ValueError(f"{case_id} turn {t['turn']}: returns must be a list of resource IDs")
            if len(set(returned)) != len(returned):
                raise ValueError(f"{case_id} turn {t['turn']}: duplicate returned resource ID")
            if any(rid not in by_id for rid in returned):
                raise ValueError(f"{case_id} turn {t['turn']}: unknown returned resource ID")
            turns.append(Turn(
                episode_id=case_id,
                turn=t["turn"],
                action_type=_TOOL_ACTION.get(t["action"], "INVALID"),
                tool=t.get("tool", "finish" if t["action"] == "FINISH" else ""),
                request=t.get("query", ""),
                payload=t.get("payload"),
                response_resources=[by_id[rid] for rid in returned],
                error=t.get("error"),
                message=t.get("message"),
            ))
        episodes.append(Episode(
            episode_id=case_id,
            task_id="demo_renal",
            patient_id=case["patient"]["id"],
            reference_time=reference_time,
            turns=turns,
            terminal_result=terminal,
            environment_resources=case["resources"],
            meta={"title": case["title"], "input_provenance": {
                "kind": "AUTHORED_TEST_INPUT",
                "fixture": supplement_path.name,
                "schema_version": supplement["schema_version"],
                "reference_time": reference_time.isoformat(),
                "terminal_result_source": "authored supplemental fixture (not observed results)",
            }},
        ))
        turn_expectations = {t["turn"]: list(t["expected_labels"]) for t in case["trajectory"]
                             if t["action"] != "FINISH"}
        for turn, labels in authored.get("expected_turn_labels", {}).items():
            if int(turn) not in turn_expectations:
                raise ValueError(f"{case_id}: expectation override names unknown non-FINISH turn {turn}")
            turn_expectations[int(turn)] = list(labels)
        expected[case_id] = {
            "episode": case["expected_episode_label"],
            "turns": turn_expectations,
        }
    return episodes, expected
