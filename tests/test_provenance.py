"""Regression tests for the MedOmit reproducibility layer (Milestone 1).

Covers the validation list: stable episode UID construction; different repeat IDs; different
tasks/patients; missing model metadata; missing seed support; manifest integrity and hashes;
output-directory collision prevention.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from procsafe.provenance import (MANIFEST_VERSION, RunManifest, build_episode_uid, build_run_id,
                                 derive_seed, deterministic_case_order, ensure_fresh_output_dir,
                                 evaluator_version, file_sha256, parse_episode_uid,
                                 policy_fingerprints, prompt_fingerprint, seed_record, slug)

REPO = Path(__file__).resolve().parents[1]
RUN_ID = "2026-11-18__qwen2.5-1.5b-instruct__v4-decision-step__r1"


# --- episode UID -------------------------------------------------------------------------------

def test_episode_uid_is_stable_across_calls():
    a = build_episode_uid(RUN_ID, "task9_5", 244)
    b = build_episode_uid(RUN_ID, "task9_5", 244)
    assert a == b == f"{RUN_ID}__task9_5#244"


def test_episode_uid_differs_by_repeat():
    r1 = build_run_id("2026-11-18", "qwen2.5:1.5b-instruct", "v4_decision_step", 1)
    r2 = build_run_id("2026-11-18", "qwen2.5:1.5b-instruct", "v4_decision_step", 2)
    assert r1 != r2
    assert build_episode_uid(r1, "task9_5", 244) != build_episode_uid(r2, "task9_5", 244)


def test_episode_uid_differs_by_task_and_by_case_index():
    assert build_episode_uid(RUN_ID, "task9_5", 244) != build_episode_uid(RUN_ID, "task5_5", 244)
    assert build_episode_uid(RUN_ID, "task9_5", 244) != build_episode_uid(RUN_ID, "task9_5", 240)


def test_episode_uid_round_trips():
    uid = build_episode_uid(RUN_ID, "task10_17", 317)
    assert parse_episode_uid(uid) == {"run_id": RUN_ID, "task_id": "task10_17", "case_index": 317}


def test_task_id_alone_is_not_unique_across_runs():
    """The historical artefacts key on task_id, which recurs in every run. Guard the fix."""
    runs = [build_run_id("2026-11-16", "llama3.2:1b", "v2_clinical_sequence", r) for r in (0, 1)]
    uids = {build_episode_uid(r, "task9_5", 244) for r in runs}
    assert len(uids) == 2


def test_run_id_and_slug_are_filesystem_safe():
    s = slug("Qwen2.5:1.5B-Instruct (Q4_K_M)")
    assert "/" not in s and ":" not in s and " " not in s and s == s.lower()


# --- seeds -------------------------------------------------------------------------------------

def test_derive_seed_is_deterministic_and_case_specific():
    a = derive_seed("exp1", "task9_5", 1)
    assert a == derive_seed("exp1", "task9_5", 1)
    assert a != derive_seed("exp1", "task9_5", 2)
    assert a != derive_seed("exp1", "task5_1", 1)
    assert a != derive_seed("exp2", "task9_5", 1)
    assert 0 <= a < 2 ** 31 - 1


def test_seed_record_does_not_claim_determinism_without_verified_support():
    rec = seed_record("exp1", ["task9_5", "task5_1"], 1, runtime="ollama", honoured=None)
    assert rec["seed_support"] == "unverified"
    assert rec["deterministic"] is False
    assert len(rec["requested"]) == 2
    assert "requested" in rec["note"].lower() or "not" in rec["note"].lower()


def test_seed_record_marks_absent_seed_support_as_not_honoured():
    rec = seed_record("exp1", ["task9_5"], 1, runtime="ollama", honoured=False)
    assert rec["seed_support"] == "not honoured"
    assert rec["deterministic"] is False


def test_seed_record_honoured_still_does_not_promise_bitwise_reproduction():
    rec = seed_record("exp1", ["task9_5"], 1, runtime="vllm", honoured=True)
    assert rec["seed_support"] == "honoured"
    assert rec["deterministic"] is False, "server state and hardware are not pinned by a seed"


def test_deterministic_case_order_is_sorted_and_deduplicated():
    assert deterministic_case_order([244, 120, 244, 90]) == [90, 120, 244]


# --- fingerprints ------------------------------------------------------------------------------

def test_policy_fingerprints_record_hash_and_review_status():
    paths = sorted(str(p) for p in (REPO / "policies").glob("mab_task*_v2.yaml"))
    assert paths, "the v2 policies must exist"
    fps = policy_fingerprints(paths)
    assert len(fps) == len(paths)
    for fp in fps:
        assert len(fp["sha256"]) == 64
        assert fp["policy_id"]


def test_evaluator_version_hashes_the_scoring_source():
    ev = evaluator_version(str(REPO))
    assert len(ev["source_sha256"]) == 64
    assert ev["source_files"] > 0
    assert "commit" in ev


def test_missing_model_metadata_is_reported_not_invented():
    pf = prompt_fingerprint(None, "v4_decision_step")
    assert pf["version"] == "v4_decision_step"
    assert pf["sha256"] is None


def test_prompt_fingerprint_hashes_text_when_available():
    pf = prompt_fingerprint("You are an agent.", "v4_decision_step")
    assert len(pf["sha256"]) == 64


def test_file_sha256_returns_none_for_missing_file():
    assert file_sha256(REPO / "does_not_exist.xyz") is None


# --- manifest ----------------------------------------------------------------------------------

def _manifest(**kw):
    base = dict(experiment_id="exp1", run_id=RUN_ID, manifest_version=MANIFEST_VERSION,
                model={"name": "qwen2.5:1.5b-instruct", "digest": None},
                prompt=prompt_fingerprint(None, "v4_decision_step"),
                seeds=seed_record("exp1", ["task9_5"], 1, "ollama"), repeat=1,
                cases={"count": 1, "indices": [244]}, policies=[], evaluator={}, grader={},
                benchmark={}, simulator={}, host={}, artifacts={},
                episodes=[{"episode_uid": build_episode_uid(RUN_ID, "task9_5", 244)}])
    base.update(kw)
    return RunManifest(**base)


def test_manifest_is_versioned_and_self_hashing():
    m = _manifest(created_at="2026-11-18T00:00:00Z")
    assert m.manifest_version == MANIFEST_VERSION
    h = m.self_hash()
    assert len(h) == 64
    assert h == _manifest(created_at="2026-11-18T00:00:00Z").self_hash()


def test_manifest_hash_changes_when_any_field_changes():
    a = _manifest(created_at="2026-11-18T00:00:00Z")
    b = _manifest(created_at="2026-11-18T00:00:00Z", repeat=2)
    assert a.self_hash() != b.self_hash()


def test_manifest_round_trips_through_json(tmp_path):
    m = _manifest()
    p = tmp_path / "run_manifest.json"
    m.write(p)
    body = json.loads(p.read_text())
    assert body["run_id"] == RUN_ID
    assert body["manifest_version"] == MANIFEST_VERSION
    assert body["episodes"][0]["episode_uid"].endswith("__task9_5#244")


def test_manifest_records_unavailable_fields_with_reasons():
    m = _manifest()
    m.unavailable = {"model.digest": "not recorded by the runner"}
    body = json.loads(m.to_json())
    assert body["unavailable"]["model.digest"]


# --- output directory collisions ---------------------------------------------------------------

def test_fresh_output_dir_created_when_absent(tmp_path):
    out = ensure_fresh_output_dir(tmp_path / "new_run")
    assert out.is_dir()


def test_non_empty_output_dir_is_refused(tmp_path):
    (tmp_path / "x.json").write_text("{}")
    with pytest.raises(FileExistsError):
        ensure_fresh_output_dir(tmp_path)


def test_non_empty_output_dir_allowed_only_with_force(tmp_path):
    (tmp_path / "x.json").write_text("{}")
    assert ensure_fresh_output_dir(tmp_path, force=True) == tmp_path


def test_empty_output_dir_is_accepted(tmp_path):
    assert ensure_fresh_output_dir(tmp_path) == tmp_path


# --- the historical runs stay untouched --------------------------------------------------------

@pytest.mark.parametrize("frozen", ["runs/E0_grader_audit", "runs/E1_null_agents",
                                    "outputs/human_validation_v1"])
def test_frozen_directories_are_not_modified_by_the_provenance_layer(frozen):
    """The provenance modules must not import, open for writing, or reference frozen paths."""
    src = (REPO / "procsafe/provenance.py").read_text() + (REPO / "procsafe/output_status.py").read_text()
    assert frozen not in src


def test_provenance_is_not_imported_by_any_scoring_module():
    """Scoring must be unchanged by Milestone 1."""
    for name in ("checker.py", "metrics.py", "policy.py", "evidence.py", "schema.py"):
        p = REPO / "procsafe" / name
        if p.is_file():
            text = p.read_text()
            imports = re.findall(r"^\s*(?:from|import)\s+\S+.*$", text, re.M)
            for line in imports:
                assert "provenance" not in line, f"{name} must not import the provenance layer"
                assert "output_status" not in line, f"{name} must not import output_status"


def test_cli_manifest_on_a_historical_run(tmp_path):
    run = REPO / "runs/2026-11-16_slm-heldout_n20/fewshot2/llama3.2-1b-ctx8k"
    if not run.is_dir():
        pytest.skip("historical run not present")
    out = tmp_path / "m"
    r = subprocess.run([sys.executable, str(REPO / "scripts/medomit_provenance.py"), "manifest",
                        "--run", str(run), "--out", str(out)],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    body = json.loads((out / "run_manifest.json").read_text())
    assert body["cases"]["count"] == 20
    assert len(body["episodes"]) == 20
    assert body["unavailable"], "historical gaps must be declared"
    assert all(e["requested_seed"] is None for e in body["episodes"])
