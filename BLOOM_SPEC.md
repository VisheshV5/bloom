# Bloom: Build Spec / PRD

> **Audience:** a fresh Claude Code session on a different laptop. It has none of the
> context from the session that wrote this, so this document is self-contained. Read all
> of it before writing code. Owner: **Vishesh** (Flower username `vverm`).
> Written 2026-09-28, the night before the hackathon.

---

## 0. Ground rules (put these in `CLAUDE.md`, verbatim, and obey them)

- NEVER run `flwr app publish` without asking Vishesh first. Published code is public and the upload is immediate.
- NEVER put API keys, tokens, private keys, or credentials in any project file. Scan generated agents for them before publishing. Keys live in env vars only (`FLWR_MODEL_API_KEY`, etc.).
- The name `bloom` is reserved for the final app. Name any test app published to Hub `bloom-test-*`.
- **No git commits, no GitHub pushes, no `gh` commands** unless Vishesh explicitly asks. (Do not run `git init` either unless he says so.)
- Ask before deleting files, making anything public, registering SuperNodes, or changing federation membership.
- Flower Agent is experimental. Read the actual template code, the installed `flwr` source (`.venv/lib/python3.*/site-packages/flwr/`), and https://flower.ai/docs/agent/ instead of guessing APIs. If something isn't documented, say so rather than inventing it. Check `--help` for exact CLI syntax before scripting any `flwr` command.
- Keep it simple and demo-ready. Working end to end beats clever.
- Check in with Vishesh after each milestone in §12.

---

## 1. Pitch

Multi-agent systems are hand-assembled: when a team hits a task outside its skills, a
developer writes a new agent. **Bloom's team grows itself.** It starts as one generalist
agent. When it keeps failing a category of tasks, Forge agents design, write, and test a
new specialist. After a human approves it, the specialist joins the federation as a new
node on Flower's SuperGrid and collaborates with the rest of the team through Grid
messages.

**Demo:** start with 1 agent, end with ~6 we didn't write, which then solve a multi-part
task together.

**Event:** Flower Collaborative Agent Hackathon, Stanford, Tue 2026-09-29. Hacking
10:30–16:30, demos from 17:15 (3–5 min per team plus questions).

**Judging:** use of Flower (Flower Agents + SuperGrid), impact & originality, demo &
delivery. The main theme is collaborative agents. Bonus for using the **Endeavor** model.

**Submission:** team details, short description, a **published Flower Hub app**
(`@vverm/bloom`), and a GitHub repo link.

---

## 2. How Flower Agent collaboration actually works (verified from source, flwr 1.39.0)

