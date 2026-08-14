"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useRef, useState, type ReactNode } from "react";
import { buttonVariants, cx } from "@/lib/theme";
import type { DataPlanPart } from "@/lib/parts";
import { CopilotSidebar } from "./copilot-sidebar";
import { CopilotSidebarProvider } from "./copilot-sidebar-context";
import { PanelIcon, SignOutIcon } from "./icons";
import { RidgelineMark } from "./ridgeline-mark";
import { SessionPlan } from "./session-plan";

type WorkspaceTab = "member" | "graph";

const tabs: ReadonlyArray<{ label: string; value: WorkspaceTab; href: string }> = [
  { label: "Member", value: "member", href: "/member" },
  { label: "Graph", value: "graph", href: "/graph" },
];

const member = {
  id: "mbr_01HX9JORDAN",
  name: "Jordan Rivera",
  initials: "JR",
} as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const activeTab: WorkspaceTab = pathname.startsWith("/graph")
    ? "graph"
    : "member";
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [composerValue, setComposerValue] = useState("");
  const [planPart, setPlanPart] = useState<DataPlanPart | null>(null);
  const composerRef = useRef<HTMLInputElement>(null);
  const prefillMessage = useCallback((message: string) => {
    setSidebarOpen(true);
    setComposerValue(message);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }, []);

  return (
    <CopilotSidebarProvider prefillMessage={prefillMessage}>
      <div className="screen-enter min-h-svh">
        <header className="topbar sticky top-0 z-30 flex h-[var(--header-height)] items-center gap-3.5 px-[18px]">
          <Link href="/member" aria-label="Ridgeline member workspace">
            <RidgelineMark className="size-[26px] text-xs" />
          </Link>

          <nav
            aria-label="Workspace"
            className="shell-tabs rounded-full border border-border bg-surface p-[3px]"
            data-active-tab={activeTab}
          >
            <span className="shell-tab-indicator" aria-hidden="true" />
            {tabs.map((tab) => (
              <Link
                key={tab.value}
                href={tab.href}
                aria-current={activeTab === tab.value ? "page" : undefined}
                className={cx(
                  "press relative z-10 rounded-full px-3.5 py-1 text-[13px] font-medium transition-colors",
                  activeTab === tab.value
                    ? "text-foreground"
                    : "text-foreground-muted hover:text-foreground",
                )}
              >
                {tab.label}
              </Link>
            ))}
          </nav>

          <button
            type="button"
            className="press flex items-center gap-2 rounded-full border border-border bg-surface py-1 pr-3.5 pl-1"
            aria-label="Select member"
          >
            <span className="grid size-[25px] place-items-center rounded-full bg-accent-muted text-[10.5px] font-semibold text-accent">
              {member.initials}
            </span>
            <span className="shell-member-name text-[13px] font-semibold">
              {member.name} <span className="text-foreground-subtle">⌄</span>
            </span>
          </button>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              aria-controls="copilot-sidebar"
              aria-expanded={sidebarOpen}
              aria-label={sidebarOpen ? "Hide copilot" : "Show copilot"}
              className={buttonVariants({ intent: "icon", size: "icon" })}
              onClick={() => setSidebarOpen((open) => !open)}
            >
              <PanelIcon className="size-4" />
            </button>
            <Link
              href="/"
              aria-label="Sign out"
              className={buttonVariants({ intent: "icon", size: "icon" })}
            >
              <SignOutIcon className="size-4" />
            </Link>
          </div>
        </header>

        <div
          className="shell-columns"
          data-sidebar-state={sidebarOpen ? "open" : "closed"}
        >
          <main className="min-w-0 px-5 pt-[22px] pb-14 sm:px-[26px]">
            {children}
            {planPart === null ? null : <SessionPlan part={planPart} />}
          </main>
          <aside
            id="copilot-sidebar"
            data-slot="copilot-sidebar"
            aria-hidden={!sidebarOpen}
            inert={!sidebarOpen}
            className="copilot-slot"
          >
            <CopilotSidebar
              memberId={member.id}
              memberName={member.name}
              composerValue={composerValue}
              composerRef={composerRef}
              hasPlan={planPart !== null}
              onComposerChange={setComposerValue}
              onPlan={setPlanPart}
            />
          </aside>
        </div>
      </div>
    </CopilotSidebarProvider>
  );
}
