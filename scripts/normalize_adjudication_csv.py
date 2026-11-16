"""Rename an adjudication sheet's columns to the names the analysis script expects.

The adjudicator's sheet and `scripts/analyze_human_annotations.py` use different column names for
the same four things. This script renames them and copies every value **verbatim**. It never
changes, fills in, infers or drops a human judgement, and it never writes to the input file.

    source column                  -> expected column
    annotation_id                  -> annotation_id            (unchanged)
    disputed_field                 -> field
    reviewer_A_value               -> reviewer_a
    reviewer_B_value               -> reviewer_b
    final_adjudicated_judgement    -> final_adjudicated_judgement  (unchanged)
    adjudicator_rationale          -> adjudicator_rationale        (unchanged)
    resolution_category            -> resolution_category          (unchanged)

Columns the analysis script does not read (`task`, `A_confidence`, `B_confidence`, `A_rationale`,
`B_rationale`, `adjudicator_decision`, `adjudicator_initials`, `adjudicator_notes`) are carried
through unchanged after the expected ones, so the normalized file stays a faithful copy.

    python scripts/normalize_adjudication_csv.py --in <sheet.csv> --out <normalized.csv>
"""
import argparse
import csv
from pathlib import Path

RENAME = {"disputed_field": "field", "reviewer_A_value": "reviewer_a", "reviewer_B_value": "reviewer_b"}
EXPECTED = ["annotation_id", "field", "reviewer_a", "reviewer_b", "final_adjudicated_judgement",
            "adjudicator_rationale", "resolution_category"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    with open(src, newline="") as f:
        reader = csv.DictReader(f)
        rows, source_columns = list(reader), list(reader.fieldnames or [])
    renamed = [RENAME.get(c, c) for c in source_columns]
    missing = [c for c in EXPECTED if c not in renamed]
    if missing:
        raise SystemExit(f"REFUSING: {src} has no column mapping to {missing}. Source columns: "
                         f"{source_columns}. Fix the input rather than guessing a judgement.")
    extras = [c for c in renamed if c not in EXPECTED]
    out_columns = EXPECTED + extras
    kept = 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_columns)
        w.writeheader()
        for row in rows:
            if not (row.get("annotation_id") or "").strip() or row["annotation_id"].startswith("#"):
                continue
            w.writerow({RENAME.get(k, k): v for k, v in row.items() if k is not None})
            kept += 1
    print(f"{src} -> {dst}")
    print(f"  {kept} rows copied verbatim; columns renamed: "
          + ", ".join(f"{k} -> {v}" for k, v in RENAME.items() if k in source_columns))
    print(f"  carried through unchanged: {', '.join(extras) or 'none'}")


if __name__ == "__main__":
    main()
