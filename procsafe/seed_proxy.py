"""Per-case seed injection proxy (D4 item 1).

Why a proxy. `HTTPAgent.inference()` in the benchmark harness does

    body = self.body.copy()
    body.update(self._handle_history(history))

so the request body is fixed for the whole run and the agent never learns which case it is serving.
A per-case seed therefore cannot live in the agent. A proxy can: it sits between the harness and the
model runtime, reads the case identity out of the prompt it is already being sent, derives the
seed deterministically, and injects it.

What it injects. For Ollama's `/api/chat` the sampling seed belongs in `options.seed`. The proxy
sets it, leaves everything else the caller sent untouched, and records what it did.

Case identity. The prompt carries the patient MRN and the task instruction, which together identify
the case; the proxy keys on `sha256(MRN + instruction line)`. That is auditable after the fact from
the same log, and needs no cooperation from the harness.

Honesty. The proxy records what it REQUESTED. Whether the runtime honoured it is a separate,
measured question - see `scripts/medomit_seed_check.py`. Nothing here may be read as a claim of
determinism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from procsafe.provenance import derive_seed

MRN_RE = re.compile(r"\bS\d{7}\b")
# The harness prompt template ends with, literally:
#     {fewshot}Context: {context}
#     Question: {question}
# so the case's own context and instruction are whatever follows the LAST of these markers. Keying
# on the first MRN instead would pick up the few-shot example's patient, which is identical in every
# prompt - a bug this parser exists to avoid.
CONTEXT_MARKER, QUESTION_MARKER = "Context:", "Question:"


def case_text(prompt: str) -> tuple[str, str]:
    """(context, question) for this case, taken from the last markers in the prompt.

    Only the FIRST LINE after each marker is taken. The proxy is sent the whole conversation, so
    reading to the end of the string would absorb every later turn and give the same episode a
    different key - and therefore a different seed - on every turn.
    """
    qi = prompt.rfind(QUESTION_MARKER)
    question = (prompt[qi + len(QUESTION_MARKER):].lstrip().split("\n", 1)[0].strip()
                if qi >= 0 else "")
    head = prompt[:qi] if qi >= 0 else prompt
    ci = head.rfind(CONTEXT_MARKER)
    context = (head[ci + len(CONTEXT_MARKER):].lstrip().split("\n", 1)[0].strip()
               if ci >= 0 else "")
    return context, question


def case_key(prompt: str) -> str:
    """A stable case identifier derived from the prompt alone."""
    context, question = case_text(prompt)
    if not question:
        # No marker found: fall back to the whole prompt, which is still stable per case, rather
        # than to an MRN that may belong to the few-shot example.
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]
    return hashlib.sha256(f"{context}|{question}".encode()).hexdigest()[:16]


def case_label(prompt: str) -> dict:
    context, question = case_text(prompt)
    mrns = MRN_RE.findall(question) or MRN_RE.findall(context)
    return {"mrn": mrns[0] if mrns else None,
            "instruction": question[:160] or None,
            "context_head": context[:80] or None}


class SeedProxy:
    def __init__(self, upstream: str, experiment_id: str, repeat: int, log: Path,
                 temperature: Optional[float] = None):
        self.upstream, self.experiment_id, self.repeat = upstream, experiment_id, repeat
        self.log, self.temperature = Path(log), temperature
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.injected = 0

    def transform(self, body: dict) -> tuple[dict, dict]:
        prompt = "\n".join(m.get("content", "") for m in body.get("messages", []))
        key = case_key(prompt)
        seed = derive_seed(self.experiment_id, key, self.repeat)
        out = json.loads(json.dumps(body))
        options = dict(out.get("options") or {})
        options["seed"] = seed
        if self.temperature is not None:
            options["temperature"] = self.temperature
        out["options"] = options
        record = {"case_key": key, "requested_seed": seed, "repeat": self.repeat,
                  "experiment_id": self.experiment_id, "model": body.get("model"),
                  "options_sent": options, **case_label(prompt)}
        return out, record

    def note(self, record: dict) -> None:
        with self.lock:
            self.injected += 1
            with open(self.log, "a") as f:
                f.write(json.dumps(record) + "\n")


def make_handler(proxy: SeedProxy):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            sent, record = proxy.transform(body)
            payload = json.dumps(sent).encode()
            req = urllib.request.Request(proxy.upstream + self.path, data=payload,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    answer, status = r.read(), r.status
            except Exception as exc:                      # upstream failure is reported, not hidden
                answer = json.dumps({"error": f"upstream: {exc}"}).encode()
                status = 502
            record["upstream_status"] = status
            proxy.note(record)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

    return Handler


def serve(port: int, proxy: SeedProxy) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), make_handler(proxy))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=11690)
    ap.add_argument("--upstream", default="http://localhost:11434")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--repeat", type=int, default=0)
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--log", default="outputs/seed_proxy/seed_log.jsonl")
    a = ap.parse_args()
    proxy = SeedProxy(a.upstream, a.experiment_id, a.repeat, Path(a.log), a.temperature)
    serve(a.port, proxy)
    print(f"seed proxy :{a.port} -> {a.upstream} | experiment={a.experiment_id} "
          f"repeat={a.repeat} | log={a.log}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
