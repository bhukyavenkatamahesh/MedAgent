"""Authored fixture metadata is input, never a simulated benchmark result."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from procsafe.adapters.demo_json import load_demo
from procsafe.checker import SafetyChecker
from procsafe.policy import Policy
from procsafe.report import write_outputs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/synthetic_fhir_demo_data.json"
SUPPLEMENT = ROOT / "data/demo_supplemental.json"


@pytest.fixture
def policy():
    return Policy.load(ROOT / "policies/demo_renal_v0.yaml")


def test_original_demo_bytes_are_preserved():
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == "2471a1649abec8cfcdb1129afa8f426d21337b56a1ee83dfdc05128097c657dc"


def test_explicit_authored_inputs_and_override(policy):
    episodes, expected = load_demo(DATA, policy)
    assert {ep.episode_id: ep.terminal_result for ep in episodes} == {
        "case_safe_success": "PASS", "case_unsafe_success": "PASS",
        "case_unsafe_action": "FAIL", "case_appropriate_defer": "PASS",
    }
    assert all(ep.reference_time == datetime(2026, 9, 19, 10, tzinfo=timezone.utc) for ep in episodes)
    assert all(ep.meta["input_provenance"]["kind"] == "AUTHORED_TEST_INPUT" for ep in episodes)
    assert expected["case_appropriate_defer"]["turns"][3] == ["RETRIEVE_EMPTY", "CHECK_MISSING"]
    assert "medication_and_requested_dose" not in policy.required_before_action


@pytest.mark.parametrize("field,value", [
    ("reference_time", None), ("reference_time", "2026-09-19T10:00:00"),
    ("provenance", "OBSERVED"), ("schema_version", "unknown"),
])
def test_incomplete_or_misrepresented_metadata_rejected(tmp_path, policy, field, value):
    supplement = json.loads(SUPPLEMENT.read_text())
    supplement[field] = value
    path = tmp_path / "supplement.json"
    path.write_text(json.dumps(supplement))
    with pytest.raises(ValueError):
        load_demo(DATA, policy, path)


def test_no_terminal_fallback_and_no_original_result_override(tmp_path, policy):
    supplement = json.loads(SUPPLEMENT.read_text())
    path = tmp_path / "supplement.json"
    del supplement["cases"]["case_safe_success"]["terminal_result"]
    path.write_text(json.dumps(supplement))
    with pytest.raises(ValueError, match="explicit authored terminal_result"):
        load_demo(DATA, policy, path)
    supplement = json.loads(SUPPLEMENT.read_text())
    supplement["cases"]["case_unsafe_success"]["terminal_result"] = "FAIL"
    path.write_text(json.dumps(supplement))
    with pytest.raises(ValueError, match="conflicts with original"):
        load_demo(DATA, policy, path)


def test_expected_labels_never_enter_evaluation(tmp_path, policy):
    original_episodes, _ = load_demo(DATA, policy)
    altered = json.loads(DATA.read_text())
    for case in altered["cases"]:
        case["expected_episode_label"] = "ARBITRARY_TEST_EXPECTATION"
        for turn in case["trajectory"]:
            turn["expected_labels"] = ["ARBITRARY_TEST_EXPECTATION"]
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(altered))
    episodes, expected = load_demo(path, policy, SUPPLEMENT)
    assert episodes == original_episodes
    assert expected["case_safe_success"]["episode"] == "ARBITRARY_TEST_EXPECTATION"
    assert SafetyChecker(policy).evaluate(episodes[0]).process_result == "SAFE_SUCCESS"


def test_policy_changes_cannot_manufacture_terminal_results(policy):
    original, _ = load_demo(DATA, policy)
    policy.required_before_action = ["patient_identity"]
    changed, _ = load_demo(DATA, policy)
    assert [ep.terminal_result for ep in changed] == [ep.terminal_result for ep in original]


def test_report_retains_authored_input_attribution(tmp_path, policy):
    episodes, _ = load_demo(DATA, policy)
    result = SafetyChecker(policy).evaluate(episodes[0])
    write_outputs([result], {}, tmp_path)
    saved = json.loads((tmp_path / "episodes.jsonl").read_text())
    assert saved["input_provenance"]["kind"] == "AUTHORED_TEST_INPUT"
    assert "not observed benchmark results" in (tmp_path / "report.md").read_text()
    assert "AUTHORED_TEST_INPUT" in (tmp_path / "turn_labels.csv").read_text()


@pytest.mark.parametrize("returned", [None, "obs-demo-pot-001", [None],
                                      ["unknown-id"], ["obs-demo-pot-001", "obs-demo-pot-001"]])
def test_malformed_or_unresolvable_return_ids_rejected(tmp_path, policy, returned):
    data = json.loads(DATA.read_text())
    data["cases"][0]["trajectory"][1]["returns"] = returned
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="resource ID"):
        load_demo(path, policy, SUPPLEMENT)


@pytest.mark.parametrize("duplicate", ["case", "resource"])
def test_duplicate_demo_identity_rejected(tmp_path, policy, duplicate):
    data = json.loads(DATA.read_text())
    if duplicate == "case":
        data["cases"].append(data["cases"][0])
    else:
        resources = data["cases"][0]["resources"]
        resources.append(resources[0])
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        load_demo(path, policy, SUPPLEMENT)
