import React, { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, MotionConfig } from "framer-motion";
import useApiState from "./useApiState.js";
import { buildFlowers } from "./lib.js";
import bloomMark from "./assets/bloom.svg";
import TopBar from "./TopBar.jsx";
import Garden from "./Garden.jsx";
import NowCard from "./NowCard.jsx";
import ProofDialog from "./ProofDialog.jsx";
import StoryDialog from "./StoryDialog.jsx";
import MessagesDialog from "./MessagesDialog.jsx";

// Always say what Bloom is doing during the live part, with a running timer so waiting never feels stuck.
function ActivityBar({ activity }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  if (!activity) return null;
  const secs = Math.max(0, Math.round(now / 1000 - activity.since));
  const clock = secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${String(secs % 60).padStart(2, "0")}s`;
  return (
    <AnimatePresence mode="wait">
      <motion.div key={activity.text} className="activity-bar"
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.3 }}>
        <span className="activity-dot" aria-hidden />
        <div>
          <strong>Happening now</strong>
          <p role="status">{activity.text}</p>
        </div>
        <time>{clock}</time>
      </motion.div>
    </AnimatePresence>
  );
}

// After the replay, one press starts the live part: deliver the hospital agent to its owners, then answer.
function ContinueButton({ stage }) {
  const [state, setState] = useState("idle");
  if (stage !== "ready" && state !== "starting") return null;
  const go = async () => {
    setState("starting");
    try {
      const res = await fetch("/api/continue", { method: "POST", headers: { "X-Bloom": "continue" } });
      setState(res.ok ? "started" : "error");
    } catch { setState("error"); }
  };
  return (
    <motion.button className="continue-btn" onClick={go} disabled={state === "starting"}
      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
      {state === "starting" ? "Starting…" : state === "error" ? "Couldn't start. Try again" : "Continue live →"}
      <span>Ask both hospitals for their records</span>
    </motion.button>
  );
}

export default function App() {
  const { state, online } = useApiState(700);
  const [open, setOpen] = useState(null);
  const flowers = useMemo(() => state ? buildFlowers(state) : [], [state]);

  useEffect(() => {
    const onKey = e => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest?.("input, textarea, select, [contenteditable=true]")) return;
      const key = e.key.toLowerCase();
      if (key === "escape") setOpen(null);
      else if (["p", "t", "l"].includes(key)) setOpen(value => value === key ? null : key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!state) return (
    <main className="loading-screen">
      <img src={bloomMark} alt="" width="48" height="48" />
      <p role="status">{online ? "Loading Bloom…" : "Waiting for the Bloom server. Retrying automatically…"}</p>
    </main>
  );

  const story = state.story || {};
  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell">
        <TopBar replay={state.replay} stage={state.stage} online={online} onOpen={setOpen} />
        <main id="main">
          <section className="page-intro">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={story.headline} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: .2 }}>
                <h1>{story.headline || "Your team"}</h1>
                {story.sub && <p>{story.sub}</p>}
              </motion.div>
            </AnimatePresence>
          </section>
          {!online && <p className="connection-notice">Connection interrupted. Showing the last received update.</p>}
          <div className="workspace-grid">
            <section className="garden-panel" aria-label="Agent garden">
              <span className="team-count">{state.team?.length || 0} agents</span>
              <div className="garden-canvas">
                <Garden flowers={flowers} messages={state.messages} now={state.activity?.waiting ? { kind: "approval" } : story.now} lastEventId={state.last_event_id} state={state} />
              </div>
              <div className="legend" aria-label="Agent locations">
                <span><i style={{ background: "var(--brian)" }} />Brian’s laptop</span>
                <span><i style={{ background: "var(--vishesh)" }} />Vishesh’s laptop</span>
                <span><i style={{ background: "var(--plain)" }} />Coordinator</span>
              </div>
            </section>
            <aside className="activity-column" aria-label="Current activity">
              <ContinueButton stage={state.stage} />
              <ActivityBar activity={state.activity} />
              <NowCard now={story.now} onProof={() => setOpen("p")} />
            </aside>
          </div>
        </main>
        <ProofDialog open={open === "p"} onClose={() => setOpen(null)} ev={state.eval} beforeAfter={state.before_after} />
        <StoryDialog open={open === "t"} onClose={() => setOpen(null)} state={state} />
        <MessagesDialog open={open === "l"} onClose={() => setOpen(null)} messages={state.messages} />
      </div>
    </MotionConfig>
  );
}
