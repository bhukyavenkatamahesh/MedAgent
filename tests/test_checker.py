from pathlib import Path

import pytest

from procsafe.adapters.demo_json import load_demo
from procsafe.adapters.medagentbench import load_runs, tool_name
from procsafe.checker import SafetyChecker
from procsafe.metrics import aggregate
from procsafe.policy import Policy

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demo():
    policy = Policy.load(ROOT / "policies/demo_renal_v0.yaml")
    episodes, expected = load_demo(ROOT / "data/synthetic_fhir_demo_data.json", policy)
    results = {ep.episode_id: SafetyChecker(policy).evaluate(ep) for ep in episodes}
    return results, expected


def test_episode_labels_match_expected(demo):
    results, expected = demo
    for case_id, exp in expected.items():
        assert results[case_id].process_result == exp["episode"], case_id


def test_turn_labels_match_expected(demo):
    results, expected = demo
    for case_id, exp in expected.items():
        got = {t.turn: t.labels for t in results[case_id].turns}
        for turn, labels in exp["turns"].items():
            assert sorted(got[turn]) == sorted(labels), (case_id, turn, got[turn], labels)


def test_later_get_does_not_justify_earlier_post(demo):
    r = demo[0]["case_unsafe_success"]
    assert r.terminal_result == "PASS" and r.process_result == "UNSAFE_SUCCESS"
    assert r.prerequisites_before_action is False


def test_unsafe_success_rate_denominator(demo):
    m = aggregate(list(demo[0].values()))
    assert m["unsafe_success_rate"]["den"] == m["terminal_success_rate"]["num"]


def test_medagentbench_parser_and_task9_policy():
    policy = Policy.load(ROOT / "policies/mab_task9_potassium_v0.yaml")
    eps = load_runs(ROOT / "tests/fixtures/mab_runs_synthetic.jsonl",
                    ROOT / "tests/fixtures/mab_tasks_synthetic.json",
                    terminal_results={0: "PASS", 1: "PASS"}, task_prefixes=("task9",))
    assert [len(e.turns) for e in eps] == [3, 3]
    assert eps[0].turns[0].tool == "lab.search" and eps[0].turns[1].tool == "medicationrequest.create"
    res = [SafetyChecker(policy).evaluate(e) for e in eps]
    assert res[0].process_result == "SAFE_SUCCESS"
    assert res[1].process_result == "UNSAFE_SUCCESS"      # ordered before checking potassium


def test_tool_names():
    assert tool_name("GET", "http://x/fhir/Observation?patient=1&category=vital-signs") == "vital.search"
    assert tool_name("POST", "http://x/fhir/ServiceRequest") == "servicerequest.create"
