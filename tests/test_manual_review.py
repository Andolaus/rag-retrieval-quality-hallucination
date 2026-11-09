"""Synthetic spreadsheet round trips; no network or research judgments."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.build_conditions import build_conditions
from scripts.finalize_selection import finalize_selection, parse_approval
from scripts.nq_data import ROOT, read_jsonl
from scripts.prepare_manual_review import REVIEW_FIELDS, prepare_manual_review


class ManualReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "candidates.jsonl"
        self.review = self.directory / "review.csv"
        self.output = self.directory / "selected.jsonl"
        self.candidates: list[dict[str, object]] = [
            {
                "question_id": f"synthetic-{index}",
                "question": f'  Which fictional "city", number {index}?\nSecond line',
                "answers": ["City \u00c5", 'Alias, with "quotes"', "Another alias"],
                "include": True,
                "exclusion_reason": None,
            }
            for index in range(12)
        ]
        self.candidates.append({
            "question_id": "excluded", "question": "", "answers": [],
            "include": False, "exclusion_reason": "malformed_or_empty",
        })
        self.write_candidates()

    def write_candidates(self) -> None:
        self.source.write_text(
            "".join(json.dumps(row) + "\n" for row in self.candidates),
            encoding="utf-8",
        )

    def prepare(self, seed: int = 42) -> list[dict[str, str]]:
        prepare_manual_review(self.source, self.review, sample_size=5, seed=seed)
        with self.review.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def save_review(self, rows: list[dict[str, str]]) -> None:
        with self.review.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def approve(self, row: dict[str, str]) -> None:
        row.update(
            approved="TRUE",
            verified_ground_truth=json.dumps(["Independently checked synthetic answer"]),
            verification_source="Synthetic fixture, not research evidence",
            notes='Checked a source, with "quotes"\nand a second line.',
        )

    def test_seeded_sample_aliases_nulls_and_source_preservation(self) -> None:
        original = self.source.read_bytes()
        rows = self.prepare()
        second = self.directory / "second.csv"
        summary = prepare_manual_review(self.source, second, sample_size=5)
        self.assertEqual(self.review.read_bytes(), second.read_bytes())
        self.assertEqual(summary["eligible_candidates"], 12)
        self.assertEqual(summary["sampled_questions"], 5)
        self.assertEqual(summary["seed"], 42)
        self.assertEqual(len({row["review_id"] for row in rows}), 5)
        originals = {row["question_id"]: row for row in self.candidates}
        for row in rows:
            source = originals[row["review_id"]]
            self.assertTrue(source["include"])
            self.assertEqual(row["question"], source["question"])
            self.assertEqual(json.loads(row["answers"]), source["answers"])
            for field in (
                "approved", "exclusion_reason", "verified_ground_truth",
                "verification_source", "notes",
            ):
                self.assertEqual(row[field], "")
        self.assertEqual(original, self.source.read_bytes())
        prepare_manual_review(self.source, second, 5, seed=43, overwrite=True)
        self.assertNotEqual(self.review.read_bytes(), second.read_bytes())

    def test_existing_csv_is_protected_until_explicit_overwrite(self) -> None:
        rows = self.prepare()
        self.approve(rows[0])
        self.save_review(rows)
        edited = self.review.read_bytes()
        with self.assertRaisesRegex(ValueError, "--overwrite"):
            prepare_manual_review(self.source, self.review, 5)
        self.assertEqual(edited, self.review.read_bytes())
        prepare_manual_review(self.source, self.review, 5, overwrite=True)
        self.assertNotEqual(edited, self.review.read_bytes())

    def test_sample_size_errors_do_not_create_output(self) -> None:
        for size in (0, -1, 13):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    prepare_manual_review(self.source, self.review, size)
                self.assertFalse(self.review.exists())
        self.candidates = []
        self.write_candidates()
        with self.assertRaisesRegex(ValueError, "only 0"):
            prepare_manual_review(self.source, self.review, 1)

    def test_candidate_schema_and_duplicate_ids(self) -> None:
        for update in (
            {"include": "true"}, {"question_id": ""}, {"question": ""},
            {"answers": []}, {"answers": [""]},
        ):
            with self.subTest(update=update):
                self.candidates[0] = {**self.candidates[1], **update}
                self.write_candidates()
                with self.assertRaisesRegex(ValueError, ":1:"):
                    prepare_manual_review(self.source, self.review, 1)
        self.candidates[0] = dict(self.candidates[1])
        self.write_candidates()
        with self.assertRaisesRegex(ValueError, "duplicate question_id"):
            prepare_manual_review(self.source, self.review, 1)

    def test_finalize_round_trip_summary_and_condition_compatibility(self) -> None:
        rows = self.prepare()
        self.approve(rows[0])
        self.approve(rows[1])
        rows[2].update(approved="false", exclusion_reason="ambiguous")
        rows[3].update(approved="False", exclusion_reason="")
        rows[4]["approved"] = "null"
        self.save_review(rows)
        review_bytes = self.review.read_bytes()
        summary = finalize_selection(self.review, self.output)
        self.assertEqual(summary["total_rows"], 5)
        self.assertEqual(summary["total_reviewed"], 4)
        self.assertEqual(summary["total_approved"], 2)
        self.assertEqual(summary["total_excluded"], 2)
        self.assertEqual(summary["total_pending"], 1)
        self.assertEqual(summary["exclusion_reasons"], {"ambiguous": 1, "unspecified": 1})
        selected = [record for _, record in read_jsonl(self.output)]
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["question"], rows[0]["question"])
        self.assertEqual(selected[0]["answers"], json.loads(rows[0]["answers"]))
        self.assertEqual(selected[0]["notes"], rows[0]["notes"])
        self.assertEqual(selected[0]["question_id"], rows[0]["review_id"])
        self.assertIs(selected[0]["manually_approved"], True)
        with self.assertRaises(NotImplementedError):
            build_conditions(selected[0])
        self.assertEqual(review_bytes, self.review.read_bytes())
        output_bytes = self.output.read_bytes()
        finalize_selection(self.review, self.output)
        self.assertEqual(output_bytes, self.output.read_bytes())

    def test_invalid_approved_fields_leave_existing_output_untouched(self) -> None:
        rows = self.prepare()
        self.approve(rows[0])
        valid = dict(rows[0])
        self.output.write_text("existing output", encoding="utf-8")
        for field, value in (
            ("question", " "), ("answers", "[]"), ("answers", '[""]'),
            ("answers", "Not JSON"), ("answers", '["ok", 1]'),
            ("verified_ground_truth", ""), ("verified_ground_truth", '[" "]'),
            ("verified_ground_truth", '"Not an array"'),
            ("verification_source", " "), ("verification_source", "null"),
            ("exclusion_reason", "ambiguous"),
            ("approved", "yes"), ("review_id", ""),
        ):
            with self.subTest(field=field, value=value):
                rows[0] = {**valid, field: value}
                self.save_review(rows)
                with self.assertRaisesRegex(ValueError, "CSV row 2"):
                    finalize_selection(self.review, self.output)
                self.assertEqual(self.output.read_text(encoding="utf-8"), "existing output")

    def test_multiple_errors_and_duplicate_review_ids(self) -> None:
        rows = self.prepare()
        rows[0]["approved"] = "yes"
        rows[1]["approved"] = "no"
        self.save_review(rows)
        with self.assertRaises(ValueError) as error:
            finalize_selection(self.review, self.output)
        self.assertIn("CSV row 2", str(error.exception))
        self.assertIn("CSV row 3", str(error.exception))
        rows[0]["approved"] = ""
        rows[1]["approved"] = ""
        rows[1]["review_id"] = rows[0]["review_id"]
        self.save_review(rows)
        with self.assertRaisesRegex(ValueError, "Duplicate review_id"):
            finalize_selection(self.review, self.output)
        self.assertFalse(self.output.exists())

    def test_no_approvals_produce_explicit_zero_counts_and_empty_output(self) -> None:
        rows = self.prepare()
        for decision in ("", "false"):
            for row in rows:
                row["approved"] = decision
            self.save_review(rows)
            self.output.write_text("existing", encoding="utf-8")
            summary = finalize_selection(self.review, self.output)
            self.assertEqual(summary["total_approved"], 0)
            self.assertEqual(summary["total_pending"], 5 if decision == "" else 0)
            self.assertEqual(summary["total_excluded"], 5 if decision == "false" else 0)
            self.assertEqual(self.output.read_bytes(), b"")

    def test_boolean_parsing(self) -> None:
        for text, expected in (
            ("TRUE", True), (" true ", True), ("False", False),
            ("", None), ("null", None), ("NULL", None),
        ):
            self.assertIs(parse_approval(text), expected)
        for text in ("yes", "no", "1", "0", "maybe"):
            with self.assertRaises(ValueError):
                parse_approval(text)

    def test_malformed_headers_rows_and_empty_files(self) -> None:
        for contents in (
            "", "review_id,approved\nx,true\n",
            ",".join(REVIEW_FIELDS) + ",approved\n",
            ",".join(REVIEW_FIELDS) + "\nonly_one_cell\n",
            ",".join(REVIEW_FIELDS) + "\n" + ",".join(["x"] * 9) + "\n",
            ",".join(REVIEW_FIELDS) + "\n",
            ",".join(REVIEW_FIELDS).replace(",", ";") + "\n",
        ):
            with self.subTest(contents=contents):
                self.review.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    finalize_selection(self.review, self.output)
                self.assertFalse(self.output.exists())

    def test_raw_and_input_paths_cannot_be_overwritten(self) -> None:
        self.prepare()
        for operation, source in (
            (prepare_manual_review, self.source), (finalize_selection, self.review),
        ):
            for output in (source, ROOT / "data" / "raw" / "never-created.csv"):
                with self.subTest(operation=operation, output=output):
                    with self.assertRaisesRegex(ValueError, "must not overwrite"):
                        operation(source, output)

    def test_cli_round_trip_and_overwrite_failure(self) -> None:
        command = [
            sys.executable, "-B", str(ROOT / "scripts" / "prepare_manual_review.py"),
            "--input", str(self.source), "--output", str(self.review),
            "--sample-size", "5", "--seed", "42",
        ]
        completed = subprocess.run(
            command, cwd=self.directory, capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(completed.stdout)["sampled_questions"], 5)
        completed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("--overwrite", completed.stderr)
        with self.review.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.approve(rows[0])
        self.save_review(rows)
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "finalize_selection.py"),
             "--input", str(self.review), "--output", str(self.output)],
            cwd=self.directory, capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(completed.stdout)["total_approved"], 1)
        rows[0]["verification_source"] = ""
        self.save_review(rows)
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "finalize_selection.py"),
             "--input", str(self.review), "--output", str(self.output)],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("CSV row 2", completed.stderr)


if __name__ == "__main__":
    unittest.main()
