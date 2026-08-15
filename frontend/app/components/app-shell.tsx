"use client";

import { Dialog } from "@base-ui/react/dialog";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { formatInjury } from "@/lib/member-format";
import type {
  DashboardMessage,
  DataConstraintsPart,
  DataPlanPart,
  MemberSnapshotPart,
} from "@/lib/parts";
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
  initialCopilotMessages,
}: {
  children: ReactNode;
  memberSnapshot: MemberSnapshotPart | null;
  initialCopilotMessages: DashboardMessage[];
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
  const [constraintsPart, setConstraintsPart] =
    useState<DataConstraintsPart | null>(null);
  const composerRef = useRef<HTMLInputElement>(null);
  const copilotToggleRef = useRef<HTMLButtonElement>(null);
  const copilotCloseRef = useRef<HTMLButtonElement>(null);
  const focusComposerOnOpenRef = useRef(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 980px)");
    const update = () => setIsNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const prefillMessage = useCallback(
    (message: string) => {
      if (isNarrow) {
        focusComposerOnOpenRef.current = true;
        setMobileCopilotOpen(true);
      }
      setComposerValue(message);
      if (!isNarrow) {
        window.requestAnimationFrame(() => composerRef.current?.focus());
      }
    },
    [isNarrow],
  );

  const identity = memberSnapshot?.identity ?? null;
  const memberName = identity?.name ?? "Member";
  const injury = identity?.injury ?? null;
  const adherence = memberSnapshot?.stats.adherence ?? null;
  const sleep = memberSnapshot?.stats.sleep ?? null;
  const sessions = memberSnapshot?.stats.sessions ?? null;
  const churnRisk = memberSnapshot?.stats.churn_risk ?? null;
  const goal = identity?.goals[0] ?? null;
  const acceptPlan = useCallback((part: DataPlanPart) => {
    setConstraintsPart(null);
    setPlanPart(part);
  }, []);

  return (
    <CopilotSidebarProvider
      planPart={planPart}
      constraintsPart={constraintsPart}
      prefillMessage={prefillMessage}
    >
      <Dialog.Root
        open={isNarrow && mobileCopilotOpen}
        onOpenChange={setMobileCopilotOpen}
        onOpenChangeComplete={(open) => {
          if (open) {
            focusComposerOnOpenRef.current = false;
          }
        }}
      >
        <div className="app-frame screen-enter">
          <header className="app-header">
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
              <Dialog.Trigger
                ref={copilotToggleRef}
                className="mobile-copilot-toggle"
                aria-controls="copilot-panel"
              >
                <PanelIcon className="size-4" />
                Copilot
              </Dialog.Trigger>
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
              <div className="member-context-item" data-tone="snapshot">
                <TrendIcon className="member-context-icon" />
                <div className="member-context-stats">
                  <span>{formatAdherence(adherence)}</span>
                  <span>{formatStat("Sleep", sleep)}</span>
                  <span>{formatStat("Sessions", sessions)}</span>
                  <span>{formatStat("Churn risk", churnRisk)}</span>
                </div>
              </div>
              <div className="member-context-item" data-tone="goal">
                <GoalIcon className="member-context-icon" />
                <span>
                  {goal === null ? "Goal unavailable" : `Goal · ${goal.text}`}
                </span>
              </div>
            </div>
          </header>

          <div className="workspace-split">
            <main className="dashboard-canvas">{children}</main>
            {isNarrow ? null : (
              <aside
                id="copilot-panel"
                className="copilot-pane"
                aria-labelledby="copilot-title"
              >
                <div className="copilot-pane-inner">
                  <div className="copilot-heading-row">
                    <h2 id="copilot-title" className="display-title copilot-title">
                      Copilot
                    </h2>
                  </div>
                  <CopilotSidebar
                    memberId={member.id}
                    memberName={memberName}
                    initialMessages={initialCopilotMessages}
                    composerValue={composerValue}
                    composerRef={composerRef}
                    hasPlan={planPart !== null}
                    onComposerChange={setComposerValue}
                    onConstraints={setConstraintsPart}
                    onPlan={acceptPlan}
                  />
                </div>
              </aside>
            )}
          </div>

          {isNarrow ? (
            <Dialog.Portal>
              <Dialog.Backdrop className="copilot-backdrop" />
              <Dialog.Popup
                id="copilot-panel"
                className="copilot-pane"
                aria-labelledby="copilot-title"
                initialFocus={() =>
                  focusComposerOnOpenRef.current
                    ? composerRef.current
                    : copilotCloseRef.current
                }
                finalFocus={copilotToggleRef}
              >
                <div className="copilot-pane-inner">
                  <div className="copilot-heading-row">
                    <Dialog.Title
                      id="copilot-title"
                      className="display-title copilot-title"
                    >
                      Copilot
                    </Dialog.Title>
                    <Dialog.Close
                      ref={copilotCloseRef}
                      className="copilot-close"
                      aria-label="Close Copilot"
                    >
                      <CloseIcon className="size-5" />
                    </Dialog.Close>
                  </div>
                  <CopilotSidebar
                    memberId={member.id}
                    memberName={memberName}
                    initialMessages={initialCopilotMessages}
                    composerValue={composerValue}
                    composerRef={composerRef}
                    hasPlan={planPart !== null}
                    onComposerChange={setComposerValue}
                    onConstraints={setConstraintsPart}
                    onPlan={acceptPlan}
                  />
                </div>
              </Dialog.Popup>
            </Dialog.Portal>
          ) : null}
        </div>
      </Dialog.Root>
    </CopilotSidebarProvider>
  );
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

function formatStat(
  label: string,
  stat: MemberSnapshotPart["stats"][keyof MemberSnapshotPart["stats"]] | null,
): string {
  if (stat?.value === null || stat === null) {
    return `${label} unavailable`;
  }
  const value = `${stat.value}${stat.suffix ?? ""}`;
  const age = stat.source?.stale
    ? ` · ${formatAge(stat.source.age_days)} old`
    : "";
  return `${label} ${value} · ${stat.trend_text}${age}`;
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
