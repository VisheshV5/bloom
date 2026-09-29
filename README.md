---
tags: [agentapp, collaborative, multi-agent]
dataset: []
framework: [flower]
---

# Bloom: a self-growing team of Flower Agents

Multi-agent systems are hand-assembled: when a team hits a task outside its skills, a
developer writes a new agent. **Bloom's team grows itself.** It starts as one generalist.
When it keeps failing a category of tasks, the Forge (Architect, Builder, and Reviewer
agents) designs, writes, and tests a new specialist. After a human approves it, the
specialist joins the federation as a new SuperNode and collaborates with the rest of the
team over Flower's Grid.

**Demo:** start with 1 agent, end with 6 (5 written by Bloom), which then solve a
multi-part data question together: dates → SQL → statistics → an executive note.

Built for the Flower Collaborative Agent Hackathon (Stanford, 2026-09-29).

## How it works

```
 Local laptop (the Forge: all side effects, human approval)         Flower federation
 ┌──────────────────────────────┐   start run (prompt=job)   ┌──────────────────────────────┐
 │ evaluator: benchmark + gaps  │ ─────────────────────────▶ │ bloom AgentApp @ SuperLink    │
 │ forge: architect/builder/    │ ◀── BLOOM_RESULT (logs) ── │  orchestrator (Endeavor)      │
 │        reviewer runs, y/N    │                            │   get_nodes / push / pull     │
 │ registry.json, dashboard     │                            └──────────────┬───────────────┘
 │ starts SuperNodes ───────────┼──────────────▶ ┌─────────────────┐        │ Grid messages
 └──────────────────────────────┘                │ bloom @SuperNode │◀───────┘
                                                 │ specialist role  │  push_reply_message
                                                 └─────────────────┘
```

- **One Flower app, `bloom`** (`bloom/`). Its role is picked at runtime:
  - **orchestrator** (SuperLink side): plans with Endeavor, lists SuperNodes, sends each step to a specialist over the Grid, and passes results along.
  - **specialist** (SuperNode side, triggered by a Grid message): loads its spec, runs the model with local tools (SQL, stats, dates, units, regex, calculator), and replies once.
  - **architect / builder / reviewer / solve**: Forge "thinking" jobs, each one short run.
