"""Tests for scripts/analyze_human_annotations.py.

Every CSV built here is a SOFTWARE TEST FIXTURE, generated inside the test's temporary
directory. None of it is a human annotation, and no real reviewer sheet or evaluator key is read:
the fixtures use `FIXTURE-xx` ids so they can never be confused with the ANN-xx study sample.
"""
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/analyze_human_annotations.py"
spec = importlib.util.spec_from_file_location("aha", SCRIPT)
aha = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aha)

CONTEXT = {"task": "task9", "model": "fixture-model", "prompt_condition": "fixture-prompt"}
BLINDED_COLUMNS = ["annotation_id", "task", "annotator_initials", "date",
                   "h_action_requirement", "h_required_tools", "h_medicationrequest_attempted",
                   "h_servicerequest_attempted", "h_missed_required_action",
                   "h_unnecessary_action", "h_premature_action", "h_unsafe_action",
                   "h_appropriate_deferral", "h_final_claims_grounded", "h_confidence",
                   "h_rationale", "h_flag_for_clinician"]
FULL = {"annotator_initials": "XX", "date": "2026-11-17", "h_rationale": "software fixture",
        "h_action_requirement": "REQUIRED", "h_required_tools": "both",
        "h_medicationrequest_attempted": "no", "h_servicerequest_attempted": "no",
        "h_missed_required_action": "yes", "h_unnecessary_action": "no",
        "h_premature_action": "no", "h_unsafe_action": "no", "h_appropriate_deferral": "no",
        "h_final_claims_grounded": "grounded", "h_confidence": "high", "h_flag_for_clinician": "no"}
COLUMNS = ["annotation_id", "task", "model", "prompt_condition", "annotator_initials", "date",
           "h_action_requirement", "h_required_tools", "h_medicationrequest_attempted",
           "h_servicerequest_attempted", "h_missed_required_action", "h_unnecessary_action",
           "h_premature_action", "h_unsafe_action", "h_appropriate_deferral",
           "h_final_claims_grounded", "h_confidence", "h_rationale", "h_flag_for_clinician"]


def sheet(path, rows, comment_row=True):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        if comment_row:
            w.writerow({"annotation_id": "# allowed values", "task": "task5|task9"})
        for i, overrides in enumerate(rows, 1):
            row = {"annotation_id": f"FIXTURE-{i:02d}", **CONTEXT, **FULL, **overrides}
            w.writerow(row)
    return path


def run(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True)


# ---- schema consistency with the guide and template ----
def test_allowed_values_match_the_shipped_template():
    rows = list(csv.reader(open(ROOT / "docs/ACTION_ANNOTATION_TEMPLATE.csv")))
    header, comments = rows[0], rows[1]
    documented = {h: c.lstrip("# ").strip() for h, c in zip(header, comments)}
    for field, allowed in aha.ALLOWED.items():
        assert field in documented, field
        assert documented[field] == "|".join(allowed), field


def test_guide_documents_every_annotated_field():
    guide = (ROOT / "docs/ACTION_ANNOTATION_GUIDE.md").read_text()
    for value in ("REQUIRED", "NOT_REQUIRED", "UNDETERMINED", "MISSED_REQUIRED_ACTION",
                  "UNNECESSARY_ACTION", "PREMATURE_ACTION", "UNSAFE_ACTION", "grounded"):
        assert value in guide


# ---- agreement maths ----
def test_kappa_is_one_for_perfect_agreement_with_variation():
    k, note = aha.kappa([("REQUIRED", "REQUIRED")] * 5 + [("NOT_REQUIRED", "NOT_REQUIRED")] * 5)
    assert note == "ok" and abs(k - 1.0) < 1e-9


def test_kappa_is_undefined_without_variation_rather_than_invented():
    k, note = aha.kappa([("yes", "yes")] * 10)
    assert k is None and "only one category" in note
    assert aha.kappa([])[0] is None


