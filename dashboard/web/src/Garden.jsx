import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { GOLDEN_ANGLE, laptop, person, siteName, slot } from "./lib.js";
import { SvgGlyph, agentIcon } from "./icons.jsx";
import AgentDialog from "./AgentDialog.jsx";

const W = 1200, H = 780, CX = W / 2, CY = H / 2 + 6;
const FLOWER_SCALE = 1.8;
const BACK = [0.34, 1.56, 0.64, 1]; // easeOutBack: the petals overshoot a little, like a real bloom
const PULSE_MS = 1900;
const BUZZ_MS = 1400; // how long the bee revs up before its card opens

// Petal palettes: deep at the base, light at the tip, like a real blossom.
export const PALETTES = {
  brian: ["#b83b5e", "#e8799a", "#fde3ea"],
  vishesh: ["#6d4aa8", "#b39ddb", "#efe7fb"],
  plain: ["#8a7866", "#cbbba8", "#f6efe6"],
};
export const paletteOf = (f) => (f.kind === "generalist" ? "plain" : person(f.owner) === "Brian" ? "brian" : person(f.owner) === "Vishesh" ? "vishesh" : "plain");

// One petal pointing up from the centre, with a small notch at the tip (cherry-blossom shape).
const PETAL = "M0,0 C-9,-4 -15,-17 -11,-27 C-8,-33 -3,-33 0,-29 C3,-33 8,-33 11,-27 C15,-17 9,-4 0,0 Z";

function Defs() {
  return (
    <defs>
      {Object.entries(PALETTES).map(([k, [deep, mid, light]]) => (
        <radialGradient key={k} id={`petal-${k}`} gradientUnits="userSpaceOnUse" cx="0" cy="0" r="32">
          <stop offset="0" stopColor={deep} />
          <stop offset="0.4" stopColor={mid} />
          <stop offset="1" stopColor={light} />
        </radialGradient>
      ))}
      <radialGradient id="sun-core" cx="0.42" cy="0.38" r="0.65">
        <stop offset="0" stopColor="#fff6cf" />
        <stop offset="0.55" stopColor="#fbbf24" />
        <stop offset="1" stopColor="#ea8a0c" />
      </radialGradient>
      <radialGradient id="sun-glow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor="#fcd34d" stopOpacity="0.55" />
        <stop offset="1" stopColor="#fcd34d" stopOpacity="0" />
      </radialGradient>
      <radialGradient id="petal-sun" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="32">
        <stop offset="0" stopColor="#d97706" />
        <stop offset="0.45" stopColor="#fbbf24" />
        <stop offset="1" stopColor="#fde68a" />
      </radialGradient>
      <radialGradient id="seed-disc" cx="0.45" cy="0.4" r="0.6">
        <stop offset="0" stopColor="#8a5a1c" />
        <stop offset="1" stopColor="#4a2c0c" />
      </radialGradient>
      <radialGradient id="bee-body" cx="0.4" cy="0.3" r="0.8">
        <stop offset="0" stopColor="#fff1b8" />
        <stop offset="0.45" stopColor="#fbbf24" />
        <stop offset="1" stopColor="#d97706" />
      </radialGradient>
      <linearGradient id="bee-wing" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.95" />
        <stop offset="1" stopColor="#fde7c8" stopOpacity="0.55" />
      </linearGradient>
      <clipPath id="bee-clip"><ellipse rx="17" ry="12" /></clipPath>
      <radialGradient id="stamen" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor="#a16207" />
        <stop offset="1" stopColor="#facc15" />
      </radialGradient>
    </defs>
  );
}

