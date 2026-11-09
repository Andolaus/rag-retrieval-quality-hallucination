"""Conservative first-stage screening, not final question selection."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import TypedDict

if __package__:
    from .nq_data import DEFAULT_INPUT, ROOT, protect_output, read_jsonl, valid_answers
else:
    from nq_data import DEFAULT_INPUT, ROOT, protect_output, read_jsonl, valid_answers

# Rules are applied in this order; each excluded row gets its first matching reason.
TIME_DEPENDENT = re.compile(
    r"\b(?:current|currently|today|right\s+now|latest|this\s+year|this\s+season)\b",
    re.IGNORECASE,
)
LONG_LIST = re.compile(
    r"\b(?:list\s+(?:all|every)|name\s+(?:all|every)|"
    r"what\s+are\s+all|list\s+the\s+names)\b",
    re.IGNORECASE,
)
MAX_ANSWER_WORDS = 20
MAX_ANSWER_CHARACTERS = 200
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "nq_candidates.jsonl"


class Candidate(TypedDict):
    """Raw values survive malformed-field exclusion; valid rows use str/list[str]."""

    question_id: str
    question: object
    answers: object
    include: bool
    exclusion_reason: str | None


def exclusion_reason(record: dict[str, object]) -> str | None:
    """Reject only explicit heuristics; multiple aliases alone are never a reason."""
    question = record.get("question")
    answers = record.get("answer")
    if (
        not isinstance(question, str)
        or not question.strip()
        or not valid_answers(answers)
    ):
        return "malformed_or_empty"
    if TIME_DEPENDENT.search(question):
        return "time_dependent"
    if LONG_LIST.search(question):
        return "long_list"
    if all(
        len(answer.split()) > MAX_ANSWER_WORDS
        or len(answer) > MAX_ANSWER_CHARACTERS
        for answer in answers
    ):
        return "long_answer"
    return None


def make_candidate(line_number: int, record: dict[str, object]) -> Candidate:
    """Keep source order and values; identifiers encode one-based source lines."""
    reason = exclusion_reason(record)
    return {
        "question_id": f"nq-dev-{line_number:06d}",
        "question": record.get("question"),
        "answers": record.get("answer"),
        "include": reason is None,
        "exclusion_reason": reason,
    }


def filter_dataset(input_path: Path, output_path: Path) -> dict[str, object]:
    """Write all rows, including exclusions, after fully parsing the input."""
    protect_output(input_path, output_path)
    candidates = [make_candidate(n, record) for n, record in read_jsonl(input_path)]
    if not candidates:
        raise ValueError(f"{input_path}: dataset is empty.")
    counts = Counter(
        row["exclusion_reason"] for row in candidates if not row["include"]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in candidates:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    return {
        "original_examples": len(candidates),
        "remaining_candidates": sum(row["include"] for row in candidates),
        "excluded_by_reason": {
            reason: counts[reason]
            for reason in (
                "malformed_or_empty", "time_dependent", "long_list", "long_answer"
            )
        },
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        summary = filter_dataset(args.input, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
