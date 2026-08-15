"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { DataPlanPart } from "@/lib/parts";

interface CopilotSidebarInterface {
  planPart: DataPlanPart | null;
  prefillMessage(message: string): void;
}

const CopilotSidebarContext = createContext<CopilotSidebarInterface | null>(
  null,
);

export function CopilotSidebarProvider({
  children,
  planPart,
  prefillMessage,
}: {
  children: ReactNode;
  planPart: DataPlanPart | null;
  prefillMessage(message: string): void;
}) {
  const value = useMemo(
    () => ({ planPart, prefillMessage }),
    [planPart, prefillMessage],
  );

  return (
    <CopilotSidebarContext.Provider value={value}>
      {children}
    </CopilotSidebarContext.Provider>
  );
}

export function useCopilotSidebar(): CopilotSidebarInterface {
  const sidebar = useContext(CopilotSidebarContext);
  if (sidebar === null) {
    throw new Error("useCopilotSidebar requires CopilotSidebarProvider");
  }
  return sidebar;
}