export function Petals({ pal, T, back, unravel }) {
  const n = 5;
  return Array.from({ length: n }, (_, i) => (
    <g key={i} transform={`rotate(${i * (360 / n) + (back ? 36 : 0)}) scale(${back ? 0.88 : 1})`}>
      <motion.g
        style={{ originX: 0.5, originY: 1 }}
        initial={{ scale: 0 }}
        animate={unravel ? { scale: 1.9, rotate: back ? -75 : 75, opacity: 0 } : { scale: 1, rotate: 0, opacity: 1 }}
        transition={unravel
          ? { delay: i * 0.05 + (back ? 0.08 : 0), duration: 0.7, ease: [0.4, 0, 0.2, 1] }
          : { delay: T * (back ? 0.25 : 0.42) + i * 0.06, duration: T * 0.45, ease: BACK }}
      >
        <path d={PETAL} fill={`url(#petal-${pal})`} stroke={PALETTES[pal][0]} strokeOpacity={0.45} strokeWidth={0.7}
          opacity={back ? 0.75 : 1} />
        {!back && <path d="M0,-4 C-1,-12 1,-18 0,-24" fill="none" stroke={PALETTES[pal][0]} strokeOpacity={0.3} strokeWidth={0.7} />}
      </motion.g>
    </g>
  ));
}

export function Stamen({ T, unravel }) {
  return (
    <motion.g initial={{ scale: 0, opacity: 0 }}
      animate={unravel ? { scale: 2.2, opacity: 0 } : { scale: 1, opacity: 1 }}
      transition={unravel ? { delay: 0.2, duration: 0.5 } : { delay: T * 0.7, duration: 0.5, ease: BACK }}>
      {Array.from({ length: 10 }, (_, i) => {
        const a = (i * 36 * Math.PI) / 180, r = i % 2 ? 9 : 10.5;
        return (
          <g key={i}>
            <line x1={0} y1={0} x2={Math.cos(a) * r} y2={Math.sin(a) * r} stroke="#c98a12" strokeWidth={0.6} strokeOpacity={0.7} />
            <circle cx={Math.cos(a) * r} cy={Math.sin(a) * r} r={1.1} fill="#e8a317" />
          </g>
        );
      })}
      <circle r={4.5} fill="url(#stamen)" />
    </motion.g>
  );
}

// The Generalist is a bee: it visits every flower but has no tools or data of its own.
export function Bee({ T = 1.6, unravel }) {
  const brown = "#4a3320";
  const wing = (x, rot, delay) => (
    <g transform={`translate(${x},-7) rotate(${rot})`}>
      <g className="wing-flap" style={{ animationDelay: delay }}>
        <ellipse cx={0} cy={-11} rx={7.5} ry={12} fill="url(#bee-wing)" stroke="#c9a77a" strokeOpacity={0.6} strokeWidth={0.8} />
        <path d="M0,-2 C-1,-9 1,-15 0,-21" fill="none" stroke="#c9a77a" strokeOpacity={0.45} strokeWidth={0.6} />
      </g>
    </g>
  );
  return (
    <motion.g
      initial={{ scale: 0, opacity: 0 }}
      animate={unravel ? { y: -40, scale: 1.3, opacity: 0 } : { y: 0, scale: 1, opacity: 1 }}
      transition={unravel ? { duration: 0.7, ease: [0.4, 0, 0.2, 1] } : { delay: T * 0.3, duration: 0.6, ease: BACK }}
    >
      <g className="bee-bob">
        <g className="blossom">
          {wing(-4, -28, "0s")}
          <ellipse rx={17} ry={12} fill="url(#bee-body)" stroke="#b45309" strokeOpacity={0.45} strokeWidth={0.9} />
          <g clipPath="url(#bee-clip)">
            <rect x={-7} y={-13} width={4.5} height={26} fill={brown} opacity={0.9} />
            <rect x={2} y={-13} width={4.5} height={26} fill={brown} opacity={0.9} />
            <rect x={-20} y={-13} width={5} height={26} fill={brown} opacity={0.9} />
          </g>
          <path d="M-16.5,-1.5 L-22,0.5 L-16.5,2.5 Z" fill={brown} />
          {wing(3, 18, "-0.06s")}
          <circle cx={17} cy={-1} r={7.5} fill={brown} />
          <circle cx={19.6} cy={-3} r={1.7} fill="#fff" />
          <circle cx={20} cy={-3} r={0.8} fill={brown} />
          <path d="M18,-7.5 C19,-14 22,-16.5 25.5,-16" fill="none" stroke={brown} strokeWidth={1} strokeLinecap="round" />
          <path d="M15,-7.5 C15,-14 17,-17.5 20,-18.5" fill="none" stroke={brown} strokeWidth={1} strokeLinecap="round" />
          <circle cx={25.5} cy={-16} r={1.3} fill={brown} />
          <circle cx={20} cy={-18.5} r={1.3} fill={brown} />
        </g>
      </g>
    </motion.g>
  );
}

