# The Impact of Retrieval Quality on Factual Hallucinations in Retrieval-Augmented Large Language Models

## Research question

**How do retrieval relevance and factual correctness of retrieved context affect
factual hallucination rates in Retrieval-Augmented Large Language Models?**

This ongoing master's-level Data Science / AI project studies how retrieved
evidence affects factual claims in generated answers. This repository currently
provides data inspection, conservative screening, and interfaces for future
experiments. There are no experimental results yet; the methodology may evolve.

## Experimental idea

Use the same manually selected questions across four controlled conditions:

| Condition | Context relevance | Context factuality |
|---|---|---|
| `no_retrieval` | Not applicable | Not applicable |
| `relevant_correct` | Relevant | Correct |
| `irrelevant_correct` | Irrelevant | Correct |
| `relevant_incorrect` | Relevant | Incorrect |

These comparisons separate relevance effects from factuality effects, but are
not a complete factorial design: `irrelevant_incorrect` is not planned.
Contexts are not ground truth. Every experimental question requires an
**independently verified ground-truth answer and verification source**.
Passage truth and relevance must themselves be reviewed; schema validation
cannot establish either.

Primary outcomes are factual correctness and factual hallucination rate.
Secondary measures may include answer correctness and faithfulness to context.
A response repeating a false retrieved claim can be faithful yet factually
incorrect. A wrong answer or abstention is not automatically a hallucination.
Define the annotation rubric, abstention handling, and analysis before running
experiments. Initial aggregation uses separately judged, response-level binary
outcomes with per-metric denominators, grouped by condition.

## Dataset

The local source is the **NQ-Open development split**, derived from Natural
Questions, with an expected **3,610 examples**. Each JSONL row contains a
`question` string and an `answer` list of strings. Multiple strings may be
aliases; the pipeline never excludes a question solely for having aliases.

