import React from "react";
import { Box, Flex, Text } from "@chakra-ui/react";
import { Chip, Dialog, DialogContent, IconButton } from "@mui/material";
import { AnimatePresence, motion } from "framer-motion";
import { prettyName } from "./lib.js";

const who = (s) => (s === "forge" ? "You" : prettyName(s));

export default function MessagesDialog({ open, onClose, messages }) {
  const rows = [...(messages || [])].reverse();
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { bgcolor: "#0d1410", backgroundImage: "none", border: "1px solid var(--line)" } }}>
      <DialogContent sx={{ p: 4 }}>
        <Flex justify="space-between" align="center" mb={3}>
          <Text fontSize="24px" fontWeight={800}>Messages on the Flower Grid</Text>
          <IconButton onClick={onClose} sx={{ color: "var(--muted)" }}>✕</IconButton>
        </Flex>
        {!rows.length && <Text color="var(--muted)">No messages yet.</Text>}
        <AnimatePresence initial={false}>
          {rows.map((m) => (
            <motion.div key={m.id} layout initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
              <Box py={3} borderBottom="1px solid var(--line)">
                <Flex align="center" gap={2} mb={1}>
                  <Text fontWeight={700}>{who(m.src)}</Text>
                  <Text color="var(--green)">→</Text>
                  <Text fontWeight={700}>{who(m.dst)}</Text>
                  {m.tier && <Chip size="small" variant="outlined" label={m.tier === "nodes" ? "over the Grid" : m.tier === "inprocess" ? "inside coordinator" : m.tier} />}
                  <Text ml="auto" fontSize="12px" color="var(--muted)">{new Date(m.ts * 1000).toLocaleTimeString()}</Text>
                </Flex>
                <Text fontSize="14px" color="#cfdcd3" noOfLines={3}>{m.text}</Text>
              </Box>
            </motion.div>
          ))}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  );
}