// Name with its MUI icon inline, and where it runs underneath. Placed on the side facing away from the hub.
function Label({ f, place, color }) {
  const isGen = f.kind === "generalist";
  const name = f.site ? `${siteName(f.site)} records` : f.name;
  const loc = isGen ? "inside the coordinator" : [siteName(f.site), person(f.owner) && laptop(f.owner)].filter(Boolean).join(" · ");
  const side = place === "left" || place === "right";
  const x = side ? (place === "left" ? -38 : 38) : 0;
  const y = place === "above" ? -50 : place === "below" ? 44 : -2;
  const anchor = place === "left" ? "end" : place === "right" ? "start" : "middle";
  // Measure the rendered name so the icon sits snug against it whatever the font.
  const ref = useRef(null);
  const [w, setW] = useState(name.length * 6);
  useLayoutEffect(() => {
    const measure = () => ref.current && setW(ref.current.getComputedTextLength());
    measure();
    document.fonts?.ready.then(measure); // re-measure once Inter has loaded
  }, [name]);
  const GAP = 14; // icon width + spacing
  const textX = anchor === "middle" ? x + GAP / 2 : anchor === "start" ? x + GAP : x;
  const iconX = anchor === "middle" ? x - w / 2 - GAP / 2 + 5.5 : anchor === "start" ? x + 5.5 : x - w - GAP + 5.5;
  return (
    <>
      <SvgGlyph Icon={agentIcon(f.slug, f.category)} x={iconX} y={y - 4} size={11} color={color} />
      <text ref={ref} x={textX} y={y} textAnchor={anchor} fontSize={11.5} fontWeight={600} fill="var(--ink)">{name}</text>
      <text x={x} y={y + 12} textAnchor={anchor} fontSize={8.5} fill="var(--muted)">{loc}</text>
    </>
  );
}

// A new agent opens like a real blossom: back petals, then front petals, then the stamens.
function Flower({ f, x, y, index, active, place, unravel, onPick, beeRef }) {
  const T = 1.6;
  const pal = paletteOf(f);
  return (
    <g transform={`translate(${x},${y}) scale(${FLOWER_SCALE})`} className="flower-hit" onClick={onPick}
      role="button" tabIndex={0} aria-label={`About ${f.name}`} onKeyDown={(e) => e.key === "Enter" && onPick()}>
      <circle r={38} fill="transparent" />
      {unravel && (
        <motion.circle r={20} fill="none" stroke={PALETTES[pal][1]} strokeWidth={1.5}
          initial={{ scale: 0.5, opacity: 1 }} animate={{ scale: 3.2, opacity: 0 }} transition={{ duration: 0.8, ease: "easeOut" }} />
      )}
      <motion.circle
        r={24} fill="none" stroke={PALETTES[pal][1]} strokeWidth={1}
        initial={{ scale: 0.6, opacity: 0.8 }} animate={{ scale: 2.2, opacity: 0 }}
        transition={{ delay: T * 0.9, duration: 1.2, ease: "easeOut" }}
      />
      <AnimatePresence>
        {active && (
          <motion.circle key="glow" className="pulse" r={36} fill={PALETTES[pal][1]} fillOpacity={0.22}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
        )}
      </AnimatePresence>
      {f.kind === "generalist" ? (
        <g transform="scale(1.35)">
          {/* moved toward the mouse by Garden's animation loop */}
          <g ref={beeRef} style={{ willChange: "transform" }}>
            <Bee T={T} unravel={unravel} />
          </g>
        </g>
      ) : (
      <g className="sway" style={{ animationDuration: `${5 + (index % 3)}s`, animationDelay: `-${index * 0.7}s` }}>
        <g className="spin blossom" style={{ animationDuration: `${80 + (index % 4) * 10}s`, animationDirection: index % 2 ? "reverse" : "normal" }}>
          <g className="bloom-pulse" style={{ animationDelay: `-${(index * 0.9) % 3.2}s` }}>
            <Petals pal={pal} T={T} back unravel={unravel} />
            <Petals pal={pal} T={T} unravel={unravel} />
          </g>
        </g>
        <Stamen T={T} unravel={unravel} />
      </g>
      )}
      <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: T * 0.8, duration: 0.5 }}>
        <Label f={f} place={place} color={PALETTES[pal][1]} />
      </motion.g>
    </g>
  );
}

