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
    // Sites whose nodes joined this session win; otherwise fall back to where the last task ran.
    const joined = (state.sites || {})[m.slug];
    const sited = joined?.length ? joined : places.filter((p) => p.slug === m.slug && p.site);
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

// Agents often reply in terse key=value form ("old_admissions=565, ..."). Turn that into a sentence.
const num = (v) => Number(v).toLocaleString();
const rate = (x, n) => `${((100 * x) / n).toFixed(1)}%`;
export function humanize(answer) {
  const text = String(answer || "").trim();
  const kv = Object.fromEntries([...text.matchAll(/(\w+)\s*=\s*([^,;]+)/g)].map((m) => [m[1].toLowerCase(), m[2].trim()]));
  const n = (k) => Number(String(kv[k] ?? "").replace(/[^\d.eE+-]/g, ""));

  // One hospital's counts
  if (["old_admissions", "old_readmissions", "new_admissions", "new_readmissions"].every((k) => k in kv)) {
    const [oa, or, na, nr] = ["old_admissions", "old_readmissions", "new_admissions", "new_readmissions"].map(n);
    return `Old protocol: ${num(or)} of ${num(oa)} patients were readmitted within 30 days (${rate(or, oa)}). ` +
      `New protocol: ${num(nr)} of ${num(na)} (${rate(nr, na)}).`;
  }

  // Pooled statistics: old=1004 admissions/189 readmissions (18.82%), new=..., change=-6.16 pp, z=4.465, p=8.0e-06
  const pooled = text.match(/old\s*=\s*(\d+)\s*admissions\/(\d+)\s*readmissions\s*\(([\d.]+)%\).*?new\s*=\s*(\d+)\s*admissions\/(\d+)\s*readmissions\s*\(([\d.]+)%\)/i);
  if (pooled) {
    const [, oa, or, orate, na, nr, nrate] = pooled;
    const parts = [`Both hospitals together: ${num(or)} of ${num(oa)} patients readmitted under the old protocol (${orate}%), ` +
      `${num(nr)} of ${num(na)} under the new one (${nrate}%).`];
    const change = text.match(/change\s*=\s*([-+−]?[\d.]+)\s*pp/i);
    if (change) parts.push(`That is a change of ${change[1].replace("-", "−")} percentage points.`);
    const z = text.match(/\bz\s*=\s*([-\d.]+)/i), p = text.match(/\bp\s*=\s*([\d.eE+-]+)/i);
    if (z && p) {
      const pv = Number(p[1]);
      parts.push(`A two-proportion z-test gives z = ${z[1]}, p ${pv < 0.001 ? "< 0.001" : `= ${pv.toFixed(3)}`}` +
        (/not\s+significant/i.test(text) ? ", which is not statistically significant." : /significant/i.test(text) ? ", which is statistically significant." : "."));
    }
    return parts.join(" ");
  }

  // Generic key=value list -> "Key: value · Key: value"
  if (/^(\w+\s*=\s*[^,;]+[,;]\s*)+\w+\s*=\s*[^,;]+\.?$/.test(text)) {
    return Object.entries(kv).map(([k, v]) => `${k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}: ${v}`).join(" · ");
  }
  return text;
}
