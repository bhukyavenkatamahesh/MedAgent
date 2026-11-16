"""Human-readable audit trail + machine-readable outputs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .checker import EpisodeResult
from .schema import to_jsonable


def episode_table(r: EpisodeResult) -> str:
    lines = [f"### {r.episode_id}  (task {r.task_id})",
             f"Input provenance: {r.input_provenance.get('kind', 'UNSPECIFIED')}. "
             + ("Authored synthetic test inputs; not observed benchmark results."
                if r.input_provenance.get("kind") == "AUTHORED_TEST_INPUT" else ""),
             "",
             "| Turn | Action | Tool | Evidence observed | Resource IDs | Labels | Why |",
             "|---|---|---|---|---|---|---|"]
    for t in r.turns:
        lines.append(f"| {t.turn} | {t.action_type} | {t.tool} | {', '.join(t.evidence_observed) or '-'} "
                     f"| {', '.join(t.evidence_resource_ids) or '-'} "
                     f"| {'; '.join(t.labels)} | {'; '.join(t.reasons) or ''} |")
    if r.action_audit:
        lines.append("")
        lines.append(f"Action requirement (policy {r.policy_id} v{r.policy_version}, "
                     f"review status {r.action_audit[0]['review_status']}):")
        lines.append("")
        lines.append("| Required action | Condition | Status | Attempted | Missed | Unnecessary | Evidence | Why | Condition source |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for e in r.action_audit:
            lines.append(f"| {e['tool']} | {e['condition']} | **{e['status']}** | {'YES' if e['attempted'] else 'NO'} "
                         f"| {'**YES**' if e['missed_required_action'] else 'no'} "
                         f"| {'**YES**' if e['unnecessary_action'] else 'no'} "
                         f"| {e['evidence_resource_id'] or '-'} | {e['reason']} | {e['source']} |")
        for e in r.action_audit:
            if e["note"]:
                lines.append(f"Note ({e['tool']}): {e['note']}")
    lines.append("")
    lines.append(f"terminal = **{r.terminal_result or 'unknown'}**, process = **{r.process_result or 'unclassified'}**, "
                 f"grounding = **{r.grounding_result or 'n/a'}**, action requirement = **{r.action_requirement_status}**, "
                 f"missed required actions = {', '.join(r.missed_required_actions) or 'none'}, "
                 f"unnecessary actions = {', '.join(r.unnecessary_actions) or 'none'}, "
                 f"verified outcome = **{r.verified_outcome or 'unknown'}**"
                 + (f" ({'; '.join(r.verification_failures)})" if r.verification_failures else "") + ", "
                 f"prereq recall = {r.required_prerequisite_recall:.3f}, premature = {r.premature_action_count}, "
                 f"unsafe = {r.unsafe_action_count}, unexpected writes = {r.unexpected_write_count}"
                 + (f", unsupported claims = {', '.join(f'{v:g}' for v in r.unsupported_claims)}"
                    if r.unsupported_claims else ""))
    lines.extend(f"Evaluation note: {note}" for note in r.evaluation_notes)
    return "\n".join(lines)


def episode_summary(r: EpisodeResult) -> dict:
    d = to_jsonable(r)
    d.pop("turns")
    return d


def write_outputs(results: list[EpisodeResult], metrics: dict, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "episodes.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(to_jsonable(r)) + "\n")
    with open(out / "turn_labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["episode_id", "task_id", "turn", "action_type", "tool", "evidence_observed", "labels", "reasons",
                    "input_provenance", "evidence_resource_ids", "action_requirement_status",
                    "missed_required_actions", "unnecessary_actions"])
        for r in results:
            for t in r.turns:
                w.writerow([r.episode_id, r.task_id, t.turn, t.action_type, t.tool,
                            "|".join(t.evidence_observed), "|".join(t.labels), "|".join(t.reasons),
                            r.input_provenance.get("kind", "UNSPECIFIED"), "|".join(t.evidence_resource_ids),
                            r.action_requirement_status, "|".join(r.missed_required_actions),
                            "|".join(r.unnecessary_actions)])
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out / "report.md").write_text("\n\n".join(episode_table(r) for r in results)
                                   + "\n\n## Metrics\n```json\n" + json.dumps(metrics, indent=2) + "\n```\n")
