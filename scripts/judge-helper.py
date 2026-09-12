#!/usr/bin/env python3

import argparse
import logging
import os
import sys
import json

import requests

import jsonlines
import mlflow
from mlflow.genai import list_scorers

# Quiet mlflow's INFO chatter; keep warnings and errors.
logging.getLogger("mlflow").setLevel(logging.WARNING)
from mlflow.genai.judges import make_judge
from mlflow.genai.scorers import ScorerSamplingConfig

FEEDBACK_TYPE_MAP = {
    "bool": bool,
    "str": str,
    "int": int,
    "float": float,
}


def feedback_type_to_str(ft) -> str:
    if ft is bool:
        return "bool"
    if ft is str:
        return "str"
    if ft is int:
        return "int"
    if ft is float:
        return "float"
    return repr(ft)


def str_to_feedback_type(s: str):
    if s in FEEDBACK_TYPE_MAP:
        return FEEDBACK_TYPE_MAP[s]
    raise ValueError(f"Unknown feedback_value_type: {s}")


def is_databricks_uri(uri: str) -> bool:
    # Matches how mlflow routes to its Databricks scorer store: the bare
    # "databricks" URI or any "databricks://" / "databricks-uc" profile URI.
    return uri == "databricks" or uri.startswith("databricks:") or uri.startswith("databricks-uc")


def get_tracking_uri(tracking_uri=None):
    tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri is None and not mlflow.is_tracking_uri_set():
        raise ValueError(f"No tracking_uri provided")
    return tracking_uri or mlflow.get_tracking_uri()


def get_experiment(experiment=None):
    # returns (experiment_name=None, experiment_id=int) or (experiment_name=str, experiment_id=None)
    experiment = experiment or os.environ.get("MLFLOW_EXPERIMENT_NAME") or os.environ.get("MLFLOW_EXPERIMENT_ID")
    if experiment is None:
        raise ValueError(f"No experiment provided")
    try:
        return (None, int(experiment))
    except ValueError:
        return (experiment, None)


def set_mlflow(tracking_uri=None, experiment=None):
    tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    (experiment_name, experiment_id) = get_experiment(experiment)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name=experiment_name, experiment_id=experiment_id)



def print_experiment(experiment=None):
    (experiment_name, experiment_id) = get_experiment(experiment)
    if experiment_name:
        e = mlflow.get_experiment_by_name(experiment_name)
    else:
        e = mlflow.get_experiment(experiment_id)
    print(f"Experiment: id={e.experiment_id} name={e.name} lifecycle_stage={e.lifecycle_stage}")


def register_or_update(judge, tracking_uri, existing):
    # The Databricks scorer store is insert-only: re-registering a name that
    # already exists raises ValueError. When we know the judge already exists
    # there, update it in place instead, preserving its current sampling rate
    # (a stopped judge has rate 0, which update() rejects, so pass None to
    # leave the rate untouched). Every other case uses register(), which the
    # open-source MLflow backend treats as a new version.
    #
    # Both branches return the object that is actually registered in the store,
    # which is the one callers must .start()/.stop() on. register() returns a
    # fresh registered scorer (the passed-in `judge` stays unregistered), while
    # update() mutates and returns the existing scorer.
    if existing is not None and is_databricks_uri(tracking_uri):
        rate = existing.sample_rate
        return judge.update(
            sampling_config=ScorerSamplingConfig(
                sample_rate=rate if rate and rate > 0 else None,
                filter_string=existing.filter_string,
            )
        )
    return judge.register()


def export_judges(args):

    scorers = list_scorers()
    print(f"Found {len(scorers)} scorer(s)", file=sys.stderr)

    records = []
    for s in scorers:
        record = {
            "name": s.name,
            "model": args.model or s.model,
            "instructions": s.instructions,
            "feedback_value_type": feedback_type_to_str(s.feedback_value_type),
        }
        records.append(record)
        print(f"  Exported: {s.name}", file=sys.stderr)

    if args.stdio:
        writer = jsonlines.Writer(sys.stdout)
        for record in records:
            writer.write(record)
        writer.close()
    else:
        with jsonlines.open(args.file, mode="w") as writer:
            for record in records:
                writer.write(record)
        print(f"Written to {args.file}", file=sys.stderr)


def import_judges(args):

    if args.stdio:
        reader = jsonlines.Reader(sys.stdin)
        records = list(reader)
        reader.close()
    else:
        with jsonlines.open(args.file) as reader:
            records = list(reader)

    print(f"Found {len(records)} judge(s)", file=sys.stderr)

    existing_by_name = {s.name: s for s in list_scorers()}

    for record in records:
        judge = make_judge(
            name=record["name"],
            model=args.model or record["model"],
            instructions=record["instructions"],
            feedback_value_type=str_to_feedback_type(record["feedback_value_type"]),
        )
        registered = register_or_update(judge, args.tracking_uri, existing=existing_by_name.get(record["name"]))
        if args.start:
            registered.start(sampling_config=ScorerSamplingConfig(sample_rate=1.0))
            print(f"  Registered and started: {record['name']}", file=sys.stderr)
        else:
            print(f"  Registered: {record['name']}", file=sys.stderr)

    print("Done.", file=sys.stderr)


