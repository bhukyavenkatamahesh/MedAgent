"""Milestone 3 — provenance integration, seed derivation and delivery, simulator-state fingerprint.

Engineering tests only: no model inference, no network, development cases only.
"""
import json
from pathlib import Path

import pytest

from procsafe.fhir_state import observation_projection, state_fingerprint, verify_pristine
from procsafe.provenance import derive_seed
from procsafe.runtime_fingerprints import (_triple_quoted, harness_prompt_fingerprint,
                                           ollama_model_fingerprint)
from procsafe.seed_proxy import SeedProxy, case_key, case_label, case_text

REPO = Path(__file__).resolve().parents[1]
MAB = Path("/Users/venkatamahesh/Desktop/MedAgentBench/MedAgentBench")

PROMPT = ("You are an expert in using FHIR functions.\n"
          "Here is a list of functions...\n"
          "Context: Patient S0000000 example few-shot case\n"
          "Question: What is the most recent CBG of the patient S0000000?\n"
          "GET http://x/fhir/Observation?patient=S0000000\n"
          "Context: It's 2023-11-13T10:15:00+00:00 now. The code for CBG is \"GLU\"\n"
          "Question: What is the most recent CBG of the patient S2823623?")


# ---- case identity: the bug that made a per-case seed drift between turns ------------------------

def test_case_text_takes_the_last_markers_not_the_fewshot_example():
    context, question = case_text(PROMPT)
    assert "S2823623" in question
    assert "S0000000" not in question
    assert "code for CBG" in context


def test_case_label_reports_the_real_case_patient():
    assert case_label(PROMPT)["mrn"] == "S2823623"


def test_case_key_is_stable_across_turns_of_one_episode():
    """The proxy is sent the whole conversation. A later turn must not change the case key."""
    turn1 = PROMPT
    turn2 = PROMPT + "\nGET http://x/fhir/Observation?patient=S2823623&code=GLU"
    turn3 = turn2 + "\n{'resourceType': 'Bundle', 'entry': []}\nFINISH([95])"
    assert case_key(turn1) == case_key(turn2) == case_key(turn3)


def test_case_key_differs_between_cases():
    assert case_key(PROMPT) != case_key(PROMPT.replace("S2823623", "S3032536"))


def test_case_key_falls_back_to_the_whole_prompt_when_markers_are_absent():
    a, b = case_key("no markers here"), case_key("different text")
    assert a != b and len(a) == 16


# ---- seed derivation and delivery ---------------------------------------------------------------

def _proxy(tmp_path, experiment="exp", repeat=1, temperature=None):
    return SeedProxy("http://localhost:11434", experiment, repeat,
                     tmp_path / "seed.jsonl", temperature)


def test_the_same_case_gets_the_same_seed_on_every_turn(tmp_path):
    p = _proxy(tmp_path)
    body = {"model": "m", "messages": [{"role": "user", "content": PROMPT}]}
    later = {"model": "m", "messages": [{"role": "user", "content": PROMPT},
                                        {"role": "assistant", "content": "GET http://x"}]}
    assert p.transform(body)[1]["requested_seed"] == p.transform(later)[1]["requested_seed"]


def test_different_cases_get_different_seeds(tmp_path):
    p = _proxy(tmp_path)
    one = {"model": "m", "messages": [{"role": "user", "content": PROMPT}]}
    two = {"model": "m", "messages": [{"role": "user",
                                       "content": PROMPT.replace("S2823623", "S3032536")}]}
    assert p.transform(one)[1]["requested_seed"] != p.transform(two)[1]["requested_seed"]


def test_different_repeats_get_different_seeds(tmp_path):
    body = {"model": "m", "messages": [{"role": "user", "content": PROMPT}]}
    r1 = _proxy(tmp_path / "a", repeat=1).transform(body)[1]["requested_seed"]
    r2 = _proxy(tmp_path / "b", repeat=2).transform(body)[1]["requested_seed"]
    assert r1 != r2


def test_different_experiments_get_different_seeds(tmp_path):
    body = {"model": "m", "messages": [{"role": "user", "content": PROMPT}]}
    a = _proxy(tmp_path / "a", experiment="exp_a").transform(body)[1]["requested_seed"]
    b = _proxy(tmp_path / "b", experiment="exp_b").transform(body)[1]["requested_seed"]
    assert a != b


def test_the_seed_is_injected_into_the_runtime_options(tmp_path):
    p = _proxy(tmp_path)
    sent, record = p.transform({"model": "m", "options": {"num_ctx": 8192},
                                "messages": [{"role": "user", "content": PROMPT}]})
    assert sent["options"]["seed"] == record["requested_seed"]
    assert sent["options"]["num_ctx"] == 8192, "the caller's own options survive"


def test_the_proxy_does_not_alter_anything_else(tmp_path):
    p = _proxy(tmp_path)
    body = {"model": "m", "stream": False, "keep_alive": "5m",
            "messages": [{"role": "user", "content": PROMPT}]}
    sent, _ = p.transform(body)
    assert sent["model"] == "m" and sent["stream"] is False and sent["keep_alive"] == "5m"
    assert sent["messages"] == body["messages"]
    assert body.get("options") is None, "the caller's body must not be mutated in place"


