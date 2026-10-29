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
    source: str = "retrieved"          # "retrieved" = agent must GET it; "task_given" = provided in the task text
    max_age_hours: Optional[float] = None   # freshness window (None = no limit)
    min_value: Optional[float] = None       # below this -> disqualifying (None = no value rule)
    max_value: Optional[float] = None       # above this -> disqualifying
    emit_check_label: bool = False     # emit CHECK_SATISFIED / CHECK_MISSING when this evidence is queried


@dataclass
class Policy:
    policy_id: str
    version: str
    status: str
    guarded_tools: list[str]           # actions that require prerequisites, e.g. medicationrequest.create
    required_before_action: list[str]  # names of EvidenceRule that must be satisfied before a guarded action
    evidence: dict[str, EvidenceRule]
    defer_keywords: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        raw = yaml.safe_load(Path(path).read_text())
        ev = {name: EvidenceRule(name=name, **cfg) for name, cfg in raw["evidence"].items()}
        missing = [r for r in raw["required_before_action"] if r not in ev]
        if missing:
            raise ValueError(f"required_before_action names unknown evidence: {missing}")
        return cls(
            policy_id=raw["policy_id"],
            version=str(raw["version"]),
            status=raw.get("status", "UNREVIEWED"),
            guarded_tools=raw["guarded_tools"],
            required_before_action=raw["required_before_action"],
            evidence=ev,
            defer_keywords=[k.lower() for k in raw.get("defer_keywords", [])],
        )

    def rule_for_code(self, code: str) -> Optional[EvidenceRule]:
        for rule in self.evidence.values():
            if code in rule.codes:
                return rule
        return None
