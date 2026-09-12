---
name: kickoff
description: Run the judge iteration loop end-to-end for one judge — seeds iteration 001, drives the five stage subagents through each iteration, and stops on convergence or a cap.
arguments: [judge_name]
---

You are the ORCHESTRATOR for ONE judge's iteration loop. You run as the main
agent of this session: you invoke each stage subagent in turn. You do NOT run
the stages inline — always delegate to the stage subagents.

## Parameters
JUDGE                 = $judge_name         # name of judge, required; e.g. 'appropriate_title'
MAX_ITERS             = 5                   # hard cap on iterations this run
JUDGE_MODEL           = gateway:/anthropic-claude-haiku-endpoint # judge-under-test model (stage 1 --model)
STOP_ON_CONVERGENCE   = true                # stop early if an iteration accepts 0 proposals
CASE_LIMIT            = 0                   # 0 = all cases; >0 = --limit for cheap smoke runs

## 1. Orient
Read: `${CLAUDE_PLUGIN_ROOT}/doc/iteration-loop.md`, `${CLAUDE_PLUGIN_ROOT}/doc/tool-run-judge.md`.
Check your MEMORY index for standing rules before touching cases.

## 2. Constraints (respect exactly)
- data/ is READ-ONLY. All run artifacts live under runs/<JUDGE>/<NNN>/.
- Cases are ALWAYS keyed by positional case-NNN, never by any field from within
  the record.
- Real gateway LLM calls are AUTHORIZED for this run (respect CASE_LIMIT).
- Invoke each stage via its subagent (judge-runner / -reporter / -proposer / -editor
  / -synthesizer), passing the iteration directory. Do not edit the agent defs or
  the contract — orchestration lives only here.

## 3. Seed iteration 001 (only if runs/<JUDGE>/001/judge.jsonl is absent)
Copy that judge out of read-only data/judges.jsonl into runs/<JUDGE>/001/judge.jsonl,
setting model to JUDGE_MODEL. Use the seeding snippet in
`${CLAUDE_PLUGIN_ROOT}/doc/iteration-loop.md`.
If JUDGE is not found in data/judges.jsonl, STOP immediately and report it — this
is almost certainly a typo in JUDGE or missing data, not something to work around.
Do not continue or invent a judge.

## 4. The loop (NNN = 001 .. MAX_ITERS)
For each iteration NNN:
  a. For stage in [1 runner, 2 reporter, 3 proposer, 4 editor]:
       - Invoke the stage subagent on runs/<JUDGE>/<NNN>/ (stage 1 also passes
         --model JUDGE_MODEL, and --limit CASE_LIMIT if CASE_LIMIT > 0; the runner
         def doesn't expose --limit, so for a limited run invoke run-judge.py
         directly for stage 1 only — remember to also pass --input-key/
         --output-key if the test cases aren't shaped request/response, same as
         the runner would).
       - When it returns, verify its work yourself from the artifact on disk —
         never trust a subagent's self-reported line/record counts — verify
         with wc -l / a jsonl count / a verdict tally.
  b. Convergence check: read <NNN>/accepted-updates.md. If the editor accepted ZERO
     proposals (judge prompt would not change) and STOP_ON_CONVERGENCE is true,
     STOP the whole loop (do not run stage 5, do not seed the next iteration).
  c. Otherwise invoke stage 5 (synthesizer) on <NNN>/. It seeds
     runs/<JUDGE>/<NNN+1>/judge.jsonl (and copies parked.md forward).
  d. If NNN == MAX_ITERS: stage 5 has just seeded <MAX_ITERS+1>/ — STOP there
     (do NOT run stage 1 of the next iteration).

## 5. Report
After each iteration: one line — verdict tally, parked-case count, proposals
accepted. At the end: state whether the loop stopped by CONVERGENCE or the
MAX_ITERS cap, summarize how the judge prompt evolved, and list parked cases with
disposition. Confirm the final seeded directory.