- **Routing tiers:** (1) a SuperNode dedicated to that specialist, found by node id or name; (2) any SuperNode, with the spec in the payload; (3) in-process. `auto` degrades 1 → 2 → 3, so the demo never hard-fails on the Grid.
- **The Forge** (`forge/`) runs locally and owns every side effect: it writes the module, updates `registry.json`, starts SuperNodes, and (optionally) publishes, but only after `y` at the terminal.
- **What a specialist is:** a generated Python module with (1) focused instructions,
  (2) a curated subset of Bloom's tools, (3) **worked examples**: the dev tasks the team
  failed, each with a correct method (the exact SQL query, tool calls, and result),
  and (4) a **self-check step**: after drafting an answer, it re-verifies it with its tools
  in a category-specific way (e.g. "re-derive with a differently written query", "convert
  back to the original units") and corrects itself if needed. Worked examples only ever come
  from dev tasks, never from the held-out test set.
- **Growth triggers:** a benchmark category below 60% over the last 5 tasks, or the planner asking for a capability that no agent has (for example a report writer).

## What is verified (2026-09-28, flwr 1.39.0)

Tested on a **local Flower SuperLink** with a fake model server (`scripts/local_stack.sh`):

| Check | Result |
|---|---|
| Bloom app runs in the real Flower runtime; tools and SQL work in-process | ✅ |
| `instructions`, `tools`, and `tool_choice` reach the model provider | ✅ (U6) |
| Orchestrator → SuperNode → `push_reply_message` → orchestrator over the Grid | ✅ Tier 2 and Tier 1 |
| `flower-supernode --node-config 'bloom-specialty="…"'` reaches `context.node_config` | ✅ (U2) |
| A SuperNode started later is visible to the next run without restarting anything | ✅ (U3) |
| Multi-step plan with a handoff between specialists | ✅ |
| Full Forge cycle (Architect → Builder → Reviewer tests → retries) as real AgentApp runs | ✅ |
| Several local SuperNodes on one laptop (distinct ports) | ✅ (U7) |

**Important finding:** in flwr 1.39, **`flwr run` cannot start AgentApp runs**. The
SuperLink rejects them ("A user prompt is required"), and only `flwr chat` sends a
prompt. Bloom starts runs the same way chat does (`forge/flower_client.py`), so this also
applies to `flwr run @vverm/bloom-test-hello supergrid ...`. Smoke-test apps with
`flwr chat` instead.

**Still unverified on SuperGrid itself** (needs allow-listing): registering our own
SuperNodes against SuperGrid, whether `--name` shows up in `get_nodes`, and SuperGrid run
latency. Code paths are marked `# UNVERIFIED(U#)`; see `BLOOM_SPEC.md` §2.2.

## Quickstart

```bash
uv sync
uv run pytest                     # 76 tests
uv run flwr build                 # builds vverm.bloom.0-1-0.*.fab
```

### 1. Mock demo (no Flower runtime, deterministic, ~90 s)

```bash
uv run python -m dashboard.server          # http://localhost:8765
uv run python -m forge demo --backend mock --fresh            # approve each specialist with y
uv run python -m forge demo --backend mock --fresh --auto-approve --speed 1   # hands-free
```

`--fresh` moves the current `registry.json`, events, and generated specialists into
`runs/backup/<timestamp>/` (nothing is deleted) and starts from the generalist alone.

### 2. Real Flower runtime on your laptop (local SuperLink)

```bash
scripts/local_stack.sh start              # fake model; or: export FLWR_MODEL_API_KEY=... && scripts/local_stack.sh start-real
export FLWR_HOME=$PWD/runs/flwr-home
export FLWR_MODEL_API_ENDPOINT=http://127.0.0.1:8080/v1/responses FLWR_MODEL_API_KEY=local-mock   # fake-model mode only
uv run python -m forge bench --backend supergrid --connection local-agent --join local --limit 10
scripts/local_stack.sh stop
```

With a real `FLWR_MODEL_API_KEY` (flower.ai → Profile → Settings → API Keys), this runs
real models through a real Flower runtime, with real SuperNodes, without SuperGrid access.

### 3. SuperGrid (day of)

```bash
uvx --from flwr==1.39.0 flwr login supergrid
uv run python -m forge bench --backend supergrid --connection supergrid --dry-run --limit 1   # prints what it would do
uv run python -m forge bench --backend supergrid --connection supergrid --limit 10
uv run python -m forge final --backend supergrid --connection supergrid
# Real SuperNodes (every command asks y/N first):
uv run python -m forge grow --category sql --backend supergrid --join node --federation @vverm/<federation>
```

## Telemetry and the dashboard views

Every model call and tool call is recorded as a timed span (`bloom/trace.py`): model,
phase (solve / self-check), tokens in/out, tool arguments and a result preview. Specialists
send their spans back inside the Grid reply, and the coordinator adds each step's Grid
message id and timing. The dashboard has three views:

- **Main screen:** the story in plain English (steps, headline, agent cards, before/after).
- **P, evaluation report:** stat cards, per-skill gain with bootstrap intervals (forest plot),
  standard vs hard, accuracy vs cost, and the method. Mock runs are stamped SIMULATED.
- **T, agent internals:** a waterfall of the latest multi-agent run (Endeavor planning run,
  each specialist's Grid round trip, and its model/tool/self-check spans), counters, an event
  stream with the real SQL and tool I/O, and click-to-inspect spans. Nothing is invented.

## Commands

| Command | What it does |
|---|---|
| `python -m forge demo` | round 1 (grow), round 2 (re-test), final task |
| `python -m forge bench [--limit N]` | run the benchmark once |
| `python -m forge grow --category C` | force one Forge cycle |
| `python -m forge final` | run the collaborative finale (grows a writer if missing) |
| `python -m forge registry show\|reset` | inspect / reset (with backup) the team |
| `python -m forge nodes list\|stop` | SuperNodes started by the Forge |
| `python -m forge scan` | secret scan of the repo (run before any publish) |

Backends: `mock` (canned, offline), `supergrid` (real AgentApp runs on any SuperLink
connection), `nebius` (real model, runs roles locally without Flower; fallback only).

## Layout

```
bloom/          Flower AgentApp (shipped in the FAB): roles, orchestrator, specialist, tools, specialists/
forge/          local controller: pipeline, backends, review checks, approval, nodes, publish, CLI
evaluator/      scorer, gap detector, benchmark runner
tasks/          benchmark generator (answers computed from data), benchmark.jsonl, final task
dashboard/      stdlib server + one-file projector-friendly UI
templates/      specialist module template; a copy of the @flwrlabs/agent template (used by scripts/spawn_test.py)
scripts/        local_stack.sh, mock_model_server.py, spawn_test.py
registry.json   the team: specs, creators, approvals, nodes, scores
```

## Data owners, approval, discovery (two-laptop mode)

"Isn't this just subagents?" No: a subagent inherits its parent's access. A Bloom specialist
**gets new access**, because it's deployed as a SuperNode on a machine that holds data, a model
or credentials the coordinator lacks.

- **Data never ships in the FAB.** The dataset generator lives in `tasks/` (local only);
  `python -m tasks.export_sqlite` writes `coffee.sqlite` for the data owner, who attaches it with
  `--node-config 'bloom-db="/abs/path/coffee.sqlite"'`. `run_sql` exists only on such a node:
  read-only, one aggregating `SELECT` (GROUP BY or SUM/COUNT/…; no `SELECT *`), at most 200 rows.
  The coordinator can't answer SQL at all: the gap is about **access**, not prompting.
- **The data owner approves on their own machine.** For node-hosted specialists
  (`forge grow ... --join node`), the Forge stops after review and writes
  `runs/proposals/<slug>.json` = `{spec, module_source, spec_sha256, reviewer_results,
  dev_examples_used}`. The owner's launcher shows it, asks `y/N`, appends `spec_sha256` to
  `~/.bloom/approved.json` and starts the node with `bloom-approved=<that file>`. The node
  refuses (`spec not approved on this node`) to run any spec whose canonical hash
  (`bloom.specs.spec_hash`, sorted-key compact JSON) isn't on the list, so an edited instruction
  needs a new approval. `python -m forge activate <slug>` flips the registry entry to active
  (`approved_by: node-owner:<owner>`) once the node is online, then warms it with a describe run.
- **Discovery, not a local registry.** Each run starts with `describe` to every node (20 s budget);
  nodes reply with their specialist, tools usable there, model, `has_db`, approval status. The
  planner sees what's actually on the Grid; unapproved nodes are ignored; the registry is only a
  fallback when there are zero nodes. `python -m forge describe` is the smoke test. Node names
  follow `<slug>@<owner>` (Tier 1 matches the part before `@`).
- **A model per node.** A node's `FLWR_MODEL_API_ENDPOINT`/`KEY` pick its provider, and
  `bloom-model` overrides the spec's model to one that endpoint actually serves (e.g. Kimi on
  Nebius). The coordinator plans on `flwrlabs/endeavor-1.0`.
- **Budgets:** discovery 20 s, per step 90 s, hard stop 240 s, plans ≤ 4 steps.
- **Several nodes on one laptop** need distinct `--port`s and **their own `FLWR_HOME`** (shared
  homes collide on the per-run environment); after stopping a node, wait until SuperGrid shows it
  offline before restarting (`forge nodes start` waits for you).

Day-of order: Deployment Runtime for both accounts → invite `brianhuang08` to
`@vverm/bloom-team` → Brian registers `sql-analyst@brian`, `stats-analyst@brian` → `forge describe`
→ a SQL question through Brian's node → a Forge cycle (proposal → Brian's `y` → `forge activate`)
→ finale → optional 2-arm eval (`forge eval`, defaults: specialist vs AI + every tool,
6 questions per skill, 2 repeats).

