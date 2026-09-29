/* Agent internals: a waterfall of the latest multi-agent run, from real trace spans.
   Timeline = Endeavor planning run + orchestration run. Each step bar spans the Grid round
   trip (push -> node -> reply); inner spans are the specialist's own model and tool calls. */
(function () {
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const name = s => String(s || "").split("-").map(w => w === "sql" ? "SQL" : (w[0] || "").toUpperCase() + w.slice(1)).join(" ");
  const fmt = ms => (ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms");
  const short = id => id ? String(id).slice(0, 8) + "…" + String(id).slice(-4) : "–";
  let lastKey = "", spanIndex = [];

  function counters(tr) {
    let model = 0, tool = 0, tin = 0, tout = 0, grid = 0;
    for (const s of tr.steps) {
      const u = s.usage || {};
      model += u.model_calls || 0; tool += u.tool_calls || 0; tin += u.tokens_in || 0; tout += u.tokens_out || 0;
      if (s.tier === "nodes" || s.tier === "payload") grid += 2;
    }
    const wall = (tr.plan_ms || 0) + Math.max(0, ...tr.steps.map(s => s.end_ms || 0));
    return [["Agents", new Set(tr.steps.map(s => s.specialist)).size + (tr.plan_ms ? 1 : 0)], ["Grid messages", grid],
            ["Model calls", model + (tr.plan_ms ? 1 : 0)], ["Tool calls", tool],
            ["Tokens in / out", `${(tin / 1000).toFixed(1)}k / ${(tout / 1000).toFixed(1)}k`], ["Plan + execute", fmt(wall)]];
  }

  function build(tr) {
    const plan = tr.plan_ms || 0;
    // Axis = actual orchestration time (tr.total_ms is local wall time incl. SuperGrid queueing).
    const exec = Math.max(1, ...tr.steps.map(s => s.end_ms || 0)) * 1.03;
    // Planning happens in its own run and can dwarf execution; draw it compressed (≈ break) so the
    // multi-agent execution gets the width. Labels and the stream keep real times.
    const planW = plan ? 12 : 0, gap = plan ? 2 : 0;
    const pct = ms => (ms <= plan ? (planW * ms) / Math.max(plan, 1) : planW + gap + ((100 - planW - gap) * (ms - plan)) / exec);
    const total = plan + exec;
    spanIndex = [];
    let lanes = "", stream = [];
    if (plan) {
      lanes += `<div class="lane"><div class="who"><b>Endeavor planner</b><span class="t">flwrlabs/endeavor-1.0 · ${fmt(plan)}</span><br><span class="tier">own SuperGrid run</span></div>
        <div class="track"><div class="wstep" style="left:0%;width:${planW}%"><div class="span model" data-i="${spanIndex.length}" style="left:4%;width:92%"></div></div>
        <div class="brk" style="left:${planW}%">≈</div></div></div>`;
      spanIndex.push({ who: "Endeavor planner", kind: "model", name: "flwrlabs/endeavor-1.0", phase: "plan", start: 0, end: plan,
                       detail: `Planned ${tr.steps.length} steps: ${tr.steps.map(s => s.specialist).join(" → ")}` });
      stream.push({ t: 0, html: `<span class="ag">planner</span> <span class="md">endeavor-1.0</span> plan → ${tr.steps.map(s => esc(s.specialist)).join(" → ")} <span class="ts">(${fmt(plan)})</span>` });
    }
    for (const s of tr.steps) {
      const a = plan + (s.start_ms || 0), b = plan + (s.end_ms || s.start_ms || 0), len = Math.max(1, b - a);
      const spans = s.trace || [], tlen = Math.max(1, ...spans.map(x => x.end || 0), (s.usage || {}).ms || 0);
      const remote = s.tier === "nodes" || s.tier === "payload";
      const scale = Math.min(1, (len * (remote ? 0.9 : 1)) / tlen), off = remote ? (len - tlen * scale) / 2 : 0;
      let inner = "";
      for (const sp of spans) {
        const L = (100 * (off + sp.start * scale)) / len, W = Math.max(0.4, (100 * (sp.end - sp.start) * scale) / len);
        const kind = sp.kind === "tool" ? "tool" : String(sp.phase || "").startsWith("self-check") ? "model check" : "model";
        inner += `<div class="span ${kind}" data-i="${spanIndex.length}" style="left:${L}%;width:${W}%"></div>`;
        spanIndex.push({ who: name(s.specialist), ...sp });
        const t = a + off + sp.start * scale;
        stream.push({ t, html: sp.kind === "tool"
          ? `<span class="ag">${esc(s.specialist)}</span> <span class="tl">tool ${esc(sp.name)}</span>(${esc(sp.args)}) → ${esc(sp.result)} <span class="ts">${fmt(sp.end - sp.start)}</span>`
          : `<span class="ag">${esc(s.specialist)}</span> <span class="${String(sp.phase).startsWith("self-check") ? "ck" : "md"}">${esc(sp.phase)} · ${esc(String(sp.name).split("/").pop())}</span> in=${sp.tokens_in} out=${sp.tokens_out}${sp.requested_tools && sp.requested_tools.length ? " → calls " + esc(sp.requested_tools.join(", ")) : ""} <span class="ts">${fmt(sp.end - sp.start)}</span>` });
      }
      const hops = remote ? `<div class="hop" style="left:0" data-label="push ${short(s.message_id)}"></div><div class="hop" style="right:0;left:auto" data-label=""></div>` : "";
      lanes += `<div class="lane"><div class="who"><b>${esc(name(s.specialist))}</b><span class="t">${s.node_id ? "node " + short(s.node_id) : "coordinator process"} · ${esc(String(s.model || "").split("/").pop() || "–")}</span><br>
        <span class="tier ${esc(s.tier)}">${esc(s.tier === "nodes" ? "Grid → dedicated SuperNode" : s.tier === "payload" ? "Grid → any SuperNode" : s.tier)}</span>${s.checked ? ` <span class="tier">${s.changed ? "self-check fixed" : "self-checked"}</span>` : ""}</div>
        <div class="track"><div class="wstep" style="left:${pct(a)}%;width:${Math.max(0.6, pct(b) - pct(a))}%">${hops}${inner}</div></div></div>`;
      if (remote) {
        stream.push({ t: a, html: `<span class="gd">grid push_messages → node ${esc(short(s.node_id))} msg ${esc(short(s.message_id))}</span> <span class="ts">${esc(s.specialist)}</span>` });
        stream.push({ t: b, html: `<span class="gd">grid pull_messages ← reply for ${esc(short(s.message_id))}</span> answer: ${esc(String(s.answer || "").slice(0, 90))}` });
      }
      if (s.fallback) stream.push({ t: a, html: `<span class="er">fallback → in-process: ${esc(s.fallback)}</span>` });
    }
    stream.sort((x, y) => x.t - y.t);
    const ticks = (plan ? [`<div class="tick" style="left:${planW / 2}%">plan ${fmt(plan)}</div>`] : []).concat(
      (plan ? [0.25, 0.5, 0.75, 1] : [0, 0.25, 0.5, 0.75, 1]).map(f => `<div class="tick" style="left:${pct(plan + f * exec)}%">+${fmt(f * exec)}</div>`)).join("");
    return {
      waterfall: `<div class="axis">${ticks}</div>${lanes}<div class="playhead" id="playhead"></div>
        <div class="legend"><span><i style="background:#14b8a6"></i>model call</span><span><i style="background:#8b5cf6"></i>tool call</span>
        <span><i style="background:#f59e0b"></i>self-check</span><span><i style="background:rgba(124,243,193,.2)"></i>Grid round trip</span></div>`,
      stream: stream.map(e => `<div class="ln"><span class="ts">[+${(e.t / 1000).toFixed(2).padStart(6)}s]</span> ${e.html}</div>`).join(""),
    };
  }

  window.renderTrace = function (traces) {
    const el = document.getElementById("internals-body");
    if (!el) return;
    const tr = (traces || []).slice(-1)[0];
    if (!tr || !tr.steps || !tr.steps.length) {
      el.innerHTML = `<div class="empty">No multi-agent run traced yet. Run the final task: <b>python -m forge final</b>.</div>`;
      lastKey = "";
      return;
    }
    if (tr.id === lastKey) return;
    lastKey = tr.id;
    const view = build(tr);
    el.innerHTML = `
      <div class="hd"><h1>Agent internals</h1>
        <span class="sub">job ${esc(tr.job_id)} · run ${esc(tr.run_id || "–")} · federation ${esc(tr.federation || "–")}</span>
        ${tr.simulated ? '<span class="sim">SIMULATED</span>' : ""}</div>
      <div class="counters">${counters(tr).map(([k, v]) => `<div class="ctr"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
      <div class="body">
        <div class="box"><h3>Execution waterfall · click a span</h3><div id="wf">${view.waterfall}</div><div id="detail">Click any span for its inputs and outputs.</div></div>
        <div class="box"><h3>Event stream</h3><div id="stream">${view.stream}</div></div>
      </div>`;
    el.querySelectorAll("#wf .span").forEach(node => node.addEventListener("click", () => {
      const sp = spanIndex[+node.dataset.i];
      document.getElementById("detail").textContent = sp.kind === "tool"
        ? `${sp.who} · tool ${sp.name} · ${fmt(sp.end - sp.start)}\nargs:   ${sp.args}\nresult: ${sp.result}`
        : `${sp.who} · ${sp.phase} · ${sp.name} · ${fmt(sp.end - sp.start)}\ntokens in ${sp.tokens_in ?? "–"} · out ${sp.tokens_out ?? "–"}` +
          (sp.requested_tools && sp.requested_tools.length ? `\nrequested tools: ${sp.requested_tools.join(", ")}` : "") + (sp.detail ? `\n${sp.detail}` : "");
    }));
    const ph = document.getElementById("playhead"), wf = document.getElementById("wf");
    if (ph && wf) {
      const w = wf.querySelector(".axis").getBoundingClientRect().width;
      ph.animate([{ transform: "translateX(0)" }, { transform: `translateX(${w}px)` }], { duration: 4200, easing: "linear", fill: "forwards" });
    }
  };
})();
