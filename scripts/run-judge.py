#!/usr/bin/env python3

import os
import sys
import code
import json
import argparse
import pathlib
import math

from mlflow.genai.judges.instructions_judge import InstructionsJudge
import jsonlines

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action=argparse.BooleanOptionalAction, default=True, help='print test case output with judge output')
parser.add_argument('-i', '--interactive', action=argparse.BooleanOptionalAction, default=False, help='drop to REPL prompt after running')
parser.add_argument('--force', action=argparse.BooleanOptionalAction, default=True, help='overwrite output files if they exist (default: on; pass --no-force to refuse and exit instead)')
parser.add_argument('--judge-file', required=True, help='path to judges jsonlines')
parser.add_argument('--judge-name', help='judge name to run if more than 1 judge in judge-file input')
parser.add_argument('--limit', default=0, type=int, help='max number of test cases to process')
parser.add_argument('--input-key', default='request', help='key name of field to use as input passed to judge')
parser.add_argument('--output-key', default='response', help='key name of field to use as output passed to judge')
parser.add_argument('--meta-key', default='sample_index', help='meta key to assosciate with test case')
parser.add_argument('--model', default='gateway:/anthropic-claude-haiku-endpoint', help='judge model to use')
parser.add_argument('--input-file', required=True, help='jsonlines of request/response pairs to judge')
parser.add_argument('--output-file', help='output file of results')
args = parser.parse_args()

def print_result(r, meta_key=None, meta_value=None, outputs=None):
    print(f"\n========")
    if meta_key and meta_value:
        print(f"{meta_key}: {meta_value}")
    if outputs:
        print(f"judged_output: {outputs}")
    print(f"judge_result: {r.feedback.value}")
    print(f"judge_rationale: {r.rationale}\n")


output_path = pathlib.Path(args.output_file) if args.output_file else None
if output_path and output_path.exists() and args.force == False:
    print(f"Output path {output_path} exists; overwrite is refused because --no-force was passed")
    sys.exit(1)

# Per-case output directory: sits alongside --output-file as `cases/`, holding one
# JSON file per test case named by zero-padded POSITIONAL index (case-001.json, ...).
# Deliberately `cases/` (not `outputs/`) to avoid colliding with the combined
# outputs.jsonl. Only produced with --output-file.
cases_dir = output_path.parent / 'cases' if output_path else None

output_writer = None
num_written = 0

judges = list(jsonlines.open(args.judge_file))
if args.judge_name:
    judges = [x for x in judges if x['name'] == args.judge_name]
if not judges:
    print(f"Judge {args.judge_name} not found in {args.judge_file}")
    sys.exit(1)

jd = dict(judges[0])
if args.model:
    jd['model'] = args.model
judge = InstructionsJudge(**jd)

meta_key = args.meta_key

test_cases = list(jsonlines.open(args.input_file))
if args.limit > 0:
    test_cases = test_cases[:args.limit]

pad = int(math.log10(len(test_cases))) + 1 
print(f"Running judge '{judge.name}' on {len(test_cases)} item(s)")


for (ix, test_case) in enumerate(test_cases):
    inputs = test_case[args.input_key]
    outputs = test_case[args.output_key]
    meta = test_case.get('meta', {})
    meta_value = meta[meta_key] if meta_key in meta else f"data-{ix+1:>0{pad}}"
    judge_result = judge.run(inputs=inputs, outputs=outputs)
    print_result(judge_result, meta_key, meta_value, outputs if args.verbose else None)
    if output_path:
        result_dict = judge_result.to_dictionary()
        d = dict(inputs=inputs, outputs=outputs, meta=meta, judge_result=result_dict)
        if output_writer is None:
            if output_path.exists() and args.force == True:
                output_path.unlink()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_writer = jsonlines.open(output_path, 'w', flush=True)
            # Prepare the per-case directory once, clearing any stale case-*.json so a
            # re-run leaves exactly the current set (positional handles stay authoritative).
            cases_dir.mkdir(parents=True, exist_ok=True)
            for stale in cases_dir.glob('case-*.json'):
                stale.unlink()
        output_writer.write(d)
        # Positional index is 1-based and zero-padded to three digits: case-001.json.
        case_path = cases_dir / f"case-{ix + 1:03d}.json"
        with open(case_path, 'w') as cf:
            json.dump(d, cf, indent=2)
        num_written += 1



if output_writer:
    output_writer.close()

if num_written:
    print(f"Wrote {num_written} to {output_path}")
    print(f"Wrote {num_written} per-case file(s) to {cases_dir}/ (case-001.json ...)")

if args.interactive:
    code.interact(local=locals())
sys.exit(0)
################################################################################
# EOF
################################################################################

