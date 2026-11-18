"""Computed-answer grounding — SYNTHETIC fixtures only.

Every observation below is authored for this test file. **No task-6 reference answer was computed,
read or used**, and nothing here queries the simulator: that is the exposure boundary which keeps
task 6 eligible as a final test set.

The rule under test is specified in `procsafe/aggregate_claims.py` and is deliberately NOT wired
into the scoring path; wiring it changes a scoring-policy definition and awaits approval.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from procsafe.aggregate_claims import (AGGREGATE_INCOMPLETE, AGGREGATE_MISMATCH,
                                       AGGREGATE_SUPPORTED, AGGREGATE_UNDETERMINED, FAITHFUL,
                                       NARROWED, NO_READ_SET, SENTINEL_NOT_ESTABLISHED,
                                       SENTINEL_SUPPORTED, AggregateRule, Observation,
                                       evaluate_aggregate_claim)

NOW = datetime(2023, 11, 13, 10, 15, tzinfo=timezone.utc)
MRN, OTHER = "S0000001", "S0000002"

# Mirrors what a task-6 policy would declare: refsol task6 sums in-window GLU and divides by the
# count, with `abs(stated - ref) < 0.1`. Nothing here is a clinical threshold.
RULE = AggregateRule(function="mean", window_hours=24, tolerance=0.1, units=("mg/dL",),
                     codes=("GLU",), code_systems=("http://loinc.org",), sentinel=-1,
                     source="TEST FIXTURE mirroring refsol.py task6 L171-180 (in-window mean) and "
                            "L186 (tolerance 0.1)")


def obs(value, hours_ago=2.0, unit="mg/dL", code="GLU", system="http://loinc.org",
        patient=MRN, dated=True):
    return Observation(patient_id=patient, code=code, code_system=system, unit=unit, value=value,
                       observed_at=(NOW - timedelta(hours=hours_ago)) if dated else None)


def ev(stated, read_set, completeness=FAITHFUL, absence=None):
    return evaluate_aggregate_claim(stated, read_set, RULE, MRN, NOW, completeness, absence)


# ---- positive ------------------------------------------------------------------------------------

def test_exact_mean_of_the_read_set_is_supported():
    r = ev(110.0, [obs(100), obs(110), obs(120)])
    assert r.status == AGGREGATE_SUPPORTED
    assert r.recomputed == pytest.approx(110.0)
    assert r.contributing == 3


def test_a_single_observation_is_its_own_mean():
    r = ev(95.0, [obs(95)])
    assert r.status == AGGREGATE_SUPPORTED and r.contributing == 1


def test_a_value_inside_the_tolerance_is_supported():
    r = ev(110.09, [obs(100), obs(110), obs(120)])
    assert r.status == AGGREGATE_SUPPORTED


def test_a_rounded_answer_within_tolerance_is_supported():
    r = ev(103.3, [obs(100), obs(102), obs(108)])      # true mean 103.333...
    assert r.status == AGGREGATE_SUPPORTED


def test_out_of_window_observations_are_excluded_from_the_mean():
    r = ev(100.0, [obs(100, hours_ago=1), obs(400, hours_ago=48)])
    assert r.status == AGGREGATE_SUPPORTED
    assert r.recomputed == pytest.approx(100.0)
    assert "outside_window" in r.excluded


# ---- boundary ------------------------------------------------------------------------------------

@pytest.mark.parametrize("hours_ago,counts", [(0.0, True), (23.99, True), (24.0, True),
                                              (24.01, False)])
def test_window_boundary_is_inclusive_at_exactly_the_window(hours_ago, counts):
    """refsol compares `effective_time >= cutoff - 24h`, so exactly 24 h old qualifies."""
    r = ev(50.0, [obs(50, hours_ago=hours_ago)])
    assert (r.status == AGGREGATE_SUPPORTED) is counts


def test_tolerance_boundary_is_inclusive():
    assert ev(110.1, [obs(100), obs(110), obs(120)]).status == AGGREGATE_SUPPORTED
    assert ev(110.2, [obs(100), obs(110), obs(120)]).status == AGGREGATE_MISMATCH


def test_a_future_timestamp_does_not_count():
    r = ev(50.0, [obs(50, hours_ago=-1)])
    assert r.status != AGGREGATE_SUPPORTED


def test_zero_is_a_legitimate_value_not_a_missing_one():
    r = ev(0.0, [obs(0)])
    assert r.status == AGGREGATE_SUPPORTED and r.recomputed == 0.0


def test_negative_values_are_averaged_not_discarded():
    r = ev(-5.0, [obs(-10), obs(0)])
    assert r.status == AGGREGATE_SUPPORTED


# ---- negative: the arithmetic -------------------------------------------------------------------

def test_a_wrong_mean_is_a_mismatch_and_reports_the_true_one():
    r = ev(120.0, [obs(100), obs(110), obs(120)])
    assert r.status == AGGREGATE_MISMATCH
    assert r.recomputed == pytest.approx(110.0)


def test_stating_the_newest_value_instead_of_the_mean_is_a_mismatch():
    """The characteristic task-6 error: answering task 7's question."""
    r = ev(120.0, [obs(100, hours_ago=5), obs(120, hours_ago=1)])
    assert r.status == AGGREGATE_MISMATCH


