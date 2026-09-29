import React, { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { laptop, person, siteName, slot, vine } from "./lib.js";
import { Hub as HubIcon, SvgGlyph, agentIcon } from "./icons.jsx";

const W = 1200, H = 780, CX = W / 2, CY = H / 2 + 6;
const FLOWER_SCALE = 1.8;
const BACK = [0.34, 1.56, 0.64, 1]; // easeOutBack: the petals overshoot a little, like a real bloom
const PULSE_MS = 1900;

function Leaf({ p, delay, color = "var(--vine)", size = 1 }) {
  return (
    <g transform={`translate(${p.x},${p.y}) rotate(${p.angle - 40})`}>
      <motion.path
        d="M0,0 C4,-6 12,-6 16,0 C12,6 4,6 0,0 Z"
        fill={color}
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: size, opacity: 0.9 }}
        transition={{ delay, duration: 0.5, ease: BACK }}
      />
    </g>
  );
}

// Stem 0–35%, inner petals 25–65%, outer petals 40–90%, then an idle sway (flower-bloom's choreography, in 2D).
function Flower({ f, x, y, index, active, place }) {
  const T = 1.6;
  const isGen = f.kind === "generalist";
  const loc = isGen ? "inside the coordinator" : [siteName(f.site), person(f.owner) && laptop(f.owner)].filter(Boolean).join(" · ");
  return (
    <g transform={`translate(${x},${y}) scale(${FLOWER_SCALE})`}>
      <motion.circle
        r={26} fill="none" stroke={f.color} strokeWidth={2}
        initial={{ scale: 0.5, opacity: 0.9 }} animate={{ scale: 2.6, opacity: 0 }}
        transition={{ delay: T * 0.8, duration: 1.3, ease: "easeOut" }}
      />
      <AnimatePresence>
        {active && (
          <motion.circle
            key="glow" r={34} fill={f.color} fillOpacity={0.18} stroke={f.color} strokeOpacity={0.7}
            initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: [1, 1.18, 1], opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.9, repeat: Infinity }}
          />
        )}
      </AnimatePresence>
      <motion.g
        animate={{ rotate: [-3, 3, -3] }}
        transition={{ delay: T, duration: 5 + (index % 3), repeat: Infinity, ease: "easeInOut" }}
      >
        {Array.from({ length: 8 }, (_, i) => (
          <g key={`o${i}`} transform={`rotate(${i * 45 + 22.5})`}>
            <motion.ellipse
              cx={0} rx={isGen ? 6 : 8} fill={f.color} fillOpacity={0.38}
              initial={{ cy: 0, ry: 0 }} animate={{ cy: -20, ry: 16 }}
              transition={{ delay: T * 0.4 + i * 0.04, duration: T * 0.5, ease: BACK }}
            />
          </g>
        ))}
        {Array.from({ length: 5 }, (_, i) => (
          <g key={`i${i}`} transform={`rotate(${i * 72})`}>
            <motion.ellipse
              cx={0} rx={7} fill={f.color} fillOpacity={0.9}
              initial={{ cy: 0, ry: 0 }} animate={{ cy: -13, ry: 11 }}
              transition={{ delay: T * 0.25 + i * 0.05, duration: T * 0.4, ease: BACK }}
            />
          </g>
        ))}
        <motion.circle
          r={14} fill="#0f1612" stroke={f.color} strokeWidth={2}
          initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: T * 0.2, duration: 0.4, ease: BACK }}
        />
        <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: T * 0.45 }}>
          <SvgGlyph Icon={agentIcon(f.slug, f.category)} size={15} color="#eef5ef" />
        </motion.g>
      </motion.g>
      <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: T * 0.7, duration: 0.5 }}>
        {(() => {
          // Labels sit on the side facing away from the hub so neighbours never cover them.
          const side = place === "left" || place === "right";
          const x = side ? (place === "left" ? -40 : 40) : 0;
          const y = place === "above" ? -56 : place === "below" ? 46 : -2;
          const anchor = place === "left" ? "end" : place === "right" ? "start" : "middle";
          return (
            <>
              <text x={x} y={y} textAnchor={anchor} fontSize={11.5} fontWeight={650} fill="var(--ink)">
                {f.site ? `${siteName(f.site)} records` : f.name}
              </text>
              <text x={x} y={y + 12} textAnchor={anchor} fontSize={9} fill={f.color}>{loc}</text>
            </>
          );
        })()}
      </motion.g>
    </g>
  );
}