This is the most important section. The original idea ("publish each specialist as its
own Hub app, and the orchestrator calls it by name") **does not match how Flower works**.
The design below is built around the real mechanism.

### 2.1 Facts

- An **AgentApp** is a Python object registered with `@app.main()`:
  `def main(agent: AgentSession, context: Context) -> None`. It is packaged as a FAB
  (`flwr build`). One FAB contains exactly one `agentapp` component.
- `AgentSession` provides:
  - `agent.prompt`: the initial prompt (str)
  - `agent.connectors.tools(refs)` / `.call(tool_call)`: built-ins such as `web_search`, `web_fetch`, `filesystem`, and OAuth connectors
  - `agent.events.emit(event_dict)` / `.get_trace()`: frontend-visible events and run-series history
  - `agent.grid.tools()` / `.call(tool_call)`: **Grid tools**
- Model access happens inside the AgentApp only, via the OpenAI SDK against the runtime:
  `OpenAI(base_url=os.environ["FLWR_RUNTIME_BASE_URL"], api_key=os.environ["FLWR_RUNTIME_API_KEY"], max_retries=0)`.
  The runtime accepts: `model`, `input`, `stream`, `tools`, `tool_choice`, `instructions`,
  `previous_response_id` (unsupported by the default provider), `reasoning`,
  `max_output_tokens`, `metadata`, `text`. **This endpoint is not reachable from outside a run.**
- Model IDs use OpenRouter format: `openai/gpt-5.6-sol`, `openai/gpt-6-luna`,
  `openai/gpt-5.6-terra`. **Endeavor = `flwrlabs/endeavor-1.0`** (used by the
  `@flwrlabs/endeavor-agent` template). Nebius models (key shared in Slack on the day):
  `dedicated/flowerai/Kimi-K2.7-Code-1OUHWL`, `dedicated/flowerai/MiniMax-M3-OOLI9o`, via
  `FLWR_MODEL_API_ENDPOINT=https://api.tokenfactory.tf-ca1.nebius.com/v1/responses`.
- A **federation** = one SuperLink plus N **SuperNodes** (machines). A run belongs to one
  federation. Each user has `@<account>/personal`.
- **Grid tools = SuperLink ↔ SuperNode messaging.** Source:
  `flwr/supercore/task_process/agent/grid.py`.
  - An AgentApp running **on the SuperLink** (the orchestrator) gets:
    - `get_nodes(sample_size: int|null)` → `{"nodes":[{"id": "<uint64 str>", "name": str|null, "location": str|null}], "num_available": int}`
    - `push_messages(messages:[{"dst_node_id": str, "payload": str, "reply_to_message_id": str|null}])` → `{"results":[{"message_id": str|null, "error": str|null}]}`
    - `pull_messages(message_ids:[str], timeout: 0..300)` → `{"messages":[{"message_id","reply_to_message_id","src_node_id","payload": str|null,"error": str|null}], "pending_message_ids":[str]}`
  - An AgentApp running **on a SuperNode** (because a message arrived) gets only:
    - `push_reply_message(payload: str)` → `{"message_id": str|null, "error": str|null}` (one reply per instruction)
  - When a SuperNode receives a message, it starts **the same run's FAB**. Its
    `agent.prompt` is a compact JSON string `{"message_id": ..., "src_node_id": ..., "payload": ...}`.
  - **Every node runs the same app.** Nodes differ by identity (id/name/location), their
    node config, and their own model credentials. There is **no API to call a different
    Hub app** from an AgentApp. The `start_automation` connector also reuses the same FAB.
  - The topology is a **star**: nodes reply to the SuperLink. Node-to-node handoffs go
    through the orchestrator.
- `agent.grid.call(tool_call)` is a plain Python call. You do NOT need the model to invoke
  Grid tools. Build `{"type":"function_call","name":"get_nodes","call_id":"<uuid>","arguments":"<json str>"}`
  and call it directly from code. It returns `{"type":"function_call_output","call_id":...,"output":"<json str>"}`
  and emits the call and output as run events, which are visible in the SuperGrid UI. **Bloom uses deterministic
  code for Grid routing** (more reliable than a model-driven loop).
- **CLI (flwr 1.39.0):** `new, run, chat, build, install, log, list, stop, login, pull, supernode {register, unregister, list}, app {publish, review}, federation {list, archive, create, add-supernode, remove-supernode, remove-account, simulation-config, invite}, config`.
  - There is **no CLI to "add an app to a federation"**. That is UI-only (Hub page → "Add app to federation" → choose federation → Confirm) and only makes the app selectable in chat. **Bloom does not need it.**
  - `flwr run [APP] [SUPERLINK] --federation @acct/name --run-config ... --stream`. `--run-config` accepts `k=v` pairs or **a path to a TOML file** (prefer the file to avoid shell-quoting JSON). Keys must exist under `[tool.flwr.app.config]` in `pyproject.toml`.
  - `flwr log <run-id> supergrid --show`, `flwr list --run-id <id> supergrid`, `flwr stop <id> supergrid`.
  - `flwr app publish [APP]` uploads the project dir, filtered by `.gitignore` and allowed file extensions.
- **Running your own SuperNode** (from the hackathon guide, shown for Nebius, same binary locally):
  ```
  ssh-keygen -t ecdsa -b 384 -N "" -f keys/<node>
  flwr supernode register keys/<node>.pub supergrid
  flower-supernode --superlink=fleet-supergrid.flower.ai:443 \
      --auth-supernode-private-key=keys/<node> --allow-runtime-dependency-installation
  flwr supernode list supergrid --verbose
  ```
  A SuperNode needs `FLWR_MODEL_API_KEY` (and `FLWR_MODEL_API_ENDPOINT` for Nebius) **in its environment** to reach a model.
- **Limits:** each task has a **5-minute timeout** once Running. The hackathon gives credits.
- **Verified on Vishesh's laptop:** `flwr login supergrid` works. `flwr build` works.
  `flwr app publish .` works (`@vverm/bloom-test-hello` is live). Running agents fails with
  `Entitlement error ... Starting a run for Deployment Runtime is not allowed` until he is
  allow-listed on the morning of 09-29. **Nothing on SuperGrid can be tested tonight.**

### 2.2 Unverified (must be tested on the day, see §13)

> **Status update (2026-09-28, late):** built. Verified on a local SuperLink: U2, U3, U5 (see below), U6, U7 ✅.
> U5 answer: `flwr run` cannot start AgentApp runs in 1.39 (no user_prompt); Bloom starts runs like
> `flwr chat` does (`forge/flower_client.py`). Still open on SuperGrid: U1, U8, node `--name` in get_nodes.


| # | Question | Fallback if "no" |
|---|---|---|
| U1 | Can Vishesh run his own SuperNodes (on his laptop) against SuperGrid? | Tier 2/3 routing (§4.3) |
| U2 | Does a SuperNode's `--node-config` (or a name) reach `context.node_config` / `get_nodes().name`? | Put the spec in the payload (Tier 2) |
| U3 | Does `get_nodes` show a node that joined after the orchestrator started? | Each task is a new run anyway, so it's only a live-demo nicety |
| U4 | Does `flwr run ... --stream` show our `print()` lines, or do we need `flwr log --show`? | Parse `flwr log` output |
| U5 | With `flwr run` (not chat), is `agent.prompt` empty? Is `bloom.input` from run-config needed? | Always read both (§5.1) |
| U6 | Does `instructions=` reach the model through the runtime? | Prepend the instructions to `input` |
| U7 | Can several `flower-supernode` processes run on one laptop (port clashes)? | Check `flower-supernode --help` for address/port flags; or use fewer nodes |
| U8 | Exact syntax of `flwr federation add-supernode` and whether `register` already adds the node to the personal federation | Read `--help`; ask Vishesh |

Every code path that depends on these gets a `# UNVERIFIED(U#):` comment.

---

## 3. Architecture

```
                         ┌────────────────────── SuperGrid federation ──────────────────────┐
 Local laptop            │                                                                   │
 ┌───────────────┐  flwr run   ┌──────────────────────────┐   push/pull   ┌────────────────┐ │
 │ Forge / runner │───────────▶│ bloom AgentApp @SuperLink │◀────────────▶│ bloom @SuperNode│ │
 │ (local Python) │◀─ logs ────│ role: ORCHESTRATOR        │  Grid msgs    │ role: SPECIALIST│ │
 │  - evaluator   │            │ model: Endeavor           │               │ (sql-analyst)   │ │
 │  - forge       │            └──────────────────────────┘      ...       └────────────────┘ │
 │  - registry    │                                                        ┌────────────────┐ │
 │  - dashboard   │  starts local flower-supernode processes ─────────────▶│ (stats-analyst) │ │
 └───────────────┘                                                        └────────────────┘ │
                         └───────────────────────────────────────────────────────────────────┘
```

**One Flower app: `bloom`** (package `bloom/`). Its role is decided at runtime:

| Role | When | What it does |
|---|---|---|
| `orchestrate` | SuperLink-side run started by `flwr run`/chat, default mode | Plans with Endeavor, picks specialists from the registry, sends steps to nodes over the Grid, passes results forward, returns the final answer |
| `specialist` | Prompt is Grid-message JSON (`src_node_id` + `payload`) | Loads its spec (node config → payload → error), runs the LLM plus allowlisted local tools, replies via `push_reply_message` |
| `architect` / `builder` / `reviewer` / `solve` | `bloom.mode` run-config set by the local Forge | Single LLM "thinking" job for the Forge. Prints one `BLOOM_RESULT {json}` line |

**The local controller** (`forge/`, `evaluator/`, `dashboard/`; not in the FAB) runs every
side effect: writing files, building, registering and starting SuperNodes, and publishing.
It acts only after Vishesh approves at the terminal.

**How the team grows:** a new specialist = (a) a spec in `registry.json`, (b) a generated
module `bloom/specialists/<slug>.py`, and (c) in node mode, a new SuperNode started with
`--node-config 'bloom-specialty="<slug>"'` that joins the federation. The next `flwr run .`
packages the new module automatically; no Hub publish is needed per specialist.

---

## 4. Components

### 4.1 Package layout (build exactly this)

```
bloom/                          # repo root
├── CLAUDE.md                   # §0 rules + pointers to this spec
├── README.md                   # pitch, architecture diagram, how to run mock demo + real mode
├── BLOOM_SPEC.md               # this file
├── LICENSE                     # Apache-2.0 (copy from any flwr template)
├── .gitignore                  # .venv/ *.fab __pycache__/ runs/ keys/ .env* *.pem *.key
├── pyproject.toml              # the Flower app (name = "bloom")
├── registry.json               # source of truth for agents
├── bloom/                      # ── shipped in the FAB ──
│   ├── __init__.py
│   ├── agent_app.py            # app = AgentApp(); main() dispatches on role
│   ├── roles.py                # detect_role(agent, context) -> Role
│   ├── orchestrator.py         # plan → route → collect → answer
│   ├── specialist.py           # node-side worker
│   ├── forge_roles.py          # architect/builder/reviewer/solve prompts (real backend)
│   ├── protocol.py             # payload dataclasses + (de)serialisation, version=1
│   ├── grid_client.py          # ONLY file that touches agent.grid (UNVERIFIED markers here)
│   ├── llm.py                  # runtime OpenAI client + complete()/stream helpers
│   ├── registry_view.py        # parse the registry JSON passed in via run-config
│   ├── tools/                  # allowlisted local tools specialists may use
│   │   ├── __init__.py         # TOOL_REGISTRY: name -> (schema, fn)
│   │   ├── sql.py              # run_sql(query) on the embedded SQLite dataset (read-only)
│   │   ├── stats.py            # describe(), ttest_welch(), linregress(), correlation()
│   │   ├── dates.py            # add_business_days(), days_between(), weekday()
│   │   ├── units.py            # convert(value, from_unit, to_unit)
│   │   └── text.py             # regex_findall(pattern, text)
│   ├── data/
│   │   └── coffee.py           # dataset as Python literals (NOT .csv/.db, see §9)
│   └── specialists/
│       ├── __init__.py         # load_specialist(slug) -> module; list_specialists()
│       └── generalist.py       # the one hand-written agent
├── forge/                      # ── local only ──
│   ├── __main__.py             # `python -m forge ...` CLI
│   ├── pipeline.py             # gap → spec → build → review → approve → deploy → (publish)
│   ├── backends/
│   │   ├── base.py             # LLMBackend protocol
│   │   ├── mock.py             # canned, deterministic
│   │   ├── supergrid.py        # each call = `flwr run . supergrid` with bloom.mode=...
│   │   └── nebius.py           # optional direct Responses API using env key
│   ├── review_checks.py        # AST allowlist, contract check, secret scan, flwr build
│   ├── approval.py             # terminal y/N, prints spec + diff
│   ├── deploy.py               # write module, update registry
│   ├── nodes.py                # SuperNode lifecycle (keygen/register/add/start/stop)
│   ├── publish.py              # optional standalone publish (always asks)
│   ├── secret_scan.py
│   ├── events.py               # append-only JSONL event bus → runs/events.jsonl
│   └── demo.py                 # scripted end-to-end story
├── evaluator/
│   ├── scorer.py               # check(task, answer) -> bool
│   ├── gaps.py                 # rolling-window gap detection
│   └── runner.py               # run tasks through a backend, record scores
├── tasks/
│   ├── build_benchmark.py      # generates benchmark.jsonl with answers COMPUTED from data
│   ├── benchmark.jsonl
│   └── final_task.py           # the collaborative finale
├── templates/
│   ├── specialist_module.py.tmpl
│   └── flower/                 # reference copies: collaborative-agent, endeavor-agent (via `flwr new`)
├── dashboard/
│   ├── server.py               # stdlib http.server; /api/state, /api/events?since=
│   └── index.html              # single file, vanilla JS + SVG, no CDN
├── scripts/
│   └── spawn_test.py           # standalone "copy template → specialist app → build → ask → publish"
├── runs/                       # gitignored: events.jsonl, run logs, overrides TOMLs
├── keys/                       # gitignored: SuperNode keypairs
└── tests/                      # pytest
```

### 4.2 `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bloom"
version = "0.1.0"
description = "Bloom: a self-growing team of Flower Agents"
license = { file = "LICENSE" }
requires-python = ">=3.11,<4.0"
dependencies = ["flwr>=1.39.0,<2.0", "openai>=2.16.0,<3.0.0"]

[project.optional-dependencies]
dev = ["pytest"]

[tool.hatch.build.targets.wheel]
packages = ["bloom"]

[tool.flwr.app]
publisher = "vverm"
display-name = "Bloom"
fab-format-version = 1
flwr-version-target = "1.39.0"
fab-include = ["bloom/**/*.py", "LICENSE"]

[tool.flwr.app.components]
agentapp = "bloom.agent_app:app"

[tool.flwr.app.config]
bloom.mode = "orchestrate"         # orchestrate | architect | builder | reviewer | solve
bloom.input = ""                   # task text or JSON job, used if agent.prompt is empty
bloom.registry = ""                # JSON string of the registry snapshot (see §6)
bloom.routing = "auto"             # auto | nodes | payload | inprocess (see §4.3)
bloom.orchestrator-model = "flwrlabs/endeavor-1.0"
bloom.specialist-model = "openai/gpt-5.6-sol"
bloom.step-timeout = 90            # seconds per Grid step
```

Only the standard library plus `openai` may be imported in `bloom/` (numpy is not
guaranteed on nodes). `flwr build` must succeed.

### 4.3 Routing tiers (orchestrator, `grid_client.py`)

Always try in order and record which tier was used (shown on the dashboard):

1. **Tier 1: nodes by specialty.** `get_nodes(null)`, then match `node.name == slug`, or the
   `node_id` recorded in `registry.json` (`agents[].node_id`) → push a payload without the
   spec (the node knows its role from node config).
2. **Tier 2: any node, spec in payload.** If there's no dedicated node but ≥1 node exists,
   send `{"spec": {...}}` inside the payload. Pick nodes round-robin.
3. **Tier 3: in-process.** No nodes (for example the personal federation has no SuperNodes):
   the orchestrator runs the specialist logic itself by calling `specialist.run_spec(spec, step)`.
   The demo still works, just without Grid traffic.

`bloom.routing` can force a tier. `auto` = 1 → 2 → 3.

### 4.4 Wire protocol (`protocol.py`), payload is a JSON string

Orchestrator → node:
```json
{"bloom": 1, "kind": "step", "job_id": "j-...", "step_id": "s1",
 "specialist": "sql-analyst", "spec": {...optional...},
 "instruction": "Compute daily revenue for store 3 between 2026-03-02 and 2026-03-31",
 "context": [{"from": "date-wrangler", "output": "..."}]}
```
Node → orchestrator (via `push_reply_message`):
```json
{"bloom": 1, "kind": "result", "job_id": "j-...", "step_id": "s1",
 "specialist": "sql-analyst", "ok": true, "output": "...full text...",
 "answer": "...short machine-checkable answer or null...", "error": null}
```
Keep payloads < 32 KB. Truncate `context` outputs to 4 KB each.

### 4.5 Role detection (`roles.py`)

```
mode = context.run_config.get("bloom.mode", "orchestrate")
try: p = json.loads(agent.prompt); if isinstance(p, dict) and "src_node_id" in p and "payload" in p: return SPECIALIST(p)
except ValueError: pass
return mode
```
Input text for orchestrator/forge roles = `agent.prompt.strip() or context.run_config["bloom.input"]` (UNVERIFIED U5).

### 4.6 Orchestrator (`orchestrator.py`)

1. Load the registry snapshot from `bloom.registry`.
2. **Plan** with Endeavor (`bloom.orchestrator-model`): the model receives the task plus
   the available specialists' `{slug, purpose, category}` and returns JSON
   `{"steps":[{"step_id","specialist","instruction","depends_on":[...]}], "missing_capabilities":[{"capability","why"}]}`.
   Use `text={"format": {"type": "json_schema", ...}}` if supported; otherwise parse
   leniently and fall back to a **keyword classifier** (category keywords → specialist,
   default generalist). Single-category benchmark tasks can skip the LLM planner
   (`plan = [one step]`) to save time and credits.
3. **Execute** steps in dependency order. Independent steps go into one `push_messages`
   batch. `pull_messages(ids, timeout=bloom.step-timeout)`. Retry a failed or timed-out
   step once via the next tier.
4. **Answer:** for a single step, the answer is the specialist's output. For multi-step
   plans, the final step's output (usually the writer). Stream the final text with
   `agent.events.emit(...)` (see the template pattern in Appendix A), then
   `print("BLOOM_RESULT " + json.dumps({...}))` with
   `{job_id, answer, steps:[{step_id, specialist, tier, node_id, ok, ms}], missing_capabilities}`.
5. Also `agent.events.emit` a custom event per step: `{"type":"bloom.step", ...}` (custom
   event types are allowed: `type` just has to be a non-empty string).
6. Must finish within **4 minutes** (hard stop before the 5-minute task limit): budget-check before each step.

### 4.7 Specialist (`specialist.py`)

1. Parse the Grid prompt → payload → `Step`.
2. Resolve the spec: `context.node_config.get("bloom-specialty")` → `registry`/module
   `bloom.specialists.<slug>` (UNVERIFIED U2) → else `payload.spec` → else reply `ok:false`.
3. `run_spec(spec, step)`: bounded tool loop (≤ 4 rounds) with the Responses API. The tools
   are the spec's allowlisted tools from `bloom/tools` (function schemas you write; the
   functions execute locally in-process). Then `module.postprocess(text) -> answer`.
4. Reply exactly once with `grid.call(push_reply_message)`. Never raise before replying:
   catch everything → `ok:false, error:str(e)`. (The runtime turns an exception before a
   reply into a generic "AgentApp failed before replying" error.)

### 4.8 Specialist module contract (what the Builder generates)

`templates/specialist_module.py.tmpl` → `bloom/specialists/<slug>.py`:
```python
"""Bloom specialist: {purpose}. Generated by Forge on {date} from spec v{version}."""
SLUG = "{slug}"
CATEGORY = "{category}"
MODEL = "{model}"
TOOLS = [{tools}]                 # subset of bloom.tools.TOOL_REGISTRY names
INSTRUCTIONS = """{instructions}"""
EXAMPLES = [...]                  # optional few-shot (input, output) pairs

def postprocess(text: str) -> str | None:
    """Extract the short final answer (e.g. the line after 'FINAL:')."""
    ...                           # Builder writes this body
```
Every specialist must end its output with `FINAL: <answer>`. The default `postprocess`
extracts that. Imports allowed in generated modules: `re, json, math, statistics,
datetime, decimal, fractions, itertools, collections`. Nothing else.

### 4.9 Forge pipeline (`forge/pipeline.py`)

```
GapReport ─▶ Architect(spec) ─▶ Builder(module) ─▶ Reviewer(checks+tests) ─┬─ fail ─▶ Builder w/ notes (≤2 retries) ─▶ abandon + log
                                                                            └─ pass ─▶ Approval (y/N) ─▶ Deploy ─▶ Join (node) ─▶ [optional Publish (y/N)]
```

- **Reuse first:** before the Architect runs, check `registry.json` for an active agent
  whose `category` matches or whose `capabilities` overlap. If one exists, route to it and
  log `reused` instead of creating a duplicate.
- **Architect** input: gap report (category, failing task prompts plus wrong answers,
  current registry). Output: a spec (§6 schema). Validate with a hand-written validator
  (no pydantic needed): the slug is kebab-case, the tools are all allowlisted, the model is
  in the allowed list, and the instructions are ≤ 2,000 characters.
- **Builder** input: spec (+ reviewer notes). Output: the module file text (template-filled; the model writes `INSTRUCTIONS`, `EXAMPLES`, and the `postprocess` body).
- **Reviewer** (local checks, then optional LLM notes):
  1. `ast.parse`; the import allowlist; forbid `eval, exec, compile, open, __import__, globals, getattr(…, "__…")`, and any attribute starting with `__`.
  2. Contract: the required names exist with the right types; `TOOLS ⊆ TOOL_REGISTRY`.
  3. `secret_scan` (patterns: `sk-[A-Za-z0-9_-]{16,}`, `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{20,}`, `-----BEGIN .*PRIVATE KEY-----`, `(api[_-]?key|secret|token|password)\s*=\s*['"][^'"]{8,}`).
  4. `uv run flwr build` in a temp copy of the project with the module added.
  5. **Test tasks:** 3 held-out tasks from the gap's category (not the ones that triggered the gap), run through the backend with this spec. Pass = ≥ 2/3 correct.
  6. On failure: produce concrete notes (which check failed, the wrong answers) → Builder. Max 2 retries.
- **Approval** (`approval.py`): print the spec (pretty JSON), a unified diff of every file
  change (new module + `registry.json`), the review results, and the exact side-effect
  commands that will run next. Prompt `Approve <slug>? [y/N]`. Only a literal `y`/`Y`
  approves. Emit `approval_pending` / `approval_resolved` events.
  - `--auto-approve` exists **only when backend == mock** (hard error otherwise), so the
    mock demo can run unattended.
- **Deploy:** write the module, add it to the registry (`status: "active"`, `created_by: ["architect","builder","reviewer"]`, `approved_by: "vverm"`, timestamps).
- **Join** (`nodes.py`, only in `--join node` mode; default in mock is simulated):
  every command is printed, and Vishesh confirms each one with y/N:
  1. `ssh-keygen -t ecdsa -b 384 -N "" -f keys/<slug>` (keys/ is gitignored; never print key contents)
  2. `uvx --from flwr==1.39.0 flwr supernode register keys/<slug>.pub supergrid`. Capture the node id if printed, and store it in the registry.
  3. If needed: `flwr federation add-supernode ...` (read `--help` first; UNVERIFIED U8).
  4. Start `flower-supernode --superlink=fleet-supergrid.flower.ai:443 --auth-supernode-private-key=keys/<slug> --allow-runtime-dependency-installation --node-config 'bloom-specialty="<slug>"'` as a background subprocess. Inherit env (`FLWR_MODEL_API_KEY`) and never write it anywhere. Log to `runs/nodes/<slug>.log`. Give each process unique local ports (UNVERIFIED U7).
  5. Poll `flwr supernode list supergrid --verbose` until the node is online (60 s timeout) → emit `node_joined`.
  - `python -m forge nodes stop` terminates all started SuperNode processes.
- **Publish** (optional, `--publish-standalone`, default OFF): generates a standalone app
  `bloom-test-<slug>` (like `scripts/spawn_test.py`) and asks `Publish @vverm/bloom-test-<slug> to Flower Hub (PUBLIC, immediate)? [y/N]`. In mock mode, publishing is **always simulated**, and `flwr app publish` is never invoked.

### 4.10 LLM backends (`forge/backends/`)

```python
class LLMBackend(Protocol):
    name: str
    def architect(self, gap: GapReport, registry: Registry) -> dict: ...            # spec
    def builder(self, spec: dict, notes: list[str] | None) -> str: ...              # module source
    def reviewer_notes(self, spec: dict, source: str, results: dict) -> list[str]: ...
    def run_task(self, task: Task, registry: Registry, routing: str) -> TaskResult: ...  # through the orchestrator
    def run_with_spec(self, spec: dict, task: Task) -> TaskResult: ...              # reviewer tests
```
- **mock:** deterministic canned specs and modules per category. `run_task` simulates the
  orchestrator: the generalist answers with a per-category accuracy profile (seeded RNG;
  wrong on sql 90%, stats 70%, dates 70%, units 60%, extraction 10%), while specialists use
  the reference solvers from `tasks/build_benchmark.py` (so they are correct about 95% of
  the time). It also emits realistic `message` events (orchestrator ↔ node) with small
  sleeps (`--speed` flag) so the dashboard animates.
- **supergrid:** each call writes `runs/overrides/<id>.toml` (`bloom.mode`, `bloom.input`
  as a JSON job, `bloom.registry`), runs `uv run flwr run . supergrid --run-config runs/overrides/<id>.toml --stream`
  (add `--federation` if configured), captures stdout, and extracts the last
  `BLOOM_RESULT {json}` line. If absent, find the run id and use `flwr log <id> supergrid --show` (UNVERIFIED U4). Timeout: 280 s.
- **nebius (optional fallback for Forge thinking only):** OpenAI SDK against
  `FLWR_MODEL_API_ENDPOINT` with `FLWR_MODEL_API_KEY` from the env. Refuse to start if the
  env vars are missing. Never log them.

### 4.11 Evaluator (`evaluator/`)

- `scorer.check(task, answer) -> bool` by `task.check`:
  - `exact` (normalized: strip, casefold, collapse whitespace)
  - `number` (abs/rel tolerance per task, default rel 1e-2)
  - `set` (comma- or newline-separated, order-insensitive)
  - `date` (ISO `YYYY-MM-DD`)
- `gaps.GapDetector(threshold=0.6, window=5, min_attempts=5)`: per `(agent_slug, category)`
  rolling window. A gap is flagged when the generalist's (or the current specialist's)
  accuracy in that category is < threshold over the last `window` attempts. Suppress it if
  a specialist for that category is active or pending. If an active specialist itself
  drops below the threshold → flag `kind: "improve"` (stretch: the Forge produces v2).
- `runner`: iterate tasks (interleaved categories, seeded shuffle), call
  `backend.run_task`, score, update `registry.json` scores and emit `task_result`. When a
  gap fires, **pause the benchmark → run the Forge pipeline → resume**. Tasks after the new
  specialist joins get routed to it.

### 4.12 Dashboard (`dashboard/`)

- `server.py`: stdlib `http.server` on `localhost:8765`. `GET /` → `index.html`.
  `GET /api/state` → `{registry, scores, pending_approvals, nodes, last_event_id}` built
  by folding `runs/events.jsonl`. `GET /api/events?since=<id>` → new events. No external
  dependencies.
- `index.html`: one file, vanilla JS, no CDN (venue wifi risk). Polls every 1 s. Dark
  background, **large type (≥ 20 px body, 32 px headings)**, readable from the back of a
  room. Four panels:
  1. **Agent graph** (SVG): `bloom` orchestrator in the centre; specialists on a circle
     around it (new ones animate in with a "bloom" scale/fade); Forge agents
     (Architect/Builder/Reviewer) as a small cluster at the bottom that lights up while
     working. Edges pulse when a message crosses them. Each node shows its slug, tier
     (node/payload/in-process) and accuracy.
  2. **Live message log**: last ~15 events, e.g. `bloom → sql-analyst: "Compute daily revenue…"`, colour-coded by kind.
  3. **Approval queue**: pending specs with purpose, tools, and review status. Approval
     itself happens in the terminal; the panel says "waiting for human approval in terminal".
  4. **Scores**: per category, generalist accuracy vs specialist accuracy (horizontal bars), plus a headline counter "Agents: 1 → 6".
- Event schema (`forge/events.py`, one JSON per line, monotonically increasing `id`):
  `{"id", "ts", "type", ...}` where `type` ∈ `agent_added, agent_status, message, task_result, gap_flagged, forge_stage, approval_pending, approval_resolved, node_joined, published, final_task, error`.

---

## 5. Benchmark (`tasks/`)

- ~38 tasks in 5 categories, each ~7–8 tasks. **All answers are computed by code** in
  `build_benchmark.py` from the seeded dataset or task inputs (no hand-typed answer keys).
  Each line: `{"id","category","prompt","answer","check","tolerance"?}`. Prompts end
  with: "End your reply with `FINAL: <answer>`."

| Category | Needs | Example |
|---|---|---|
| `sql` | `run_sql` on the coffee dataset (the generalist has no data access, so it must fail) | "Which city had the highest total revenue in Q2 2026?" → `Palo Alto` |
| `stats` | precise computation on numbers given in the prompt | "Welch t-test p-value for A=[…20 numbers…] vs B=[…], 3 decimals" → `0.013` (number, abs 0.002) |
| `dates` | business-day and calendar arithmetic | "What date is 45 business days after 2026-03-02 (Mon–Fri, no holidays)?" → `2026-05-04` |
| `units` | unit conversions and chained arithmetic | "A 2.5 lb bag of beans costs $18. Price per kg in USD, 2 decimals?" → `15.87` |
| `extraction` | regex/text extraction (LLMs are usually fine, **expected: no gap**) | "List every order ID (format ORD-#####) in this text…" → set |

- **Dataset** (`bloom/data/coffee.py`, seed 42, stdlib only): `stores(id, name, city, opened)` with 4 stores; `products(id, name, category, price)` with ~10 products; `sales(id, store_id, product_id, date, qty)` for ~1,500 rows over 2026-01-01..2026-06-30. **Plant an effect** for the finale: the Palo Alto store's daily revenue rises ~12% from 2026-04-01 (the "loyalty program launch"). Load into in-memory SQLite in `tools/sql.py`; only `SELECT` is allowed (reject anything else, read-only connection).
- **Mock accuracy profile** (§4.10) is tuned so that in mock mode gaps fire for `sql`,
  `stats`, `dates`, `units` and not for `extraction`. That honest "not everything spawns"
  beat is a demo line.

## 6. Registry (`registry.json`)

```json
{
  "version": 1,
  "agents": [
    {
      "slug": "generalist",
      "kind": "generalist",
      "category": null,
      "purpose": "Answers anything; no tools.",
      "spec": {"model": "openai/gpt-5.6-sol", "tools": [], "instructions": "..."},
      "module": "bloom/specialists/generalist.py",
      "status": "active",
      "created_at": "2026-09-29T10:30:00Z",
      "created_by": ["human:vverm"],
      "approved_by": "vverm",
      "node": {"mode": "inprocess", "node_id": null, "name": null},
      "hub": null,
      "scores": {"sql": {"attempts": 0, "correct": 0, "recent": []}}
    }
  ],
  "forge_log": [
    {"ts": "...", "gap": {"category": "sql", "accuracy": 0.2}, "outcome": "approved|rejected|failed_review|reused", "slug": "sql-analyst", "attempts": 1}
  ]
}
```
- Spec fields (Architect output): `slug, category, purpose, instructions, model, tools[], capabilities[], output_format, version`.
- Allowed models: `openai/gpt-5.6-sol`, `openai/gpt-6-luna`, `openai/gpt-5.6-terra`, `flwrlabs/endeavor-1.0` (+ the Nebius IDs when configured).
- Writes are atomic (write a temp file, then `os.replace`). `forge reset` restores the
  registry to generalist-only (asks for confirmation; keeps a timestamped backup in `runs/`).

## 7. Final collaborative task (`tasks/final_task.py`)

Implement **A** as the default. Keep the structure pluggable so B or C can be swapped in
if Vishesh picks them.

- **A: "Data detective" (recommended).** *"Did the loyalty program launched on 2026-04-01
  increase average daily revenue at the Palo Alto store? Compare the 30 business days
  before and after, test significance, and write a 3-sentence note for the CEO."*
  Plan: `date-wrangler` (compute both windows) → `sql-analyst` (daily revenue series for
  each window) → `stats-analyst` (means, % change, Welch t-test p) → `report-writer`
  (3-sentence summary). The planner emits `missing_capabilities: [report-writer]` because
  no writer exists yet → **the Forge creates `report-writer` on demand** (the second growth
  trigger, a capability request rather than a score gap) → the task runs. Checkable parts:
  the window dates, both means (tolerance 1%), and p < 0.05 true/false, all from the reference solver.
- **B: Incident post-mortem.** Log text → `extraction` (error lines + timestamps) → `date-wrangler` (durations, MTTR) → `stats-analyst` (p95 latency) → `report-writer`.
- **C: Shipping quote.** `sql-analyst` (rates table) → `unit-converter` (lb/kg, in/cm) → `date-wrangler` (delivery date in business days) → `report-writer`.

The end state for the demo: generalist + sql-analyst + stats-analyst + date-wrangler +
unit-converter + report-writer = **6 agents, 5 of them written by Bloom**.

## 8. CLI surface (`python -m forge …`)

```
python -m forge demo --backend mock [--auto-approve] [--speed 1.0]     # the full story, dashboard-driven
python -m forge bench --backend {mock|supergrid} [--limit N] [--join {sim|node}]
python -m forge forge --category sql --backend ...                     # force one Forge cycle
python -m forge final --backend ...                                     # run the finale
python -m forge registry show | reset
python -m forge nodes list | stop
python -m dashboard.server                                              # http://localhost:8765
```
Also `scripts/spawn_test.py` (standalone): copy the `@flwrlabs/agent` template project →
rename to `bloom-test-<slug>` (pyproject `name`, `version = "0.1.0"`, description) →
insert an `INSTRUCTIONS` constant + `instructions=INSTRUCTIONS` into
`responses.create(...)` → write a README → `flwr build` → show a diff → secret scan →
**ask y/N** → `flwr app publish`. Each regex substitution must match exactly once or the
script aborts. Output goes **outside** the repo (for example `../bloom-agents/<name>`),
because `flwr app publish` uploads everything not in `.gitignore`.

## 9. Gotchas

- `flwr app publish` uploads the whole project dir minus `.gitignore`. Keep `keys/`,
  `runs/`, and `.env*` gitignored **before** any publish. Run `secret_scan` over the whole
  repo as a pre-publish gate.
- Keep `bloom/` stdlib + `openai` only. Embed data as Python literals: non-`.py` files
  aren't in `fab-include`, and Hub may reject unknown extensions.
- The 5-minute task limit: every benchmark task and every Forge LLM job is its own short
  run. Never loop the whole benchmark inside one run.
- The Collaborative template (written for 1.38) tells nodes to reply with
  `push_messages`. In 1.39, node-side tasks only have `push_reply_message`. Use the latter.
- The default model provider doesn't support `previous_response_id`. Always send full `input`.
- Calling `agent.events.emit` after the stream closes raises. Emit everything before `main` returns.
- The runtime base URL and key exist only inside a run. Nothing local can call models
  except the optional Nebius backend.

## 10. Tests (`tests/`, run with `uv run pytest`)

- The scorer's check types; gap detection (window, threshold, suppression); the registry's
  atomic write and reuse lookup.
- The protocol round-trips; role detection (Grid prompt vs plain prompt vs forge modes).
- Orchestrator routing with a **FakeAgentSession / FakeGrid** implementing the `AgentGrid`
  ABC (`tools()`, `call()`) with 0, 1, and N nodes → tiers 3, 2, and 1. The fake must
  return exactly the output JSON shapes in §2.1.
- Specialist: always replies exactly once, even when the LLM or a tool raises.
- Review checks reject: a forbidden import, `eval`, a dunder access, a planted fake OpenAI-style key, and unknown tools.
- The benchmark builder is deterministic (same seed → same file); every answer re-verifies via the reference solver.
- `uv run flwr build` succeeds for the repo (mark the test `slow`).
- The mock demo runs end to end headless (`--auto-approve --speed 0`) and ends with 6 active agents.

## 11. Definition of done (tonight, no SuperGrid)

1. `uv sync && uv run pytest` passes; `uv run flwr build` produces `vverm.bloom.0-1-0.*.fab`.
2. `python -m dashboard.server` plus `python -m forge demo --backend mock` shows, in the
   browser, 1 → 6 agents growing: gaps flagged, Forge stages, approval prompts in the
   terminal (unless `--auto-approve`), nodes joining (simulated), scores improving, then
   the finale with visible handoffs and a final answer. Total run time ≈ 2–3 min at `--speed 1`.
3. The `supergrid` backend and node lifecycle code are written, unit-tested with fakes,
   and every unverified assumption is marked `# UNVERIFIED(U#)`.
4. README explains the architecture, mock demo, real mode, and day-of runbook.
5. No commits, no publishes, no key material anywhere in the tree.

## 12. Build milestones (check in with Vishesh after each)

| M | Deliverable | Acceptance |
|---|---|---|
| M0 | Scaffold: layout, pyproject, CLAUDE.md, README stub, `.gitignore`, templates fetched with `uvx --from flwr==1.39.0 flwr new @flwrlabs/collaborative-agent` and `@flwrlabs/endeavor-agent` into `templates/flower/` | `flwr build` OK |
| M1 | Dataset, tools, benchmark builder, scorer, gap detector + tests | pytest green, `tasks/benchmark.jsonl` generated |
| M2 | Registry, event bus, mock backend, runner | `forge bench --backend mock` flags sql/stats/dates/units gaps |
| M3 | Forge pipeline (spec → build → review → approval → deploy → simulated join) + review checks | a forced cycle creates `bloom/specialists/sql_analyst.py`, registry updated |
| M4 | Dashboard | the demo animates in the browser; readable at 1080p from far away |
| M5 | Flower app: roles, orchestrator, specialist, grid_client, forge roles + FakeGrid tests | pytest green, `flwr build` OK |
| M6 | supergrid + nebius backends, node lifecycle, spawn_test script | code complete, dry-run mode prints the commands it would run |
| M7 | Finale + full mock demo + README runbook | §11 all green |

## 13. Day-of runbook (09-29, after allow-listing, ~10:30)

Test in this order and stop to fix at each failure:

1. `uvx --from flwr==1.39.0 flwr run @vverm/bloom-test-hello supergrid --stream` (plain run works?) → answers U5 and U4.
2. `uv run flwr run . supergrid --run-config runs/overrides/smoke.toml --stream` with `bloom.mode="solve"` → a BLOOM_RESULT line comes back? `instructions=` honoured? (U6)
3. `uvx --from flwr==1.39.0 flwr federation list supergrid` and `flwr supernode list supergrid --verbose` → what federations and nodes exist.
4. Start one local SuperNode per §4.9 Join (with Vishesh approving each command) → online? (U1, U7, U8)
5. Orchestrator → that node, Tier 2 (spec in payload) → reply received?
6. Restart the node with `--node-config 'bloom-specialty="sql-analyst"'` → Tier 1 works? (U2)
7. **Critical:** with an orchestrator run in flight, start a second node → does `get_nodes` see it? (U3)
8. Switch `forge` to `--backend supergrid` (Endeavor as orchestrator model) and run `bench --limit 10`.
9. Run the finale. Then Vishesh decides which 2–3 specialists to pre-publish as backups (`--publish-standalone`, each needs his y).
10. By ~15:30: Vishesh approves publishing `@vverm/bloom` (`uv run flwr app publish .` from the repo root after a whole-repo secret scan), then pushing to GitHub (his call), then the submission text.

**Fallback ladder if the Grid misbehaves:** Tier 1 → Tier 2 → Tier 3 (in-process on
SuperGrid, still real Flower runs with Endeavor) → mock backend with the dashboard (last
resort; say so honestly on stage).

## 14. Demo script (3–5 min)

1. (20 s) The problem: agent teams are hand-assembled.
2. (30 s) The dashboard shows one agent. Start the benchmark; the generalist fails SQL questions; the red bar drops.
3. (60 s) Gap flagged → Architect/Builder/Reviewer light up → the terminal shows the spec and diff → Vishesh types `y` → a new SuperNode joins the federation → the graph blooms → SQL accuracy jumps.
4. (30 s) Fast-forward: stats, dates, units specialists appear; extraction doesn't need one ("it only grows where it's weak").
5. (60 s) The finale: the planner asks for a missing writer → Forge builds it → sql → stats → writer handoffs over the Grid → CEO note on screen.
6. (20 s) Flower usage recap: every agent is a Flower AgentApp on SuperGrid, Grid messaging, SuperNodes joining live, Endeavor orchestrating, published on Flower Hub.

---

## Appendix A: Reference code from `@flwrlabs/collaborative-agent` (flwr 1.38 template)

Main loop (model-driven Grid tools; Bloom does routing in code instead, but reuse the streaming pattern):
```python
tools = [*agent.grid.tools(), *connector_tools]
for _ in range(MAX_TOOL_ROUNDS):
    response, completed_event = _stream_response(client, agent, input_items, tools)
    response_output = [item.to_dict() for item in response.output]
    tool_calls = [i for i in response_output if i.get("type") == "function_call"]
    input_items.extend(response_output)
    if not tool_calls:
        agent.events.emit(completed_event); print(response.output_text); return
    input_items.extend(agent.grid.call(i) for i in tool_calls)
```
Streaming helper: `client.responses.create(model=..., reasoning={"effort": "medium"}, input=..., instructions=..., tools=..., stream=True)`;
emit only `response.output_text.delta` and `response.reasoning_summary_text.delta`
events, keep `response.completed` as the final event and emit it at the end.

The template's collaboration instruction (adapt for node-side replies): *"The presence of
`src_node_id` in the prompt means the request came from another agent; `payload` is its
request. Reply with `dst_node_id` = `src_node_id` and `reply_to_message_id` = `message_id`.
Send only one reply."*

History rebuild from `agent.events.get_trace()`: collect `data.type == "message"` with
role user/assistant, and assistant messages inside `response.completed` events; append the
current prompt if it isn't already present.

## Appendix B: Endeavor usage (from `@flwrlabs/endeavor-agent`)

`_MODEL = "flwrlabs/endeavor-1.0"`. Non-streaming tool-selection calls
(`client.responses.create(model=_MODEL, input=[...], stream=False, instructions=..., tools=..., tool_choice="auto")`),
then a streamed final answer. Connector rounds are capped (4). Use the same shape for the
orchestrator's planner.
