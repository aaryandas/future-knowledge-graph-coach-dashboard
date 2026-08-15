"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { CopilotSidebarProvider } from "./copilot-sidebar-context";
import {
  AdjustIcon,
  CloseIcon,
  DumbbellIcon,
  ExplainIcon,
  GoalIcon,
  KneeIcon,
  PanelIcon,
  PersonIcon,
  SendIcon,
  ShieldIcon,
  TrendIcon,
  type IconProps,
} from "./icons";

type WorkspaceTab = "dashboard" | "members" | "graph";

const tabs: ReadonlyArray<{
  label: string;
  value: WorkspaceTab;
  href: string;
}> = [
  { label: "Dashboard", value: "dashboard", href: "/member" },
  { label: "Members", value: "members", href: "/members" },
  { label: "Graph", value: "graph", href: "/graph" },
];

const memberFacts: ReadonlyArray<{
  label: string;
  tone: "identity" | "attention" | "goal";
  Icon: ComponentType<IconProps>;
}> = [
  { label: "Jordan Rivera · 41", tone: "identity", Icon: PersonIcon },
  {
    label: "Left-knee PFPS · recovering",
    tone: "attention",
    Icon: KneeIcon,
  },
  { label: "No barbell", tone: "attention", Icon: DumbbellIcon },
  {
    label: "Adherence 50% from 100%",
    tone: "attention",
    Icon: TrendIcon,
  },
  {
    label: "Goal · Lower-body strength",
    tone: "goal",
    Icon: GoalIcon,
  },
];

const quickActions = [
  {
    label: "Adjust",
    prompt: "Adjust today’s session",
    Icon: AdjustIcon,
  },
  {
    label: "Explain",
    prompt: "Explain the choices in today’s session",
    Icon: ExplainIcon,
  },
  {
    label: "Constraints",
    prompt: "Check today’s session against Jordan’s constraints",
    Icon: ShieldIcon,
  },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const activeTab: WorkspaceTab = pathname.startsWith("/graph")
    ? "graph"
    : pathname.startsWith("/members")
      ? "members"
      : "dashboard";
  const [mobileCopilotOpen, setMobileCopilotOpen] = useState(false);
  const [isNarrow, setIsNarrow] = useState(false);
  const [composerValue, setComposerValue] = useState("");
  const composerRef = useRef<HTMLInputElement>(null);
  const copilotToggleRef = useRef<HTMLButtonElement>(null);
  const copilotCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 980px)");
    const update = () => setIsNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!isNarrow || !mobileCopilotOpen) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isNarrow, mobileCopilotOpen]);

  const closeMobileCopilot = useCallback(() => {
    setMobileCopilotOpen(false);
    window.requestAnimationFrame(() => copilotToggleRef.current?.focus());
  }, []);

  useEffect(() => {
    if (!isNarrow || !mobileCopilotOpen) {
      return;
    }

    copilotCloseRef.current?.focus();

    function handlePanelKeydown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMobileCopilot();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const panel = document.getElementById("copilot-panel");
      const focusable = panel?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable || focusable.length === 0) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }

    document.addEventListener("keydown", handlePanelKeydown);
    return () => document.removeEventListener("keydown", handlePanelKeydown);
  }, [closeMobileCopilot, isNarrow, mobileCopilotOpen]);

  const prefillMessage = useCallback((message: string) => {
    setMobileCopilotOpen(true);
    setComposerValue(message);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }, []);

  const copilotHidden = isNarrow && !mobileCopilotOpen;

  return (
    <CopilotSidebarProvider prefillMessage={prefillMessage}>
      <div className="app-frame screen-enter">
        <header className="app-header" inert={isNarrow && mobileCopilotOpen ? true : undefined}>
          <div className="global-nav-row">
            <Link className="future-wordmark" href="/member" aria-label="Future Coach dashboard">
              Future Coach
            </Link>
            <nav className="global-nav" aria-label="Workspace">
              {tabs.map((tab) => (
                <Link
                  key={tab.value}
                  href={tab.href}
                  aria-current={activeTab === tab.value ? "page" : undefined}
                  className="global-nav-link"
                >
                  {tab.label}
                </Link>
              ))}
            </nav>
            <button
              ref={copilotToggleRef}
              type="button"
              className="mobile-copilot-toggle"
              aria-controls="copilot-panel"
              aria-expanded={mobileCopilotOpen}
              onClick={() => setMobileCopilotOpen(true)}
            >
              <PanelIcon className="size-4" />
              Copilot
            </button>
          </div>

          <div className="member-context-strip" aria-label="Jordan Rivera context">
            {memberFacts.map(({ label, tone, Icon }) => (
              <div key={label} className="member-context-item" data-tone={tone}>
                <Icon className="member-context-icon" />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </header>

        <div className="workspace-split" data-mobile-copilot={mobileCopilotOpen ? "open" : "closed"}>
          <main
            className="dashboard-canvas"
            inert={isNarrow && mobileCopilotOpen ? true : undefined}
          >
            {children}
          </main>
          <aside
            id="copilot-panel"
            className="copilot-pane"
            aria-labelledby="copilot-title"
            aria-hidden={copilotHidden}
            inert={copilotHidden ? true : undefined}
          >
            <div className="copilot-pane-inner">
              <div className="copilot-heading-row">
                <h2 id="copilot-title" className="display-title copilot-title">
                  Copilot
                </h2>
                <button
                  ref={copilotCloseRef}
                  type="button"
                  className="copilot-close"
                  aria-label="Close Copilot"
                  onClick={closeMobileCopilot}
                >
                  <CloseIcon className="size-5" />
                </button>
              </div>

              <p className="copilot-empty">What can I help with today?</p>

              <div className="copilot-controls">
                <div className="copilot-quick-actions" aria-label="Copilot quick actions">
                  {quickActions.map(({ label, prompt, Icon }) => (
                    <button
                      key={label}
                      type="button"
                      className="copilot-chip"
                      onClick={() => prefillMessage(prompt)}
                    >
                      <Icon className="size-[18px]" />
                      {label}
                    </button>
                  ))}
                </div>
                <form
                  className="copilot-composer"
                  onSubmit={(event) => event.preventDefault()}
                >
                  <label htmlFor="copilot-composer" className="sr-only">
                    Ask Copilot about this session
                  </label>
                  <input
                    ref={composerRef}
                    id="copilot-composer"
                    value={composerValue}
                    placeholder="Ask about this session…"
                    onChange={(event) => setComposerValue(event.target.value)}
                  />
                  <button type="submit" aria-label="Send message">
                    <SendIcon className="size-5" />
                  </button>
                </form>
              </div>
            </div>
          </aside>
          <button
            type="button"
            className="copilot-backdrop"
            aria-label="Close Copilot"
            tabIndex={-1}
            onClick={closeMobileCopilot}
          />
        </div>
      </div>
    </CopilotSidebarProvider>
  );
}
