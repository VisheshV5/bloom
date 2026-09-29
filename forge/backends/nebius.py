"""Optional real-model backend that runs Bloom's roles locally (no SuperGrid).

Uses an OpenAI-compatible Responses endpoint from the environment:
  FLWR_MODEL_API_ENDPOINT  e.g. https://api.tokenfactory.tf-ca1.nebius.com/v1/responses
  FLWR_MODEL_API_KEY       (never written to disk or logged)
  BLOOM_LOCAL_MODEL        model id to use for every role (default: Kimi-K2.7-Code)
Specialists run in-process with Bloom's local tools. Useful as a fallback when
SuperGrid is unavailable; it does not exercise Flower, so say so if you demo it.
"""

from __future__ import annotations

import json
import os

from bloom import forge_roles, orchestrator
from bloom.local_session import LocalAgent, LocalContext
from forge.backends.base import TaskResult

DEFAULT_MODEL = "dedicated/flowerai/Kimi-K2.7-Code-1OUHWL"


class _ModelOverride:
    """Wraps an OpenAI client so every request uses one model id."""

    def __init__(self, client, model: str):
        self._client, self._model = client, model
        self.responses = self

    def create(self, **kwargs):
        kwargs["model"] = self._model
        return self._client.responses.create(**kwargs)


class NebiusBackend:
    name = "nebius"

    def __init__(self, bus, workers: int = 12, **_):
        from forge.envfile import load_env

        env = {**load_env(), **{k: v for k, v in os.environ.items() if k.startswith(("FLWR_MODEL_", "BLOOM_"))}}
        endpoint = env.get("FLWR_MODEL_API_ENDPOINT")
        key = env.get("FLWR_MODEL_API_KEY")
        self.workers = workers
        from bloom.tools import sql
        from forge.paths import RUNS

        db = env.get("BLOOM_DB") or str(RUNS / "coffee.sqlite")
        self.has_data = sql.configure(db)  # local copy (python -m tasks.export_sqlite)
        if not endpoint or not key:
            raise RuntimeError("Set FLWR_MODEL_API_ENDPOINT and FLWR_MODEL_API_KEY in the environment.")
        from openai import OpenAI

        base_url = endpoint.rstrip("/")
        if base_url.endswith("/responses"):
            base_url = base_url[: -len("/responses")]
        self.model = env.get("BLOOM_LOCAL_MODEL") or env.get("BLOOM_NODE_MODEL") or DEFAULT_MODEL
        self.client = _ModelOverride(OpenAI(base_url=base_url, api_key=key, max_retries=1), self.model)
        self.bus = bus

    def _ctx(self, registry=None) -> LocalContext:
        return LocalContext({"bloom.registry": json.dumps(registry or []), "bloom.routing": "inprocess",
                             "bloom.orchestrator-model": self.model})

    def architect(self, gap, registry):
        return forge_roles.architect({"gap": gap, "registry": registry}, self._ctx(), self.client)["spec"]

    def builder(self, spec, notes, examples=None):
        return forge_roles.builder({"spec": spec, "notes": notes or [], "examples": examples or []},
                                   self._ctx(), self.client)["fields"]

    def reviewer_notes(self, spec, source, results):
        return [str(n) for n in forge_roles.reviewer(
            {"spec": spec, "source": source, "results": results}, self._ctx(), self.client).get("notes", [])]

    def run_task(self, task, registry, mode="single"):
        job = json.dumps({"task": task["prompt"], "mode": task.get("mode", mode), "job_id": task.get("id")})
        agent = LocalAgent(job)
        res = orchestrator.orchestrate(agent, self._ctx(registry), job, client=self.client)
        steps = res["steps"]
        for s in steps:
            self.bus.emit("message", src="bloom", dst=s["specialist"], node_id=None, text=f"step {s['step_id']}")
            self.bus.emit("message", src=s["specialist"], dst="bloom", node_id=None, text=f"FINAL: {s['answer']}")
        return TaskResult(answer=res["answer"], output=res["output"],
                          agent=steps[-1]["specialist"] if steps else "generalist", ok=res["ok"],
                          steps=steps, missing_capabilities=res["missing_capabilities"], ms=res["ms"])

    def run_with_spec(self, spec, task):
        res = forge_roles.solve({"spec": {**spec, "model": self.model}, "task": task["prompt"]},
                                self._ctx(), self.client)
        return TaskResult(answer=res["answer"], output=res["output"], agent=spec["slug"], ok=res["ok"],
                          error=res["error"])

    def eval_batch(self, jobs):
        slim = [{**j, "spec": {**j["spec"], "model": self.model}} for j in jobs]
        # Local run: no 5-minute task limit, so give the whole batch a generous budget.
        return forge_roles.eval_batch({"jobs": slim, "workers": self.workers, "budget_s": 3 * 3600},
                                      self._ctx(), self.client)["results"]
