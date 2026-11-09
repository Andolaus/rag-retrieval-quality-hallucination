"""Shared JSONL input handling; raw data is never opened for writing."""

import json
from pathlib import Path
from typing import Iterator, TypeGuard

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "NQ-open.dev.jsonl"


def reject_nonfinite(value: str) -> None:
    raise ValueError(f"{value} is not valid JSON.")


def read_jsonl(path: Path) -> Iterator[tuple[int, dict[str, object]]]:
    """Read JSON objects with one-based source line numbers and useful errors."""
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    value = json.loads(line, parse_constant=reject_nonfinite)
                except ValueError as error:
                    raise ValueError(
                        f"{path}:{line_number}: invalid JSON: {error}"
                    ) from error
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{path}:{line_number}: expected a JSON object."
                    )
                yield line_number, value
    except FileNotFoundError as error:
        raise ValueError(
            f"Input not found: {path}. Download NQ-Open separately; "
            f"the default location is {DEFAULT_INPUT}."
        ) from error


def valid_answers(value: object) -> TypeGuard[list[str]]:
    """Require a nonempty list of nonempty answer strings."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(answer, str) and bool(answer.strip()) for answer in value)
    )


def protect_output(input_path: Path, output_path: Path) -> None:
    """Reject writes to the input or anywhere inside the raw-data directory."""
    source = input_path.resolve()
    destination = output_path.resolve()
    raw_directory = (ROOT / "data" / "raw").resolve()
    if (
        destination == source
        or destination.is_relative_to(raw_directory)
        or (
            destination.exists()
            and source.exists()
            and destination.samefile(source)
        )
    ):
        raise ValueError("Output must not overwrite the input or any raw-data file.")
