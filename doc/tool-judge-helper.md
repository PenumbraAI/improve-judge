# tool: judge-helper.py

## Overview

`judge-helper.py` manages MLflow-registered judges (scorers) on a running
MLflow tracking server: listing, starting/stopping automatic evaluation,
switching a judge's model, pinging a model-gateway endpoint, and
importing/exporting judge definitions as JSON Lines. It's a server-management
utility, distinct from `run-judge.py` (which runs a judge locally against
test cases and never touches the tracking server's registered scorers).

Every invocation connects to MLflow first (`--tracking-uri` and
`--experiment`, or their env-var equivalents) before dispatching to a
command — so all commands, including read-only ones, require a resolvable
tracking URI and experiment.

## Usage

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/judge-helper.py" [--tracking-uri <uri>] [-x/--experiment <name-or-id>] \
  <command> [file] [--stdio] [--start | --no-start] [--model <model>]
```

## Commands

| Command | Positional `file` | Description |
|---|---|---|
| `info` | — | Prints experiment id/name/lifecycle stage, then lists registered judges. |
| `list` | — | Lists registered judges: name, model, feedback type, status. |
| `start` | — | Starts automatic evaluation (`sample_rate=1.0`) on every registered judge. Errors if none are registered. |
| `stop` | — | Stops automatic evaluation on every registered judge. Errors if none are registered. |
| `set-model` | new model string (required) | Re-registers every judge whose model differs from the given value, under the new model. Judges already on that model are skipped. |
| `ping-gw` | gateway endpoint name (or use `--model`) | POSTs a test message to `{tracking-uri}/gateway/{endpoint}/mlflow/invocations`; reports OK/FAIL. |
| `export` | output path (or `--stdio`) | Writes every registered judge's `name`/`model`/`instructions`/`feedback_value_type` as JSON Lines. |
| `import` | input path (or `--stdio`) | Reads judge definitions as JSON Lines and registers (or updates) each one. |

## Options

| Option | Applies to | Description |
|---|---|---|
| `--tracking-uri` | all | MLflow tracking URI. Default: `$MLFLOW_TRACKING_URI`. |
| `-x`, `--experiment` | all | Experiment name or numeric id. Default: `$MLFLOW_EXPERIMENT_NAME` / `$MLFLOW_EXPERIMENT_ID`. |
| `--stdio` | `export`, `import` | Write to stdout / read from stdin instead of the `file` positional. Mutually exclusive with `file`. |
| `--start` / `--no-start` | `import` | Start automatic evaluation (`sample_rate=1.0`) on each imported judge. Default: `--no-start`. |
| `--model` | `export`, `import`, `ping-gw` | `export`/`import`: overrides every judge's model instead of using each judge's own. `ping-gw`: the endpoint to ping, as an alternative to the `file` positional. |

## Registering vs. updating

Importing or `set-model`-ing a judge that already exists behaves differently
depending on the backend:

- **Databricks tracking URI** (`databricks`, `databricks:...`, `databricks-uc...`):
  the scorer store is insert-only for new names, so an existing judge is
  updated in place instead, preserving its current sample rate and filter.
- **Everything else** (e.g. an MLflow server): every import/`set-model` call
  registers a new version via `.register()` —
  an MLflow API method on the judge object `mlflow.genai.judges.make_judge()`
  returns, not something defined in this script. It persists that judge
  object to the tracking server's scorer store as a new entry.

## Notes

- `list`/`info`/`start`/`stop` operate on **all** registered judges — there's
  no per-judge filter.
- `set-model`'s new-model value is passed positionally as `file`, not via a
  dedicated flag — easy to misread from the CLI signature alone.