def test_temperature_is_overridden_only_when_asked(tmp_path):
    body = {"model": "m", "options": {"temperature": 0},
            "messages": [{"role": "user", "content": PROMPT}]}
    assert _proxy(tmp_path / "a").transform(body)[1]["options_sent"]["temperature"] == 0
    assert _proxy(tmp_path / "b", temperature=0.7).transform(body)[1]["options_sent"]["temperature"] == 0.7


def test_the_proxy_logs_what_it_requested(tmp_path):
    p = _proxy(tmp_path)
    _, record = p.transform({"model": "m", "messages": [{"role": "user", "content": PROMPT}]})
    p.note(record)
    rows = [json.loads(l) for l in (tmp_path / "seed.jsonl").read_text().splitlines()]
    assert rows[0]["requested_seed"] == record["requested_seed"]
    assert rows[0]["mrn"] == "S2823623"


def test_a_logged_seed_is_a_request_not_a_guarantee(tmp_path):
    """The proxy records a REQUEST. Honouring is measured by medomit_seed_check.py, not assumed."""
    _, record = _proxy(tmp_path).transform({"model": "m",
                                            "messages": [{"role": "user", "content": PROMPT}]})
    assert "requested_seed" in record
    assert not any(k in record for k in ("honoured", "deterministic", "reproducible"))


# ---- simulator-state fingerprint ----------------------------------------------------------------

def test_fingerprint_scope_is_part_of_the_record():
    """Two fingerprints are comparable only over the same scope, so the scope is hashed too."""
    import procsafe.fhir_state as fs
    calls = []

    def fake(base, patient, code):
        calls.append((patient, code))
        return [["2023-11-13T08:00:00+00:00", 1.8, "mg/dL", [["http://loinc.org", code]]]]

    orig_proj, orig_counts = fs.observation_projection, fs.write_counts
    fs.observation_projection = fake
    fs.write_counts = lambda base, patients: {"MedicationRequest": {p: 0 for p in patients}}
    try:
        a = fs.state_fingerprint("x", ["S1", "S2"], ["MG"])
        b = fs.state_fingerprint("x", ["S1"], ["MG"])
        assert a["scope_sha256"] != b["scope_sha256"]
        assert a["fingerprint"] != b["fingerprint"]
        c = fs.state_fingerprint("x", ["S2", "S1"], ["MG"])
        assert c["fingerprint"] == a["fingerprint"], "patient order must not matter"
    finally:
        fs.observation_projection, fs.write_counts = orig_proj, orig_counts


def test_verify_pristine_reports_rather_than_repairs():
    base = {"scope_sha256": "s", "fingerprint": "f", "observations_sha256": "o",
            "writes_sha256": "w"}
    assert verify_pristine(base, base)["status"] == "matches_baseline"
    assert verify_pristine(base, None)["status"] == "no_baseline"
    other_scope = {**base, "scope_sha256": "other"}
    assert verify_pristine(other_scope, base)["status"] == "incomparable"
    mutated = {**base, "fingerprint": "f2", "writes_sha256": "w2"}
    out = verify_pristine(mutated, base)
    assert out["status"] == "differs_from_baseline"
    assert "writes_sha256" in out["changed"]


def test_an_image_digest_is_not_a_state_fingerprint():
    """Documented explicitly, because conflating them is the mistake this module exists to prevent."""
    import procsafe.fhir_state as fs
    assert "image digest pins the software, not the record" in fs.__doc__.replace("\n", " ") or \
           "not the *record*" in fs.__doc__


# ---- launch-time fingerprints --------------------------------------------------------------------

def test_triple_quoted_extraction():
    text = 'A = """hello"""\nB = \'\'\'world\'\'\'\n'
    assert _triple_quoted(text, "A") == "hello"
    assert _triple_quoted(text, "B") == "world"
    assert _triple_quoted(text, "C") is None


def test_model_fingerprint_reports_unavailability_instead_of_guessing():
    out = ollama_model_fingerprint("definitely-not-installed:0b", base="http://localhost:1")
    assert out["digest"] is None
    assert out["source"].startswith("unavailable") or "not installed" in out["source"]
    assert out["name"] == "definitely-not-installed:0b"


def test_model_fingerprint_never_substitutes_the_tag_for_the_digest():
    out = ollama_model_fingerprint("x:1b", base="http://localhost:1")
    assert out["digest"] != out["name"]


@pytest.mark.skipif(not MAB.is_dir(), reason="benchmark clone not present")
def test_prompt_fingerprint_differs_between_fewshot_versions():
    seen = {harness_prompt_fingerprint(MAB, fs)["sha256"] for fs in ("1", "2", "3", "4", None)}
    assert len(seen) == 5, "each prompt version must hash differently"


@pytest.mark.skipif(not MAB.is_dir(), reason="benchmark clone not present")
def test_prompt_fingerprint_is_stable():
    a = harness_prompt_fingerprint(MAB, "4")
    b = harness_prompt_fingerprint(MAB, "4")
    assert a["sha256"] == b["sha256"] and len(a["sha256"]) == 64
    assert a["components"]["prompt_template_sha256"]
    assert a["components"]["fewshot_block_sha256"]


def test_prompt_fingerprint_handles_a_missing_clone(tmp_path):
    out = harness_prompt_fingerprint(tmp_path, "4")
    assert out["sha256"] is None and "not found" in out["source"]
