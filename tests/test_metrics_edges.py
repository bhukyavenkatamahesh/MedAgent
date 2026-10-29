"""Metrics keep unknown outcomes separate and count each episode once."""
from dataclasses import replace
from pathlib import Path

import pytest

from procsafe.adapters.demo_json import load_demo
from procsafe.checker import SafetyChecker
from procsafe.metrics import aggregate
from procsafe.policy import Policy

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def results():
    policy = Policy.load(ROOT / "policies/demo_renal_v0.yaml")
    episodes, _ = load_demo(ROOT / "data/synthetic_fhir_demo_data.json", policy)
    return [SafetyChecker(policy).evaluate(ep) for ep in episodes]


def test_known_demo_metric_counts(results):
    metrics = aggregate(results)
    assert metrics["terminal_success_rate"]["num"] == 3
    assert metrics["terminal_success_rate"]["den"] == 4
    assert metrics["unsafe_success_rate"]["num"] == 1
    assert metrics["unsafe_success_rate"]["den"] == 3
    assert metrics["unsafe_action_rate"]["num"] == 2
    assert metrics["unsafe_action_rate"]["den"] == 3
    assert metrics["appropriate_defer_count"] == 1
    assert metrics["mean_required_prerequisite_recall"] == 0.8333
    assert metrics["input_provenance_counts"] == {"AUTHORED_TEST_INPUT": 4}


def test_unknown_outcome_is_not_a_terminal_failure(results):
    unknown = replace(results[0], episode_id="unknown", terminal_result=None, process_result=None)
    metrics = aggregate([results[0], unknown])
    assert metrics["terminal_success_rate"]["den"] == 1
    assert metrics["terminal_success_rate"]["value"] == 1
    assert metrics["unknown_terminal_count"] == 1
    assert metrics["unclassified_process_count"] == 1
    assert "SAFE_FAILURE" not in metrics["process_result_counts"]


def test_duplicate_episodes_are_rejected(results):
    with pytest.raises(ValueError, match="Duplicate episode"):
        aggregate([results[0], results[0]])


def test_zero_denominators_are_undefined():
    metrics = aggregate([])
    for name in ["terminal_success_rate", "safe_success_rate", "unsafe_success_rate",
                 "premature_action_rate", "unsafe_action_rate"]:
        assert metrics[name]["value"] is None
        assert metrics[name]["den"] == 0


def test_multiple_violations_count_once_per_successful_episode(results):
    multiple = replace(results[1], guarded_action_count=2, premature_action_count=2, unsafe_action_count=2)
    metrics = aggregate([multiple])
    assert metrics["unsafe_success_rate"]["num"] == metrics["unsafe_success_rate"]["den"] == 1
    assert metrics["unsafe_action_rate"]["num"] == metrics["unsafe_action_rate"]["den"] == 2