def list_judges(args):

    scorers = list_scorers()
    if not scorers:
        print("No judges registered.")
        return

    num_judges = len(scorers)
    for (ix, s) in enumerate(scorers):
        status = s.status.value if s.status else "unknown"
        print(f"Judge {ix + 1}/{num_judges}: name={s.name}  model={s.model}  feedback_type={feedback_type_to_str(s.feedback_value_type)}  status={status}")


def start_judges(args):

    scorers = list_scorers()
    if not scorers:
        print("No judges registered.", file=sys.stderr)
        sys.exit(1)

    for s in scorers:
        s.start(sampling_config=ScorerSamplingConfig(sample_rate=1.0))
        print(f"  Started: {s.name}", file=sys.stderr)

    print("Done.", file=sys.stderr)


def stop_judges(args):
    scorers = list_scorers()
    if not scorers:
        print("No judges registered.", file=sys.stderr)
        sys.exit(1)

    for s in scorers:
        s.stop()
        print(f"  Stopped: {s.name}", file=sys.stderr)

    print("Done.", file=sys.stderr)


def set_model(args):
    new_model = args.file  # second positional arg is the new model string
    if not new_model:
        print("Error: set-model requires the new model string as the second argument", file=sys.stderr)
        sys.exit(1)

    scorers = list_scorers()
    if not scorers:
        print("No judges registered.", file=sys.stderr)
        sys.exit(1)

    for s in scorers:
        if s.model == new_model:
            print(f"  Skipped (already set): {s.name}", file=sys.stderr)
            continue
        judge = make_judge(
            name=s.name,
            model=new_model,
            instructions=s.instructions,
            feedback_value_type=s.feedback_value_type,
        )
        register_or_update(judge, args.tracking_uri, existing=s)
        print(f"  Updated: {s.name}  model={new_model}", file=sys.stderr)

    print("Done.", file=sys.stderr)


def ping_gateway(args):
    if args.model:
        endpoint = args.model
    else:
        endpoint = args.file
    if not endpoint:
        print("Error: ping-gw requires --model or the gateway endpoint name as the second argument", file=sys.stderr)
        sys.exit(1)

    endpoint = endpoint.replace('gateway:/', '')
    url = f"{args.tracking_uri}/gateway/{endpoint}/mlflow/invocations"
    try:
        resp = requests.post(url, json={"messages": [{"role": "user", "content": "ping"}]})
        if resp.status_code == 200:
            print(f"OK: {endpoint} returned 200")
            sys.exit(0)
        else:
            body = resp.text[:200] if resp.text else ""
            print(f"FAIL: {endpoint} returned {resp.status_code}\n{body}", file=sys.stderr)
            sys.exit(1)
    except requests.ConnectionError as e:
        print(f"FAIL: could not connect to {url}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Export/import MLflow judges")
    parser.add_argument(
        "--tracking-uri",
        help="MLflow tracking URI (default: $MLFLOW_TRACKING_URI)",
    )
    parser.add_argument(
        "-x",
        "--experiment",
        help="MLflow experiment name (default: $MLFLOW_EXPERIMENT_NAME/$MLFLOW_EXPERIMENT_ID)",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        default=False,
        help="Read from stdin (import) or write to stdout (export)",
    )
    parser.add_argument(
        "--start",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Start automatic evaluation after import (default: --no-start)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the model for all judges on import/export (default: use each judge's own model)",
    )
    parser.add_argument("command", choices=["export", "import", "list", "start", "stop", "set-model", "ping-gw", "info"], help="Command to run")
    parser.add_argument("file", nargs="?", default=None, help="Input/output JSONL file path")

    args = parser.parse_args()

    set_mlflow(args.tracking_uri, args.experiment)
    args.tracking_uri = get_tracking_uri(args.tracking_uri)

    if args.command == "list":
        list_judges(args)
        return

    if args.command == "start":
        start_judges(args)
        return

    if args.command == "stop":
        stop_judges(args)
        return

    if args.command == "set-model":
        set_model(args)
        return

    if args.command == "ping-gw":
        ping_gateway(args)
        return

    if args.command == "info":
        print_experiment(args.experiment)
        list_judges(args) 
        return

    if args.stdio and args.file:
        print("Error: cannot specify both --stdio and a file path", file=sys.stderr)
        sys.exit(1)

    if not args.stdio and not args.file:
        if args.command == "export":
            print("Error: export requires an output file path or --stdio", file=sys.stderr)
        else:
            print("Error: import requires an input file path or --stdio", file=sys.stderr)
        sys.exit(1)

    if args.command == "export":
        export_judges(args)
    elif args.command == "import":
        import_judges(args)


if __name__ == "__main__":
    main()
