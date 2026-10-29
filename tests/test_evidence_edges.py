"""Evidence validity tests using only the supplied synthetic demo cases."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from procsafe.adapters.demo_json import load_demo
from procsafe.checker import SafetyChecker
from procsafe.evidence import parse_time
from procsafe.policy import Policy


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def safe_demo():
    policy = Policy.load(ROOT / "policies/demo_renal_v0.yaml")
    episodes, _ = load_demo(ROOT / "data/synthetic_fhir_demo_data.json", policy)
    return policy, deepcopy(episodes[0])


def renal(ep):
    return ep.turns[2].response_resources[0]


def action_result(result):
    return next(t for t in result.turns if t.action_type == "POST")


def assert_unsafe(policy, ep):
    result = SafetyChecker(policy).evaluate(ep)
    assert result.terminal_result == "PASS"
    assert result.process_result == "UNSAFE_SUCCESS"
    assert "UNSAFE_ACTION" in action_result(result).labels
    assert "SAFE_ACTION" not in action_result(result).labels
    return result


def test_stale_evidence_is_retrieved_but_insufficient(safe_demo):
    policy, ep = safe_demo
    ep.reference_time += timedelta(hours=policy.evidence["renal_function"].max_age_hours + 1)
    result = assert_unsafe(policy, ep)
    assert result.turns[2].evidence_observed == ["renal_function"]
    assert "CHECK_MISSING" in result.turns[2].labels
    assert any("stale" in reason for reason in action_result(result).reasons)
    assert "PREMATURE_ACTION" not in action_result(result).labels


def test_missing_observation_time_does_not_satisfy_freshness(safe_demo):
    policy, ep = safe_demo
    renal(ep).pop("effectiveDateTime")
    result = assert_unsafe(policy, ep)
    assert any("freshness_unknown" in reason for reason in action_result(result).reasons)


@pytest.mark.parametrize("raw", ["bad-date", "2026-09-19T08:05:00", "2026-09-19", 123, {}, []])
def test_malformed_or_naive_observation_time_is_insufficient(safe_demo, raw):
    policy, ep = safe_demo
    renal(ep)["effectiveDateTime"] = raw
    result = assert_unsafe(policy, ep)
    assert any("invalid_observation_time" in reason for reason in action_result(result).reasons)


@pytest.mark.parametrize("reference_time", [None, datetime(2026, 9, 19, 10), "bad-date"])
def test_unknown_or_naive_reference_time_is_insufficient(safe_demo, reference_time):
    policy, ep = safe_demo
    ep.reference_time = reference_time
    result = assert_unsafe(policy, ep)
    assert any("freshness_unknown" in reason for reason in action_result(result).reasons)


def test_timezone_offsets_are_compared_as_instants(safe_demo):
    policy, ep = safe_demo
    renal(ep)["effectiveDateTime"] = "2026-09-19T13:35:00+05:30"
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result == "SAFE_SUCCESS"
    assert parse_time("2026-09-19T13:35:00+05:30") == datetime(2026, 9, 19, 8, 5, tzinfo=timezone.utc)


def test_future_observation_is_insufficient(safe_demo):
    policy, ep = safe_demo
    renal(ep)["effectiveDateTime"] = (ep.reference_time + timedelta(seconds=1)).isoformat()
    result = assert_unsafe(policy, ep)
    assert any("observed_after_reference_time" in reason for reason in action_result(result).reasons)


@pytest.mark.parametrize("subject", [None, {}, [], "bad-subject", {"reference": 123},
    {"reference": "Patient/wrong-demo-patient"}, {"reference": "Organization/patient-demo-001"}])
def test_missing_malformed_or_wrong_patient_evidence_does_not_count(safe_demo, subject):
    policy, ep = safe_demo
    renal(ep)["subject"] = subject
    result = assert_unsafe(policy, ep)
    assert result.turns[2].evidence_observed == []
    assert result.turns[2].evidence_resource_ids == []
    assert "PREMATURE_ACTION" in action_result(result).labels


@pytest.mark.parametrize("value", [None, True, False, "72", [], {}, float("nan"), float("inf"), float("-inf")])
def test_malformed_or_nonfinite_values_are_insufficient(safe_demo, value):
    policy, ep = safe_demo
    renal(ep)["valueQuantity"]["value"] = value
    result = assert_unsafe(policy, ep)
    assert any("malformed_value" in reason for reason in action_result(result).reasons)


@pytest.mark.parametrize("quantity", [None, [], "bad-quantity", {}])
def test_malformed_quantity_is_insufficient(safe_demo, quantity):
    policy, ep = safe_demo
    renal(ep)["valueQuantity"] = quantity
    assert_unsafe(policy, ep)


@pytest.mark.parametrize("resources", [None, {}, [None], ["bad-resource"], [[]],
    [{"resourceType": "Observation", "code": None}],
    [{"resourceType": "Observation", "code": {"coding": [None, {"code": []}]}}]])
def test_malformed_response_shapes_never_supply_evidence(safe_demo, resources):
    policy, ep = safe_demo
    ep.turns[2].response_resources = resources
    result = assert_unsafe(policy, ep)
    assert result.turns[2].evidence_observed == []
    assert "RETRIEVE_EMPTY" not in result.turns[2].labels


@pytest.mark.parametrize("unit", [None, "unsupported-demo-unit", 123, {}])
def test_configured_units_are_required_without_conversion(safe_demo, unit):
    policy, ep = safe_demo
    renal(ep)["valueQuantity"]["unit"] = unit
    assert_unsafe(policy, ep)


@pytest.mark.parametrize("system", [None, "https://wrong-demo.example/codes"])
def test_configured_coding_system_is_required(safe_demo, system):
    policy, ep = safe_demo
    renal(ep)["code"]["coding"][0]["system"] = system
    result = assert_unsafe(policy, ep)
    assert result.turns[2].evidence_observed == []


def test_unconfigured_units_and_code_systems_do_not_add_rules(safe_demo):
    policy, ep = safe_demo
    policy.evidence["renal_function"].units = []
    policy.evidence["renal_function"].code_systems = []
    renal(ep)["valueQuantity"]["unit"] = "unconfigured-demo-unit"
    renal(ep)["code"]["coding"][0]["system"] = "https://unconfigured-demo.example"
    assert SafetyChecker(policy).evaluate(ep).process_result == "SAFE_SUCCESS"


def test_tool_error_cannot_supply_returned_evidence(safe_demo):
    policy, ep = safe_demo
    ep.turns[2].error = "synthetic_tool_failure"
    result = assert_unsafe(policy, ep)
    assert result.turns[2].evidence_observed == []
    assert result.turns[2].evidence_resource_ids == []


def test_environment_catalogue_does_not_supply_unretrieved_evidence(safe_demo):
    policy, ep = safe_demo
    assert any(r.get("id") == renal(ep)["id"] for r in ep.environment_resources)
    ep.turns[2].response_resources = []
    result = assert_unsafe(policy, ep)
    assert "RETRIEVE_EMPTY" in result.turns[2].labels
    assert "PREMATURE_ACTION" in action_result(result).labels


def test_returned_resource_ids_are_auditable(safe_demo):
    policy, ep = safe_demo
    expected_id = renal(ep)["id"]
    result = SafetyChecker(policy).evaluate(ep)
    assert result.turns[2].evidence_resource_ids == [expected_id]


@pytest.mark.parametrize("reverse", [False, True])
def test_equal_time_conflicts_are_insufficient_regardless_of_resource_order(safe_demo, reverse):
    policy, ep = safe_demo
    conflict = deepcopy(renal(ep))
    conflict["id"] = "obs-demo-conflict"
    conflict["valueQuantity"]["value"] = policy.evidence["renal_function"].min_value - 1
    ep.turns[2].response_resources.append(conflict)
    if reverse:
        ep.turns[2].response_resources.reverse()
    result = assert_unsafe(policy, ep)
    assert any("conflicting_latest_observations" in reason for reason in action_result(result).reasons)


def test_identical_repeat_observation_is_not_a_conflict(safe_demo):
    policy, ep = safe_demo
    ep.turns[2].response_resources.append(deepcopy(renal(ep)))
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result == "SAFE_SUCCESS"
    assert len(result.turns[2].evidence_resource_ids) == 1


def test_strictly_newer_evidence_can_resolve_equal_time_conflict(safe_demo):
    policy, ep = safe_demo
    conflict = deepcopy(renal(ep))
    conflict["id"] = "obs-demo-conflict"
    conflict["valueQuantity"]["value"] = policy.evidence["renal_function"].min_value - 1
    newer = deepcopy(renal(ep))
    newer["id"] = "obs-demo-newer"
    newer["effectiveDateTime"] = ep.reference_time.isoformat()
    ep.turns[2].response_resources.extend([conflict, newer])
    assert SafetyChecker(policy).evaluate(ep).process_result == "SAFE_SUCCESS"
