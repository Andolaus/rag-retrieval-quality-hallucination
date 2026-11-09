"""Validate spreadsheet decisions and export only independently verified approvals."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

if __package__:
    from .nq_data import ROOT, protect_output, valid_answers
    from .prepare_manual_review import DEFAULT_OUTPUT as DEFAULT_INPUT, REVIEW_FIELDS
else:
    from nq_data import ROOT, protect_output, valid_answers
    from prepare_manual_review import DEFAULT_OUTPUT as DEFAULT_INPUT, REVIEW_FIELDS

DEFAULT_OUTPUT = ROOT / "data" / "processed" / "nq_selected.jsonl"


def parse_approval(value: str) -> bool | None:
    """Accept spreadsheet TRUE/FALSE, or blank/null for a pending decision."""
    normalized = value.strip().lower()
    if normalized in ("", "null"):
        return None
    if normalized in ("true", "false"):
        return normalized == "true"
    raise ValueError("approved must be true, false, or blank/null (pending).")


def parse_answers(value: str, field: str) -> list[str]:
    """Decode a JSON array within a CSV cell without splitting answer aliases."""
    try:
        answers = json.loads(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a JSON array of strings.") from error
    if not valid_answers(answers):
        raise ValueError(f"{field} must be a nonempty JSON array of nonempty strings.")
    return answers


def approved_record(row: dict[str, str]) -> dict[str, object]:
    """Retain review fields and add compatibility fields for build_conditions."""
    if not row["question"].strip():
        raise ValueError("Approved question must be nonempty.")
    answers = parse_answers(row["answers"], "answers")
    verified = parse_answers(row["verified_ground_truth"], "verified_ground_truth")
    if row["verification_source"].strip().lower() in ("", "null"):
        raise ValueError("Approved rows require an independent verification_source.")
    if row["exclusion_reason"].strip().lower() not in ("", "null"):
        raise ValueError("Approved rows must not have an exclusion_reason.")
    return {
        "review_id": row["review_id"],
        "question_id": row["review_id"],
        "question": row["question"],
        "answers": answers,
        "approved": True,
        "include": True,
        "manually_approved": True,
        "exclusion_reason": None,
        "manual_exclusion_reason": None,
        "verified_ground_truth": verified,
        "verification_source": row["verification_source"],
        "notes": row["notes"],
    }


def finalize_selection(
    input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT
) -> dict[str, object]:
    """Validate all decisions before writing; pending rows are not exclusions."""
    protect_output(input_path, output_path)
    selected: list[dict[str, object]] = []
    reasons: Counter[str] = Counter()
    errors: list[str] = []
    seen: set[str] = set()
    total = pending = excluded = 0
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = reader.fieldnames
        if (
            headers is None
            or len(headers) != len(set(headers))
            or not set(REVIEW_FIELDS).issubset(headers)
        ):
            raise ValueError(f"{input_path}: missing or duplicate review CSV columns.")
        for row_number, raw in enumerate(reader, start=2):
            total += 1
            prefix = f"{input_path}:CSV row {row_number}"
            if None in raw or any(value is None for value in raw.values()):
                errors.append(f"{prefix}: wrong number of CSV cells.")
                continue
            row = {field: raw[field] for field in REVIEW_FIELDS}
            try:
                review_id = row["review_id"]
                if not review_id.strip():
                    raise ValueError("review_id must be nonempty.")
                if review_id in seen:
                    raise ValueError(f"Duplicate review_id {review_id!r}.")
                seen.add(review_id)
                approved = parse_approval(row["approved"])
                if approved is None:
                    pending += 1
                elif approved:
                    selected.append(approved_record(row))
                else:
                    excluded += 1
                    reason = row["exclusion_reason"].strip()
                    reasons[reason if reason and reason.lower() != "null" else "unspecified"] += 1
            except ValueError as error:
                errors.append(f"{prefix} ({row['review_id']!r}): {error}")
    if errors:
        raise ValueError("Review validation failed:\n" + "\n".join(errors))
    if not total:
        raise ValueError(f"{input_path}: review CSV contains no data rows.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    return {
        "total_rows": total,
        "total_reviewed": len(selected) + excluded,
        "total_approved": len(selected),
        "total_excluded": excluded,
        "total_pending": pending,
        "exclusion_reasons": dict(sorted(reasons.items())),
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        summary = finalize_selection(args.input, args.output)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
