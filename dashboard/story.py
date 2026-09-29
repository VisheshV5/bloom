"""Turn Bloom's raw events into a plain-English story for the dashboard."""

from __future__ import annotations

SKILLS = {
    "sql": ("Patient records", "🏥"),
    "stats": ("Statistics", "📊"),
    "dates": ("Dates", "📅"),
    "units": ("Unit conversion", "📏"),
    "extraction": ("Text extraction", "🔎"),
    "writing": ("Writing", "✍️"),
    "currency": ("Currency", "💱"),
    "extraction": ("Text extraction", "🔎"),
}
JOBS = {
    "generalist": "Answers anything, but has no tools",
    "sql": "Queries its own hospital's patient records (aggregates only)",
    "stats": "Crunches the numbers exactly",
    "dates": "Counts days without off-by-one mistakes",
    "units": "Converts units precisely",
    "extraction": "Pulls details out of messy text",
    "writing": "Writes the note for the quality committee",
}
STEPS = ["Practice", "Spot a weakness", "Build an agent", "Human approval", "New agent joins", "Team task"]
ROLE_TEXT = {
    "architect": "The Architect is designing it",
    "builder": "The Builder is writing its code",
    "reviewer": "The Reviewer is testing it",
    "build": "The Reviewer is building it",
}


def display_name(slug: str | None) -> str:
    if not slug:
        return "an agent"
    words = slug.replace("_", "-").split("-")
    return " ".join(w.upper() if w in {"sql", "ai", "api"} else w.capitalize() for w in words)


def skill(category: str | None) -> str:
    return SKILLS.get(category or "", (category or "general", ""))[0]


def icon(category: str | None, kind: str | None = None) -> str:
    if kind == "generalist":
        return "💬"
    return SKILLS.get(category or "", ("", "🤖"))[1] or "🤖"


def job(agent: dict) -> str:
    if agent.get("kind") == "generalist":
        return JOBS["generalist"]
    text = JOBS.get(agent.get("category") or "")
    if text:
        return text
    purpose = (agent.get("purpose") or "").rstrip(".")
    return purpose if len(purpose) <= 60 else purpose[:57].rstrip() + "…"


