// Shared helpers: names, owners, colors, and the phyllotaxis geometry.

export const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5)); // 137.508°

const PEOPLE = { brianhuang08: "Brian", brian: "Brian", vishesh: "Vishesh", vverm: "Vishesh" };

export const person = (owner) => (owner ? PEOPLE[owner] || owner[0].toUpperCase() + owner.slice(1) : null);
export const laptop = (owner) => (owner ? `${person(owner)}'s laptop` : null);
export const siteName = (site) =>
  site ? site.split("-").map((w) => (w.length === 1 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1))).join(" ") : null;

export function colorFor(f) {
  if (f.kind === "generalist") return "var(--plain)";
  const p = person(f.owner);
  if (p === "Brian") return "var(--brian)";
  if (p === "Vishesh") return "var(--vishesh)";
  return "var(--green)";
}

export function prettyName(slug) {
  if (!slug) return "";
  if (slug === "bloom") return "Coordinator";
  const [base, site] = slug.split("@");
  const words = base.split(/[-_]/).map((w) => (["sql", "ai"].includes(w) ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)));
  return words.join(" ") + (site ? ` · ${siteName(site)}` : "");
}

// Team members -> flowers. A specialist that runs at several sites becomes one flower per site.
export function buildFlowers(state) {
  const places = state.places || [];
  const agents = Object.fromEntries((state.agents || []).map((a) => [a.slug, a]));
  const out = [];
  for (const m of state.team || []) {
    const sited = places.filter((p) => p.slug === m.slug && p.site);
    if (sited.length) {
      for (const p of sited) out.push({ ...m, key: `${m.slug}@${p.site}`, site: p.site, owner: p.owner, node_id: p.node_id });
      continue;
    }
    const place = places.find((p) => p.slug === m.slug);
    let owner = place?.owner || null;
    let node_id = place?.node_id || null;
    if (!owner && m.on_node) {
      const name = agents[m.slug]?.node?.name || "";
      owner = name.includes("@") ? name.split("@")[1] : "vishesh";
      node_id = agents[m.slug]?.node?.node_id || null;
    }
    out.push({ ...m, key: m.slug, site: null, owner: m.kind === "generalist" ? null : owner, node_id });
  }
  return out.map((f) => ({ ...f, color: colorFor(f) }));
}

// Golden-angle (Vogel) spiral, stretched sideways to use a wide screen.
export function slot(k, cx, cy, c = 96, sx = 1.55, sy = 0.9) {
  const r = c * Math.sqrt(k + 2.4); // start one ring out so the first agent clears the hub
  const a = k * GOLDEN_ANGLE - Math.PI / 2;
  return { x: cx + sx * r * Math.cos(a), y: cy + sy * r * Math.sin(a) };
}

// A gently curved "vine" from the hub to a flower, plus points along it for travelling buds.
export function vine(x0, y0, x1, y1) {
  const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy) || 1;
  const qx = (x0 + x1) / 2 - (dy / len) * len * 0.2;
  const qy = (y0 + y1) / 2 + (dx / len) * len * 0.2;
  const at = (t) => {
    const u = 1 - t;
    return {
      x: u * u * x0 + 2 * u * t * qx + t * t * x1,
      y: u * u * y0 + 2 * u * t * qy + t * t * y1,
      angle: (Math.atan2(2 * u * (qy - y0) + 2 * t * (y1 - qy), 2 * u * (qx - x0) + 2 * t * (x1 - qx)) * 180) / Math.PI,
    };
  };
  return { d: `M${x0},${y0} Q${qx},${qy} ${x1},${y1}`, at };
}

export const secs = (ms) => (ms == null ? "" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`);
export const pct = (x) => `${Math.round(100 * x)}%`;
