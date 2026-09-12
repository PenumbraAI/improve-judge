# Judge iteration loop

A skeleton for iterating on an LLM-as-a-judge **prompt**. This is not a
"judge the judge" system — there is no ground truth. Each stage inspects the
judge's own behaviour and reflects on it, and changes to the judge prompt are
gated by an editorial review before being applied.

## Directory contract

Everything lives under `runs/`. One directory per judge, one sub-directory per
iteration (zero-padded, `001`, `002`, ...):

```
runs/<judge>/<NNN>/
  judge.jsonl           # the judge definition used THIS iteration (one JSONL line)
  outputs.jsonl         # stage 1 — run-judge.py output (verdicts + rationales + provenance)
  cases/                # stage 1 — one JSON file per case, keyed by positional case-NNN
    case-001.json       #          (full record; cheap to Read/grep; stable handle to cite)
    ...
  iter-report.md        # stage 2 — reflection on the judge's outputs
  parked.md             # stage 2 — parked-case ledger (cross-iteration state; copied forward)
  proposed-updates.md   # stage 3 — discrete proposals, each justified w/ concrete examples
  accepted-updates.md   # stage 4 — editorial review; only material proposals survive
```

Stage 5 writes the **next** iteration's seed, `runs/<judge>/<NNN+1>/judge.jsonl`,
closing the loop; it also copies `parked.md` forward into the next directory when
one exists (`(N)/parked.md → (N+1)/parked.md`). It writes nothing into the current
directory.

**Case handle.** Cases are keyed by their positional index `case-NNN`
(`case-001`, `case-002`, …), matching the `cases/` files stage 1 writes — **never**
any field from within the record. Stage 1 runs the full case set
in the same order every iteration (parked cases included — parking only suppresses
prompt updates, not execution), so `case-NNN` identifies the same case across all
iterations by construction. Every cross-stage and cross-iteration case reference
uses this handle.

