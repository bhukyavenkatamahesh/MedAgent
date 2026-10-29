"""Evidence Mapper: turn raw FHIR responses into named evidence items.

Important distinction kept here: evidence is only counted if it was *returned
to the agent* in a tool response. Data that merely exists in the EHR is ignored.
Mapping is deterministic (codes + subject reference), no free-text matching.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .policy import EvidenceRule, Policy


@dataclass
class EvidenceItem:
    name: str
    resource_id: str
    value: Optional[float]
    unit: Optional[str]
    observed_at: Optional[datetime]


def parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _codes(resource: dict) -> list[str]:
    return [c.get("code", "") for c in resource.get("code", {}).get("coding", [])]


def _subject_id(resource: dict) -> Optional[str]:
    ref = (resource.get("subject") or {}).get("reference", "")
    return ref.split("/")[-1] if ref else None


def map_resources(resources: list[dict], policy: Policy, patient_id: str) -> list[EvidenceItem]:
    """Map FHIR resources returned in one response to policy evidence items."""
    items: list[EvidenceItem] = []
    for r in resources:
        rtype = r.get("resourceType")
        if rtype == "Patient" and r.get("id") == patient_id and "patient_identity" in policy.evidence:
            items.append(EvidenceItem("patient_identity", r["id"], None, None, None))
            continue
        # Evidence about a different patient never counts.
        if _subject_id(r) not in (None, patient_id):
            continue
        for code in _codes(r):
            rule = policy.rule_for_code(code)
            if rule and rule.resource_type == rtype:
                vq = r.get("valueQuantity") or {}
                items.append(EvidenceItem(
                    name=rule.name,
                    resource_id=r.get("id", ""),
                    value=vq.get("value"),
                    unit=vq.get("unit"),
                    observed_at=parse_time(r.get("effectiveDateTime") or r.get("issued")),
                ))
                break
    return items


def requested_evidence(request: str, policy: Policy) -> set[str]:
    """Which evidence items did the agent *ask* for (from the query's code= param)?

    Lets us label an attempted-but-empty retrieval (e.g. renal function missing
    from the chart) as a required retrieval attempt.
    """
    if not request:
        return set()
    query = urlparse(request).query or request
    params = parse_qs(query)
    names = set()
    for raw in params.get("code", []):
        for code in re.split(r"[,|]", raw):
            code = code.split("|")[-1].strip()
            rule = policy.rule_for_code(code)
            if rule:
                names.add(rule.name)
    return names


def evaluate_item(item: Optional[EvidenceItem], rule: EvidenceRule, now: Optional[datetime]) -> tuple[bool, str]:
    """Return (satisfied, reason) for one evidence item under its rule."""
    if item is None:
        return False, "missing"
    if rule.max_age_hours is not None:
        if item.observed_at is None or now is None:
            return False, "freshness_unknown"
        age_h = (now - item.observed_at).total_seconds() / 3600
        if age_h > rule.max_age_hours:
            return False, f"stale ({age_h:.1f}h > {rule.max_age_hours}h)"
        if age_h < 0:
            return False, "observed_after_reference_time"
    if rule.min_value is not None or rule.max_value is not None:
        if item.value is None:
            return False, "no_value"
        if rule.min_value is not None and item.value < rule.min_value:
            return False, f"disqualifying (value {item.value} < {rule.min_value})"
        if rule.max_value is not None and item.value > rule.max_value:
            return False, f"disqualifying (value {item.value} > {rule.max_value})"
    return True, "ok"