def test_summing_instead_of_averaging_is_a_mismatch():
    r = ev(330.0, [obs(100), obs(110), obs(120)])
    assert r.status == AGGREGATE_MISMATCH


def test_no_stated_number_is_undetermined_not_supported():
    assert ev(None, [obs(100)]).status == AGGREGATE_UNDETERMINED


# ---- negative: input validation -----------------------------------------------------------------

def test_another_patients_observation_never_contributes():
    r = ev(100.0, [obs(100), obs(999, patient=OTHER)])
    assert r.status == AGGREGATE_SUPPORTED
    assert "wrong_patient" in r.excluded


def test_a_different_code_never_contributes():
    r = ev(100.0, [obs(100), obs(999, code="MG")])
    assert "wrong_code" in r.excluded and r.recomputed == pytest.approx(100.0)


def test_a_different_code_system_never_contributes():
    r = ev(100.0, [obs(100), obs(999, system="http://example.org")])
    assert "wrong_code_system" in r.excluded


def test_a_wrong_unit_makes_the_aggregate_undetermined():
    """A glucose in another unit is the SAME measurement, so dropping it would bias the mean.

    Wrong patient, code or code system are genuinely out of scope and are excluded cleanly; a unit
    mismatch is not, so it makes the aggregate ambiguous instead.
    """
    r = ev(100.0, [obs(100), obs(5.5, unit="mmol/L")])
    assert r.status == AGGREGATE_UNDETERMINED
    assert "unit_mismatch_or_missing" in r.excluded


def test_a_missing_unit_also_makes_it_undetermined():
    r = ev(100.0, [obs(100), obs(140, unit=None)])
    assert r.status == AGGREGATE_UNDETERMINED


def test_an_undated_in_scope_observation_makes_it_undetermined():
    r = ev(100.0, [obs(100), obs(140, dated=False)])
    assert r.status == AGGREGATE_UNDETERMINED
    assert "undated" in r.excluded


def test_a_non_numeric_value_makes_it_undetermined():
    r = ev(100.0, [obs(100), obs("high")])
    assert r.status == AGGREGATE_UNDETERMINED


def test_an_infinite_value_makes_it_undetermined():
    r = ev(100.0, [obs(100), obs(float("inf"))])
    assert r.status == AGGREGATE_UNDETERMINED


# ---- missing data and the sentinel --------------------------------------------------------------

def test_sentinel_with_verified_absence_is_supported():
    r = ev(-1, [], absence=True)
    assert r.status == SENTINEL_SUPPORTED


def test_sentinel_without_verified_absence_is_not_established():
    assert ev(-1, [], absence=False).status == SENTINEL_NOT_ESTABLISHED
    assert ev(-1, [], absence=None).status == SENTINEL_NOT_ESTABLISHED


def test_sentinel_when_only_out_of_window_data_came_back():
    r = ev(-1, [obs(100, hours_ago=72)], absence=True)
    assert r.status == SENTINEL_SUPPORTED
    assert "outside_window" in r.excluded


def test_a_number_stated_with_an_empty_read_set_is_not_retrieved():
    assert ev(100.0, []).status == NO_READ_SET


# ---- read-set completeness ----------------------------------------------------------------------

def test_a_narrowed_query_cannot_yield_a_fully_supported_aggregate():
    r = ev(110.0, [obs(100), obs(110), obs(120)], completeness=NARROWED)
    assert r.status == AGGREGATE_INCOMPLETE
    assert "not known to be complete" in r.reason


def test_completeness_is_reported_on_every_verdict():
    assert ev(110.0, [obs(110)]).read_set_completeness == FAITHFUL


# ---- the rule declaration itself ----------------------------------------------------------------

def test_an_aggregate_rule_requires_a_traceable_source():
    with pytest.raises(ValueError, match="source is required"):
        AggregateRule(function="mean", tolerance=0.1, source="")


def test_an_unsupported_function_is_refused():
    with pytest.raises(ValueError, match="unsupported aggregate function"):
        AggregateRule(function="median", source="x")


def test_a_negative_tolerance_is_refused():
    with pytest.raises(ValueError, match="tolerance"):
        AggregateRule(tolerance=-1, source="x")


# ---- isolation from the scoring path ------------------------------------------------------------

def test_the_aggregate_rule_is_not_wired_into_scoring():
    """Wiring it changes a scoring-policy definition, which awaits approval."""
    import re
    repo = Path(__file__).resolve().parents[1]
    for name in ("checker.py", "metrics.py", "policy.py", "evidence.py", "schema.py"):
        p = repo / "procsafe" / name
        if p.is_file():
            for line in re.findall(r"^\s*(?:from|import)\s+\S+.*$", p.read_text(), re.M):
                assert "aggregate_claims" not in line, f"{name} must not import aggregate_claims yet"


def test_no_shipped_policy_declares_an_aggregate_rule():
    repo = Path(__file__).resolve().parents[1]
    for policy in (repo / "policies").glob("*.yaml"):
        assert "answer_aggregate" not in policy.read_text()