`data/` is read-only. Test cases are read from `data/test-cases.jsonl`; nothing
under `data/` is ever written. A judge and real test-case set ship in
`examples/` (see the plugin README's "Try it" section) if you want to see
the loop run before supplying your own `data/`.

## The five stages

Each stage is a reusable subagent in `agents/`. There is no
orchestrator — you invoke each one yourself (or ask the main agent to), passing
it the iteration directory. Loose coupling: every stage reads files and writes
exactly one artifact, so stages are independently re-runnable.

| Stage | Subagent | Model | Reads | Writes |
|---|---|---|---|---|
| 1 | `judge-runner` | haiku | `judge.jsonl`, `data/test-cases.jsonl` | `outputs.jsonl`, `cases/case-NNN.json` |
| 2 | `judge-reporter` | sonnet | `judge.jsonl`, `outputs.jsonl`, `cases/`, inherited `parked.md`, **all earlier** `iter-report.md` + `accepted-updates.md` | `iter-report.md`, `parked.md` |
| 3 | `judge-proposer` | sonnet | `judge.jsonl`, `iter-report.md`, `outputs.jsonl`, `cases/`, `parked.md` | `proposed-updates.md` |
| 4 | `judge-editor` | sonnet | `judge.jsonl`, `proposed-updates.md`, `iter-report.md`, `parked.md` | `accepted-updates.md` |
| 5 | `judge-synthesizer` | sonnet | `judge.jsonl`, `accepted-updates.md`, `parked.md` | `runs/<judge>/<NNN+1>/judge.jsonl`, `runs/<judge>/<NNN+1>/parked.md` |

Note the editor (stage 4) reads `iter-report.md` and `parked.md` only for the
reporter's recurrence flags and the parked set — **not** to verify a proposal's
evidence. It rules on each proposal as presented and never opens `outputs.jsonl`
or the `cases/` files (see the artifact-format notes below).

The editorial gate (stage 4) exists because proposer agents tend to suggest
endless immaterial changes; only proposals that pass materiality review reach
the synthesizer.

## Artifact-format contract

The loose coupling above works only if each artifact carries stable handles the
next stage can rely on, rather than re-quoting the previous stage's prose.

- **`iter-report.md` (stage 2).** Cites cases by `case-NNN` and states an explicit
  pass/fail verdict for every case it discusses, so a later reporter can read it
  and detect **recurrence** (a case failing now that an earlier report also judged
  failing). Includes a one-line "N cases parked" count. This is a light prose
  requirement — enough for history to be parseable, not a machine schema.
- **`proposed-updates.md` (stage 3).** Each proposal carries a stable **ID**
  (`P-<NNN>-<nn>`), a one-line title, its **motivating `case-NNN`(s)**, and its
  evidence embedded **in full**. Proposals are self-contained: the editor rules on
  them as presented and does not fetch the source data.
- **`accepted-updates.md` (stage 4).** Records an ACCEPT/REJECT + reason for every
  proposal *by ID*. For each accepted proposal it carries, ready for the
  synthesizer to apply without reconstructing from prose: the **verbatim final
  instruction text**, an **explicit anchor** (sentence/heading to follow, or text
  to replace), the **ID**, and the **motivating `case-NNN`(s)** carried through.
  The editor reads neither `outputs.jsonl` nor `cases/`.
- **`parked.md` (stage 2, copied forward by stage 5).** Cross-iteration ledger of
  cases the loop has stopped trying to prompt-fix.

### Parking

A **parked** case is one the loop no longer tries to fix by re-wording the prompt
— but it is still executed by stage 1 every iteration (parking suppresses *updates*,
not execution). The reporter owns park/unpark and writes `parked.md`; the
synthesizer copies it forward verbatim so each iteration folder is self-contained
and a parked case can only leave the ledger through a deliberate unpark, never
silent omission.

- **Trigger (policy knob `N = 2`).** Park `case-NNN` when the reporter judges it
  failing in the current iteration **and** ≥ N earlier iterations each accepted a
  prompt change naming that `case-NNN` as a motivating case (two failed fixes →
  park on the third failure). The count comes from the motivating `case-NNN`(s)
  recorded in earlier `accepted-updates.md`, which is why items above require that
  attribution to be carried through.
- **Parking vs recurrence.** Recurrence only needs earlier reports to have judged
  a case failing; parking additionally needs ≥ N *accepted fixes* spent on it.
  Recurrence is the broad detection signal; parking is the actionable subset.
- **Two-layer backstop.** The proposer skips parked cases; the editor rejects any
  proposal that re-litigates one.
- **Disposition.** Each parked entry records a status history and a disposition
  category — *needs ground truth / ambiguous*, *model non-compliance*, or
  *suspected test-case / data problem* — standing in for "escalate".

## Two different models

Do not confuse them:

- **Subagent model** — the model the *stage* runs on (the table above).
- **Judge-under-test model** — the model the judge itself uses to evaluate,
  passed to `run-judge.py` via `--model`. The seeded `judge.jsonl` records it in
  its `model` field, typically an MLflow gateway route (e.g.
  `gateway:/anthropic-claude-haiku-endpoint`); the runner passes it through
  as-is, without judging whether it looks valid. (Seeding sets it to
  `JUDGE_MODEL`, the model requested for that run — see below — which may
  differ from whatever `data/judges.jsonl` itself carries; that's a deliberate
  run parameter, not a correction.)

## Invoking a stage

Give the subagent the iteration directory. For example:

- "Use the **judge-runner** agent on `runs/appropriate_title/001`"
- "Use the **judge-reporter** agent on `runs/appropriate_title/001`"
- ... and so on through stage 5.

Run stages for different judges in parallel by launching multiple subagents at
once.

## Orchestrating the loop

The five stages can be driven by hand (as above) or by an **orchestrator** — a
main-agent prompt that runs one judge's loop end to end: it seeds iteration 001
and invokes stages 1→5 for each iteration up to a cap (stopping early on
convergence). The reusable prompt ships as the `kickoff` skill
(`skills/kickoff/SKILL.md`), invoked as `/improve-judge:kickoff <judge_name>`
once the plugin is installed.

The orchestrator runs as the **main agent of its session** (a skill without
`context: fork` loads inline rather than spawning an isolated subagent), so
parallelism across judges is one **session per judge**: invoke the skill once per
judge, each an independent orchestrator.

## Seeding a new judge's first iteration

Copy one judge out of the read-only `data/judges.jsonl` into
`runs/<judge>/001/judge.jsonl`:

```bash
JUDGE=appropriate_title
mkdir -p "runs/$JUDGE/001"
python3 - "$JUDGE" <<'PY'
import sys, json, jsonlines, pathlib
name = sys.argv[1]
j = next(x for x in jsonlines.open("data/judges.jsonl") if x["name"] == name)
j["model"] = "gateway:/sonnet"  # set to the judge-under-test model requested for this run
out = pathlib.Path(f"runs/{name}/001/judge.jsonl")
with jsonlines.open(out, "w") as w:
    w.write(j)
print("seeded", out)
PY
```
