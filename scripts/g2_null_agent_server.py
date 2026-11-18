"""G2 — scripted null agents for the READ-ONLY MedAgentBench tasks (4 and 7). No model inference.

The read-only counterpart of `e1_null_agent_server.py`, which is left untouched so the frozen G1
results stay reproducible.

    N0  (port 11511)  replies `FINISH([])` and nothing else.
    N2  (port 11512)  replies with ONE blind answer and nothing else — no GET, ever:
                        task 4 -> `FINISH([-1])`   the no-data sentinel the task text itself defines
                        task 7 -> `FINISH([100])`  one fixed number, arbitrary by design

Neither agent ever issues a GET or a POST, and every reply is logged, so that is auditable.
Task 4's blind reply is the sentinel because 19 of its 30 reference answers ARE the sentinel
(`runs/G2_readonly_audit/`); task 7 has no sentinel case, so a blind number is expected to fail.

    python scripts/g2_null_agent_server.py --log runs/G2_null_agents/agent_log.jsonl
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# The blind answers. Neither is a clinical value and neither is derived from any measurement.
TASK4_ANSWER = "FINISH([-1])"
TASK7_ANSWER = "FINISH([100])"


def blind_answer(prompt: str) -> str:
    """Pick the blind reply from what the PROMPT states, never from the record."""
    low = prompt.lower()
    if "magnesium" in low or '"mg"' in low:
        return TASK4_ANSWER
    if "glucose" in low or '"glu"' in low:
        return TASK7_ANSWER
    return "FINISH([])"


def make_handler(mode: str, log: Path):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"] or 0)) or b"{}")
            messages = body.get("messages", [])
            prompt = "\n".join(m.get("content", "") for m in messages)
            replies_so_far = sum(1 for m in messages if m.get("role") == "assistant")
            content = "FINISH([])" if mode == "n0" else blind_answer(prompt)
            with lock:
                with open(log, "a") as f:
                    f.write(json.dumps({"mode": mode, "turn": replies_so_far + 1, "reply": content,
                                        "issued_get": content.startswith("GET"),
                                        "issued_post": content.startswith("POST")}) + "\n")
            payload = json.dumps({"model": f"scripted-null-{mode}-readonly", "done": True,
                                  "message": {"role": "assistant", "content": content}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="runs/G2_null_agents/agent_log.jsonl")
    ap.add_argument("--n0-port", type=int, default=11511)
    ap.add_argument("--n2-port", type=int, default=11512)
    a = ap.parse_args()
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    for port, mode in ((a.n0_port, "n0"), (a.n2_port, "n2")):
        threading.Thread(target=HTTPServer(("127.0.0.1", port), make_handler(mode, log)).serve_forever,
                         daemon=True).start()
    print(f"N0 on :{a.n0_port}  N2 on :{a.n2_port}  logging to {log}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
