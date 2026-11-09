"""Inspect NQ-Open without changing it. Lengths are whitespace-separated words."""

import argparse
import json
import random
import statistics
from pathlib import Path

if __package__:
    from .nq_data import DEFAULT_INPUT, read_jsonl, valid_answers
else:
    from nq_data import DEFAULT_INPUT, read_jsonl, valid_answers


def load_examples(path: Path) -> list[tuple[str, list[str]]]:
    """Validate the raw question/answer schema before computing statistics."""
    examples: list[tuple[str, list[str]]] = []
    for line_number, record in read_jsonl(path):
        question = record.get("question")
        answers = record.get("answer")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{path}:{line_number}: question must be a nonempty string.")
        if not valid_answers(answers):
            raise ValueError(
                f"{path}:{line_number}: answer must be a nonempty list "
                "of nonempty strings."
            )
        examples.append((question, answers))
    if not examples:
        raise ValueError(f"{path}: dataset is empty.")
    return examples


def length_statistics(lengths: list[int]) -> dict[str, int | float]:
    """Return descriptive statistics for a nonempty collection of lengths."""
    if not lengths:
        raise ValueError("Cannot summarize an empty collection of lengths.")
    return {
        "minimum": min(lengths),
        "maximum": max(lengths),
        "mean": statistics.mean(lengths),
        "median": statistics.median(lengths),
    }


def inspect_dataset(path: Path, seed: int = 42, sample_size: int = 5) -> dict[str, object]:
    """Compute statistics over questions and each individual answer string."""
    if sample_size < 0:
        raise ValueError("Sample size must be nonnegative.")
    examples = load_examples(path)
    sample = random.Random(seed).sample(examples, min(sample_size, len(examples)))
    return {
        "total_questions": len(examples),
        "one_answer_string": sum(len(answers) == 1 for _, answers in examples),
        "multiple_answer_strings": sum(len(answers) > 1 for _, answers in examples),
        "length_unit": "whitespace-separated words",
        "question_length": length_statistics([len(q.split()) for q, _ in examples]),
        "answer_length": length_statistics(
            [len(answer.split()) for _, answers in examples for answer in answers]
        ),
        "seed": seed,
        "sample": [{"question": q, "answer": a} for q, a in sample],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-size", type=int, default=5)
    args = parser.parse_args()
    try:
        report = inspect_dataset(args.input, args.seed, args.sample_size)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
