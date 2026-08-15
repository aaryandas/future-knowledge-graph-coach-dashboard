"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { DataConstraintsPart, DataPlanPart } from "@/lib/parts";

interface CopilotSidebarInterface {
  planPart: DataPlanPart | null;
  constraintsPart: DataConstraintsPart | null;
  prefillMessage(message: string): void;
}

const CopilotSidebarContext = createContext<CopilotSidebarInterface | null>(
  null,
);

export function CopilotSidebarProvider({
  children,
  planPart,
  constraintsPart,
  prefillMessage,
}: {
  children: ReactNode;
  planPart: DataPlanPart | null;
  constraintsPart: DataConstraintsPart | null;
  prefillMessage(message: string): void;
}) {
  const value = useMemo(
    () => ({ planPart, constraintsPart, prefillMessage }),
    [planPart, constraintsPart, prefillMessage],
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
