import React, { useEffect, useMemo, useState } from "react";
import { Box, Flex, Grid, Text } from "@chakra-ui/react";
import { Button } from "@mui/material";
import { AnimatePresence, motion } from "framer-motion";
import useApiState from "./useApiState.js";
import { buildFlowers } from "./lib.js";
import { LocalFlorist, agentIcon } from "./icons.jsx";
import TopBar from "./TopBar.jsx";
import Garden from "./Garden.jsx";
import NowCard from "./NowCard.jsx";
import ProofDialog from "./ProofDialog.jsx";
import StoryDialog from "./StoryDialog.jsx";
import MessagesDialog from "./MessagesDialog.jsx";

function BeforeAfter({ rows }) {
  if (!rows?.length) return null;
  return (
    <Box mt={4} p={4} borderRadius="16px" border="1px solid var(--line)">
      <Text fontSize="12px" letterSpacing=".12em" color="var(--muted)" fontWeight={700} mb={2}>PRACTICE QUESTIONS · BEFORE → AFTER</Text>
      {rows.map((r) => (
        <Flex key={r.category} align="center" gap={3} py={1}>
          <Flex w="160px" align="center" gap={2} fontSize="14px">{React.createElement(agentIcon(null, r.category), { sx: { fontSize: 18, color: "var(--muted)" } })}{r.skill}</Flex>
          <Text w="44px" textAlign="right" color="var(--muted)" fontWeight={700}>{r.before ?? "—"}{r.before != null && "%"}</Text>
          <Box flex={1} h="8px" bg="#18221c" borderRadius="4px" position="relative" overflow="hidden">
            <motion.div style={{ position: "absolute", inset: 0, background: "var(--green)", borderRadius: 4, transformOrigin: "left" }}
              initial={{ scaleX: (r.before || 0) / 100 }} animate={{ scaleX: (r.after ?? r.before ?? 0) / 100 }} transition={{ duration: 1.2 }} />
          </Box>
          <Text w="44px" fontWeight={800} color="var(--green)">{r.after ?? "—"}{r.after != null && "%"}</Text>
        </Flex>
      ))}
    </Box>
  );
}

function Legend() {
  const dot = (c) => <Box as="span" display="inline-block" w="10px" h="10px" borderRadius="50%" bg={c} mr={2} />;
  return (
    <Box mt={4} fontSize="13px" color="var(--muted)" lineHeight={1.9}>
      <Flex gap={5} wrap="wrap">
        <span>{dot("var(--brian)")}Brian's laptop</span>
        <span>{dot("var(--vishesh)")}Vishesh's laptop</span>
        <span>{dot("var(--plain)")}inside the coordinator</span>
      </Flex>
      <Text>New agents grow on a golden-angle spiral (137.5°), like sunflower seeds. Green vines = a question going out; a bud = the answer coming back.</Text>
    </Box>
  );
}

export default function App() {
  const { state, online } = useApiState(700);
  const [open, setOpen] = useState(null);
  const flowers = useMemo(() => (state ? buildFlowers(state) : []), [state]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "escape") setOpen(null);
      else if (k === "p" || k === "t" || k === "l") setOpen((o) => (o === k ? null : k));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!state) {
    return (
      <Flex h="100vh" align="center" justify="center" direction="column" gap={3}>
        <motion.div animate={{ scale: [1, 1.2, 1], rotate: [0, 20, 0] }} transition={{ duration: 1.6, repeat: Infinity }} style={{ display: "inline-flex" }}><LocalFlorist sx={{ fontSize: 64, color: "#f472b6" }} /></motion.div>
        <Text color="var(--muted)">{online ? "Loading Bloom…" : "Can't reach the Bloom server on this machine."}</Text>
      </Flex>
    );
  }
  const story = state.story || {};

  return (
    <Flex direction="column" h={{ base: "auto", lg: "100vh" }} minH="100vh">
      <TopBar story={story} replay={state.replay} teamSize={state.team?.length || 0} online={online} />
      <Box px={{ base: 4, lg: 10 }} pt={2}>
        <AnimatePresence mode="wait">
          <motion.div key={story.headline} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.4 }}>
            <Text fontSize="34px" fontWeight={850} lineHeight={1.15}>{story.headline}</Text>
            <Text fontSize="17px" color="var(--muted)" mt={1} noOfLines={1}>{story.sub || " "}</Text>
          </motion.div>
        </AnimatePresence>
      </Box>
      <Grid templateColumns={{ base: "1fr", lg: "1.9fr 1fr" }} gap={6} px={{ base: 4, lg: 8 }} pb={5} flex={1} minH={0}>
        <Box minH={{ base: "420px", lg: 0 }} position="relative">
          <Garden flowers={flowers} messages={state.messages} now={story.now} lastEventId={state.last_event_id} />
        </Box>
        <Flex direction="column" minH={0} overflowY="auto" pt={4} pr={2} sx={{ "& > *": { flexShrink: 0 } }}>
          <NowCard now={story.now} />
          <Flex gap={3} mt={4}>
            {[["p", "Proof"], ["t", "What happened"], ["l", "Messages"]].map(([k, label]) => (
              <Button key={k} variant={k === "p" ? "contained" : "outlined"} size="large" onClick={() => setOpen(k)}
                sx={{ flex: 1, textTransform: "none", fontWeight: 700, fontSize: 15, py: 1.4 }}>
                <span className="kbd">{k.toUpperCase()}</span>{label}
              </Button>
            ))}
          </Flex>
          <BeforeAfter rows={state.before_after} />
          <Legend />
        </Flex>
      </Grid>
      <ProofDialog open={open === "p"} onClose={() => setOpen(null)} ev={state.eval} />
      <StoryDialog open={open === "t"} onClose={() => setOpen(null)} state={state} />
      <MessagesDialog open={open === "l"} onClose={() => setOpen(null)} messages={state.messages} />
    </Flex>
  );
}
