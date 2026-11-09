"""Evaluation interfaces only: no automatic factual judgments or LLM judge.

Factual correctness is judged against independently verified ground truth.
Faithfulness concerns support in the retrieved context, even when it is false.
Hallucination is a separately annotated unsupported/false factual claim, not
simply the inverse of answer correctness: an abstention need not hallucinate.
The annotation rubric and treatment of partial answers must be preregistered.
"""

import argparse
import json
from pathlib import Path
from typing import TypedDict

if __package__:
    from .build_conditions import CONDITION_METADATA, ConditionRecord
    from .nq_data import read_jsonl
else:
    from build_conditions import CONDITION_METADATA, ConditionRecord
    from nq_data import read_jsonl

METRICS = (
    "factual_correctness",
    "factual_hallucination",
    "faithfulness",
    "answer_correctness",
)


class EvaluationRecord(TypedDict):
    """One response with explicit judgments; None means unjudged/not applicable."""

    question_id: str
    condition: str
    response: str
    factual_correctness: bool | None
    factual_hallucination: bool | None
    faithfulness: bool | None
    answer_correctness: bool | None


def evaluate_response(
    response: str, condition_record: ConditionRecord
) -> EvaluationRecord:
    """Future evaluator with identity, independent truth, and context available."""
    raise NotImplementedError(
        "No automatic evaluator is implemented. Define a manual annotation "
        "rubric using independent ground truth and record separate judgments."
    )


def validate_evaluation(record: dict[str, object]) -> None:
    """Require explicit nullable judgments and an identified response."""
    question_id = record.get("question_id")
    if not isinstance(question_id, str) or not question_id.strip():
        raise ValueError("question_id must be a nonempty string.")
    condition = record.get("condition")
    if not isinstance(condition, str) or condition not in CONDITION_METADATA:
        raise ValueError(f"Unsupported condition: {condition!r}.")
    if not isinstance(record.get("response"), str):
        raise ValueError("response must be a string (an empty response is allowed).")
    for metric in METRICS:
        if metric not in record:
            raise ValueError(f"Missing judgment: {metric}; use null if unjudged.")
        if record[metric] is not None and not isinstance(record[metric], bool):
            raise ValueError(f"{metric} must be true, false, or null.")
    if condition == "no_retrieval" and record["faithfulness"] is not None:
        raise ValueError("Faithfulness must be null when there is no retrieved context.")


def summarize_evaluations(records: list[dict[str, object]]) -> dict[str, object]:
    """Compute per-condition, response-level rates with explicit denominators.

    Each metric uses only its own non-null judgments. No pooled condition rate
    is produced, and no missing judgment is counted as a negative outcome.
    """
    if not records:
        raise ValueError("No evaluation records to summarize.")
    seen: set[tuple[str, str]] = set()
    groups: dict[str, list[dict[str, object]]] = {}
    for record in records:
        validate_evaluation(record)
        key = (str(record["question_id"]), str(record["condition"]))
        if key in seen:
            raise ValueError(f"Duplicate question/condition pair: {key}.")
        seen.add(key)
        groups.setdefault(key[1], []).append(record)
    summary: dict[str, object] = {}
    for condition, rows in groups.items():
        metrics: dict[str, object] = {}
        for metric in METRICS:
            judgments = [row[metric] for row in rows if row[metric] is not None]
            positive = sum(value is True for value in judgments)
            metrics[metric] = {
                "positive": positive,
                "judged": len(judgments),
                "unjudged_or_not_applicable": len(rows) - len(judgments),
                "rate": positive / len(judgments) if judgments else None,
            }
        summary[condition] = {"responses": len(rows), "metrics": metrics}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True,
        help="JSONL of existing manual judgments; does not evaluate model responses.",
    )
    args = parser.parse_args()
    try:
        records = []
        for line_number, record in read_jsonl(args.input):
            try:
                validate_evaluation(record)
            except ValueError as error:
                raise ValueError(f"{args.input}:{line_number}: {error}") from error
            records.append(record)
        summary = summarize_evaluations(records)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
