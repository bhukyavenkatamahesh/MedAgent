"""Evidence Mapper: turn raw FHIR responses into named evidence items.

Important distinction kept here: evidence is only counted if it was *returned
to the agent* in a tool response. Data that merely exists in the EHR is ignored.
Mapping is deterministic (codes + subject reference), no free-text matching.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
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
    invalid_reason: Optional[str] = None


def parse_time(s: Optional[str]) -> Optional[datetime]:
    """Parse an explicit timezone without guessing one for incomplete data."""
    if not isinstance(s, str) or not s:
        return None
    try:
        value = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _codes(resource: dict) -> list[dict]:
    code = resource.get("code")
    coding = code.get("coding") if isinstance(code, dict) else None
    return [c for c in coding if isinstance(c, dict)] if isinstance(coding, list) else []


def patient_reference_id(reference: object) -> Optional[str]:
    """Accept explicit relative/absolute Patient references, including versions."""
    if not isinstance(reference, str) or not reference:
        return None
    try:
        parts = urlparse(reference).path.rstrip("/").split("/")
    except ValueError:
        return None
    if len(parts) >= 4 and parts[-2] == "_history":
        parts = parts[:-2]
    return parts[-1] if len(parts) >= 2 and parts[-2] == "Patient" and parts[-1] else None


def _subject_id(resource: dict) -> Optional[str]:
    subject = resource.get("subject")
    return patient_reference_id(subject.get("reference")) if isinstance(subject, dict) else None


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def map_resources(resources: list[dict], policy: Policy, patient_id: str) -> list[EvidenceItem]:
    """Map FHIR resources returned in one response to policy evidence items."""
    items: list[EvidenceItem] = []
    if not isinstance(resources, list):
        return items
    for r in resources:
        if not isinstance(r, dict):
            continue
        rtype = r.get("resourceType")
        if rtype == "Patient" and r.get("id") == patient_id and "patient_identity" in policy.evidence:
            items.append(EvidenceItem("patient_identity", r["id"], None, None, None))
            continue
        # Evidence about a different patient never counts.
        if _subject_id(r) != patient_id:
            continue
        for coding in _codes(r):
            code = coding.get("code")
            rule = policy.rule_for_code(code) if isinstance(code, str) else None
            if rule and rule.resource_type == rtype:
                if rule.code_systems and coding.get("system") not in rule.code_systems:
                    continue
                invalid_reason = None
                resource_id = r.get("id")
                if not isinstance(resource_id, str) or not resource_id:
                    resource_id, invalid_reason = "", "missing_resource_id"
                vq = r.get("valueQuantity")
                if not isinstance(vq, dict):
                    vq = {}
                    invalid_reason = "missing_or_malformed_quantity"
                value = vq.get("value")
                if not _finite_number(value):
                    value, invalid_reason = None, "missing_or_malformed_value"
                unit = vq.get("unit")
                if unit is not None and not isinstance(unit, str):
                    unit, invalid_reason = None, "malformed_unit"
                raw_time = r.get("effectiveDateTime", r.get("issued"))
                observed_at = parse_time(raw_time)
                if raw_time is not None and observed_at is None:
                    invalid_reason = "invalid_observation_time"
                items.append(EvidenceItem(
                    name=rule.name,
                    resource_id=resource_id,
                    value=value,
                    unit=unit,
                    observed_at=observed_at,
                    invalid_reason=invalid_reason,
                ))
                break
    return items


def requested_evidence(request: str, policy: Policy, patient_id: Optional[str] = None) -> set[str]:
    """Which evidence items did the agent *ask* for (from the query's code= param)?

    Lets us label an attempted-but-empty retrieval (e.g. renal function missing
    from the chart) as a required retrieval attempt.
    """
    if not isinstance(request, str) or not request:
        return set()
    try:
        query = urlparse(request).query or request
    except ValueError:
        return set()
    params = parse_qs(query)
    if patient_id is not None:
        for target in params.get("patient", []) + params.get("subject", []):
            if target != patient_id and patient_reference_id(target) != patient_id:
                return set()
    names = set()
    for raw in params.get("code", []):
        for token in raw.split(","):
            parts = token.strip().rsplit("|", 1)
            code = parts[-1]
            rule = policy.rule_for_code(code)
            system_matches = rule is not None and (
                len(parts) == 1 or not rule.code_systems or parts[0] in rule.code_systems
            )
            if system_matches:
                names.add(rule.name)
    return names


def evaluate_item(item: Optional[EvidenceItem], rule: EvidenceRule, now: Optional[datetime]) -> tuple[bool, str]:
    """Return (satisfied, reason) for one evidence item under its rule."""
    if item is None:
        return False, "missing"
    if item.invalid_reason:
        return False, item.invalid_reason
    if item.value is not None and not _finite_number(item.value):
        return False, "malformed_value"
    if rule.units and item.unit not in rule.units:
        return False, "unit_mismatch_or_missing"
    if rule.max_age_hours is not None:
        if (not isinstance(item.observed_at, datetime) or not isinstance(now, datetime)
                or item.observed_at.utcoffset() is None or now.utcoffset() is None):
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
