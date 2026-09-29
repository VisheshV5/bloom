# Bloom: rules for Claude Code

Bloom is a self-growing team of Flower Agents, built for the Flower Collaborative Agent
Hackathon (Stanford, 2026-09-29). Owner: Vishesh (Flower username `vverm`).
The full design lives in `BLOOM_SPEC.md`; read it before changing architecture.

## Rules
- NEVER run `flwr app publish` without asking Vishesh first. Published code is public and the upload is immediate.
- NEVER put API keys, tokens, private keys, or credentials in any project file, and check generated agents for them before publishing (`python -m forge scan`). Keys live in env vars only (`FLWR_MODEL_API_KEY`, `FLWR_MODEL_API_ENDPOINT`).
- The name `bloom` is reserved for the final app. Name test apps published to Hub `bloom-test-*`.
- No git commits, no GitHub pushes, no `gh` commands unless Vishesh explicitly asks.
- Ask before deleting files, making anything public, registering SuperNodes, or changing federation membership.
- Flower Agent is experimental. Read the actual template code (`runs/reference/`, or re-download with `uvx --from flwr==1.39.0 flwr new @flwrlabs/collaborative-agent`), the installed `flwr` source (`.venv/lib/python3.*/site-packages/flwr/`), and https://flower.ai/docs/agent/ instead of guessing APIs. If something isn't documented, say so rather than inventing it. Check `--help` before scripting any `flwr` command.
- Keep things simple and demo-ready. Working end to end beats clever.
- Anything that depends on unverified SuperGrid behaviour is marked `# UNVERIFIED(U#)`; see BLOOM_SPEC.md §2.2.
- The dataset must never enter the FAB (`bloom/`). It lives in `tasks/coffee_data.py`; nodes get it as a SQLite file via `bloom-db`.
- Node-hosted specialists are approved by the node owner on their machine (proposal JSON + spec_sha256), never by a local `y`.

## Layout
- `bloom/`: the Flower AgentApp shipped in the FAB (stdlib + openai only).
- `forge/`, `evaluator/`, `tasks/`, `dashboard/`: local controller (never in the FAB).
- `registry.json`: source of truth for agents. `runs/` and `keys/` are gitignored.

## Commands
- `uv run pytest`: tests. `uv run flwr build`: build the FAB.
- `uv run python -m dashboard.server` then `uv run python -m forge demo --backend mock --auto-approve`.
