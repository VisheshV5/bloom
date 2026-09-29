import React from "react";
import bloomMark from "./assets/bloom.svg";

export default function TopBar({ replay, stage, online, onOpen }) {
  return (
    <header className="topbar">
      <a className="brand" href="#main" aria-label="Bloom home">
        <img src={bloomMark} alt="" width="32" height="32" />
        <span>Bloom</span>
      </a>
      <nav className="header-links" aria-label="Workspace details">
        {[["p", "Evaluation"], ["t", "Timeline"], ["l", "Messages"]].map(([key, label]) => (
          <button key={key} onClick={() => onOpen(key)} aria-haspopup="dialog" aria-keyshortcuts={key}>{label}</button>
        ))}
      </nav>
      <span className={`connection ${online ? "" : "offline"}`} role="status">
        <i />{!online ? "Reconnecting" : stage === "live" || (!replay && !stage) ? "Live" : "Replay"}
      </span>
    </header>
  );
}
