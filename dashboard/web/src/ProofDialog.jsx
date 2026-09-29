import React from "react";
import { Box, Flex, Grid, Text } from "@chakra-ui/react";
import { Accordion, AccordionDetails, AccordionSummary, Dialog, DialogContent, IconButton, Tooltip } from "@mui/material";
import { motion } from "framer-motion";
import { pct } from "./lib.js";
import { CATEGORY_ICON, SvgGlyph } from "./icons.jsx";

const CATS = { dates: "Dates", sql: "Database", stats: "Statistics", units: "Units" };
const ARMS = [
  ["generalist", "AI alone", "no tools, no data", "var(--plain)"],
  ["specialist", "Bloom specialist", "built by the Forge", "var(--accent)"],
  ["generalist_tools", "AI + every tool + all the data", "the ceiling: nothing held back", "var(--tools)"],
];
const BACK = [0.34, 1.56, 0.64, 1];

// Accuracies cluster near the top, so petal length uses acc^4: 83% draws at about half length, 97% near full.
const stretch = (x) => Math.pow(Math.max(0, x), 4);
const petal = (L, w) => `M0,0 C${w},${-L * 0.3} ${w},${-L * 0.82} 0,${-L} C${-w},${-L * 0.82} ${-w},${-L * 0.3} 0,0 Z`;

// One petal per question type: petal length = accuracy, translucent halo = the 95% Wilson interval.
function EvalFlower({ ev, arm, color, delay }) {
  const cats = (ev.covered || Object.keys(ev.categories)).filter((c) => ev.categories[c]?.[arm]);
  const R = 105;
  return (
    <svg viewBox="-200 -172 400 344" width="100%" style={{ maxHeight: 300 }}>
      {[0.5, 0.75, 0.9, 1].map((f) => (
        <circle key={f} r={18 + R * stretch(f)} fill="none" stroke="var(--line)" strokeDasharray={f === 1 ? "0" : "2 5"} />
      ))}
      {cats.map((c, i) => {
        const s = ev.categories[c][arm];
        const ang = (360 / cats.length) * i;
        const L = (x) => 18 + R * stretch(x);
        const tip = ((ang - 90) * Math.PI) / 180;
        const lx = Math.cos(tip) * (R + 40), ly = Math.sin(tip) * (R + 40);
        return (
          <g key={c}>
            <g transform={`rotate(${ang})`}>
              <motion.path
                d={petal(L(s.ci[1]), 30)} fill={color} fillOpacity={0.16} stroke={color} strokeOpacity={0.3} strokeDasharray="3 3"
                style={{ originX: 0.5, originY: 1 }}
                initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: delay + 0.5 + i * 0.1, duration: 0.8 }}
              />
              <motion.path
                d={petal(Math.max(L(s.acc), 20), 22)} fill={color} fillOpacity={0.85}
                style={{ originX: 0.5, originY: 1 }}
                initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: delay + i * 0.12, duration: 0.9, ease: BACK }}
              />
            </g>
            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: delay + 0.8 }}>
              {/* icon sits inline, left of the name, so it never leaves the frame or touches a petal */}
              {CATEGORY_ICON[c] && (
                <SvgGlyph Icon={CATEGORY_ICON[c]} x={lx - (String(CATS[c] || c).length * 6.6) / 2 - 11} y={ly - 10} size={14} color="var(--ink-2)" />
              )}
              <text x={lx} y={ly - 6} textAnchor="middle" fontSize={13} fill="var(--ink-2)">{CATS[c] || c}</text>
              <text x={lx} y={ly + 11} textAnchor="middle" fontSize={15} fontWeight={800} fill="var(--ink)">{pct(s.acc)}</text>
            </motion.g>
          </g>
        );
      })}
      <circle r={16} fill="var(--panel)" stroke={color} strokeWidth={2} />
    </svg>
  );
}

function Details({ ev }) {
  const cats = ev.covered || Object.keys(ev.categories);
  const vsTools = ev.paired?.vs_generalist_tools;
  const vsGen = ev.paired?.vs_generalist;
  const cell = { px: 3, py: 2, borderBottom: "1px solid var(--line)", fontSize: "14px" };
  return (
    <Box>
      <Grid templateColumns="1.4fr repeat(3, 1fr)" mb={4}>
        <Box {...cell} color="var(--muted)">Question type</Box>
        {ARMS.map(([a, name]) => <Box key={a} {...cell} color="var(--muted)">{name}</Box>)}
        {cats.map((c) => (
          <React.Fragment key={c}>
            <Box {...cell}>{CATS[c] || c}</Box>
            {ARMS.map(([a]) => {
              const s = ev.categories[c][a];
              return <Box key={a} {...cell}>{s ? `${s.correct}/${s.n}` : "—"} <Text as="span" color="var(--muted)" fontSize="12px">{s ? `(95% ${pct(s.ci[0])}–${pct(s.ci[1])})` : ""}</Text></Box>;
            })}
          </React.Fragment>
        ))}
      </Grid>
      <Text fontSize="14px" color="var(--ink-2)" lineHeight={1.7}>
        Specialist vs AI alone: {vsGen?.wins} wins, {vsGen?.losses} losses on the same questions (sign test p = {vsGen?.p?.toExponential(1)}).<br />
        Specialist vs AI + tools: {vsTools?.wins} wins, {vsTools?.losses} losses (p = {vsTools?.p?.toFixed(2)}), no real difference.<br />
        Cost per answer: specialist ≈ {Math.round(ev.cost?.specialist?.tokens || 0).toLocaleString()} tokens vs{" "}
        {Math.round(ev.cost?.generalist_tools?.tokens || 0).toLocaleString()} for AI + tools.
        {ev.cost?.specialist?.self_check_rate ? ` Its self-check changed ${pct(ev.cost.specialist.self_check_changed || 0)} of answers.` : ""}<br />
        {ev.n_runs} graded answers · {ev.n_tasks} unseen questions × {ev.repeats} repeats · model {String(ev.model || "").split("/").pop()} on {ev.backend}
        {ev.infra_errors ? ` · ${ev.infra_errors} infrastructure errors excluded` : ""}.
        Database questions were measured on an earlier practice database, not the hospital data.
      </Text>
    </Box>
  );
}

