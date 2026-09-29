#!/usr/bin/env bash
# Run Bloom on a LOCAL Flower SuperLink (no SuperGrid account needed).
#
#   scripts/local_stack.sh start        # fake model server + SuperLink (no API key needed)
#   scripts/local_stack.sh start-real   # SuperLink using YOUR model key from the environment:
#                                       #   export FLWR_MODEL_API_KEY=...   (never put it in a file)
#                                       #   optional: export FLWR_MODEL_API_ENDPOINT=.../v1/responses
#   scripts/local_stack.sh stop
#
# Then, in the same shell (so FLWR_HOME points at runs/flwr-home):
#   export FLWR_HOME=$PWD/runs/flwr-home
#   uv run python -m forge demo --backend supergrid --connection local-agent --join local
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
export FLWR_HOME="$ROOT/runs/flwr-home"
PIDS="$ROOT/runs/local_stack.pids"
mkdir -p "$FLWR_HOME" runs

write_config() {
  cat > "$FLWR_HOME/config.toml" <<TOML
[superlink]
default = "local-agent"

[superlink.local-agent]
address = "127.0.0.1:8000"
insecure = true
TOML
}

case "${1:-}" in
  start)
    write_config
    uv run python scripts/mock_model_server.py --port 8080 > runs/mock_model.log 2>&1 &
    echo $! >> "$PIDS"
    FLWR_MODEL_API_ENDPOINT=http://127.0.0.1:8080/v1/responses FLWR_MODEL_API_KEY=local-mock \
      uv run flower-superlink --insecure > runs/superlink.log 2>&1 &
    echo $! >> "$PIDS"
    echo "Started fake model server (:8080) and SuperLink (:8000 control, :9092 fleet)."
    echo "For local SuperNodes started by the Forge, also export:"
    echo "  export FLWR_MODEL_API_ENDPOINT=http://127.0.0.1:8080/v1/responses FLWR_MODEL_API_KEY=local-mock"
    ;;
  start-real)
    : "${FLWR_MODEL_API_KEY:?Set FLWR_MODEL_API_KEY in your shell first (never in a file).}"
    write_config
    uv run flower-superlink --insecure > runs/superlink.log 2>&1 &
    echo $! >> "$PIDS"
    echo "Started SuperLink with your model provider (:8000 control, :9092 fleet)."
    ;;
  stop)
    if [[ -f "$PIDS" ]]; then
      while read -r pid; do kill "$pid" 2>/dev/null || true; done < "$PIDS"
      rm -f "$PIDS"
    fi
    uv run python -m forge nodes stop || true
    echo "Stopped."
    ;;
  *) echo "usage: $0 {start|start-real|stop}"; exit 1 ;;
esac
