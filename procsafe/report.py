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
             "| Turn | Action | Tool | Evidence observed | Labels | Why |",
             "|---|---|---|---|---|---|"]
    for t in r.turns:
        lines.append(f"| {t.turn} | {t.action_type} | {t.tool} | {', '.join(t.evidence_observed) or '-'} "
                     f"| {'; '.join(t.labels)} | {'; '.join(t.reasons) or ''} |")
    lines.append("")
    lines.append(f"terminal = **{r.terminal_result}**, process = **{r.process_result}**, "
                 f"prereq recall = {r.required_prerequisite_recall}, premature = {r.premature_action_count}, "
                 f"unsafe = {r.unsafe_action_count}")
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
        w.writerow(["episode_id", "task_id", "turn", "action_type", "tool", "evidence_observed", "labels", "reasons", "input_provenance"])
        for r in results:
            for t in r.turns:
                w.writerow([r.episode_id, r.task_id, t.turn, t.action_type, t.tool,
                            "|".join(t.evidence_observed), "|".join(t.labels), "|".join(t.reasons),
                            r.input_provenance.get("kind", "UNSPECIFIED")])
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out / "report.md").write_text("\n\n".join(episode_table(r) for r in results)
                                   + "\n\n## Metrics\n```json\n" + json.dumps(metrics, indent=2) + "\n```\n")