## Benchmark

160 tasks across five skills (`sql`, `stats`, `dates`, `units`, `extraction`), all generated
from templates with answers **computed by code** from a seeded dataset, and each storing its
worked method:

| Difficulty | Per skill | Examples |
|---|---|---|
| standard | 8 dev + 12 test | "Total revenue in March", "median of these 31 numbers", "45 business days after…" |
| hard (multi-step) | 4 dev + 8 test | "largest % revenue growth Q1→Q2", "days above the store's own monthly average", coefficient of variation, "20 business days after the last Friday of March", net-45 due dates that roll off weekends, discounted $/oz, extraction with near-miss traps (6-digit IDs, Feb 30, `@@` emails) |

Dev tasks drive gap detection, the Forge's worked examples, and the Reviewer's tests.
**Test tasks are only ever used by `forge eval`.**

## Is a specialist actually better? (`python -m forge eval`)

`forge eval` compares three arms on the **held-out test tasks** (never seen by the Forge),
all using **the same model**:

| Arm | Instructions | Tools |
|---|---|---|
| `generalist` | generalist | none (the plain "AI wrapper") |
| `generalist_tools` | generalist | **every** Bloom tool (the fair baseline) |
| `specialist` | Forge-built module (+ worked examples + self-check) | the spec's curated tools |
| `generalist_tools_check` (`--ablation`) | generalist + a generic self-check | every tool |

