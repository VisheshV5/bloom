import React from "react";
import { Box, Flex, Text } from "@chakra-ui/react";
import { Chip, Dialog, IconButton } from "@mui/material";
import { motion } from "framer-motion";
import { laptop, person, siteName } from "./lib.js";
import { agentIcon } from "./icons.jsx";
import { Bee, PALETTES, Petals, Stamen, paletteOf } from "./Garden.jsx";

// Plain-English names for the tools an agent can call.
const TOOL_NAMES = {
  run_sql: "Hospital database (read-only, totals only)",
  calculate: "Calculator",
  describe: "Summary statistics",
  percentile: "Percentiles",
  ttest_welch: "t-test",
  linregress: "Linear regression",
  correlation: "Correlation",
  regex_findall: "Text pattern finder",
  convert_units: "Unit converter",
  add_days: "Date maths",
  add_business_days: "Business-day maths",
  business_days_between: "Business days between",
  business_days_in_range: "Business days in range",
  days_between: "Days between",
  weekday: "Day of the week",
};
const MAKERS = { architect: "designed by the Architect", builder: "written by the Builder", reviewer: "tested by the Reviewer" };

function Section({ title, children, delay }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.4 }}>
      <Box mt={5}>
        <Text fontSize="11px" letterSpacing=".12em" fontWeight={700} color="var(--muted)" mb={2}>{title}</Text>
        {children}
      </Box>
    </motion.div>
  );
}

export default function AgentDialog({ flower, state, onClose }) {
  const open = !!flower;
  const f = flower || {};
  const agent = (state?.agents || []).find((a) => a.slug === f.slug) || {};
  const pal = open ? paletteOf(f) : "plain";
  const color = PALETTES[pal][1];
  const isGen = f.kind === "generalist";
  const where = isGen ? "Inside the coordinator (no tools, no data)" : [siteName(f.site), laptop(f.owner)].filter(Boolean).join(" · ") || "A SuperNode";
  const makers = (agent.created_by || []).map((m) => MAKERS[m]).filter(Boolean);
  const Icon = agentIcon(f.slug, agent.category);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      PaperProps={{ sx: { bgcolor: "var(--panel)", backgroundImage: "none", borderRadius: "22px", overflow: "hidden" } }}>
      {open && (
        <Box position="relative">
          <Box position="absolute" inset={0} h="170px" bg={`linear-gradient(180deg, ${PALETTES[pal][2]} 0%, transparent 100%)`} />
          <IconButton onClick={onClose} sx={{ position: "absolute", right: 12, top: 12, color: "var(--muted)", zIndex: 1 }}>✕</IconButton>
          <Box position="relative" px={7} pt={6} pb={7}>
            <Flex align="center" gap={5}>
              {/* the blossom re-opens inside the card */}
              <svg viewBox="-40 -40 80 80" width="96" height="96" style={{ flexShrink: 0, overflow: "visible" }}>
                {isGen ? <Bee T={0.9} /> : (
                  <>
                    <g className="spin blossom" style={{ animationDuration: "40s" }}>
                      <Petals pal={pal} T={0.9} back />
                      <Petals pal={pal} T={0.9} />
                    </g>
                    <Stamen T={0.9} />
                  </>
                )}
              </svg>
              <Box minW={0}>
                <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25 }}>
                  <Flex align="center" gap={2}>
                    <Icon sx={{ color, fontSize: 22 }} />
                    <Text fontSize="26px" fontWeight={800} lineHeight={1.15}>{f.site ? `${f.name} · ${siteName(f.site)}` : f.name}</Text>
                  </Flex>
                  <Text mt={1} fontSize="16px" color="var(--ink-2)">{f.job}</Text>
                  <Flex mt={3} gap={2} wrap="wrap">
                    <Chip size="small" label={isGen ? "Starting agent · the bee" : "Specialist"} sx={{ bgcolor: PALETTES[pal][2], color: PALETTES[pal][0], fontWeight: 600 }} />
                    {f.skill && !isGen && <Chip size="small" variant="outlined" label={f.skill} />}
                  </Flex>
                </motion.div>
              </Box>
            </Flex>

            <Section title="WHAT IT DOES" delay={0.35}>
              <Text fontSize="15px" color="var(--ink-2)" lineHeight={1.6}>{agent.purpose || f.job}</Text>
            </Section>

            <Section title="WHERE IT RUNS" delay={0.45}>
              <Text fontSize="15px" color="var(--ink-2)">{where}</Text>
              {f.node_id && <Text fontSize="12px" color="var(--muted)" mt={1}>Flower SuperNode {f.node_id}</Text>}
              {f.site && (
                <Text fontSize="13px" color="var(--muted)" mt={1}>
                  {siteName(f.site)}'s patient records stay on {person(f.owner) ? `${person(f.owner)}'s` : "this"} laptop; only totals leave.
                </Text>
              )}
            </Section>

            <Section title="TOOLS IT CAN USE" delay={0.55}>
              {(agent.tools || []).length ? (
                <Flex gap={2} wrap="wrap">
                  {agent.tools.map((t) => <Chip key={t} size="small" variant="outlined" label={TOOL_NAMES[t] || t} />)}
                </Flex>
              ) : (
                <Text fontSize="15px" color="var(--ink-2)">None: it answers from what the AI model already knows.</Text>
              )}
            </Section>

            {!isGen && (
              <Section title="HOW IT JOINED THE TEAM" delay={0.65}>
                <Text fontSize="15px" color="var(--ink-2)" lineHeight={1.6}>
                  Bloom noticed a gap, then it was {makers.length ? makers.join(", ") : "built by the Forge"}.
                  It only started running after its owner approved it.
                  {agent.created_at && <Text as="span" color="var(--muted)"> ({new Date(agent.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })})</Text>}
                </Text>
              </Section>
            )}

          </Box>
        </Box>
      )}
    </Dialog>
  );
}