function Hub({ pulse }) {
  return (
    <g transform={`translate(${CX},${CY}) scale(1.45)`}>
      <motion.circle
        r={46} fill="none" stroke="var(--hub)" strokeOpacity={0.45} strokeDasharray="3 7" strokeWidth={2}
        animate={{ rotate: 360 }} transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
      />
      <AnimatePresence>
        {pulse && (
          <motion.circle
            key={pulse} r={40} fill="none" stroke="var(--hub)" strokeWidth={3}
            initial={{ scale: 0.8, opacity: 1 }} animate={{ scale: 2.4, opacity: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 1.2 }}
          />
        )}
      </AnimatePresence>
      <circle r={34} fill="#1a1608" stroke="var(--hub)" strokeWidth={2.5} />
      {Array.from({ length: 12 }, (_, i) => (
        <ellipse key={i} cx={0} cy={-27} rx={4} ry={8} fill="var(--hub)" fillOpacity={0.55} transform={`rotate(${i * 30})`} />
      ))}
      <circle r={17} fill="#2a220b" />
      <SvgGlyph Icon={HubIcon} size={20} color="var(--hub)" />
      <text y={58} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--ink)">Coordinator</text>
      <text y={71} textAnchor="middle" fontSize={9.5} fill="var(--hub)">Flower SuperGrid</text>
    </g>
  );
}

// A proposal waiting for its owner is a closed bud; "no" makes it wilt.
function Bud({ x, y, mode }) {
  const wilted = mode === "rejected";
  const building = mode === "building";
  return (
    <g transform={`translate(${x},${y})`}>
      <motion.g
        initial={{ opacity: 0, scale: 0.3 }}
        animate={{ opacity: wilted ? 0.35 : 1, scale: 1, rotate: wilted ? 50 : 0 }}
        exit={{ opacity: 0, scale: 0.2 }}
        transition={{ duration: wilted ? 1.6 : 0.6, ease: BACK }}
      >
        {building ? (
          <motion.g animate={{ rotate: [-6, 6, -6] }} transition={{ duration: 1.2, repeat: Infinity }}>
            <path d="M0,16 C0,6 0,0 0,-4" stroke="var(--green)" strokeWidth={3} fill="none" />
            <path d="M0,4 C-10,-2 -14,-8 -12,-12 C-6,-10 -2,-4 0,4 Z" fill="var(--green)" />
            <path d="M0,0 C8,-6 14,-8 14,-14 C8,-14 2,-8 0,0 Z" fill="var(--green)" fillOpacity={0.8} />
          </motion.g>
        ) : (
          <motion.g
            animate={wilted ? {} : { scale: [1, 1.08, 1] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          >
            <path d="M0,22 C0,14 0,10 0,6" stroke="var(--vine)" strokeWidth={3} fill="none" />
            <path d="M0,-22 C12,-12 12,4 0,8 C-12,4 -12,-12 0,-22 Z" fill={wilted ? "#6b7280" : "var(--brian)"} fillOpacity={0.85} />
            <path d="M0,8 C-8,6 -12,0 -12,-6 C-6,-2 -2,2 0,8 Z" fill="var(--vine)" />
            <path d="M0,8 C8,6 12,0 12,-6 C6,-2 2,2 0,8 Z" fill="var(--vine)" />
          </motion.g>
        )}
        <text y={42} textAnchor="middle" fontSize={12} fontWeight={600} fill={wilted ? "var(--muted)" : "var(--ink)"}>
          {building ? "Growing a new agent…" : wilted ? "Not approved" : "Waiting for the owner's “y”"}
        </text>
      </motion.g>
    </g>
  );
}

// Messages: a vine grows out along the edge with the question; the answer rides back as a bud.
function Pulse({ p, from, to }) {
  const v = vine(from.x, from.y, to.x, to.y);
  const pts = Array.from({ length: 20 }, (_, i) => v.at(i / 19));
  if (p.out) {
    const tip = v.at(1);
    return (
      <g>
        <motion.path
          d={v.d} fill="none" stroke="#86efac" strokeWidth={4} strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: [0, 1, 1], opacity: [1, 1, 0] }}
          transition={{ duration: PULSE_MS / 1000, times: [0, 0.55, 1] }}
        />
        <motion.g initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 0] }} transition={{ duration: PULSE_MS / 1000, times: [0.45, 0.6, 1] }}>
          <Leaf p={tip} delay={0.9} color="#86efac" size={1.2} />
        </motion.g>
      </g>
    );
  }
  const back = [...pts].reverse();
  return (
    <motion.circle
      r={7} fill={p.color} stroke="#fff" strokeWidth={1.5}
      initial={{ cx: back[0].x, cy: back[0].y, opacity: 0 }}
      animate={{ cx: back.map((q) => q.x), cy: back.map((q) => q.y), opacity: [0, 1, 1, 1, 0] }}
      transition={{ duration: 1.3, ease: "easeInOut" }}
    />
  );
}

