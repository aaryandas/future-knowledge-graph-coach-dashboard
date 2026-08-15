"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { DataPlanPart, MemberSnapshotPart } from "@/lib/parts";
import { CopilotSidebar } from "./copilot-sidebar";
import { CopilotSidebarProvider } from "./copilot-sidebar-context";
import {
  CloseIcon,
  DumbbellIcon,
  GoalIcon,
  KneeIcon,
  PanelIcon,
  PersonIcon,
  TrendIcon,
} from "./icons";
import { JourneyStageChip } from "./journey-stage-chip";
import { SessionPlan } from "./session-plan";

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

const member = {
  id: "mbr_01HX9JORDAN",
} as const;

export function AppShell({
  children,
  memberSnapshot,
}: {
  children: ReactNode;
  memberSnapshot: MemberSnapshotPart | null;
}) {
  const pathname = usePathname();
  const activeTab: WorkspaceTab = pathname.startsWith("/graph")
    ? "graph"
    : pathname.startsWith("/members")
      ? "members"
      : "dashboard";
  const [mobileCopilotOpen, setMobileCopilotOpen] = useState(false);
  const [isNarrow, setIsNarrow] = useState(false);
  const [composerValue, setComposerValue] = useState("");
  const [planPart, setPlanPart] = useState<DataPlanPart | null>(null);
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
  const identity = memberSnapshot?.identity ?? null;
  const memberName = identity?.name ?? "Member";
  const injury = identity?.injury ?? null;
  const adherence = memberSnapshot?.stats.adherence ?? null;
  const goal = identity?.goals[0] ?? null;

  return (
    <CopilotSidebarProvider prefillMessage={prefillMessage}>
      <div className="app-frame screen-enter">
        <header
          className="app-header"
          inert={isNarrow && mobileCopilotOpen ? true : undefined}
        >
          <div className="global-nav-row">
            <Link
              className="future-wordmark"
              href="/member"
              aria-label="Future Coach dashboard"
            >
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

          <div
            className="member-context-strip"
            aria-label={`${memberName} context`}
          >
            <div className="member-context-item" data-tone="identity">
              <PersonIcon className="member-context-icon" />
              <span>
                {identity === null
                  ? "Member unavailable"
                  : `${identity.name} · ${identity.age}`}
              </span>
            </div>
            <div className="member-context-item" data-tone="attention">
              <KneeIcon className="member-context-icon" />
              <span>{formatInjury(injury)}</span>
              {memberSnapshot === null ? null : (
                <JourneyStageChip journeyStage={memberSnapshot.journey_stage} />
              )}
            </div>
            <div className="member-context-item" data-tone="attention">
              <DumbbellIcon className="member-context-icon" />
              <span>No barbell</span>
            </div>
            <div className="member-context-item" data-tone="attention">
              <TrendIcon className="member-context-icon" />
              <span>{formatAdherence(adherence)}</span>
            </div>
            <div className="member-context-item" data-tone="goal">
              <GoalIcon className="member-context-icon" />
              <span>{goal === null ? "Goal unavailable" : `Goal · ${goal.text}`}</span>
            </div>
          </div>
        </header>

        <div
          className="workspace-split"
          data-mobile-copilot={mobileCopilotOpen ? "open" : "closed"}
        >
          <main
            className="dashboard-canvas"
            inert={isNarrow && mobileCopilotOpen ? true : undefined}
          >
            {children}
            {planPart === null ? null : <SessionPlan part={planPart} />}
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
              <CopilotSidebar
                memberId={member.id}
                memberName={memberName}
                composerValue={composerValue}
                composerRef={composerRef}
                hasPlan={planPart !== null}
                onComposerChange={setComposerValue}
                onPlan={setPlanPart}
              />
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

function formatInjury(
  injury: MemberSnapshotPart["identity"]["injury"],
): string {
  if (injury === null) {
    return "No active MemberInjury";
  }
  return [injury.region, injury.finding, injury.status].filter(Boolean).join(" · ");
}

function formatAdherence(
  adherence: MemberSnapshotPart["stats"]["adherence"] | null,
): string {
  if (adherence?.value === null || adherence === null) {
    return "Adherence unavailable";
  }
  const value = `${adherence.value}${adherence.suffix ?? ""}`;
  const age = adherence.source?.stale
    ? ` · ${formatAge(adherence.source.age_days)} old`
    : "";
  return `Adherence ${value} · ${adherence.trend_text}${age}`;
}

function formatAge(days: number): string {
  if (days < 14) {
    return `${days}d`;
  }
  if (days < 60) {
    return `${Math.floor(days / 7)}w`;
  }
  if (days < 730) {
    return `${Math.floor(days / 30.4375)}mo`;
  }
  return `${Math.floor(days / 365.25)}y`;
}
