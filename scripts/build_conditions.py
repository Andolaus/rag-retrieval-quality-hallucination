"""Assemble supplied, reviewed contexts or validate existing condition records.

No retrieval, passage fabrication, or factual verification is performed here.
Verification metadata records human work; validation cannot establish truth.
"""

import argparse
import json
from pathlib import Path
from typing import Literal, TypedDict

if __package__:
    from .nq_data import read_jsonl, valid_answers
else:
    from nq_data import read_jsonl, valid_answers

ConditionLabel = Literal[
    "no_retrieval", "relevant_correct", "irrelevant_correct", "relevant_incorrect"
]
Relevance = Literal["none", "relevant", "irrelevant"]
Factuality = Literal["none", "correct", "incorrect"]
CONDITION_METADATA: dict[ConditionLabel, tuple[Relevance, Factuality]] = {
    "no_retrieval": ("none", "none"),
    "relevant_correct": ("relevant", "correct"),
    "irrelevant_correct": ("irrelevant", "correct"),
    "relevant_incorrect": ("relevant", "incorrect"),
}


class ConditionRecord(TypedDict):
    """Ground truth comes from independent verification, never from context."""

    question_id: str
    question: str
    ground_truth: list[str]
    verification_source: str
    condition: ConditionLabel
    context: str | None
    context_relevance: Relevance
    context_factuality: Factuality


def require_text(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    return value


def validate_condition(record: dict[str, object]) -> None:
    """Validate schema and condition consistency, not passage truth or relevance."""
    for field in ("question_id", "question", "verification_source"):
        require_text(record, field)
    if not valid_answers(record.get("ground_truth")):
        raise ValueError("ground_truth must contain independently verified answer strings.")
    label = record.get("condition")
    if not isinstance(label, str) or label not in CONDITION_METADATA:
        raise ValueError(f"Unsupported condition: {label!r}.")
    relevance, factuality = next(
        metadata for key, metadata in CONDITION_METADATA.items() if key == label
    )
    if (
        record.get("context_relevance") != relevance
        or record.get("context_factuality") != factuality
    ):
        raise ValueError(f"Context metadata does not match condition {label!r}.")
    if "context" not in record:
        raise ValueError("context is required (null for no_retrieval).")
    context = record["context"]
    if label == "no_retrieval":
        if context is not None and context != "":
            raise ValueError("no_retrieval must have null or empty-string context.")
    elif not isinstance(context, str) or not context.strip():
        raise ValueError(f"{label} requires a nonempty context string.")


def prepare_context(question_id: str, condition: ConditionLabel) -> str:
    """Future extension point for independently reviewed experimental passages."""
    raise NotImplementedError(
        f"No context provider implemented for {question_id!r}, {condition!r}. "
        "Supply a manually prepared, reviewed context; no passage is invented."
    )


def build_conditions(
    reviewed_example: dict[str, object],
    contexts: dict[ConditionLabel, str] | None = None,
) -> list[ConditionRecord]:
    """Build the four paired conditions from a manually verified candidate.

    Extra manual-review fields on the candidate are allowed. Its original
    answers are deliberately not used as a fallback for verified_ground_truth.
    """
    if reviewed_example.get("include") is not True:
        raise ValueError("Only included candidates can enter the experimental subset.")
    if reviewed_example.get("manually_approved") is not True:
        raise ValueError("manually_approved must be true before building conditions.")
    question_id = require_text(reviewed_example, "question_id")
    question = require_text(reviewed_example, "question")
    source = require_text(reviewed_example, "verification_source")
    verified = reviewed_example.get("verified_ground_truth")
    if not valid_answers(verified):
        raise ValueError("verified_ground_truth must be a nonempty list of answer strings.")
    ground_truth = list(verified)
    if contexts is not None:
        expected = set(CONDITION_METADATA) - {"no_retrieval"}
        if set(contexts) != expected:
            raise ValueError("Supply exactly the three retrieval-condition contexts.")
    records: list[ConditionRecord] = []
    for label, (relevance, factuality) in CONDITION_METADATA.items():
        context = None
        if label != "no_retrieval":
            context = (
                contexts[label] if contexts is not None
                else prepare_context(question_id, label)
            )
        record: ConditionRecord = {
            "question_id": question_id,
            "question": question,
            "ground_truth": list(ground_truth),
            "verification_source": source,
            "condition": label,
            "context": context,
            "context_relevance": relevance,
            "context_factuality": factuality,
        }
        validate_condition(dict(record))
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True,
        help="Existing condition JSONL to validate; this CLI does not create contexts.",
    )
    args = parser.parse_args()
    count = 0
    seen: set[tuple[str, str]] = set()
    try:
        for line_number, record in read_jsonl(args.input):
            try:
                validate_condition(record)
                key = (str(record["question_id"]), str(record["condition"]))
                if key in seen:
                    raise ValueError(f"Duplicate question/condition pair: {key}.")
                seen.add(key)
            except ValueError as error:
                raise ValueError(f"{args.input}:{line_number}: {error}") from error
            count += 1
        if not count:
            raise ValueError("Condition file is empty.")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps({"validated_condition_records": count}))


if __name__ == "__main__":
    main()
