"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { buttonVariants, cx } from "@/lib/theme";
import { PanelIcon, SendIcon, SignOutIcon } from "./icons";
import { RidgelineMark } from "./ridgeline-mark";

type WorkspaceTab = "member" | "graph";

const tabs: ReadonlyArray<{ label: string; value: WorkspaceTab; href: string }> = [
  { label: "Member", value: "member", href: "/member" },
  { label: "Graph", value: "graph", href: "/graph" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const activeTab: WorkspaceTab = pathname.startsWith("/graph")
    ? "graph"
    : "member";
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
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
            JR
          </span>
          <span className="shell-member-name text-[13px] font-semibold">
            Jordan Rivera <span className="text-foreground-subtle">⌄</span>
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
        </main>
        <aside
          id="copilot-sidebar"
          data-slot="copilot-sidebar"
          aria-hidden={!sidebarOpen}
          inert={!sidebarOpen}
          className="copilot-slot"
        >
          <div className="copilot-panel flex flex-col px-[18px] pt-[18px] pb-6">
            <div className="mb-3 flex items-baseline gap-2">
              <h2 className="text-[15px] font-semibold">Copilot</h2>
              <span className="text-xs text-foreground-subtle">Jordan Rivera</span>
            </div>
            <div className="mb-4 flex flex-wrap gap-1.5" aria-label="Quick prompts">
              {["Adherence", "Sleep", "Messages", "4 weeks"].map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="press rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground-muted transition-colors hover:border-border-strong hover:text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
            <div className="flex flex-1 items-center justify-center border-y border-border py-10 text-center">
              <div className="max-w-[230px]">
                <p className="font-medium text-foreground">Ask about Jordan</p>
                <p className="mt-1 text-xs text-foreground-subtle">
                  Member context, session planning, and coach actions appear here.
                </p>
              </div>
            </div>
            <form className="flex gap-2 pt-3" onSubmit={(event) => event.preventDefault()}>
              <label htmlFor="copilot-composer" className="sr-only">
                Message copilot
              </label>
              <input
                id="copilot-composer"
                className="min-w-0 flex-1 rounded-[14px] border border-border-strong bg-surface-input px-3.5 py-2.5 text-foreground outline-none placeholder:text-foreground-subtle"
                placeholder="Plan a session · ask about Jordan"
              />
              <button
                type="submit"
                className={buttonVariants({ size: "icon" })}
                aria-label="Send message"
              >
                <SendIcon className="size-4" />
              </button>
            </form>
          </div>
        </aside>
      </div>
    </div>
  );
}
