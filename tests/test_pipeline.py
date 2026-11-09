"""Synthetic tests only; no NQ-Open examples, network access, or dependencies."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_conditions import build_conditions, validate_condition
from scripts.evaluate import (
    evaluate_response,
    summarize_evaluations,
    validate_evaluation,
)
from scripts.filter_nq import (
    MAX_ANSWER_CHARACTERS,
    MAX_ANSWER_WORDS,
    exclusion_reason,
    filter_dataset,
)
from scripts.inspect_dataset import inspect_dataset
from scripts.nq_data import ROOT, protect_output, read_jsonl


class DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "input.jsonl"
        self.output = self.directory / "candidates.jsonl"

    def write_rows(self, rows: list[dict[str, object]]) -> None:
        self.source.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def test_inspection_statistics_and_deterministic_sample(self) -> None:
        self.write_rows([
            {"question": "Which invented city?", "answer": ["New Harbor", "Harbor"]},
            {"question": "Who?", "answer": ["Test Person"]},
        ])
        report = inspect_dataset(self.source, seed=7, sample_size=10)
        self.assertEqual(report, inspect_dataset(self.source, seed=7, sample_size=10))
        self.assertEqual(report["total_questions"], 2)
        self.assertEqual(report["one_answer_string"], 1)
        self.assertEqual(report["multiple_answer_strings"], 1)
        self.assertEqual(report["question_length"], {
            "minimum": 1, "maximum": 3, "mean": 2, "median": 2,
        })
        answer_stats = report["answer_length"]
        self.assertEqual(answer_stats, {
            "minimum": 1, "maximum": 2, "mean": 5 / 3, "median": 2,
        })

    def test_aliases_are_preserved(self) -> None:
        self.write_rows([{
            "question": "  Which invented city?  ", "answer": ["New Harbor", "Harbor"],
        }])
        report = filter_dataset(self.source, self.output)
        row = list(read_jsonl(self.output))[0][1]
        self.assertEqual(row["question"], "  Which invented city?  ")
        self.assertEqual(row["answers"], ["New Harbor", "Harbor"])
        self.assertEqual(row["question_id"], "nq-dev-000001")
        self.assertIsNone(row["exclusion_reason"])
        self.assertTrue(row["include"])
        self.assertEqual(report["remaining_candidates"], 1)

    def test_all_exclusions_and_raw_preservation(self) -> None:
        self.write_rows([
            {"question": "Who is current leader?", "answer": ["Person"]},
            {"question": "List all fictional cities", "answer": ["A", "B"]},
            {"question": "Describe it", "answer": ["word " * (MAX_ANSWER_WORDS + 1)]},
            {"question": "", "answer": []},
            {"question": "Who founded the fictional city?", "answer": ["Person"]},
        ])
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        report = filter_dataset(self.source, self.output)
        self.assertEqual(report["original_examples"], 5)
        self.assertEqual(report["remaining_candidates"], 1)
        self.assertEqual(report["excluded_by_reason"], {
            "malformed_or_empty": 1, "time_dependent": 1,
            "long_list": 1, "long_answer": 1,
        })
        self.assertEqual(len(list(read_jsonl(self.output))), 5)
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).hexdigest())
        first_output = self.output.read_bytes()
        filter_dataset(self.source, self.output)
        self.assertEqual(first_output, self.output.read_bytes())

    def test_time_terms_and_word_boundaries(self) -> None:
        for term in (
            "CURRENT", "currently", "today", "right now", "latest",
            "this year", "this season",
        ):
            with self.subTest(term=term):
                self.assertEqual(exclusion_reason({
                    "question": f"Who is {term} leader?", "answer": ["Person"],
                }), "time_dependent")
        self.assertIsNone(exclusion_reason({
            "question": "What is a recurrent pattern?", "answer": ["Pattern"],
        }))

    def test_thresholds_and_short_alias(self) -> None:
        for answer in (
            " ".join(["word"] * MAX_ANSWER_WORDS),
            "x" * MAX_ANSWER_CHARACTERS,
        ):
            self.assertIsNone(exclusion_reason({"question": "What?", "answer": [answer]}))
        for answer in (
            " ".join(["word"] * (MAX_ANSWER_WORDS + 1)),
            "x" * (MAX_ANSWER_CHARACTERS + 1),
        ):
            self.assertEqual(exclusion_reason({
                "question": "What?", "answer": [answer],
            }), "long_answer")
            self.assertIsNone(exclusion_reason({
                "question": "What?", "answer": [answer, "Short alias"],
            }))

    def test_malformed_fields_are_excluded_but_inspection_fails(self) -> None:
        for record in (
            {}, {"question": "What?"}, {"question": None, "answer": ["X"]},
            {"question": "What?", "answer": "X"},
            {"question": "What?", "answer": [1]},
            {"question": "What?", "answer": [" "]},
        ):
            with self.subTest(record=record):
                self.assertEqual(exclusion_reason(record), "malformed_or_empty")
                self.write_rows([record])
                with self.assertRaisesRegex(ValueError, ":1:"):
                    inspect_dataset(self.source)
                filter_dataset(self.source, self.output)
                row = list(read_jsonl(self.output))[0][1]
                self.assertEqual(row["answers"], record.get("answer"))
                self.assertEqual(row["question"], record.get("question"))

    def test_bad_json_does_not_replace_existing_output(self) -> None:
        self.output.write_text("existing output", encoding="utf-8")
        for contents in ("{}\nnot-json\n", "\n", "[]\n", '{"x": NaN}\n'):
            with self.subTest(contents=contents):
                self.source.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    filter_dataset(self.source, self.output)
                self.assertEqual(self.output.read_text(encoding="utf-8"), "existing output")

    def test_empty_missing_and_invalid_sample_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "Input not found"):
            inspect_dataset(self.source)
        self.source.write_text("", encoding="utf-8")
        for operation in (
            lambda: inspect_dataset(self.source),
            lambda: filter_dataset(self.source, self.output),
            lambda: inspect_dataset(self.source, sample_size=-1),
        ):
            with self.assertRaises(ValueError):
                operation()

    def test_output_protection(self) -> None:
        self.write_rows([{"question": "What?", "answer": ["X"]}])
        for destination in (
            self.source,
            ROOT / "data" / "raw" / "not-created.jsonl",
            ROOT / "data" / "raw" / "nested" / "not-created.jsonl",
        ):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, "must not overwrite"):
                    protect_output(self.source, destination)

    def test_cli_inspection_and_filtering(self) -> None:
        self.write_rows([{"question": "Which invented city?", "answer": ["Harbor"]}])
        commands = (
            ("inspect_dataset.py", "--seed", "42"),
            ("filter_nq.py", "--output", str(self.output)),
        )
        for filename, *options in commands:
            with self.subTest(script=filename):
                completed = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "scripts" / filename),
                     "--input", str(self.source), *options],
                    cwd=self.directory, capture_output=True, text=True, check=True,
                )
                self.assertIsInstance(json.loads(completed.stdout), dict)


class ExperimentInterfaceTests(unittest.TestCase):
    def reviewed_example(self) -> dict[str, object]:
        return {
            "question_id": "synthetic-1",
            "question": "Which invented city?",
            "answers": ["Unverified original"],
            "include": True,
            "manually_approved": True,
            "verified_ground_truth": ["Independent answer"],
            "verification_source": "Synthetic test fixture; not research evidence",
        }

    def conditions(self) -> list[dict[str, object]]:
        return [dict(row) for row in build_conditions(self.reviewed_example(), {
            "relevant_correct": "Synthetic relevant-correct placeholder",
            "irrelevant_correct": "Synthetic irrelevant-correct placeholder",
            "relevant_incorrect": "Synthetic relevant-incorrect placeholder",
        })]

    def test_four_conditions_and_independent_ground_truth(self) -> None:
        records = self.conditions()
        self.assertEqual(len(records), 4)
        self.assertIsNone(records[0]["context"])
        for record in records:
            validate_condition(record)
            self.assertEqual(record["ground_truth"], ["Independent answer"])

    def test_review_is_required_no_answer_fallback(self) -> None:
        for field in (
            "include", "manually_approved", "verified_ground_truth", "verification_source",
        ):
            with self.subTest(field=field):
                example = self.reviewed_example()
                del example[field]
                with self.assertRaises(ValueError):
                    build_conditions(example)
        with self.assertRaises(NotImplementedError):
            build_conditions(self.reviewed_example())

    def test_conditions_reject_inconsistent_or_missing_fields(self) -> None:
        no_retrieval = self.conditions()[0]
        retrieval = self.conditions()[1]
        cases = [
            {**no_retrieval, "context": "Must not be here"},
            {**no_retrieval, "context_relevance": "relevant"},
            {**retrieval, "context": ""},
            {**retrieval, "condition": "unsupported"},
            {**retrieval, "ground_truth": []},
            {**retrieval, "verification_source": ""},
        ]
        missing_context = dict(no_retrieval)
        del missing_context["context"]
        cases.append(missing_context)
        for record in cases:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    validate_condition(record)

    def test_incomplete_or_extra_context_mapping_is_rejected(self) -> None:
        for contexts in (
            {},
            {"no_retrieval": "Unexpected"},
            {"relevant_correct": "Only one context"},
        ):
            with self.subTest(contexts=contexts):
                with self.assertRaisesRegex(ValueError, "exactly the three"):
                    build_conditions(self.reviewed_example(), contexts)

    def judgment(self) -> dict[str, object]:
        return {
            "question_id": "synthetic-1",
            "condition": "relevant_incorrect",
            "response": "A synthetic false claim",
            "factual_correctness": False,
            "factual_hallucination": True,
            "faithfulness": True,
            "answer_correctness": False,
        }

    def test_factuality_and_faithfulness_remain_separate(self) -> None:
        report = summarize_evaluations([self.judgment()])
        metrics = report["relevant_incorrect"]["metrics"]
        self.assertEqual(metrics["faithfulness"]["rate"], 1)
        self.assertEqual(metrics["factual_correctness"]["rate"], 0)
        self.assertEqual(metrics["factual_hallucination"]["rate"], 1)

    def test_null_denominators_abstention_and_condition_grouping(self) -> None:
        unknown = {
            **self.judgment(), "question_id": "synthetic-2",
            "factual_correctness": None, "factual_hallucination": None,
        }
        abstention = {
            **self.judgment(), "condition": "no_retrieval",
            "response": "I do not know", "factual_hallucination": False,
            "faithfulness": None,
        }
        report = summarize_evaluations([self.judgment(), unknown, abstention])
        metric = report["relevant_incorrect"]["metrics"]["factual_hallucination"]
        self.assertEqual(metric["judged"], 1)
        self.assertEqual(metric["unjudged_or_not_applicable"], 1)
        self.assertEqual(metric["rate"], 1)
        no_retrieval = report["no_retrieval"]["metrics"]
        self.assertIsNone(no_retrieval["faithfulness"]["rate"])
        self.assertEqual(no_retrieval["factual_hallucination"]["rate"], 0)

    def test_evaluation_validation_and_unimplemented_judge(self) -> None:
        for record in (
            {**self.judgment(), "factual_correctness": 1},
            {**self.judgment(), "condition": "no_retrieval"},
            {**self.judgment(), "response": None},
        ):
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    validate_evaluation(record)
        with self.assertRaises(ValueError):
            summarize_evaluations([self.judgment(), self.judgment()])
        with self.assertRaises(ValueError):
            summarize_evaluations([])
        with self.assertRaises(NotImplementedError):
            evaluate_response("Answer", build_conditions(self.reviewed_example(), {
                "relevant_correct": "Synthetic placeholder",
                "irrelevant_correct": "Synthetic placeholder",
                "relevant_incorrect": "Synthetic placeholder",
            })[0])

    def test_condition_and_evaluation_clis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            for script, records, output_field in (
                ("build_conditions.py", self.conditions(), "validated_condition_records"),
                ("evaluate.py", [self.judgment()], "relevant_incorrect"),
            ):
                with self.subTest(script=script):
                    path.write_text(
                        "".join(json.dumps(record) + "\n" for record in records),
                        encoding="utf-8",
                    )
                    completed = subprocess.run(
                        [sys.executable, "-B", str(ROOT / "scripts" / script),
                         "--input", str(path)],
                        cwd=directory, capture_output=True, text=True, check=True,
                    )
                    self.assertIn(output_field, json.loads(completed.stdout))
            path.write_text("{}\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "scripts" / "build_conditions.py"),
                 "--input", str(path)],
                capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn(":1:", completed.stderr)


if __name__ == "__main__":
    unittest.main()
