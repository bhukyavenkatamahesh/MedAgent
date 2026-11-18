"""Regression tests for the five-view output-status layer (Milestone 1).

The five views must stay separate and an official grade must never be rewritten:
  raw response | harness interpretation | official grade | strict parser result | completion status
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from procsafe.output_status import (FINISH_MALFORMED, FINISH_PARSED, FINISH_TRUNCATED,
                                    NO_TERMINAL_ACTION, NO_TURNS, classify_final_message, describe,
                                    official_grade)

REPO = Path(__file__).resolve().parents[1]
BALANCED = 'FINISH([{"K": 3.9}])'
TRUNCATED = 'FINISH([{"resourceType": "MedicationRequest", "medicationCodeableConcept": {"coding": ['


def test_balanced_finish_is_parsed():
    assert classify_final_message(BALANCED) == FINISH_PARSED


def test_unbalanced_finish_is_truncated_not_discarded():
    assert classify_final_message(TRUNCATED) == FINISH_TRUNCATED


def test_non_terminal_last_message():
    assert classify_final_message("GET http://localhost/fhir/Observation?code=K") == NO_TERMINAL_ACTION


def test_empty_episode():
    assert classify_final_message("") == NO_TURNS


def test_finish_without_parenthesis_is_malformed():
    assert classify_final_message("FINISH the task") == FINISH_MALFORMED


def test_official_grade_is_a_verbatim_map():
    assert official_grade("completedCorrect") == "PASS"
    assert official_grade("completedIncorrect") == "FAIL"


@pytest.mark.parametrize("status", ["agent invalid action", "agent context limit",
                                    "task limit reached", None, "unknown status"])
def test_ungraded_statuses_return_no_grade(status):
    assert official_grade(status) is None


def test_truncated_finish_keeps_its_official_fail():
    st = describe(TRUNCATED, "completedIncorrect", strict_parser_action="INVALID")
    assert st.completion_status == FINISH_TRUNCATED
    assert st.official_grade == "FAIL", "a truncated payload must never be promoted"
    assert st.graded is True
    assert st.parser_and_harness_agree is False


def test_truncated_finish_graded_correct_is_still_reported_as_pass():
    """If the harness graded it correct, we record PASS and flag the parser disagreement.

    The evaluator may not overturn the official grade in either direction.
    """
    st = describe(TRUNCATED, "completedCorrect", strict_parser_action="INVALID")
    assert st.official_grade == "PASS"
    assert st.completion_status == FINISH_TRUNCATED
    assert st.parser_and_harness_agree is False


def test_normal_finish_agrees_with_the_harness():
    st = describe(BALANCED, "completedCorrect", strict_parser_action="FINISH")
    assert st.completion_status == FINISH_PARSED
    assert st.official_grade == "PASS"
    assert st.parser_and_harness_agree is True


def test_invalid_response_is_ungraded_and_keeps_the_raw_text():
    raw = "Sure! I will now check the potassium level."
    st = describe(raw, "agent invalid action", strict_parser_action="INVALID")
    assert st.official_grade is None
    assert st.graded is False
    assert st.raw_final_message == raw


def test_raw_response_is_preserved_verbatim():
    st = describe(TRUNCATED, "completedIncorrect")
    assert st.raw_final_message == TRUNCATED


def test_views_are_all_present_and_independent():
    st = describe(TRUNCATED, "completedIncorrect", strict_parser_action="INVALID",
                  episode_uid="run__task9_5#244", task_id="task9_5", case_index=244)
    d = st.as_dict()
    for key in ("raw_final_message", "harness_status", "official_grade", "strict_parser_action",
                "completion_status"):
        assert key in d
    assert d["harness_status"] == "completedIncorrect"
    assert d["episode_uid"] == "run__task9_5#244"


def test_describe_assigns_no_safety_label():
    """Milestone 1 must not label safety; that stays with the checker."""
    d = describe(BALANCED, "completedCorrect").as_dict()
    for forbidden in ("verified_outcome", "process_result", "grounding_result",
                      "action_requirement_status", "UNVERIFIED_PASS", "UNSAFE_SUCCESS"):
        assert forbidden not in json.dumps(d)


# --- backward compatibility for the existing task 5 / 9 / 10 scoring ---------------------------

@pytest.mark.parametrize("policy", ["mab_task5_magnesium_v2.yaml", "mab_task9_potassium_v2.yaml",
                                    "mab_task10_hba1c_v2.yaml"])
def test_task_policies_are_unchanged_and_still_load(policy):
    from procsafe.policy import Policy
    p = REPO / "policies" / policy
    assert p.is_file()
    pol = Policy.load(p)
    assert pol.policy_id
    assert pol.action_requirements, "the v2 policies carry action requirements"


def test_status_cli_on_a_historical_run_matches_the_official_counts(tmp_path):
    run = REPO / "runs/2026-11-16_slm-heldout_n20/fewshot4/qwen2.5-1.5b-ctx8k"
    if not run.is_dir():
        pytest.skip("historical run not present")
    out = tmp_path / "s"
    r = subprocess.run([sys.executable, str(REPO / "scripts/medomit_provenance.py"), "status",
                        "--run", str(run), "--out", str(out)],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    summary = json.loads((out / "output_status_summary.json").read_text())
    official = json.loads((run / "medagentbench/overall.json").read_text())["custom"]
    assert summary["episodes"] == 20
    # The PASS count we report must equal the harness's own success count, exactly.
    assert summary["official_grade"].get("PASS", 0) == round(official["success rate"] * 20)
