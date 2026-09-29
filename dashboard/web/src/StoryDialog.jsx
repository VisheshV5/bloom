import React from "react";
import { Box, Flex, Grid, Text } from "@chakra-ui/react";
import { Accordion, AccordionDetails, AccordionSummary, Chip, Dialog, DialogContent, IconButton } from "@mui/material";
import { motion } from "framer-motion";
import { colorFor, laptop, prettyName, secs } from "./lib.js";
import { Lock, agentIcon } from "./icons.jsx";

function sqlOf(args) {
  try { return JSON.parse(args).query; } catch { /* truncated JSON */ }
  return String(args || "").replace(/^\{"query":\s*"/, "").replace(/\\n/g, "\n").replace(/\\"/g, '"');
}
function rowsOf(result) {
  try { const r = JSON.parse(result).result; return r?.rows ? `${r.columns.join(" | ")}\n${r.rows.map((x) => x.join(" | ")).join("\n")}` : result; }
  catch { return result; }
}

function Counter({ label, value, delay }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}>
      <Box p={4} borderRadius="14px" bg="var(--panel)" border="1px solid var(--line)" textAlign="center">
        <Text fontSize="28px" fontWeight={900}>{value}</Text>
        <Text fontSize="13px" color="var(--muted)">{label}</Text>
      </Box>
    </motion.div>
  );
}

