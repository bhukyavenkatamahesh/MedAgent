"""Computed-answer grounding: a generic rule for answers that are an AGGREGATE of the read set.

STATUS: SPECIFIED AND TESTED, DELIBERATELY NOT WIRED IN. Nothing in the scoring path imports this
module, because wiring it changes a scoring-policy definition and that needs the supervisor's
approval. A test enforces the isolation.

THE PROBLEM IT SOLVES
---------------------
Answer grounding today asks: does the stated number equal the value of a policy evidence item that
was returned? That is right for "most recent X" tasks and wrong for any task whose answer is
computed. MedAgentBench task 6 asks for the *average* CBG over 24 hours, so the correct answer
usually equals no returned value at all and today's check would mark every correct answer
`not_retrieved`.

THE RULE
--------
The aggregate is recomputed **from the read set only** - the observations actually returned to the
agent - and never by querying the simulator. Two reasons: the question we are asking is whether the
agent's own evidence supports its answer, and querying the server for a case in a final test set
would expose its reference answer.

A stated number is `aggregate_supported` when all of these hold:

  1. the qualifying set Q is non-empty;
  2. every member of Q is valid: right patient, declared code and code system, declared unit,
     inside the declared window, a usable timestamp, and a finite numeric value;
  3. no in-window observation was *excluded for being invalid or undated* - if any was, the mean the
     agent could compute is ambiguous, so the verdict is `aggregate_undetermined`, not supported;
  4. |stated - recomputed| <= tolerance, with the tolerance declared by the policy (task 6's grader
     uses `abs(l[0] - ref) < 0.1`, so a policy mirroring it declares 0.1).

Empty Q is where this meets the L1 sentinel rule, and the semantics are identical: a faithful query
that returned nothing establishes absence, so the task's declared sentinel is `sentinel_supported`;
anything weaker - no query, a failed query, a wrong-patient query, a narrowed filter - leaves it
`sentinel_absence_not_established`.

WHAT IT REFUSES TO CLAIM
------------------------
`read_set_completeness` is reported, never assumed. A narrowed query can yield a read set whose mean
is internally consistent but unrepresentative of the record. Such an answer is
`aggregate_supported_by_incomplete_read_set`, which is a distinct verdict from `aggregate_supported`
and must never be counted as grounded without saying so.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

MEAN = "mean"
SUPPORTED_FUNCTIONS = (MEAN,)

AGGREGATE_SUPPORTED = "aggregate_supported"
AGGREGATE_INCOMPLETE = "aggregate_supported_by_incomplete_read_set"
AGGREGATE_MISMATCH = "aggregate_mismatch"
AGGREGATE_UNDETERMINED = "aggregate_undetermined"
SENTINEL_SUPPORTED = "sentinel_verified_absence"
SENTINEL_NOT_ESTABLISHED = "sentinel_absence_not_established"
NO_READ_SET = "not_retrieved"

FAITHFUL, NARROWED, UNKNOWN = "faithful", "narrowed", "unknown"


@dataclass
class AggregateRule:
    """Declared by a policy; every field must be traceable to the task text or the grader."""
    function: str = MEAN
    window_hours: Optional[float] = None
    tolerance: float = 0.0
    units: tuple = ()
    codes: tuple = ()
    code_systems: tuple = ()
    sentinel: Optional[float] = None
    source: str = ""

    def __post_init__(self):
        if self.function not in SUPPORTED_FUNCTIONS:
            raise ValueError(f"unsupported aggregate function {self.function!r}; "
                             f"declared functions are {SUPPORTED_FUNCTIONS}")
        if self.tolerance < 0:
            raise ValueError("tolerance must not be negative")
        if not str(self.source).strip():
            raise ValueError("source is required so every aggregate rule stays traceable to the "
                             "task instruction or the reference grader")


@dataclass
class Observation:
    """One observation as it was RETURNED TO THE AGENT."""
    patient_id: Optional[str]
    code: Optional[str]
    code_system: Optional[str]
    unit: Optional[str]
    value: Optional[float]
    observed_at: Optional[datetime]


@dataclass
class AggregateVerdict:
    status: str
    stated: Optional[float] = None
    recomputed: Optional[float] = None
    contributing: int = 0
    excluded: list = field(default_factory=list)
    read_set_completeness: str = UNKNOWN
    reason: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status, "stated": self.stated, "recomputed": self.recomputed,
                "contributing": self.contributing, "excluded": list(self.excluded),
                "read_set_completeness": self.read_set_completeness, "reason": self.reason}


def _invalid_reason(obs: Observation, rule: AggregateRule, patient_id: str,
                    now: Optional[datetime]) -> Optional[str]:
    """Why this observation cannot contribute, or None if it can."""
    if obs.patient_id != patient_id:
        return "wrong_patient"
    if rule.codes and obs.code not in rule.codes:
        return "wrong_code"
    if rule.code_systems and obs.code_system not in rule.code_systems:
        return "wrong_code_system"
    if rule.units and obs.unit not in rule.units:
        return "unit_mismatch_or_missing"
    if obs.value is None or isinstance(obs.value, bool) or not isinstance(obs.value, (int, float)):
        return "no_numeric_value"
    if not math.isfinite(float(obs.value)):
        return "malformed_value"
    if rule.window_hours is not None:
        if not isinstance(obs.observed_at, datetime) or not isinstance(now, datetime):
            return "undated"
        if obs.observed_at.utcoffset() is None or now.utcoffset() is None:
            return "age_unknown"
    return None


def _in_window(obs: Observation, rule: AggregateRule, now: Optional[datetime]) -> Optional[bool]:
    """True/False, or None when the age cannot be determined."""
    if rule.window_hours is None:
        return True
    if (not isinstance(obs.observed_at, datetime) or not isinstance(now, datetime)
            or obs.observed_at.utcoffset() is None or now.utcoffset() is None):
        return None
    age_h = (now - obs.observed_at).total_seconds() / 3600
    # The grader's comparison is `effective_time >= cutoff - 24h`, so exactly 24h old qualifies.
    return 0 <= age_h <= rule.window_hours


def evaluate_aggregate_claim(stated: Optional[float], read_set: Iterable[Observation],
                             rule: AggregateRule, patient_id: str, now: Optional[datetime],
                             completeness: str = UNKNOWN,
                             absence_established: Optional[bool] = None) -> AggregateVerdict:
    """Is a stated number supported by an aggregate of the evidence the agent actually received?

    `completeness` is the caller's assessment of whether the query that produced the read set could
    have returned everything in scope. `absence_established` carries the L1 verified-absence
    judgement and is used only when the qualifying set is empty.
    """
    qualifying, excluded, ambiguous = [], [], False
    for obs in read_set:
        why = _invalid_reason(obs, rule, patient_id, now)
        inside = _in_window(obs, rule, now)
        if why is not None:
            excluded.append(why)
            # An observation that LOOKS in scope but cannot be validated makes the mean ambiguous.
            # A wrong unit is included here on purpose: a glucose reported in another unit is the
            # same measurement, so dropping it silently would bias the mean rather than exclude an
            # irrelevant row. Wrong patient / code / code system are genuinely out of scope.
            if why in ("undated", "age_unknown", "no_numeric_value", "malformed_value",
                       "unit_mismatch_or_missing"):
                ambiguous = True
            continue
        if inside is None:
            excluded.append("age_unknown")
            ambiguous = True
            continue
        if not inside:
            excluded.append("outside_window")
            continue
        qualifying.append(float(obs.value))

    if not qualifying:
        if rule.sentinel is not None and stated is not None and stated == rule.sentinel:
            if absence_established:
                return AggregateVerdict(SENTINEL_SUPPORTED, stated, None, 0, excluded, completeness,
                                        "no qualifying observation, and a faithful query "
                                        "established the absence")
            return AggregateVerdict(SENTINEL_NOT_ESTABLISHED, stated, None, 0, excluded,
                                    completeness,
                                    "the task's sentinel was stated, but absence was not "
                                    "established by a faithful retrieval")
        return AggregateVerdict(NO_READ_SET, stated, None, 0, excluded, completeness,
                                "no qualifying observation was returned, so no aggregate is "
                                "computable from the read set")

    if ambiguous:
        return AggregateVerdict(AGGREGATE_UNDETERMINED, stated, None, len(qualifying), excluded,
                                completeness,
                                "an observation that may belong in scope could not be validated, "
                                "so the aggregate the agent could compute is ambiguous")

    recomputed = sum(qualifying) / len(qualifying)
    if stated is None:
        return AggregateVerdict(AGGREGATE_UNDETERMINED, None, recomputed, len(qualifying), excluded,
                                completeness, "no number was stated")
    if abs(stated - recomputed) <= rule.tolerance:
        status = AGGREGATE_SUPPORTED if completeness == FAITHFUL else AGGREGATE_INCOMPLETE
        reason = ("the stated number matches the aggregate of the validated read set within the "
                  "declared tolerance")
        if completeness != FAITHFUL:
            reason += ("; the read set is not known to be complete, so this is not the same claim "
                       "as agreement with the record")
        return AggregateVerdict(status, stated, recomputed, len(qualifying), excluded, completeness,
                                reason)
    return AggregateVerdict(AGGREGATE_MISMATCH, stated, recomputed, len(qualifying), excluded,
                            completeness,
                            "the stated number does not match the aggregate of the read set within "
                            "the declared tolerance")