// The Coordinator is a sunflower drawn like the other blossoms: two rings of golden petals around a seed disc
// whose seeds sit on the same golden-angle spiral the team grows on.
function Hub({ pulse }) {
  const ring = (n, back) => Array.from({ length: n }, (_, i) => (
    <g key={`${back ? "b" : "f"}${i}`} transform={`rotate(${(360 / n) * i + (back ? 180 / n : 0)}) translate(0,-13) scale(${back ? 0.5 : 0.46},${back ? 0.95 : 0.85})`}>
      <path d={PETAL} fill="url(#petal-sun)" stroke="#b45309" strokeOpacity={0.35} strokeWidth={0.9} opacity={back ? 0.8 : 1} />
      {!back && <path d="M0,-4 C-1,-12 1,-18 0,-24" fill="none" stroke="#b45309" strokeOpacity={0.25} strokeWidth={0.9} />}
    </g>
  ));
  return (
    <g transform={`translate(${CX},${CY}) scale(1.75)`}>
      <circle className="sun-glow" r={50} fill="url(#sun-glow)" />
      <AnimatePresence>
        {pulse && (
          <motion.circle
            key={pulse} r={24} fill="none" stroke="var(--hub)" strokeWidth={1.2}
            initial={{ scale: 0.9, opacity: 0.9 }} animate={{ scale: 2.4, opacity: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 1.2 }}
          />
        )}
      </AnimatePresence>
      <g className="spin blossom" style={{ animationDuration: "120s" }}>
        <g className="bloom-pulse" style={{ animationDuration: "4.5s" }}>
          {ring(16, true)}
          {ring(16, false)}
        </g>
      </g>
      <circle r={14} fill="url(#seed-disc)" />
      {Array.from({ length: 70 }, (_, i) => {
        const r = 1.55 * Math.sqrt(i + 0.5), a = i * GOLDEN_ANGLE;
        return <circle key={i} cx={r * Math.cos(a)} cy={r * Math.sin(a)} r={0.75} fill="#d9a441" opacity={0.55 + (i % 3) * 0.12} />;
      })}
      <text y={60} textAnchor="middle" fontSize={11} fontWeight={650} fill="var(--ink)">Coordinator</text>
      <text y={71} textAnchor="middle" fontSize={7.5} fill="var(--muted)">Flower SuperGrid</text>
    </g>
  );
}

