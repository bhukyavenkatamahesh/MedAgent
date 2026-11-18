"""Measure whether the local model runtime actually honours a seed (D4 item 1).

A recorded seed is a REQUEST. This script turns "honoured" from an assumption into a measurement.

Method. The decisive detail is temperature. At temperature 0 decoding is greedy, so repeated calls
agree whether or not a seed is honoured - the test would pass vacuously and prove nothing. The check
therefore runs at a temperature where sampling is active:

  A. same prompt, same seed, twice   -> identical output expected if the seed is honoured
  B. same prompt, different seeds    -> different output expected if the seed actually drives sampling
  C. same prompt, no seed, twice     -> usually differs; shows A is not simply determinism

Both A and B must hold. A alone can be produced by a runtime that ignores the seed and is
deterministic anyway; B alone by a runtime whose sampling is unseeded noise.

Verdict: honoured / not honoured / inconclusive. It is scoped to the model, runtime build and host
measured, and says nothing about a different model or machine. Reproducing a FULL RUN needs more
than this: identical runtime build, hardware, concurrency and simulator state.

    python scripts/medomit_seed_check.py --model qwen2.5:1.5b-instruct --out outputs/seed_check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procsafe.provenance import derive_seed

PROMPT = ("You are a clinical assistant. In two sentences, describe what a magnesium blood test "
          "measures. Do not use lists.")


def chat(base: str, model: str, prompt: str, seed, temperature: float, num_ctx: int,
         keep_alive=None) -> str:
    options = {"temperature": temperature, "num_ctx": num_ctx}
    if seed is not None:
        options["seed"] = seed
    body = {"model": model, "stream": False, "options": options,
            "messages": [{"role": "user", "content": prompt}]}
    if keep_alive is not None:
        body["keep_alive"] = keep_alive
    req = urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())["message"]["content"]


def runtime_info(base: str) -> dict:
    out = {"host": platform.platform(), "python": platform.python_version()}
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=20) as r:
            out["runtime_version"] = json.loads(r.read().decode()).get("version")
    except Exception as exc:
        out["runtime_version"] = f"unavailable: {exc}"
    return out


def model_info(base: str, model: str) -> dict:
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=30) as r:
            for m in json.loads(r.read().decode()).get("models", []):
                if m.get("name") == model or m.get("model") == model:
                    det = m.get("details") or {}
                    return {"name": m.get("name"), "digest": m.get("digest"),
                            "quantization": det.get("quantization_level"),
                            "parameter_size": det.get("parameter_size"),
                            "family": det.get("family")}
    except Exception as exc:
        return {"name": model, "error": str(exc)}
    return {"name": model, "error": "not installed"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--base", default="http://localhost:11434")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--experiment-id", default="seed_check")
    ap.add_argument("--out")
    a = ap.parse_args()

    sha = lambda t: hashlib.sha256(t.encode()).hexdigest()
    seed_a = derive_seed(a.experiment_id, "case_A", 1)
    seed_b = derive_seed(a.experiment_id, "case_A", 2)

    runs = {
        "A_same_seed_1": chat(a.base, a.model, PROMPT, seed_a, a.temperature, a.num_ctx),
        "A_same_seed_2": chat(a.base, a.model, PROMPT, seed_a, a.temperature, a.num_ctx),
        "B_other_seed": chat(a.base, a.model, PROMPT, seed_b, a.temperature, a.num_ctx),
        "C_no_seed_1": chat(a.base, a.model, PROMPT, None, a.temperature, a.num_ctx),
        "C_no_seed_2": chat(a.base, a.model, PROMPT, None, a.temperature, a.num_ctx),
    }
    # D. Greedy decoding at temperature 0, three times. If the runtime ignores the seed, this is
    # the only reproducibility route left, and it is worth measuring rather than assuming.
    greedy = [chat(a.base, a.model, PROMPT, seed_a, 0.0, a.num_ctx) for _ in range(3)]
    greedy_identical = len(set(greedy)) == 1
    runs.update({f"D_greedy_{i+1}": g for i, g in enumerate(greedy)})

    # E. Cold start. The first generation after a model load is a DIFFERENT deterministic regime
    # from the warm one, at the identical seed. Measured, not assumed: see the report.
    import time as _time
    chat(a.base, a.model, PROMPT, seed_a, a.temperature, a.num_ctx, keep_alive=0)
    _time.sleep(3)
    cold = chat(a.base, a.model, PROMPT, seed_a, a.temperature, a.num_ctx)
    warm_after_cold = chat(a.base, a.model, PROMPT, seed_a, a.temperature, a.num_ctx)
    cold_matches_warm = cold == warm_after_cold
    runs.update({"E_cold": cold, "E_warm_after_cold": warm_after_cold})

    same_seed_identical = runs["A_same_seed_1"] == runs["A_same_seed_2"]
    seed_changes_output = runs["A_same_seed_1"] != runs["B_other_seed"]
    unseeded_identical = runs["C_no_seed_1"] == runs["C_no_seed_2"]

    if same_seed_identical and seed_changes_output:
        verdict, why = "honoured", ("the same seed reproduced the output exactly and a different "
                                    "seed changed it, at a temperature where sampling is active")
    elif not same_seed_identical:
        verdict, why = "not honoured", "the same seed did not reproduce the same output"
    else:
        verdict, why = "inconclusive", ("the same seed reproduced the output, but a different seed "
                                        "did not change it, so the seed may simply be ignored by a "
                                        "runtime that is deterministic at this temperature")

    result = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "temperature": a.temperature, "num_ctx": a.num_ctx,
        "note": ("Temperature must be > 0 or the test is vacuous: greedy decoding repeats itself "
                 "whether or not the seed is honoured."),
        "model": model_info(a.base, a.model), "runtime": runtime_info(a.base),
        "seeds": {"A": seed_a, "B": seed_b},
        "output_sha256": {k: sha(v) for k, v in runs.items()},
        "same_seed_identical": same_seed_identical,
        "different_seed_changes_output": seed_changes_output,
        "unseeded_repeats_identical": unseeded_identical,
        "greedy_temperature_0_identical_3x": greedy_identical,
        "cold_start_matches_warm": cold_matches_warm,
        "cold_start_note": ("The FIRST generation after a model load does not match later ones at "
                            "the same seed, and both regimes are individually stable. A final run "
                            "must therefore warm the model before the measured episodes and record "
                            "per-episode whether it ran cold or warm; otherwise the first episode "
                            "of every run is not reproducible against the rest."),
        "greedy_note": ("If the seed is not honoured, temperature 0 is the only reproducibility "
                        "route available, and it is a property of greedy decoding rather than of "
                        "any recorded seed. It still does not pin hardware, runtime build, "
                        "concurrency or simulator state."),
        "seed_support": verdict, "reason": why,
        "scope": ("This verdict covers only this model, this runtime build and this host. It is NOT "
                  "a claim that a full run reproduces: that also requires identical runtime build, "
                  "hardware, concurrency and simulator state."),
        "full_run_reproducibility": "not demonstrated",
    }
    print(json.dumps({k: v for k, v in result.items() if k != "output_sha256"}, indent=1))
    if a.out:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        (out / f"seed_check_{a.model.replace(':', '-').replace('/', '-')}.json").write_text(
            json.dumps(result, indent=1) + "\n")
        for k, v in runs.items():
            (out / f"{k}.txt").write_text(v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