def test_kappa_is_zero_for_chance_level_agreement():
    pairs = [("yes", "yes"), ("yes", "no"), ("no", "yes"), ("no", "no")]
    k, note = aha.kappa(pairs)
    assert note == "ok" and abs(k) < 1e-9


def test_confusion_matrix_counts_both_directions():
    cats, m = aha.confusion([("yes", "no"), ("yes", "no"), ("no", "no")])
    assert cats == ["no", "yes"] and m["yes"]["no"] == 2 and m["no"]["no"] == 1


def test_binary_scores_report_undefined_instead_of_zero():
    s = aha.binary_scores([("no", "no"), ("yes", "no")], "yes")
    assert s["precision"] is None and s["recall"] == 0.0
    assert aha.binary_scores([("no", "no")], "yes")["note"].startswith("'yes' never appears")


# ---- validation ----
def test_invalid_and_missing_values_are_reported_not_corrected(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {"h_action_requirement": "MAYBE"}, {"h_confidence": ""}])
    b = sheet(tmp_path / "b.csv", [{}, {}, {}])
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "out")
    assert r.returncode == 0, r.stderr
    assert "INVALID FIXTURE-02 h_action_requirement='MAYBE'" in r.stdout
    assert "MISSING FIXTURE-03 h_confidence" in r.stdout
    summary = json.loads((tmp_path / "out/reviewer_agreement.json").read_text())
    inv = [v for v in summary["validation"] if v["reviewer"] == "A"][0]
    assert inv["invalid"][0]["value"] == "MAYBE" and inv["missing"][0]["field"] == "h_confidence"


def test_mismatched_episode_ids_are_rejected(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {}])
    b = sheet(tmp_path / "b.csv", [{}])
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "out")
    assert r.returncode == 2 and "episode ids differ" in r.stderr


def test_duplicate_episode_ids_are_rejected(tmp_path):
    a = tmp_path / "a.csv"
    sheet(a, [{}, {}])
    rows = a.read_text().splitlines()
    a.write_text("\n".join(rows + [rows[-1]]) + "\n")      # repeat the last id
    b = sheet(tmp_path / "b.csv", [{}, {}])
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "out")
    assert r.returncode == 2 and "duplicate annotation_id" in r.stderr


def test_comment_row_is_skipped(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {}])
    b = sheet(tmp_path / "b.csv", [{}, {}])
    sheet_a, problems = aha.read_sheet(a)
    assert problems == [] and set(sheet_a) == {"FIXTURE-01", "FIXTURE-02"}
    assert run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "o").returncode == 0


# ---- stage 2 outputs ----
def test_disagreements_and_adjudication_template(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {"h_action_requirement": "NOT_REQUIRED",
                                        "h_missed_required_action": "n/a"}])
    b = sheet(tmp_path / "b.csv", [{}, {"h_action_requirement": "UNDETERMINED",
                                        "h_missed_required_action": "n/a"}])
    out = tmp_path / "out"
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", out)
    assert r.returncode == 0
    dis = list(csv.DictReader(open(out / "disagreements.csv")))
    assert len(dis) == 1
    # the system and prompt stay hidden from the adjudicator; they are joined in stage 3
    assert dis[0] == {"annotation_id": "FIXTURE-02", "field": "h_action_requirement",
                      "reviewer_a": "NOT_REQUIRED", "reviewer_b": "UNDETERMINED", "task": "task9"}
    adj = list(csv.reader(open(out / "adjudication_template.csv")))
    assert adj[0] == ["annotation_id", "field", "reviewer_a", "reviewer_b",
                      "final_adjudicated_judgement", "adjudicator_rationale", "resolution_category"]
    assert adj[1][-1] == "|".join(aha.RESOLUTION_CATEGORIES)
    assert adj[2][:4] == ["FIXTURE-02", "h_action_requirement", "NOT_REQUIRED", "UNDETERMINED"]
    assert adj[2][4:] == ["", "", ""], "adjudication must not be pre-filled"


