"""Adapter for MedAgentBench (stanfordmlgroup/MedAgentBench) run logs.

MedAgentBench writes one JSON line per task to
    outputs/<run>/<agent>/medagentbench-std/runs.jsonl
with shape {"index", "output": {"status", "result", "history": [{"role","content"}, ...]}}.

History alternates: user prompt -> agent action -> user (env response) -> agent ...
  agent:  "GET http://localhost:8080/fhir/Observation?patient=S123&code=K"
  agent:  "POST http://localhost:8080/fhir/MedicationRequest\n{...json...}"
  agent:  "FINISH([...])"
  env after GET:  "Here is the response from the GET request:\n{python-dict repr}. Please call FINISH ..."

Terminal correctness is normally supplied separately via `terminal_results`
(index -> "PASS"/"FAIL"). Explicit logged Correct/Incorrect statuses are also
accepted; completion status alone never supplies a terminal outcome. Verify the
log schema against the benchmark version before using this adapter in a pilot.
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ..schema import FINISH, GET, INVALID, POST, Episode, Turn

_GET_PREFIX = "Here is the response from the GET request:"
_NOW_RE = re.compile(r"It's (\S+) now")


def tool_name(method: str, url: str) -> str:
    """Map a FHIR URL to the MedAgentBench function name."""
    path = urlparse(url).path.rstrip("/").split("/")[-1]
    params = parse_qs(urlparse(url).query)
    if path == "Observation":
        cat = (params.get("category") or [""])[0]
        if method == GET:
            return "vital.search" if "vital" in cat else "lab.search"
        return "vital.create"
    base = {"Patient": "patient", "Condition": "condition", "MedicationRequest": "medicationrequest",
            "Procedure": "procedure", "ServiceRequest": "servicerequest"}.get(path, path.lower())
    return f"{base}.search" if method == GET else f"{base}.create"


def _parse_get_response(text: str) -> tuple[list[dict], Optional[str]]:
    if not isinstance(text, str):
        return [], "invalid_response_text"
    if not text.startswith(_GET_PREFIX):
        return [], text.strip()[:300] or "missing_response"  # error message from env
    body = text[len(_GET_PREFIX):].strip()
    body = body.split(". Please call FINISH")[0]
    data = None
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(body)
            break
        except (ValueError, SyntaxError, TypeError):
            continue
    if not isinstance(data, dict):
        return [], "unparseable_response"
    if data.get("resourceType") == "Bundle":
        entries = data.get("entry", [])
        if not isinstance(entries, list):
            return [], "malformed_bundle_entries"
        if any(not isinstance(e, dict) or "resource" not in e for e in entries):
            return [], "malformed_bundle_entry"
        resources = [entry["resource"] for entry in entries]
    else:
        resources = [data]
    # Do not turn a malformed or partially parsed response into an empty-success
    # retrieval, or quietly keep only its valid entries.
    if any(not _resource_shape_valid(resource) for resource in resources):
        return [], "malformed_response_resource"
    if any(resource["resourceType"] == "OperationOutcome" for resource in resources):
        return [], "operation_outcome_response"
    return resources, None


def _resource_shape_valid(resource: object) -> bool:
    """Validate the fields this adapter/evaluator reads, not the full FHIR spec."""
    if not isinstance(resource, dict):
        return False
    if not isinstance(resource.get("resourceType"), str) or not resource["resourceType"]:
        return False
    for field in ("id", "effectiveDateTime", "issued"):
        if field in resource and not isinstance(resource[field], str):
            return False
    for field in ("subject", "code", "valueQuantity"):
        if field in resource and not isinstance(resource[field], dict):
            return False
    subject = resource.get("subject", {})
    if "reference" in subject and not isinstance(subject["reference"], str):
        return False
    coding = resource.get("code", {}).get("coding", [])
    if not isinstance(coding, list):
        return False
    return all(isinstance(item, dict)
               and all(isinstance(item[key], str) for key in ("code", "system") if key in item)
               for item in coding)


def _terminal_status(status: str) -> Optional[str]:
    if status.endswith("Incorrect"):
        return "FAIL"
    if status.endswith("Correct"):
        return "PASS"
    return None


def _clean(content: str) -> str:
    return content.strip().replace("```tool_code", "").replace("```", "").strip()


def parse_history(history: list[dict], episode_id: str) -> list[Turn]:
    if not isinstance(history, list) or any(not isinstance(m, dict) or "role" not in m for m in history):
        raise ValueError("History must be a list of messages with explicit roles")
    turns: list[Turn] = []
    n = 0
    for i, msg in enumerate(history):
        if msg["role"] != "agent":
            continue
        n += 1
        if not isinstance(msg.get("content"), str):
            turns.append(Turn(episode_id, n, INVALID, "invalid", error="invalid_action_text"))
            continue
        r = _clean(msg["content"])
        nxt = history[i + 1].get("content", "") if i + 1 < len(history) and history[i + 1]["role"] == "user" else ""
        if r == GET or r.startswith("GET "):
            url = r[3:].strip()
            resources, err = _parse_get_response(nxt)
            turns.append(Turn(episode_id, n, GET, tool_name(GET, url), request=url,
                              response_resources=resources, error=err))
        elif r == POST or r.startswith("POST "):
            first, *rest = r.split("\n")
            url = first[4:].strip()
            try:
                payload, err = json.loads("\n".join(rest)), None
                if not isinstance(payload, dict):
                    payload, err = None, "invalid_post_payload"
            except (ValueError, TypeError):
                payload, err = None, "invalid_post_payload"
            # The attempted write remains visible even when its payload is
            # malformed; otherwise a guarded action could disappear from audit.
            turns.append(Turn(episode_id, n, POST,
                              tool_name(POST, url), request=url, payload=payload, error=err))
        elif r.startswith("FINISH(") and r.endswith(")"):
            turns.append(Turn(episode_id, n, FINISH, "finish", message=r[len("FINISH("):-1]))
        else:
            turns.append(Turn(episode_id, n, INVALID, "invalid", message=r[:300]))
    return turns


def load_runs(runs_jsonl: str | Path, tasks_json: str | Path,
              terminal_results: Optional[dict[int, str]] = None,
              task_prefixes: tuple[str, ...] = ("task5", "task9")) -> list[Episode]:
    """Load MedAgentBench runs for the selected task families."""
    tasks = json.loads(Path(tasks_json).read_text())
    episodes = []
    seen = set()
    for line in Path(runs_jsonl).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        idx = rec["index"]
        if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < len(tasks):
            raise ValueError("Run index must identify a task in the supplied task list")
        out = rec.get("output") or rec
        task = tasks[idx]
        if not task["id"].split("_")[0] in task_prefixes:
            continue
        if idx in seen:
            raise ValueError(f"Duplicate selected run index: {idx}")
        seen.add(idx)
        m = _NOW_RE.search(task.get("context", ""))
        now = datetime.fromisoformat(m.group(1).replace("Z", "+00:00")) if m else None
        status = str(out.get("status", ""))
        terminal = (terminal_results or {}).get(idx)
        if terminal is None:
            terminal = _terminal_status(status)
        elif terminal not in ("PASS", "FAIL"):
            raise ValueError(f"Run {idx}: terminal result must be PASS, FAIL, or absent")
        episode_id = f"{task['id']}#{idx}"
        episodes.append(Episode(
            episode_id=episode_id,
            task_id=task["id"],
            patient_id=task["eval_MRN"],
            reference_time=now,
            turns=parse_history(out.get("history") or [], episode_id),
            terminal_result=terminal,
            meta={"status": status, "instruction": task["instruction"]},
        ))
    return episodes


def load_overall_terminal(overall_json: str | Path) -> dict[int, str]:
    """Read PASS/FAIL per index from MedAgentBench overall.json raw_results (status ends with Correct/Incorrect)."""
    data = json.loads(Path(overall_json).read_text())
    raw = data.get("custom", data).get("raw_results", data.get("raw_results", []))
    res = {}
    for r in raw:
        st = str(r.get("status", ""))
        terminal = _terminal_status(st)
        if terminal is not None:
            if r["index"] in res:
                raise ValueError(f"Duplicate terminal result index: {r['index']}")
            res[r["index"]] = terminal
    return res
