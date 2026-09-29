/* Evaluation report: renders runs/eval/latest.json (via /api/state .eval). */
(function () {
  const ARM = {
    generalist: { label: "AI alone", color: "#94a3b8" },
    generalist_tools: { label: "AI + every tool", color: "#a78bfa" },
    generalist_tools_check: { label: "AI + every tool + self-check", color: "#fbbf24" },
    specialist: { label: "Bloom specialist", color: "#7cf3c1" },
  };
  const SKILL = { sql: "Patient records (SQL)", stats: "Statistics", dates: "Dates", units: "Unit conversion", extraction: "Text extraction", writing: "Writing" };
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = x => (x == null ? "–" : Math.round(100 * x) + "%");
  const pts = x => (x == null ? "–" : (x >= 0 ? "+" : "") + Math.round(100 * x));
  const cls = x => (x == null ? "flat" : x > 0.005 ? "pos" : x < -0.005 ? "neg" : "flat");
  let lastKey = "";

  function forest(ev) {
    const rows = ev.covered.map(c => ({ name: SKILL[c] || c, p: ev.categories[c].paired.vs_generalist_tools }));
    rows.push({ name: "All skills", p: ev.paired.vs_generalist_tools, overall: true });
    const W = 640, rowH = 40, top = 30, left = 170, right = 70, H = top + rows.length * rowH + 30;
    const lo = -0.6, hi = 0.6, x = v => left + ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (W - left - right);
    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%">`;
    for (const t of [-0.5, -0.25, 0, 0.25, 0.5]) {
      g += `<line x1="${x(t)}" x2="${x(t)}" y1="${top - 8}" y2="${H - 24}" stroke="${t === 0 ? "#3b4b5c" : "#18222d"}" stroke-width="${t === 0 ? 2 : 1}" ${t === 0 ? "" : 'stroke-dasharray="3 4"'}/>`;
      g += `<text x="${x(t)}" y="${H - 8}" fill="#6b7a89" font-size="11" text-anchor="middle">${t > 0 ? "+" : ""}${Math.round(t * 100)} pts</text>`;
    }
    g += `<text x="${x(0.3)}" y="16" fill="#7cf3c1" font-size="11" text-anchor="middle">specialist better →</text>`;
    g += `<text x="${x(-0.3)}" y="16" fill="#ff8f8f" font-size="11" text-anchor="middle">← AI + tools better</text>`;
    rows.forEach((r, i) => {
      const y = top + i * rowH + rowH / 2, p = r.p || {};
      if (r.overall) g += `<line x1="10" x2="${W - 10}" y1="${y - rowH / 2}" y2="${y - rowH / 2}" stroke="#1f2a36"/>`;
      g += `<text x="10" y="${y + 4}" fill="${r.overall ? "#e7edf3" : "#b8c6d4"}" font-size="${r.overall ? 14 : 13}" font-weight="${r.overall ? 800 : 500}">${esc(r.name)}</text>`;
      if (p.delta == null) return;
      const ci = p.delta_ci || [p.delta, p.delta], col = p.delta > 0.005 ? "#7cf3c1" : p.delta < -0.005 ? "#ff8f8f" : "#cbd5e1";
      g += `<line x1="${x(ci[0])}" x2="${x(ci[1])}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="3" stroke-linecap="round" opacity=".7"/>`;
      g += r.overall ? `<rect x="${x(p.delta) - 8}" y="${y - 8}" width="16" height="16" transform="rotate(45 ${x(p.delta)} ${y})" fill="${col}"/>`
                     : `<circle cx="${x(p.delta)}" cy="${y}" r="7" fill="${col}" stroke="#090c11" stroke-width="2"/>`;
      g += `<text x="${W - 8}" y="${y + 4}" fill="${col}" font-size="13" font-weight="700" text-anchor="end" class="num">${pts(p.delta)}</text>`;
    });
    return g + "</svg>";
  }

  function difficultyBars(ev) {
    const arms = (ev.arms || Object.keys(ARM)).filter(a => ARM[a]);
    const diffs = Object.keys(ev.difficulty || {});
    if (!diffs.length) return `<div class="cap">No difficulty breakdown in this run.</div>`;
    const W = 460, H = 250, left = 40, bottom = 34, top = 14, gw = (W - left - 10) / diffs.length, bw = Math.min(34, (gw - 30) / arms.length);
    const y = v => top + (1 - v) * (H - top - bottom);
    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%">`;
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      g += `<line x1="${left}" x2="${W - 6}" y1="${y(t)}" y2="${y(t)}" stroke="#18222d"/>`;
      g += `<text x="${left - 6}" y="${y(t) + 4}" fill="#6b7a89" font-size="10" text-anchor="end">${t * 100}%</text>`;
    }
    diffs.forEach((d, gi) => {
      const x0 = left + gi * gw + (gw - bw * arms.length - 6 * (arms.length - 1)) / 2;
      arms.forEach((a, ai) => {
        const r = ev.difficulty[d][a];
        if (!r || !r.n) return;
        const xx = x0 + ai * (bw + 6), yy = y(r.acc);
        g += `<rect x="${xx}" y="${yy}" width="${bw}" height="${H - bottom - yy}" rx="3" fill="${ARM[a].color}" opacity=".9"><title>${ARM[a].label}: ${pct(r.acc)} (n=${r.n})</title></rect>`;
        g += `<line x1="${xx + bw / 2}" x2="${xx + bw / 2}" y1="${y(r.ci[1])}" y2="${y(r.ci[0])}" stroke="#e7edf3" stroke-width="1.5" opacity=".55"/>`;
        g += `<text x="${xx + bw / 2}" y="${yy - 5}" fill="#cbd5e1" font-size="10" text-anchor="middle" class="num">${Math.round(100 * r.acc)}</text>`;
      });
      g += `<text x="${left + gi * gw + gw / 2}" y="${H - 12}" fill="#b8c6d4" font-size="13" font-weight="700" text-anchor="middle">${d === "hard" ? "Hard (multi-step)" : "Standard"}</text>`;
    });
    return g + "</svg>";
  }

  function costScatter(ev) {
    const pts_ = Object.entries(ev.cost || {}).filter(([a, c]) => c && c.tokens && ev.overall[a] && ev.overall[a].n);
    if (!pts_.length) return `<div class="cap">No token/latency data in this run.</div>`;
    const W = 460, H = 250, left = 44, bottom = 36, top = 16, right = 16;
    const maxT = Math.max(...pts_.map(([, c]) => c.tokens)) * 1.15;
    const x = v => left + (v / maxT) * (W - left - right), y = v => top + (1 - v) * (H - top - bottom);
    let g = `<svg viewBox="0 0 ${W} ${H}" width="100%">`;
    for (const t of [0, 0.5, 1]) g += `<line x1="${left}" x2="${W - right}" y1="${y(t)}" y2="${y(t)}" stroke="#18222d"/><text x="${left - 6}" y="${y(t) + 4}" fill="#6b7a89" font-size="10" text-anchor="end">${t * 100}%</text>`;
    g += `<text x="${(W + left) / 2}" y="${H - 6}" fill="#6b7a89" font-size="11" text-anchor="middle">tokens per answer →</text>`;
    for (const [a, c] of pts_) {
      const acc = ev.overall[a].acc, cx = x(c.tokens), cy = y(acc);
      g += `<circle cx="${cx}" cy="${cy}" r="${7 + Math.min(10, c.seconds)}" fill="${ARM[a]?.color || "#fff"}" opacity=".85" stroke="#090c11" stroke-width="2"><title>${ARM[a]?.label}: ${pct(acc)}, ${Math.round(c.tokens)} tokens, ${c.seconds.toFixed(1)}s, ${c.tool_calls.toFixed(1)} tool calls</title></circle>`;
      const flip = cx > W * 0.55;
      g += `<text x="${flip ? cx - 16 : cx + 16}" y="${cy + 4}" fill="#cbd5e1" font-size="11" text-anchor="${flip ? "end" : "start"}">${ARM[a]?.label || a} · ${Math.round(c.tokens)} tok · ${c.seconds.toFixed(1)}s</text>`;
    }
    return g + "</svg>";
  }

  window.renderProof = function (ev) {
    const el = document.getElementById("report-body");
    if (!el) return;
    if (!ev || !ev.overall) { el.innerHTML = `<div class="empty">No evaluation yet. Run <span class="num">python -m forge eval</span>.</div>`; return; }
    const key = ev.created_at + ev.n_runs;
    if (key === lastKey) return;
    lastKey = key;
    const o = ev.overall, pt = ev.paired.vs_generalist_tools || {}, pc = (ev.paired.vs_generalist_tools_check || null);
    const cs = ev.cost || {}, costRatio = cs.specialist && cs.generalist_tools && cs.generalist_tools.tokens ? cs.specialist.tokens / cs.generalist_tools.tokens : null;
    const arms = (ev.arms || Object.keys(ARM)).filter(a => ARM[a]);
    const ci = pt.delta_ci ? `95% CI ${pts(pt.delta_ci[0])} to ${pts(pt.delta_ci[1])} pts` : "";
    const verdict = pt.delta_ci ? (pt.delta_ci[0] > 0 ? "Specialists are better, and the whole confidence interval is above zero."
      : pt.delta_ci[1] < 0 ? "The AI with every tool is better here."
      : "The difference is not distinguishable from zero at this sample size.") : "";
    el.innerHTML = `
      <div class="eyebrow">Evaluation report · held-out test set</div>
      <h1>Do Bloom's specialists beat the same AI given every tool?</h1>
      <div class="meta">
        ${ev.simulated ? '<span class="chip stamp">SIMULATED · mock backend</span>'
          : `<span class="chip">${ev.backend === "nebius" ? "measured directly on Nebius Token Factory (same agent code, not via SuperGrid)"
             : ev.backend === "supergrid" ? "measured on Flower SuperGrid" : "backend: " + esc(ev.backend)}</span>`}
        ${ev.infra_errors ? `<span class="chip">${ev.infra_errors} answers excluded (infrastructure errors)</span>` : ""}
        <span class="chip">model (all arms): ${esc(ev.model)}</span>
        <span class="chip">${ev.n_tasks} unseen questions × ${ev.repeats} repeat${ev.repeats > 1 ? "s" : ""}</span>
        <span class="chip">${ev.n_runs} graded answers</span>
        ${ev.seconds ? `<span class="chip">${ev.seconds >= 90 ? Math.round(ev.seconds / 60) + " min" : Math.round(ev.seconds) + " s"} on ${esc(ev.backend)}</span>` : ""}
        <span class="chip">${esc((ev.created_at || "").replace("T", " "))}</span>
      </div>
      <div class="grid cards">
        <div class="rcard"><div class="k">Specialist accuracy</div><div class="v num pos">${pct(o.specialist?.acc)}</div>
          <div class="s">range ${pct(o.specialist?.ci?.[0])}–${pct(o.specialist?.ci?.[1])} · AI + tools ${pct(o.generalist_tools?.acc)} · AI alone ${pct(o.generalist?.acc)}</div></div>
        <div class="rcard"><div class="k">Gain vs AI + every tool</div><div class="v num ${cls(pt.delta)}">${pts(pt.delta)}<span style="font-size:22px"> pts</span></div>
          <div class="s">${ci}<br>${esc(verdict)}</div></div>
        <div class="rcard"><div class="k">Head to head, same question</div><div class="v num"><span class="pos">${pt.wins ?? "–"}</span><span style="color:#3b4b5c"> / </span><span class="neg">${pt.losses ?? "–"}</span></div>
          <div class="s">wins / losses, ${pt.ties ?? 0} ties · exact sign test p = <span class="num">${pt.p != null ? pt.p.toPrecision(2) : "–"}</span>${pc && pc.pairs ? `<br>vs AI + tools + self-check: ${pts(pc.delta)} pts` : ""}</div></div>
        <div class="rcard"><div class="k">Cost per answer</div><div class="v num">${costRatio ? costRatio.toFixed(2) + "×" : "–"}</div>
          <div class="s">${costRatio ? `specialist tokens vs AI + every tool<br>${Math.round(cs.specialist.tokens)} vs ${Math.round(cs.generalist_tools.tokens)} tokens · ${cs.specialist.seconds.toFixed(1)}s vs ${cs.generalist_tools.seconds.toFixed(1)}s` : "no usage data"}${cs.specialist?.self_check_changed != null ? `<br>self-check changed ${pct(cs.specialist.self_check_changed)} of checked answers` : ""}</div></div>
      </div>
      <div class="grid two">
        <div class="panel2"><h3>Where the gain comes from</h3><div class="cap">Specialist minus AI + every tool, per skill. Bars show the 95% bootstrap interval (resampling questions).</div>${forest(ev)}</div>
        <div class="panel2"><h3>Standard vs hard questions</h3><div class="cap">Accuracy by difficulty; thin lines are 95% Wilson intervals.</div>
          <div class="legend">${arms.map(a => `<span><i style="background:${ARM[a].color}"></i>${ARM[a].label}</span>`).join("")}</div>${difficultyBars(ev)}</div>
      </div>
      <div class="grid two">
        <div class="panel2"><h3>Accuracy by skill</h3>
          <table><tr><th>Skill</th>${arms.map(a => `<th style="color:${ARM[a].color}">${ARM[a].label}</th>`).join("")}<th>Gain</th></tr>
          ${Object.entries(ev.categories).map(([c, r]) => `<tr><td>${esc(SKILL[c] || c)}</td>${arms.map(a => `<td class="num">${r[a] && r[a].n ? pct(r[a].acc) : "–"}</td>`).join("")}
            <td class="num ${cls(r.paired?.vs_generalist_tools?.delta)}">${r.paired ? pts(r.paired.vs_generalist_tools.delta) : "–"}</td></tr>`).join("")}</table></div>
        <div class="panel2"><h3>Accuracy vs cost</h3><div class="cap">Bubble size = seconds per answer.</div>${costScatter(ev)}</div>
      </div>
      <div class="panel2 method"><h3>Method</h3><ul>
        <li><b>Held out.</b> Test questions are never shown to the Forge: gap detection, worked examples and the Reviewer's checks use a separate dev split.</li>
        <li><b>Same model.</b> Every arm calls ${esc(ev.model)}. Only instructions, tools, worked examples and the self-check differ.</li>
        <li><b>Fair baseline.</b> "AI + every tool" gets all ${"15"} Bloom tools, a superset of every specialist's tools${pc ? "; the self-check ablation isolates checking from specialization" : ""}.</li>
        <li><b>Paired statistics.</b> Arms answer the identical questions; the sign test counts discordant pairs, and the bootstrap resamples questions (repeats averaged per question).</li>
        <li><b>Answers computed, not typed.</b> Every expected answer is produced by code from a seeded dataset; each benchmark task also stores its worked method.</li>
      </ul></div>`;
  };
})();
