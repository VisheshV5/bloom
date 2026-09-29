import React from "react";
import { Flex, Text, Box } from "@chakra-ui/react";
import { Step, StepLabel, Stepper, Chip } from "@mui/material";
import { motion } from "framer-motion";
import { LocalFlorist } from "./icons.jsx";

const hm = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export default function TopBar({ story, replay, teamSize, online }) {
  const active = Math.max(0, (story?.step || 0) - 1);
  return (
    <Flex align="center" gap={6} px={8} pt={5} pb={2}>
      <Flex align="center" gap={3} minW="190px">
        <motion.span
          style={{ display: "inline-flex" }}
          animate={{ rotate: [0, 12, -8, 0] }} transition={{ duration: 6, repeat: Infinity }}
        ><LocalFlorist sx={{ fontSize: 38, color: "#f472b6" }} /></motion.span>
        <Box>
          <Text fontSize="26px" fontWeight={800} lineHeight={1}>Bloom</Text>
          <Text fontSize="12px" color="var(--muted)">a team of agents that grows itself</Text>
        </Box>
      </Flex>
      <Box flex={1}>
        <Stepper activeStep={active} alternativeLabel sx={{ "& .MuiStepLabel-label": { fontSize: 13, mt: "6px !important" } }}>
          {(story?.steps || []).map((s, i) => (
            <Step key={s} completed={i < active || (story?.step === 6 && i === 5)}>
              <StepLabel>{s}</StepLabel>
            </Step>
          ))}
        </Stepper>
      </Box>
      <Flex direction="column" align="flex-end" gap={1} minW="190px">
        {replay && (
          <Chip
            size="small"
            color={replay.live ? "success" : "warning"}
            label={replay.live ? "● LIVE" : `REPLAY · recorded ${hm(replay.from)}–${hm(replay.to)}`}
            sx={{ fontWeight: 700 }}
          />
        )}
        {!online && <Chip size="small" color="error" label="server offline" />}
        <Text fontSize="13px" color="var(--muted)">
          {teamSize} agent{teamSize === 1 ? "" : "s"} on the team
        </Text>
      </Flex>
    </Flex>
  );
}
