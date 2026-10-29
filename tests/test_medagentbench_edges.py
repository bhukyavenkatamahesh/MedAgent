"""Synthetic log-shape regressions; these are not observed benchmark runs."""
import json
from pathlib import Path

import pytest

from procsafe.adapters.medagentbench import (
    _parse_get_response, load_overall_terminal, load_runs, parse_history,
)
from procsafe.schema import GET, POST

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tests/fixtures/mab_tasks_synthetic.json"
PREFIX = "Here is the response from the GET request:\n"


@pytest.mark.parametrize("body", [
    "{broken", "[]", "null", "{}",
    '{"resourceType": "Bundle", "entry": null}',
    '{"resourceType": "Bundle", "entry": {}}',
    '{"resourceType": "Bundle", "entry": [null]}',
    '{"resourceType": "Bundle", "entry": [{}]}',
    '{"resourceType": "Bundle", "entry": [{"resource": null}]}',
    '{"resourceType": "Observation", "code": null}',
    '{"resourceType": "Observation", "code": {"coding": [null]}}',
    '{"resourceType": "Observation", "subject": {"reference": 123}}',
])
def test_malformed_get_responses_produce_error_not_evidence(body):
    resources, error = _parse_get_response(PREFIX + body)
    assert resources == []
    assert error


def test_bundle_with_one_bad_entry_does_not_partially_count_evidence():
    body = {"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "Observation", "id": "synthetic-k"}},
        {"resource": "not a resource"},
    ]}
    resources, error = _parse_get_response(PREFIX + json.dumps(body))
    assert resources == [] and error == "malformed_response_resource"


@pytest.mark.parametrize("text", ["", "Timeout", None, 123])
def test_missing_failed_or_nontext_response_is_not_empty_success(text):
    resources, error = _parse_get_response(text)
    assert resources == [] and error


def test_actual_empty_bundle_is_successful_empty_response():
    assert _parse_get_response(PREFIX + '{"resourceType": "Bundle", "entry": []}') == ([], None)


def test_python_repr_get_response_is_still_supported():
    resource = {"resourceType": "Patient", "id": "synthetic-patient"}
    resources, error = _parse_get_response(PREFIX + repr(resource) + ". Please call FINISH when ready")
    assert resources == [resource] and error is None


def test_operation_outcome_is_not_clinical_evidence():
    resource = {"resourceType": "OperationOutcome", "issue": [{"severity": "error"}]}
    assert _parse_get_response(PREFIX + json.dumps(resource)) == ([], "operation_outcome_response")


@pytest.mark.parametrize("payload", ["{broken", "null", "[]", "7", '"text"'])
def test_malformed_post_remains_a_guarded_action_attempt(payload):
    history = [{"role": "agent", "content": "POST http://example/fhir/MedicationRequest\n" + payload}]
    turn = parse_history(history, "synthetic-episode")[0]
    assert turn.action_type == POST
    assert turn.tool == "medicationrequest.create"
    assert turn.payload is None and turn.error == "invalid_post_payload"


def test_malformed_get_environment_message_preserves_action():
    history = [{"role": "agent", "content": "GET http://example/fhir/Observation?code=K"},
               {"role": "user", "content": {"unexpected": "object"}}]
    turn = parse_history(history, "synthetic-episode")[0]
    assert turn.action_type == GET and turn.response_resources == []
    assert turn.error == "invalid_response_text"


def test_malformed_finish_does_not_become_termination():
    assert parse_history([{"role": "agent", "content": "FINISH(unclosed"}], "synthetic")[0].action_type == "INVALID"


def _write_run(tmp_path, status="completed", repeats=1):
    source = ROOT / "tests/fixtures/mab_runs_synthetic.jsonl"
    record = json.loads(source.read_text().splitlines()[0])
    record["output"]["status"] = status
    path = tmp_path / "runs.jsonl"
    path.write_text("\n".join(json.dumps(record) for _ in range(repeats)))
    return path


@pytest.mark.parametrize("status,expected", [
    ("Incorrect", "FAIL"), ("TaskStatus.Incorrect", "FAIL"),
    ("Correct", "PASS"), ("completed", None),
])
def test_logged_terminal_status_is_explicit_or_unknown(tmp_path, status, expected):
    episodes = load_runs(_write_run(tmp_path, status), TASKS)
    assert episodes[0].terminal_result == expected


def test_explicit_terminal_input_and_consistent_episode_identity(tmp_path):
    episodes = load_runs(_write_run(tmp_path), TASKS, terminal_results={0: "FAIL"})
    assert episodes[0].terminal_result == "FAIL"
    assert all(turn.episode_id == episodes[0].episode_id for turn in episodes[0].turns)


def test_duplicate_selected_runs_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate selected run"):
        load_runs(_write_run(tmp_path, repeats=2), TASKS)


def test_duplicate_overall_outcomes_rejected(tmp_path):
    path = tmp_path / "overall.json"
    path.write_text(json.dumps({"raw_results": [
        {"index": 0, "status": "Correct"}, {"index": 0, "status": "Incorrect"},
    ]}))
    with pytest.raises(ValueError, match="Duplicate terminal result"):
        load_overall_terminal(path)
