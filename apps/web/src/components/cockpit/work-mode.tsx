"use client";

// Progressive disclosure (OttoOS spec §05): COMMAND — full shell · FOCUS — nav collapses ·
// DEEP — nav + rail collapse, band slims, approvals queue silently. ESC exits.
// Nothing is lost — panels reorganize around attention.
import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type WorkMode = "command" | "focus" | "deep";

const WorkModeContext = createContext<{
  mode: WorkMode;
  setMode: (mode: WorkMode) => void;
}>({ mode: "command", setMode: () => {} });

export function WorkModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<WorkMode>("command");

  // ESC steps back toward the full shell (deep → command), matching the prototype.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && mode !== "command") setMode("command");
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mode]);

  const value = useMemo(() => ({ mode, setMode }), [mode]);
  return <WorkModeContext.Provider value={value}>{children}</WorkModeContext.Provider>;
}

export function useWorkMode() {
  return useContext(WorkModeContext);
}
