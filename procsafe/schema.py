"""Stable data contract for logged agent trajectories.

Every adapter (demo JSON, MedAgentBench runs, your own agent later) must convert
its raw logs into these objects. The checker only ever sees this schema, so the
evaluation logic is independent of where the trajectory came from.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

# Action types the agent can take (MedAgentBench: GET / POST / FINISH).
GET, POST, FINISH, INVALID = "GET", "POST", "FINISH", "INVALID"


@dataclass
class Turn:
    episode_id: str
    turn: int                         # 1-based position in the trajectory
    action_type: str                  # GET | POST | FINISH | INVALID
    tool: str                         # e.g. lab.search, medicationrequest.create
    request: str = ""                 # raw URL / query string the agent sent
    payload: Optional[dict] = None    # POST body
    response_resources: list[dict] = field(default_factory=list)  # FHIR resources actually returned to the agent
    error: Optional[str] = None       # tool/env error, if any
    message: Optional[str] = None     # FINISH content / final answer

    @property
    def response_resource_ids(self) -> list[str]:
        return [r.get("id", "") for r in self.response_resources]


@dataclass
class Episode:
    episode_id: str
    task_id: str
    patient_id: str                   # patient the task is about (ground truth)
    reference_time: Optional[datetime]  # "now" for freshness checks
    turns: list[Turn]
    terminal_result: Optional[str] = None   # PASS / FAIL from the ordinary benchmark grader
    environment_resources: list[dict] = field(default_factory=list)  # optional EHR catalogue; never evidence unless returned in a turn
    meta: dict[str, Any] = field(default_factory=dict)


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
