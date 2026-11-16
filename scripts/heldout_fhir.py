"""Add / remove the synthetic lab results that turn held-out MedAgentBench cases into
positive-action cases (a low value, so an order is required).

MedAgentBench has only 3 natural order-required cases among the 60 task5 + task9 cases.
This script adds one new, newest Observation (a low value) for selected held-out patients on the
LOCAL FHIR server. The unmodified benchmark grader reads the server, so it grades these cases
against the new value. `remove` deletes exactly the resources `add` created.

    python scripts/heldout_fhir.py add    --spec medagentbench_setup/heldout_v1.json
    python scripts/heldout_fhir.py remove --spec medagentbench_setup/heldout_v1.json
"""
import argparse
import json
import urllib.request
from pathlib import Path


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"})
    with urllib.request.urlopen(req) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["add", "remove", "status"])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--fhir", default="http://localhost:8080/fhir")
    ap.add_argument("--state", default=None, help="file recording created resource ids (default: <spec>.created.json)")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    state_path = Path(a.state or a.spec.replace(".json", ".created.json"))
    created = json.loads(state_path.read_text()) if state_path.exists() else {}

    if a.action == "status":
        print(json.dumps(created, indent=1))
        return
    if a.action == "remove":
        for key, rid in list(created.items()):
            call("DELETE", f"{a.fhir}/Observation/{rid}")
            print("deleted", key, rid)
            del created[key]
            state_path.write_text(json.dumps(created, indent=1))
        return
    for s in spec["synthetic_observations"]:
        key = f"{s['mrn']}:{s['code']}"
        if key in created:
            print("already present", key, created[key])
            continue
        bundle = call("GET", f"{a.fhir}/Observation?code={s['code']}&_sort=-date&_count=1&_format=json")
        template = bundle["entry"][0]["resource"]           # any existing result of this lab, as a format template
        obs = {k: v for k, v in template.items() if k not in ("id", "meta")}
        obs["subject"] = {"reference": f"Patient/{s['mrn']}", "identifier": {
            "system": "http://terminology.hl7.org/CodeSystem/v2-0203", "value": s["mrn"]}}
        obs["effectiveDateTime"] = obs["issued"] = s["time"]
        obs["valueQuantity"] = {**template["valueQuantity"], "value": s["value"]}
        obs.pop("interpretation", None)
        res = call("POST", f"{a.fhir}/Observation", obs)
        created[key] = res["id"]
        state_path.write_text(json.dumps(created, indent=1))
        print("created", key, res["id"], s["value"], s["time"])


if __name__ == "__main__":
    main()
