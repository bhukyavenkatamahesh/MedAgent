"""Adapter for MedAgentBench (stanfordmlgroup/MedAgentBench) run logs.

MedAgentBench writes one JSON line per task to
    outputs/<run>/<agent>/medagentbench-std/runs.jsonl
with shape {"index", "output": {"status", "result", "history": [{"role","content"}, ...]}}.

History alternates: user prompt -> agent action -> user (env response) -> agent ...
  agent:  "GET http://localhost:8080/fhir/Observation?patient=S123&code=K"
  agent:  "POST http://localhost:8080/fhir/MedicationRequest\n{...json...}"
  agent:  "FINISH([...])"
  env after GET:  "Here is the response from the GET request:\n{python-dict repr}. Please call FINISH ..."

Terminal correctness is NOT in runs.jsonl; it is computed by refsol.py in
calculate_overall(). Pass it in via `terminal_results` (index -> "PASS"/"FAIL").
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
    if not text.startswith(_GET_PREFIX):
        return [], text.strip()[:300]  # error message from env
    body = text[len(_GET_PREFIX):].strip()
    body = body.split(". Please call FINISH")[0]
    data = None
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(body)
            break
        except Exception:
            continue
    if not isinstance(data, dict):
        return [], "unparseable_response"
    if data.get("resourceType") == "Bundle":
        return [e["resource"] for e in data.get("entry", []) if "resource" in e], None
    return [data], None


def _clean(content: str) -> str:
    return content.strip().replace("```tool_code", "").replace("```", "").strip()


def parse_history(history: list[dict], episode_id: str) -> list[Turn]:
    turns: list[Turn] = []
    n = 0
    for i, msg in enumerate(history):
        if msg["role"] != "agent":
            continue
        n += 1
        r = _clean(msg["content"])
        nxt = history[i + 1]["content"] if i + 1 < len(history) and history[i + 1]["role"] == "user" else ""
        if r.startswith("GET"):
            url = r[3:].strip()
            resources, err = _parse_get_response(nxt)
            turns.append(Turn(episode_id, n, GET, tool_name(GET, url), request=url,
                              response_resources=resources, error=err))
        elif r.startswith("POST"):
            first, *rest = r.split("\n")
            url = first[4:].strip()
            try:
                payload, err = json.loads("\n".join(rest)), None
            except Exception:
                payload, err = None, "invalid_post_payload"
            turns.append(Turn(episode_id, n, POST if payload is not None else INVALID,
                              tool_name(POST, url), request=url, payload=payload, error=err))
        elif r.startswith("FINISH("):
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
    for line in Path(runs_jsonl).read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        idx = rec["index"]
        out = rec.get("output") or rec
        task = tasks[idx]
        if not task["id"].split("_")[0] in task_prefixes:
            continue
        m = _NOW_RE.search(task.get("context", ""))
        now = datetime.fromisoformat(m.group(1)) if m else None
        status = str(out.get("status", ""))
        terminal = (terminal_results or {}).get(idx)
        if terminal is None and status.endswith("Correct"):
            terminal = "PASS" if not status.endswith("Incorrect") else "FAIL"
        episodes.append(Episode(
            episode_id=f"{task['id']}#{idx}",
            task_id=task["id"],
            patient_id=task["eval_MRN"],
            reference_time=now,
            turns=parse_history(out.get("history") or [], task["id"]),
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
        if st.endswith("Incorrect"):
            res[r["index"]] = "FAIL"
        elif st.endswith("Correct"):
            res[r["index"]] = "PASS"
    return res