// While Bloom waits (building an agent, or waiting for its owner's "y"), a seedling grows in the next free
// spot: the stem rises, two leaves unfold, a bud forms and keeps swelling. When the node joins, the bud gives
// way to the real flower in the same spot. "No" makes it wilt.
function Sprout({ x, y, mode }) {
  const wilted = mode === "rejected";
  const waiting = mode === "approval";
  const green = wilted ? "#b0a393" : "#6b9a55";
  const leaf = (side, delay) => (
    <g transform={`translate(0,${side < 0 ? 4 : -2}) scale(${side},1)`}>
      <motion.path
        d="M0,0 C5,-9 15,-11 20,-6 C15,1 6,3 0,0 Z" fill={green} stroke="#4f7a3d" strokeOpacity={0.4} strokeWidth={0.7}
        style={{ originX: 0, originY: 0.5 }}
        initial={{ scale: 0, rotate: 30 }} animate={{ scale: 1, rotate: 0 }}
        transition={{ delay, duration: 0.7, ease: BACK }}
      />
    </g>
  );
  return (
    <g transform={`translate(${x},${y}) scale(${FLOWER_SCALE})`}>
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: wilted ? 0.45 : 1, rotate: wilted ? 35 : 0 }}
        exit={{ opacity: 0, scale: 1.4, transition: { duration: 0.5 } }}
        transition={{ duration: wilted ? 1.6 : 0.4 }}
      >
        <ellipse cx={0} cy={22} rx={16} ry={3.5} fill="#e7d8c3" />
        <g className={wilted ? undefined : "sway"} style={{ animationDuration: "5s" }}>
          <motion.path
            d="M0,22 C-2,12 2,4 0,-10" fill="none" stroke={green} strokeWidth={2.6} strokeLinecap="round"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: "easeOut" }}
          />
          {leaf(-1, 0.7)}
          {leaf(1, 0.95)}
          <g transform="translate(0,-10)">
            <motion.g initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 1.3, duration: 0.7, ease: BACK }}>
              <g className={waiting ? "bud-swell" : wilted ? undefined : "breathe"}>
                <path d="M0,-17 C8,-10 8,2 0,4 C-8,2 -8,-10 0,-17 Z" fill={wilted ? "#b0a393" : "url(#petal-brian)"}
                  stroke="#b83b5e" strokeOpacity={wilted ? 0 : 0.35} strokeWidth={0.7} />
                <path d="M0,4 C-6,3 -9,-2 -8,-7 C-4,-3 -2,0 0,4 Z" fill={green} />
                <path d="M0,4 C6,3 9,-2 8,-7 C4,-3 2,0 0,4 Z" fill={green} />
              </g>
            </motion.g>
          </g>
        </g>
        <motion.text y={40} textAnchor="middle" fontSize={7} fontWeight={600} fill={wilted ? "var(--muted)" : "var(--ink)"}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
          {wilted ? "Not approved" : waiting ? "Waiting for the owner's “y”…" : "Growing a new agent…"}
        </motion.text>
      </motion.g>
    </g>
  );
}

// Messages: a dot carries the question out along the stem; another carries the answer back.
function Pulse({ p, from, to }) {
  const [a, b] = p.out ? [from, to] : [to, from];
  return (
    <motion.circle
      r={6} fill={p.out ? "var(--hub)" : p.color} stroke="#fffdf9" strokeWidth={1.5}
      initial={{ cx: a.x, cy: a.y, opacity: 0 }}
      animate={{ cx: [a.x, b.x], cy: [a.y, b.y], opacity: [0, 1, 1, 0] }}
      transition={{ duration: 1.2, ease: "easeInOut" }}
    />
  );
}

function labelPlace({ x, y }) {
  const dx = x - CX, dy = y - CY;
  // Beside the flower when it sits level with the hub, unless that would run off the edge.
  if (Math.abs(dx) * 0.55 > Math.abs(dy) && Math.abs(dx) < 340) return dx < 0 ? "left" : "right";
  return dy < 0 ? "above" : "below";
}

