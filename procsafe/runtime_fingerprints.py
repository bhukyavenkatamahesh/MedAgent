"""Launch-time fingerprints for the model runtime and the harness prompt (D4 items 2 and 3).

Kept separate from `provenance.py` so the manifest layer stays free of runtime dependencies. Both
functions record only what they can read and say so plainly when they cannot; neither guesses.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Optional

FEWSHOT_CONSTANTS = {"1": "FEWSHOT_BLOCK", "2": "FEWSHOT_BLOCK_V2",
                     "3": "FEWSHOT_BLOCK_V3", "4": "FEWSHOT_BLOCK_V4"}


def ollama_model_fingerprint(model: str, base: str = "http://localhost:11434") -> dict:
    """Model digest and quantization from the live runtime.

    A tag such as `qwen2.5:1.5b-instruct` is mutable; the digest is not. D4 item 2 asks for the
    digest "not the tag", so a run whose digest is absent must say the field is unavailable rather
    than fall back to the tag.
    """
    out = {"name": model, "digest": None, "quantization": None, "parameter_size": None,
           "family": None, "runtime": "ollama", "runtime_version": None, "source": "unavailable"}
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=20) as r:
            out["runtime_version"] = json.loads(r.read().decode()).get("version")
    except Exception:
        pass
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=30) as r:
            for m in json.loads(r.read().decode()).get("models", []):
                if model in (m.get("name"), m.get("model")):
                    det = m.get("details") or {}
                    out.update({"name": m.get("name"), "digest": m.get("digest"),
                                "quantization": det.get("quantization_level"),
                                "parameter_size": det.get("parameter_size"),
                                "family": det.get("family"),
                                "source": "ollama /api/tags, read at launch"})
                    break
            else:
                out["source"] = "model not installed in this runtime"
    except Exception as exc:
        out["source"] = f"unavailable: {exc}"
    return out


def _triple_quoted(text: str, const: str) -> Optional[str]:
    """The body of `CONST = \"\"\"...\"\"\"` (or single-quoted form), without a regex."""
    for opener in ('"""', "'''"):
        marker = const + " = " + opener
        i = text.find(marker)
        if i < 0:
            marker = const + "=" + opener
            i = text.find(marker)
        if i < 0:
            continue
        start = i + len(marker)
        end = text.find(opener, start)
        if end > start:
            return text[start:end]
    return None


def harness_prompt_fingerprint(mab_root: str | Path, fewshot: Optional[str] = None) -> dict:
    """Hash the actual prompt template the harness will send.

    The template and the few-shot blocks live in the task worker and are chosen by the `FEWSHOT`
    environment variable, which is why the historical runs stored no prompt hash. Reading the real
    source makes `prompt.sha256` a fact rather than a label.
    """
    src = Path(mab_root) / "src/server/tasks/medagentbench/__init__.py"
    version = f"fewshot{fewshot}" if fewshot else "base"
    if not src.is_file():
        return {"version": version, "sha256": None, "source": f"not found: {src}"}
    text = src.read_text()
    parts = {"worker_module_sha256": hashlib.sha256(text.encode()).hexdigest()}
    template = _triple_quoted(text, "MedAgentBench_prompt")
    parts["prompt_template_sha256"] = (hashlib.sha256(template.encode()).hexdigest()
                                       if template else None)
    const = FEWSHOT_CONSTANTS.get(str(fewshot or ""))
    if const:
        block = _triple_quoted(text, const)
        parts["fewshot_constant"] = const
        parts["fewshot_block_sha256"] = (hashlib.sha256(block.encode()).hexdigest()
                                         if block else None)
    combined = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return {"version": version, "sha256": combined, "components": parts, "source": str(src),
            "note": ("Hashes the template and the selected few-shot block as the worker defines "
                     "them. The rendered per-case prompt also contains the case's own instruction "
                     "and context, which the case table already pins.")}
