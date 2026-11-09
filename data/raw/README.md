# Local NQ-Open source data

Download `NQ-open.dev.jsonl` separately and place it here:

```text
data/raw/NQ-open.dev.jsonl
```

The original NQ-Open development split contains **3,610 questions**. NQ-Open
originates from Natural Questions and provides open-domain questions with
short-answer strings. Multiple answer strings may be aliases or alternative
valid forms, not necessarily different target facts.

Obtain the development split through the official
[Dense Passage Retrieval data instructions](https://github.com/facebookresearch/DPR#data)
or the [Natural Questions open-domain resources](https://ai.google.com/research/NaturalQuestions).
Check that the file is JSONL with one object per line and fields `question`
(string) and `answer` (list of strings); other distributions may use JSON arrays.
Renaming a JSON array to `.jsonl` does not convert it.

NQ-Open is distributed under
[Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0)](https://creativecommons.org/licenses/by-sa/3.0/).
The original dataset is intentionally **not stored in this repository** and is
excluded by the root `.gitignore`. Do not add it to Git or overwrite it.
Any redistributed selected subset must retain attribution, identify changes,
and comply with the applicable ShareAlike obligations.

## Required citations

- Tom Kwiatkowski et al. (2019). *Natural Questions: A Benchmark for Question
  Answering Research*. Transactions of the Association for Computational
  Linguistics, 7, 453-466.
  https://doi.org/10.1162/tacl_a_00276
- Kenton Lee, Ming-Wei Chang, and Kristina Toutanova (2019). *Latent Retrieval
  for Weakly Supervised Open Domain Question Answering*. Proceedings of ACL,
  6086-6096.
  https://doi.org/10.18653/v1/P19-1612