export default function StoryDialog({ open, onClose, state }) {
  const trace = (state?.traces || []).slice(-1)[0];
  const places = state?.places || [];
  const team = Object.fromEntries((state?.team || []).map((m) => [m.slug, m]));
  const question = [...(state?.messages || [])].reverse().find((m) => m.src === "forge")?.text;
  const steps = trace?.steps || [];
  const total = Math.max(1, ...steps.map((s) => s.end_ms || 0));
  const spans = steps.flatMap((s) => (s.trace || []).map((sp) => ({ ...sp, step: s })));
  const queries = spans.filter((sp) => sp.kind === "tool" && sp.name === "run_sql");
  const tokens = spans.reduce((n, sp) => n + (sp.tokens_in || 0) + (sp.tokens_out || 0), 0);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth PaperProps={{ sx: { bgcolor: "#0d1410", backgroundImage: "none", border: "1px solid var(--line)" } }}>
      <DialogContent sx={{ p: 5 }}>
        <Flex justify="space-between" align="start">
          <Box>
            <Text fontSize="13px" letterSpacing=".12em" color="var(--muted)" fontWeight={700}>WHAT HAPPENED IN THE LAST TEAM TASK</Text>
            <Text fontSize="28px" fontWeight={800} mt={1} noOfLines={2}>{question ? `“${question}…”` : "No team task yet."}</Text>
          </Box>
          <IconButton onClick={onClose} sx={{ color: "var(--muted)" }}>✕</IconButton>
        </Flex>

        {trace && (
          <>
            <Grid templateColumns="repeat(4, 1fr)" gap={3} mt={5}>
              <Counter label="agents worked on it" value={steps.length} delay={0.1} />
              <Counter label="total time" value={secs(trace.total_ms)} delay={0.2} />
              <Counter label="database queries (aggregates only)" value={queries.length} delay={0.3} />
              <Counter label="AI tokens used" value={tokens.toLocaleString()} delay={0.4} />
            </Grid>

            {queries.length > 0 && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
                <Flex mt={4} p={4} gap={3} align="center" borderRadius="14px" bg="rgba(244,114,182,.07)" border="1px solid rgba(244,114,182,.4)">
                  <Lock sx={{ fontSize: 30, color: "var(--brian)" }} />
                  <Text fontSize="16px">
                    <b>Patient rows never left either hospital.</b> Each hospital's agent ran its queries on its own laptop and sent back only counts.
                  </Text>
                </Flex>
              </motion.div>
            )}

            <Box mt={6} position="relative" pl="34px">
              <motion.div
                style={{ position: "absolute", left: 11, top: 8, width: 3, background: "var(--vine)", borderRadius: 2 }}
                initial={{ height: 0 }} animate={{ height: "calc(100% - 16px)" }} transition={{ duration: 0.4 + steps.length * 0.35 }}
              />
              {steps.map((s, i) => {
                const place = places.find((p) => p.specialist === s.specialist) || {};
                const color = colorFor({ owner: place.owner, kind: s.tier === "inprocess" ? "generalist" : "specialist" });
                const where = s.tier === "nodes" ? `ran on ${laptop(place.owner) || "a SuperNode"}` : "ran inside the coordinator";
                const n = (s.trace || []).filter((sp) => sp.name === "run_sql").length;
                const left = (100 * (s.start_ms || 0)) / total;
                const width = Math.max(1.5, (100 * ((s.end_ms || s.ms || 0) - (s.start_ms || 0))) / total);
                return (
                  <motion.div key={s.step_id} initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + i * 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
                    <Box position="relative" mb={4}>
                      <Box position="absolute" left="-30px" top="18px" w="18px" h="18px" borderRadius="50%" bg={color} boxShadow={`0 0 0 5px rgba(0,0,0,.6)`} />
                      <Box p={4} borderRadius="16px" bg="var(--panel)" border="1px solid var(--line)">
                        <Flex justify="space-between" align="center" gap={4}>
                          <Flex align="center" gap={3} minW={0}>
                            {React.createElement(agentIcon(s.specialist, null), { sx: { fontSize: 28, color } })}
                            <Box minW={0}>
                              <Text fontSize="18px" fontWeight={800}>{prettyName(s.specialist)}</Text>
                              <Text fontSize="13px" color={color}>{where}{s.fallback ? ` · fallback: ${s.fallback}` : ""}</Text>
                            </Box>
                          </Flex>
                          <Flex gap={2} align="center" flexShrink={0}>
                            {n > 0 && <Chip size="small" label={`${n} quer${n === 1 ? "y" : "ies"}`} variant="outlined" />}
                            {s.checked && <Chip size="small" label="self-checked" variant="outlined" />}
                            <Chip size="small" color={s.ok ? "success" : "error"} label={s.ok ? secs(s.ms) : "failed"} />
                          </Flex>
                        </Flex>
                        <Text mt={2} fontSize="14px" color="var(--muted)" noOfLines={1}>Asked: {s.instruction}</Text>
                        <Text mt={1} fontSize="15px" color="#dfeae2" noOfLines={2}>→ {s.answer || s.error}</Text>
                        <Box mt={3} h="6px" bg="#18221c" borderRadius="3px" position="relative" overflow="hidden">
                          <motion.div
                            style={{ position: "absolute", left: `${left}%`, top: 0, bottom: 0, background: color, borderRadius: 3 }}
                            initial={{ width: 0 }} animate={{ width: `${width}%` }} transition={{ delay: 0.8 + i * 0.35, duration: 0.7 }}
                          />
                        </Box>
                      </Box>
                    </Box>
                  </motion.div>
                );
              })}
            </Box>
            <Text fontSize="12px" color="var(--muted)">The thin bar under each step shows when it ran. Steps that overlap ran at the same time on different laptops.</Text>

            {queries.length > 0 && (
              <Accordion sx={{ mt: 3, bgcolor: "transparent", boxShadow: "none", border: "1px solid var(--line)", "&:before": { display: "none" } }}>
                <AccordionSummary expandIcon={<span>▾</span>}>
                  <Text fontWeight={700}>Show the exact queries and what came back</Text>
                </AccordionSummary>
                <AccordionDetails>
                  {queries.map((q, i) => (
                    <Box key={i} mb={4} p={3} borderRadius="10px" bg="#0a100c" border="1px solid var(--line)">
                      <Text fontSize="13px" color="var(--muted)" mb={2}>{prettyName(q.step.specialist)} · {q.phase}</Text>
                      <div className="sql">{sqlOf(q.args)}</div>
                      <div className="sql" style={{ color: "#fbcfe8", marginTop: 8 }}>{rowsOf(q.result)}</div>
                    </Box>
                  ))}
                </AccordionDetails>
              </Accordion>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
