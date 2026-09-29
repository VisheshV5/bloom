import { useEffect, useState } from "react";

// Poll the stdlib dashboard server; keep the last good state on errors.
export default function useApiState(ms = 700) {
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let alive = true;
    let timer;
    const tick = async () => {
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        if (alive) { setState(data); setOnline(true); }
      } catch {
        if (alive) setOnline(false);
      }
      if (alive) timer = setTimeout(tick, ms);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [ms]);
  return { state, online };
}
