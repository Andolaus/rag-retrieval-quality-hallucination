"""Sample included candidates for spreadsheet review without changing the source."""

import argparse
import csv
import json
from pathlib import Path
import random

if __package__:
    from .nq_data import ROOT, protect_output, read_jsonl, valid_answers
else:
    from nq_data import ROOT, protect_output, read_jsonl, valid_answers

DEFAULT_INPUT = ROOT / "data" / "interim" / "nq_candidates.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "nq_manual_review.csv"
DEFAULT_SEED = 42
DEFAULT_SAMPLE_SIZE = 400
REVIEW_FIELDS = (
    "review_id", "question", "answers", "approved", "exclusion_reason",
    "verified_ground_truth", "verification_source", "notes",
)


def prepare_manual_review(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    overwrite: bool = False,
) -> dict[str, object]:
    """Sample without replacement; review IDs retain original question IDs."""
    protect_output(input_path, output_path)
    if output_path.exists() and not overwrite:
        raise ValueError(f"{output_path} already exists. Use --overwrite to replace it.")
    if sample_size <= 0:
        raise ValueError("Sample size must be positive.")
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for line_number, record in read_jsonl(input_path):
        prefix = f"{input_path}:{line_number}"
        if not isinstance(record.get("include"), bool):
            raise ValueError(f"{prefix}: include must be true or false.")
        if record["include"] is False:
            continue
        question_id = record.get("question_id")
        question = record.get("question")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError(f"{prefix}: question_id must be a nonempty string.")
        if question_id in seen:
            raise ValueError(f"{prefix}: duplicate question_id {question_id!r}.")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{prefix}: question must be a nonempty string.")
        answers = record.get("answers")
        if not valid_answers(answers):
            raise ValueError(f"{prefix}: answers must be a nonempty list of strings.")
        seen.add(question_id)
        candidates.append({
            "review_id": question_id,
            "question": question,
            "answers": json.dumps(answers, ensure_ascii=False),
            "approved": None,
            "exclusion_reason": None,
            "verified_ground_truth": None,
            "verification_source": None,
            "notes": "",
        })
    if sample_size > len(candidates):
        raise ValueError(
            f"Requested {sample_size} questions, but only {len(candidates)} "
            "included candidates are available. Choose a smaller --sample-size."
        )
    sample = random.Random(seed).sample(candidates, sample_size)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a file appearing after the check.
    with output_path.open(
        "w" if overwrite else "x", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(sample)
    return {
        "eligible_candidates": len(candidates),
        "sampled_questions": len(sample),
        "seed": seed,
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        summary = prepare_manual_review(
            args.input, args.output, args.sample_size, args.seed, args.overwrite
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
