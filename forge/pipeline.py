"""The Forge: gap -> spec -> build -> review (<=2 retries) -> approval -> deploy -> join -> [publish]."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bloom.specs import module_name, spec_from_source, spec_hash, validate_spec
from forge.approval import TerminalApprover, unified_diff
from forge.nodes import NodeManager
from forge.paths import PROPOSALS, REGISTRY, ROOT, SPECIALISTS_DIR
from forge.publish import publish
from forge.registry import Registry
from forge.render import render_module
from forge.review_checks import build_check, contract_check, postprocess_check, static_check

MAX_RETRIES = 2
MAX_EXAMPLES = 3
EXAMPLE_INPUT_CHARS = 700
TESTS_PER_REVIEW = 3
TESTS_REQUIRED = 2


def _json_safe(review: dict) -> dict:
    return json.loads(json.dumps(review, default=str))


def local_notes(review: dict) -> list[str]:
    """Deterministic notes for mechanical failures (no model call needed)."""
    notes = [f"Fix: {p}" for p in review.get("static", []) + review.get("contract", []) + review.get("postprocess", [])]
    build = review.get("build")
    if build and not build.get("ok", True):
        notes.append("flwr build failed: " + str(build.get("log", ""))[-300:])
    return notes


@dataclass
class ForgeOutcome:
    outcome: str  # approved | rejected | failed_review | reused | invalid_spec | error
    slug: str | None = None
    attempts: int = 0
    notes: list[str] = field(default_factory=list)


class Forge:
    def __init__(self, backend, registry: Registry, bus, approver: TerminalApprover,
                 nodes: NodeManager, benchmark: list[dict], run_build: bool = True,
                 publish_standalone: bool = False):
        self.backend = backend
        self.registry = registry
        self.bus = bus
        self.approver = approver
        self.nodes = nodes
        self.benchmark = benchmark
        self.run_build = run_build
        self.publish_standalone = publish_standalone

    def _stage(self, stage: str, **data) -> None:
        self.bus.emit("forge_stage", stage=stage, **data)

    def _test_tasks(self, category: str, exclude: set[str]) -> list[dict]:
        pool = [t for t in self.benchmark if t["category"] == category]
        held_out = [t for t in pool if t["id"] not in exclude] or pool
        return held_out[-TESTS_PER_REVIEW:]

    def worked_examples(self, gap: dict) -> list[list[str]]:
        """Worked solutions for the dev tasks the team FAILED (never test tasks, never review tasks)."""
        by_id = {t["id"]: t for t in self.benchmark}
        out = []
        for f in gap.get("failures", []):
            t = by_id.get(f.get("task_id"))
            if not t or not t.get("how"):
                continue
            prompt = t["prompt"] if len(t["prompt"]) <= EXAMPLE_INPUT_CHARS else t["prompt"][:EXAMPLE_INPUT_CHARS] + " ..."
            out.append([prompt, f"Method: {t['how']}\nFINAL: {t['answer']}"])
            if len(out) == MAX_EXAMPLES:
                break
        return out

    @staticmethod
    def _module_fields(source: str) -> dict:
        """Instructions/examples/verify exactly as rendered, so tests run the real module."""
        import ast

        out = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in {"INSTRUCTIONS", "EXAMPLES", "VERIFY", "TOOLS"}:
                    out[name.lower()] = ast.literal_eval(node.value)
        return out

    def _review(self, spec: dict, source: str, exclude: set[str]) -> dict:
        from evaluator.scorer import check

        results: dict = {"static": static_check(source)}
        results["contract"] = contract_check(source, spec) if not results["static"] else []
        if not results["static"] and not results["contract"]:
            results["postprocess"] = postprocess_check(source)
        else:
            results["postprocess"] = []
        blocking = results["static"] + results["contract"] + results["postprocess"]
        if not blocking and self.run_build:
            self._stage("build", slug=spec["slug"])
            results["build"] = build_check(source, spec["slug"])
        needs_data = "run_sql" in (spec.get("tools") or [])
        if not blocking and needs_data and not getattr(self.backend, "has_data", True):
            # The data lives only on the owner's node, so the coordinator can't run SQL tests.
            results["tests"] = {"passed": 0, "total": 0, "required": 0,
                                "skipped": "data-bound: tested on the data owner's node after approval"}
        elif not blocking and (results.get("build") or {"ok": True})["ok"]:
            tests = self._test_tasks(spec["category"], exclude)
            candidate = {**spec, **self._module_fields(source)}
            jobs = [{"arm": "candidate", "spec": candidate, "task_id": t["id"], "prompt": t["prompt"], "rep": 0}
                    for t in tests]
            answers = {r["task_id"]: r.get("answer") for r in self.backend.eval_batch(jobs)} if jobs else {}
            passed = sum(int(check(t, answers.get(t["id"]))) for t in tests)
            required = min(TESTS_REQUIRED, len(tests))
            results["tests"] = {"passed": passed, "total": len(tests), "required": required}
        ok = (not blocking and (results.get("build") or {"ok": True})["ok"]
              and (results.get("tests") or {}).get("passed", 0) >= (results.get("tests") or {}).get("required", 1))
        results["ok"] = ok
        return results

    def _propose(self, spec: dict, source: str, review: dict, examples: list, gap: dict, attempt: int) -> ForgeOutcome:
        """Write the module (status: proposed) and runs/proposals/<slug>.json, then stop.

        The node owner's launcher shows the spec + module, asks them y/N on their machine, adds
        spec_sha256 to their approved list and starts the node. `python -m forge activate <slug>`
        flips the registry entry to active once that node is online.
        """
        from forge.registry import now_iso

        slug = spec["slug"]
        final_source = source.replace("Approved by: pending.", "Approved by: node owner (on their machine).")
        module_path = SPECIALISTS_DIR / f"{module_name(slug)}.py"
        module_path.write_text(final_source)
        digest = spec_hash(spec_from_source(final_source))
        self.registry.add_specialist(spec, str(module_path.relative_to(ROOT)), approved_by=None, status="proposed")
        self.registry.get(slug)["spec_sha256"] = digest
        self.registry.save()
        PROPOSALS.mkdir(parents=True, exist_ok=True)
        proposal = {
            "slug": slug, "spec": spec, "module_source": final_source, "spec_sha256": digest,
            "reviewer_results": _json_safe(review), "dev_examples_used": examples, "created_at": now_iso(),
            "federation": self.nodes.federation, "suggested_node_name": f"{slug}@<owner>",
            "node_config": {"bloom-specialty": slug, "bloom-db": "/abs/path/to/coffee.sqlite (if the specialist needs data)",
                            "bloom-approved": "~/.bloom/approved.json"},
        }
        path = PROPOSALS / f"{slug}.json"
        path.write_text(json.dumps(proposal, indent=2))
        self.bus.emit("proposal", slug=slug, category=spec["category"], purpose=spec["purpose"], tools=spec["tools"],
                      tests=review.get("tests"), attempts=attempt, spec_sha256=digest, path=str(path.relative_to(ROOT)))
        self.registry.log_forge(gap=gap, outcome="proposed", slug=slug, attempts=attempt)
        print(f"Proposal ready: send {path.relative_to(ROOT)} to the node owner (spec_sha256 {digest[:16]}…). "
              f"Then: python -m forge activate {slug}")
        return ForgeOutcome("proposed", slug, attempt)


    def grow(self, gap: dict) -> ForgeOutcome:
        """Run one Forge cycle for a gap report or a capability request."""
        category = gap.get("category")
        reuse = self.registry.find_reusable(category, [gap.get("capability")] if gap.get("capability") else None)
        if reuse:
            self.registry.log_forge(gap=gap, outcome="reused", slug=reuse["slug"], attempts=0)
            self._stage("reused", slug=reuse["slug"], category=category)
            return ForgeOutcome("reused", reuse["slug"])

        self.bus.emit("agent_status", slug="architect", status="working")
        self._stage("architect", category=category, reason=gap.get("kind", "gap"))
        try:
            spec = self.backend.architect(gap, self.registry.snapshot())
        except Exception as exc:  # noqa: BLE001
            self._stage("error", error=str(exc))
            self.bus.emit("agent_status", slug="architect", status="idle")
            return ForgeOutcome("error", notes=[str(exc)])
        spec.setdefault("version", 1)
        spec.setdefault("capabilities", [])
        if category:  # the gap decides the category, not the model
            spec["category"] = category
        self.bus.emit("agent_status", slug="architect", status="idle")
        problems = validate_spec(spec)
        if problems:
            self._stage("invalid_spec", problems=problems)
            self.registry.log_forge(gap=gap, outcome="invalid_spec", slug=spec.get("slug"), attempts=0)
            return ForgeOutcome("invalid_spec", spec.get("slug"), notes=problems)
        slug = spec["slug"]
        if self.registry.get(slug):
            return ForgeOutcome("reused", slug)
        self._stage("spec", slug=slug, spec=spec)

        exclude = {f.get("task_id") for f in gap.get("failures", [])}
        examples = self.worked_examples(gap)
        if examples:
            self._stage("examples", slug=slug, count=len(examples))
        notes: list[str] | None = None
        source, review = "", {}
        attempt = 0
        for attempt in range(1, MAX_RETRIES + 2):
            self.bus.emit("agent_status", slug="builder", status="working")
            self._stage("builder", slug=slug, attempt=attempt, notes=notes or [])
            try:
                fields = self.backend.builder(spec, notes, examples)
                # Worked examples are injected deterministically (the Builder may add its own).
                own = [e for e in (fields.get("examples") or []) if isinstance(e, (list, tuple)) and len(e) == 2]
                fields["examples"] = (examples + own)[:MAX_EXAMPLES]
                source = render_module(spec, fields)
            except Exception as exc:  # noqa: BLE001
                fields, source = {}, ""
                review = {"ok": False, "static": [f"builder error: {exc}"]}
            self.bus.emit("agent_status", slug="builder", status="idle")
            if source:
                self.bus.emit("agent_status", slug="reviewer", status="working")
                self._stage("reviewer", slug=slug, attempt=attempt)
                review = self._review(spec, source, exclude)
                self.bus.emit("agent_status", slug="reviewer", status="idle")
            review["attempts"] = attempt
            if review.get("ok"):
                self._stage("review_passed", slug=slug, attempt=attempt, tests=review.get("tests"))
                break
            notes = local_notes(review)
            if not notes:  # only ask the Reviewer model when the failure needs judgment (test answers)
                notes = self.backend.reviewer_notes(spec, source, review) or ["Review failed; fix the issues."]
            self._stage("review_failed", slug=slug, attempt=attempt, notes=notes)
        else:
            self.registry.log_forge(gap=gap, outcome="failed_review", slug=slug, attempts=attempt)
            self._stage("abandoned", slug=slug, attempts=attempt)
            return ForgeOutcome("failed_review", slug, attempt, notes or [])

        if self.nodes.mode == "node":  # node-hosted: the data owner approves on THEIR machine
            return self._propose(spec, source, review, examples, gap, attempt)

        # ── human approval ───────────────────────────────────────────────
        module_path = SPECIALISTS_DIR / f"{module_name(slug)}.py"
        rel_module = str(module_path.relative_to(ROOT))
        final_source = source.replace("Approved by: pending.", "Approved by: vverm.")
        before_registry = REGISTRY.read_text() if REGISTRY.exists() else ""
        commands = self.nodes.planned_commands(slug)
        self.bus.emit("approval_pending", slug=slug, category=spec["category"], purpose=spec["purpose"], tools=spec["tools"],
                      tests=review.get("tests"), attempts=attempt)
        self.approver.show(spec, [unified_diff(rel_module, "", final_source)], review, commands)
        approved = self.approver.confirm(f"Approve specialist '{slug}' and add it to the team?")
        self.bus.emit("approval_resolved", slug=slug, approved=approved)
        if not approved:
            self.registry.log_forge(gap=gap, outcome="rejected", slug=slug, attempts=attempt)
            return ForgeOutcome("rejected", slug, attempt)

        # ── deploy + join ────────────────────────────────────────────────
        module_path.write_text(final_source)
        entry = self.registry.add_specialist(spec, rel_module, approved_by="vverm")
        after_registry = REGISTRY.read_text()
        print(unified_diff("registry.json", before_registry, after_registry)[:3000])
        self.bus.emit("agent_added", slug=slug, category=spec["category"], purpose=spec["purpose"],
                      created_by=entry["created_by"])
        try:
            node = self.nodes.join(slug)
            self.registry.set_node(slug, node)
        except Exception as exc:  # noqa: BLE001 - agent still works in-process
            self._stage("join_failed", slug=slug, error=str(exc))
        if self.publish_standalone:
            try:
                hub = publish(slug, spec["purpose"], self.approver.confirm,
                              simulate=self.backend.name == "mock", bus=self.bus)
                if hub:
                    self.registry.set_hub(slug, hub)
            except Exception as exc:  # noqa: BLE001
                self._stage("publish_failed", slug=slug, error=str(exc))
        self.registry.log_forge(gap=gap, outcome="approved", slug=slug, attempts=attempt)
        self._stage("done", slug=slug)
        return ForgeOutcome("approved", slug, attempt)
