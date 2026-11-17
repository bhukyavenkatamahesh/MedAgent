"""E1 — scripted null agents, served over the Ollama chat API so the real benchmark harness and the
real reference grader can run them end to end. **No language model is involved.**

Two agents, each on its own port:

    N0  (port 11501)  replies `FINISH([])` and nothing else. It never issues a GET or a POST.
    N1  (port 11502)  replies with ONE order for the task, built only from the task text (the MRN and
                      the codes the prompt states), then `FINISH([])`. It never issues a GET.

N1's payloads are deliberately blind: for task10 the grader's expected ServiceRequest contains no
field derived from the observed value, so the fixed payload is exactly right; for task5 and task9 the
dose is value-derived, so N1 posts a fixed dose and is expected to fail. That asymmetry is the point.

Every request and reply is appended to a JSONL log, so the absence of any GET is auditable.

    python scripts/e1_null_agent_server.py --log runs/E1_null_agents/agent_log.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FHIR = "http://localhost:8080/fhir/"
NOW = "2023-11-13T10:15:00+00:00"


def blind_order(prompt: str) -> str | None:
    """One fixed order for the task, using only what the prompt itself states."""
    mrn = (re.search(r"\bS\d{7}\b", prompt) or [None])[0] if re.search(r"\bS\d{7}\b", prompt) else None
    if mrn is None:
        return None
    subject = {"reference": f"Patient/{mrn}"}
    if "HbA1C" in prompt or '"A1C"' in prompt:
        return f'POST {FHIR}ServiceRequest\n' + json.dumps({
            "resourceType": "ServiceRequest",
            "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4",
                                 "display": "HbA1C lab test"}]},
            "authoredOn": NOW, "status": "active", "intent": "order", "priority": "stat",
            "subject": subject})
    if "magnesium" in prompt.lower():
        return f'POST {FHIR}MedicationRequest\n' + json.dumps({
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {"coding": [{"system": "http://hl7.org/fhir/sid/ndc",
                                                      "code": "0338-1715-40",
                                                      "display": "magnesium sulfate IV"}]},
            "authoredOn": NOW,
            "dosageInstruction": [{"route": "IV", "doseAndRate": [
                {"doseQuantity": {"value": 1, "unit": "g"}, "rateQuantity": {"value": 1, "unit": "h"}}]}],
            "status": "active", "intent": "order", "subject": subject})
    if "potassium" in prompt.lower():
        return f'POST {FHIR}MedicationRequest\n' + json.dumps({
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {"coding": [{"system": "http://hl7.org/fhir/sid/ndc",
                                                      "code": "40032-917-01",
                                                      "display": "potassium chloride oral"}]},
            "authoredOn": NOW,
            "dosageInstruction": [{"route": "oral", "doseAndRate": [
                {"doseQuantity": {"value": 10, "unit": "mEq"}}]}],
            "status": "active", "intent": "order", "subject": subject})
    return None


def make_handler(mode: str, log: Path):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):   # keep the harness output readable
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)) or b"{}")
            messages = body.get("messages", [])
            prompt = "\n".join(m.get("content", "") for m in messages)
            replies_so_far = sum(1 for m in messages if m.get("role") == "assistant")
            if mode == "n0":
                content = "FINISH([])"
            else:
                order = blind_order(prompt)
                content = order if (replies_so_far == 0 and order) else "FINISH([])"
            with lock:
                with open(log, "a") as f:
                    f.write(json.dumps({"mode": mode, "turn": replies_so_far + 1,
                                        "reply": content,
                                        "issued_get": content.startswith("GET"),
                                        "issued_post": content.startswith("POST")}) + "\n")
            payload = json.dumps({"model": f"scripted-null-{mode}", "done": True,
                                  "message": {"role": "assistant", "content": content}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="runs/E1_null_agents/agent_log.jsonl")
    ap.add_argument("--n0-port", type=int, default=11501)
    ap.add_argument("--n1-port", type=int, default=11502)
    a = ap.parse_args()
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    servers = [HTTPServer(("127.0.0.1", a.n0_port), make_handler("n0", log)),
               HTTPServer(("127.0.0.1", a.n1_port), make_handler("n1", log))]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"N0 on :{a.n0_port}  N1 on :{a.n1_port}  logging to {log}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
