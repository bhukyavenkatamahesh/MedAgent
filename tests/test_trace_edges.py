"""Trace integrity and outcome separation for synthetic episodes."""
from copy import deepcopy
from pathlib import Path

import pytest

from procsafe.adapters.demo_json import load_demo
from procsafe.checker import SafetyChecker
from procsafe.policy import Policy
from procsafe.schema import Turn


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def demo():
    policy = Policy.load(ROOT / "policies/demo_renal_v0.yaml")
    episodes, _ = load_demo(ROOT / "data/synthetic_fhir_demo_data.json", policy)
    return policy, {ep.episode_id: deepcopy(ep) for ep in episodes}


@pytest.mark.parametrize("bad_turn", [1, 0, -1, True, "2", 2.0])
def test_duplicate_nonincreasing_or_invalid_turn_numbers_are_rejected(demo, bad_turn):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns[1].turn = bad_turn
    with pytest.raises(ValueError, match="strictly increasing"):
        SafetyChecker(policy).evaluate(ep)


def test_out_of_order_trace_is_rejected_without_sorting(demo):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns[1], ep.turns[2] = ep.turns[2], ep.turns[1]
    with pytest.raises(ValueError, match="strictly increasing"):
        SafetyChecker(policy).evaluate(ep)
    assert [t.turn for t in ep.turns] == [1, 3, 2, 4, 5]


@pytest.mark.parametrize("payload", [None, [], "bad-payload", {}, {"subject": None},
    {"subject": []}, {"subject": {"reference": "Patient/wrong-demo-patient"}},
    {"subject": {"reference": "Organization/patient-demo-001"}}])
def test_missing_malformed_or_wrong_order_subject_is_unsafe(demo, payload):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns[3].payload = payload
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result == "UNSAFE_SUCCESS"
    assert result.guarded_action_count == 1
    assert result.turns[3].labels == ["UNSAFE_ACTION"]


def test_errored_guarded_post_is_an_unsafe_attempt(demo):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns[3].error = "invalid_post_payload"
    result = SafetyChecker(policy).evaluate(ep)
    assert result.guarded_action_count == result.unsafe_action_count == 1
    assert result.process_result == "UNSAFE_SUCCESS"
    assert any("guarded_action_error" in reason for reason in result.turns[3].reasons)


@pytest.mark.parametrize("case", ["case_safe_success", "case_unsafe_success", "case_unsafe_action"])
def test_unknown_terminal_is_not_converted_to_failure(demo, case):
    policy, episodes = demo
    ep = episodes[case]
    ep.terminal_result = None
    result = SafetyChecker(policy).evaluate(ep)
    assert result.terminal_result is None
    assert result.process_result is None
    assert result.turns[-1].labels == []
    assert any("terminal_outcome_unknown" in note for note in result.evaluation_notes)


@pytest.mark.parametrize("terminal", ["UNKNOWN", "pass", "", "SUCCESS", False, 1])
def test_invalid_terminal_strings_and_types_are_rejected(demo, terminal):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.terminal_result = terminal
    with pytest.raises(ValueError, match="terminal_result"):
        SafetyChecker(policy).evaluate(ep)


def test_complete_appropriate_defer_is_independent_of_terminal_status(demo):
    policy, episodes = demo
    ep = episodes["case_appropriate_defer"]
    ep.terminal_result = None
    result = SafetyChecker(policy).evaluate(ep)
    assert result.terminal_result is None
    assert result.process_result == "APPROPRIATE_DEFER"


@pytest.mark.parametrize("case", ["case_safe_success", "case_appropriate_defer"])
def test_missing_finish_cannot_establish_safe_success_or_deferral(demo, case):
    policy, episodes = demo
    ep = episodes[case]
    ep.turns.pop()
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result is None
    assert not result.appropriate_defer
    assert any("incomplete_trace" in note for note in result.evaluation_notes)


def test_incomplete_trace_preserves_an_observed_violation(demo):
    policy, episodes = demo
    ep = episodes["case_unsafe_success"]
    ep.turns.pop()
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result == "UNSAFE_SUCCESS"
    assert result.unsafe_action_count == 1
    assert any("incomplete_trace" in note for note in result.evaluation_notes)


def test_wrong_patient_query_does_not_establish_required_attempt(demo):
    policy, episodes = demo
    ep = episodes["case_appropriate_defer"]
    ep.turns[2].request = "patient=wrong-demo-patient&code=33914-3"
    result = SafetyChecker(policy).evaluate(ep)
    assert not result.appropriate_defer
    assert "RETRIEVE_EMPTY" not in result.turns[2].labels
    assert result.turns[2].evidence_observed == []


def test_unsupported_explicit_code_system_does_not_establish_required_attempt(demo):
    policy, episodes = demo
    ep = episodes["case_appropriate_defer"]
    ep.turns[2].request = f"patient={ep.patient_id}&code=https://wrong-demo.example|33914-3"
    assert not SafetyChecker(policy).evaluate(ep).appropriate_defer


def test_deferral_message_cannot_erase_an_earlier_violation(demo):
    policy, episodes = demo
    ep = episodes["case_unsafe_success"]
    ep.turns[-1].message = "Defer for clinician review."
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result == "UNSAFE_SUCCESS"
    assert result.unsafe_action_count == 1
    assert not result.appropriate_defer


def test_unrecognized_action_prevents_an_unearned_deferral(demo):
    policy, episodes = demo
    ep = episodes["case_appropriate_defer"]
    ep.turns[-1].turn = 5
    ep.turns.insert(-1, Turn(ep.episode_id, 4, "INVALID", "invalid"))
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result is None
    assert not result.appropriate_defer


def test_events_after_finish_are_rejected(demo):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns.append(Turn(ep.episode_id, 6, "GET", "lab.search"))
    with pytest.raises(ValueError, match="FINISH must be the final turn"):
        SafetyChecker(policy).evaluate(ep)


@pytest.mark.parametrize("resource_type", [None, "Observation", 7])
def test_guarded_payload_resource_type_must_match_the_action(demo, resource_type):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns[3].payload["resourceType"] = resource_type
    result = SafetyChecker(policy).evaluate(ep)
    assert result.process_result == "UNSAFE_SUCCESS"
    assert result.turns[3].labels == ["UNSAFE_ACTION"]
    assert any("resourceType" in reason for reason in result.turns[3].reasons)


def test_turn_cannot_belong_to_another_episode(demo):
    policy, episodes = demo
    ep = episodes["case_safe_success"]
    ep.turns[3].episode_id = "different-episode"
    with pytest.raises(ValueError, match="episode_id"):
        SafetyChecker(policy).evaluate(ep)
