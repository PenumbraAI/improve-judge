# tool: run-judge.py

## Overview

`run-judge.py` runs an **LLM-as-a-judge** evaluation over a set of
request/response test cases. It loads a judge definition, applies that judge to
each test case, prints the judge's verdict and rationale, and optionally writes
the results to a file.

The judge itself is an MLflow `InstructionsJudge`
(`mlflow.genai.judges.instructions_judge`). A judge is defined by a set of
natural-language instructions plus a feedback type, and it evaluates each
`(request, response)` pair against those instructions, returning a value and a
written rationale.

The tool is intended to be driven from the command line: point it at a file of
judge definitions and a file of test cases, and it will evaluate every test case
in turn.

## What the tool does

1. Loads judge definitions from a JSON Lines file (`--judge-file`).
2. Selects a single judge — either the only judge in the file, or the one whose
   `name` matches `--judge-name`.
3. Overrides the judge's model with `--model`.
4. Loads request/response test cases from a JSON Lines file (`--input-file`),
   optionally capped by `--limit`. The input/output field names default to
   `request`/`response` but are configurable via `--input-key`/`--output-key`.
5. Runs the judge against each test case.
6. Prints each result (verdict + rationale, plus optional test-case output).
7. Optionally writes the full results to a JSON Lines file (`--output-file`), and
   alongside it a `cases/` directory holding one JSON file per case.
8. Optionally drops into an interactive REPL afterwards (`--interactive`).

## Usage

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-judge.py" \
  --judge-file  <judges.jsonl> \
  --input-file  <test_cases.jsonl> \
  [--judge-name <name>] \
  [--model      <model>] \
  [--output-file <results.jsonl>] \
  [--limit      <n>] \
  [--input-key  <key>] \
  [--output-key <key>] \
  [--meta-key   <key>] \
  [-v | --verbose | --no-verbose] \
  [--force | --no-force] \
  [-i | --interactive | --no-interactive]
```

## Examples

> `data/` is read-only — never write `--output-file` (or its sibling `cases/`
> dir) there. Send output to a scratch path (`/tmp/…`) for ad-hoc runs, or to a
> structured path such as `runs/<judge>/<NNN>/outputs.jsonl` for saved runs.

Run the `harmless` judge over the test cases and write the results,
overwriting the output file if it already exists:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-judge.py" \
  --judge-file data/judges.jsonl \
  --judge-name harmless \
  --input-file data/test-cases.jsonl \
  --output-file /tmp/harmless.jsonl \
  --force
```

Run the `appropriate_title` judge over just the first 3 test cases and
write the results:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-judge.py" \
  --judge-file data/judges.jsonl \
  --judge-name appropriate_title \
  --input-file data/test-cases.jsonl \
  --output-file /tmp/appropriate_title.jsonl \
  --limit 3
```

## Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--judge-file` | yes | — | Path to a JSON Lines file of judge definitions. |
| `--input-file` | yes | — | Path to a JSON Lines file of request/response test cases to judge. |
| `--judge-name` | no | — | Name of the judge to run. Required only when the judge file contains more than one judge; the tool selects the judge whose `name` field matches. |
| `--model` | no | `gateway:/anthropic-claude-haiku-endpoint` | Model used to run the judge. Overrides the `model` field in the judge definition. |
| `--output-file` | no | — | Path to write results as JSON Lines. If omitted, results are only printed. |
| `--limit` | no | `0` | Maximum number of test cases to process. `0` means process all. |
| `--input-key` | no | `request` | Key in each test case used as the input passed to the judge (`inputs`). |
| `--output-key` | no | `response` | Key in each test case used as the output passed to the judge (`outputs`). |
| `--meta-key` | no | `sample_index` | Key looked up in each test case's `meta` object; its value is printed alongside the result to identify the test case. If the key is absent from `meta`, a synthesized `data-NNN` label (1-based, zero-padded to the test-case count) is used instead. |
| `-v` / `--verbose` / `--no-verbose` | no | `true` | When enabled, prints the judged response output along with the judge result. |
| `--force` / `--no-force` | no | `true` (force on) | Overwrite `--output-file` (and refresh the per-case `cases/` dir) if it already exists. On by default, since each iteration run targets a fresh directory. Pass `--no-force` to refuse and exit instead of overwriting. |
| `-i` / `--interactive` / `--no-interactive` | no | `false` | After running all cases, drop into an interactive Python REPL (`code.interact`) with the run's locals in scope (`judge`, `test_cases`, `args`, …). Intended for ad-hoc debugging. |

## Input formats

### Judge file (`--judge-file`)

A JSON Lines file where each line is a judge definition. Each definition maps
onto the fields of an MLflow `InstructionsJudge`:

| Field | Description |
|---|---|
| `name` | Judge name. Used by `--judge-name` to select a judge. |
| `instructions` | Natural-language instructions describing what the judge should evaluate. |
| `model` | Model the judge uses (overridden by `--model` when passed). |
| `description` | Optional human-readable description of the judge. |
| `feedback_value_type` | The type of value the judge returns as feedback. |

### Test case / input file (`--input-file`)

A JSON Lines file where each line is a single test case. The field names below
are configurable via `--input-key`/`--output-key`; the names shown are the
defaults (`request`/`response`).

| Field | Required | Description |
|---|---|---|
| `request` (`--input-key`) | yes | The input passed to the judge as `inputs` (the request that was made). |
| `response` (`--output-key`) | yes | The output passed to the judge as `outputs` (the response to be evaluated). |
| `meta` | no | An object of metadata about the test case. The value at `--meta-key` is printed to identify the case, falling back to a synthesized `data-NNN` label when the key is absent. |

## Output

### Printed output

For each test case, the tool prints:

- The metadata value at `--meta-key`, or a synthesized `data-NNN` label when the key is absent from `meta`.
- The judged response output (when `--verbose` is enabled).
- The judge's result value (`judge_result`).
- The judge's rationale (`judge_rationale`).

### Output file (`--output-file`)

When `--output-file` is provided, each result is written as one JSON object per
line with the following shape:

```json
{
  "inputs":  <request>,
  "outputs": <response>,
  "meta":    <meta object>,
  "judge_result": <judge result as a dictionary>
}
```

The output file is only created once there is a result to write. If the file
exists, the tool overwrites it by default; pass `--no-force` to make it refuse
and exit instead.

### Per-case files (`cases/`)

Whenever `--output-file` is given, the tool also writes a `cases/` directory
**alongside** the output file (e.g. `runs/<judge>/<NNN>/cases/` when the output
file is `runs/<judge>/<NNN>/outputs.jsonl`). It holds one pretty-printed JSON
file per test case, each containing the same full record as the corresponding
`outputs.jsonl` line:

```
cases/
  case-001.json
  case-002.json
  ...
```

Files are named by **zero-padded positional index** (`case-001`, `case-002`, …),
matching the order test cases appear in `--input-file` — **never** by any field
from within the record. Because the tool runs the full case set in the same
order each time, `case-NNN` is a stable handle for the same case across runs,
cheap to Read/grep and safe to cite elsewhere. The directory is `cases/` (deliberately distinct
from the combined `outputs.jsonl`, to avoid an `outputs/`-vs-`outputs.jsonl`
name collision). Each run refreshes it: stale `case-*.json` files are cleared
before the current set is written.