export default function ProofDialog({ open, onClose, ev, beforeAfter }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth PaperProps={{ sx: { bgcolor: "var(--panel)", backgroundImage: "none", border: "1px solid var(--line)" } }}>
      <DialogContent sx={{ p: 5 }}>
        <Flex justify="space-between" align="start">
          <Box>
            <Text fontSize="13px" letterSpacing=".12em" color="var(--muted)" fontWeight={700}>PROOF · UNSEEN TEST QUESTIONS</Text>
            <Text fontSize="30px" fontWeight={800} mt={1}>Does adding an agent actually help?</Text>
          </Box>
          <IconButton onClick={onClose} sx={{ color: "var(--muted)" }}>✕</IconButton>
        </Flex>
        {!ev ? (
          <Text mt={8} fontSize="18px" color="var(--muted)">No evaluation has been run yet.</Text>
        ) : (
          <>
            <Grid templateColumns="repeat(3, 1fr)" gap={4} mt={4}>
              {ARMS.map(([arm, name, what, color], i) => {
                const o = ev.overall?.[arm];
                return (
                  <motion.div key={arm} initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.25 }}>
                    <Box textAlign="center" p={3} borderRadius="18px" bg={arm === "specialist" ? "var(--accent-soft)" : "transparent"}>
                      <EvalFlower ev={ev} arm={arm} color={color} delay={0.3 + i * 0.35} />
                      <Text fontSize="20px" fontWeight={800} color={color} minH="30px" lineHeight={1.2}>{name}</Text>
                      <Text fontSize="13px" color="var(--muted)">{what}</Text>
                      {o && (
                        <Tooltip title={`${o.correct} of ${o.n} right. 95% Wilson interval ${pct(o.ci[0])}–${pct(o.ci[1])}`}>
                          <Text fontSize="44px" fontWeight={900} lineHeight={1.1} mt={2}>{pct(o.acc)}</Text>
                        </Tooltip>
                      )}
                      {o && <Text fontSize="12px" color="var(--muted)">likely between {pct(o.ci[0])} and {pct(o.ci[1])}</Text>}
                    </Box>
                  </motion.div>
                );
              })}
            </Grid>
            <Text textAlign="center" fontSize="13px" color="var(--muted)" mt={1}>
              Each petal is a question type. Longer petal = right more often (scaled so small gaps are easy to see; rings mark 50%, 75%, 90%, 100%). The faint halo = the 95% error bar.
            </Text>
            <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.6 }}>
              <Box mt={6} p={5} borderRadius="16px" border="1px solid var(--green)" bg="var(--green-soft)">
                <Text fontSize="22px" fontWeight={800}>The win comes from access, not a smarter brain.</Text>
                <Text fontSize="16px" color="var(--ink-2)" mt={2} lineHeight={1.6}>
                  On its own, the AI got {pct(ev.overall?.generalist?.acc || 0)} right. With every tool and all the data, or as a Bloom specialist, it got
                  {" "}{(() => { const [lo, hi] = [ev.overall?.generalist_tools?.acc || 0, ev.overall?.specialist?.acc || 0].sort((a, b) => a - b);
                    return lo === hi ? pct(lo) : `${pct(lo)}–${pct(hi)}`; })()}.
                  A specialist is no smarter than the same AI with the same tools. So Bloom's job is to bring the right
                  tool and the right data to each question, with the data owner's approval.
                </Text>
              </Box>
            </motion.div>
            <Accordion sx={{ mt: 3, bgcolor: "transparent", boxShadow: "none", border: "1px solid var(--line)", "&:before": { display: "none" } }}>
              <AccordionSummary expandIcon={<span>▾</span>}>
                <Text fontWeight={700}>Show the numbers</Text>
              </AccordionSummary>
              <AccordionDetails><Details ev={ev} /></AccordionDetails>
            </Accordion>
          </>
        )}
        {beforeAfter?.length > 0 && (
          <section className="practice-results" aria-label="Practice results">
            <h3>Practice results</h3>
            <p>Accuracy before and after adding specialists.</p>
            {beforeAfter.map(row => (
              <div className="practice-row" key={row.category}>
                <span>{row.skill}</span>
                <span>{row.before == null ? "—" : `${row.before}%`} → <strong>{row.after == null ? "—" : `${row.after}%`}</strong></span>
              </div>
            ))}
          </section>
        )}
      </DialogContent>
    </Dialog>
  );
}