function labelPlace({ x, y }) {
  const dx = x - CX, dy = y - CY;
  // Beside the flower when it sits level with the hub, unless that would run off the edge.
  if (Math.abs(dx) * 0.55 > Math.abs(dy) && Math.abs(dx) < 340) return dx < 0 ? "left" : "right";
  return dy < 0 ? "above" : "below";
}

export default function Garden({ flowers, messages, now, lastEventId }) {
  const positions = useMemo(() => flowers.map((_, k) => slot(k, CX, CY)), [flowers.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const next = slot(flowers.length, CX, CY);
  const [pulses, setPulses] = useState([]);
  const [active, setActive] = useState({});
  const [hubPulse, setHubPulse] = useState(null);
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
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" style={{ display: "block" }}>
      {/* the golden-angle spiral: faint seeds show where future agents will grow */}
      {Array.from({ length: 14 }, (_, k) => {
        const s = slot(k, CX, CY);
        return <circle key={k} cx={s.x} cy={s.y} r={k < flowers.length ? 0 : 2.5} fill="#2c4a37" />;
      })}
      {flowers.map((f, k) => {
        const v = vine(CX, CY, positions[k].x, positions[k].y);
        return (
          <g key={`v-${f.key}`}>
            <motion.path
              d={v.d} fill="none" stroke="var(--vine)" strokeWidth={2.5} strokeLinecap="round"
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, ease: "easeOut" }}
            />
            <Leaf p={v.at(0.42)} delay={0.45} />
            <Leaf p={v.at(0.7)} delay={0.6} size={0.8} />
          </g>
        );
      })}
      {pulses.map((p) => positions[p.k] && <Pulse key={p.uid} p={p} from={{ x: CX, y: CY }} to={positions[p.k]} />)}
      <Hub pulse={hubPulse} />
      {flowers.map((f, k) => (
        <Flower key={f.key} f={f} x={positions[k].x} y={positions[k].y} index={k} active={!!active[f.key]} place={labelPlace(positions[k])} />
      ))}
      <AnimatePresence>
        {budMode && <Bud key={budMode} x={next.x} y={next.y} mode={budMode} />}
      </AnimatePresence>
    </svg>
  );
}