Download `NQ-open.dev.jsonl` separately using the
[DPR data instructions](https://github.com/facebookresearch/DPR#data) or
[Natural Questions resources](https://ai.google.com/research/NaturalQuestions).
Place the JSONL file at `data/raw/NQ-open.dev.jsonl`. Confirm the filename and
format; JSON-array distributions are not interchangeable with JSONL.
See [raw-data instructions](data/raw/README.md). Nothing downloads automatically.

## Repository structure

```text
data/
  raw/README.md             Local-data instructions and attribution
  interim/                 Screening output, ignored by Git
  processed/               Future reviewed subset, not ignored by default
scripts/
  nq_data.py               Shared JSONL reading and raw-output protection
  inspect_dataset.py       Schema checks, statistics, seeded sample
  filter_nq.py             Conservative screening with auditable exclusions
  build_conditions.py     Condition assembly interfaces and validation
  evaluate.py             Evaluation interfaces and manual-judgment summaries
prompts/                   Future versioned prompts
results/                   Local generated outputs, ignored by Git
notebooks/                 Optional exploratory analyses
tests/                     Standard-library unit tests
requirements.txt           No external dependencies initially
```

## Setup and first commands

Python **3.11+** is required. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The installation step is optional: the implementation uses only the standard
library. Activation is not required when using the interpreter path above.
After placing the raw data:

```powershell
.\.venv\Scripts\python.exe scripts\inspect_dataset.py --seed 42 --sample-size 5
.\.venv\Scripts\python.exe scripts\filter_nq.py
```

Inspection reports total questions, one/multiple-answer counts, word-length
minimum/maximum/mean/median, and a seeded sample. Answer-length statistics cover
**each answer string**, including aliases, rather than concatenated answers.
Invalid schemas fail with filename and line number.

Filtering writes `data/interim/nq_candidates.jsonl` and prints a JSON summary.
Optional `--input` and `--output` accept alternate paths. Default paths are
resolved relative to the repository, not the shell's working directory.
The output contains **every source row**, not just survivors:

```json
{
  "question_id": "nq-dev-000001",
  "question": "<original question>",
  "answers": ["<original answer>"],
  "include": true,
  "exclusion_reason": null
}
```

IDs encode one-based source line numbers and remain stable only for an unchanged
source file/order. No candidates are sampled or shuffled, so filtering needs no
random seed. A malformed field is preserved (missing fields become null) and
excluded. Invalid JSON, blank lines, or non-object rows fail explicitly instead
of being silently dropped. An empty dataset also fails.

### Initial screening rules

Rules and thresholds are near the top of [filter_nq.py](scripts/filter_nq.py).
The **first matching rule** determines the single exclusion reason:

1. `malformed_or_empty`: missing/blank question, or missing, empty, non-list,
   non-string, or blank answers.
2. `time_dependent`: whole-word/phrase matches for current, currently, today,
   right now, latest, this year, or this season (case-insensitive).
3. `long_list`: explicit phrases such as "list all", "list every", "name all",
   "name every", "what are all", or "list the names".
4. `long_answer`: **every** answer string exceeds 20 whitespace-separated words
   or 200 characters. At least one short alias is sufficient to retain the row.

These are screening heuristics, not semantic judgments. They may miss unsuitable
questions or flag suitable ones (for example, "electric current"); exclusions
remain available for audit. The script does not infer a final 200-question set.

## Manual review and future experiments

Review candidates with `include: true`, aiming for approximately 200 questions:

- Clear, objective, independently verifiable factual answer.
- Not strongly time-dependent; preferably one underlying target fact.
- Suitable for controlled retrieval passages and a believable incorrect variant.

Extend reviewed rows with `manually_approved` (boolean),
`manual_exclusion_reason` (string or null), `verified_ground_truth` (answer-string
list), and `verification_source` (nonempty independent source URL/citation).
Save the selected, reviewed subset under `data/processed/`. Keep the screening
output unchanged as an audit trail.

`build_conditions()` requires inclusion, manual approval, verified answers, and
a verification source. It accepts three explicitly supplied, reviewed contexts
and constructs the no-retrieval record with null context. Without supplied
contexts, the context-provider stub raises `NotImplementedError`.
It does not retrieve or fabricate passages.

The following commands are **for later use with prepared files**, not prerequisites:

```powershell
.\.venv\Scripts\python.exe scripts\build_conditions.py --input data\processed\nq_conditions.jsonl
.\.venv\Scripts\python.exe scripts\evaluate.py --input results\manual_judgments.jsonl
```

The first CLI only validates existing condition records; it does not generate
them or require a complete paired experimental set yet. Each record requires
`question_id`, `question`, `ground_truth`, `verification_source`, `condition`,
`context`, `context_relevance`, and `context_factuality`. No-retrieval records
use `"none"` for both context metadata fields and null or empty context.

The second CLI only summarizes existing manual judgments. Each row needs
`question_id`, `condition`, `response`, and four boolean-or-null fields:
`factual_correctness`, `factual_hallucination`, `faithfulness`,
`answer_correctness`. Null means unjudged/not applicable; no-retrieval
faithfulness must be null. Duplicate question/condition pairs are rejected.
No automatic factual evaluator or LLM-as-a-judge is implemented.

## Reproducibility

- Never edit the raw file. Output guards reject the input path and raw directory.
- Record the source origin, download date, checksum, Python version, screening
  thresholds, seed, and manual-review decisions with the final subset.
  PowerShell can obtain the checksum with
  `Get-FileHash data\raw\NQ-open.dev.jsonl -Algorithm SHA256`.
- Inspection uses a local seeded RNG (default 42); filtering preserves source
  order. Identical inputs/rules produce identical candidate contents.
- Record model versions, generation settings, prompts, passages, annotation
  rubric, and evaluation code before later experiments.
- Raw JSONL, interim JSONL, credentials, environments, and generated results are
  ignored. Processed data is deliberately not ignored; check attribution and
  licensing before publishing it.

## Dataset license and attribution

NQ-Open is distributed under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
The original dataset is intentionally not committed. Attribute the original
creators, identify filtering/manual changes, and observe ShareAlike requirements
when redistributing derived data. No separate software license is selected yet.

### Academic citations

- Kwiatkowski, T., et al. (2019). *Natural Questions: A Benchmark for Question
  Answering Research*. Transactions of the Association for Computational
  Linguistics, 7, 453-466. https://doi.org/10.1162/tacl_a_00276
- Lee, K., Chang, M.-W., & Toutanova, K. (2019). *Latent Retrieval for Weakly
  Supervised Open Domain Question Answering*. Proceedings of ACL, 6086-6096.
  https://doi.org/10.18653/v1/P19-1612
