import React from "react";
import { Box, Flex, Text } from "@chakra-ui/react";
import { Chip, LinearProgress } from "@mui/material";
import { AnimatePresence, motion } from "framer-motion";

const COLORS = { approval: "#d9577e", final: "#5e8c4f", joined: "#8e6cc4", building: "#e0a030", gap: "#d9703a", proof: "#5e8c4f" };
const ROLES = [["architect", "Architect", "designs it"], ["builder", "Builder", "writes the code"], ["reviewer", "Reviewer", "tests it"]];
import { NOW_ICON } from "./icons.jsx";

function Roles({ roles }) {
  return (
    <Flex gap={2} mt={4}>
      {ROLES.map(([k, name, what]) => {
        const s = roles?.[k] || "todo";
        return (
          <Box key={k} flex={1} p={3} borderRadius="12px" border="1px solid"
            borderColor={s === "active" ? "var(--green)" : "var(--line)"}
            bg={s === "active" ? "var(--green-soft)" : "transparent"} opacity={s === "todo" ? 0.5 : 1}>
            <Text fontWeight={700} fontSize="14px">{s === "done" ? "✓ " : ""}{name}</Text>
            <Text fontSize="12px" color="var(--muted)">{what}</Text>
            {s === "active" && <LinearProgress sx={{ mt: 1, borderRadius: 2 }} />}
          </Box>
        );
      })}
    </Flex>
  );
}

export default function NowCard({ now, onProof }) {
  if (!now) now = { kind: "idle", title: "Waiting for a task", body: "The team’s latest activity will appear here." };
  const key = `${now.kind}|${now.title}`;
  return (
    <Box position="relative" >
      <AnimatePresence mode="wait">
        <motion.div
          key={key}
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -16, scale: 0.98 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          <Box p={6} borderRadius="16px" bg="var(--panel)" border="1px solid var(--line)"
            boxShadow={now.kind === "approval" ? "0 0 0 1px var(--brian)" : "none"}>
            <Text fontSize="12px" letterSpacing=".12em" color="var(--muted)" fontWeight={700}>RIGHT NOW</Text>
            <Flex align="center" gap={3} mt={2}>
              <Flex w="48px" h="48px" borderRadius="14px" align="center" justify="center" bg={COLORS[now.kind] ? `${COLORS[now.kind]}22` : "var(--panel-2)"} flexShrink={0}>
                {React.createElement(NOW_ICON[now.kind] || NOW_ICON.idle, { sx: { fontSize: 28, color: COLORS[now.kind] || "#5e8c4f" } })}
              </Flex>
              <Text fontSize="22px" fontWeight={600} lineHeight={1.15}>{now.title}</Text>
            </Flex>
            {now.body && (
              <Text mt={3} fontSize="14px" color="var(--ink-2)" lineHeight={1.75}>
                {now.body}
              </Text>
            )}
            {now.kind === "building" && <Roles roles={now.roles} />}
            {now.problem && now.kind === "building" && (
              <Text mt={3} fontSize="13px" color="#c2410c">Reviewer found: {now.problem}</Text>
            )}
            {now.kind === "approval" && (
              <Flex mt={4} gap={2} wrap="wrap">
                {now.detail && <Chip label={now.detail} color="secondary" variant="outlined" />}
                {now.sha && <Chip label={`fingerprint ${now.sha}…`} variant="outlined" />}
                <Chip label={now.owner ? "only the data owner can approve" : "a human must approve"} />
              </Flex>
            )}
            {now.kind === "final" && (
              <Flex mt={4} gap={2} wrap="wrap" align="center">
                {now.passed && <Chip color="success" label="✓ matches the reference answer" />}
                {now.proof_ready && <Chip variant="outlined" label="View evaluation" onClick={onProof} />}
              </Flex>
            )}
          </Box>
        </motion.div>
      </AnimatePresence>
    </Box>
  );
}
