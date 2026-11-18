"""Output-status classification: keep the five views of an episode's ending separate.

Six episodes in the development runs end with a `FINISH(` payload the model never closed. The
benchmark harness accepts a terminal action by prefix, grades it, and the grade is FAIL; the strict
adapter requires a balanced `FINISH( ... )` and records an invalid action. Both readings are correct
and both must be preserved.

This module **only classifies and records**. It assigns no label, changes no score, and never turns an
official grade into another value: `official_grade` is copied from the harness verbatim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

# Episode completion status (ours), orthogonal to the official grade.
FINISH_PARSED = "FINISH_PARSED"              # balanced FINISH( ... ), the strict parser accepts it
FINISH_TRUNCATED = "FINISH_TRUNCATED"        # starts FINISH( and never closes: output cut short
FINISH_MALFORMED = "FINISH_MALFORMED"        # mentions FINISH but not as FINISH(
NO_TERMINAL_ACTION = "NO_TERMINAL_ACTION"    # last message is a GET/POST or free text
NO_TURNS = "NO_TURNS"                        # the agent produced nothing

# The harness's own statuses, mapped to a grade without reinterpretation.
_GRADE = {"completedCorrect": "PASS", "completedIncorrect": "FAIL"}


def classify_final_message(message: Optional[str]) -> str:
    if message is None or not str(message).strip():
        return NO_TURNS
    text = str(message).strip()
    if text.startswith("FINISH("):
        return FINISH_PARSED if text.endswith(")") else FINISH_TRUNCATED
    if text.upper().startswith("FINISH"):
        return FINISH_MALFORMED
    return NO_TERMINAL_ACTION


def official_grade(harness_status: Optional[str]) -> Optional[str]:
    """PASS / FAIL exactly as the benchmark graded it; None when it refused to grade.

    Never derived from our own parsing, and never upgraded or downgraded.
    """
    if harness_status is None:
        return None
    return _GRADE.get(harness_status)


@dataclass
class OutputStatus:
    episode_uid: Optional[str]
    task_id: Optional[str]
    case_index: Optional[int]
    raw_final_message: str                 # 1. the model's own words, verbatim
    harness_status: Optional[str]          # 2. how the harness interpreted the run
    official_grade: Optional[str]          # 3. the official terminal grade (PASS/FAIL/None)
    strict_parser_action: Optional[str]     # 4. what the strict adapter made of the last turn
    completion_status: str                  # 5. our explicit classification
    graded: bool
    parser_and_harness_agree: bool
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def describe(raw_final_message: Optional[str], harness_status: Optional[str],
             strict_parser_action: Optional[str] = None, episode_uid: Optional[str] = None,
             task_id: Optional[str] = None, case_index: Optional[int] = None) -> OutputStatus:
    """Build the five-view record for one episode. Pure; reads nothing from disk."""
    completion = classify_final_message(raw_final_message)
    grade = official_grade(harness_status)
    graded = grade is not None
    parser_finished = strict_parser_action == "FINISH"
    harness_finished = harness_status is not None and harness_status.startswith("completed")
    note = ""
    if completion == FINISH_TRUNCATED:
        note = ("the model's final answer was cut off before its closing parenthesis: the harness "
                "accepts it by prefix and grades it, the strict parser rejects it as unbalanced")
    elif not graded and completion == NO_TERMINAL_ACTION:
        note = "the harness refused to grade this episode: no terminal action was produced"
    return OutputStatus(
        episode_uid=episode_uid, task_id=task_id, case_index=case_index,
        raw_final_message=str(raw_final_message or ""),
        harness_status=harness_status, official_grade=grade,
        strict_parser_action=strict_parser_action, completion_status=completion,
        graded=graded, parser_and_harness_agree=(parser_finished == harness_finished), note=note)