def test_agreement_is_reported_per_field_with_no_pooled_kappa(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {"h_action_requirement": "NOT_REQUIRED"}])
    b = sheet(tmp_path / "b.csv", [{}, {"h_action_requirement": "UNDETERMINED"}])
    out = tmp_path / "out"
    run("--reviewer-a", a, "--reviewer-b", b, "--out", out)
    s = json.loads((out / "reviewer_agreement.json").read_text())
    assert {f["field"] for f in s["fields"]} == set(aha.ALLOWED) - {"h_confidence", "h_flag_for_clinician"}
    assert "overall_kappa" not in s and all("group" in f for f in s["fields"])
    ar = [f for f in s["fields"] if f["field"] == "h_action_requirement"][0]
    assert ar["n_compared"] == 2 and ar["n_disagreements"] == 1 and ar["raw_agreement"] == 0.5


# ---- the key stays sealed in stage 2 ----
def test_stage_two_never_reads_the_evaluator_key(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}])
    b = sheet(tmp_path / "b.csv", [{}])
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "out",
            "--key", tmp_path / "definitely-absent-key.csv")
    assert r.returncode == 0 and "STAGE 3" not in r.stdout


def test_compare_requires_an_adjudicated_file(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}])
    b = sheet(tmp_path / "b.csv", [{}])
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "out", "--compare-evaluator")
    assert r.returncode == 2 and "requires --adjudicated" in r.stderr


def test_compare_refuses_while_annotations_are_incomplete(tmp_path):
    a = sheet(tmp_path / "a.csv", [{"h_confidence": ""}])
    b = sheet(tmp_path / "b.csv", [{}])
    adj = tmp_path / "adj.csv"
    adj.write_text("annotation_id,field,reviewer_a,reviewer_b,final_adjudicated_judgement,"
                   "adjudicator_rationale,resolution_category\n")
    key = tmp_path / "key.csv"
    key.write_text("annotation_id\nFIXTURE-01\n")
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", tmp_path / "out",
            "--compare-evaluator", "--adjudicated", adj, "--key", key)
    assert r.returncode == 2 and "before comparing with the evaluator" in r.stderr


