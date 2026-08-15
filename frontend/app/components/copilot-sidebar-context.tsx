"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import type {
  DataConstraintsPart,
  DataPlanPart,
  DataTracePart,
} from "@/lib/parts";

interface CopilotSidebarInterface {
  planPart: DataPlanPart | null;
  tracePart: DataTracePart | null;
  constraintsPart: DataConstraintsPart | null;
  adjustmentBusy: boolean;
  prefillMessage(message: string): void;
  submitAdjustment(message: string): void;
}

const CopilotSidebarContext = createContext<CopilotSidebarInterface | null>(
  null,
);

export function CopilotSidebarProvider({
  children,
  planPart,
  tracePart,
  constraintsPart,
  adjustmentBusy,
  prefillMessage,
  submitAdjustment,
}: {
  children: ReactNode;
  planPart: DataPlanPart | null;
  tracePart: DataTracePart | null;
  constraintsPart: DataConstraintsPart | null;
  adjustmentBusy: boolean;
  prefillMessage(message: string): void;
  submitAdjustment(message: string): void;
}) {
  const value = useMemo(
    () => ({
      planPart,
      tracePart,
      constraintsPart,
      adjustmentBusy,
      prefillMessage,
      submitAdjustment,
    }),
    [
      planPart,
      tracePart,
      constraintsPart,
      adjustmentBusy,
      prefillMessage,
      submitAdjustment,
    ],
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
