"""Run provenance: stable identifiers, derived seeds, artefact hashes and the run manifest.

Nothing here touches scoring. No label, metric, policy or clinical rule is defined or changed in this
module; it only records what a run was made of. Fields that cannot be recovered are recorded as
`None` with a reason in `unavailable`, never invented.

Manifest schema version 1.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

MANIFEST_VERSION = 1
SEED_MODULUS = 2 ** 31 - 1          # fits the signed 32-bit seeds most runtimes accept

# ---------------------------------------------------------------- identifiers


def slug(text: str) -> str:
    """Filesystem- and id-safe form of a model or prompt name, stable across platforms."""
    return re.sub(r"[^A-Za-z0-9.]+", "-", str(text)).strip("-").lower()


def build_run_id(date: str, model: str, prompt_version: str, repeat: int | str) -> str:
    """A run is one (date, model, prompt version, repeat). Deterministic and sortable."""
    return f"{date}__{slug(model)}__{slug(prompt_version)}__r{repeat}"


def build_episode_uid(run_id: str, task_id: str, case_index: int) -> str:
    """One episode = one case inside one run.

    `task_id` alone is NOT unique across runs: the same case appears in every run, which is why
    joining on it silently merged 24 runs during the human-validation analysis.
    """
    return f"{run_id}__{task_id}#{case_index}"


def parse_episode_uid(uid: str) -> dict:
    run_id, _, tail = uid.rpartition("__")
    task_id, _, index = tail.partition("#")
    if not run_id or not task_id or not index.isdigit():
        raise ValueError(f"not an episode uid: {uid!r}")
    return {"run_id": run_id, "task_id": task_id, "case_index": int(index)}


def derive_seed(experiment_id: str, case_id: str, repeat: int) -> int:
    """A seed per (experiment, case, repeat).

    Deterministic and independent of wall-clock time, so a single episode can be replayed. This is a
    *requested* seed: whether the model runtime honours it is a separate, unverified question —
    see `seed_support` in the manifest.
    """
    digest = hashlib.sha256(f"{experiment_id}:{case_id}:{repeat}".encode()).hexdigest()
    return int(digest[:16], 16) % SEED_MODULUS


def deterministic_case_order(indices: list[int]) -> list[int]:
    """Case order is fixed by ascending index, never by set iteration or dict order."""
    return sorted(dict.fromkeys(int(i) for i in indices))


# ---------------------------------------------------------------- hashing


def file_sha256(path: str | Path) -> Optional[str]:
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha256(paths: list[str | Path]) -> Optional[str]:
    """One hash over several files, order-independent: identifies an evaluator build."""
    parts = []
    for p in sorted(Path(x) for x in paths):
        digest = file_sha256(p)
        if digest:
            parts.append(f"{p.name}:{digest}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest() if parts else None


def _git(repo: str | Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                             timeout=20)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_provenance(repo: str | Path) -> dict:
    commit = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain")
    return {"repo": str(repo), "commit": commit,
            "clean_worktree": (status == "") if status is not None else None,
            "dirty_paths": [l[3:] for l in status.splitlines()][:20] if status else []}


def evaluator_version(repo: str | Path = ".") -> dict:
    pkg = Path(repo) / "procsafe"
    return {**git_provenance(repo),
            "source_sha256": tree_sha256(sorted(pkg.glob("**/*.py"))),
            "source_files": len(list(pkg.glob("**/*.py")))}


def policy_fingerprints(policy_paths: list[str | Path]) -> list[dict]:
    out = []
    for p in policy_paths:
        path = Path(p)
        entry = {"path": str(path), "sha256": file_sha256(path),
                 "policy_id": None, "version": None, "status": None, "review_status": None}
        if path.is_file():
            text = path.read_text()
            for key, pattern in (("policy_id", r"^policy_id:\s*(\S+)"),
                                 ("version", r'^version:\s*"?([^"\n]+)"?'),
                                 ("status", r"^status:\s*(\S+)")):
                m = re.search(pattern, text, re.M)
                if m:
                    entry[key] = m.group(1).strip()
            reviews = sorted(set(re.findall(r"review_status:\s*(\S+)", text)))
            entry["review_status"] = reviews or None
        out.append(entry)
    return out


# ---------------------------------------------------------------- manifest


@dataclass
class RunManifest:
    experiment_id: str
    run_id: str
    manifest_version: int = MANIFEST_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    model: dict = field(default_factory=dict)
    prompt: dict = field(default_factory=dict)
    seeds: dict = field(default_factory=dict)
    repeat: Optional[int] = None
    cases: dict = field(default_factory=dict)
    policies: list = field(default_factory=list)
    evaluator: dict = field(default_factory=dict)
    grader: dict = field(default_factory=dict)
    benchmark: dict = field(default_factory=dict)
    simulator: dict = field(default_factory=dict)
    host: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    episodes: list = field(default_factory=list)
    unavailable: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=1, sort_keys=False)

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json() + "\n")
        return p

    def self_hash(self) -> str:
        """Hash of the manifest with its own hash field excluded, for tamper detection."""
        body = {k: v for k, v in self.__dict__.items() if k != "manifest_sha256"}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def prompt_fingerprint(prompt_text: Optional[str], version: Optional[str]) -> dict:
    return {"version": version,
            "sha256": hashlib.sha256(prompt_text.encode()).hexdigest() if prompt_text else None,
            "chars": len(prompt_text) if prompt_text else None}


def host_fingerprint() -> dict:
    import platform
    return {"platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count()}


def docker_image_digest(container: str) -> Optional[str]:
    out = subprocess.run(["docker", "inspect", "--format", "{{.Image}}", container],
                         capture_output=True, text=True)
    return out.stdout.strip() or None if out.returncode == 0 else None


def simulator_fingerprint(container: Optional[str] = None,
                          case_table: Optional[str | Path] = None) -> dict:
    """Identify the simulator state as far as it is identifiable.

    The FHIR server is mutated in place and has no snapshot mechanism, so the closest available
    identifier is the image digest plus the per-case reference answers recorded by the G0 audit.
    """
    fp: dict = {"container": container, "image_digest": None, "case_table": None,
                "case_table_sha256": None}
    if container:
        fp["image_digest"] = docker_image_digest(container)
    if case_table and Path(case_table).is_file():
        fp["case_table"] = str(case_table)
        fp["case_table_sha256"] = file_sha256(case_table)
    return fp


def seed_record(experiment_id: str, cases: list[str], repeat: int, runtime: str,
                honoured: Optional[bool] = None, note: str = "") -> dict:
    """Requested seeds, kept separate from whether the runtime actually honours them."""
    return {
        "scheme": "sha256(experiment_id:case_id:repeat) mod (2**31-1)",
        "requested": {case: derive_seed(experiment_id, case, repeat) for case in cases},
        "runtime": runtime,
        "seed_support": ("honoured" if honoured else "unverified" if honoured is None else "not honoured"),
        # Never promise bit-identical reproduction: a seed does not pin the runtime build, the
        # GPU/CPU kernels, concurrency, or the FHIR server's mutable state.
        "deterministic": False,
        "determinism_caveat": ("A requested seed constrains sampling only. Reproduction also "
                               "requires the same runtime build, hardware, batch/concurrency "
                               "settings and simulator state, none of which a seed pins."),
        "note": note or ("The runtime accepts a seed parameter, but determinism across server "
                         "builds, hardware and concurrency has not been verified in this project."),
    }


def ensure_fresh_output_dir(path: str | Path, force: bool = False) -> Path:
    """Refuse to write into a directory that already holds artefacts, unless forced.

    Protects the historical runs, G0/G1 and the frozen validation outputs from being overwritten.
    """
    p = Path(path)
    if p.exists() and any(p.iterdir()) and not force:
        raise FileExistsError(
            f"output directory {p} is not empty; choose a new versioned directory or pass force=True")
    p.mkdir(parents=True, exist_ok=True)
    return p