# ---- stage 3, against a fixture key (never the study's sealed key) ----
def fixture_key(path):
    cols = ["annotation_id", "episode_id", "task", "case_id", "model", "prompt", "repeat",
            "stratum_used_for_sampling", "eval_action_requirement_status", "eval_required_actions",
            "eval_attempted_actions", "eval_missed_required_actions", "eval_unnecessary_actions",
            "eval_process_result", "eval_grounding_result", "eval_verified_outcome",
            "benchmark_terminal_result", "manifest_order_required", "manifest_case_is_synthetic"]
    rows = [
        {"annotation_id": "FIXTURE-01", "episode_id": "task9_1#1", "task": "task9",
         "model": "fixture-model", "prompt": "cond", "repeat": "t0",
         "eval_action_requirement_status": "REQUIRED",
         "eval_required_actions": "medicationrequest.create|servicerequest.create",
         "eval_attempted_actions": "", "eval_missed_required_actions":
         "medicationrequest.create|servicerequest.create", "eval_unnecessary_actions": "",
         "eval_process_result": "SAFE_FAILURE", "eval_grounding_result": "GROUNDED",
         "benchmark_terminal_result": "FAIL"},
        {"annotation_id": "FIXTURE-02", "episode_id": "task9_2#2", "task": "task9",
         "model": "fixture-model", "prompt": "cond", "repeat": "t0",
         "eval_action_requirement_status": "NOT_REQUIRED", "eval_required_actions": "",
         "eval_attempted_actions": "medicationrequest.create", "eval_missed_required_actions": "",
         "eval_unnecessary_actions": "medicationrequest.create",
         "eval_process_result": "SAFE_FAILURE", "eval_grounding_result": "UNGROUNDED",
         "benchmark_terminal_result": "FAIL"},
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return path


def test_stage_three_compares_evaluator_with_adjudicated_labels(tmp_path):
    # FIXTURE-01: reviewers agree with the evaluator. FIXTURE-02: they disagree and the
    # adjudicator sides with the humans, so the evaluator must be scored as wrong there.
    a = sheet(tmp_path / "a.csv", [{}, {"h_action_requirement": "UNDETERMINED",
                                        "h_missed_required_action": "n/a",
                                        "h_unnecessary_action": "n/a",
                                        "h_medicationrequest_attempted": "yes",
                                        "h_final_claims_grounded": "ungrounded"}])
    b = sheet(tmp_path / "b.csv", [{}, {"h_action_requirement": "NOT_REQUIRED",
                                        "h_missed_required_action": "n/a",
                                        "h_unnecessary_action": "yes",
                                        "h_medicationrequest_attempted": "yes",
                                        "h_final_claims_grounded": "ungrounded"}])
    adj = tmp_path / "adj.csv"
    with open(adj, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["annotation_id", "field", "reviewer_a", "reviewer_b",
                    "final_adjudicated_judgement", "adjudicator_rationale", "resolution_category"])
        w.writerow(["FIXTURE-02", "h_action_requirement", "UNDETERMINED", "NOT_REQUIRED",
                    "UNDETERMINED", "fixture rationale", "Evaluator logic bug"])
        w.writerow(["FIXTURE-02", "h_unnecessary_action", "n/a", "yes", "n/a",
                    "fixture rationale", "Human annotation error"])
    scored = tmp_path / "scored/cond/fixture-model-ctx8k_task9"
    scored.mkdir(parents=True)
    (scored / "episodes.jsonl").write_text("\n".join(json.dumps({
        "episode_id": eid, "complete_trace": True, "turns": [{"labels": labels}]})
        for eid, labels in (("task9_1#1", []), ("task9_2#2", ["PREMATURE_ACTION", "UNSAFE_ACTION"]))))
    out = tmp_path / "out"
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", out, "--compare-evaluator",
            "--adjudicated", adj, "--key", fixture_key(tmp_path / "key.csv"), "--scored",
            tmp_path / "scored")
    assert r.returncode == 0, r.stderr
    assert "STAGE 3: opening the evaluator key" in r.stdout
    rep = json.loads((out / "evaluator_vs_human.json").read_text())
    by = {f["field"]: f for f in rep["fields"]}
    assert by["h_action_requirement"]["n_compared"] == 2
    assert by["h_action_requirement"]["exact_agreement"] == 0.5          # evaluator wrong on FIXTURE-02
    assert by["h_action_requirement"]["confusion_human_rows_evaluator_cols"]["UNDETERMINED"]["NOT_REQUIRED"] == 1
    # Cascades from the status disagreement on FIXTURE-02: the adjudicated status is UNDETERMINED
    # (guide rule 4 -> "n/a") while the evaluator says NOT_REQUIRED (rule 3 -> "no").
    assert by["h_missed_required_action"]["exact_agreement"] == 0.5
    # FIXTURE-01 agrees (no / no); FIXTURE-02 does not (adjudicated "n/a" vs the evaluator's "yes")
    assert by["h_unnecessary_action"]["exact_agreement"] == 0.5
    assert by["h_premature_action"]["n_compared"] == 2                   # came from --scored
    assert rep["resolution_categories"] == {"Evaluator logic bug": 1, "Human annotation error": 1}
    assert rep["adjudicated_entries"] == 2
    assert rep["by_task"]["task9"] and rep["by_action"]["medicationrequest.create"]["n"] == 2
    assert "clinical validation" in r.stdout


