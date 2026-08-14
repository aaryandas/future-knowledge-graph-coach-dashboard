"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

interface CopilotSidebarInterface {
  prefillMessage(message: string): void;
}

const CopilotSidebarContext = createContext<CopilotSidebarInterface | null>(
  null,
);

export function CopilotSidebarProvider({
  children,
  prefillMessage,
}: {
  children: ReactNode;
  prefillMessage(message: string): void;
}) {
  const value = useMemo(() => ({ prefillMessage }), [prefillMessage]);

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
