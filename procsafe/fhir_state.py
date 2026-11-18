"""FHIR simulator state fingerprint (D4 item 5).

A Docker image digest pins the *software*, not the *record*. The harness's own POSTs mutate the
simulator: every task-5/9/10 run writes MedicationRequests and ServiceRequests, and task-3/8 cases
would write Observations and referrals. Two runs of the same image can therefore see different
patient records, so the image digest alone cannot establish reproducibility.

WHAT IS HASHED
--------------
A canonical projection, never the raw server bytes (which carry server-assigned ids, versions and
`lastUpdated` stamps that change on every restart and would make every fingerprint unique).

For each (patient, code) pair in scope, the observation projection is the sorted list of

    [effectiveDateTime, value, unit, code, system]

so the fingerprint covers exactly the fields every policy reads: identity, time, value, unit and
coding. For the writable resource types it additionally records a **count** per patient, because a
write is a change of state even when its content is irrelevant to scoring.

The result is:

    {"scope_sha256": ..., "observations_sha256": ..., "writes_sha256": ...,
     "write_counts": {...}, "patients": n, "codes": [...], "fingerprint": <sha256 of the above>}

RESET PROCEDURE
---------------
State is reset by recreating the container from the pinned image digest - not by deleting
resources, which cannot restore overwritten ones:

    docker rm -f <container>
    docker run -d --name <container> -p 8080:8080 <image>@<digest>

then recomputing the fingerprint and comparing it to the pristine baseline. `verify_pristine()`
does the comparison. A run whose closing fingerprint differs from its opening one mutated the
record and must say so in its manifest.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Iterable, Optional

# Resource types the harness can write, so their counts are part of the state.
WRITABLE = ("MedicationRequest", "ServiceRequest", "Observation", "Procedure")


def _get(base: str, path: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def observation_projection(base: str, patient: str, code: str) -> list:
    """The scoring-relevant fields of every observation for one patient and code, canonically ordered."""
    bundle = _get(base, f"Observation?patient={patient}&code={code}&_count=5000&_format=json")
    rows = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        vq = res.get("valueQuantity") or {}
        codings = sorted((c.get("system"), c.get("code"))
                         for c in (res.get("code", {}).get("coding") or []))
        rows.append([res.get("effectiveDateTime"), vq.get("value"), vq.get("unit"), codings])
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return rows


def write_counts(base: str, patients: Iterable[str]) -> dict:
    """Per-patient counts of the resource types the harness can create."""
    counts = {}
    for rtype in WRITABLE:
        per = {}
        for p in patients:
            try:
                bundle = _get(base, f"{rtype}?patient={p}&_summary=count&_format=json")
                per[p] = bundle.get("total", 0)
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
                per[p] = None
        counts[rtype] = per
    return counts


def state_fingerprint(base: str, patients: list[str], codes: list[str],
                      include_write_counts: bool = True) -> dict:
    """The simulator-state fingerprint for a declared scope.

    `patients` and `codes` ARE the scope: a fingerprint is only comparable to another computed over
    the same scope, which is why `scope_sha256` is part of the record.
    """
    patients, codes = sorted(set(patients)), sorted(set(codes))
    obs = {p: {c: observation_projection(base, p, c) for c in codes} for p in patients}
    counts = write_counts(base, patients) if include_write_counts else {}
    body = {
        "scope_sha256": _sha({"patients": patients, "codes": codes}),
        "observations_sha256": _sha(obs),
        "writes_sha256": _sha(counts) if include_write_counts else None,
        "write_counts_total": {k: sum(v for v in per.values() if isinstance(v, int))
                               for k, per in counts.items()} if include_write_counts else {},
        "patients": len(patients),
        "codes": codes,
        "method": "canonical projection [effectiveDateTime, value, unit, codings] per patient+code",
    }
    body["fingerprint"] = _sha(body)
    return body


def verify_pristine(current: dict, baseline: Optional[dict]) -> dict:
    """Compare a fingerprint with a recorded baseline. States a fact; never repairs anything."""
    if baseline is None:
        return {"status": "no_baseline",
                "note": "no pristine baseline recorded, so state identity cannot be asserted"}
    if current.get("scope_sha256") != baseline.get("scope_sha256"):
        return {"status": "incomparable",
                "note": "the fingerprints were computed over different scopes"}
    if current.get("fingerprint") == baseline.get("fingerprint"):
        return {"status": "matches_baseline"}
    changed = [k for k in ("observations_sha256", "writes_sha256")
               if current.get(k) != baseline.get(k)]
    return {"status": "differs_from_baseline", "changed": changed,
            "note": "the simulator record is not in its pristine state; recreate the container "
                    "from the pinned image digest before a final run"}