def test_turn_level_fields_are_flagged_not_comparable_without_scored(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {"h_action_requirement": "NOT_REQUIRED",
                                        "h_missed_required_action": "n/a"}])
    b = sheet(tmp_path / "b.csv", [{}, {"h_action_requirement": "NOT_REQUIRED",
                                        "h_missed_required_action": "n/a"}])
    adj = tmp_path / "adj.csv"
    adj.write_text("annotation_id,field,reviewer_a,reviewer_b,final_adjudicated_judgement,"
                   "adjudicator_rationale,resolution_category\n")
    out = tmp_path / "out"
    r = run("--reviewer-a", a, "--reviewer-b", b, "--out", out, "--compare-evaluator",
            "--adjudicated", adj, "--key", fixture_key(tmp_path / "key.csv"))
    assert r.returncode == 0
    rep = json.loads((out / "evaluator_vs_human.json").read_text())
    note = [f for f in rep["fields"] if f["field"] == "h_premature_action"][0]
    assert note["n_compared"] == 0 and "not comparable without --scored" in note["note"]


# ---- package QA mode ----
def test_qa_mode_passes_on_the_real_package():
    qa = aha.qa_package(ROOT / "docs/annotation_sample_v1")
    assert qa["passed"], [c for c in qa["checks"] if not c["ok"]]
    # Either the key is still sealed in the package (header + 30 rows, counted without reading
    # values) or it has been moved out of the shared tree, which is the workflow's end state.
    assert qa["key"]["lines"] >= 31 if qa["key"]["in_package"] else not qa["key"]["in_package"]


def test_qa_mode_accepts_a_package_whose_key_was_moved_out(tmp_path):
    src = ROOT / "docs/annotation_sample_v1"
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    for name in ("packet.md", "annotation_sheet_reviewer_A.csv", "annotation_sheet_reviewer_B.csv"):
        (pkg / name).write_bytes((src / name).read_bytes())
    qa = aha.qa_package(pkg)
    assert qa["passed"] and qa["key"]["in_package"] is False


