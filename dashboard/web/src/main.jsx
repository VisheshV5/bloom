import React from "react";
import { createRoot } from "react-dom/client";
import { ChakraProvider, extendTheme } from "@chakra-ui/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import App from "./App.jsx";
import "./styles.css";

const chakraTheme = extendTheme({
  config: { initialColorMode: "dark", useSystemColorMode: false },
  fonts: { heading: "var(--font)", body: "var(--font)" },
  styles: { global: { body: { bg: "var(--bg)", color: "var(--ink)" } } },
});

const muiTheme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#4ade80" },
    secondary: { main: "#f472b6" },
    background: { default: "#0a0e0c", paper: "#111814" },
  },
  shape: { borderRadius: 14 },
  typography: { fontFamily: "var(--font)" },
});

createRoot(document.getElementById("root")).render(
  <ChakraProvider theme={chakraTheme}>
    <ThemeProvider theme={muiTheme}>
      <App />
    </ThemeProvider>
  </ChakraProvider>,
);
