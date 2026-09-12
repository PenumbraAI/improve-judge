# improve-judge

Iterate on an LLM-as-a-judge prompt: run it over test cases, reflect on its
verdicts, gate proposed prompt edits through editorial review, and seed the
next iteration. See `doc/iteration-loop.md` for the full stage contract.

## Prerequisites

- An MLflow tracking server reachable from the environment (`MLFLOW_TRACKING_URI`).
  See [MLFlow Configuration](#mlflow-configuration) below for details.
- Python 3 with `mlflow`, `jsonlines`, and `requests` installed. This plugin
  does not install these — Claude Code has no Python dependency mechanism, so
  run e.g. `pip install mlflow jsonlines requests` before using it.
- A project with `data/test-cases.jsonl` (and, if seeding via the kickoff
  skill, `data/judges.jsonl`) — see `doc/tool-run-judge.md`.

## Install

```
/plugin marketplace add PenumbraAI/improve-judge
/plugin install improve-judge@improve-judge
```
(https://github.com/PenumbraAI/improve-judge)

For local development instead, run against a checked-out copy:

```bash
claude --plugin-dir ./improve-judge
```

## Try it

A judge and 10 real test cases ship in `examples/`, so you can see the loop
run before wiring up your own data. The test cases use their original field
names (`risk_text`/`risk`) rather than the tool's `request`/`response`
defaults — on purpose, to demonstrate `run-judge.py`'s `--input-key`/
`--output-key` options (see `doc/tool-run-judge.md`); `judge-runner` picks
these up by inspection, no extra setup required. In a Claude Code session
with this plugin enabled, ask Claude to seed your project from them (it can
resolve `${CLAUDE_PLUGIN_ROOT}/examples/`), e.g.:

> copy improve-judge's example judge and test cases into data/

(If you're testing locally via `--plugin-dir ./improve-judge`, you can instead
run `mkdir -p data && cp improve-judge/examples/*.jsonl data/` directly — if
you installed the published plugin instead, asking Claude is the way to go,
since you won't have a local `improve-judge/` path to `cp` from.) Then:

```
/improve-judge:kickoff appropriate_title
```

## Usage

Run the full loop for one judge:

```
/improve-judge:kickoff <judge_name>
```

Or drive the five stages by hand — see `doc/iteration-loop.md` — invoking
`judge-runner`, `judge-reporter`, `judge-proposer`, `judge-editor`, and
`judge-synthesizer` on an iteration directory (`runs/<judge>/<NNN>/`).

## Scripts

- `scripts/run-judge.py` — runs a judge over test cases locally (see
  `doc/tool-run-judge.md`).
- `scripts/judge-helper.py` — manages judges registered on the MLflow tracking
  server: list/start/stop/set-model/import/export/ping-gw (see
  `doc/tool-judge-helper.md`).


## MLFlow Configuration

### Tracking Server

Start a local server with

```
mflow server
```

See https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/ for details.

### Environment Variables

Configure the environment with the MFLow Tracking Server and Experiment information:

```
export MLFLOW_TRACKING_URI="http://127.0.0.1:5000"
export MLFLOW_EXPERIMENT_ID="0"
```

Or, add them to .claude/settings.json 

```
  "env": {
    "MLFLOW_TRACKING_URI": "http://127.0.0.1:5000",
    "MLFLOW_EXPERIMENT_ID": "0"
  }
```

### Judge AI Gateway Endpoint

An AI Gateway Endpoint configured in MLFlow is required. See here for more 
information https://mlflow.org/docs/latest/genai/governance/ai-gateway/quickstart/

The example assumes an endpoint named anthropic-claude-haiku-endpoint
accessed as `gateway:/anthropic-claude-haiku-endpoint`

This can be set as part of the judges configuration or overridden with the `--model` argument  