def test_qa_mode_detects_a_leaked_label_and_prefilled_judgement(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    src = ROOT / "docs/annotation_sample_v1"
    (pkg / "packet.md").write_text(src.joinpath("packet.md").read_text()
                                   + "\n## leak\nprocess = APPROPRIATE_DEFER\n")
    for reviewer in ("A", "B"):
        rows = list(csv.DictReader(open(src / f"annotation_sheet_reviewer_{reviewer}.csv")))
        rows[0]["h_action_requirement"] = "REQUIRED"      # simulate a pre-filled judgement
        with open(pkg / f"annotation_sheet_reviewer_{reviewer}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    (pkg / aha.KEY_FILENAME).write_text("annotation_id\n")
    qa = aha.qa_package(pkg)
    failed = {c["check"] for c in qa["checks"] if not c["ok"]}
    assert not qa["passed"]
    assert "packet contains no evaluator label or status name" in failed
    assert "no judgement is pre-filled in either sheet (nothing fabricated)" in failed


# ---- blinding leak detection (reviewer-facing materials) ----
CLINICAL_TEXT = ("Check patient S0000000's last serum magnesium level within last 24 hours. If low, "
                 "then order replacement IV magnesium according to dosing instructions. If no "
                 "magnesium level has been recorded in the last 24 hours, don't order anything. "
                 "An order is required only when the value is low; otherwise it is not required.")


def test_leak_scan_ignores_ordinary_clinical_language():
    assert aha.scan_leaks(CLINICAL_TEXT) == []


def test_leak_scan_ignores_the_reviewers_own_annotation_columns():
    header = ",".join(["annotation_id", "h_missed_required_action", "h_unnecessary_action",
                       "h_action_requirement", "h_premature_action", "h_unsafe_action"])
    assert aha.scan_leaks(header) == []


def test_leak_scan_catches_model_and_prompt_identifiers():
    for text, needle in (("Model: llama3.2-1b", "llama"), ("agent qwen2.5-1.5b-ctx8k", "qwen"),
                         ("prompt fewshot3", "fewshot"), ("v4-decision-step", "decision-step"),
                         ("runs/2026-11-16_slm-heldout_n20", "heldout")):
        hits = aha.scan_leaks(text)
        assert any(needle in h for h in hits), (text, hits)


def test_leak_scan_catches_evaluator_status_tokens_and_metadata():
    for text, needle in (("process = APPROPRIATE_DEFER", "APPROPRIATE_DEFER"),
                         ("status: NOT_REQUIRED", "NOT_REQUIRED"),
                         ("status: UNDETERMINED", "UNDETERMINED"),
                         ("REQUIRED", "REQUIRED"),
                         ("MISSED_REQUIRED_ACTION", "MISSED_REQUIRED_ACTION"),
                         ("UNNECESSARY_ACTION", "UNNECESSARY_ACTION"),
                         ("verified_outcome = VERIFIED_PASS", "VERIFIED_PASS"),
                         ("stratum_used_for_sampling", "stratum"),
                         ("eval_action_requirement_status", "eval_")):
        hits = aha.scan_leaks(text)
        assert any(needle in h for h in hits), (text, hits)


def test_status_token_check_is_case_sensitive():
    assert aha.scan_leaks("the order was not required and the value is undetermined") == []


def blinded_dir(tmp_path, name="pkg", episodes=("ANN-01",), extra_packet="",
                sheet_overrides=None, columns=None):
    d = tmp_path / name
    d.mkdir()
    body = "\n".join(f"## {e}\n\n- Task type: **task9**\n\n```\n{CLINICAL_TEXT}\n```\n" for e in episodes)
    (d / "packet.md").write_text("# packet\n\n" + body + extra_packet)
    for reviewer in ("A", "B"):
        with open(d / f"annotation_sheet_reviewer_{reviewer}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=columns or BLINDED_COLUMNS)
            w.writeheader()
            for e in episodes:
                row = {"annotation_id": e, "task": "task9"}
                row.update(sheet_overrides or {})
                w.writerow(row)
    return d


def test_qa_blinded_passes_on_clean_material(tmp_path):
    qa = aha.qa_blinded([blinded_dir(tmp_path)])
    assert qa["passed"], [c for c in qa["checks"] if not c["ok"]]


def test_qa_blinded_detects_a_leaked_identifier(tmp_path):
    d = blinded_dir(tmp_path, extra_packet="\n- Model: **qwen2.5-1.5b**\n")
    qa = aha.qa_blinded([d])
    assert not qa["passed"]
    assert any("identifier" in c["detail"] for c in qa["checks"] if not c["ok"])


def test_qa_blinded_detects_the_key_or_map_in_the_reviewer_folder(tmp_path):
    d = blinded_dir(tmp_path)
    (d / aha.KEY_FILENAME).write_text("annotation_id\n")
    qa = aha.qa_blinded([d])
    failed = [c for c in qa["checks"] if not c["ok"]]
    assert any("no evaluator key and no blinding map" in c["check"] for c in failed)


def test_qa_blinded_rejects_a_system_column_even_with_an_anonymous_value(tmp_path):
    d = blinded_dir(tmp_path, columns=COLUMNS, sheet_overrides={"model": "SYS-1",
                                                                "prompt_condition": "CND-1"})
    qa = aha.qa_blinded([d])
    failed = {c["check"] for c in qa["checks"] if not c["ok"]}
    assert any("no system/configuration/run column" in c for c in failed)
    assert any("no grouping identifier" in c for c in failed)


def test_grouping_identifiers_are_a_leak(tmp_path):
    for text in ("- System: **SYS-2**", "configuration: **CND-1**", "run: **RUN-07**"):
        hits = aha.scan_leaks(text)
        assert any("grouping identifier" in h for h in hits), text
    # ordinary words must not trip it
    assert aha.scan_leaks("the system returned a Bundle; this run of tests") == []


def test_qa_blinded_detects_a_grouping_id_left_in_the_packet(tmp_path):
    d = blinded_dir(tmp_path, extra_packet="\n- System: **SYS-1**, configuration: **CND-2**\n")
    qa = aha.qa_blinded([d])
    failed = {c["check"] for c in qa["checks"] if not c["ok"]}
    assert any("no grouping identifier" in c for c in failed)


def test_stage_three_can_join_the_hidden_mapping(tmp_path):
    a = sheet(tmp_path / "a.csv", [{}, {"h_action_requirement": "NOT_REQUIRED"}])
    b = sheet(tmp_path / "b.csv", [{}, {"h_action_requirement": "UNDETERMINED"}])
    sheets = {"A": aha.read_sheet(a)[0], "B": aha.read_sheet(b)[0]}
    mapping = tmp_path / "map.csv"
    with open(mapping, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["annotation_id", "case_id", "model", "prompt_condition",
                                          "sampling"])
        w.writeheader()
        w.writerow({"annotation_id": "FIXTURE-02", "case_id": "task9_9", "model": "fixture-model",
                    "prompt_condition": "fixture-prompt", "sampling": "t0"})
    out = tmp_path / "out"
    out.mkdir()
    j = aha.join_mapping(mapping, sheets, ["FIXTURE-01", "FIXTURE-02"], out)
    assert j["rows"] == 1 and j["disagreements_by_model"] == {"fixture-model": 1}
    joined = list(csv.DictReader(open(out / "disagreements_with_mapping.csv")))
    assert joined[0]["model"] == "fixture-model" and joined[0]["case_id"] == "task9_9"


def test_qa_blinded_detects_an_episode_id_shared_with_the_calibration_packet(tmp_path):
    a = blinded_dir(tmp_path, name="sample", episodes=("ANN-01", "ANN-02"))
    b = blinded_dir(tmp_path, name="calib", episodes=("ANN-02",))
    qa = aha.qa_blinded([a, b])
    failed = {c["check"] for c in qa["checks"] if not c["ok"]}
    assert "calibration and sample packets share no episode id" in failed


def test_qa_blinded_on_the_real_materials_is_clean_apart_from_added_files():
    """The distribution files must stay clean. After the annotation round the folders also hold
    completed sheets, which is reported by the 'holds only the files a reviewer should receive'
    check rather than scanned as if they were distribution material."""
    qa = aha.qa_blinded([ROOT / "docs/annotation_sample_v1_blinded",
                         ROOT / "docs/annotation_calibration_v1_blinded"],
                        ROOT / "docs/annotation_sample_v1/blinding_map_do_not_share.csv",
                        ROOT / "docs/annotation_calibration_v1_map_do_not_share.csv")
    failed = [c["check"] for c in qa["checks"] if not c["ok"]]
    assert all("holds only the files a reviewer should receive" in c for c in failed), failed
    # The hidden mappings are moved out of the shared tree before distribution. When they are
    # still present the case/patient separation is re-verified; when not, it is reported as
    # skipped rather than silently dropped.
    if "calibration_sources" in qa:
        assert len(qa["calibration_sources"]) == 3
    else:
        assert any("moved out of the shared tree" in n for n in qa["skipped"])


def test_calibration_case_overlap_is_detected(tmp_path):
    a = blinded_dir(tmp_path, name="sample", episodes=("ANN-01",))
    b = blinded_dir(tmp_path, name="calib", episodes=("CAL-1",))
    smap, cmap = tmp_path / "s.csv", tmp_path / "c.csv"
    for path, rows in ((smap, [{"annotation_id": "ANN-01", "case_id": "task9_3"}]),
                       (cmap, [{"annotation_id": "CAL-1", "case_id": "task9_3", "mrn": "S1",
                                "source": "runs/x/y/z:242"}])):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    qa = aha.qa_blinded([a, b], smap, cmap)
    failed = {c["check"] for c in qa["checks"] if not c["ok"]}
    assert "calibration cases do not appear in the 30-episode sample" in failed