The optional ablation arm separates "checking your work" from "specialization": if the
specialist beats `generalist_tools_check`, the gain isn't just the self-check.

It reports accuracy with Wilson 95% confidence intervals per skill, per difficulty and
overall; a paired comparison (same question, same repeat) of specialist vs each baseline
(wins/losses, exact sign-test p-value); a **paired bootstrap 95% CI on the accuracy gain**
that resamples *questions* (repeats averaged per question, so repeats don't inflate
confidence); and **cost per answer** (tokens, seconds, tool calls, self-check change rate).
Answers that never happened (a run killed at the 5-minute limit, a provider error) are
**excluded and counted separately**, never scored as wrong. Results go to `runs/eval/latest.json` and the dashboard.
With 12 test tasks per category, per-category intervals are wide, so use `--repeats 2`
or more on real models. The overall paired comparison is where significance shows up.
Mock-backend evals are **simulated** (hard-coded profiles) and labelled as such; they only
test the plumbing.

```bash
uv run python -m forge eval --backend supergrid --connection supergrid --repeats 2
uv run python -m forge demo --backend mock --fresh --auto-approve --eval   # simulated
```

On SuperGrid, eval jobs run 12 per AgentApp run (6 in parallel inside the run, 3 runs at
a time), so 60 tasks × 3 arms × 2 repeats = 360 model calls in about 30 runs.

## Final task

**A: Data detective (implemented).** "Did the loyalty program launched on 2026-04-01
increase average daily revenue at the Palo Alto store? …" date-wrangler → sql-analyst →
stats-analyst → report-writer. The dataset plants a +12.8% lift (p < 0.0001), so the
answer is checkable (`tasks/final_task.py`).
Alternatives: **B** incident post-mortem (extraction → dates → stats → writer),
**C** shipping quote (sql → units → dates → writer).

## Safety rules

See `CLAUDE.md`. In short: never publish without asking; never put keys in files
(`FLWR_MODEL_API_KEY` stays in env; SuperNode keys live in gitignored `keys/`); test apps
are `bloom-test-*` (`bloom` is reserved for the final app); generated specialist code is
AST-checked (import allowlist, no eval/exec/open/dunders), secret-scanned, built, and
tested before a human sees it.