def build_story(events: list[dict], agents_by_slug: dict[str, dict]) -> dict:
    """Walk the events and keep the latest plain-English state."""
    step = 0
    headline = "Waiting for Bloom to start…"
    sub = ""
    now: dict = {"kind": "idle", "title": "Watching the team", "body": "Nothing to approve right now."}
    tasks = 0
    round_name = ""
    building: dict = {}
    for ev in events:
        t = ev["type"]
        if t == "phase":
            name = str(ev.get("name") or "")
            if name == "session start":
                step, headline = 0, "Bloom starts with one agent: the Generalist."
                sub = "It can answer anything, but it has no tools and no access to anyone's data."
                now = {"kind": "idle", "title": "One agent", "body": "Watch the team grow."}
            elif name.startswith("round 1") or name == "bench":
                step, round_name = 1, "practice"
                headline = "The team is working through practice questions."
                sub = "Bloom watches which kinds of questions it keeps getting wrong."
            elif name.startswith("round 2"):
                step, round_name = 1, "retest"
                headline = "Re-testing the same questions with the bigger team."
                sub = "Questions now go to the specialist for each skill."
            elif name == "final task":
                step = 6
                headline = "The whole team is solving one big question together."
                sub = "Each specialist does its part and hands the result to the next."
            elif name.startswith("eval"):
                headline = "Proof: testing on questions the team has never seen."
                sub = "Same AI model for everyone. Press P to see the results."
        elif t == "task_result":
            tasks += 1
        elif t == "gap_flagged":
            step = 2
            cat = ev.get("category")
            if ev.get("kind") == "capability":
                headline = f"The big question needs {skill(cat).lower()}, and nobody on the team can do it."
                sub = f"Bloom will build a {display_name(ev.get('capability'))}."
            else:
                acc = ev.get("accuracy")
                window = ev.get("window") or 5
                right = round((acc or 0) * window)
                headline = f"The team got only {right} of {window} {skill(cat).lower()} questions right."
                sub = "That's a skill gap, so Bloom will build a specialist for it."
            now = {"kind": "gap", "title": f"Weak spot: {skill(cat)}", "icon": icon(cat), "body": sub}
        elif t == "forge_stage":
            stage = ev.get("stage")
            slug = ev.get("slug") or building.get("slug")
            if stage == "architect":
                building = {"slug": None, "category": ev.get("category"), "problem": None}
            if slug:
                building["slug"] = slug
            if stage in ROLE_TEXT:
                step = 3
                role = "reviewer" if stage == "build" else stage
                order = ["architect", "builder", "reviewer"]
                name = display_name(building["slug"]) if building.get("slug") else f"{skill(building.get('category'))} specialist"
                headline = f"Building a new agent: {name}."
                sub = ROLE_TEXT[stage] + "."
                if role == "builder" and building.get("problem"):
                    sub = "The Builder is fixing what the Reviewer found."
                now = {"kind": "building", "title": f"Building: {name}", "icon": icon(building.get("category")),
                       "body": sub, "problem": building.get("problem"),
                       "roles": {r: ("done" if order.index(r) < order.index(role) else
                                     "active" if r == role else "todo") for r in order}}
            elif stage == "review_failed":
                notes = ev.get("notes") or []
                building["problem"] = (notes[0] if notes else "The Reviewer found a problem.")[:140]
                sub = "The Reviewer found a problem and sent it back to the Builder."
                now = {**now, "body": sub, "problem": building["problem"]}
            elif stage == "review_passed":
                sub = "It passed every check and its test questions."
            elif stage == "reused":
                headline = f"{display_name(slug)} already exists, so Bloom reuses it instead of building a copy."
                sub = ""
            elif stage in ("abandoned", "invalid_spec", "error"):
                headline = "The Forge couldn't build a good enough agent this time."
                sub = "Nothing was added. The team keeps working with what it has."
                now = {"kind": "idle", "title": "Build stopped", "body": sub}
        elif t == "approval_pending":
            step = 4
            name = display_name(ev.get("slug"))
            headline = f"{name} is ready. Waiting for a human to approve it."
            tests = ev.get("tests") or {}
            passed = f"Passed {tests.get('passed')} of {tests.get('total')} test questions." if tests.get("total") else "Passed every check."
            sub = "Nothing joins the team without a person saying yes."
            agent = agents_by_slug.get(ev.get("slug"), {})
            now = {"kind": "approval", "title": f"{name} is ready", "icon": icon(ev.get("category") or agent.get("category")),
                   "body": ev.get("purpose") or "", "detail": passed,
                   "tools": len(ev.get("tools") or [])}
        elif t == "proposal":
            step = 4
            name = display_name(ev.get("slug"))
            headline = f"{name} is ready. Waiting for the data owner to approve it on their machine."
            sub = "Only the owner of the node (and its data) can say yes. Bloom can't approve it for them."
            tests = ev.get("tests") or {}
            detail = tests.get("skipped") or (f"Passed {tests.get('passed')} of {tests.get('total')} test questions."
                                              if tests.get("total") else "Passed every check.")
            now = {"kind": "approval", "title": f"{name} is ready", "icon": icon(ev.get("category")),
                   "body": ev.get("purpose") or "", "detail": detail, "tools": len(ev.get("tools") or []),
                   "owner": True, "sha": (ev.get("spec_sha256") or "")[:12]}
        elif t == "delivered":
            name = display_name(ev.get("slug"))
            who = str(ev.get("owner") or "the data owner").capitalize()
            if ev.get("ok"):
                step = 4
                headline = f"{name} was delivered over the Flower Grid to {who}'s machine."
                sub = f"Nothing runs until {who} reads the code and types y."
                now = {**now, "kind": "approval", "owner": True,
                       "detail": f"In {who}'s inbox via node {str(ev.get('node_name') or ev.get('node_id'))}. Waiting for y."}
            else:
                sub = f"Delivery failed: {ev.get('error')}"
        elif t == "approval_resolved":
            if not ev.get("approved"):
                headline = f"The human said no, so {display_name(ev.get('slug'))} was not added."
                sub = ""
                now = {"kind": "idle", "title": "Rejected", "body": "Nothing was added."}
        elif t in ("agent_added", "node_joined"):
            slug = ev.get("slug")
            if slug == "generalist":
                continue
            step = 5
            agent = agents_by_slug.get(slug, {})
            headline = f"{display_name(slug)} joined the team."
            sub = f"From now on, {skill(agent.get('category')).lower()} questions go to it."
            now = {"kind": "joined", "title": f"Welcome, {display_name(slug)}", "icon": icon(agent.get("category")),
                   "body": job(agent) if agent else ""}
        elif t == "final_task":
            step = 6
            ok = ev.get("passed")
            headline = "The team answered the big question." if ok else "The team finished the big question."
            chain = [display_name(a) for a in ev.get("agents") or []]
            sub = " → ".join(chain)
            now = {"kind": "final", "title": "Answer", "body": ev.get("answer") or "", "passed": ok, "chain": chain}
        elif t == "eval_result":
            if now.get("kind") == "final":  # keep the team's answer on screen; just point to the proof
                now = {**now, "proof_ready": True, "simulated": ev.get("simulated")}
            else:
                now = {"kind": "proof", "title": "Proof is ready",
                       "body": "Press P to see how the specialists did on unseen questions.",
                       "simulated": ev.get("simulated")}
    return {"step": step, "steps": STEPS, "headline": headline, "sub": sub, "now": now,
            "tasks": tasks, "round": round_name}


def before_after(registry_agents: list[dict]) -> list[dict]:
    """Per skill: how often the generalist was right vs the specialist (practice questions)."""
    gen = next((a for a in registry_agents if a.get("kind") == "generalist"), None)
    rows = []
    cats = sorted({c for a in registry_agents for c in (a.get("scores") or {})})
    for c in cats:
        g = (gen or {}).get("scores", {}).get(c)
        spec = next((a for a in registry_agents if a.get("kind") == "specialist" and a.get("category") == c), None)
        s = (spec or {}).get("scores", {}).get(c)
        pct = lambda x: round(100 * x["correct"] / x["attempts"]) if x and x["attempts"] else None  # noqa: E731
        rows.append({"category": c, "skill": skill(c), "icon": icon(c), "before": pct(g), "after": pct(s),
                     "specialist": display_name(spec["slug"]) if spec else None})
    return rows
