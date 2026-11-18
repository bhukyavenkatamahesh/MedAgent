"""Task Safety Policy: loaded from a versioned YAML file.

The policy is *configuration*, not code. Thresholds live only in the YAML so
that a clinician can review one file, and so every result can be traced to the
exact policy version that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class EvidenceRule:
    name: str                          # e.g. "renal_function"
    resource_type: str = "Observation"  # FHIR resource type that carries it
    codes: list[str] = field(default_factory=list)  # LOINC / local codes that count as this evidence
    code_systems: list[str] = field(default_factory=list)  # optional allowed namespaces; no inferred terminology mapping
    units: list[str] = field(default_factory=list)  # optional exact units; no implicit conversion
    # Codes whose EMPTY result proves the chart holds no such evidence. Default (empty) = `codes`.
    # Needed because a policy may accept several codes while the environment stores only one: an
    # empty answer to a code the server never uses says nothing about the chart.
    absence_codes: list[str] = field(default_factory=list)
    # True when a faithful query that returned NOTHING satisfies this prerequisite. Needed where the
    # task's action is triggered by absence (task 10 orders a new test when none is on record), so
    # ordering after a verified-empty search is correct rather than premature.
    satisfied_by_verified_absence: bool = False
    source: str = "retrieved"          # "retrieved" = agent must GET it; "task_given" = provided in the task text
    max_age_hours: Optional[float] = None   # freshness window (None = no limit)
    min_value: Optional[float] = None       # below this -> disqualifying (None = no value rule)
    max_value: Optional[float] = None       # above this -> disqualifying
    emit_check_label: bool = False     # emit CHECK_SATISFIED / CHECK_MISSING when this evidence is queried


ACTION_STATUSES = ("REQUIRED", "NOT_REQUIRED", "UNDETERMINED", "NOT_CONFIGURED")
OPERATORS = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=", "older_than_days": "older than"}
# Operators that compare the evidence's AGE at the reference time instead of its value. Needed by
# task 10, whose trigger is "the last result is older than one year", not a value threshold.
AGE_OPERATORS = ("older_than_days",)


@dataclass
class ActionRequirement:
    """When does the task REQUIRE a given action (tool)?

    Kept separate from EvidenceRule.min_value / max_value: those say when the evidence
    *permits* a guarded action, this says when the task *demands* one. Every rule must cite
    its `source` (benchmark task text and/or reference grader) and its `review_status`,
    both of which appear in the report.
    """
    tool: str
    evidence: str
    operator: str                      # lt | lte | gt | gte
    value: float
    source: str                        # citation for the condition; no uncited thresholds
    review_status: str                 # e.g. TASK_NATIVE_AWAITING_CLINICAL_REVIEW
    # Status when a successful query showed no evidence inside the task's window.
    # NOT_REQUIRED only where the task text itself says not to act (task5/task9 both do).
    no_recent_evidence: str = "UNDETERMINED"
    # Require a usable timestamp on every matching observation: without one the "most recent"
    # value is ambiguous, so the status is UNDETERMINED even when no freshness window applies.
    require_dated_observations: bool = True
    note: str = ""

    @property
    def basis(self) -> str:
        """What the condition compares: the evidence's value, or its age in days."""
        return "age_days" if self.operator in AGE_OPERATORS else "value"

    @property
    def condition_text(self) -> str:
        if self.basis == "age_days":
            return f"{self.evidence} older than {self.value:g} days"
        return f"{self.evidence} {OPERATORS[self.operator]} {self.value:g}"

    def triggered(self, quantity: float) -> bool:
        """`quantity` is the evidence value, or its age in days for an age operator."""
        return {"lt": quantity < self.value, "lte": quantity <= self.value,
                "gt": quantity > self.value, "gte": quantity >= self.value,
                "older_than_days": quantity > self.value}[self.operator]


@dataclass
class Policy:
    policy_id: str
    version: str
    status: str
    guarded_tools: list[str]           # actions that require prerequisites, e.g. medicationrequest.create
    required_before_action: list[str]  # names of EvidenceRule that must be satisfied before a guarded action
    evidence: dict[str, EvidenceRule]
    defer_keywords: list[str] = field(default_factory=list)
    # Writes (POSTs) that are expected but not guarded, e.g. task9's follow-up lab ServiceRequest.
    # None (key absent) = legacy v0 behaviour: every unguarded POST is OTHER_ACTION.
    # A list (even empty) = every POST that is neither guarded nor listed here is an UNEXPECTED_WRITE.
    allowed_writes: Optional[list[str]] = None
    # Optional. tool -> ActionRequirement. None (key absent) = no action-requirement judgement
    # at all (status NOT_CONFIGURED), which is the behaviour of every v0 / v1 policy.
    action_requirements: Optional[dict[str, ActionRequirement]] = None

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        raw = yaml.safe_load(Path(path).read_text())
        ev = {name: EvidenceRule(name=name, **cfg) for name, cfg in raw["evidence"].items()}
        missing = [r for r in raw["required_before_action"] if r not in ev]
        if missing:
            raise ValueError(f"required_before_action names unknown evidence: {missing}")
        reqs = None
        if raw.get("action_requirements") is not None:
            reqs = {}
            for tool, cfg in raw["action_requirements"].items():
                cfg = dict(cfg)
                cond = cfg.pop("condition", None)
                if not isinstance(cond, dict) or cond.get("operator") not in OPERATORS:
                    raise ValueError(f"action_requirements[{tool}]: condition needs operator in {sorted(OPERATORS)}")
                if cfg.get("evidence") not in ev:
                    raise ValueError(f"action_requirements[{tool}]: unknown evidence {cfg.get('evidence')!r}")
                for key in ("source", "review_status"):
                    if not str(cfg.get(key, "")).strip():
                        raise ValueError(f"action_requirements[{tool}]: '{key}' is required so every "
                                         "action condition stays traceable and reviewable")
                # REQUIRED is allowed because for some tasks the ABSENCE of a result is itself the
                # trigger (task 10: "order a new HbA1C if none is on record").
                if cfg.get("no_recent_evidence", "UNDETERMINED") not in ("NOT_REQUIRED", "UNDETERMINED",
                                                                         "REQUIRED"):
                    raise ValueError(f"action_requirements[{tool}]: no_recent_evidence must be "
                                     "NOT_REQUIRED, UNDETERMINED or REQUIRED")
                reqs[tool] = ActionRequirement(tool=tool, operator=cond["operator"],
                                               value=float(cond["value"]), **cfg)
        return cls(
            policy_id=raw["policy_id"],
            version=str(raw["version"]),
            status=raw.get("status", "UNREVIEWED"),
            guarded_tools=raw["guarded_tools"],
            required_before_action=raw["required_before_action"],
            evidence=ev,
            defer_keywords=[k.lower() for k in raw.get("defer_keywords", [])],
            allowed_writes=raw.get("allowed_writes"),
            action_requirements=reqs,
        )

    def rule_for_code(self, code: str) -> Optional[EvidenceRule]:
        for rule in self.evidence.values():
            if code in rule.codes:
                return rule
        return None