export default function Garden({ flowers, messages, now, lastEventId, state }) {
  const positions = useMemo(() => flowers.map((_, k) => slot(k, CX, CY)), [flowers.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const next = slot(flowers.length, CX, CY);
  const [pulses, setPulses] = useState([]);
  const [active, setActive] = useState({});
  const [hubPulse, setHubPulse] = useState(null);
  // The bee. At home it drifts toward the mouse (at most 15 units). Click a flower and it flies there
  // (turning around first if the flower is behind it), lands, and then the flower unravels. One animation
  // loop eases everything and writes the transform directly, so none of this re-renders the garden.
  const svgRef = useRef(null);
  const beeRef = useRef(null);
  const BEE_SCALE = FLOWER_SCALE * 1.35; // the bee's group is drawn at this scale inside its flower
  const lean = useRef({ x: 0, y: 0, tilt: 0 });
  const bee = useRef({ x: 0, y: 0, tilt: 0, face: 1, faceTo: 1, flight: null, away: false, buzz: null });
  const genIndex = flowers.findIndex((f) => f.kind === "generalist");
  const beePos = genIndex >= 0 ? positions[genIndex] : null;
  const onMove = (e) => {
    const svg = svgRef.current, ctm = svg?.getScreenCTM();
    if (!ctm || !beePos) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const dx = pt.x - beePos.x, dy = pt.y - beePos.y, d = Math.hypot(dx, dy) || 1;
    const r = Math.min(15, d * 0.04);
    lean.current = { x: (dx / d) * r, y: (dy / d) * r, tilt: Math.max(-8, Math.min(8, dx * 0.02)) };
  };
  const onLeave = () => { lean.current = { x: 0, y: 0, tilt: 0 }; };

  // Fly to a point given in garden (viewBox) units. Returns how long the whole move takes, in ms.
  const flyTo = (point) => {
    const b = bee.current;
    const to = { x: (point.x - beePos.x) / BEE_SCALE, y: (point.y - beePos.y) / BEE_SCALE };
    const dir = Math.sign(to.x - b.x) || b.faceTo;
    const turn = dir !== b.faceTo ? 320 : 0; // turn around before flying forward
    b.faceTo = dir;
    const dur = Math.max(650, Math.min(1400, Math.hypot(to.x - b.x, to.y - b.y) * BEE_SCALE * 2.4));
    b.flight = { from: { x: b.x, y: b.y }, to, start: performance.now() + turn, dur };
    return turn + dur;
  };

  useEffect(() => {
    let raf, last = performance.now();
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
    const tick = (now) => {
      const dt = Math.min(64, now - last); last = now;
      const b = bee.current, k = 1 - Math.exp(-dt / 220);
      b.face += (b.faceTo - b.face) * (1 - Math.exp(-dt / 70)); // scaleX sweeps through 0: a quick turn
      if (b.flight) {
        const f = b.flight, t = Math.max(0, Math.min(1, (now - f.start) / f.dur)), e = ease(t);
        b.x = f.from.x + (f.to.x - f.from.x) * e;
        b.y = f.from.y + (f.to.y - f.from.y) * e - Math.sin(Math.PI * t) * 14; // a little arc
        b.tilt += ((t > 0 && t < 1 ? Math.max(-12, Math.min(12, (f.to.y - f.from.y) * 0.25)) * b.faceTo : 0) - b.tilt) * k;
        if (t >= 1) b.flight = null;
      } else if (!b.away) {
        for (const key of ["x", "y", "tilt"]) b[key] += (lean.current[key] - b[key]) * k;
      }
      // Clicked bee: wings flap faster and faster (0.12 s -> 0.012 s per beat) and it buzzes harder.
      let jx = 0, jy = 0;
      if (b.buzz !== null) {
        const p = Math.min(1, (now - b.buzz) / BUZZ_MS);
        const amp = 3 * p * p;
        jx = (Math.random() - 0.5) * amp; jy = (Math.random() - 0.5) * amp;
        beeRef.current?.style.setProperty("--flap", `${(0.12 * Math.pow(0.1, p)).toFixed(4)}s`);
      }
      if (beeRef.current) {
        beeRef.current.style.transform =
          `translate(${(b.x + jx).toFixed(2)}px, ${(b.y + jy).toFixed(2)}px) rotate(${b.tilt.toFixed(2)}deg) scale(${b.face.toFixed(3)}, 1)`;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Clicking: the bee flies to the flower and lands on it, the flower unravels, then its card opens.
  // Clicking the bee itself: it flies up and away, then its card opens. Closing sends the bee home.
  const [unravel, setUnravel] = useState(null);
  const [selected, setSelected] = useState(null);
  const busy = useRef(false);
  const pick = (f, k) => {
    if (busy.current || unravel) return;
    busy.current = true;
    if (f.kind === "generalist") { // the bee buzzes itself into a frenzy, then its card opens
      bee.current.buzz = performance.now();
      setTimeout(() => { setSelected(f); busy.current = false; }, BUZZ_MS);
      return;
    }
    let wait = 0;
    if (beePos) {
      bee.current.away = true;
      wait = flyTo({ x: positions[k].x, y: positions[k].y - 28 });
    }
    setTimeout(() => {
      setUnravel(f.key);
      setTimeout(() => { setSelected(f); busy.current = false; }, 650); // keep the agent itself, so a refresh can't drop it
    }, wait);
  };
  const close = () => {
    setSelected(null);
    if (bee.current.buzz !== null) { // calm the wings back down
      bee.current.buzz = null;
      beeRef.current?.style.removeProperty("--flap");
      return;
    }
    setTimeout(() => setUnravel(null), 150);
    if (bee.current.away && beePos) {
      setTimeout(() => {
        const ms = flyTo(beePos);
        setTimeout(() => { bee.current.away = false; }, ms);
      }, 500);
    }
  };
  const seen = useRef(null);

  useEffect(() => {
    const msgs = messages || [];
    const maxId = msgs.reduce((m, x) => Math.max(m, x.id), 0);
    if (seen.current === null || maxId < seen.current) { seen.current = maxId; return; }
    const fresh = msgs.filter((m) => m.id > seen.current).slice(-6);
    seen.current = maxId;
    if (!fresh.length) return;
    const add = [];
    for (const m of fresh) {
      const out = m.src === "bloom";
      const other = out ? m.dst : m.src;
      if (other === "forge" || other === "bloom") { setHubPulse(`h${m.id}`); continue; }
      const base = String(other).split("@")[0];
      const idx = flowers.findIndex((f) => (m.node_id && f.node_id === m.node_id) || f.key === other);
      const k = idx >= 0 ? idx : flowers.findIndex((f) => f.slug === base);
      if (k < 0) continue;
      add.push({ uid: `${m.id}`, k, out, color: flowers[k].color, key: flowers[k].key });
    }
    if (!add.length) return;
    setPulses((ps) => [...ps, ...add].slice(-10));
    setActive((a) => ({ ...a, ...Object.fromEntries(add.map((p) => [p.key, Date.now()])) }));
    const t = setTimeout(() => {
      setPulses((ps) => ps.filter((p) => !add.includes(p)));
      setActive((a) => Object.fromEntries(Object.entries(a).filter(([, ts]) => Date.now() - ts < PULSE_MS)));
    }, PULSE_MS + 50);
    return () => clearTimeout(t);
  }, [lastEventId]); // eslint-disable-line react-hooks/exhaustive-deps

  const budMode = now?.kind === "approval" ? "approval" : now?.kind === "building" || now?.kind === "gap" ? "building"
    : now?.title === "Rejected" ? "rejected" : null;

  return (
    <>
    <svg ref={svgRef} onPointerMove={onMove} onPointerLeave={onLeave} viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" style={{ display: "block" }}>
      <Defs />
      {flowers.map((f, k) => (
        <motion.line
          key={`e-${f.key}`} x1={CX} y1={CY} x2={positions[k].x} y2={positions[k].y}
          stroke={active[f.key] ? "var(--hub)" : "var(--vine)"} strokeWidth={active[f.key] ? 2.5 : 1.5}
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, ease: "easeOut" }}
        />
      ))}
      {pulses.map((p) => positions[p.k] && <Pulse key={p.uid} p={p} from={{ x: CX, y: CY }} to={positions[p.k]} />)}
      <Hub pulse={hubPulse} />
      {/* the bee is drawn last so it flies over the other flowers */}
      {flowers.map((f, k) => [f, k]).sort(([a], [b]) => (a.kind === "generalist") - (b.kind === "generalist")).map(([f, k]) => (
        <Flower key={f.key} f={f} x={positions[k].x} y={positions[k].y} index={k} active={!!active[f.key]} place={labelPlace(positions[k])}
          unravel={unravel === f.key} onPick={() => pick(f, k)} beeRef={f.kind === "generalist" ? beeRef : null} />
      ))}
      <AnimatePresence>
        {/* one seedling per free spot: it keeps growing across building -> waiting, and a new one starts at the next spot */}
        {budMode && <Sprout key={`sprout-${flowers.length}`} x={next.x} y={next.y} mode={budMode} />}
      </AnimatePresence>
    </svg>
    <AgentDialog flower={selected} state={state} onClose={close} />
    </>
  );
}
